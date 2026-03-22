"""
Naukri automation module.
Handles browser-based job search and application via Playwright.
Supports full-auto and semi-auto modes.
"""

import os
import re
import time
import tempfile
import urllib.parse
import requests as http_req
from playwright.sync_api import sync_playwright, Page


# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
NAUKRI_URL       = "https://www.naukri.com"
NAUKRI_LOGIN_URL = "https://www.naukri.com"   # login is a drawer on homepage now
NAV_WAIT         = 3
MAX_APPLY        = 5


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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page    = context.new_page()

        try:
            if not _login(page):
                return {"applied_count": 0, "skipped_count": 0, "message": "Login failed or cancelled"}

            jobs = _search_jobs(page, keywords, location, task_input)
            print(f"  [NAUKRI] Found {len(jobs)} job links")

            applied = 0
            skipped = 0
            for job_url in jobs[:max_apply]:
                success = _apply_to_job(page, job_url, task_input)
                if success:
                    applied += 1
                    print(f"  [NAUKRI] ✅ Applied ({applied}/{max_apply})")
                else:
                    skipped += 1
                    print("  [NAUKRI] ⏭  Skipped")

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


# ──────────────────────────────────────────────────────────────
# Login
# ──────────────────────────────────────────────────────────────
def _login(page: Page) -> bool:
    email    = os.environ.get("NAUKRI_EMAIL", "")
    password = os.environ.get("NAUKRI_PASSWORD", "")

    print("  [NAUKRI] Opening homepage...")
    page.goto(NAUKRI_URL, wait_until="domcontentloaded")
    time.sleep(NAV_WAIT)

    # If already logged in (avatar / profile icon visible), skip login
    if page.locator(".nI-gNb-menuItems .view-profile-wrapper, [class*='nI-gNb-desktop__avatar']").count() > 0:
        print("  [NAUKRI] Already logged in ✅")
        return True

    # Click the Login link in the header
    try:
        page.click("a#login_Layer, a.nI-gNb-lg-rg__login", timeout=5000)
        time.sleep(1.5)
    except Exception:
        print("  [NAUKRI] Could not find Login button — trying direct login URL...")
        page.goto("https://login.naukri.com/nLogin/Login.php", wait_until="domcontentloaded")
        time.sleep(NAV_WAIT)

    if email and password:
        # Auto-fill the drawer form
        try:
            page.fill("input[placeholder*='Email ID']", email, timeout=5000)
            page.fill("input[type='password']", password, timeout=5000)
            print("  [NAUKRI] Credentials filled — clicking Login...")
            page.click("button.loginButton", timeout=5000)
            time.sleep(3)
        except Exception as e:
            print(f"  [NAUKRI] Auto-fill failed ({e}), waiting for manual login...")

    # Whether auto-fill was used or not, wait for the user to be logged in
    print("  [NAUKRI] ============================================")
    print("  [NAUKRI]  Waiting for login to complete...          ")
    print("  [NAUKRI]  (You have 3 minutes if manual login)      ")
    print("  [NAUKRI] ============================================")

    try:
        # Wait until the drawer is gone AND a post-login URL/element appears
        page.wait_for_function(
            """() => {
                // drawer closed
                const drawer = document.querySelector('.drawer-wrapper');
                if (drawer && drawer.offsetParent !== null) return false;
                // still on login sub-page
                if (window.location.href.includes('login.naukri.com')) return false;
                if (window.location.href.includes('/nlogin/')) return false;
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

    slug   = re.sub(r"[^a-z0-9]+", "-", keywords.strip().lower()).strip("-")
    params: dict = {"k": keywords, "nignbevent_src": "jobsearchDesk"}
    if location:
        params["l"] = location

    search_url = f"{NAUKRI_URL}/{slug}-jobs?{urllib.parse.urlencode(params)}"
    print(f"  [NAUKRI] URL: {search_url}")
    page.goto(search_url, wait_until="domcontentloaded")
    time.sleep(NAV_WAIT + 2)

    # Apply sidebar filters from user preferences
    _apply_filters(page, task_input or {})

    job_links: list[str] = []

    def _collect(selector: str):
        try:
            for el in page.locator(selector).all():
                href = el.get_attribute("href") or ""
                if "naukri.com" in href and "/job-listings/" in href:
                    if href not in job_links:
                        job_links.append(href)
        except Exception:
            pass

    # Multiple selector strategies Naukri has used across redesigns
    _collect("article.jobTuple a.title")
    _collect("a.title[href*='/job-listings/']")
    _collect(".srp-jobtuple-wrapper a[href*='/job-listings/']")
    _collect("a[href*='/job-listings/']")          # broad fallback

    print(f"  [NAUKRI] Found {len(job_links)} job links")
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
    semi_auto  = task_input.get("semi_auto", False)

    print(f"  [NAUKRI] Opening: {job_url}")
    page.goto(job_url, wait_until="domcontentloaded")
    time.sleep(NAV_WAIT)

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

        # ── Skip if "Apply on company site" ──────────────────────
        # These jobs require applying on the employer's own website.
        # We save the job on Naukri and skip the application.
        try:
            company_btn = page.locator(
                "button#company-site-button, button.company-site-button"
            ).first
            if company_btn.is_visible(timeout=3000):
                print("  [NAUKRI] 'Apply on company site' — saving job and skipping")
                try:
                    page.locator(
                        "button.styles_save-job-button__WLm_s, button:has-text('Save')"
                    ).first.click(timeout=2000)
                    time.sleep(1)
                except Exception:
                    pass
                return False
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

        url_before = page.url
        apply_btn.click()
        time.sleep(3)

        # Bail if redirected externally
        if "naukri.com" not in page.url:
            print(f"  [NAUKRI] External redirect ({page.url[:60]}) — skipping")
            page.goto(url_before)
            return False

        # ── Semi-auto mode: let user complete the form ────────────
        if semi_auto:
            print(
                "  [NAUKRI] [SEMI-AUTO] ⏸  Please review the pre-filled form "
                "and click Submit/Apply in the browser."
            )
            try:
                page.wait_for_selector(
                    ".success-message, .confirmation-message, "
                    "div:has-text('application has been sent'), "
                    "div:has-text('successfully applied'), "
                    "div:has-text('Application submitted'), "
                    "p:has-text('Your application has been sent')",
                    timeout=300_000,
                )
                print("  [NAUKRI] [SEMI-AUTO] Application detected!")
                _dismiss_post_apply(page)
                return True
            except Exception:
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
                    inp.fill(str(int(years)))
                    print(f"  [NAUKRI] Filled experience = {years}")
                elif any(w in combined for w in ("notice", "noticeperiod")):
                    inp.fill(str(int(notice)))
                    print(f"  [NAUKRI] Filled notice = {notice}")
                elif any(w in combined for w in ("salary", "ctc", "expected", "lpa", "currentctc", "expectedctc")):
                    if salary:
                        inp.fill(salary)
                        print(f"  [NAUKRI] Filled salary = {salary}")
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
                ta.fill(cover_note)
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
    """Download resume from Supabase and set it on the file input if present."""
    resume_url = (task_input or {}).get("resume_url", "").strip()
    if not resume_url:
        return

    try:
        file_input = page.locator("input[type='file']").first
        if file_input.count() == 0:
            return
        if not file_input.is_visible(timeout=1500):
            return
    except Exception:
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
        time.sleep(2)
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
        time.sleep(1)

        # Submit button
        try:
            if page.locator(_SUBMIT_SEL).first.is_visible(timeout=2000):
                if _click_if_visible(page, _SUBMIT_SEL, timeout=2500):
                    time.sleep(3)
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

    # ── Text input question (CTC / salary) ───────────────────────
    if has_text_input:
        val = None
        if "current ctc" in pl or ("current" in pl and "lacs" in pl and "salary" not in pl):
            val = str(task_input.get("current_ctc") or "")
        elif "expected ctc" in pl or ("expected" in pl and "lacs" in pl):
            val = str(
                task_input.get("expected_ctc")
                or task_input.get("salary_expectation")
                or ""
            )

        if val:
            try:
                chatbot_inp.fill(val)
                print(f"  [NAUKRI] CTC filled → {val}")
                time.sleep(0.5)
                _try_chatbot_proceed(page)
                return True
            except Exception:
                pass

        # No value — skip the question
        if _click_skip(page):
            print("  [NAUKRI] CTC → Skipped")
            time.sleep(0.5)
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

        time.sleep(1)
        _try_chatbot_proceed(page)
        return True

    return False


# ──────────────────────────────────────────────────────────────
# Sidebar filter application
# ──────────────────────────────────────────────────────────────
def _apply_filters(page: Page, task_input: dict):
    """
    Apply Naukri sidebar filters based on user job preferences.

    Supported task_input keys:
      work_mode      str  "remote" | "hybrid" | "office" / "wfo"
      freshness_days int  1 | 3 | 7 | 15 | 30
    """
    if not task_input:
        return

    # ── Work mode filter ─────────────────────────────────────────
    work_mode = str(task_input.get("work_mode") or "").lower()
    if work_mode:
        mode_map = {
            "remote":         "Remote",
            "work from home": "Remote",
            "hybrid":         "Hybrid",
            "office":         "Work from office",
            "wfo":            "Work from office",
        }
        for key, label in mode_map.items():
            if key in work_mode:
                try:
                    cb = page.locator(f"input[id='chk-{label}-wfhType-']")
                    if cb.count() > 0 and not cb.first.is_checked():
                        cb.first.click()
                        time.sleep(1.5)
                        print(f"  [NAUKRI] Filter: Work mode = {label}")
                except Exception:
                    pass
                break

    # ── Freshness filter ─────────────────────────────────────────
    freshness = task_input.get("freshness_days")
    if freshness:
        try:
            page.click("button#filter-freshness", timeout=3000)
            time.sleep(0.5)
            page.click(f"a[data-id='filter-freshness-{freshness}']", timeout=3000)
            time.sleep(2)
            print(f"  [NAUKRI] Filter: Freshness = last {freshness} days")
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
                btn.click()
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
            btn.click()
            return True
    except Exception:
        pass
    return False


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
                btn.click()
                time.sleep(1)
                return
        except Exception:
            pass
