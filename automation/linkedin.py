"""
LinkedIn automation module.
Handles browser-based job search and application via Playwright.
"""

import os
import re
import sys
import time
import base64
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
def _log(task_input: dict, msg: str, level: str = "info", category: str = "system", meta: dict = None) -> None:
    """Push a structured log line to Supabase tasks.logs (best-effort, never raises)."""
    task_id = task_input.get("task_id", "")
    print(f"  [LINKEDIN] {msg}")
    if not task_id:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import push_log
        push_log(task_id, msg, level, category, meta)
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


def _request_approval(task_input: dict, page: Page, job_title: str, company: str, job_url: str) -> bool:
    """
    For TAILOR_AND_APPLY (semi_auto) mode: pause and wait for Supabase-based user approval
    before the bot clicks the final Submit button.
    Returns True  → proceed with submit.
    Returns False → skip this job.
    For AUTO_APPLY (semi_auto=False): always returns True immediately.
    """
    if not task_input.get("semi_auto", False):
        return True   # Auto mode — submit without pausing

    task_id = task_input.get("task_id", "")
    if not task_id:
        return True   # No task tracking — just submit

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import set_waiting_approval, poll_approval_decision

        _log(task_input,
             f"⏸ Waiting for your approval — {company} — {job_title}",
             "warning", "approval",
             {"company": company, "job_title": job_title, "url": job_url})

        # Screenshot the filled form
        try:
            screenshot_bytes = page.screenshot(type="jpeg", quality=60)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
        except Exception:
            screenshot_b64 = None

        import datetime as _dt
        payload = {
            "job_title":      job_title,
            "company":        company,
            "url":            job_url,
            "screenshot_b64": screenshot_b64,
            "waiting_since":  _dt.datetime.utcnow().isoformat(),
        }
        set_waiting_approval(task_id, payload)

        decision = poll_approval_decision(task_id, timeout_seconds=300)

        if decision == "approved":
            _log(task_input,
                 f"✅ Approved — submitting {company} — {job_title}",
                 "success", "approval",
                 {"company": company, "job_title": job_title})
            return True
        elif decision == "timeout":
            _log(task_input,
                 f"⏭ Auto-skipped (no response in 5 min) — {company} — {job_title}",
                 "skip", "approval",
                 {"company": company, "job_title": job_title, "skip_reason": "approval_timeout"})
            return False
        else:
            _log(task_input,
                 f"⏭ Skipped by user — {company} — {job_title}",
                 "skip", "approval",
                 {"company": company, "job_title": job_title, "skip_reason": "user_skipped"})
            return False

    except Exception as _e:
        _log(task_input, f"⚠️ Approval flow error ({_e}) — submitting anyway", "warning", "approval")
        return True


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
            print("  [LINKEDIN] Enriching keywords from resume…")
            from automation.ai_client import analyze_resume
            resume_info = analyze_resume(resume_text_raw)
            top_skills  = resume_info.get("skills", [])[:3]
            # Append skills only if not already present in keywords
            kw_lower = keywords.lower()
            additions = [s for s in top_skills if s.lower() not in kw_lower]
            if additions:
                keywords = f"{keywords} {' '.join(additions)}"
                print(f"  [LINKEDIN] Keywords enriched from resume: {keywords}")
        except Exception as e:
            print(f"  [LINKEDIN] Keyword enrichment skipped ({e})")

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

    print("  [LINKEDIN] Launching browser…")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=stealth_launch_args())
        context = browser.new_context(**stealth_context_options())
        page    = context.new_page()
        inject_stealth(page)
        print("  [LINKEDIN] Browser launched ✅")

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

            # ── Direct URL mode: skip keyword search if specific_urls provided ──
            _li_specific_urls_mode = bool(task_input.get("specific_urls", []))

            if favorite_companies and not _li_specific_urls_mode:
                _log(task_input, f"🏢 Targeting {len(favorite_companies)} favourite companies: {', '.join(favorite_companies)}", "info", "search", {"count": len(favorite_companies)})
                for company in favorite_companies:
                    for _kw in _li_kw_list:
                        for _li_loc in _li_loc_list:
                            _loc_tag = f" in '{_li_loc}'" if _li_loc else ""
                            _log(task_input, f"Searching '{_kw}' at {company}{_loc_tag}…", "info", "search", {"job_title": _kw, "company": company})
                            company_jobs = _search_jobs(page, f"{_kw} {company}", _li_loc, task_input)
                            _log(task_input, f"Found {len(company_jobs)} jobs at {company}{_loc_tag}", "success", "search", {"company": company, "count": len(company_jobs)})
                            for url in company_jobs:
                                all_jobs.append((url, company))
                    if len(all_jobs) >= max_apply * 5:
                        break
            elif not _li_specific_urls_mode:
                for _kw in _li_kw_list:
                    for _li_loc in _li_loc_list:
                        _loc_tag = f" in '{_li_loc}'" if _li_loc else " (anywhere)"
                        _log(task_input, f"Searching for '{_kw}'{_loc_tag}…", "info", "search", {"job_title": _kw})
                        general_jobs = _search_jobs(page, _kw, _li_loc, task_input)
                        _log(task_input, f"Found {len(general_jobs)} Easy Apply jobs for '{_kw}'{_loc_tag}", "success", "search", {"job_title": _kw, "count": len(general_jobs)})
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
                        _log(task_input, f"Skipping {_li_already_seen} previously-seen job(s) (30-day history)", "warning", "skip", {"count": _li_already_seen, "skip_reason": "already_seen"})
                except Exception as _li_se:
                    _log(task_input, f"Job history unavailable ({_li_se})", "warning", "system")
            unique_jobs = [(url, hint) for url, hint in unique_jobs if url not in _li_seen_urls]

            # ── Direct URL mode: replace search results with specific_urls ──────
            if _li_specific_urls_mode:
                _raw_urls = task_input.get("specific_urls", [])
                _log(task_input, f"🔗 Manual URL mode — {len(_raw_urls)} URL(s) to process directly", "info", "system", {"count": len(_raw_urls)})
                seen_urls = set()
                unique_jobs = [(u.strip(), "") for u in _raw_urls if u.strip()]

            _set_progress(task_input, 5)

            # ── STEP 3: Apply ──────────────────────────────────
            applied  = 0
            skipped  = 0
            total    = len(unique_jobs)
            _exhausted_pool = False   # flag: pool ran out before hitting max_apply
            for idx, (job_url, company_hint) in enumerate(unique_jobs):
                if applied >= max_apply:
                    break
                # ── Check pause / stop / live custom prompt ────
                ctrl = _check_control(task_input)
                if ctrl.get("stop_requested"):
                    _log(task_input, "Stop requested by user — halting run", "warning", "system")
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
                _log(task_input, f"Opening job page", "info", "navigation", {"company": company_hint, "url": job_url})

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
                    _log(task_input, f"Applied — {company_hint or 'LinkedIn'} ({applied}/{max_apply})", "success", "submit", {"company": company_hint, "url": job_url})
                    _record_application(task_input, job_url, company_hint)
                else:
                    skipped += 1
                    _log(task_input, f"Skipped job ({skipped} total) — trying next", "skip", "skip", {"company": company_hint, "url": job_url})
            else:
                # The for loop finished without break → pool exhausted
                if applied < max_apply:
                    _exhausted_pool = True

            # ── If pool exhausted, search for more jobs and continue ──
            if _exhausted_pool and applied < max_apply:
                _log(task_input, f"Pool of {total} jobs exhausted (applied {applied}/{max_apply}) — searching for more…", "warning", "search")
                # Search next pages with larger offset
                extra_jobs: list[tuple[str, str]] = []
                for _kw in _li_kw_list:
                    for _li_loc in _li_loc_list:
                        _loc_tag = f" in '{_li_loc}'" if _li_loc else " (anywhere)"
                        _log(task_input, f"Extended search '{_kw}'{_loc_tag}…", "info", "search", {"job_title": _kw})
                        extra_links = _search_jobs(page, _kw, _li_loc, task_input)
                        extra_jobs.extend([(url, "") for url in extra_links])
                # Deduplicate and remove already-seen
                for url, hint in extra_jobs:
                    if url not in seen_urls and url not in _li_seen_urls:
                        seen_urls.add(url)
                        unique_jobs_extra = [(url, hint)]
                        for ej_url, ej_hint in unique_jobs_extra:
                            if applied >= max_apply:
                                break
                            ctrl = _check_control(task_input)
                            if ctrl.get("stop_requested"):
                                break
                            progress = 5 + int((applied / max_apply) * 90) if max_apply else 5
                            _set_progress(task_input, progress, ej_url)
                            _log(task_input, f"[{applied+1}/{max_apply}] Opening {ej_url}")
                            success = _apply_to_job(page, ej_url, task_input)
                            if _li_user_id:
                                try:
                                    from api_client import record_seen_job as _li_record_seen2
                                    _li_skip_meta2: dict = {}
                                    if _li_resume_fp:
                                        _li_skip_meta2["resume_fingerprint"] = _li_resume_fp
                                    _li_record_seen2(
                                        _li_user_id, "linkedin", ej_url,
                                        status="applied" if success else "skipped",
                                        skip_reason="applied" if success else "skipped",
                                        metadata=_li_skip_meta2,
                                    )
                                except Exception:
                                    pass
                            if success:
                                applied += 1
                                _log(task_input, f"Applied — {ej_hint or 'LinkedIn'} ({applied}/{max_apply})", "success", "submit", {"company": ej_hint, "url": ej_url})
                                _record_application(task_input, ej_url, ej_hint)
                            else:
                                skipped += 1
                                _log(task_input, f"Skipped job ({skipped} total) — trying next", "skip", "skip", {"url": ej_url})

            _set_progress(task_input, 100)
            _log(task_input, f"Run complete — applied: {applied}, skipped: {skipped}", "success", "system", {"applied": applied, "skipped": skipped})
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
        # Phone number input — skip if already filled
        phone_input = page.locator("input[id*='phoneNumber-nationalNumber']").first
        if phone_input.is_visible(timeout=2000):
            existing = (phone_input.input_value() or "").strip()
            if existing:
                print(f"  [LINKEDIN] Phone already filled ({existing}) — skipping")
            else:
                # Set country code first (only when we're actually filling the number)
                try:
                    country_sel = page.locator("select[id*='phoneNumber-country']").first
                    if country_sel.is_visible(timeout=1000):
                        country_sel.select_option(phone_country)
                        print(f"  [LINKEDIN] Set phone country: {phone_country}")
                except Exception:
                    pass
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


def _pick_autocomplete(page: Page, inp, typed_text: str, timeout: int = 3000) -> bool:
    """
    After typing in an input, wait for an autocomplete/typeahead dropdown to appear
    and click the best matching suggestion. Returns True if a suggestion was selected.
    Works with LinkedIn's aria-autocomplete inputs and role="listbox" suggestion containers.
    """
    try:
        # Wait briefly for the dropdown to appear
        human_sleep(0.8, 1.5)

        # LinkedIn uses several patterns for autocomplete suggestions:
        suggestion_selectors = [
            # LinkedIn's standard autocomplete suggestions
            "div[role='listbox'] div[role='option']",
            "ul[role='listbox'] li[role='option']",
            "[role='listbox'] [role='option']",
            # Generic dropdown suggestions
            ".basic-typeahead__selectable",
            ".typeahead-suggestion",
            ".autocomplete-suggestion",
            ".suggestions-list li",
            "ul.typeahead-results li",
            # Visible dropdown items near the input
            ".fb-typeahead-result",
        ]

        suggestions = []
        for sel in suggestion_selectors:
            try:
                items = page.locator(sel).all()
                visible = [item for item in items if item.is_visible(timeout=500)]
                if visible:
                    suggestions = visible
                    break
            except Exception:
                continue

        if not suggestions:
            return False

        # Find best match: prefer exact match, then starts-with, then contains
        typed_lower = typed_text.strip().lower()
        best_match = None
        best_score = -1

        for item in suggestions:
            try:
                item_text = (item.inner_text() or "").strip().lower()
                if not item_text:
                    continue
                if item_text == typed_lower:
                    best_match = item
                    best_score = 3
                    break
                elif item_text.startswith(typed_lower) and best_score < 2:
                    best_match = item
                    best_score = 2
                elif typed_lower in item_text and best_score < 1:
                    best_match = item
                    best_score = 1
            except Exception:
                continue

        # If no text match, just pick the first suggestion
        if best_match is None and suggestions:
            best_match = suggestions[0]

        if best_match:
            try:
                selected_text = best_match.inner_text().strip()
                best_match.click(timeout=2000)
                human_sleep(0.3, 0.8)
                print(f"  [LINKEDIN] Autocomplete selected: '{selected_text[:60]}'")
                return True
            except Exception:
                # Try JS click as fallback
                try:
                    best_match.evaluate("el => el.click()")
                    print(f"  [LINKEDIN] Autocomplete selected (JS click)")
                    return True
                except Exception:
                    pass

    except Exception:
        pass
    return False


def _is_autocomplete_input(inp) -> bool:
    """Check if an input field is an autocomplete/typeahead input."""
    try:
        aria_ac = (inp.get_attribute("aria-autocomplete") or "").lower()
        if aria_ac in ("list", "both"):
            return True
        role = (inp.get_attribute("role") or "").lower()
        if role == "combobox":
            return True
        inp_class = (inp.get_attribute("class") or "").lower()
        if any(kw in inp_class for kw in ("typeahead", "autocomplete", "combobox")):
            return True
    except Exception:
        pass
    return False


def _build_user_profile(task_input: dict) -> dict:
    """
    Build a user_profile dict from task_input for Claude AI calls.
    If dashboard fields are empty, auto-extracts from resume text as fallback.
    Only extracts once per run (cached in task_input under _resume_profile_cache).
    """
    # Return cached version if already built this run
    if "_user_profile_cache" in task_input:
        return dict(task_input["_user_profile_cache"])

    profile = {
        "full_name": task_input.get("full_name", ""),
        "email": task_input.get("email", ""),
        "phone": task_input.get("phone", ""),
        "current_city": task_input.get("current_city", ""),
        "linkedin_url": task_input.get("linkedin_url", ""),
        "github_url": task_input.get("github_url", ""),
        "portfolio_url": task_input.get("portfolio_url", ""),
        "years_experience": task_input.get("years_experience", 2),
        "highest_education": task_input.get("highest_education", ""),
        "notice_period": task_input.get("notice_period", ""),
        "salary_expectation": task_input.get("salary_expectation", ""),
        "current_ctc": task_input.get("current_ctc", ""),
    }

    # Add employment context
    emps = task_input.get("employments") or task_input.get("_employment_data") or []
    if emps:
        current = next((e for e in emps if e.get("is_current")), emps[0])
        profile["current_company"] = current.get("company", "")
        profile["current_position"] = current.get("position", "")

    # Add education context
    edus = task_input.get("educations") or task_input.get("_education_data") or []
    if edus:
        profile["school"] = edus[0].get("school", "")
        profile["degree"] = edus[0].get("degree", "")
        profile["major"] = edus[0].get("major", "")
        grad_year = edus[0].get("end_year", "")
        if grad_year:
            profile["graduation_year"] = str(grad_year)

    # ── Resume fallback: extract missing fields from resume text ──
    # If key profile fields are still empty, auto-extract from resume once
    resume_text = task_input.get("resume_text", "")
    needs_resume_extract = resume_text and (
        not profile.get("current_company") or
        not profile.get("school") or
        not profile.get("current_city") or
        not emps or not edus
    )

    if needs_resume_extract and not task_input.get("_resume_extracted"):
        task_input["_resume_extracted"] = True  # prevent re-extraction
        try:
            from automation.ai_client import extract_employment, extract_education, analyze_resume
            # Extract employment if missing
            if not emps:
                extracted_emps = extract_employment(resume_text)
                if extracted_emps:
                    task_input["_employment_data"] = extracted_emps
                    current = next((e for e in extracted_emps if e.get("is_current")), extracted_emps[0])
                    profile["current_company"] = profile.get("current_company") or current.get("company", "")
                    profile["current_position"] = profile.get("current_position") or current.get("position", "")
                    print(f"  [PROFILE] 💼 Auto-extracted {len(extracted_emps)} employment entries from resume")
            # Extract education if missing
            if not edus:
                extracted_edus = extract_education(resume_text)
                if extracted_edus:
                    task_input["_education_data"] = extracted_edus
                    profile["school"] = profile.get("school") or extracted_edus[0].get("school", "")
                    profile["degree"] = profile.get("degree") or extracted_edus[0].get("degree", "")
                    profile["major"] = profile.get("major") or extracted_edus[0].get("major", "")
                    grad_year = extracted_edus[0].get("end_year", "")
                    if grad_year:
                        profile["graduation_year"] = profile.get("graduation_year") or str(grad_year)
                    print(f"  [PROFILE] 🎓 Auto-extracted {len(extracted_edus)} education entries from resume")
            # Extract basic info (email, years_experience) if missing
            if not profile.get("email") or not profile.get("years_experience"):
                basic = analyze_resume(resume_text)
                if not profile.get("email") and basic.get("email_hint"):
                    profile["email"] = basic["email_hint"]
                if not profile.get("years_experience") and basic.get("years_experience"):
                    profile["years_experience"] = basic["years_experience"]
        except Exception as e:
            print(f"  [PROFILE] ⚠️ Resume fallback extraction failed: {e}")

    # Cache the built profile for this run
    task_input["_user_profile_cache"] = dict(profile)
    return profile


def _fill_additional_questions(page: Page, task_input: dict):
    """
    Auto-fill additional application questions.
    Handles: years-of-experience inputs, decimal-with-minimum inputs,
    skill rating inputs, yes/no selects, open text, autocomplete/typeahead,
    education fields, and checkboxes.
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
                        # Check if this is an autocomplete/typeahead input
                        is_autocomplete = _is_autocomplete_input(inp)

                        # Detect city/location fields for autocomplete
                        is_city_field = any(w in label_text for w in (
                            "city", "location", "town", "where", "place", "metro",
                            "hometown", "home town", "address",
                        ))

                        # Use Claude to compose a free-text answer
                        try:
                            from automation.ai_client import claude_answer_question
                            resume_summary = task_input.get("resume_text", "")[:500]
                            user_profile = _build_user_profile(task_input)

                            # For city fields, prefer profile data directly
                            if is_city_field:
                                answer = (task_input.get("current_city") or "").strip()
                            else:
                                answer = claude_answer_question(label_text, [], resume_summary, user_profile=user_profile)

                            if answer:
                                human_type(page, answer, locator=inp)
                                print(f"  [LINKEDIN] {'Claude' if not is_city_field else 'Profile'} filled text '{label_text[:60]}' = {answer[:60]}")

                                # Try to pick from autocomplete if dropdown appears
                                if is_autocomplete or is_city_field:
                                    _pick_autocomplete(page, inp, answer)
                        except Exception:
                            pass
                    # Leave truly unknown fields empty

            except Exception:
                pass
    except Exception:
        pass

    # ── Textarea fields ────────────────────────────────────────
    # Use AI-generated cover note if auto_cover_letter is enabled (default True)
    cover_note = task_input.get("cover_note", "")
    if not cover_note and task_input.get("auto_cover_letter", True):
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
                    print("  [LINKEDIN] ✍️  AI cover letter generated")
                    # Save to cover_letters table (best-effort)
                    try:
                        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
                        from api_client import save_cover_letter
                        save_cover_letter(
                            user_id=task_input.get("user_id", ""),
                            job_id=task_input.get("_current_job_id"),
                            cover_letter=cover_note,
                            cover_type="intro_message",
                            metadata={"company": company, "role": role},
                        )
                    except Exception:
                        pass
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
            "personal relationship", "relationship with", "know the employee",
            "associated with deloitte", "employed by any company",
            "applied to", "applied in the past",
        )
        # Keywords that should get "Yes" (all other yes/no questions)
        _YES_KEYWORDS = (
            "authorized", "authorised", "eligible", "legally",
            "work authorization", "work authorisation",
            "start immediately", "immediately", "urgently",
            "can you start", "available immediately",
            "background check", "drug test", "agree",
            "text/sms updates", "sms updates", "email me about",
            "newsletter",
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

                # Location-based radio (e.g. "Are you currently based in Bangkok?")
                if not want_no and any(kw in question_text for kw in ("currently based", "open to relocate", "willing to relocate")):
                    user_city = (task_input.get("current_city") or "").lower()
                    user_locs = [p.strip().lower() for p in str(task_input.get("location", "")).split(",") if p.strip()]
                    # Check if the question mentions a city/country that matches user's location
                    all_locs = [user_city] + user_locs if user_city else user_locs
                    if all_locs and any(loc in question_text for loc in all_locs):
                        want_no = False  # Yes — user is there or willing
                    else:
                        want_no = True   # No — not based there

                want_yes = not want_no  # default is Yes for all other questions

                # Find the target option
                target_radio, target_label_id = None, None
                # Check if these are simple Yes/No radio options
                option_labels = [lbl for _, lbl, _, _ in options]
                is_yes_no = set(option_labels) <= {"yes", "no", ""}

                if is_yes_no:
                    # Simple Yes/No — use keyword heuristics
                    for r, lbl, val, inp_id in options:
                        is_yes = val in ("yes", "true", "1") or lbl in ("yes",)
                        is_no  = val in ("no", "false", "0") or lbl in ("no",)
                        if want_yes and is_yes:
                            target_radio, target_label_id = r, inp_id
                            break
                        if want_no and is_no:
                            target_radio, target_label_id = r, inp_id
                            break
                else:
                    # Non-Yes/No radios — use Claude to pick the best option
                    try:
                        from automation.ai_client import claude_answer_question
                        non_blank = [lbl for _, lbl, _, _ in options if lbl.strip()]
                        if non_blank and question_text:
                            resume_summary = task_input.get("resume_text", "")[:500]
                            user_profile = _build_user_profile(task_input)
                            answer = claude_answer_question(question_text, non_blank, resume_summary, user_profile=user_profile)
                            for r, lbl, val, inp_id in options:
                                if lbl == answer.lower() or answer.lower() in lbl or lbl in answer.lower():
                                    target_radio, target_label_id = r, inp_id
                                    print(f"  [LINKEDIN] Radio → Claude picked '{lbl}' for: {question_text[:60]!r}")
                                    break
                    except Exception:
                        pass

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

                # How did you hear about this job → LinkedIn
                elif any(w in question_text for w in ("how did you hear", "how did you find", "where did you hear", "source")):
                    if not _pick(["linkedin", "job board", "online", "internet"]):
                        for i, v in enumerate(opt_vals):
                            if v.lower() not in _SKIP_VALS:
                                sel.select_option(v)
                                break

                # Highest education / academic level
                elif any(w in question_text for w in ("education", "academic level", "degree", "qualification")):
                    edu = (task_input.get("highest_education") or "").lower()
                    if edu:
                        # Try to match the user's education first
                        if not _pick([edu]):
                            _pick(["bachelor", "master", "b.tech", "b.e", "m.tech", "m.e"])
                    else:
                        _pick(["bachelor", "master", "b.tech", "b.e", "m.tech", "m.e"])

                # Country / region based
                elif any(w in question_text for w in ("country", "region", "based in")):
                    city = (task_input.get("current_city") or "").lower()
                    country = (task_input.get("phone_country") or "").split("(")[0].strip().lower()
                    if city and _pick([city]):
                        pass
                    elif country and _pick([country]):
                        pass
                    else:
                        _pick(["india"])

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
                                user_profile = _build_user_profile(task_input)
                                answer = claude_answer_question(question_text, non_blank, resume_summary, user_profile=user_profile)
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

    # ── Checkboxes (privacy / terms / agreement) ───────────────
    try:
        checkboxes = page.locator("input[type='checkbox']").all()
        for cb in checkboxes:
            try:
                if cb.is_checked():
                    continue
                # Get associated label text
                cb_id = cb.get_attribute("id") or ""
                label_text = ""
                if cb_id:
                    lbl = page.locator(f"label[for='{cb_id}']")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().lower()
                if not label_text:
                    try:
                        label_text = cb.evaluate(
                            "el => el.closest('label') ? el.closest('label').innerText : ''"
                        ).lower()
                    except Exception:
                        pass
                # Also check nearby text for context
                if not label_text:
                    try:
                        label_text = cb.evaluate(
                            """el => {
                                let p = el.parentElement;
                                for (let i = 0; i < 4; i++) {
                                    if (!p) break;
                                    const t = p.innerText || '';
                                    if (t.length > 5 && t.length < 500) return t;
                                    p = p.parentElement;
                                }
                                return '';
                            }"""
                        ).lower()
                    except Exception:
                        pass

                # Check if this looks like a terms/privacy/agreement checkbox
                _AGREE_KEYWORDS = (
                    "agree", "terms", "privacy", "consent", "certify",
                    "acknowledge", "confirm", "policy", "declaration",
                    "i have read", "i accept", "checking this box",
                    "by checking", "i understand",
                )
                if any(kw in label_text for kw in _AGREE_KEYWORDS) or not label_text:
                    # Click the label if possible (checkbox may be CSS-hidden)
                    clicked = False
                    if cb_id:
                        try:
                            lbl_el = page.locator(f"label[for='{cb_id}']").first
                            if lbl_el.is_visible(timeout=1000):
                                lbl_el.click(timeout=2000)
                                clicked = True
                        except Exception:
                            pass
                    if not clicked:
                        try:
                            cb.click(timeout=2000)
                            clicked = True
                        except Exception:
                            pass
                    if not clicked:
                        try:
                            cb.evaluate("el => el.click()")
                            clicked = True
                        except Exception:
                            pass
                    if clicked:
                        print(f"  [LINKEDIN] ☑ Checked: '{label_text[:60]}'")
                        micro_pause()
            except Exception:
                pass
    except Exception:
        pass

    # ── Education section fields ───────────────────────────────
    # LinkedIn Easy Apply sometimes has education sub-forms with:
    # School, City, Degree (dropdown), Major/Field of study, Dates
    _fill_education_fields(page, task_input)

    # ── Employment / Work Experience fields ────────────────────
    _fill_employment_fields(page, task_input)


def _fill_education_fields(page: Page, task_input: dict):
    """
    Fill education section fields in LinkedIn Easy Apply forms.
    Extracts education data from resume via AI and fills school, city, degree, major, dates.
    """
    task_input = task_input or {}

    # Check if there are education-related fields on this page
    edu_labels = page.locator(
        "label:visible"
    ).all()
    has_edu_fields = False
    for lbl in edu_labels:
        try:
            txt = (lbl.inner_text() or "").lower()
            if any(kw in txt for kw in ("school", "university", "college", "degree", "field of study", "major")):
                has_edu_fields = True
                break
        except Exception:
            pass

    if not has_edu_fields:
        return

    # Get or extract education data
    # Priority: 1) Dashboard-provided educations, 2) AI extraction from resume
    edu_data = task_input.get("_education_data")
    if edu_data is None:
        # Check if user provided education from dashboard
        dashboard_edu = task_input.get("educations")
        if dashboard_edu and len(dashboard_edu) > 0:
            edu_data = dashboard_edu
            task_input["_education_data"] = edu_data
            print(f"  [LINKEDIN] 🎓 Using {len(edu_data)} education entries from dashboard profile")
        else:
            # Fall back to AI extraction from resume
            resume_text = task_input.get("resume_text", "")
            if resume_text:
                try:
                    from automation.ai_client import extract_education
                    edu_data = extract_education(resume_text)
                    task_input["_education_data"] = edu_data
                    if edu_data:
                        print(f"  [LINKEDIN] 🎓 Extracted {len(edu_data)} education entries from resume")
                except Exception as e:
                    print(f"  [LINKEDIN] ⚠️ Education extraction failed: {e}")
                    edu_data = []
                    task_input["_education_data"] = edu_data

    if not edu_data:
        return

    # Use the most recent education entry (first in the list)
    edu = edu_data[0] if edu_data else {}

    # Map label keywords to education data fields
    _EDU_FIELD_MAP = {
        ("school", "university", "college", "institution"): "school",
        ("degree",): "_degree_dropdown",  # handled as dropdown below
        ("field of study", "major", "area of study", "specialization", "discipline"): "major",
        ("gpa", "grade", "cgpa", "percentage"): "gpa",
    }

    # Fill text inputs for education fields
    try:
        inputs = page.locator("input[type='text']:visible").all()
        for inp in inputs:
            try:
                val = (inp.input_value() or "").strip()
                if val:
                    continue

                inp_id = inp.get_attribute("id") or ""
                label_text = ""
                if inp_id:
                    lbl = page.locator(f"label[for='{inp_id}']")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().lower()

                if not label_text:
                    continue

                # Match against education field keywords
                for keywords, field_key in _EDU_FIELD_MAP.items():
                    if any(kw in label_text for kw in keywords):
                        if field_key == "_degree_dropdown":
                            continue  # handled in dropdown section
                        fill_value = edu.get(field_key, "")
                        if fill_value:
                            human_type(page, str(fill_value), locator=inp)
                            print(f"  [LINKEDIN] 🎓 Filled education '{label_text[:50]}' = {fill_value[:50]}")
                            # Try autocomplete if it appears (e.g., School name)
                            if _is_autocomplete_input(inp) or any(kw in label_text for kw in ("school", "university", "college")):
                                _pick_autocomplete(page, inp, str(fill_value))
                        break

                # City field in education section
                if any(kw in label_text for kw in ("city", "location")) and "school" not in label_text:
                    city = edu.get("city", "")
                    if city:
                        human_type(page, city, locator=inp)
                        print(f"  [LINKEDIN] 🎓 Filled education city = {city}")
                        if _is_autocomplete_input(inp):
                            _pick_autocomplete(page, inp, city)

            except Exception:
                pass
    except Exception:
        pass

    # Fill degree dropdown (select element)
    try:
        selects = page.locator("select:visible").all()
        for sel in selects:
            try:
                sel_id = sel.get_attribute("id") or ""
                question_text = ""
                if sel_id:
                    lbl = page.locator(f"label[for='{sel_id}']")
                    if lbl.count() > 0:
                        question_text = lbl.first.inner_text().lower()
                if not question_text:
                    continue
                if "degree" not in question_text:
                    continue

                current = sel.evaluate("el => el.value") or ""
                if current and current.lower() not in ("", "select an option", "none", "please select"):
                    continue

                degree = edu.get("degree", "")
                if not degree:
                    continue

                opts = sel.locator("option").all()
                opt_vals = [(o.get_attribute("value") or "").strip() for o in opts]
                opt_texts = [(o.inner_text() or "").strip().lower() for o in opts]
                degree_lower = degree.lower()

                # Try to match degree
                matched = False
                for i, t in enumerate(opt_texts):
                    if degree_lower in t or t in degree_lower:
                        sel.select_option(opt_vals[i])
                        print(f"  [LINKEDIN] 🎓 Degree dropdown → '{opt_texts[i]}'")
                        matched = True
                        break
                if not matched:
                    # Try common degree mappings
                    degree_map = {
                        "b.tech": "bachelor", "b.e": "bachelor", "bsc": "bachelor",
                        "ba": "bachelor", "bba": "bachelor", "bcom": "bachelor",
                        "m.tech": "master", "m.e": "master", "msc": "master",
                        "ma": "master", "mba": "master", "mcom": "master",
                        "phd": "doctor", "ph.d": "doctor",
                        "diploma": "associate",
                    }
                    mapped = None
                    for key, val_mapped in degree_map.items():
                        if key in degree_lower:
                            mapped = val_mapped
                            break
                    if mapped:
                        for i, t in enumerate(opt_texts):
                            if mapped in t:
                                sel.select_option(opt_vals[i])
                                print(f"  [LINKEDIN] 🎓 Degree dropdown (mapped) → '{opt_texts[i]}'")
                                break
            except Exception:
                pass
    except Exception:
        pass

    # Fill date fields (month/year dropdowns or inputs)
    try:
        # Look for date-related selects (start/end month, start/end year)
        selects = page.locator("select:visible").all()
        for sel in selects:
            try:
                sel_id = sel.get_attribute("id") or ""
                question_text = ""
                if sel_id:
                    lbl = page.locator(f"label[for='{sel_id}']")
                    if lbl.count() > 0:
                        question_text = lbl.first.inner_text().lower()
                if not question_text:
                    question_text = sel.evaluate(
                        """el => {
                            let p = el.parentElement;
                            for (let i = 0; i < 4; i++) {
                                if (!p) break;
                                const h = p.querySelector('label,legend,span');
                                if (h && h.innerText.trim().length > 2) return h.innerText.trim();
                                p = p.parentElement;
                            }
                            return '';
                        }"""
                    ).lower()

                current = sel.evaluate("el => el.value") or ""
                if current and current.lower() not in ("", "select an option", "none", "please select", "month", "year"):
                    continue

                opts = sel.locator("option").all()
                opt_vals = [(o.get_attribute("value") or "").strip() for o in opts]
                opt_texts = [(o.inner_text() or "").strip().lower() for o in opts]

                # Determine if this is a month or year dropdown and start or end
                is_month = "month" in question_text or any("january" in t or "february" in t for t in opt_texts)
                is_year = "year" in question_text or any(t.isdigit() and len(t) == 4 for t in opt_texts)
                is_start = "start" in question_text or "from" in question_text
                is_end = "end" in question_text or "to" in question_text

                # Default to end date if not clearly start
                if not is_start and not is_end:
                    # Check parent section for clues
                    try:
                        section_text = sel.evaluate(
                            """el => {
                                let p = el.parentElement;
                                for (let i = 0; i < 6; i++) {
                                    if (!p) break;
                                    const t = p.innerText || '';
                                    if (t.toLowerCase().includes('start') || t.toLowerCase().includes('from')) return 'start';
                                    if (t.toLowerCase().includes('end') || t.toLowerCase().includes('to date')) return 'end';
                                    p = p.parentElement;
                                }
                                return 'end';
                            }"""
                        ).lower()
                        is_start = section_text == "start"
                        is_end = section_text == "end"
                    except Exception:
                        is_end = True

                if is_month:
                    month_val = edu.get("start_month" if is_start else "end_month", "")
                    if month_val:
                        month_int = int(month_val)
                        # Month options are usually month names or numbers
                        for i, t in enumerate(opt_texts):
                            # Match by number or month name
                            import calendar
                            month_names = [m.lower() for m in calendar.month_name[1:]]
                            if (t.isdigit() and int(t) == month_int) or \
                               (month_int <= 12 and t.startswith(month_names[month_int - 1][:3])):
                                sel.select_option(opt_vals[i])
                                print(f"  [LINKEDIN] 🎓 {'Start' if is_start else 'End'} month → '{opt_texts[i]}'")
                                break

                elif is_year:
                    year_val = edu.get("start_year" if is_start else "end_year", "")
                    if year_val:
                        for i, t in enumerate(opt_texts):
                            if t == str(year_val):
                                sel.select_option(opt_vals[i])
                                print(f"  [LINKEDIN] 🎓 {'Start' if is_start else 'End'} year → '{year_val}'")
                                break

            except Exception:
                pass
    except Exception:
        pass


def _fill_employment_fields(page: Page, task_input: dict):
    """
    Fill employment/work experience fields in LinkedIn Easy Apply forms.
    Uses dashboard-provided employment data first, falls back to AI extraction.
    Handles: company name, title/position, city, dates.
    """
    task_input = task_input or {}

    # Check if there are employment-related fields on this page
    has_emp_fields = False
    for lbl in page.locator("label:visible").all():
        try:
            txt = (lbl.inner_text() or "").lower()
            if any(kw in txt for kw in ("company", "employer", "organization", "title", "position", "job title")):
                has_emp_fields = True
                break
        except Exception:
            pass

    if not has_emp_fields:
        return

    # Get or extract employment data
    emp_data = task_input.get("_employment_data")
    if emp_data is None:
        dashboard_emp = task_input.get("employments")
        if dashboard_emp and len(dashboard_emp) > 0:
            emp_data = dashboard_emp
            task_input["_employment_data"] = emp_data
            print(f"  [LINKEDIN] 💼 Using {len(emp_data)} employment entries from dashboard")
        else:
            resume_text = task_input.get("resume_text", "")
            if resume_text:
                try:
                    from automation.ai_client import extract_employment
                    emp_data = extract_employment(resume_text)
                    task_input["_employment_data"] = emp_data
                    if emp_data:
                        print(f"  [LINKEDIN] 💼 Extracted {len(emp_data)} employment entries from resume")
                except Exception as e:
                    print(f"  [LINKEDIN] ⚠️ Employment extraction failed: {e}")
                    emp_data = []
                    task_input["_employment_data"] = emp_data

    if not emp_data:
        return

    # Use the most recent (current) employment entry
    emp = emp_data[0] if emp_data else {}

    # Map label keywords to employment data fields
    _EMP_FIELD_MAP = {
        ("company", "employer", "organization", "company name"): "company",
        ("title", "position", "job title", "role", "designation"): "position",
    }

    try:
        inputs = page.locator("input[type='text']:visible").all()
        for inp in inputs:
            try:
                val = (inp.input_value() or "").strip()
                if val:
                    continue

                inp_id = inp.get_attribute("id") or ""
                label_text = ""
                if inp_id:
                    lbl = page.locator(f"label[for='{inp_id}']")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().lower()

                if not label_text:
                    continue

                for keywords, field_key in _EMP_FIELD_MAP.items():
                    if any(kw in label_text for kw in keywords):
                        fill_value = emp.get(field_key, "")
                        if fill_value:
                            human_type(page, str(fill_value), locator=inp)
                            print(f"  [LINKEDIN] 💼 Filled employment '{label_text[:50]}' = {fill_value[:50]}")
                            if _is_autocomplete_input(inp) or any(kw in label_text for kw in ("company", "employer")):
                                _pick_autocomplete(page, inp, str(fill_value))
                        break

                # City field in employment section
                if any(kw in label_text for kw in ("city", "location")) and not any(kw in label_text for kw in ("company", "title")):
                    city = emp.get("city", "") or task_input.get("current_city", "")
                    if city:
                        human_type(page, city, locator=inp)
                        print(f"  [LINKEDIN] 💼 Filled employment city = {city}")
                        if _is_autocomplete_input(inp):
                            _pick_autocomplete(page, inp, city)

                # Description/responsibilities
                if any(kw in label_text for kw in ("description", "responsibilities", "summary")):
                    desc = emp.get("description", "")
                    if desc:
                        human_type(page, str(desc)[:500], locator=inp)
                        print(f"  [LINKEDIN] 💼 Filled employment description")

            except Exception:
                pass
    except Exception:
        pass

    # Fill employment date fields (month/year dropdowns)
    try:
        import calendar
        selects = page.locator("select:visible").all()
        for sel in selects:
            try:
                sel_id = sel.get_attribute("id") or ""
                question_text = ""
                if sel_id:
                    lbl = page.locator(f"label[for='{sel_id}']")
                    if lbl.count() > 0:
                        question_text = lbl.first.inner_text().lower()
                if not question_text:
                    question_text = sel.evaluate(
                        """el => {
                            let p = el.parentElement;
                            for (let i = 0; i < 4; i++) {
                                if (!p) break;
                                const h = p.querySelector('label,legend,span');
                                if (h && h.innerText.trim().length > 2) return h.innerText.trim();
                                p = p.parentElement;
                            }
                            return '';
                        }"""
                    ).lower()

                # Skip already-filled selects
                current = sel.evaluate("el => el.value") or ""
                if current and current.lower() not in ("", "select an option", "none", "please select", "month", "year"):
                    continue

                # Check if this is within employment section context
                section_text = sel.evaluate(
                    """el => {
                        let p = el.parentElement;
                        for (let i = 0; i < 8; i++) {
                            if (!p) break;
                            const t = p.innerText || '';
                            if (t.toLowerCase().includes('work experience') ||
                                t.toLowerCase().includes('employment') ||
                                t.toLowerCase().includes('company')) return 'employment';
                            p = p.parentElement;
                        }
                        return '';
                    }"""
                ).lower()
                if "employment" not in section_text and not any(kw in question_text for kw in ("title", "company", "work")):
                    continue

                opts = sel.locator("option").all()
                opt_vals = [(o.get_attribute("value") or "").strip() for o in opts]
                opt_texts = [(o.inner_text() or "").strip().lower() for o in opts]

                is_month = "month" in question_text or any("january" in t or "february" in t for t in opt_texts)
                is_year = "year" in question_text or any(t.isdigit() and len(t) == 4 for t in opt_texts)
                is_start = "start" in question_text or "from" in question_text
                is_end = "end" in question_text or "to" in question_text

                if not is_start and not is_end:
                    parent_hint = sel.evaluate(
                        """el => {
                            let p = el.parentElement;
                            for (let i = 0; i < 6; i++) {
                                if (!p) break;
                                const t = (p.innerText || '').toLowerCase();
                                if (t.includes('start') || t.includes('from')) return 'start';
                                if (t.includes('end') || t.includes('to date')) return 'end';
                                p = p.parentElement;
                            }
                            return 'start';
                        }"""
                    ).lower()
                    is_start = parent_hint == "start"
                    is_end = parent_hint == "end"

                if is_month:
                    month_val = emp.get("start_month" if is_start else "end_month", "")
                    if month_val:
                        month_int = int(month_val)
                        month_names = [m.lower() for m in calendar.month_name[1:]]
                        for i, t in enumerate(opt_texts):
                            if (t.isdigit() and int(t) == month_int) or \
                               (month_int <= 12 and t.startswith(month_names[month_int - 1][:3])):
                                sel.select_option(opt_vals[i])
                                print(f"  [LINKEDIN] 💼 {'Start' if is_start else 'End'} month → '{opt_texts[i]}'")
                                break

                elif is_year:
                    year_val = emp.get("start_year" if is_start else "end_year", "")
                    if year_val:
                        for i, t in enumerate(opt_texts):
                            if t == str(year_val):
                                sel.select_option(opt_vals[i])
                                print(f"  [LINKEDIN] 💼 {'Start' if is_start else 'End'} year → '{year_val}'")
                                break

            except Exception:
                pass
    except Exception:
        pass

    # Handle "I currently work here" checkbox
    try:
        if emp.get("is_current"):
            checkboxes = page.locator("input[type='checkbox']:visible").all()
            for cb in checkboxes:
                try:
                    if cb.is_checked():
                        continue
                    cb_id = cb.get_attribute("id") or ""
                    label_text = ""
                    if cb_id:
                        lbl = page.locator(f"label[for='{cb_id}']")
                        if lbl.count() > 0:
                            label_text = lbl.first.inner_text().lower()
                    if any(kw in label_text for kw in ("currently work", "current", "present")):
                        try:
                            lbl_el = page.locator(f"label[for='{cb_id}']").first
                            if lbl_el.is_visible(timeout=1000):
                                lbl_el.click(timeout=2000)
                            else:
                                cb.click(timeout=2000)
                        except Exception:
                            cb.evaluate("el => el.click()")
                        print(f"  [LINKEDIN] 💼 ☑ Checked 'Currently work here'")
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
    # When smart_match is on, most jobs get skipped — fetch a much larger pool
    smart_match = task_input.get("smart_match", False)
    pool_mult   = 10 if smart_match else 4
    target_pool = max(max_apply * pool_mult, 30)   # minimum 30 jobs
    max_pages   = 20
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
                         "info", "ai_decision",
                         {"score": score, "threshold": match_threshold, "skip_reason": "below_score_threshold" if score < match_threshold else None})
                    if score < match_threshold:
                        _log(task_input,
                             f"Skipped — score {score}% below threshold {match_threshold}%",
                             "skip", "skip",
                             {"score": score, "threshold": match_threshold, "url": job_url, "skip_reason": "below_score_threshold"})
                        return False
                    _log(task_input, f"Match score {score}% passed — proceeding to apply", "success", "ai_decision", {"score": score})
                    task_input = dict(task_input)
                    task_input["_last_match_score"] = score
                except Exception as _me:
                    _log(task_input, f"Match scoring failed ({_me}) — applying anyway", "warning", "ai_decision")
            else:
                _log(task_input, "Smart match skipped — no resume text available", "warning", "ai_decision")

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
                        _log(task_input, f"Tailoring resume for {role or 'this role'} at {company or 'this company'}…", "info", "tailor", {"company": company, "job_title": role})
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
                            f"Resume tailored — ATS score {result.score_before:.0f}%→{result.score_after:.0f}%",
                            "success", "tailor",
                            {"company": company, "job_title": role, "score": result.score_after},
                        )
                        if result.tailored_pdf_path and os.path.isfile(result.tailored_pdf_path):
                            task_input = dict(task_input)
                            task_input["resume_path"]   = result.tailored_pdf_path
                            task_input["_tailored_pdf"] = result.tailored_pdf_path
                    except Exception as _te:
                        _log(task_input, f"Tailoring failed ({_te}) — applying with original resume", "warning", "tailor")
            else:
                _log(task_input, "Could not extract JD text — applying with original resume", "warning", "tailor")

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
                    # ── Approval gate for TAILOR_AND_APPLY ─────────
                    job_title_str = task_input.get("role", task_input.get("keywords", "this role"))
                    company_str   = task_input.get("company", "this company")
                    if not _request_approval(task_input, page, job_title_str, company_str, job_url):
                        _close_modal(page)
                        return False
                    # ───────────────────────────────────────────────
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
