"""
LinkedIn automation module.
Handles browser-based job search and application via Playwright.
"""

import os
import re
import sys
import time
import random
import tempfile
import requests as http_req
from playwright.sync_api import sync_playwright, Page
from automation.human import (
    human_sleep, micro_pause, thinking_pause, reading_pause,
    human_mouse_move, human_click, human_type,
    human_scroll_down, idle_jiggle,
    stealth_launch_args, stealth_context_options, inject_stealth,
)


# ──────────────────────────────────────────────────────────────
# Config — tweak these or pass them in via task input
# ──────────────────────────────────────────────────────────────
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_JOBS_URL  = "https://www.linkedin.com/jobs/"

# How long to wait (seconds) after navigating to a page
NAV_WAIT           = 3
# Max jobs to attempt applying to per run (Easy Apply only)
MAX_APPLY          = 5


# ──────────────────────────────────────────────────────────────
# Retry helpers
# ──────────────────────────────────────────────────────────────
def _safe_goto(page: Page, url: str, max_retries: int = 3) -> bool:
    """Navigate to url with exponential backoff. Returns True on success."""
    for attempt in range(max_retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            return True
        except Exception as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"  [LINKEDIN] Navigation failed (attempt {attempt+1}/{max_retries}): {e} — retrying in {wait}s")
            time.sleep(wait)
    return False


def _retry_click(page: Page, selector: str, max_retries: int = 3) -> bool:
    """Click selector with exponential backoff. Returns True on success."""
    for attempt in range(max_retries):
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=3000):
                btn.click()
                return True
        except Exception as e:
            wait = 2 ** attempt
            if attempt < max_retries - 1:
                print(f"  [LINKEDIN] Click retry {attempt+1}/{max_retries}: {e}")
                time.sleep(wait)
    return False


# ──────────────────────────────────────────────────────────────
# Live-logging helper — no-ops gracefully if task_id absent
# ──────────────────────────────────────────────────────────────
def _log(task_input: dict, msg: str, level: str = "info") -> None:
    """Push a log line to Supabase tasks.logs (best-effort, never raises)."""
    task_id = task_input.get("task_id", "")
    print(f"  [LINKEDIN] {msg}")
    if not task_id:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import push_log
        push_log(task_id, msg, level)
    except Exception:
        pass


def _check_control(task_input: dict) -> dict:
    """
    Fetch pause / stop / custom_prompt_override from Supabase.
    Returns the control dict; pauses the thread here if paused=True.
    """
    task_id = task_input.get("task_id", "")
    if not task_id:
        return {"paused": False, "stop_requested": False, "custom_prompt_override": None}
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import fetch_task_control
        ctrl = fetch_task_control(task_id)
        # If paused — block here and poll every 3 s until unpaused or stopped
        while ctrl.get("paused") and not ctrl.get("stop_requested"):
            time.sleep(3)
            ctrl = fetch_task_control(task_id)
        return ctrl
    except Exception:
        return {"paused": False, "stop_requested": False, "custom_prompt_override": None}


def _set_progress(task_input: dict, progress: int, current_job: str = None) -> None:
    task_id = task_input.get("task_id", "")
    if not task_id:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import update_task_progress
        update_task_progress(task_id, progress, current_job)
    except Exception:
        pass


def _clean_jd_text(raw_text: str) -> str:
    lines = [line.strip() for line in (raw_text or "").splitlines()]
    cleaned: list[str] = []
    seen = set()
    noise_patterns = [
        r"^easy apply$",
        r"^save$",
        r"^share$",
        r"^report this job$",
        r"^sign in to set job alerts",
        r"^set alert for similar jobs$",
        r"^jobs you may be interested in$",
        r"^people also viewed$",
        r"^meet the hiring team$",
        r"^promoted$",
        r"^actively reviewing applicants$",
        r"^over \d+ applicants$",
        r"^see who .* has hired for this role$",
    ]
    stop_patterns = [
        r"^meet the hiring team$",
        r"^people also viewed$",
        r"^jobs you may be interested in$",
        r"^similar jobs$",
        r"^set alert for similar jobs$",
        r"^show all$",
        r"^insights$",
    ]

    started = False
    for line in lines:
        if not line:
            continue
        lower = line.lower()
        if not started and lower in {"about the job", "job description", "about this role"}:
            started = True
        if any(re.search(pattern, lower) for pattern in stop_patterns):
            break
        if any(re.search(pattern, lower) for pattern in noise_patterns):
            continue
        if line in seen and len(line) < 120:
            continue
        seen.add(line)
        cleaned.append(line)

    if started:
        result = "\n".join(cleaned).strip()
        if len(result) > 150:
            return result

    return "\n".join(cleaned).strip()


# ──────────────────────────────────────────────────────────────
# Public entry point called by task_runner.py
# ──────────────────────────────────────────────────────────────
def apply_linkedin_jobs(task_input: dict = None) -> dict:
    """
    Main entry point.
    task_input keys (all optional):
        keywords   str   Job search keywords  e.g. "Software Engineer"
        location   str   Job location         e.g. "Remote"
        max_apply  int   Max applications     default 5
    Returns a result dict: { applied_count, skipped_count, message }
    """
    if task_input is None:
        task_input = {}

    keywords  = task_input.get("keywords", "Software Engineer")
    location  = task_input.get("location", "")
    max_apply = int(task_input.get("max_apply", MAX_APPLY))

    # ── Enrich keywords with top skills from the resume ────────
    resume_text_raw = task_input.get("resume_text", "").strip()
    if resume_text_raw and keywords:
        try:
            from automation.ai_client import analyze_resume
            resume_info = analyze_resume(resume_text_raw)
            top_skills  = resume_info.get("skills", [])[:3]
            # Append skills only if not already present in keywords
            kw_lower = keywords.lower()
            additions = [s for s in top_skills if s.lower() not in kw_lower]
            if additions:
                keywords = f"{keywords} {' '.join(additions)}"
                print(f"  [LINKEDIN] Keywords enriched from resume: {keywords}")
        except Exception:
            pass

    # ── Download resume once for the whole run ─────────────────
    # tailor_resume_for_job needs a local file path (or raw text)
    _resume_tmp_path = ""  # temp file to clean up after run
    if not task_input.get("resume_path"):
        resume_url  = task_input.get("resume_url", "").strip()
        resume_text = task_input.get("resume_text", "").strip()
        if resume_url:
            try:
                resp = http_req.get(resume_url, timeout=30)
                if resp.status_code == 200:
                    filename = task_input.get("resume_filename", "resume.pdf")
                    suffix   = os.path.splitext(filename)[1] or ".pdf"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                        f.write(resp.content)
                        _resume_tmp_path = f.name
                    task_input = dict(task_input)
                    task_input["resume_path"] = _resume_tmp_path
                    print(f"  [LINKEDIN] Resume downloaded to: {_resume_tmp_path}")
                else:
                    print(f"  [LINKEDIN] Resume download failed HTTP {resp.status_code} — will try parsed_text fallback")
            except Exception as dl_err:
                print(f"  [LINKEDIN] Resume download error: {dl_err}")
        if not task_input.get("resume_path") and resume_text:
            # Fall back to writing parsed_text to a temp .txt file so tailor can read it
            with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
                f.write(resume_text)
                _resume_tmp_path = f.name
            task_input = dict(task_input)
            task_input["resume_path"] = _resume_tmp_path
            print(f"  [LINKEDIN] Using parsed_text as resume source: {_resume_tmp_path}")
        if not task_input.get("resume_path") and task_input.get("tailor_resume"):
            print("  [LINKEDIN] ⚠️  Tailor mode requested but no resume available — tailoring will be skipped")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=stealth_launch_args())
        context = browser.new_context(**stealth_context_options())
        page    = context.new_page()
        inject_stealth(page)

        try:
            # ── STEP 1: Login ──────────────────────────────────
            _log(task_input, "Opening LinkedIn login page…")
            result = _login(page, task_input)
            if not result:
                _log(task_input, "Login failed or cancelled", "error")
                return {"applied_count": 0, "skipped_count": 0, "message": "Login failed or cancelled"}

            # ── STEP 2: Search jobs ────────────────────────────
            # Build keyword list (up to 3 sequential keywords)
            _li_kw_list = [
                k.strip() for k in [
                    task_input.get("keywords", ""),
                    task_input.get("keywords2", ""),
                    task_input.get("keywords3", ""),
                ] if k.strip()
            ]
            if not _li_kw_list:
                _li_kw_list = ["Software Engineer"]

            # Compute resume fingerprint for smart_match invalidation
            import hashlib as _li_hashlib
            _li_resume_fp = ""
            _li_resume_text_raw = task_input.get("resume_text", "")
            if _li_resume_text_raw:
                _li_resume_fp = _li_hashlib.md5(_li_resume_text_raw[:500].encode()).hexdigest()[:16]
            elif task_input.get("resume_url", ""):
                _li_resume_fp = _li_hashlib.md5(task_input["resume_url"].encode()).hexdigest()[:16]

            favorite_companies = task_input.get("favorite_companies", [])
            # List of (job_url, company_hint) tuples
            all_jobs: list[tuple[str, str]] = []

            # Build location list — split comma-separated string; empty = anywhere
            _li_loc_list = [
                l.strip() for l in task_input.get("location", "").split(",") if l.strip()
            ] or [""]

            if favorite_companies:
                _log(task_input, f"🏢 Targeting {len(favorite_companies)} favourite companies: {', '.join(favorite_companies)}")
                for company in favorite_companies:
                    for _kw in _li_kw_list:
                        for _li_loc in _li_loc_list:
                            _loc_tag = f" in '{_li_loc}'" if _li_loc else ""
                            _log(task_input, f"🔍 Searching '{_kw}' at {company}{_loc_tag}…")
                            company_jobs = _search_jobs(page, f"{_kw} {company}", _li_loc, task_input)
                            _log(task_input, f"  Found {len(company_jobs)} jobs at {company}{_loc_tag}", "success")
                            for url in company_jobs:
                                all_jobs.append((url, company))
                    if len(all_jobs) >= max_apply * 5:
                        break
            else:
                for _kw in _li_kw_list:
                    for _li_loc in _li_loc_list:
                        _loc_tag = f" in '{_li_loc}'" if _li_loc else " (anywhere)"
                        _log(task_input, f"Searching for '{_kw}'{_loc_tag}…")
                        general_jobs = _search_jobs(page, _kw, _li_loc, task_input)
                        _log(task_input, f"Found {len(general_jobs)} Easy Apply jobs for '{_kw}'{_loc_tag}", "success")
                        all_jobs.extend([(url, "") for url in general_jobs])

            # Deduplicate URLs while preserving company order
            seen_urls: set[str] = set()
            unique_jobs: list[tuple[str, str]] = []
            for url, company_hint in all_jobs:
                if url not in seen_urls:
                    seen_urls.add(url)
                    unique_jobs.append((url, company_hint))

            # ── Filter URLs already seen in previous runs (applied OR skipped) ──
            _li_user_id = task_input.get("user_id", "")
            _li_apply_types = task_input.get("apply_types", "both")
            _li_seen_urls: set = set()
            if _li_user_id:
                try:
                    import sys as _sys_li
                    _sys_li.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
                    from api_client import fetch_seen_jobs as _li_fetch_seen
                    _li_seen_urls = _li_fetch_seen(
                        _li_user_id, "linkedin",
                        apply_types=_li_apply_types,
                        resume_fingerprint=_li_resume_fp,
                    )
                    _li_already_seen = sum(1 for url, _ in unique_jobs if url in _li_seen_urls)
                    if _li_already_seen:
                        _log(task_input, f"Skipping {_li_already_seen} previously-seen job(s) (30-day history)", "warn")
                except Exception as _li_se:
                    _log(task_input, f"Job history unavailable ({_li_se})", "warn")
            unique_jobs = [(url, hint) for url, hint in unique_jobs if url not in _li_seen_urls]

            _set_progress(task_input, 5)

            # ── STEP 3: Apply ──────────────────────────────────
            applied  = 0
            skipped  = 0
            total    = len(unique_jobs)
            for idx, (job_url, company_hint) in enumerate(unique_jobs):
                if applied >= max_apply:
                    break
                # ── Check pause / stop / live custom prompt ────
                ctrl = _check_control(task_input)
                if ctrl.get("stop_requested"):
                    _log(task_input, "Stop requested by user — halting run", "warn")
                    break
                # Allow user to update the custom prompt mid-run
                live_prompt = ctrl.get("custom_prompt_override")
                if live_prompt:
                    task_input = dict(task_input)
                    task_input["tailor_custom_prompt"] = live_prompt

                # Inject current company for tailoring context
                if company_hint:
                    task_input = dict(task_input)
                    task_input["company"] = company_hint

                # Progress: 5 % base + up to 90 % for applications
                progress = 5 + int((applied / max_apply) * 90) if max_apply else 5
                company_tag = f" [{company_hint}]" if company_hint else ""
                _set_progress(task_input, progress, job_url)
                _log(task_input, f"[{applied+1}/{max_apply}]{company_tag} Opening {job_url}")

                success = _apply_to_job(page, job_url, task_input)
                # Record to job history DB (won't revisit for 30 days)
                if _li_user_id:
                    try:
                        from api_client import record_seen_job as _li_record_seen
                        _li_skip_meta: dict = {}
                        if _li_resume_fp:
                            _li_skip_meta["resume_fingerprint"] = _li_resume_fp
                        _li_record_seen(
                            _li_user_id, "linkedin", job_url,
                            status="applied" if success else "skipped",
                            skip_reason="applied" if success else "skipped",
                            metadata=_li_skip_meta,
                        )
                    except Exception:
                        pass
                if success:
                    applied += 1
                    _log(task_input, f"✅ Applied ({applied}/{max_apply})", "success")
                    _record_application(task_input, job_url, company_hint)
                else:
                    skipped += 1
                    _log(task_input, f"⏭  Skipped ({skipped} total) — trying next job", "warn")

            _set_progress(task_input, 100)
            _log(task_input, f"Run complete — applied: {applied}, skipped: {skipped}", "success")
            return {
                "applied_count": applied,
                "skipped_count": skipped,
                "message": f"Applied to {applied} jobs on LinkedIn"
            }

        except Exception as e:
            print(f"  [LINKEDIN] ERROR: {e}")
            raise
        finally:
            browser.close()
            # Clean up the base resume temp file (tailored PDFs are in versioned output dirs)
            if _resume_tmp_path and os.path.isfile(_resume_tmp_path):
                try:
                    os.unlink(_resume_tmp_path)
                except Exception:
                    pass


# ──────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────

def _login(page: Page, task_input: dict = None) -> bool:
    """
    Open the LinkedIn login page.
    - If linkedin_email + linkedin_password are in task_input: auto-fill and sign in.
    - If only linkedin_email: pre-fill the email field; user types password.
    - If neither: wait up to 3 minutes for user to log in manually.
    """
    task_input = task_input or {}
    email    = task_input.get("linkedin_email", "").strip()
    password = task_input.get("linkedin_password", "").strip()

    print("  [LINKEDIN] Opening login page...")
    page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded")
    human_sleep(NAV_WAIT, NAV_WAIT + 2)

    if email:
        try:
            email_input = page.locator("input#username, input[name='session_key']").first
            if email_input.is_visible(timeout=3000):
                human_type(page, email, locator=email_input)
                print(f"  [LINKEDIN] Pre-filled email: {email}")
        except Exception:
            pass

    if email and password:
        try:
            pwd_input = page.locator("input#password, input[name='session_password']").first
            if pwd_input.is_visible(timeout=3000):
                human_sleep(0.4, 1.0)   # natural pause between email → password
                human_type(page, password, locator=pwd_input, typo_rate=0.0)
            human_sleep(0.5, 1.5)       # brief hesitation before clicking Sign In
            sign_in = page.locator("button[type='submit'], button[data-litms-control-urn='login-submit']").first
            if sign_in.is_visible(timeout=2000):
                human_click(page, locator=sign_in)
                print("  [LINKEDIN] Auto-clicked Sign In")
        except Exception:
            pass
    elif email:
        print("  [LINKEDIN] Email pre-filled — please enter password and click Sign In")
    else:
        print("  [LINKEDIN] ============================================")
        print("  [LINKEDIN]  Please log in to LinkedIn in the browser.  ")
        print("  [LINKEDIN]  Waiting automatically — no ENTER needed.   ")
        print("  [LINKEDIN]  (You have 3 minutes to log in)             ")
        print("  [LINKEDIN] ============================================")

    try:
        page.wait_for_url(
            lambda url: "linkedin.com/login" not in url and "linkedin.com/checkpoint" not in url,
            timeout=180_000
        )
        print(f"  [LINKEDIN] Login confirmed ✅  URL: {page.url}")
        return True
    except Exception as e:
        print(f"  [LINKEDIN] Login timed out or failed: {e}")
        return False


def _fill_contact_fields(page: Page, task_input: dict):
    """
    Fill phone country code and phone number fields if they appear in the apply form.
    """
    phone = (task_input or {}).get("phone", "").strip()
    phone_country = (task_input or {}).get("phone_country", "India (+91)").strip()

    if not phone:
        return  # nothing to fill

    try:
        # Phone country code dropdown
        country_sel = page.locator("select[id*='phoneNumber-country']").first
        if country_sel.is_visible(timeout=2000):
            country_sel.select_option(phone_country)
            print(f"  [LINKEDIN] Set phone country: {phone_country}")
    except Exception:
        pass

    try:
        # Phone number input
        phone_input = page.locator("input[id*='phoneNumber-nationalNumber']").first
        if phone_input.is_visible(timeout=2000):
            human_type(page, phone, locator=phone_input)
            print(f"  [LINKEDIN] Filled phone: {phone}")
    except Exception:
        pass


def _click_if_visible(page: Page, selector: str, timeout: int = 2000) -> bool:
    """Move to element naturally then click. Returns True on success."""
    try:
        btn = page.locator(selector).first
        if btn.is_visible(timeout=timeout):
            human_click(page, locator=btn, timeout=timeout)
            return True
    except Exception:
        pass
    return False


def _upload_resume(page: Page, task_input: dict):
    """
    Upload the user's resume to the LinkedIn file input.
    Prefers a local file (task_input["resume_path"]) — which may be the tailored PDF —
    and falls back to downloading from task_input["resume_url"] if needed.
    Skips if a resume is already attached or no resume source is available.
    """
    task_input  = task_input or {}
    resume_path = task_input.get("resume_path", "").strip()
    resume_url  = task_input.get("resume_url", "").strip()

    if not resume_path and not resume_url:
        return

    try:
        # If a resume card is already shown (previously attached), skip uploading
        if page.locator(".jobs-document-card__filename, .ui-attachment__filename").first.is_visible(timeout=1500):
            print("  [LINKEDIN] Resume already attached — skipping upload")
            return
    except Exception:
        pass

    # Find file input
    file_input = page.locator("input[id*='jobs-document-upload-file-input-upload-resume']")
    try:
        if file_input.count() == 0:
            return
    except Exception:
        return

    tmp_path = ""
    try:
        # ── Prefer local file (may already be tailored PDF) ──────
        if resume_path and os.path.isfile(resume_path):
            upload_path = resume_path
            owned_tmp   = False
            print(f"  [LINKEDIN] Uploading local resume: {os.path.basename(resume_path)}")
        else:
            # Fall back: download from Supabase URL
            if not resume_url:
                print("  [LINKEDIN] ⚠️  No resume source available for upload")
                return
            print(f"  [LINKEDIN] Downloading resume for upload…")
            resp = http_req.get(resume_url, timeout=30)
            if resp.status_code != 200:
                print(f"  [LINKEDIN] Resume download failed: HTTP {resp.status_code}")
                return

            filename = task_input.get("resume_filename", "resume.pdf")
            suffix   = os.path.splitext(filename)[1] or ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(resp.content)
                tmp_path  = f.name
            upload_path = tmp_path
            owned_tmp   = True

        file_input.set_input_files(upload_path)
        human_sleep(1.5, 3.0)   # wait for upload processing
        print(f"  [LINKEDIN] ✅ Resume uploaded")
    except Exception as e:
        print(f"  [LINKEDIN] Resume upload error: {e}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def _fill_additional_questions(page: Page, task_input: dict):
    """
    Auto-fill additional application questions.
    Handles: years-of-experience inputs, decimal-with-minimum inputs,
    skill rating inputs, yes/no selects, open text.
    """
    task_input   = task_input or {}
    years        = task_input.get("years_experience", 2)
    skill_rating = float(task_input.get("skill_rating", 8))

    def _parse_min_from_hint(page: Page, input_id: str) -> float | None:
        """Read the aria-describedby hint element and extract minimum value e.g. 'larger than 4.0' → 4.0"""
        if not input_id:
            return None
        try:
            hint_el = page.locator(f"#{input_id}-hint, #{input_id}-error").first
            if hint_el.count() == 0:
                # Try the describedby attribute
                described_by = page.locator(f"#{input_id}").evaluate(
                    "el => el.getAttribute('aria-describedby')"
                ) or ""
                for part in described_by.split():
                    hint_el = page.locator(f"#{part}").first
                    if hint_el.count() > 0:
                        break
            text = hint_el.inner_text()
            m = re.search(r"larger than\s+([\d.]+)", text, re.IGNORECASE)
            if m:
                return float(m.group(1))
        except Exception:
            pass
        return None

    # ── Text / Number inputs ────────────────────────────────────
    try:
        inputs = page.locator(
            "input[type='text']:visible, input[type='number']:visible"
        ).all()
        for inp in inputs:
            try:
                inp_id = inp.get_attribute("id") or ""
                # Skip phone and email inputs
                if "phoneNumber" in inp_id or "email" in inp_id.lower():
                    continue

                val = inp.input_value()
                if val and val.strip():
                    continue  # already filled

                # Get label text for this input
                label_text = ""
                if inp_id:
                    lbl = page.locator(f"label[for='{inp_id}']")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().lower()

                # Check for minimum value from hint text
                min_val = _parse_min_from_hint(page, inp_id)

                # Decide value based on label content
                if any(w in label_text for w in ("skill rating", "rating", "proficiency", "score")):
                    # Skill ratings: use skill_rating (default 8), respect min
                    fill_val = max(skill_rating, (min_val or 0) + 1)
                    human_type(page, str(int(fill_val)), locator=inp)
                    print(f"  [LINKEDIN] Filled skill rating '{label_text[:60]}' = {fill_val}")

                elif any(w in label_text for w in ("month", "months willing", "months you are")):
                    fill_val = max(6.0, (min_val or 0) + 1)
                    human_type(page, str(int(fill_val)), locator=inp)
                    print(f"  [LINKEDIN] Filled months '{label_text[:60]}' = {fill_val}")

                elif any(w in label_text for w in ("hour", "hours per day", "hours willing")):
                    fill_val = max(5.0, (min_val or 0) + 1)
                    human_type(page, str(int(fill_val)), locator=inp)
                    print(f"  [LINKEDIN] Filled hours '{label_text[:60]}' = {fill_val}")

                elif any(w in label_text for w in ("year", "experience", "how long", "how many")):
                    fill_val = max(float(years), (min_val or 0) + 1) if min_val else float(years)
                    human_type(page, str(int(fill_val)), locator=inp)
                    print(f"  [LINKEDIN] Filled years '{label_text[:60]}' = {fill_val}")

                elif any(w in label_text for w in ("notice", "notice period")):
                    fill_val = int(task_input.get("notice_period", 30))
                    if min_val:
                        fill_val = max(fill_val, int(min_val) + 1)
                    human_type(page, str(fill_val), locator=inp)

                elif any(w in label_text for w in ("salary", "ctc", "expected")):
                    sal = str(task_input.get("salary_expectation", ""))
                    if sal:
                        if min_val:
                            sal = str(max(float(sal), min_val + 1))
                        human_type(page, sal, locator=inp)

                else:
                    # Unknown field — try Claude first, then safe numeric default
                    input_type = inp.get_attribute("type") or "text"
                    if input_type == "number" or min_val is not None:
                        fill_val = (min_val or 0) + 1
                        inp.fill(str(int(fill_val)))
                        print(f"  [LINKEDIN] Filled unknown numeric '{label_text[:60]}' = {fill_val}")
                    elif input_type == "text" and label_text:
                        # Use Claude to compose a free-text answer
                        try:
                            from automation.ai_client import claude_answer_question
                            resume_summary = task_input.get("resume_text", "")[:500]
                            answer = claude_answer_question(label_text, [], resume_summary)
                            if answer:
                                human_type(page, answer, locator=inp)
                                print(f"  [LINKEDIN] Claude filled text '{label_text[:60]}' = {answer[:60]}")
                        except Exception:
                            pass
                    # Leave truly unknown fields empty

            except Exception:
                pass
    except Exception:
        pass

    # ── Textarea fields ────────────────────────────────────────
    # Use AI-generated cover note if resume text + JD text are available
    cover_note = task_input.get("cover_note", "")
    if not cover_note:
        resume_text_for_cover = task_input.get("resume_text", "")
        jd_text_for_cover     = task_input.get("_current_jd_text", "")
        company               = task_input.get("company", "")
        role                  = task_input.get("keywords", "")
        if resume_text_for_cover and jd_text_for_cover:
            try:
                from automation.ai_client import generate_cover_letter
                cl_result  = generate_cover_letter(resume_text_for_cover, jd_text_for_cover, company, role)
                cover_note = cl_result.get("intro_message") or cl_result.get("cover_letter", "")
                if cover_note:
                    print("  [LINKEDIN] AI cover note generated")
            except Exception:
                pass
    if not cover_note:
        cover_note = "I am very interested in this role and believe my skills and experience align well with the requirements."
    try:
        textareas = page.locator("textarea:visible").all()
        for ta in textareas:
            try:
                if ta.input_value().strip():
                    continue
                human_type(page, cover_note, locator=ta)
                print("  [LINKEDIN] Filled textarea")
            except Exception:
                pass
    except Exception:
        pass

    # ── Radio buttons ──────────────────────────────────────────
    # LinkedIn hides the actual <input type="radio"> elements with CSS (opacity:0 /
    # visibility:hidden), so :visible filters them out.  We query ALL radios and
    # click their associated <label> instead of the hidden input.
    try:
        # Keywords that should get "No" (visa / sponsorship questions)
        _NO_KEYWORDS = (
            "sponsorship", "require visa", "need visa", "need sponsorship",
            "require sponsorship", "do you need", "will you require",
        )
        # Keywords that should get "Yes" (all other yes/no questions)
        _YES_KEYWORDS = (
            "authorized", "authorised", "eligible", "legally",
            "work authorization", "work authorisation",
            "start immediately", "immediately", "urgently",
            "can you start", "available immediately",
            "background check", "drug test", "agree",
        )

        # Collect ALL radio inputs (including CSS-hidden ones)
        radios = page.locator("input[type='radio']").all()

        # Build a map: group_name → list of (radio_element, label_text, value)
        groups: dict[str, list] = {}
        for r in radios:
            try:
                name = r.get_attribute("name") or r.get_attribute("id") or ""
                val  = (r.get_attribute("value") or "").strip()
                inp_id = r.get_attribute("id") or ""
                label_text = ""
                # Try label[for=id]
                if inp_id:
                    lbl = page.locator(f"label[for='{inp_id}']")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().strip()
                # Fallback: parent label
                if not label_text:
                    try:
                        label_text = r.evaluate(
                            "el => el.closest('label') ? el.closest('label').innerText : ''"
                        ) or ""
                    except Exception:
                        pass
                if name not in groups:
                    groups[name] = []
                groups[name].append((r, label_text.lower(), val.lower(), inp_id))
            except Exception:
                pass

        for name, options in groups.items():
            try:
                # Skip already-answered groups
                if any(r.is_checked() for r, _, _, _ in options):
                    continue

                # Get the question text from the fieldset legend or nearby heading
                question_text = ""
                try:
                    question_text = options[0][0].evaluate(
                        """el => {
                            const fs = el.closest('fieldset');
                            if (fs) {
                                const leg = fs.querySelector('legend');
                                if (leg) return leg.innerText;
                            }
                            // Walk up to find a heading/label sibling
                            let p = el.parentElement;
                            for (let i = 0; i < 6; i++) {
                                if (!p) break;
                                const h = p.querySelector('h3,h4,label,span.fb-form-element__label,legend');
                                if (h && h.innerText.length > 3) return h.innerText;
                                p = p.parentElement;
                            }
                            return '';
                        }"""
                    ) or ""
                    question_text = question_text.lower()
                except Exception:
                    pass

                # Decide: should this group get "Yes" or "No"?
                want_no = any(kw in question_text for kw in _NO_KEYWORDS)
                want_yes = not want_no  # default is Yes for all other questions

                # Find the target option
                target_radio, target_label_id = None, None
                # First pass: find Yes or No option matching intent
                for r, lbl, val, inp_id in options:
                    is_yes = val in ("yes", "true", "1") or lbl in ("yes",)
                    is_no  = val in ("no", "false", "0") or lbl in ("no",)
                    if want_yes and is_yes:
                        target_radio, target_label_id = r, inp_id
                        break
                    if want_no and is_no:
                        target_radio, target_label_id = r, inp_id
                        break

                # Fallback: first option in the group
                if target_radio is None and options:
                    target_radio, _, _, target_label_id = options[0]

                if target_radio is None:
                    continue

                # Click the <label> (visible) rather than the hidden <input>
                clicked = False
                if target_label_id:
                    try:
                        lbl_el = page.locator(f"label[for='{target_label_id}']").first
                        if lbl_el.count() > 0:
                            lbl_el.click(timeout=3000)
                            clicked = True
                    except Exception:
                        pass

                if not clicked:
                    # Try clicking the input directly (works when not fully hidden)
                    try:
                        target_radio.click(timeout=3000)
                        clicked = True
                    except Exception:
                        pass

                if not clicked:
                    # Force-click via JS as last resort
                    try:
                        target_radio.evaluate("el => el.click()")
                        clicked = True
                    except Exception:
                        pass

                if clicked:
                    answer = "No" if want_no else "Yes"
                    q_preview = question_text[:60] if question_text else name
                    print(f"  [LINKEDIN] Radio → '{answer}' for: {q_preview!r}")
                    micro_pause()

            except Exception:
                pass
    except Exception:
        pass

    # ── Select dropdowns ───────────────────────────────────────
    try:
        selects = page.locator("select:visible").all()
        for sel in selects:
            try:
                sel_id = sel.get_attribute("id") or ""
                if "phoneNumber-country" in sel_id:
                    continue

                # Auto-select single email option
                if "multipleChoice" in sel_id and "email" in sel_id.lower():
                    opts = sel.locator("option:not([value='Select an option'])").all()
                    if len(opts) == 1:
                        v = opts[0].get_attribute("value")
                        if v:
                            sel.select_option(v)
                    continue

                current = sel.evaluate("el => el.value")
                if current and current.lower() not in ("", "select an option", "none"):
                    continue

                # ── Get the question label for this select ──────────────
                question_text = ""
                if sel_id:
                    try:
                        lbl = page.locator(f"label[for='{sel_id}']")
                        if lbl.count() > 0:
                            question_text = lbl.first.inner_text().lower()
                    except Exception:
                        pass
                if not question_text:
                    try:
                        question_text = sel.evaluate(
                            """el => {
                                let p = el.parentElement;
                                for (let i = 0; i < 6; i++) {
                                    if (!p) break;
                                    const h = p.querySelector('label,legend,h3,h4,span.fb-form-element__label');
                                    if (h && h.innerText.trim().length > 2) return h.innerText.trim();
                                    p = p.parentElement;
                                }
                                return '';
                            }"""
                        ) or ""
                        question_text = question_text.lower()
                    except Exception:
                        pass

                opts = sel.locator("option").all()
                opt_vals  = [(o.get_attribute("value") or "").strip() for o in opts]
                opt_texts = [(o.inner_text() or "").strip().lower() for o in opts]

                # Blank/placeholder values to skip
                _SKIP_VALS = {"", "select an option", "none", "please select", "select"}

                def _pick(preferred_texts: list[str]) -> bool:
                    """Try to select an option whose text contains any preferred keyword."""
                    for kw in preferred_texts:
                        for i, t in enumerate(opt_texts):
                            if kw in t and opt_vals[i].lower() not in _SKIP_VALS:
                                sel.select_option(opt_vals[i])
                                print(f"  [LINKEDIN] Dropdown '{question_text[:50]}' → '{opt_texts[i]}'")
                                return True
                    return False

                # ── Question-specific logic ─────────────────────────────

                # Language / proficiency dropdowns → pick a strong level
                if any(w in question_text for w in (
                    "proficiency", "language", "fluency", "english", "hindi",
                    "speak", "linguistic",
                )):
                    _pick([
                        "native or bilingual", "full professional",
                        "professional working", "limited working", "elementary",
                    ])

                # Sponsorship / work auth needs "No" or "I don't need"
                elif any(w in question_text for w in (
                    "sponsorship", "require visa", "need visa", "require work",
                )):
                    if not _pick(["no", "i don't need", "not required", "citizen", "authorized"]):
                        # fallback first valid
                        for i, v in enumerate(opt_vals):
                            if v.lower() not in _SKIP_VALS:
                                sel.select_option(v)
                                break

                # Yes/No questions → Yes
                elif any(w in question_text for w in (
                    "authorized", "eligible", "legally", "work authorization",
                    "background check", "drug test", "agree", "start immediately",
                    "can you start",
                )):
                    if not _pick(["yes"]):
                        for i, v in enumerate(opt_vals):
                            if v.lower() not in _SKIP_VALS:
                                sel.select_option(v)
                                break

                # Gender / diversity dropdowns → "Prefer not to say"
                elif any(w in question_text for w in ("gender", "ethnicity", "race", "disability", "veteran")):
                    if not _pick(["prefer not", "decline", "do not wish", "not specified"]):
                        for i, v in enumerate(opt_vals):
                            if v.lower() not in _SKIP_VALS:
                                sel.select_option(v)
                                break

                # Generic Yes/No dropdown
                elif opt_texts and set(t for t in opt_texts if t not in _SKIP_VALS) <= {"yes", "no"}:
                    _pick(["yes"])

                # Fallback: first valid non-None option
                else:
                    # Try Claude for ambiguous questions before falling back to first-option
                    if question_text and len(opts) > 1:
                        non_blank = [o for o in opt_texts if o.lower() not in _SKIP_VALS]
                        if non_blank:
                            try:
                                from automation.ai_client import claude_answer_question
                                resume_summary = task_input.get("resume_text", "")[:500]
                                answer = claude_answer_question(question_text, non_blank, resume_summary)
                                matched = False
                                for i, t in enumerate(opt_texts):
                                    if t == answer.lower() and opt_vals[i].lower() not in _SKIP_VALS:
                                        sel.select_option(opt_vals[i])
                                        print(f"  [LINKEDIN] Claude dropdown '{question_text[:50]}' → '{t}'")
                                        matched = True
                                        break
                                if not matched:
                                    raise ValueError("no match")
                            except Exception:
                                for i, v in enumerate(opt_vals):
                                    if v.lower() not in _SKIP_VALS:
                                        sel.select_option(v)
                                        print(f"  [LINKEDIN] Dropdown fallback '{question_text[:50]}' → '{opt_texts[i]}'")
                                        break
                    else:
                        for i, v in enumerate(opt_vals):
                            if v.lower() not in _SKIP_VALS:
                                sel.select_option(v)
                                print(f"  [LINKEDIN] Dropdown fallback '{question_text[:50]}' → '{opt_texts[i]}'")
                                break

            except Exception:
                pass
    except Exception:
        pass


def _fill_all_fields(page: Page, task_input: dict):
    """Fill all fillable fields on the current form step."""
    _fill_contact_fields(page, task_input)
    _upload_resume(page, task_input)
    _fill_additional_questions(page, task_input)


def _close_modal(page: Page):
    """Close the Easy Apply modal and confirm discard if prompted."""
    for sel in [
        "button[aria-label='Dismiss']",
        "button[aria-label='Cancel']",
        "button:has-text('×')",
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                human_click(page, locator=btn)
                micro_pause()
                # Confirm discard popup if it appears
                _click_if_visible(page, "button:has-text('Discard')", timeout=1500)
                return
        except Exception:
            pass


def _record_application(task_input: dict, job_url: str, company_hint: str = "") -> None:
    """Persist a successful application to Supabase (fire-and-forget, never raises)."""
    user_id = task_input.get("user_id", "")
    if not user_id:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import record_application
        company = company_hint or task_input.get("company", "Unknown Company")
        role    = task_input.get("keywords", "Position")
        followup_days = int(task_input.get("followup_days", 3))
        ats_score = task_input.get("_last_match_score")
        record_application(
            user_id=user_id,
            company=company,
            role=role,
            job_url=job_url,
            followup_days=followup_days,
            ats_score=int(ats_score) if ats_score is not None else None,
        )
    except Exception as e:
        print(f"  [LINKEDIN] Could not record application: {e}")


def _dismiss_post_apply_modal(page: Page):
    """Dismiss the post-apply modal (any variant LinkedIn may show)."""
    for sel in [
        "button:has-text('Not now')",
        "button[aria-label='Not now']",
        "button:has-text('Done')",
        "button[aria-label='Done']",
        "button:has-text('Dismiss')",
        "button[aria-label='Dismiss']",
        "button[aria-label='Close']",
        "button.artdeco-modal__dismiss",
        "button[data-test-modal-close-btn]",
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                human_click(page, locator=btn)
                print("  [LINKEDIN] Dismissed post-apply modal")
                human_sleep(0.5, 1.5)
                return
        except Exception:
            pass


def _search_jobs(page: Page, keywords: str, location: str, task_input: dict = None) -> list[str]:
    """
    Navigate to the jobs search URL with keywords, location, Easy Apply filter,
    and any user-specified filters, then return a deduplicated list of job detail URLs.
    Paginates through multiple pages until enough jobs are gathered.
    """
    import urllib.parse
    task_input = task_input or {}
    print(f"  [LINKEDIN] Searching: '{keywords}' in '{location}'")

    # ── Build filter params ─────────────────────────────────────────────
    params: dict[str, str] = {
        "keywords": keywords,
        "location": location,
        "f_AL":     "true",   # Easy Apply only
        "sortBy":   "DD",     # Most recent
    }

    # Date posted: f_TPR  (r86400 = last 24h, r604800 = last week, r2592000 = last month)
    _DATE_MAP = {
        "past24h":   "r86400",
        "pastWeek":  "r604800",
        "pastMonth": "r2592000",
    }
    date_posted = task_input.get("linkedin_date_posted", "any")
    if date_posted in _DATE_MAP:
        params["f_TPR"] = _DATE_MAP[date_posted]

    # Remote filter: f_WT=2  (1=onsite, 2=remote, 3=hybrid)
    if task_input.get("linkedin_remote"):
        params["f_WT"] = "2"

    # Experience level: f_E  (1=Internship, 2=Entry, 3=Associate, 4=Mid-Senior, 5=Director, 6=Executive)
    _EXP_MAP = {
        "internship": "1",
        "entry":      "2",
        "associate":  "3",
        "mid":        "4",
        "director":   "5",
        "executive":  "6",
    }
    exp_level = task_input.get("linkedin_exp_level", "all")
    if exp_level in _EXP_MAP:
        params["f_E"] = _EXP_MAP[exp_level]

    # Job type: f_JT  (F=Full-time, P=Part-time, C=Contract, T=Temporary, I=Internship, V=Volunteer)
    _JOBTYPE_MAP = {
        "fullTime":   "F",
        "partTime":   "P",
        "contract":   "C",
        "temporary":  "T",
        "internship": "I",
        "volunteer":  "V",
    }
    job_type = task_input.get("linkedin_job_type", "all")
    if job_type in _JOBTYPE_MAP:
        params["f_JT"] = _JOBTYPE_MAP[job_type]

    base_url = "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)

    # ── Pagination ─────────────────────────────────────────────────────
    max_apply   = int(task_input.get("max_apply", MAX_APPLY))
    target_pool = max_apply * 3   # fetch 3× so skips don't exhaust the list
    max_pages   = 10
    seen: set   = set()
    job_links: list[str] = []

    for page_num in range(max_pages):
        start = page_num * 25
        search_url = f"{base_url}&start={start}"
        print(f"  [LINKEDIN] Page {page_num + 1} URL: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded")
        human_sleep(NAV_WAIT + 1, NAV_WAIT + 4)
        human_scroll_down(page, steps=random.randint(2, 4))   # browse-style scroll

        before = len(job_links)
        try:
            cards = page.locator(
                "a.job-card-container__link, a.job-card-list__title, a[href*='/jobs/view/']"
            ).all()
            for card in cards:
                href = card.get_attribute("href") or ""
                if "/jobs/view/" in href:
                    if href.startswith("/"):
                        href = "https://www.linkedin.com" + href
                    url = href.split("?")[0]
                    if url not in seen:
                        seen.add(url)
                        job_links.append(url)
        except Exception as e:
            print(f"  [LINKEDIN] Could not collect job links on page {page_num + 1}: {e}")

        added = len(job_links) - before
        print(f"  [LINKEDIN] Page {page_num + 1}: +{added} new links (total {len(job_links)})")

        if added == 0:
            print(f"  [LINKEDIN] No new jobs on page {page_num + 1} — stopping pagination")
            break

        if len(job_links) >= target_pool:
            print(f"  [LINKEDIN] Pool of {len(job_links)} sufficient — stopping pagination")
            break

    print(f"  [LINKEDIN] Found {len(job_links)} job links (across {page_num + 1} page(s))")
    return job_links


def _apply_to_job(page: Page, job_url: str, task_input: dict = None) -> bool:
    """
    Complete Easy Apply flow for one job.
    Handles: contact info, resume upload, additional questions, Review, Submit, post-apply modal.
    Returns True if submitted, False if skipped.
    """
    task_input = task_input or {}
    print(f"  [LINKEDIN] Opening: {job_url}")
    if not _safe_goto(page, job_url):
        print(f"  [LINKEDIN] Could not load job page after retries — skipping")
        return False
    human_sleep(NAV_WAIT, NAV_WAIT + 2)

    try:
        # ── Skip if already applied ───────────────────────────────
        try:
            if page.locator(
                "button[aria-label*='Applied'], "
                ".jobs-s-apply__application-link--applied, "
                "span:has-text('Applied')"
            ).first.is_visible(timeout=2000):
                print("  [LINKEDIN] Already applied — skipping")
                return False
        except Exception:
            pass

        # ── Extract JD text (needed for smart match and/or tailoring) ─
        smart_match     = task_input.get("smart_match", False)
        match_threshold = int(task_input.get("match_threshold", 70))
        needs_jd        = smart_match or task_input.get("tailor_resume", False)
        jd_text         = ""

        if needs_jd:
            human_sleep(1.5, 3.0)
            # Expand "Show more" so full JD is in DOM
            for expand_sel in [
                "button.jobs-description__footer-button",
                "button[aria-label*='Show more']",
                "button.show-more-less-html__button--more",
                "button:has-text('Show more')",
            ]:
                try:
                    btn = page.locator(expand_sel).first
                    if btn.count() > 0:
                        human_click(page, locator=btn, timeout=2000)
                        micro_pause()
                        break
                except Exception:
                    pass

            for jd_sel in [
                "div.jobs-description-content__text",
                "div.jobs-description-content__text--stretch",
                "div[class*='jobs-description-content']",
                "div.jobs-unified-description__content",
                "div[class*='jobs-unified-description']",
                "div.show-more-less-html__markup",
                "div.jobs-description__content",
                "div[class*='jobs-description']",
                "article.jobs-description",
                "div#job-details",
                "div.description__text",
                "section.jobs-view-more-text",
                "div[data-testid='job-description']",
                "div.description",
            ]:
                try:
                    el = page.locator(jd_sel).first
                    if el.count() > 0:
                        try:
                            el.scroll_into_view_if_needed(timeout=2000)
                        except Exception:
                            pass
                        candidate = _clean_jd_text(el.text_content() or "")
                        if len(candidate) > 100:
                            jd_text = candidate
                            break
                except Exception:
                    continue

            # Simulate reading the job description
            if jd_text:
                reading_pause(min(len(jd_text), 1200))

            if not jd_text:
                for fallback_sel in ["main", "div[role='main']", "div.scaffold-layout__detail"]:
                    try:
                        el = page.locator(fallback_sel).first
                        if el.count() > 0:
                            candidate = _clean_jd_text(el.text_content() or "")
                            if len(candidate) > 200:
                                jd_text = candidate[:8000]
                                break
                    except Exception:
                        continue

        # ── Smart match gate ──────────────────────────────────────
        if smart_match and jd_text:
            resume_text = task_input.get("resume_text", "")
            if resume_text:
                try:
                    from automation.ai_client import match_score
                    result = match_score(resume_text, jd_text)
                    score  = result.get("score", 0)
                    missing = result.get("missing_skills", [])
                    _log(task_input,
                         f"🎯 Match score: {score}% (threshold: {match_threshold}%) "
                         f"| Missing: {', '.join(missing[:4]) or 'none'}",
                         "info")
                    if score < match_threshold:
                        _log(task_input,
                             f"⏭  Skipped (score {score}% < {match_threshold}%) — {job_url}",
                             "warn")
                        return False
                    _log(task_input, f"✅ Match score {score}% passed — proceeding to apply", "success")
                    task_input = dict(task_input)
                    task_input["_last_match_score"] = score
                except Exception as _me:
                    _log(task_input, f"⚠️  Match scoring failed ({_me}) — applying anyway", "warn")
            else:
                _log(task_input, "⚠️  Smart match skipped — no resume text available", "warn")

        # Store jd_text in task_input so _fill_additional_questions can use it for AI cover note
        if jd_text:
            task_input = dict(task_input)
            task_input["_current_jd_text"] = jd_text

        # ── Tailor resume to this JD if requested ─────────────────
        if task_input.get("tailor_resume"):
            resume_path = task_input.get("resume_path", "")
            if not resume_path or not os.path.isfile(resume_path):
                _log(task_input, "⚠️  No resume file available — applying without tailoring. Upload a resume to enable tailoring.", "warn")
            elif jd_text.strip():
                    try:
                        from automation.resume_tailor import tailor_resume_for_job
                        company       = task_input.get("company", "")
                        role          = task_input.get("role", task_input.get("keywords", ""))
                        custom_prompt = task_input.get("tailor_custom_prompt", "")
                        _log(task_input, f"✨ Tailoring resume for {role or 'this role'} at {company or 'this company'}…")
                        result = tailor_resume_for_job(
                            resume_source=resume_path,
                            jd_text=jd_text,
                            custom_prompt=custom_prompt,
                            company=company,
                            role=role,
                            save_pdf=True,
                        )
                        _log(
                            task_input,
                            f"Match score: {result.score_before:.0f}% → {result.score_after:.0f}%  ATS: {result.ats_score}",
                            "success",
                        )
                        if result.tailored_pdf_path and os.path.isfile(result.tailored_pdf_path):
                            task_input = dict(task_input)
                            task_input["resume_path"]   = result.tailored_pdf_path
                            task_input["_tailored_pdf"] = result.tailored_pdf_path
                    except Exception as _te:
                        _log(task_input, f"⚠️  Tailoring failed ({_te}) — applying with original resume", "warn")
            else:
                _log(task_input, "⚠️  Could not extract JD text — applying with original resume", "warn")

        # ── Find Easy Apply link/button ───────────────────────────
        easy_apply_btn = None
        for sel in [
            "a[aria-label='Easy Apply to this job']",
            "a[aria-label*='Easy Apply']",
            "#jobs-apply-button-id",
            "button[aria-label*='Easy Apply']",
            "button.jobs-apply-button",
            "button:has-text('Easy Apply')",
            ":is(a, button):has-text('Easy Apply')",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    easy_apply_btn = btn
                    print(f"  [LINKEDIN] Easy Apply via: {sel}")
                    break
            except Exception:
                continue

        if easy_apply_btn is None:
            print(f"  [LINKEDIN] No Easy Apply button — skipping")
            return False

        human_click(page, locator=easy_apply_btn)
        idle_jiggle(page, duration=random.uniform(3.0, 5.5))   # jiggle while modal loads

        # ── Multi-step apply loop (up to 10 steps) ────────────────
        for step in range(10):
            human_sleep(2.0, 3.5)
            print(f"  [LINKEDIN] Form step {step + 1}")

            # Fill every visible field on this step
            _fill_all_fields(page, task_input)
            human_sleep(1.0, 2.5)  # let validation re-evaluate

            semi_auto    = task_input.get("semi_auto", False)
            _SUBMIT_SEL  = ("button[aria-label='Submit application'], "
                            "button[data-live-test-easy-apply-submit-button]")
            _REVIEW_SEL  = ("button[aria-label='Review your application'], "
                            "button[data-live-test-easy-apply-review-button]")

            # ── helper: submit or pause for semi-auto ─────────────
            def _do_submit(label: str) -> bool:
                if semi_auto:
                    print(f"  [LINKEDIN] [SEMI-AUTO] ⏸  {label} — "
                          "All fields filled. Please review and click Submit in the browser.")
                    # Poll every 2 s for up to 5 min — catches any LinkedIn post-submit UI
                    _POST_SUBMIT_SELECTORS = [
                        # Success headings (various LinkedIn wordings)
                        "h2:has-text('application was sent')",
                        "h2:has-text('application was submitted')",
                        "h2:has-text('Application submitted')",
                        "h3:has-text('application was sent')",
                        "h3:has-text('Application submitted')",
                        "[class*='post-apply']",
                        # Post-apply action buttons
                        "button:has-text('Not now')",
                        "button[aria-label='Not now']",
                        "button:has-text('Done')",
                        "button[aria-label='Done']",
                        "button:has-text('Dismiss')",
                        "button[aria-label='Dismiss']",
                        # The Easy Apply modal closes — form container disappears
                        "div.jobs-easy-apply-content",
                    ]
                    deadline = time.time() + 300  # 5-minute max wait
                    detected = False
                    # First check: wait for the Submit button to disappear
                    # (means user clicked it and LinkedIn advanced past it)
                    try:
                        page.wait_for_selector(_SUBMIT_SEL, state="detached", timeout=300_000)
                        detected = True
                    except Exception:
                        pass
                    if not detected:
                        # Fallback: poll for any success indicator
                        while time.time() < deadline:
                            for sel in _POST_SUBMIT_SELECTORS:
                                try:
                                    if page.locator(sel).first.is_visible(timeout=500):
                                        detected = True
                                        break
                                except Exception:
                                    pass
                            if detected:
                                break
                            time.sleep(2)
                    if detected:
                        print("  [LINKEDIN] [SEMI-AUTO] ✅ Submission detected!")
                        _dismiss_post_apply_modal(page)
                        return True
                    else:
                        print("  [LINKEDIN] [SEMI-AUTO] Timed out — skipping this job")
                        _close_modal(page)
                        return False
                else:
                    submit_btn = page.locator(_SUBMIT_SEL).first
                    human_sleep(0.5, 1.5)  # last-second hesitation before submit
                    human_click(page, locator=submit_btn)
                    human_sleep(2.5, 4.5)
                    print(f"  [LINKEDIN] ✅ {label}")
                    _dismiss_post_apply_modal(page)
                    return True

            # Priority 1: Submit application (final step)
            try:
                submit_visible = page.locator(_SUBMIT_SEL).first.is_visible(timeout=2500)
            except Exception:
                submit_visible = False

            if submit_visible:
                return _do_submit("Submitted!")

            # Priority 2: Review your application (second-to-last step)
            if _click_if_visible(page, _REVIEW_SEL, timeout=2500):
                time.sleep(2.5)
                _fill_all_fields(page, task_input)
                time.sleep(1)
                try:
                    submit_visible_after_review = page.locator(_SUBMIT_SEL).first.is_visible(timeout=2500)
                except Exception:
                    submit_visible_after_review = False
                if submit_visible_after_review:
                    return _do_submit("Submitted after Review!")
                continue  # re-check buttons on next iteration

            # Priority 3: Next step
            if _click_if_visible(page,
                "button[aria-label='Continue to next step'], "
                "button[data-easy-apply-next-button], "
                "button[data-live-test-easy-apply-next-button], "
                "button:has-text('Next')",
                timeout=3000):
                continue  # go to next step

            # No button found — stuck
            print(f"  [LINKEDIN] No actionable button on step {step + 1} — aborting")
            break

    except Exception as e:
        print(f"  [LINKEDIN] Apply error on {job_url}: {e}")
        import traceback; traceback.print_exc()

    _close_modal(page)
    # Clean up temp tailored PDF (it lives in the versioned output dir — keep it)
    return False
