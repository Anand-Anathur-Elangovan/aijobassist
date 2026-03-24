"""
Naukri automation module.
Handles browser-based job search and application via Playwright.
Supports full-auto and semi-auto modes.
"""

import os
import re
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
# Config
# ──────────────────────────────────────────────────────────────
NAUKRI_URL       = "https://www.naukri.com"
NAUKRI_LOGIN_URL = "https://www.naukri.com"   # login is a drawer on homepage now
NAV_WAIT         = 3
MAX_APPLY        = 5


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
            print(f"  [NAUKRI] Navigation failed (attempt {attempt+1}/{max_retries}): {e} — retrying in {wait}s")
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
                print(f"  [NAUKRI] Click retry {attempt+1}/{max_retries}: {e}")
                time.sleep(wait)
    return False


# ──────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────
def apply_naukri_jobs(task_input: dict = None) -> dict:
    """
    Main entry point called by task_runner.py.
    task_input keys:
        keywords           str   e.g. "Python Developer"
        location           str   e.g. "Bangalore"
        max_apply          int   default 5
        semi_auto          bool  if True, bot fills fields but user clicks Submit
        years_experience   int
        notice_period      int   days
        salary_expectation int   LPA / annual figure
        phone              str
        resume_url         str   Supabase presigned URL
        resume_filename    str
        cover_note         str
    """
    if task_input is None:
        task_input = {}

    keywords  = task_input.get("keywords", "Software Engineer")
    location  = task_input.get("location", "")
    max_apply = int(task_input.get("max_apply", MAX_APPLY))

    # ── Download resume once for the whole run (avoid re-download per job) ─
    _resume_tmp_path = ""
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
                    print(f"  [NAUKRI] Resume downloaded to: {_resume_tmp_path}")
            except Exception as dl_err:
                print(f"  [NAUKRI] Resume download error: {dl_err}")
        if not task_input.get("resume_path") and resume_text:
            with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
                f.write(resume_text)
                _resume_tmp_path = f.name
            task_input = dict(task_input)
            task_input["resume_path"] = _resume_tmp_path
            print(f"  [NAUKRI] Using parsed_text as resume source: {_resume_tmp_path}")

    # ── Enrich keywords with top skills from the resume ────────
    resume_text_raw = task_input.get("resume_text", "").strip()
    if resume_text_raw and keywords:
        try:
            from automation.ai_client import analyze_resume
            resume_info = analyze_resume(resume_text_raw)
            top_skills  = resume_info.get("skills", [])[:3]
            kw_lower    = keywords.lower()
            additions   = [s for s in top_skills if s.lower() not in kw_lower]
            if additions:
                keywords = f"{keywords} {' '.join(additions)}"
                print(f"  [NAUKRI] Keywords enriched from resume: {keywords}")
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=stealth_launch_args())
        context = browser.new_context(**stealth_context_options())
        page    = context.new_page()
        inject_stealth(page)

        try:
            if not _login(page, task_input):
                return {"applied_count": 0, "skipped_count": 0, "message": "Login failed or cancelled"}

            # ── Build keyword list (up to 3 keywords, sequential) ────
            _kw_list = [
                k.strip() for k in [
                    task_input.get("keywords", ""),
                    task_input.get("keywords2", ""),
                    task_input.get("keywords3", ""),
                ] if k.strip()
            ]
            if not _kw_list:
                _kw_list = ["Software Engineer"]

            # ── Compute resume fingerprint (ties smart_match skips to this resume) ──
            import hashlib as _hashlib
            _resume_fp = ""
            _resume_text_raw2 = task_input.get("resume_text", "")
            if _resume_text_raw2:
                _resume_fp = _hashlib.md5(_resume_text_raw2[:500].encode()).hexdigest()[:16]
            elif task_input.get("resume_url", ""):
                _resume_fp = _hashlib.md5(task_input["resume_url"].encode()).hexdigest()[:16]

            # ── Fetch seen jobs (smart-filtered: mode-aware + resume fingerprint) ──
            _user_id     = task_input.get("user_id", "")
            _apply_types = task_input.get("apply_types", "both")
            _seen_urls: set = set()
            if _user_id:
                try:
                    import sys as _sys_h
                    _sys_h.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
                    from api_client import fetch_seen_jobs as _fetch_seen_jobs
                    _seen_urls = _fetch_seen_jobs(
                        _user_id, "naukri",
                        apply_types=_apply_types,
                        resume_fingerprint=_resume_fp,
                    )
                    print(f"  [NAUKRI] {len(_seen_urls)} URL(s) in 30-day history — will be skipped")
                except Exception as _sh_err:
                    print(f"  [NAUKRI] Job history unavailable ({_sh_err}) — proceeding without filter")

            # ── Build location list (comma-separated, empty = anywhere) ─
            _loc_list = [
                l.strip() for l in task_input.get("location", "").split(",") if l.strip()
            ] or [""]

            # ── Search each keyword × location, collect fresh (unseen) URLs ─
            _all_jobs: list = []
            _dedup: set = set(_seen_urls)      # dedup across keywords + locations
            for _kw in _kw_list:
                for _loc in _loc_list:
                    _loc_tag = f" | 📍{_loc}" if _loc else ""
                    print(f"  [NAUKRI] 🔑 Keyword: '{_kw}'{_loc_tag}")
                    _kw_jobs = _search_jobs(page, _kw, _loc, task_input)
                    _fresh   = [u for u in _kw_jobs if u not in _dedup]
                    _dedup.update(_fresh)
                    _all_jobs.extend(_fresh)
                    print(f"  [NAUKRI]   → {len(_fresh)} fresh job(s) found")

            if not _all_jobs:
                return {"applied_count": 0, "skipped_count": 0,
                        "message": "No new jobs found (all already seen in 30-day history)"}

            # ── Safe-copy task_input so we can store per-job skip metadata ──
            task_input = dict(task_input)

            applied = 0
            skipped = 0
            for job_url in _all_jobs:
                if applied >= max_apply:
                    print(f"  [NAUKRI] Reached limit of {max_apply}. Run again to continue from the next batch.")
                    break
                task_input["_last_skip_reason"]   = "skipped"  # reset before each job
                task_input["_last_skip_metadata"] = {}
                success = _apply_to_job(page, job_url, task_input)
                _skip_reason = task_input.get("_last_skip_reason", "skipped")
                _skip_meta   = dict(task_input.get("_last_skip_metadata") or {})
                if _skip_reason == "smart_match" and _resume_fp:
                    _skip_meta.setdefault("resume_fingerprint", _resume_fp)
                if _skip_reason == "mode_skip":
                    _skip_meta.setdefault("apply_types", _apply_types)
                # Record to history (smart_match & mode_skip have their own expiry logic)
                if _user_id:
                    try:
                        from api_client import record_seen_job as _record_seen_job
                        _record_seen_job(
                            _user_id, "naukri", job_url,
                            status="applied" if success else "skipped",
                            skip_reason="applied" if success else _skip_reason,
                            metadata=_skip_meta,
                        )
                    except Exception:
                        pass
                if success:
                    applied += 1
                    _record_application(task_input, job_url, _company_from_url(job_url))
                    print(f"  [NAUKRI] ✅ Applied ({applied}/{max_apply})")
                else:
                    skipped += 1
                    print(f"  [NAUKRI] ⏭  Skipped [{_skip_reason}] ({skipped} total) — trying next job")

            return {
                "applied_count": applied,
                "skipped_count": skipped,
                "message": f"Applied to {applied} jobs on Naukri",
            }

        except Exception as e:
            print(f"  [NAUKRI] ERROR: {e}")
            raise
        finally:
            browser.close()
            if _resume_tmp_path and os.path.isfile(_resume_tmp_path):
                try:
                    os.unlink(_resume_tmp_path)
                except Exception:
                    pass


# ──────────────────────────────────────────────────────────────
# Login
# ──────────────────────────────────────────────────────────────
def _login(page: Page, task_input: dict = None) -> bool:
    task_input = task_input or {}
    # Dashboard sends linkedin_email/linkedin_password for BOTH platforms — fall back to those keys.
    email    = (
        task_input.get("naukri_email")
        or task_input.get("linkedin_email")
        or os.environ.get("NAUKRI_EMAIL", "")
    ).strip()
    password = (
        task_input.get("naukri_password")
        or task_input.get("linkedin_password")
        or os.environ.get("NAUKRI_PASSWORD", "")
    ).strip()

    # Navigate directly to the Naukri login page (more reliable than clicking the header button)
    print("  [NAUKRI] Navigating to login page...")
    page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
    human_sleep(3.5, 5.5)  # React SPA needs time to render

    # If already logged in (avatar / profile icon visible), skip login
    for _logged_in_sel in [
        ".nI-gNb-menuItems .view-profile-wrapper",
        "[class*='nI-gNb-desktop__avatar']",
        "[class*='view-profile-wrapper']",
        "a[href*='/profile/']",
    ]:
        if page.locator(_logged_in_sel).count() > 0:
            print("  [NAUKRI] Already logged in ✅")
            return True

    # Wait for the login form fields to appear
    _EMAIL_SELS = (
        "input#usernameField, "
        "input[type='email'], "
        "input[placeholder*='Enter your active Email' i], "
        "input[placeholder*='Email ID' i], "
        "input[placeholder*='Email' i], "
        "input[placeholder*='Mobile' i], "
        "input[placeholder*='Username' i], "
        "input[name='username'], "
        "input[type='text']"
    )
    try:
        page.wait_for_selector(_EMAIL_SELS, timeout=10_000)
    except Exception:
        print("  [NAUKRI] Login form not found — trying to click Login button as fallback")
        for login_sel in ["a#login_Layer", "a.nI-gNb-lg-rg__login", "a:has-text('Login')"]:
            try:
                btn = page.locator(login_sel).first
                if btn.is_visible(timeout=2000):
                    human_click(page, locator=btn)
                    human_sleep(2.5, 4.5)
                    break
            except Exception:
                continue
        try:
            page.wait_for_selector(_EMAIL_SELS, timeout=8_000)
        except Exception:
            pass

    auto_login_attempted = False
    if email and password:
        # Auto-fill the login form
        try:
            filled_email = False
            for email_sel in [
                "input#usernameField",
                "input[type='email']:visible",
                "input[placeholder*='Enter your active Email' i]:visible",
                "input[placeholder*='Email' i]:visible",
                "input[placeholder*='Mobile' i]:visible",
                "input[placeholder*='Username' i]:visible",
                "input[name='username']:visible",
                "input[type='text']:visible",
            ]:
                try:
                    el = page.locator(email_sel).first
                    if el.is_visible(timeout=1500):
                        human_type(page, email, locator=el)
                        filled_email = True
                        print(f"  [NAUKRI] Email filled ({email_sel})")
                        break
                except Exception:
                    continue

            if filled_email:
                for pwd_sel in [
                    "input#passwordField",
                    "input[type='password']:visible",
                    "input[placeholder*='password' i]:visible",
                ]:
                    try:
                        pwd_el = page.locator(pwd_sel).first
                        if pwd_el.is_visible(timeout=1500):
                            human_sleep(0.4, 1.0)   # pause between email → password
                            human_type(page, password, locator=pwd_el, typo_rate=0.0)
                            print("  [NAUKRI] Password filled — clicking Login...")
                            break
                    except Exception:
                        continue
                micro_pause()
                for btn_sel in [
                    "button.loginButton",
                    "button[type='submit']:visible",
                    "button:has-text('Login'):visible",
                    "button:has-text('Sign in'):visible",
                ]:
                    try:
                        b = page.locator(btn_sel).first
                        if b.is_visible(timeout=1500):
                            human_sleep(0.5, 1.5)  # brief hesitation before login click
                            human_click(page, locator=b)
                            print("  [NAUKRI] Login button clicked — waiting for redirect...")
                            auto_login_attempted = True
                            human_sleep(3.5, 5.5)
                            break
                    except Exception:
                        continue
            else:
                print("  [NAUKRI] Could not find email input — falling back to manual login")
        except Exception as e:
            print(f"  [NAUKRI] Auto-fill failed ({e}), falling back to manual login")

    if auto_login_attempted:
        print("  [NAUKRI] Verifying auto-login...")
    else:
        print("  [NAUKRI] ============================================")
        print("  [NAUKRI]  Please log in to Naukri in the browser.  ")
        print("  [NAUKRI]  Waiting automatically — no ENTER needed.  ")
        print("  [NAUKRI]  (You have 3 minutes to log in)           ")
        print("  [NAUKRI] ============================================")

    try:
        # Wait until logged in: no login drawer visible AND not on login sub-page
        page.wait_for_function(
            """() => {
                // still on login sub-page
                if (window.location.href.includes('login.naukri.com')) return false;
                if (window.location.href.includes('/nlogin/')) return false;
                // drawer still open (only check if it exists)
                const drawer = document.querySelector('.drawer-wrapper');
                if (drawer && drawer.offsetParent !== null) return false;
                // login form still visible
                const loginForm = document.querySelector('input#usernameField, input#passwordField');
                if (loginForm && loginForm.offsetParent !== null) return false;
                return true;
            }""",
            timeout=180_000,
        )
        print(f"  [NAUKRI] Login confirmed ✅  URL: {page.url}")
        return True
    except Exception as e:
        print(f"  [NAUKRI] Login timed out or failed: {e}")
        return False


# ──────────────────────────────────────────────────────────────
# Job Search
# ──────────────────────────────────────────────────────────────
def _search_jobs(page: Page, keywords: str, location: str, task_input: dict = None) -> list[str]:
    """Navigate to Naukri job search and return a deduplicated list of job URLs."""
    print(f"  [NAUKRI] Searching: '{keywords}' in '{location or 'anywhere'}'")

    kw_slug  = re.sub(r"[^a-z0-9]+", "-", keywords.strip().lower()).strip("-")
    loc_slug = re.sub(r"[^a-z0-9]+", "-", location.strip().lower()).strip("-") if location else ""

    # Use Naukri's canonical SEO URL format: /keyword-jobs-in-location
    if loc_slug:
        base_url = f"{NAUKRI_URL}/{kw_slug}-jobs-in-{loc_slug}"
    else:
        base_url = f"{NAUKRI_URL}/{kw_slug}-jobs"

    # ── Embed filters as URL query params (much more reliable than clicking UI) ──
    task_input = task_input or {}
    from urllib.parse import urlencode
    params = {}

    years = int(float(task_input.get("years_experience", 0) or 0))
    if years > 0:
        exp_min = max(0, years - 1)
        exp_max = years + 3
        params["experience"] = f"{exp_min}-{exp_max}"

    freshness = task_input.get("freshness_days")
    if freshness:
        params["jobAge"] = int(freshness)

    work_mode = str(task_input.get("work_mode") or "").lower()
    _wfh_code = {"remote": "0", "work from home": "0", "wfh": "0", "hybrid": "3", "office": "2", "wfo": "2"}
    for _k, _v in _wfh_code.items():
        if _k in work_mode:
            params["wfhType"] = _v
            break

    # Job type (Naukri: jobtype=1 permanent, 2 contractual, 3 temporary)
    _naukri_jobtype_map = {"fullTime": "1", "contract": "2", "temporary": "3"}
    _naukri_jt = str(task_input.get("naukri_job_type", "all"))
    if _naukri_jt in _naukri_jobtype_map:
        params["jobtype"] = _naukri_jobtype_map[_naukri_jt]

    search_url = f"{base_url}?{urlencode(params)}" if params else base_url
    print(f"  [NAUKRI] URL: {search_url}")
    page.goto(search_url, wait_until="domcontentloaded")
    human_sleep(4.5, 6.5)  # give React SPA time to render initial batch

    # Scroll down to trigger lazy-loaded job cards
    for _ in range(3):
        page.keyboard.press("End")
        human_sleep(1.2, 2.0)
    page.keyboard.press("Home")
    human_sleep(1.5, 2.5)

    # Also try sidebar filters as a best-effort secondary attempt
    _apply_filters(page, task_input)
    human_sleep(1.5, 2.5)

    # ── Collect job links across multiple pages ──────────────
    max_apply   = int((task_input or {}).get("max_apply", MAX_APPLY))
    # Pool per keyword: 3× buffer so skips don't exhaust the list; floor 100, cap 300
    target_pool = min(max(max_apply * 3, 100), 300)
    max_pages   = 15                       # safety cap (300 URLs ÷ ~20/page)
    seen: set   = set()
    job_links: list[str] = []

    def _collect_links_from_page() -> list[str]:
        """Extract deduplicated job listing links from the current page DOM."""
        found = []

        # Strategy 1: JS evaluate — match /job-listings (covers both /job-listings- and /job-listings/)
        try:
            raw = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href.split('?')[0].split('#')[0])
                            .filter(h => h.includes('naukri.com') && h.includes('/job-listings'))
                            .filter((v, i, s) => s.indexOf(v) === i)"""
            )
            found = [l for l in raw if l]
        except Exception:
            pass

        # Strategy 2: broader JS — any naukri.com link with a numeric ID (job links always have IDs)
        if not found:
            try:
                raw = page.evaluate(
                    r"""() => Array.from(document.querySelectorAll('a[href*="naukri.com"]'))
                                .map(a => a.href.split('?')[0].split('#')[0])
                                .filter(h => /\/job-listings/.test(h) || /-\d{8,}/.test(h))
                                .filter((v, i, s) => s.indexOf(v) === i)"""
                )
                found = [l for l in raw if l]
            except Exception:
                pass

        # Strategy 3: CSS selector fallbacks
        if not found:
            def _css(selector: str):
                try:
                    for el in page.locator(selector).all():
                        href = (el.get_attribute("href") or "").split("?")[0]
                        if "naukri.com" in href and "/job-listings" in href:
                            found.append(href)
                except Exception:
                    pass
            _css("a[href*='/job-listings']")
            _css("article.jobTuple a[href]")
            _css(".srp-jobtuple-wrapper a[href]")
            _css(".jobTupleHeader a[href]")

        return found

    for page_num in range(1, max_pages + 1):
        if page_num > 1:
            # Navigate to subsequent pages: Naukri appends -2, -3, … to the base slug,
            # then re-add the query params so filters stay active
            next_base = f"{base_url}-{page_num}"
            next_url  = f"{next_base}?{urlencode(params)}" if params else next_base
            print(f"  [NAUKRI] Paginating to page {page_num}: {next_url}")
            page.goto(next_url, wait_until="domcontentloaded")
            human_sleep(3.5, 5.5)
            for _ in range(3):
                page.keyboard.press("End")
                human_sleep(1.2, 2.0)
            page.keyboard.press("Home")
            human_sleep(1.5, 2.5)

        new_links = _collect_links_from_page()
        before = len(job_links)
        for link in new_links:
            if link not in seen:
                seen.add(link)
                job_links.append(link)

        added = len(job_links) - before
        print(f"  [NAUKRI] Page {page_num}: +{added} new links (total {len(job_links)})")

        if added == 0:
            print(f"  [NAUKRI] No new jobs on page {page_num} — stopping pagination")
            break

        if len(job_links) >= target_pool:
            print(f"  [NAUKRI] Pool of {len(job_links)} links is sufficient — stopping pagination")
            break

    # Debug: if still empty, show a sample of all hrefs to diagnose selector issues
    if not job_links:
        try:
            sample = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(h => h.includes('naukri.com') && !h.includes('naukri.com/#') && !h.includes('cdn') && h.length > 30)
                            .slice(0, 20)"""
            )
            print(f"  [NAUKRI] DEBUG — all naukri links on page:")
            for s in sample:
                print(f"    {s}")
        except Exception:
            pass

    print(f"  [NAUKRI] Found {len(job_links)} job links (across {page_num} page(s))")
    return job_links


# ──────────────────────────────────────────────────────────────
# Per-job application
# ──────────────────────────────────────────────────────────────
def _apply_to_job(page: Page, job_url: str, task_input: dict = None) -> bool:
    """
    Open a Naukri job listing and apply.
    Supports full-auto and semi-auto modes.
    Returns True if the application was submitted (or handed off to user in semi-auto).
    """
    task_input = task_input or {}
    semi_auto   = task_input.get("semi_auto", False)
    apply_types = task_input.get("apply_types", "both")  # "both" | "direct_only" | "company_site_only"

    print(f"  [NAUKRI] Opening: {job_url}")
    if not _safe_goto(page, job_url):
        print(f"  [NAUKRI] Could not load job page after retries — skipping")
        return False
    human_sleep(NAV_WAIT, NAV_WAIT + 2)

    try:
        # ── Skip if already applied ───────────────────────────────
        try:
            already_applied = page.locator(
                "button:has-text('Applied'), "
                ".applied-badge, "
                "span:has-text('You have already applied')"
            ).first.is_visible(timeout=2000)
            if already_applied:
                print("  [NAUKRI] Already applied — skipping")
                return False
        except Exception:
            pass

        # ── Extract JD text (needed for smart match and/or resume tailoring) ─
        needs_jd        = task_input.get("smart_match", False) or task_input.get("tailor_resume", False)
        smart_match     = task_input.get("smart_match", False)
        match_threshold = int(task_input.get("match_threshold", 70))
        jd_text         = ""

        if needs_jd:
            try:
                for jd_sel in [
                    ".styles_JDC__dang-inner-html__h0K4t",
                    "[class*='job-desc']",
                    "[class*='jd-desc']",
                    "section.styles_job-desc-container__txpYf",
                    "div[class*='jobDescription']",
                    "div.job-description",
                ]:
                    el = page.locator(jd_sel).first
                    if el.count() > 0:
                        candidate = (el.text_content() or "").strip()
                        if len(candidate) > 100:
                            jd_text = candidate[:6000]
                            break
            except Exception:
                pass

        # ── Smart match gate ──────────────────────────────────────
        if smart_match:
            resume_text_sm = task_input.get("resume_text", "")
            if resume_text_sm:
                if jd_text:
                    try:
                        from automation.ai_client import match_score
                        result  = match_score(resume_text_sm, jd_text)
                        score   = result.get("score", 0)
                        missing = result.get("missing_skills", [])
                        print(f"  [NAUKRI] 🎯 Match score: {score}% (threshold: {match_threshold}%) | Missing: {', '.join(missing[:4]) or 'none'}")
                        if score < match_threshold:
                            print(f"  [NAUKRI] ⏭  Skipped (score {score}% < {match_threshold}%)")
                            task_input["_last_skip_reason"] = "smart_match"
                            return False
                        task_input = dict(task_input)
                        task_input["_last_match_score"] = score
                    except Exception as _me:
                        print(f"  [NAUKRI] ⚠️  Match scoring failed ({_me}) — applying anyway")
                else:
                    print("  [NAUKRI] ⚠️  Could not extract JD for smart match — applying anyway")
            else:
                print("  [NAUKRI] ⚠️  Smart match skipped — no resume text available")

        # ── Tailor resume to this JD if requested ─────────────────
        if task_input.get("tailor_resume") and jd_text:
            resume_path = task_input.get("resume_path", "")
            if not resume_path or not os.path.isfile(resume_path):
                print("  [NAUKRI] ⚠️  No resume file for tailoring — applying with original")
            else:
                try:
                    from automation.resume_tailor import tailor_resume_for_job
                    company       = task_input.get("company", "")
                    role          = task_input.get("keywords", "")
                    custom_prompt = task_input.get("tailor_custom_prompt", "")
                    print(f"  [NAUKRI] ✨ Tailoring resume for '{role or 'this role'}' at '{company or 'this company'}'…")
                    result = tailor_resume_for_job(
                        resume_source=resume_path,
                        jd_text=jd_text,
                        custom_prompt=custom_prompt,
                        company=company,
                        role=role,
                        save_pdf=True,
                    )
                    print(f"  [NAUKRI] Match: {result.score_before:.0f}% → {result.score_after:.0f}%  ATS: {result.ats_score}")
                    if result.tailored_pdf_path and os.path.isfile(result.tailored_pdf_path):
                        task_input = dict(task_input)
                        task_input["resume_path"]   = result.tailored_pdf_path
                        task_input["_tailored_pdf"] = result.tailored_pdf_path
                except Exception as _te:
                    print(f"  [NAUKRI] ⚠️  Tailoring failed ({_te}) — applying with original resume")

        # ── Handle "Apply on company site" ──────────────────────
        try:
            # Only treat as company-site if the company-site button exists AND
            # there is NO direct Naukri apply button present.
            _direct_apply_present = False
            for _da_sel in [
                "button#apply-button",
                "button.apply-button:not(.company-site-button)",
                "button.styles_apply-button__uJI3A",
                "button:has-text('Easy Apply')",
            ]:
                try:
                    if page.locator(_da_sel).first.is_visible(timeout=1000):
                        _direct_apply_present = True
                        break
                except Exception:
                    pass

            company_btn = page.locator(
                "button#company-site-button, button.company-site-button, "
                "a#company-site-button, a.company-site-button, "
                "button:has-text('Apply on company site'), "
                "a:has-text('Apply on company site')"
            ).first
            if company_btn.is_visible(timeout=2000) and not _direct_apply_present:
                if apply_types == "direct_only":
                    print("  [NAUKRI] Company-site job — skipped (direct_only mode)")
                    task_input["_last_skip_reason"] = "mode_skip"
                    return False
                print("  [NAUKRI] 'Apply on company site' — attempting external apply...")
                result = _apply_company_site(page, company_btn, task_input, naukri_job_url=job_url)
                return result
        except Exception:
            pass

        # ── Capture job location for relocation Q ────────────────
        try:
            loc_el = page.locator(
                ".styles_jhc__location__W_pVs a, "
                "[class*='jhc__location'] a, "
                "[class*='jhc__loc'] span:visible"
            ).first
            if loc_el.is_visible(timeout=2000):
                task_input["_job_location"] = loc_el.inner_text().strip()
        except Exception:
            pass

        # ── Find Apply button ─────────────────────────────────────
        apply_btn = None
        for sel in [
            "button#apply-button",
            "button.apply-button:not(.company-site-button)",
            "button.styles_apply-button__uJI3A",
            "button:has-text('Easy Apply')",
            "button:has-text('Apply'):not(:has-text('company'))",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    apply_btn = btn
                    print(f"  [NAUKRI] Apply button via: {sel}")
                    break
            except Exception:
                continue

        if apply_btn is None:
            print("  [NAUKRI] No Apply button — skipping")
            return False

        if apply_types == "company_site_only":
            print("  [NAUKRI] Direct-apply job — skipped (company_site_only mode)")
            task_input["_last_skip_reason"] = "mode_skip"
            return False

        url_before = page.url
        human_click(page, locator=apply_btn)
        idle_jiggle(page, duration=random.uniform(2.5, 4.0))   # jiggle while form loads

        # Bail if redirected externally
        if "naukri.com" not in page.url:
            print(f"  [NAUKRI] External redirect ({page.url[:60]}) — skipping")
            page.goto(url_before)
            return False

        # ── Semi-auto mode: pre-fill fields, then let user submit ──
        if semi_auto:
            # Pre-fill what we can before handing off
            _fill_naukri_fields(page, task_input)
            human_sleep(0.8, 1.5)
            print(
                "  [NAUKRI] [SEMI-AUTO] ⏸  Form pre-filled. "
                "Please review and click Submit/Apply in the browser."
            )
            _POST_APPLY_SELS = (
                ".success-message, .confirmation-message, "
                "div:has-text('application has been sent'), "
                "div:has-text('successfully applied'), "
                "div:has-text('Application submitted'), "
                "p:has-text('Your application has been sent')"
            )
            detected = False
            for _ in range(150):  # poll for up to 5 min
                try:
                    if page.locator(_POST_APPLY_SELS).first.is_visible(timeout=500):
                        detected = True
                        break
                except Exception:
                    pass
                time.sleep(2)
            if detected:
                print("  [NAUKRI] [SEMI-AUTO] ✅ Submission detected!")
                _dismiss_post_apply(page)
                return True
            print("  [NAUKRI] [SEMI-AUTO] Timed out — skipping")
            _dismiss_post_apply(page)
            return False

        # ── Full-auto: chatbot drawer + legacy multi-step form ────
        result = _handle_application_flow(page, task_input)
        _dismiss_post_apply(page)
        return result

    except Exception as e:
        print(f"  [NAUKRI] Apply error on {job_url}: {e}")
        import traceback
        traceback.print_exc()

    _dismiss_post_apply(page)
    return False


# ──────────────────────────────────────────────────────────────
# Field filling
# ──────────────────────────────────────────────────────────────
def _fill_naukri_fields(page: Page, task_input: dict):
    """Fill all visible form fields on the current Naukri step."""
    task_input  = task_input or {}
    years       = task_input.get("years_experience", 2)
    notice      = task_input.get("notice_period", 30)
    salary      = str(task_input.get("salary_expectation", "") or "")
    cover_note  = task_input.get(
        "cover_note",
        "I am very interested in this role and believe my skills and experience align well with the requirements.",
    )

    # ── Resume upload ─────────────────────────────────────────
    _upload_resume(page, task_input)

    # ── Text / Number inputs ──────────────────────────────────
    try:
        for inp in page.locator("input[type='text']:visible, input[type='number']:visible").all():
            try:
                if (inp.input_value() or "").strip():
                    continue
                inp_id      = (inp.get_attribute("id")          or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                name_attr   = (inp.get_attribute("name")        or "").lower()
                combined    = f"{inp_id} {placeholder} {name_attr}"

                if any(w in combined for w in ("experience", "year", "exp", "totalexp")):
                    human_type(page, str(int(years)), locator=inp)
                    print(f"  [NAUKRI] Filled experience = {years}")
                elif any(w in combined for w in ("notice", "noticeperiod")):
                    human_type(page, str(int(notice)), locator=inp)
                    print(f"  [NAUKRI] Filled notice = {notice}")
                elif any(w in combined for w in ("currentctc", "current ctc", "current_ctc", "presentctc")):
                    current_ctc = str(task_input.get("current_ctc") or "")
                    if current_ctc:
                        human_type(page, current_ctc, locator=inp)
                        print(f"  [NAUKRI] Filled current CTC = {current_ctc}")
                elif any(w in combined for w in ("expectedctc", "expected ctc", "expected_ctc", "salary", "lpa", "ctc", "expected")):
                    expected = str(task_input.get("expected_ctc") or task_input.get("salary_expectation") or "")
                    if expected:
                        human_type(page, expected, locator=inp)
                        print(f"  [NAUKRI] Filled expected CTC = {expected}")
            except Exception:
                pass
    except Exception:
        pass

    # ── Textareas ─────────────────────────────────────────────
    try:
        for ta in page.locator("textarea:visible").all():
            try:
                if (ta.input_value() or "").strip():
                    continue
                human_type(page, cover_note, locator=ta)
                print("  [NAUKRI] Filled textarea")
            except Exception:
                pass
    except Exception:
        pass

    # ── Select dropdowns ──────────────────────────────────────
    try:
        for sel in page.locator("select:visible").all():
            try:
                current = sel.evaluate("el => el.value") or ""
                if current.lower() not in ("", "select", "please select", "-1", "0", "none"):
                    continue
                opts       = sel.locator("option").all()
                opt_vals   = [(o.get_attribute("value") or "").strip() for o in opts]
                opt_texts  = [(o.inner_text()           or "").strip().lower() for o in opts]
                # prefer "Yes" / "Immediate"
                for i, t in enumerate(opt_texts):
                    if t in ("yes", "immediate", "immediately", "0 days"):
                        sel.select_option(opt_vals[i])
                        print(f"  [NAUKRI] Dropdown selected: {opt_texts[i]}")
                        break
                else:
                    for i, v in enumerate(opt_vals):
                        if v and v.lower() not in ("", "select", "please select", "-1", "0", "none"):
                            sel.select_option(v)
                            print(f"  [NAUKRI] Dropdown first option: {v[:40]}")
                            break
            except Exception:
                pass
    except Exception:
        pass

    # ── Radio buttons ─────────────────────────────────────────
    try:
        seen_names: set = set()
        radios = page.locator("input[type='radio']:visible").all()
        for r in radios:
            try:
                name = r.get_attribute("name") or ""
                if name in seen_names or r.is_checked():
                    seen_names.add(name)
                    continue
                val        = (r.get_attribute("value") or "").lower()
                label_id   = r.get_attribute("id") or ""
                label_text = ""
                if label_id:
                    lbl = page.locator(f"label[for='{label_id}']")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().lower()
                if val in ("yes", "true", "1") or "yes" in label_text:
                    r.click()
                    seen_names.add(name)
                    print(f"  [NAUKRI] Clicked radio Yes — group '{name}'")
            except Exception:
                pass
        # Second pass: click first unchecked group
        for r in radios:
            try:
                name = r.get_attribute("name") or ""
                if name in seen_names:
                    continue
                r.click()
                seen_names.add(name)
                print(f"  [NAUKRI] Clicked first radio — group '{name}'")
            except Exception:
                pass
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# Resume upload
# ──────────────────────────────────────────────────────────────
def _upload_resume(page: Page, task_input: dict):
    """Set resume on the file input if present. Uses local resume_path first, then downloads from resume_url."""
    task_input = task_input or {}

    try:
        file_input = page.locator("input[type='file']").first
        if file_input.count() == 0:
            return
        if not file_input.is_visible(timeout=1500):
            return
    except Exception:
        return

    # ── Use already-downloaded local file if available ────────
    local_path = task_input.get("resume_path", "").strip()
    if local_path and os.path.isfile(local_path):
        try:
            file_input.set_input_files(local_path)
            time.sleep(2)
            print(f"  [NAUKRI] ✅ Resume set from local file: {os.path.basename(local_path)}")
        except Exception as e:
            print(f"  [NAUKRI] Resume upload error: {e}")
        return

    # ── Fallback: download from URL ────────────────────────────
    resume_url = task_input.get("resume_url", "").strip()
    if not resume_url:
        return

    try:
        print("  [NAUKRI] Downloading resume...")
        resp = http_req.get(resume_url, timeout=30)
        if resp.status_code != 200:
            print(f"  [NAUKRI] Resume download failed: HTTP {resp.status_code}")
            return

        filename = task_input.get("resume_filename", "resume.pdf")
        suffix   = os.path.splitext(filename)[1] or ".pdf"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name

        try:
            file_input.set_input_files(tmp_path)
            time.sleep(2)
            print(f"  [NAUKRI] ✅ Resume uploaded: {filename}")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    except Exception as e:
        print(f"  [NAUKRI] Resume upload error: {e}")


# ──────────────────────────────────────────────────────────────
# Application flow — chatbot drawer + legacy multi-step form
# ──────────────────────────────────────────────────────────────
def _handle_application_flow(page: Page, task_input: dict) -> bool:
    """
    Drive the full Naukri application after the Apply button has been clicked.
    Handles both:
      • Naukri's chatbot-style Q&A drawer (career break, CTC, notice, relocation…)
      • Legacy multi-step web forms
    """
    _SUBMIT_SEL = (
        "button:has-text('Submit'), button:has-text('Apply Now'), "
        "button[type='submit']:has-text('Apply'), button:has-text('Send Application')"
    )
    _NEXT_SEL = (
        "button:has-text('Next'), button:has-text('Continue'), "
        "button:has-text('Save & Next')"
    )

    for step in range(20):
        human_sleep(1.5, 3.0)
        print(f"  [NAUKRI] Application step {step + 1}")

        if _check_applied_success(page):
            print("  [NAUKRI] Application successful!")
            return True

        # Resume upload (works both in chatbot drawer and legacy forms)
        _upload_resume(page, task_input)

        # Handle chatbot Q&A step first
        if _handle_chatbot_step(page, task_input):
            continue

        # Legacy web form fields
        _fill_naukri_fields(page, task_input)
        human_sleep(0.8, 1.8)

        # Submit button
        try:
            if page.locator(_SUBMIT_SEL).first.is_visible(timeout=2000):
                if _click_if_visible(page, _SUBMIT_SEL, timeout=2500):
                    human_sleep(2.5, 4.5)
                    print("  [NAUKRI] Submitted!")
                    return True
        except Exception:
            pass

        # Next / Continue
        if _click_if_visible(page, _NEXT_SEL, timeout=2500):
            continue

        print(f"  [NAUKRI] No actionable button on step {step + 1} — done")
        break

    return _check_applied_success(page)


def _handle_chatbot_step(page: Page, task_input: dict) -> bool:
    """
    Handle one step of Naukri's chatbot-style application questionnaire.
    Returns True if an action was taken (so the caller knows to loop again).

    Questions handled:
      • Career break?            → No
      • Current CTC              → from task_input, else Skip
      • Expected CTC             → from task_input, else Skip
      • Notice period            → mapped from notice_period_days
      • Relocation / residency   → Yes if job location matches user pref, else No
      • Generic Yes/No           → No (safe default)
    """
    # ── Detect chatbot radio buttons ─────────────────────────────
    radio_containers = page.locator(
        ".singleselect-radiobutton-container:visible, "
        "[id*='SingleSelectRadioButton']:visible"
    )
    has_radios = radio_containers.count() > 0

    # ── Detect chatbot text / number input ───────────────────────
    chatbot_inp = page.locator(
        "[class*='chatbot'] input[type='text']:visible, "
        "[class*='chatbot'] input[type='number']:visible, "
        "[class*='chat'] input[type='number']:visible, "
        "[class*='drawer'] input[type='number']:visible, "
        "input[placeholder*='Enter']:visible"
    ).first
    has_text_input = False
    try:
        has_text_input = chatbot_inp.is_visible(timeout=1000)
    except Exception:
        pass

    if not has_radios and not has_text_input:
        return False

    # Get all visible page text to determine question context
    try:
        page_text = page.locator("body").inner_text()
    except Exception:
        page_text = ""
    pl = page_text.lower()

    # ── Text input question (experience / CTC / salary) ──────────
    if has_text_input:
        val = None
        if any(w in pl for w in ("years of experience", "total experience", "work experience", "experience in years", "years experience")):
            val = str(int(float(task_input.get("years_experience", 2) or 2)))
            print(f"  [NAUKRI] Experience input → {val}")
        elif "current ctc" in pl or ("current" in pl and "lacs" in pl and "salary" not in pl):
            val = str(task_input.get("current_ctc") or "")
        elif "expected ctc" in pl or ("expected" in pl and "lacs" in pl):
            val = str(
                task_input.get("expected_ctc")
                or task_input.get("salary_expectation")
                or ""
            )

        if val:
            try:
                human_type(page, val, locator=chatbot_inp)
                print(f"  [NAUKRI] Chatbot input filled → {val}")
                micro_pause()
                _try_chatbot_proceed(page)
                return True
            except Exception:
                pass

        # No value — skip the question
        if _click_skip(page):
            print("  [NAUKRI] CTC → Skipped")
            micro_pause()
            _try_chatbot_proceed(page)
            return True

    # ── Radio button question ─────────────────────────────────────
    if has_radios:
        if "career break" in pl:
            _click_radio_by_value(page, "No")
            print("  [NAUKRI] Career break → No")

        elif "notice period" in pl:
            notice_days = int(task_input.get("notice_period", 30))
            _click_radio_for_notice(page, notice_days)
            print(f"  [NAUKRI] Notice period → {notice_days} days")

        elif "relocat" in pl or ("willing" in pl and "reside" in pl):
            job_loc   = task_input.get("_job_location", "").lower()
            pref_locs = [
                p.strip().lower()
                for p in str(task_input.get("location", "")).split(",")
                if p.strip()
            ]
            willing = not pref_locs or any(
                p in job_loc or job_loc in p for p in pref_locs
            )
            _click_radio_by_value(page, "Yes" if willing else "No")
            print(f"  [NAUKRI] Relocation → {'Yes' if willing else 'No'}")

        else:
            # Generic question — skip if possible, otherwise default No
            if not _click_skip(page):
                if not _click_radio_by_value(page, "No"):
                    _click_radio_by_value(page, "Yes")
            print("  [NAUKRI] Generic radio → answered")

        micro_pause()
        _try_chatbot_proceed(page)
        return True

    return False


# ──────────────────────────────────────────────────────────────
# Company-site external apply  (Claude-powered)
# ──────────────────────────────────────────────────────────────
def _apply_company_site(page: Page, company_btn, task_input: dict, naukri_job_url: str = "") -> bool:
    """
    Navigate to the company's career site, fill the form with resume data + Claude AI,
    and submit (full-auto) or hand off to the user (semi-auto).
    After applying, the browser returns to naukri_job_url so the bot can continue.
    """
    task_input = task_input or {}
    semi_auto  = task_input.get("semi_auto", False)

    # Current Naukri URL to come back to after same-tab navigation
    naukri_return_url = naukri_job_url or page.url or NAUKRI_URL

    # ── Get direct href if available (avoids popup) ───────────────────
    ext_url = None
    try:
        href = (company_btn.get_attribute("href") or "").strip()
        if href.startswith("http"):
            ext_url = href
    except Exception:
        pass

    target_page = None
    opened_popup = False

    if not ext_url:
        # Button click may open a new tab on Naukri
        try:
            with page.context.expect_page(timeout=6000) as popup_info:
                human_click(page, locator=company_btn)
            target_page  = popup_info.value
            opened_popup = True
            target_page.wait_for_load_state("domcontentloaded", timeout=20000)
            human_sleep(1.5, 3.0)
            print(f"  [NAUKRI] Company site (new tab): {target_page.url[:70]}")
        except Exception as popup_err:
            print(f"  [NAUKRI] No new-tab popup ({popup_err}) — checking same-tab navigation...")
            human_sleep(1.5, 3.0)
            if "naukri.com" not in page.url:
                # Button navigated the current tab to the company site
                target_page = page
                print(f"  [NAUKRI] Company site (same tab): {page.url[:70]}")
            else:
                # Try clicking once more and navigating via data-href or onclick
                try:
                    human_click(page, locator=company_btn)
                    human_sleep(2.5, 4.5)
                    if "naukri.com" not in page.url:
                        target_page = page
                        print(f"  [NAUKRI] Company site (same tab, retry): {page.url[:70]}")
                    else:
                        print("  [NAUKRI] Could not navigate to company site — skipping")
                        return False
                except Exception:
                    return False
    else:
        print(f"  [NAUKRI] Company site (direct URL): {ext_url[:70]}")
        try:
            page.goto(ext_url, wait_until="domcontentloaded", timeout=20000)
            human_sleep(2.5, 4.5)
            target_page = page
        except Exception as nav_err:
            print(f"  [NAUKRI] Navigation failed: {nav_err}")
            return False

    # ── Click "Apply Now" if we landed on a job-detail page (not the form) ──
    for _apply_now_sel in [
        "button:has-text('Apply Now'):visible",
        "button:has-text('Apply for this job'):visible",
        "button:has-text('Apply for this position'):visible",
        "a:has-text('Apply Now'):visible",
        "a.apply-button:visible",
    ]:
        try:
            btn = target_page.locator(_apply_now_sel).first
            if btn.is_visible(timeout=1000):
                _cur_domain = target_page.url.split("/")[2] if "://" in target_page.url else ""
                btn_href    = btn.get_attribute("href") or ""
                # Only click if staying on same domain
                if not btn_href.startswith("http") or _cur_domain in btn_href:
                    human_click(target_page, locator=btn)
                    target_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    human_sleep(1.5, 3.0)
                    print(f"  [NAUKRI] Clicked 'Apply Now' on company site")
                    break
        except Exception:
            pass

    result = _fill_and_submit_external(target_page, task_input, use_ai=True, semi_auto=semi_auto)

    # ── Navigate back to Naukri after same-tab navigation ────────────
    if not opened_popup and target_page is page:
        try:
            print(f"  [NAUKRI] Returning to Naukri: {naukri_return_url[:60]}")
            page.goto(naukri_return_url, wait_until="domcontentloaded", timeout=20000)
            human_sleep(NAV_WAIT, NAV_WAIT + 2)
        except Exception as back_err:
            print(f"  [NAUKRI] Could not navigate back to Naukri: {back_err}")

    # ── Close popup tab ───────────────────────────────────────────────
    if opened_popup and target_page is not None:
        try:
            target_page.close()
        except Exception:
            pass

    return result


def _fill_and_submit_external(page: Page, task_input: dict, use_ai: bool = False, semi_auto: bool = False) -> bool:
    """
    Fill and submit a generic external ATS / company application form.

    1. Claude AI analyses the page HTML and returns precise fill actions (if use_ai=True).
    2. Falls back to keyword-based dumb fill on any AI failure.
    3. Uploads resume file.
    4. semi_auto=True → fills everything then waits up to 5 min for the user to submit.
    5. Full-auto → tries multiple submit-button selectors and clicks the first visible one.
    """
    from automation.ai_client import analyze_and_fill_form

    task_input = task_input or {}
    # All credential key variants (dashboard sends linkedin_email for both platforms)
    email_addr = (
        task_input.get("naukri_email")
        or task_input.get("linkedin_email")
        or task_input.get("email")
        or os.environ.get("NAUKRI_EMAIL", "")
    ).strip()
    name       = (task_input.get("full_name") or task_input.get("name") or "").strip()
    phone      = task_input.get("phone", "")
    years      = task_input.get("years_experience", 2)
    cover_note = task_input.get(
        "cover_note",
        "I am very interested in this role and my skills align well with the requirements.",
    )

    human_sleep(1.5, 3.0)

    ai_did_fill = False

    # ── Claude-powered fill ─────────────────────────────────────────
    if use_ai:
        try:
            form_html    = page.content()
            user_profile = {
                "full_name":        name,
                "email":            email_addr,
                "phone":            phone,
                "years_experience": years,
                "cover_note":       cover_note,
                "resume_text":      task_input.get("resume_text", ""),
            }
            actions = analyze_and_fill_form(form_html, user_profile)
            if actions:
                print(f"  [NAUKRI] 🤖 Claude returned {len(actions)} form actions")
                for act in actions:
                    action   = act.get("action", "fill")
                    selector = act.get("selector", "")
                    value    = act.get("value", "")
                    if not selector:
                        continue
                    # Skip submit actions in semi-auto — user submits manually
                    if action == "click" and semi_auto:
                        print("  [NAUKRI] [SEMI-AUTO] Skipping submit click (user will submit)")
                        continue
                    try:
                        el = page.locator(selector).first
                        if not el.is_visible(timeout=1500):
                            continue
                        if action == "fill":
                            if not (el.input_value() or "").strip():
                                human_type(page, str(value), locator=el)
                        elif action == "select":
                            el.select_option(str(value))
                        elif action == "click":
                            human_click(page, locator=el)
                            human_sleep(1.5, 3.0)
                    except Exception:
                        pass
                ai_did_fill = True
        except Exception as ai_err:
            print(f"  [NAUKRI] Claude form fill error: {ai_err} — falling back to dumb fill")

    # ── Dumb fill fallback ──────────────────────────────────────────
    if not ai_did_fill:
        print("  [NAUKRI] Using generic form fill (no AI)")
        if email_addr:
            for sel in ["input[type='email']", "input[placeholder*='mail' i]", "input[name*='email' i]"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=800) and not (el.input_value() or "").strip():
                        human_type(page, email_addr, locator=el)
                        break
                except Exception:
                    pass

        if name:
            parts = name.strip().split(" ", 1)
            first, last = parts[0], (parts[1] if len(parts) > 1 else "")
            for sel in ["input[name*='firstName' i]", "input[placeholder*='first name' i]",
                        "input[name*='first' i]", "input[placeholder*='name' i]"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=500) and not (el.input_value() or "").strip():
                        human_type(page, first, locator=el)
                        break
                except Exception:
                    pass
            if last:
                for sel in ["input[name*='lastName' i]", "input[placeholder*='last name' i]",
                            "input[name*='last' i]"]:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=500) and not (el.input_value() or "").strip():
                            human_type(page, last, locator=el)
                            break
                    except Exception:
                        pass

        if phone:
            for sel in ["input[type='tel']", "input[placeholder*='phone' i]", "input[name*='phone' i]"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=500) and not (el.input_value() or "").strip():
                        human_type(page, str(phone), locator=el)
                        break
                except Exception:
                    pass

        try:
            for ta in page.locator("textarea:visible").all():
                try:
                    if not (ta.input_value() or "").strip():
                        human_type(page, cover_note, locator=ta)
                        break
                except Exception:
                    pass
        except Exception:
            pass

    # ── Resume upload (always, regardless of fill method) ──────────
    _upload_resume(page, task_input)
    human_sleep(0.5, 1.5)

    # ── Semi-auto: hand off to user, poll for completion ───────────
    if semi_auto:
        print(
            "  [NAUKRI] [SEMI-AUTO] ⏸  Company site form filled. "
            "Please review and click Submit in the browser."
        )
        _initial_url = page.url
        _SUCCESS_SELS = [
            "div:has-text('Thank you for applying')",
            "div:has-text('application submitted')",
            "div:has-text('application has been received')",
            "div:has-text('successfully applied')",
            "h1:has-text('Thank you')",
            "h2:has-text('Thank you')",
            "p:has-text('Thank you for your application')",
            ".thank-you, .success-page, .confirmation",
        ]
        deadline = time.time() + 300  # 5-minute max wait
        detected = False
        while time.time() < deadline:
            if page.url != _initial_url:
                detected = True
                print(f"  [NAUKRI] [SEMI-AUTO] URL changed → {page.url[:60]}")
                break
            for _s in _SUCCESS_SELS:
                try:
                    if page.locator(_s).first.is_visible(timeout=400):
                        detected = True
                        break
                except Exception:
                    pass
            if detected:
                break
            time.sleep(2)
        if detected:
            print("  [NAUKRI] [SEMI-AUTO] ✅ Company site submission detected!")
        else:
            print("  [NAUKRI] [SEMI-AUTO] Timed out — treating as skipped")
        return detected

    # ── Full-auto: click Submit ─────────────────────────────────────
    for sub_sel in [
        "button[type='submit']:visible",
        "button:has-text('Submit Application'):visible",
        "button:has-text('Submit your application'):visible",
        "button:has-text('Apply Now'):visible",
        "button:has-text('Apply'):visible",
        "button:has-text('Submit'):visible",
        "input[type='submit']:visible",
        "a:has-text('Submit Application'):visible",
    ]:
        try:
            btn = page.locator(sub_sel).first
            if btn.is_visible(timeout=1500):
                human_sleep(0.5, 1.5)    # last-second hesitation
                human_click(page, locator=btn)
                human_sleep(2.5, 4.5)
                print("  [NAUKRI] Company site: submitted! ✅")
                return True
        except Exception:
            pass

    # If Claude filled but we couldn't find a submit button, report as best-effort success
    if ai_did_fill:
        print("  [NAUKRI] 🤖 Form filled by Claude but no submit button found — marking as best-effort")
        return True

    print("  [NAUKRI] Company site: no submit button found — skipping")
    return False


# ──────────────────────────────────────────────────────────────
# Sidebar filter application
# ──────────────────────────────────────────────────────────────
def _apply_filters(page: Page, task_input: dict):
    """
    Apply Naukri sidebar filters as a secondary best-effort attempt.
    Primary filtering is done via URL query params in _search_jobs.
    """
    if not task_input:
        return

    # ── Work mode filter ─────────────────────────────────────────
    work_mode = str(task_input.get("work_mode") or "").lower()
    if work_mode:
        mode_label_map = {
            "remote":         ["Work from home", "Remote", "WFH"],
            "work from home": ["Work from home", "Remote", "WFH"],
            "wfh":            ["Work from home", "Remote", "WFH"],
            "hybrid":         ["Hybrid"],
            "office":         ["Work from office", "On-site"],
            "wfo":            ["Work from office", "On-site"],
        }
        for key, labels in mode_label_map.items():
            if key in work_mode:
                for label in labels:
                    try:
                        # Try by visible label text in filter sidebar
                        cb = page.locator(
                            f"label:has-text('{label}') input[type='checkbox']:not(:checked), "
                            f"span.filterLabel:has-text('{label}')"
                        ).first
                        if cb.is_visible(timeout=1500):
                            cb.click()
                            micro_pause()
                            print(f"  [NAUKRI] Filter: Work mode = {label}")
                            break
                    except Exception:
                        pass
                break

    # ── Freshness filter ─────────────────────────────────────────
    freshness = task_input.get("freshness_days")
    if freshness:
        freshness = int(freshness)
        freshness_label_map = {1: "1 day ago", 3: "3 days ago", 7: "1 week ago", 15: "2 weeks ago", 30: "1 month ago"}
        label = freshness_label_map.get(freshness, f"{freshness} days")
        try:
            # Strategy 1: dedicated freshness filter button
            for btn_sel in [
                "button#filter-freshness",
                "span.filter-label:has-text('Date Posted')",
                "div.filter-title:has-text('Date Posted')",
            ]:
                try:
                    btn = page.locator(btn_sel).first
                    if btn.is_visible(timeout=1500):
                        btn.click()
                        micro_pause()
                        break
                except Exception:
                    pass
            # Strategy 2: click the freshness option
            for link_sel in [
                f"a[data-id='filter-freshness-{freshness}']",
                f"label:has-text('{label}')",
                f"span:has-text('{freshness} Day')",
            ]:
                try:
                    el = page.locator(link_sel).first
                    if el.is_visible(timeout=1500):
                        el.click()
                        human_sleep(1.5, 3.0)
                        print(f"  [NAUKRI] Filter: Freshness = last {freshness} days")
                        break
                except Exception:
                    pass
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────
# Chatbot radio / input helpers
# ──────────────────────────────────────────────────────────────
def _click_radio_by_value(page: Page, value: str) -> bool:
    """Click a visible radio input whose value matches (case-insensitive)."""
    try:
        r = page.locator(f"input[type='radio'][value='{value}']:visible").first
        if r.is_visible(timeout=1000):
            r.click()
            return True
    except Exception:
        pass
    try:
        for r in page.locator("input[type='radio']:visible").all():
            if (r.get_attribute("value") or "").lower() == value.lower():
                r.click()
                return True
    except Exception:
        pass
    try:
        lbl = page.locator(f"label.ssrc__label:visible:has-text('{value}')").first
        if lbl.is_visible(timeout=1000):
            lbl.click()
            return True
    except Exception:
        pass
    return False


def _click_radio_for_notice(page: Page, notice_days: int):
    """Select the appropriate notice period radio option."""
    if notice_days <= 15:
        label = "15 Days or less"
    elif notice_days <= 30:
        label = "1 Month"
    elif notice_days <= 60:
        label = "2 Months"
    elif notice_days <= 90:
        label = "3 Months"
    else:
        label = "More than 3 Months"

    if _click_radio_by_value(page, label):
        return

    # Fallback: partial label text match
    try:
        short = label.split()[0]
        for lbl in page.locator("label.ssrc__label:visible").all():
            txt = lbl.inner_text() or ""
            if txt.startswith(short):
                lbl.click()
                return
    except Exception:
        pass


def _click_skip(page: Page) -> bool:
    """Click 'Skip this question' radio or element."""
    if _click_radio_by_value(page, "Skip"):
        return True
    for sel in [
        "input[type='radio'][id='Skip this question']:visible",
        "label.ssrc__label:has-text('Skip this question'):visible",
        "button:has-text('Skip this question'):visible",
        "a:has-text('Skip this question'):visible",
        "span:has-text('Skip this question'):visible",
    ]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1000):
                el.click()
                return True
        except Exception:
            pass
    return False


def _try_chatbot_proceed(page: Page) -> bool:
    """Click the chatbot proceed / next button after answering a question."""
    for sel in [
        "button:has-text('Proceed')",
        "button:has-text('Next')",
        "button:has-text('Continue')",
        "button:has-text('Got it')",
        "button:has-text('OK')",
        "[class*='proceed']:visible button",
        "[class*='chatbot'] button[type='submit']:visible",
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                human_click(page, locator=btn)
                return True
        except Exception:
            pass
    return False


def _check_applied_success(page: Page) -> bool:
    """Return True if the page text indicates a successful submission."""
    try:
        body = page.locator("body").inner_text().lower()
        for phrase in [
            "application has been sent",
            "successfully applied",
            "application submitted",
            "applied successfully",
            "your application has been",
            "thank you for applying",
            "job has been applied",
        ]:
            if phrase in body:
                return True
    except Exception:
        pass
    return False


# ──────────────────────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────────────────────
def _click_if_visible(page: Page, selector: str, timeout: int = 2000) -> bool:
    try:
        btn = page.locator(selector).first
        if btn.is_visible(timeout=timeout):
            human_click(page, locator=btn, timeout=timeout)
            return True
    except Exception:
        pass
    return False


def _record_application(task_input: dict, job_url: str, company_hint: str = "") -> None:
    """Persist a successful Naukri application to Supabase (fire-and-forget, never raises)."""
    import sys
    user_id = task_input.get("user_id", "")
    if not user_id:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import record_application
        # Company: use hint first, then task_input, then extract from job URL slug
        company = (
            company_hint
            or task_input.get("company", "")
            or _company_from_url(job_url)
            or "Unknown Company"
        )
        role          = task_input.get("keywords", "Position")
        followup_days = int(task_input.get("followup_days", 3))
        ats_score     = task_input.get("_last_match_score")
        record_application(
            user_id=user_id,
            company=company,
            role=role,
            job_url=job_url,
            followup_days=followup_days,
            ats_score=int(ats_score) if ats_score is not None else None,
        )
    except Exception as e:
        print(f"  [NAUKRI] Could not record application: {e}")


def _company_from_url(job_url: str) -> str:
    """Best-effort company name extraction from a Naukri job-listings URL."""
    try:
        # Naukri URL pattern: /job-listings-<role>-<company>-<location>-<id>
        slug = job_url.rstrip("/").split("/")[-1].split("?")[0]
        # Remove trailing numeric ID and known keywords
        slug = re.sub(r"-\d+$", "", slug)
        parts = slug.split("-")
        # Heuristic: the middle section between role words and location is typically the company
        # Just return the first 3 capitalised-looking words as a best guess
        candidates = [p.capitalize() for p in parts if p and not p.isdigit() and len(p) > 2]
        return " ".join(candidates[:3]) if candidates else ""
    except Exception:
        return ""


def _dismiss_post_apply(page: Page):
    """Close any confirmation / success modal after applying."""
    for sel in [
        "button:has-text('Close')",
        "button:has-text('Done')",
        "button:has-text('OK')",
        "button[aria-label='Close']",
        "span.close-button",
        ".modal-close",
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                human_click(page, locator=btn)
                human_sleep(0.5, 1.5)
                return
        except Exception:
            pass
