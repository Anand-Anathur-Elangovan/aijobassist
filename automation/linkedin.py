"""
LinkedIn automation module.
Handles browser-based job search and application via Playwright.
"""

import os
import re
import sys
import time
import json
import base64
import random
import tempfile
import threading
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
    """Navigate to url with exponential backoff. Returns True on success.

    Playwright throws ERR_HTTP_RESPONSE_CODE_FAILURE and ERR_TOO_MANY_REDIRECTS
    on LinkedIn's redirect chains even when the final page loaded fine.
    After any error we check page.url — if the browser landed on a real page
    (not about:blank) we treat it as success.
    Detects HTTP 429 (rate-limit) and backs off 60 s before retrying.
    """
    for attempt in range(max_retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            # Check for 429 even on a "successful" navigation (LinkedIn serves it as 200 HTML)
            try:
                if page.locator("text=HTTP ERROR 429").is_visible(timeout=1000):
                    raise Exception("HTTP 429 rate-limit page")
            except Exception as _chk:
                if "429" in str(_chk):
                    raise
            return True
        except Exception as e:
            # If rate-limited, wait 60 s before retrying
            if "429" in str(e):
                wait = 60
                print(f"  [LINKEDIN] Rate-limited (429) — waiting {wait}s before retry {attempt+1}/{max_retries}")
                time.sleep(wait)
                continue
            # Check if the page actually loaded despite the Playwright navigation error
            try:
                landed = page.url or ""
                if landed and "about:blank" not in landed and not landed.startswith("data:"):
                    # Still check for 429 content on the landed page
                    try:
                        if page.locator("text=HTTP ERROR 429").is_visible(timeout=500):
                            wait = 60
                            print(f"  [LINKEDIN] Rate-limited (429) on landed page — waiting {wait}s")
                            time.sleep(wait)
                            continue
                    except Exception:
                        pass
                    return True
            except Exception:
                pass
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


def _push_screenshot(task_input: dict, page) -> None:
    """Push a live screenshot to railway_sessions (cloud mode only, best-effort)."""
    session_id = task_input.get("session_id", "")
    if not session_id:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
        from api_client import push_screenshot
        push_screenshot(session_id, page)
    except Exception:
        pass


# ── Telegram real-time reply helpers ──────────────────────────────────────────

def _get_telegram_update_offset(bot_token: str, chat_id: str) -> int:
    """Return the update_id of the most recent Telegram update (so we only see NEW replies)."""
    if not bot_token:
        return 0
    try:
        resp = http_req.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates",
            params={"limit": 1, "offset": -1},
            timeout=8,
        )
        updates = resp.json().get("result", [])
        return updates[-1]["update_id"] if updates else 0
    except Exception:
        return 0


def _poll_telegram_for_reply(bot_token: str, chat_id: str,
                              last_update_id: int) -> tuple:
    """
    Non-blocking poll for new Telegram messages from chat_id after last_update_id.
    Returns (reply_text_lower_or_None, new_last_update_id).
    """
    if not bot_token or not chat_id:
        return None, last_update_id
    try:
        resp = http_req.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 0, "limit": 10},
            timeout=8,
        )
        data = resp.json()
        if not data.get("ok"):
            return None, last_update_id
        new_last = last_update_id
        for update in data.get("result", []):
            upd_id = update.get("update_id", last_update_id)
            new_last = max(new_last, upd_id)
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id", "")) == str(chat_id):
                text = (msg.get("text") or "").strip().lower()
                if text:
                    return text, new_last
        return None, new_last
    except Exception:
        return None, last_update_id


def _wait_for_resolution(page: Page, task_input: dict, tg_message: str,
                          wait_minutes: int = 10,
                          check_url_exit: bool = False) -> str:
    """
    Send a Telegram notification, then poll every 5 s waiting for one of:
      • User replies  "skip" / "s" / "next"       → returns "skip"
      • User replies  "stop" / "quit"              → returns "stop"
      • User replies  "ok" / "done" / "resume"     → returns "resolved"
      • URL leaves login/checkpoint (check_url_exit=True) → returns "resolved"
      • wait_minutes elapsed with no response      → returns "timeout"

    The caller is responsible for building `tg_message` (already contains
    the VNC URL or screen instruction).  This function only adds the reply
    instructions footer if they are not already present.
    """
    from automation.notifier import _tg_send, _cfg
    bot_token = _cfg(task_input, "telegram_bot_token", "TELEGRAM_BOT_TOKEN")
    chat_id   = _cfg(task_input, "telegram_chat_id",   "TELEGRAM_CHAT_ID")

    # Append reply-hint if not already there
    _footer = "\n\nReply <b>done</b> when finished · <b>skip</b> to skip this job · <b>stop</b> to stop all"
    full_msg = tg_message if "<b>done</b>" in tg_message or "<b>skip</b>" in tg_message else tg_message + _footer

    if bot_token and chat_id:
        try:
            _tg_send(bot_token, chat_id, full_msg)
        except Exception as _te:
            print(f"  [LINKEDIN] Telegram send failed: {_te}")

    _push_screenshot(task_input, page)

    # Snapshot update offset AFTER sending so only NEW replies are seen
    last_upd = _get_telegram_update_offset(bot_token, chat_id)

    deadline = time.time() + wait_minutes * 60
    _iter = 0
    while time.time() < deadline:
        # First 3 iterations: poll every 2 s (fast initial detection)
        # Subsequent iterations: poll every 5 s (normal cadence)
        time.sleep(2 if _iter < 3 else 5)
        _iter += 1

        # ── Telegram reply check ─────────────────────────────────
        if bot_token and chat_id:
            try:
                reply, last_upd = _poll_telegram_for_reply(bot_token, chat_id, last_upd)
                if reply:
                    if reply in ("skip", "s", "next", "n"):
                        _log(task_input, "⏭ User replied 'skip' via Telegram", "skip", "stuck")
                        try: _tg_send(bot_token, chat_id, "⏭ Skipping this job and continuing with the rest…")
                        except Exception: pass
                        return "skip"
                    elif reply in ("stop", "quit", "q"):
                        _log(task_input, "🛑 User replied 'stop' via Telegram", "error", "stuck")
                        try: _tg_send(bot_token, chat_id, "🛑 Stopping the session as requested.")
                        except Exception: pass
                        return "stop"
                    elif reply in ("ok", "done", "continue", "c", "resume", "r", "yes", "y", "d"):
                        _log(task_input, "▶️ User replied 'done' — resuming", "success", "stuck")
                        try: _tg_send(bot_token, chat_id, "▶️ Got it — resuming now!")
                        except Exception: pass
                        return "resolved"
            except Exception:
                pass

        # ── URL-exit check (login / checkpoint pages only) ────────
        if check_url_exit:
            try:
                url = page.url or ""
                _still_blocked = any(kw in url for kw in (
                    "/checkpoint/", "/challenge/", "/uas/login", "linkedin.com/login",
                ))
                if not _still_blocked and url and "about:blank" not in url:
                    _log(task_input, f"✅ Verification resolved — URL: {url[:80]}", "success", "stuck")
                    try:
                        _tg_send(bot_token, chat_id, "✅ Verification complete! Resuming job applications…")
                    except Exception:
                        pass
                    return "resolved"
            except Exception:
                continue

    # Timeout
    _log(task_input, f"⏰ Wait timed out after {wait_minutes} min", "error", "stuck")
    try:
        _tg_send(bot_token, chat_id,
                 f"⏰ No response for {wait_minutes} min — skipping this job and continuing.")
    except Exception:
        pass
    return "timeout"


def _handle_verification(page: Page, task_input: dict) -> bool:
    """
    Called when LinkedIn shows a security challenge (OTP, push-notification, CAPTCHA).
    Builds an appropriate Telegram message (with noVNC URL on Railway, or screen
    instruction locally) then delegates to _wait_for_resolution.
    Returns True if resolved (URL left the challenge page), False otherwise.
    """
    _is_railway = os.environ.get("TASK_RUNNER_ENV") == "railway"
    app_url = (
        os.environ.get("RAILWAY_STATIC_URL", "")
        or os.environ.get("NEXT_PUBLIC_APP_URL", "")
    ).rstrip("/")

    current_url = ""
    try:
        current_url = page.url or ""
    except Exception:
        pass

    _hint = "identity verification (check LinkedIn mobile app for a push notification, or look for an OTP)"
    if "otp" in current_url or "pin" in current_url or "phone" in current_url:
        _hint = "OTP / PIN code (check your phone or email)"
    elif "captcha" in current_url or "puzzle" in current_url:
        _hint = "CAPTCHA / image puzzle"

    if _is_railway and app_url:
        _sid = (task_input or {}).get("session_id", "")
        _vnc_path = f"../vnc-ws%3Fsession%3D{_sid}" if _sid else "../vnc-ws"
        _vnc = f"{app_url}/novnc/?path={_vnc_path}&autoconnect=1&resize=scale"
        tg_msg = (
            f"🔐 <b>LinkedIn Verification Required</b>\n\n"
            f"<b>Type:</b> {_hint}\n\n"
            f"👉 <b>Open the live browser:</b>\n<a href=\"{_vnc}\">{_vnc}</a>\n\n"
            f"Complete the check — I'll detect it and resume automatically.\n"
            f"Or reply <b>skip</b> to skip · <b>stop</b> to stop all.\n"
            f"⏳ Waiting up to <b>10 minutes</b>."
        )
        print(f"  [LINKEDIN] ⚠️  Verification required (cloud) — noVNC link sent via Telegram.")
    else:
        tg_msg = (
            f"🔐 <b>LinkedIn Verification Required</b>\n\n"
            f"<b>Type:</b> {_hint}\n\n"
            f"👉 Complete it in the <b>browser window on your screen</b>.\n\n"
            f"• OTP / PIN → check email or phone\n"
            f"• Push notification → tap <i>Approve</i> on LinkedIn mobile app\n"
            f"• CAPTCHA → solve the puzzle\n\n"
            f"Or reply <b>skip</b> to skip · <b>stop</b> to stop all.\n"
            f"⏳ Waiting up to <b>10 minutes</b> — auto-resumes when done."
        )
        print(f"  [LINKEDIN] ⚠️  Verification required — Telegram notification sent. Complete in browser.")

    _log(task_input,
         f"🔐 Verification required ({_hint}) — URL: {current_url[:80]}",
         "warning", "verification",
         {"url": current_url, "vnc_available": bool(_is_railway and app_url)})

    result = _wait_for_resolution(page, task_input, tg_msg,
                                  wait_minutes=10, check_url_exit=True)
    return result == "resolved"


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


def _is_session_expired(page: Page) -> bool:
    """
    Return True if LinkedIn has redirected us to a login / challenge page,
    indicating the session cookie has expired mid-run.
    """
    try:
        url = page.url or ""
        if any(kw in url for kw in ("/login", "/checkpoint", "/authwall", "/uas/login")):
            return True
        # Also check for login form visibility without a URL change
        if page.locator("input#username, input[name='session_key']").first.is_visible(timeout=1000):
            return True
    except Exception:
        pass
    return False


def _attach_crash_handler(page: Page) -> list:
    """
    Attach a page crash handler.
    Returns a single-element list [False]; the element is flipped to True on crash.
    Callers should check crashed[0] and raise if set.
    """
    crashed = [False]

    def _on_crash():
        crashed[0] = True
        print("  [LINKEDIN] ⚠️  Chromium page crashed!")

    page.on("crash", _on_crash)
    return crashed


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

    _session_start = time.time()   # for duration calculation in summary notification
    task_input.setdefault("_session_stats", {"applied": 0, "manual_needed": 0, "skipped": 0,
                                              "errors": 0, "manual_jobs": []})

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
            # Store skills so title filter can use them later
            task_input["_resume_skills"] = top_skills
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
    # Always run headed:
    #   - Local:   real display on your machine
    #   - Railway: Xvfb virtual display (:99) started by server.py on boot
    # This allows the user to see and interact with any verification challenge
    # via the noVNC live-view at /vnc/ (Railway) or directly on screen (local).
    _headless  = False
    _user_id   = task_input.get("user_id", "anonymous")

    # ── Persistent profile directory ──────────────────────────────────────────
    # Each user gets their own Chromium profile stored on disk.
    # LinkedIn sees the SAME browser fingerprint on every run → session is never
    # invalidated due to fingerprint mismatch.
    # Local:   SESSION_DIR=./sessions  (default)
    # Railway: SESSION_DIR=/sessions   (mounted volume — set in Railway env vars)
    _session_base    = os.environ.get("SESSION_DIR", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "sessions"))
    _user_data_dir   = os.path.join(_session_base, _user_id)
    os.makedirs(_user_data_dir, exist_ok=True)
    print(f"  [LINKEDIN] Profile dir: {_user_data_dir}")

    with sync_playwright() as p:
        # launch_persistent_context = browser + context in a single call.
        # The profile directory persists cookies, localStorage, and cache
        # across every run so the session survives restarts and redeploys.
        # Fingerprint is deterministic per user_id so LinkedIn always sees
        # the same browser.
        # Use the per-session virtual display allocated by display_pool (Railway only).
        # Falls back to the env DISPLAY (or :99 default) on local / if pool was exhausted.
        _session_display = task_input.get("session_display") or os.environ.get("DISPLAY", ":99")
        _launch_env = {**os.environ, "DISPLAY": _session_display}
        context = p.chromium.launch_persistent_context(
            _user_data_dir,
            headless=_headless,
            args=stealth_launch_args(),
            env=_launch_env,
            **stealth_context_options(_user_id),
        )
        # ── Block heavy non-essential resources to prevent OOM (Error code 9) ──
        # Aborts image / font / media requests. These are decorative and not
        # needed for form-filling. JS, CSS, XHR, fetch continue normally so
        # LinkedIn's SPA and Easy Apply modal render correctly.
        # Applied to the context so it covers all pages (search + apply + recycled).
        _OOM_BLOCK_TYPES = {"image", "font", "media"}

        def _abort_heavy(route):
            try:
                if route.request.resource_type in _OOM_BLOCK_TYPES:
                    route.abort()
                else:
                    route.continue_()
            except Exception:
                # CRITICAL: always resolve the route even on exception.
                # An unhandled route leaves the browser request permanently
                # pending — causing the page to spin forever (infinite load).
                # Abort as fallback so the request resolves immediately.
                try:
                    route.abort()
                except Exception:
                    pass
        context.route("**/*", _abort_heavy)

        page    = context.new_page()
        inject_stealth(page)
        _crashed = _attach_crash_handler(page)
        print("  [LINKEDIN] Browser launched ✅ (images/fonts/media blocked to prevent OOM)")

        try:
            # ── STEP 1: Login ──────────────────────────────────
            _log(task_input, "Opening LinkedIn login page…")
            result = _login(page, task_input)
            if not result:
                _log(task_input, "Login failed or cancelled", "error")
                return {"applied_count": 0, "skipped_count": 0, "message": "Login failed or cancelled"}

            # Screenshot after login so user sees the starting state
            _push_screenshot(task_input, page)

            # ── Recycle page after login before search ─────────────────────────
            # The login / session-check phase loads /feed/ which fills the renderer
            # with LinkedIn's full SPA.  Navigating the same renderer to
            # /jobs/search/ on top of that heap causes the page 1 OOM crash.
            # Close the page now to flush all feed DOM; the new page starts fresh.
            try:
                page.close()
            except Exception:
                pass
            page = context.new_page()
            inject_stealth(page)
            _crashed = _attach_crash_handler(page)
            try:
                page.goto("about:blank", wait_until="commit", timeout=10_000)
            except Exception:
                pass
            print("  [LINKEDIN] 🔄 Feed page recycled — fresh renderer ready for job search")
            _log(task_input, "🔄 Feed page recycled — fresh renderer ready for job search", "info", "system")

            # ── Notify user that cloud run has started (with VNC link) ──
            try:
                from automation.notifier import _tg_send, _cfg
                _tg_token = _cfg(task_input, "telegram_bot_token", "TELEGRAM_BOT_TOKEN")
                _tg_chat  = _cfg(task_input, "telegram_chat_id",   "TELEGRAM_CHAT_ID")
                _app_url  = (
                    os.environ.get("RAILWAY_STATIC_URL", "")
                    or os.environ.get("NEXT_PUBLIC_APP_URL", "")
                ).rstrip("/")
                if _tg_token and _tg_chat:
                    _sid_param = task_input.get("session_id", "")
                    _vnc_path = f"../vnc-ws%3Fsession%3D{_sid_param}" if _sid_param else "../vnc-ws"
                    _vnc_start = f"{_app_url}/novnc/?path={_vnc_path}&autoconnect=1&resize=scale" if _app_url else ""
                    _start_msg = (
                        f"🚀 <b>Cloud run started on Railway</b>\n\n"
                        f"Logged in to LinkedIn ✅\n"
                        f"Searching for: <b>{task_input.get('keywords', 'Software Engineer')}</b>\n"
                    )
                    if _vnc_start:
                        _start_msg += f"\n👁 <b>Watch live:</b>\n<a href=\"{_vnc_start}\">{_vnc_start}</a>\n"
                    _tg_send(_tg_token, _tg_chat, _start_msg)
            except Exception as _sne:
                print(f"  [LINKEDIN] Start notification error (non-fatal): {_sne}")

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
                        for url in general_jobs:
                            all_jobs.append((url, ""))

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

            # ── Recycle page before apply loop ────────────────────────────────
            # The search phase builds up a large JS heap (job cards, React SPA
            # state, event listeners). If we reuse that page for the apply loop
            # the renderer is already near the OOM limit before we open the first
            # job page — causing the Easy Apply modal crash (Error code 9).
            # Fix: close the search page, open a fresh renderer, navigate to
            # about:blank to confirm the new page works, then proceed.
            # context.route(_abort_images) already covers the new page — no need
            # to re-register it.
            if not _li_specific_urls_mode:
                try:
                    page.close()
                except Exception:
                    pass
                page = context.new_page()
                inject_stealth(page)
                _crashed = _attach_crash_handler(page)
                try:
                    page.goto("about:blank", wait_until="commit", timeout=10_000)
                except Exception:
                    pass
                print("  [LINKEDIN] 🔄 Search page recycled — fresh renderer ready for apply loop")
                _log(task_input, "🔄 Search page recycled — fresh renderer ready for apply loop", "info", "system")

            # ── STEP 3: Apply ──────────────────────────────────
            applied  = 0
            skipped  = 0
            total    = len(unique_jobs)
            _exhausted_pool = False   # flag: pool ran out before hitting max_apply
            _report: list[dict] = []  # per-job completion report
            for idx, (job_url, company_hint) in enumerate(unique_jobs):
                if applied >= max_apply:
                    break

                # ── Feature: Browser crash guard ──────────────────
                if _crashed[0]:
                    _log(task_input,
                         "⚠️ Chromium OOM crash (Error code 9) detected — renderer ran out of memory. "
                         "Attempting page recovery and resuming from next job.",
                         "warning", "system", {"url": job_url})
                    print("  [LINKEDIN] ⚠️  Crash detected (OOM/Error code 9) — attempting page recovery…")
                    try:
                        # Close the crashed page FIRST to release renderer memory
                        try:
                            page.close()
                        except Exception:
                            pass
                        page = context.new_page()
                        inject_stealth(page)
                        _crashed = _attach_crash_handler(page)
                        # Re-seed session on new page — without this, LinkedIn redirects
                        # every subsequent /jobs/search/ back to /feed/ (bot detection)
                        try:
                            page.goto("https://www.linkedin.com/feed/",
                                      wait_until="domcontentloaded", timeout=30_000)
                            human_sleep(3, 5)
                        except Exception:
                            pass
                        if _is_session_expired(page):
                            raise RuntimeError("Session expired after crash recovery")
                        print("  [LINKEDIN] ✅ New page created and session re-verified — resuming from next job")
                    except Exception as _ce:
                        raise RuntimeError(f"Chromium crashed and page recovery failed: {_ce}")

                # ── Feature: Session expiry detection + re-auth ───
                if _is_session_expired(page):
                    _log(task_input, "⚠️ Session expired — attempting re-login…", "warning", "system")
                    _reauth_ok = _login(page, task_input)
                    if not _reauth_ok:
                        _log(task_input,
                             "❌ Re-authentication failed — session cookie expired. "
                             "Please log in again and restart the task.",
                             "error", "system")
                        raise RuntimeError(
                            "LinkedIn session expired mid-run and re-login failed. "
                            "Please update your credentials and retry."
                        )
                    _log(task_input, "✅ Re-authenticated successfully", "success", "system")

                # ── Feature: Duplicate application guard ──────────
                _li_user_id_check = task_input.get("user_id", "")
                if _li_user_id_check:
                    try:
                        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
                        from api_client import check_already_applied as _check_dup
                        if _check_dup(_li_user_id_check, job_url):
                            _log(task_input, f"⏭ Already applied — skipping {job_url}", "skip", "skip",
                                 {"url": job_url, "skip_reason": "duplicate"})
                            skipped += 1
                            _report.append({"company": company_hint or "—", "job_title": "—",
                                             "url": job_url, "score": None,
                                             "status": "skipped", "skip_reason": "duplicate"})
                            continue
                    except Exception as _de:
                        print(f"  [LINKEDIN] Duplicate check error (non-fatal): {_de}")

                # ── Check pause / stop / live custom prompt ────
                ctrl = _check_control(task_input)
                if ctrl.get("stop_requested"):
                    _log(task_input, "Stop requested by user — halting run", "warning", "system")
                    break
                # Allow user to update the custom prompt mid-run
                live_prompt = ctrl.get("custom_prompt_override")
                if live_prompt:
                    task_input["tailor_custom_prompt"] = live_prompt

                # Inject current company for tailoring context
                if company_hint:
                    task_input["company"] = company_hint
                else:
                    task_input.pop("company", None)  # clear stale discovered company from previous job
                # Clear per-job extracted fields so stale values from previous job don't bleed into report
                task_input.pop("_page_job_title", None)
                task_input.pop("_page_company", None)

                # Progress: 5 % base + up to 90 % for applications
                progress = 5 + int((applied / max_apply) * 90) if max_apply else 5
                company_tag = f" [{company_hint}]" if company_hint else ""
                _set_progress(task_input, progress, job_url)
                _log(task_input, f"Opening job page", "info", "navigation", {"company": company_hint, "url": job_url})

                success = _apply_to_job(page, job_url, task_input)
                # Push screenshot after each application attempt (cloud mode)
                _push_screenshot(task_input, page)
                # Navigate to blank page to free renderer memory (prevents OOM crashes on Railway)
                try:
                    page.goto("about:blank", timeout=5000)
                except Exception:
                    pass
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
                    _r_company    = task_input.get("_page_company") or task_input.get("company") or company_hint or "—"
                    _r_job_title  = task_input.get("_page_job_title") or "—"
                    _r_apply_type = task_input.get("_last_apply_type", "easy_apply")
                    _log(task_input, f"✅ Applied — {_r_company} ({applied}/{max_apply})", "success", "submit", {"company": _r_company, "url": job_url, "job_title": _r_job_title})
                    _record_application(task_input, job_url, _r_company)
                    # Track easy vs external counts in session stats
                    _sstats = task_input.setdefault("_session_stats", {})
                    if _r_apply_type == "external":
                        _sstats["external_applied"] = _sstats.get("external_applied", 0) + 1
                    else:
                        _sstats["easy_applied"] = _sstats.get("easy_applied", 0) + 1
                    _report.append({
                        "company":          _r_company,
                        "job_title":        _r_job_title,
                        "url":              job_url,
                        "score":            task_input.get("_last_match_score"),
                        "status":           "applied",
                        "apply_type":       _r_apply_type,
                        "skip_reason":      "",
                        "tailored_resume_url": task_input.get("_tailored_resume_url", ""),
                        "resume_url":       task_input.get("resume_url", ""),
                        "resume_filename":  task_input.get("resume_filename", "resume.pdf"),
                    })
                else:
                    skipped += 1
                    _r_company   = task_input.get("_page_company") or task_input.get("company") or company_hint or "—"
                    _r_job_title = task_input.get("_page_job_title") or "—"
                    _log(task_input, f"⏭ Skipped — {_r_company} ({skipped} total)", "skip", "skip", {"company": _r_company, "url": job_url, "job_title": _r_job_title})
                    _report.append({
                        "company":          _r_company,
                        "job_title":        _r_job_title,
                        "url":              job_url,
                        "score":            task_input.get("_last_match_score"),
                        "status":           "skipped",
                        "apply_type":       task_input.get("_last_apply_type", ""),
                        "skip_reason":      task_input.get("_last_skip_reason", ""),
                        "resume_url":       task_input.get("resume_url", ""),
                        "resume_filename":  task_input.get("resume_filename", "resume.pdf"),
                    })
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
                        for url in extra_links:
                            extra_jobs.append((url, ""))
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
                            # Clear per-job fields so stale values don't bleed into report
                            task_input.pop("_page_job_title", None)
                            task_input.pop("_page_company", None)
                            task_input.pop("company", None)  # clear stale discovered company from previous job
                            success = _apply_to_job(page, ej_url, task_input)
                            # If user replied "stop" via Telegram during stuck handling
                            if task_input.get("_stop_requested"):
                                _log(task_input, "🛑 Session stopped by user via Telegram", "error", "system")
                                break
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
                                _er_company    = task_input.get("_page_company") or task_input.get("company") or ej_hint or "—"
                                _er_job_title  = task_input.get("_page_job_title") or "—"
                                _er_apply_type = task_input.get("_last_apply_type", "easy_apply")
                                _log(task_input, f"✅ Applied — {_er_company} ({applied}/{max_apply})", "success", "submit", {"company": _er_company, "url": ej_url, "job_title": _er_job_title})
                                _record_application(task_input, ej_url, _er_company)
                                _sstats2 = task_input.setdefault("_session_stats", {})
                                if _er_apply_type == "external":
                                    _sstats2["external_applied"] = _sstats2.get("external_applied", 0) + 1
                                else:
                                    _sstats2["easy_applied"] = _sstats2.get("easy_applied", 0) + 1
                                _report.append({
                                    "company":             _er_company,
                                    "job_title":           _er_job_title,
                                    "url":                 ej_url,
                                    "score":               task_input.get("_last_match_score"),
                                    "status":              "applied",
                                    "apply_type":          _er_apply_type,
                                    "skip_reason":         "",
                                    "tailored_resume_url": task_input.get("_tailored_resume_url", ""),
                                    "resume_url":          task_input.get("resume_url", ""),
                                    "resume_filename":     task_input.get("resume_filename", "resume.pdf"),
                                })
                            else:
                                skipped += 1
                                _er_company   = task_input.get("_page_company") or task_input.get("company") or ej_hint or "—"
                                _er_job_title = task_input.get("_page_job_title") or "—"
                                _log(task_input, f"⏭ Skipped — {_er_company} ({skipped} total)", "skip", "skip", {"url": ej_url, "job_title": _er_job_title})
                                _report.append({
                                    "company":         _er_company,
                                    "job_title":       _er_job_title,
                                    "url":             ej_url,
                                    "score":           task_input.get("_last_match_score"),
                                    "status":          "skipped",
                                    "apply_type":      task_input.get("_last_apply_type", ""),
                                    "skip_reason":     task_input.get("_last_skip_reason", ""),
                                    "resume_url":      task_input.get("resume_url", ""),
                                    "resume_filename": task_input.get("resume_filename", "resume.pdf"),
                                })

            _set_progress(task_input, 100)
            _log(task_input, f"Run complete — applied: {applied}, skipped: {skipped}", "success", "system", {"applied": applied, "skipped": skipped})

            # ── Send session summary notification ──────────────────────────
            try:
                from automation.notifier import notify_session_summary
                _duration = max(1, int((time.time() - _session_start) / 60))
                _sstats = task_input.get("_session_stats", {})
                notify_session_summary(task_input, {
                    "applied":            applied,
                    "easy_applied":       _sstats.get("easy_applied", -1),
                    "external_applied":   _sstats.get("external_applied", 0),
                    "manual_needed":      _sstats.get("manual_needed", 0),
                    "skipped":            skipped,
                    "errors":             _sstats.get("errors", 0),
                    "duration_minutes":   _duration,
                    "manual_jobs":        _sstats.get("manual_jobs", []),
                    "jobs":               _report,
                    "resume_url":         task_input.get("resume_url", ""),
                    "resume_filename":    task_input.get("resume_filename", "resume.pdf"),
                    "redirect_blocked":   task_input.get("_redirect_blocked", False),
                })
            except Exception as _sne:
                print(f"  [NOTIFY] Summary notification failed: {_sne}")

            return {
                "applied_count": applied,
                "skipped_count": skipped,
                "message": f"Applied to {applied} jobs on LinkedIn",
                "report": _report,
            }

        except Exception as e:
            print(f"  [LINKEDIN] ERROR: {e}")
            raise
        finally:
            context.close()  # closes both context and the underlying browser
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
    Open the LinkedIn login page and sign in.

    Tries cookie-based login first (li_at) — much more reliable in cloud/headless
    environments because it bypasses LinkedIn's bot-detection on the login form.
    Falls back to email+password if no cookie is provided.

    Design-agnostic: works regardless of LinkedIn UI redesigns.
    Uses 3-layer detection for each field:
      Layer 1 – Known stable attributes (fast)
      Layer 2 – Semantic label / autocomplete scan
      Layer 3 – JS DOM position analysis (future-proof)
    Always falls back to pressing Enter on the password field.
    """
    task_input = task_input or {}
    email    = task_input.get("linkedin_email", "").strip()
    password = task_input.get("linkedin_password", "").strip()
    li_at   = task_input.get("linkedin_cookie", "").strip()
    user_id = task_input.get("user_id", "").strip()

    # ── Strategy 0: Persistent profile already has a valid session ────────────
    # launch_persistent_context restores cookies + localStorage from the profile
    # directory automatically. Just navigate to feed and verify — if we land
    # there we're already logged in and no credentials are needed at all.
    #
    # Cold-start (new Railway container / empty profile): try restoring the
    # storage_state saved in Supabase Storage from a previous run first.
    print("  [LINKEDIN] Checking for existing session in profile…")
    _session_base    = os.environ.get("SESSION_DIR", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "sessions"))
    _user_data_dir   = os.path.join(_session_base, user_id) if user_id else ""
    _profile_has_data = any(True for _ in os.scandir(_user_data_dir)) if (_user_data_dir and os.path.isdir(_user_data_dir)) else False
    if not _profile_has_data and user_id:
        print("  [LINKEDIN] Profile empty — attempting cold-start restore from Supabase Storage…")
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
            from api_client import load_linkedin_session
            _saved_state = load_linkedin_session(user_id)
            if _saved_state and _saved_state.get("cookies"):
                try:
                    page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=60_000)
                except Exception:
                    pass
                try:
                    page.context.add_cookies([
                        {"name": c["name"], "value": c["value"],
                         "domain": c.get("domain", ".linkedin.com"), "path": c.get("path", "/")}
                        for c in _saved_state["cookies"]
                        if "linkedin.com" in c.get("domain", "")
                    ])
                    print(f"  [LINKEDIN] Restored {len(_saved_state['cookies'])} cookies from Supabase Storage")
                except Exception as _ce:
                    print(f"  [LINKEDIN] Cookie restore warning: {_ce}")
            else:
                print("  [LINKEDIN] No saved session found in Supabase Storage")
        except Exception as _re:
            print(f"  [LINKEDIN] Cold-start restore failed: {_re}")
    try:
        try:
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            pass
        human_sleep(2, 3)
        _url = page.url or ""
        _bad = (
            "/login" in _url or
            "linkedin.com/checkpoint" in _url or
            _url.rstrip("/") == "https://www.linkedin.com"
        )
        if not _bad:
            print(f"  [LINKEDIN] Existing session valid ✅  URL: {_url}")
            return True
        print(f"  [LINKEDIN] No valid session in profile (landed: {_url}) — proceeding with login")
    except Exception as e:
        print(f"  [LINKEDIN] Session check error: {e} — proceeding with login")

    def _save_session():
        """
        After a successful login:
        1. Save full storage_state to Supabase Storage (survives Railway redeploys).
        2. Save li_at + email/password to DB (fallback for profile rebuild).
        """
        if not user_id:
            return
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "taskrunner"))
            from api_client import save_linkedin_credentials, save_linkedin_session
            # Save storage_state to Supabase Storage
            try:
                state = page.context.storage_state()
                ok = save_linkedin_session(user_id, state)
                if ok:
                    print("  [LINKEDIN] Session saved to Supabase Storage ✅ (survives redeploys)")
                else:
                    print("  [LINKEDIN] Warning: session storage upload failed — check 'sessions' bucket exists in Supabase")
            except Exception as se:
                print(f"  [LINKEDIN] Warning: could not save session state: {se}")
            # Also save li_at to DB as a last-resort fallback
            live_li_at = None
            try:
                for cookie in page.context.cookies():
                    if cookie.get("name") == "li_at":
                        live_li_at = cookie.get("value")
                        break
            except Exception:
                pass
            save_linkedin_credentials(
                user_id,
                linkedin_cookie=live_li_at or li_at or None,
                linkedin_email=email or None,
                linkedin_password=password or None,
            )
        except Exception as e:
            print(f"  [LINKEDIN] Warning: could not save session: {e}")

    # ── Strategy 1: Cookie-based login — DISABLED ─────────────────────────────
    # LinkedIn revokes li_at when it detects a fingerprint change (new IP / browser).
    # Going straight to email+password is more reliable; if verification is needed
    # the bot will wait and notify via Telegram / noVNC.
    if False and li_at:
        print("  [LINKEDIN] Attempting cookie-based login (li_at)…")
        try:
            page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=60_000)

            # Restore the full saved cookie set if available (prevents 302 on /jobs/search/)
            all_saved_cookies = task_input.get("linkedin_cookies")
            if all_saved_cookies and isinstance(all_saved_cookies, list):
                try:
                    page.context.add_cookies(all_saved_cookies)
                    print(f"  [LINKEDIN] Restored {len(all_saved_cookies)} saved cookies")
                except Exception as _ce:
                    print(f"  [LINKEDIN] Warning: could not restore all cookies: {_ce}")
                    # Fall back to just li_at
                    page.context.add_cookies([{"name": "li_at", "value": li_at, "domain": ".linkedin.com", "path": "/"}])
            else:
                page.context.add_cookies([{"name": "li_at", "value": li_at, "domain": ".linkedin.com", "path": "/"}])

            # Navigate to feed — ignore 302 errors, just check the final URL
            try:
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60_000)
            except Exception:
                pass
            human_sleep(2, 3)
            url = page.url
            _bad = (
                "/login" in url or
                "linkedin.com/checkpoint" in url or
                # Public homepage = LinkedIn rejected the cookie and redirected us back
                url.rstrip("/") == "https://www.linkedin.com"
            )
            if not _bad:
                print(f"  [LINKEDIN] Cookie login confirmed ✅  URL: {url}")
                _save_session()
                return True
            # If LinkedIn wants a verification challenge even with the cookie, handle it
            if "linkedin.com/checkpoint" in url or "/challenge/" in url:
                print(f"  [LINKEDIN] Cookie login hit a verification challenge (URL: {url})")
                if _handle_verification(page, task_input):
                    _save_session()
                    return True
                # Verification timed out — fall through to password strategy
            else:
                print(f"  [LINKEDIN] Cookie rejected by LinkedIn (landed: {url}). "
                      f"Session was revoked — trying email/password login.")
        except Exception as e:
            print(f"  [LINKEDIN] Cookie login error: {e} — falling back to email/password")

        # Clear any cookies that may have been set during the failed cookie attempt,
        # otherwise the stale li_at causes ERR_TOO_MANY_REDIRECTS on the login page.
        try:
            page.context.clear_cookies()
        except Exception:
            pass

    # ── Strategy 2: Email + Password login ────────────────────────────────────
    print("  [LINKEDIN] Opening login page...")
    if not _safe_goto(page, LINKEDIN_LOGIN_URL):
        print("  [LINKEDIN] Could not load login page after retries")
        return False
    human_sleep(NAV_WAIT, NAV_WAIT + 2)

    def _find_email_input():
        """Find the email/phone field — design-agnostic."""
        # L1: known stable attributes (2000ms — React SPA needs time to hydrate)
        for sel in [
            "input#username", "input[name='session_key']",
            "input[autocomplete='email']", "input[autocomplete='username']",
            "input[autocomplete='webauthn']",
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000): return el
            except Exception: pass

        # L2: Playwright role/label matching
        # Note: LinkedIn wraps label text in a <div> inside <label>, so we try
        # get_by_role first (more robust), then get_by_label as fallback
        for lbl in ["Email or phone", "Email", "Phone or email", "Username"]:
            try:
                el = page.get_by_role("textbox", name=lbl).first
                if el.is_visible(timeout=1500): return el
            except Exception: pass
            try:
                el = page.get_by_label(lbl).first
                if el.is_visible(timeout=500): return el
            except Exception: pass

        # L3: JS DOM scan — find visible text/email/tel input before the password field
        # Uses attribute selector [id="..."] instead of #id to handle React's
        # dynamic IDs that contain colons (e.g. :r3:) which break CSS #id selectors
        try:
            sel_id = page.evaluate("""() => {
                const pwd = document.querySelector('input[type="password"]');
                const allInputs = Array.from(document.querySelectorAll('input'));
                const pwdPos = pwd ? allInputs.indexOf(pwd) : 9999;
                const candidates = allInputs.filter(el => {
                    const t = (el.type || 'text').toLowerCase();
                    const r = el.getBoundingClientRect();
                    const pos = allInputs.indexOf(el);
                    return (t === 'text' || t === 'email' || t === 'tel' || t === '')
                        && el.offsetParent !== null
                        && r.width > 40 && r.height > 10
                        && pos < pwdPos;
                });
                return candidates.at(-1)?.id || null;
            }""")
            if sel_id:
                # Use attribute selector — handles IDs with special chars like :r3:
                el = page.locator(f'[id="{sel_id}"]').first
                if el.is_visible(timeout=1000): return el
        except Exception: pass

        return None

    def _find_submit_button():
        """Find the sign-in submit button — design-agnostic."""
        # L1: Playwright semantic role — most future-proof (works with any DOM shape)
        try:
            el = page.get_by_role("button", name="Sign in", exact=True).first
            if el.is_visible(timeout=2000): return el
        except Exception: pass
        try:
            el = page.get_by_role("button", name="Log in", exact=True).first
            if el.is_visible(timeout=500): return el
        except Exception: pass

        # L2: known stable attribute selectors
        for sel in [
            "button[type='submit']", "input[type='submit']",
            "button[data-litms-control-urn='login-submit']",
            "button:text-is('Sign in')", "button:text-is('Log in')",
            "button:text-is('Sign In')", "button:text-is('Log In')",
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=500): return el
            except Exception: pass

        # L3: JS scan — visible button with sign-in keywords, not an SSO provider
        try:
            clicked = page.evaluate("""() => {
                const SSO   = ['google','microsoft','apple','facebook','github','twitter'];
                const WORDS = ['sign in','log in','login','signin'];
                const btn = Array.from(document.querySelectorAll(
                    'button,[role="button"],input[type="submit"]'
                )).find(el => {
                    const txt = (el.innerText||el.value||el.getAttribute('aria-label')||'').trim().toLowerCase();
                    const r = el.getBoundingClientRect();
                    return el.offsetParent !== null && r.width > 40
                        && WORDS.some(w => txt === w || txt.startsWith(w + ' '))
                        && !SSO.some(w => txt.includes(w));
                });
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            return "JS_CLICKED" if clicked else None
        except Exception: pass

        return None

    # ── Fill email ──
    email_el = None
    if email:
        email_el = _find_email_input()
        if email_el:
            try:
                email_el.click()
                human_sleep(0.3, 0.6)
                # Clear any pre-filled value first
                email_el.click(click_count=3)
                human_sleep(0.1, 0.2)
                human_type(page, email, locator=email_el)
                print(f"  [LINKEDIN] Email filled ✓")
            except Exception as e:
                print(f"  [LINKEDIN] Warning: email fill error: {e}")
        else:
            print("  [LINKEDIN] Warning: email field not found on page")

    # ── Handle two-step login: click Continue/Next if password not yet visible ──
    # LinkedIn sometimes shows email → Continue → password on separate "steps".
    if email and password:
        try:
            pwd_visible = page.locator("input[type='password']").first.is_visible(timeout=2000)
        except Exception:
            pwd_visible = False

        if not pwd_visible:
            print("  [LINKEDIN] Password field not visible — submitting email step…")
            _continued = False
            # 1. Try JS click on the submit button (most reliable across LinkedIn A/B variants)
            try:
                clicked = page.evaluate("""() => {
                    const btn = document.querySelector(
                        'button[type="submit"], input[type="submit"], button.sign-in-form__submit-button'
                    );
                    if (btn) { btn.click(); return true; }
                    const form = document.querySelector('form');
                    if (form) { form.submit(); return true; }
                    return false;
                }""")
                if clicked:
                    print("  [LINKEDIN] Submitted email form via JS ✓")
                    _continued = True
            except Exception:
                pass
            # 2. Playwright locator click fallback
            if not _continued:
                for _sel in ["button[type='submit']", "input[type='submit']",
                             "button:text('Continue')", "button:text('Sign in')"]:
                    try:
                        _btn = page.locator(_sel).first
                        if _btn.is_visible(timeout=2000):
                            human_click(page, locator=_btn)
                            print(f"  [LINKEDIN] Clicked '{_sel}' ✓")
                            _continued = True
                            break
                    except Exception:
                        pass
            # 3. Enter key last resort
            if not _continued:
                try:
                    if email_el:
                        email_el.press("Enter")
                        print("  [LINKEDIN] Pressed Enter on email field")
                except Exception:
                    pass
            # Wait for page to navigate to password step
            try:
                page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            human_sleep(3.0, 5.0)

    # ── Fill password + submit ──
    if email and password:
        try:
            pwd_el = page.locator("input[type='password']").first
            if not pwd_el.is_visible(timeout=12000):
                print("  [LINKEDIN] Password field still not visible after 12s — attempting Enter fallback")
                try: page.keyboard.press("Enter")
                except Exception: pass
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                human_sleep(2, 3)

            if pwd_el.is_visible(timeout=3000):
                pwd_el.click()
                human_sleep(0.2, 0.5)
                # Clear any auto-filled value
                pwd_el.click(click_count=3)
                human_sleep(0.1, 0.2)
                human_type(page, password, locator=pwd_el, typo_rate=0.0)
                print("  [LINKEDIN] Password filled ✓")
                human_sleep(0.6, 1.2)

                result = _find_submit_button()
                if result == "JS_CLICKED":
                    print("  [LINKEDIN] Sign In clicked via JS ✓")
                elif result:
                    human_click(page, locator=result)
                    print("  [LINKEDIN] Sign In clicked ✓")
                else:
                    print("  [LINKEDIN] Submit button not found — pressing Enter on password field")
                    pwd_el.press("Enter")
            else:
                print("  [LINKEDIN] Password field not found — pressing Enter as fallback")
                page.keyboard.press("Enter")
        except Exception as e:
            print(f"  [LINKEDIN] Warning: password/submit error: {e}")
            try: page.keyboard.press("Enter")
            except Exception: pass
    elif email:
        print("  [LINKEDIN] Email pre-filled — please enter password and click Sign In")
    else:
        print("  [LINKEDIN] ============================================")
        print("  [LINKEDIN]  Please log in to LinkedIn in the browser.  ")
        print("  [LINKEDIN]  Waiting automatically — no ENTER needed.   ")
        print("  [LINKEDIN]  (You have 3 minutes to log in)             ")
        print("  [LINKEDIN] ============================================")

    # ── Wait for successful navigation away from login/checkpoint ────────────
    # Real verification challenges (OTP, CAPTCHA, push-notification) have URLs
    # like /checkpoint/challenge/, /checkpoint/verify/, /checkpoint/wam/.
    # "/checkpoint/lg/login" is just LinkedIn's login-error page — NOT a challenge.
    _REAL_CHALLENGE_MARKERS = (
        "/checkpoint/challenge",
        "/checkpoint/verify",
        "/checkpoint/wam",
        "/challenge/",
    )

    # Fast-path: already logged in (credentials were pre-filled and accepted)
    try:
        _quick_url = page.url or ""
        _still_on_login_quick = (
            "linkedin.com/login" in _quick_url or
            "linkedin.com/checkpoint" in _quick_url or
            "/uas/login" in _quick_url
        )
        if not _still_on_login_quick:
            print(f"  [LINKEDIN] Login confirmed ✅  URL: {_quick_url}")
            _save_session()
            return True
    except Exception:
        pass

    # ── Build the VNC URL for the Telegram message ────────────────────────────
    _app_url = (
        os.environ.get("RAILWAY_STATIC_URL", "")
        or os.environ.get("NEXT_PUBLIC_APP_URL", "")
    ).rstrip("/")
    _sid = task_input.get("session_id", "")
    # Session ID must be inside the path param so noVNC passes it
    # to the WebSocket: /vnc-ws?session=ID → routes to correct x11vnc port
    _vnc_path = f"../vnc-ws%3Fsession%3D{_sid}" if _sid else "../vnc-ws"
    _vnc_url  = f"{_app_url}/novnc/?path={_vnc_path}&autoconnect=1&resize=scale" if _app_url else ""

    _log(task_input,
         "⏳ Waiting for LinkedIn login… Open the VNC screen, log in, then reply done.",
         "warning", "system")

    _login_msg = (
        "🔐 <b>LinkedIn login required</b>\n\n"
        "The cloud agent is waiting for you to log in to LinkedIn.\n"
        "You have <b>10 minutes</b> to complete the login.\n"
    )
    if _vnc_url:
        _login_msg += f"\n👁 <b>Open VNC to log in:</b>\n<a href=\"{_vnc_url}\">{_vnc_url}</a>\n"
    _login_msg += (
        "\nOnce you have logged in, reply <b>done</b> to continue.\n"
        "Or reply <b>stop</b> to stop all.\n"
        "⏳ Waiting up to <b>10 minutes</b>."
    )

    # _wait_for_resolution polls both:
    #   • URL-exit: auto-resolves as soon as the URL leaves the login/checkpoint pages
    #   • Telegram: resolves when user replies "done" / "skip" / "stop"
    # This ensures the "done" reply is always consumed here — not silently
    # discarded and then missed by _handle_verification's fresh offset snapshot.
    _login_result = _wait_for_resolution(
        page, task_input, _login_msg, wait_minutes=10, check_url_exit=True
    )

    if _login_result == "stop":
        return False

    if _login_result == "timeout":
        _push_screenshot(task_input, page)
        print(f"  [LINKEDIN] Login timed out. Final URL: {page.url}")
        return False

    # _login_result == "resolved" (URL changed or user replied "done") or "skip"
    # ── Wait for the URL to fully leave the login/checkpoint pages (up to 20 s) ──
    # This handles the race where the user replied "done" a moment before the
    # browser finished its redirect, or the URL auto-detection fired slightly
    # before the final URL settled.
    _BLOCKED_MARKERS = (
        "linkedin.com/login",
        "linkedin.com/checkpoint",
        "/uas/login",
    )
    _url_after_login = ""
    _settle_deadline = time.time() + 20
    while time.time() < _settle_deadline:
        try:
            _url_after_login = page.url or ""
        except Exception:
            time.sleep(1)
            continue
        _is_login_url = any(m in _url_after_login for m in _BLOCKED_MARKERS)
        if not _is_login_url and _url_after_login and "about:blank" not in _url_after_login:
            break  # URL has left all login/checkpoint pages
        time.sleep(1)
    else:
        # Still on login page after 20 s — check one last time
        try:
            _url_after_login = page.url or ""
        except Exception:
            _url_after_login = ""

    if any(m in _url_after_login for m in _REAL_CHALLENGE_MARKERS):
        # LinkedIn popped up a 2FA / CAPTCHA / push-notification challenge
        # after the password was accepted.  Handle it now with a fresh wait.
        if _handle_verification(page, task_input):
            _save_session()
            return True
        else:
            _log(task_input,
                 "⚠️ Login failed — verification not completed within 10 minutes. "
                 "Please restart the job agent and complete the LinkedIn security check promptly.",
                 "error", "system")
            return False

    _still_on_login_final = any(m in _url_after_login for m in _BLOCKED_MARKERS)
    if _still_on_login_final:
        _log(task_input,
             "⚠️ Still on LinkedIn login page after wait — login may have failed. "
             "Please restart and try again.",
             "error", "system")
        _push_screenshot(task_input, page)
        return False

    print(f"  [LINKEDIN] Login confirmed ✅  URL: {_url_after_login}")
    _save_session()
    return True




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


def _sanitize_url(url: str) -> str:
    """Return url only if it looks like a real public URL (not localhost/dev URLs)."""
    url = (url or "").strip()
    if not url:
        return ""
    bad = ("localhost", "127.0.0.1", "0.0.0.0", ":3000", ":8080", ":5000", ":4000")
    if any(b in url for b in bad):
        return ""
    return url


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
        "linkedin_url": _sanitize_url(task_input.get("linkedin_url", "")),
        "github_url": _sanitize_url(task_input.get("github_url", "")),
        "portfolio_url": _sanitize_url(task_input.get("portfolio_url", "")),
        "years_experience": task_input.get("years_experience", 2),
        "highest_education": task_input.get("highest_education", ""),
        "notice_period": task_input.get("notice_period", ""),
        "salary_expectation": task_input.get("salary_expectation", ""),
        "current_ctc": task_input.get("current_ctc", ""),
        # EEO / Diversity / Identity
        "work_authorization": task_input.get("work_authorization", ""),
        "nationality": task_input.get("nationality", ""),
        "country_of_origin": task_input.get("country_of_origin", ""),
        "gender": task_input.get("gender", ""),
        "disability_status": task_input.get("disability_status", ""),
        "veteran_status": task_input.get("veteran_status", ""),
        "ethnicity": task_input.get("ethnicity", ""),
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

                        # "If yes, please describe/identify" follow-up fields → "No"
                        _is_conditional_followup = any(kw in label_text for kw in (
                            "if yes, please", "if yes, describe", "if yes, identify",
                            "if applicable, please", "please explain if",
                            "please describe your",
                        ))
                        if _is_conditional_followup:
                            human_type(page, "No", locator=inp)
                            print(f"  [LINKEDIN] Conditional follow-up '{label_text[:60]}' → 'No'")
                            continue

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
                cl_result  = generate_cover_letter(resume_text_for_cover, jd_text_for_cover, company, role, quick=True)
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
            # Conflict of interest / relatives
            "family member", "relative", "friends or family",
            "outside business", "advisory", "consulting", "board role", "side business",
            "worked for", "previously worked", "ever worked", "former employee",
            "been employed by", "employment with",
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

                # EEO/diversity Yes/No radios — use user's actual profile values, not always "No"
                if is_yes_no and any(kw in question_text for kw in (
                    "disability", "disabled", "veteran", "protected veteran",
                    "gender", "race", "ethnicity", "sexual orientation",
                )):
                    d_status = (task_input.get("disability_status") or "").lower()
                    v_status = (task_input.get("veteran_status") or "").lower()
                    if "disability" in question_text or "disabled" in question_text:
                        # "No" unless user explicitly says they have a disability
                        want_no = "i have a disability" not in d_status
                    elif "veteran" in question_text:
                        # "No" unless user is a veteran
                        want_no = not ("i am a veteran" in v_status or "disabled veteran" in v_status)
                    else:
                        want_no = True  # gender/race/ethnicity/sexual orientation → No

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
                    # Non-Yes/No radios — for EEO/diversity pick "prefer not" first,
                    # then fall back to Claude for everything else
                    _eeo_question = any(kw in question_text for kw in (
                        "disability", "disabled", "veteran", "protected veteran",
                        "gender", "race", "ethnicity", "sexual orientation",
                    ))
                    if _eeo_question:
                        # Pull user's actual EEO profile values
                        d_status = (task_input.get("disability_status") or "").lower()
                        v_status = (task_input.get("veteran_status") or "").lower()
                        g_val    = (task_input.get("gender") or "").lower()
                        eth_val  = (task_input.get("ethnicity") or "").lower()

                        matched_from_profile = False
                        if "disability" in question_text or "disabled" in question_text:
                            if d_status and "prefer not" not in d_status:
                                # Map user's choice to option keywords
                                if "don't have" in d_status or "do not have" in d_status:
                                    kws = ["no disability", "i don't have", "i do not have", "not disabled", "none", "no"]
                                elif "i have" in d_status:
                                    kws = ["i have a disability", "yes, i have", "have a disability"]
                                else:
                                    kws = ["prefer not", "decline", "do not wish", "not specified", "choose not"]
                                for r, lbl, val, inp_id in options:
                                    if any(kw in lbl for kw in kws):
                                        target_radio, target_label_id = r, inp_id
                                        print(f"  [LINKEDIN] Radio → Profile disability '{lbl}' for: {question_text[:60]!r}")
                                        matched_from_profile = True
                                        break
                        elif "veteran" in question_text:
                            if v_status and "prefer not" not in v_status:
                                if "not a veteran" in v_status or ("not" in v_status and "veteran" in v_status):
                                    kws = ["not a veteran", "i am not", "not protected", "non-veteran", "no"]
                                elif "disabled veteran" in v_status:
                                    kws = ["disabled veteran", "veteran with a disability"]
                                elif "i am a veteran" in v_status:
                                    kws = ["i am a veteran", "veteran", "active duty", "yes"]
                                else:
                                    kws = ["prefer not", "decline", "not wish", "not specified"]
                                for r, lbl, val, inp_id in options:
                                    if any(kw in lbl for kw in kws):
                                        target_radio, target_label_id = r, inp_id
                                        print(f"  [LINKEDIN] Radio → Profile veteran '{lbl}' for: {question_text[:60]!r}")
                                        matched_from_profile = True
                                        break
                        elif "gender" in question_text:
                            if g_val and "prefer not" not in g_val:
                                for r, lbl, val, inp_id in options:
                                    if g_val in lbl or lbl in g_val:
                                        target_radio, target_label_id = r, inp_id
                                        print(f"  [LINKEDIN] Radio → Profile gender '{lbl}' for: {question_text[:60]!r}")
                                        matched_from_profile = True
                                        break
                        elif any(w in question_text for w in ("race", "ethnicity")):
                            if eth_val and "prefer not" not in eth_val:
                                for r, lbl, val, inp_id in options:
                                    if eth_val in lbl or lbl in eth_val:
                                        target_radio, target_label_id = r, inp_id
                                        print(f"  [LINKEDIN] Radio → Profile ethnicity '{lbl}' for: {question_text[:60]!r}")
                                        matched_from_profile = True
                                        break

                        # If no profile match or user chose prefer-not, pick opt-out option
                        if not matched_from_profile:
                            for r, lbl, val, inp_id in options:
                                if any(kw in lbl for kw in (
                                    "prefer not", "decline", "do not wish", "not specified",
                                    "choose not", "no disability", "not disabled",
                                    "i don't have", "i do not have",
                                )):
                                    target_radio, target_label_id = r, inp_id
                                    print(f"  [LINKEDIN] Radio → EEO opt-out '{lbl}' for: {question_text[:60]!r}")
                                    break
                            # If no opt-out found, pick "No" or first option
                            if target_radio is None:
                                for r, lbl, val, inp_id in options:
                                    if lbl in ("no", "none"):
                                        target_radio, target_label_id = r, inp_id
                                        break
                    else:
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
                    work_auth = (task_input.get("work_authorization") or "").lower()
                    # Citizens, GC, EAD holders don't need sponsorship
                    no_sponsor = any(kw in work_auth for kw in [
                        "citizen", "permanent resident", "green card", "ead",
                        "employment authorization", "not applicable",
                    ])
                    if no_sponsor:
                        if not _pick(["no", "i don't need", "not required", "citizen", "authorized"]):
                            for i, v in enumerate(opt_vals):
                                if v.lower() not in _SKIP_VALS:
                                    sel.select_option(v)
                                    break
                    else:
                        if not _pick(["no", "i don't need", "not required", "citizen", "authorized"]):
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

                # Gender / diversity dropdowns — use user's actual profile value, fall back to "Prefer not"
                elif any(w in question_text for w in ("gender", "ethnicity", "race", "disability", "veteran")):
                    d_status = (task_input.get("disability_status") or "").lower()
                    v_status = (task_input.get("veteran_status") or "").lower()
                    g_val    = (task_input.get("gender") or "").lower()
                    eth_val  = (task_input.get("ethnicity") or "").lower()
                    filled = False
                    if "disability" in question_text:
                        if d_status and "prefer not" not in d_status:
                            if "don't have" in d_status or "do not have" in d_status:
                                filled = _pick(["no disability", "i don't have", "i do not have", "not disabled", "no"])
                            elif "i have" in d_status:
                                filled = _pick(["yes, i have", "i have a disability", "have disability"])
                    elif "veteran" in question_text:
                        if v_status and "prefer not" not in v_status:
                            if "not a veteran" in v_status:
                                filled = _pick(["not a veteran", "i am not", "non-veteran", "no"])
                            elif "disabled veteran" in v_status:
                                filled = _pick(["disabled veteran", "veteran with a disability"])
                            elif "i am a veteran" in v_status:
                                filled = _pick(["i am a veteran", "veteran", "yes"])
                    elif "gender" in question_text:
                        if g_val and "prefer not" not in g_val:
                            filled = _pick([g_val])
                    elif any(w in question_text for w in ("ethnicity", "race")):
                        if eth_val and "prefer not" not in eth_val:
                            filled = _pick([eth_val])
                    if not filled:
                        _pick(["prefer not", "decline", "do not wish", "not specified"])

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
                elif any(w in question_text for w in ("country", "region", "based in", "nationality", "country of origin")):
                    city = (task_input.get("current_city") or "").lower()
                    country = (task_input.get("phone_country") or "").split("(")[0].strip().lower()
                    country_origin = (task_input.get("country_of_origin") or "").lower()
                    nat_val = (task_input.get("nationality") or "").lower()
                    if "nationality" in question_text and nat_val and _pick([nat_val]):
                        pass
                    elif "country of origin" in question_text and country_origin and _pick([country_origin]):
                        pass
                    elif country_origin and _pick([country_origin]):
                        pass
                    elif city and _pick([city]):
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
            resume_id=task_input.get("resume_id") or None,
            resume_version_id=task_input.get("_resume_version_id") or None,
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
    _li_apply_type = task_input.get("linkedin_apply_types", "easy_apply_only")
    params: dict[str, str] = {
        "keywords": keywords,
        "location": location,
        "sortBy":   "DD",     # Most recent
    }
    # Easy Apply filter: only when preference is easy_apply_only
    # For external_only/both we need general search (no f_AL)
    if _li_apply_type == "easy_apply_only":
        params["f_AL"] = "true"

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
    max_apply    = int(task_input.get("max_apply", MAX_APPLY))
    smart_match  = task_input.get("smart_match", False)
    smart_filter = task_input.get("smart_filter", True)   # title pre-filter toggle
    is_admin     = task_input.get("_is_super_admin", False)
    pool_mult    = 3 if smart_match else 2
    # Pool cap: admin → 150 (testing); filter ON → 50; filter OFF → 25
    if is_admin:
        SEARCH_POOL_CAP = 150
    elif smart_filter:
        SEARCH_POOL_CAP = 50
    else:
        SEARCH_POOL_CAP = 25
    target_pool = min(SEARCH_POOL_CAP, max(max_apply * pool_mult, 20))
    max_pages   = 4   # 4 pages × 25 jobs = 100 slots max; capped by SEARCH_POOL_CAP
    seen: set   = set()
    job_links: list[str] = []

    for page_num in range(max_pages):
        start = page_num * 25
        search_url = f"{base_url}&start={start}"
        print(f"  [LINKEDIN] Page {page_num + 1} URL: {search_url}")
        if not _safe_goto(page, search_url):
            print(f"  [LINKEDIN] Failed to load search page {page_num + 1} — stopping pagination")
            break
        human_sleep(NAV_WAIT + 1, NAV_WAIT + 4)
        # Verify we actually landed on a jobs page, not the homepage/feed
        _landed = page.url or ""
        if "/jobs/" not in _landed:
            print(f"  [LINKEDIN] ⚠️ Redirected to {_landed[:60]} — cooling down and retrying once…")
            try:
                page.goto("https://www.linkedin.com/feed/",
                          wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass
            human_sleep(6, 12)
            if not _safe_goto(page, search_url):
                print("  [LINKEDIN] ⚠️ Retry navigation failed — stopping search (bot detection likely)")
                task_input["_redirect_blocked"] = True
                break
            human_sleep(NAV_WAIT + 1, NAV_WAIT + 3)
            _landed = page.url or ""
            if "/jobs/" not in _landed:
                print(f"  [LINKEDIN] ⚠️ Still redirected after retry (landed: {_landed[:80]}). "
                      f"Stopping search — LinkedIn is blocking automated search.")
                task_input["_redirect_blocked"] = True
                break
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


def _dismiss_cookie_banner(pg, task_input: dict) -> None:
    """
    Click any cookie consent / GDPR banner accept button.
    Runs a broad JS sweep first (fastest), then Playwright selector checks.
    Silent — never raises.
    """
    try:
        accepted = pg.evaluate("""() => {
            // ── Pass 1: LinkedIn-specific consent modal ─────────────────────
            // Scopes the search to a dialog/modal that contains privacy/cookie text.
            // This avoids accidentally clicking connection-request 'Accept' buttons
            // or other 'Accept' buttons that appear on /feed/.
            const modalCandidates = Array.from(document.querySelectorAll(
                '[data-test-modal],[role="dialog"],.artdeco-modal,.contextual-sign-in-modal,'
                + '[class*="modal"],[class*="overlay"],[class*="cookie"],[class*="consent"],'
                + '[id*="cookie"],[id*="consent"]'
            ));
            for (const container of modalCandidates) {
                const ctxt = (container.innerText || '').toLowerCase();
                if (!(ctxt.includes('privacy') || ctxt.includes('cookie') ||
                      ctxt.includes('consent') || ctxt.includes('gdpr'))) continue;
                const acceptKws = ['accept all','accept cookies','allow all','agree',
                                   'i agree','accept','allow cookies','got it'];
                const rejectKws = ['reject','decline','deny','no thanks','refuse',
                                   'necessary only','essential only'];
                for (const btn of container.querySelectorAll('button,[role="button"]')) {
                    const txt = (btn.innerText||btn.textContent||btn.getAttribute('aria-label')||'')
                                 .trim().toLowerCase();
                    if (!txt) continue;
                    if (rejectKws.some(r => txt.includes(r))) continue;
                    if (acceptKws.some(k => txt.includes(k))) {
                        btn.click();
                        return true;
                    }
                }
            }
            // ── Pass 2: Broad sweep for non-LinkedIn ATS cookie banners ─────
            // Only runs if no modal dialog found above.
            const keywords = ['accept all','accept cookies','allow all','agree','i agree',
                              'allow cookies','got it','okay'];
            const reject   = ['reject','decline','deny','no thanks','refuse','necessary only',
                               'essential only','manage','settings','preferences'];
            for (const el of document.querySelectorAll(
                '[class*="cookie"],[class*="consent"],[id*="cookie"],[id*="consent"]'
            )) {
                const txt = (el.innerText||el.textContent||el.getAttribute('aria-label')||'').trim().toLowerCase();
                if (!txt) continue;
                if (reject.some(r => txt.includes(r))) continue;
                if (keywords.some(k => txt.includes(k))) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if accepted:
            pg.wait_for_timeout(600)
            _log(task_input, "External apply: cookie banner dismissed", "info", "navigation")
            return
    except Exception:
        pass

    # Playwright fallback — common framework selectors
    for sel in [
        "#onetrust-accept-btn-handler",
        "button#accept-all", "button#acceptAll", "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "[data-testid='cookie-policy-dialog-accept-button']",
        # ATS / job-board specific cookie consent (Taleo, Oracle, etc.)
        "button[data-ui='cookie-consent-accept-in-modal']",
        "button[data-ui='cookie-consent-save-settings']",
        "button[aria-label*='Accept']", "button[aria-label*='accept']",
        "button:has-text('Accept all')", "button:has-text('Accept All')",
        "button:has-text('Allow all')", "button:has-text('Allow All')",
        "button:has-text('Accept cookies')", "button:has-text('I accept')",
        "button:has-text('Got it')", "button:has-text('OK')",
        ".cc-accept", ".cc-btn.cc-allow",
        "[class*='cookie'] button", "[id*='cookie'] button",
    ]:
        try:
            btn = pg.locator(sel).first
            if btn.is_visible(timeout=600):
                btn.click()
                pg.wait_for_timeout(600)
                _log(task_input, f"External apply: cookie banner dismissed via {sel}", "info", "navigation")
                return
        except Exception:
            continue


def _handle_captcha(ext_page, task_input: dict, max_wait: int = 25) -> bool:
    """
    Detect Cloudflare Turnstile (or similar CAPTCHA) and handle both modes:
    - "managed" / auto mode: waits for silent auto-verification
    - "interactive" checkbox mode: clicks the "Verify you are human" checkbox,
      then waits for the #success state inside the iframe.

    Returns True if cleared/not present, False if still blocked after timeout.
    """
    _CF_IFRAME_SEL = (
        'iframe[src*="challenges.cloudflare.com"], '
        'iframe[src*="cloudflare.com/cdn-cgi/challenge-platform"], '
        'iframe[title*="Widget containing a Cloudflare security challenge"]'
    )
    try:
        has_challenge = ext_page.evaluate("""() => {
            return !!(
                document.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
                document.querySelector('iframe[src*="cloudflare.com/cdn-cgi/challenge-platform"]') ||
                document.querySelector('[id^="turnstile-container"]') ||
                document.querySelector('div[class*="cf-turnstile"]') ||
                document.querySelector('iframe[title*="Cloudflare security challenge"]')
            );
        }""")
    except Exception:
        return True  # can't check — assume OK

    if not has_challenge:
        return True

    _log(task_input,
         "External apply: Cloudflare Turnstile detected — attempting to handle…",
         "warning", "navigation")

    # ── Strategy 1: Click the "Verify you are human" checkbox (interactive mode) ──
    # Turnstile's checkbox challenge lives inside a cross-origin iframe.
    # Playwright's frame_locator() can reach it as long as the frame is loaded.
    _checkbox_clicked = False
    try:
        _cf_frame = ext_page.frame_locator(_CF_IFRAME_SEL).first
        # The checkbox is inside label.cb-lb; click it to trigger server-side verification
        _cb = _cf_frame.locator('label.cb-lb input[type="checkbox"], .cb-lb input[type="checkbox"]').first
        if _cb.is_visible(timeout=4000):
            # Use JS click inside the frame to avoid pointer interception issues
            _cb.click(force=True)
            _checkbox_clicked = True
            _log(task_input,
                 "External apply: Turnstile checkbox clicked — waiting for verification…",
                 "info", "navigation")
            time.sleep(1.5)  # give Cloudflare time to start verifying
    except Exception:
        pass  # iframe not accessible or checkbox not visible — fall through to auto-wait

    # ── Strategy 2: Wait for verification to complete ──
    for _i in range(max_wait):
        time.sleep(1.0)
        try:
            # Check #success state inside the Turnstile iframe
            if _checkbox_clicked:
                try:
                    _cf_frame2 = ext_page.frame_locator(_CF_IFRAME_SEL).first
                    if _cf_frame2.locator('#success').first.is_visible(timeout=400):
                        _log(task_input, "External apply: Turnstile checkbox verified ✓", "info", "navigation")
                        time.sleep(0.5)
                        return True
                    # If fail/expired, try clicking the checkbox again once
                    if _i == 5:
                        try:
                            _cb2 = _cf_frame2.locator('label.cb-lb input[type="checkbox"]').first
                            if _cb2.is_visible(timeout=400):
                                _cb2.click(force=True)
                                _log(task_input, "External apply: Turnstile — retry click", "info", "navigation")
                        except Exception:
                            pass
                except Exception:
                    pass

            # Challenge clears when the iframe disappears OR form inputs appear
            still_blocked = ext_page.evaluate("""() => {
                const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]')
                             || document.querySelector('iframe[src*="cloudflare.com/cdn-cgi/challenge-platform"]');
                if (!iframe || !iframe.offsetParent) return false;
                const formInputs = document.querySelectorAll(
                    'form input:not([type="hidden"]), form select, form textarea'
                ).length;
                return formInputs < 2;
            }""")
            if not still_blocked:
                _log(task_input, "External apply: Turnstile verified ✓", "info", "navigation")
                return True
        except Exception:
            pass

    _log(task_input,
         "External apply: Turnstile not resolved after 25s — will attempt to continue anyway",
         "warning", "navigation")
    return False



# ──────────────────────────────────────────────────────────────────────────────
# External ATS portal shared helpers
# ──────────────────────────────────────────────────────────────────────────────

# LinkedIn SSO selectors tried in order on any login gate
_LINKEDIN_SSO_SELECTORS = [
    "#login-with-linkedin-button",
    "[id*='linkedin-login']", "[id*='linkedin_login']",
    "a:has-text('Apply with LinkedIn')",
    "a:has-text('Login with LinkedIn')",
    "a:has-text('Sign in with LinkedIn')",
    "a:has-text('Continue with LinkedIn')",
    "button:has-text('Apply with LinkedIn')",
    "button:has-text('Login with LinkedIn')",
    "button:has-text('Sign in with LinkedIn')",
    "button:has-text('Continue with LinkedIn')",
    "[class*='linkedin-login']", "[class*='linkedin-sso']", "[class*='lwli']",
]


def _handle_portal_login(ext_page, task_input: dict, orig_page=None) -> bool:
    """
    Detect and handle a login gate on an external ATS portal.

    Strategy:
      1. If page already shows ≥3 form inputs it is NOT a login wall → skip.
      2. Detect login-page keywords in visible text.
      3. Click LinkedIn SSO button and wait for the OAuth popup to auto-close
         (works when the browser is already signed into LinkedIn).
      4. If a password-only form remains, log and return False (can't automate).

    Returns True if the login gate was cleared, False if not a login page
    or if it could not be cleared.
    """
    try:
        # Already on a real form?
        try:
            n = ext_page.evaluate(
                "() => document.querySelectorAll("
                "  'form input:not([type=\"hidden\"]):not([tabindex=\"-1\"]),"
                "   form textarea, form select:not([tabindex=\"-1\"])'"
                ").length"
            )
            if n >= 3:
                return False
        except Exception:
            pass

        try:
            page_text = (ext_page.evaluate(
                "() => (document.body && document.body.innerText) || ''"
            ) or "").lower()
        except Exception:
            return False

        is_login = any(kw in page_text for kw in [
            "log in", "login", "sign in", "signin",
            "create an account", "create account",
            "forgot your password", "forgot password",
        ])
        if not is_login:
            return False

        # Try each LinkedIn SSO selector
        for sel in _LINKEDIN_SSO_SELECTORS:
            try:
                btn = ext_page.locator(sel).first
                if not btn.is_visible(timeout=700):
                    continue
                _log(task_input,
                     f"Portal login: LinkedIn SSO found ({sel}) — clicking",
                     "info", "navigation")
                _pre_url = ext_page.url
                btn.click()
                time.sleep(1.5)

                # Handle LinkedIn OAuth popup (auto-approves if already signed in)
                all_pages = ext_page.context.pages
                lk_popups = [
                    p for p in all_pages
                    if p is not ext_page and "linkedin.com/" in (p.url or "")
                ]
                if lk_popups:
                    _log(task_input,
                         "Portal login: LinkedIn OAuth popup detected — waiting for auto-approval...",
                         "info", "navigation")
                    oauth_p = lk_popups[-1]
                    for _ in range(20):           # up to 20 s
                        time.sleep(1.0)
                        if oauth_p.is_closed() or ext_page.url != _pre_url:
                            break
                        # If OAuth needs manual Allow click
                        try:
                            for allow_sel in [
                                "button:has-text('Allow')",
                                "button:has-text('Authorize')",
                                "button:has-text('Continue')",
                                "button[type='submit']",
                            ]:
                                ab = oauth_p.locator(allow_sel).first
                                if ab.is_visible(timeout=300):
                                    ab.click()
                                    time.sleep(1.0)
                                    break
                        except Exception:
                            pass

                try:
                    ext_page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                human_sleep(1.5, 2.5)

                # Verify we moved past the login gate
                _post_url = ext_page.url
                _has_form = False
                try:
                    _has_form = ext_page.evaluate(
                        "() => document.querySelectorAll("
                        "  'form input:not([type=\"hidden\"])'"
                        ").length >= 2"
                    )
                except Exception:
                    pass
                if _post_url != _pre_url or _has_form:
                    _log(task_input,
                         "Portal login: successfully passed login gate via LinkedIn SSO",
                         "success", "navigation")
                    _dismiss_cookie_banner(ext_page, task_input)
                    return True
            except Exception:
                continue

        # Detect account-creation wall we can't bypass
        try:
            n_pwd = ext_page.evaluate(
                "() => document.querySelectorAll('input[type=\"password\"]').length"
            )
            if n_pwd > 0:
                _log(task_input,
                     "Portal login: login/registration wall — no LinkedIn SSO available. "
                     "Manual sign-in required.",
                     "warning", "ai_decision")
        except Exception:
            pass

        return False

    except Exception as _e:
        _log(task_input, f"Portal login handler error: {_e}", "warning", "navigation")
        return False


def _handle_application_method_chooser(ext_page, task_input: dict) -> bool:
    """
    Detect and handle "How would you like to apply?" screens.

    Common patterns:
      - Greenhouse  "Start Your Application" modal
      - Lever / Ashby method chooser
      - Generic "Apply with LinkedIn" / "Apply Manually" buttons

    Preference order:
      1. 'Apply with LinkedIn'  (auto-fills from profile — any chooser)
      2. 'Use my last application' (Greenhouse one-click repeat apply)
      3. 'Apply Manually' / 'Continue'  (plain form fallback)

    Returns True if a method was chosen, False if no chooser detected.
    """
    try:
        try:
            page_text = (ext_page.evaluate(
                "() => (document.body && document.body.innerText) || ''"
            ) or "").lower()
        except Exception:
            return False

        looks_like_chooser = any(kw in page_text for kw in [
            "how would you like to apply",
            "how do you want to apply",
            "start your application",
            "choose how you",
            "select how you would like",
            "apply using",
        ])

        # Also detect if a LinkedIn-method button is directly on the page
        has_lk_btn = False
        for sel in _LINKEDIN_SSO_SELECTORS:
            try:
                if ext_page.locator(sel).first.is_visible(timeout=400):
                    has_lk_btn = True
                    break
            except Exception:
                continue

        if not looks_like_chooser and not has_lk_btn:
            return False

        # ── 1. Apply with LinkedIn (preferred) ────────────────────────────
        for sel in _LINKEDIN_SSO_SELECTORS + [
            "a:has-text('Apply with LinkedIn')",
            "button:has-text('Apply with LinkedIn')",
        ]:
            try:
                btn = ext_page.locator(sel).first
                if not btn.is_visible(timeout=700):
                    continue
                _log(task_input,
                     f"Method chooser: clicking 'Apply with LinkedIn' ({sel})",
                     "info", "navigation")
                btn.click()
                time.sleep(1.2)

                # Handle LinkedIn OAuth popup
                all_pages = ext_page.context.pages
                lk_popups = [
                    p for p in all_pages
                    if p is not ext_page and "linkedin.com/" in (p.url or "")
                ]
                if lk_popups:
                    _log(task_input,
                         "Method chooser: LinkedIn OAuth popup — waiting...",
                         "info", "navigation")
                    oauth_p = lk_popups[-1]
                    for _ in range(20):
                        time.sleep(1.0)
                        if oauth_p.is_closed():
                            break
                        try:
                            for allow_sel in [
                                "button:has-text('Allow')",
                                "button:has-text('Authorize')",
                                "button[type='submit']",
                            ]:
                                ab = oauth_p.locator(allow_sel).first
                                if ab.is_visible(timeout=300):
                                    ab.click()
                                    time.sleep(1.0)
                                    break
                        except Exception:
                            pass

                try:
                    ext_page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                human_sleep(1.0, 2.0)
                _dismiss_cookie_banner(ext_page, task_input)
                return True
            except Exception:
                continue

        # ── 2. Use last application (Greenhouse) ──────────────────────────
        for sel in [
            "button:has-text('Use my last application')",
            "a:has-text('Use my last application')",
            "button:has-text('Use Last Application')",
        ]:
            try:
                btn = ext_page.locator(sel).first
                if btn.is_visible(timeout=700):
                    _log(task_input, f"Method chooser: '{sel}'", "info", "navigation")
                    btn.click()
                    try:
                        ext_page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    human_sleep(1.0, 1.5)
                    _dismiss_cookie_banner(ext_page, task_input)
                    return True
            except Exception:
                continue

        # ── 3. Manual / Continue fallback ──────────────────────────────────
        for sel in [
            "button:has-text('Apply Manually')",
            "a:has-text('Apply Manually')",
            "button:has-text('Continue')",
            "a:has-text('Continue')",
            "[data-qa='btn-apply-submit']",
        ]:
            try:
                btn = ext_page.locator(sel).first
                if btn.is_visible(timeout=700):
                    _log(task_input,
                         f"Method chooser: manual fallback ({sel})",
                         "info", "navigation")
                    btn.click()
                    try:
                        ext_page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    human_sleep(1.0, 1.5)
                    _dismiss_cookie_banner(ext_page, task_input)
                    return True
            except Exception:
                continue

        return False

    except Exception as _e:
        _log(task_input,
             f"Method chooser handler error: {_e}", "warning", "navigation")
        return False


def _unwrap_linkedin_apply_url(href: str) -> str:
    """
    Extract the real company URL from a LinkedIn safety/tracking redirect.

    LinkedIn wraps external apply links in redirects like:
      https://www.linkedin.com/safety/go?url=https%3A%2F%2Fcompany.com%2F...&_l=en_US

    Design-agnostic: checks all known redirect query-param names so it works
    even if LinkedIn renames the parameter in future redesigns.
    Returns the original href unchanged if it's already a direct URL.
    """
    if not href:
        return href
    from urllib.parse import urlparse, parse_qs, unquote
    try:
        parsed = urlparse(href)
        if "linkedin.com" not in (parsed.netloc or ""):
            return href  # already a direct company URL — nothing to unwrap
        params = parse_qs(parsed.query)
        # Try all known redirect param names (LinkedIn may rename these):
        for pname in ("url", "redirectUrl", "redirect_url", "destUrl", "dest", "target"):
            if pname in params:
                real = unquote(params[pname][0])
                if real.startswith("http"):
                    return real
    except Exception:
        pass
    return href  # return original — safety-page handler will deal with it at runtime


def _handle_linkedin_safety_redirect(ext_page, task_input: dict) -> None:
    """
    Called right after navigating to an apply URL.
    If we landed on LinkedIn's safety/interstitial page instead of the real
    company portal, this navigates through it to reach the destination.

    Design-agnostic strategy (works regardless of future safety-page redesigns):
      1. Try to extract destination from any external <a href> on the page
      2. Click the most prominent "Continue" / "Proceed" button
      3. Wait for JavaScript auto-redirect (LinkedIn sometimes auto-redirects)
    """
    try:
        cur = ext_page.url
        # Already on a non-LinkedIn page — nothing to do
        if "linkedin.com" not in cur:
            return
        # Only act on known redirect/safety URL patterns
        is_redirect_page = any(p in cur for p in (
            "/safety/go", "/safety", "/redir/", "/redirect", "/checkpoint"
        ))
        if not is_redirect_page:
            return

        _log(task_input,
             f"External apply: LinkedIn safety redirect detected ({cur[:70]}) — resolving…",
             "info", "navigation")

        # ── Strategy 1: extract real URL from any visible external link on page ──
        # The safety page always shows the destination as a clickable link.
        try:
            real_url = ext_page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                const ext = links.find(a =>
                    a.href &&
                    !a.href.includes('linkedin.com') &&
                    a.href.startsWith('http') &&
                    !a.href.startsWith('javascript')
                );
                return ext ? ext.href : null;
            }""")
            if real_url:
                _log(task_input,
                     f"External apply: safety link extracted → {real_url[:80]}",
                     "info", "navigation")
                ext_page.goto(real_url, wait_until="load", timeout=30000)
                try:
                    ext_page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                return
        except Exception:
            pass

        # ── Strategy 2: click through the interstitial (design-agnostic button scan) ──
        for sel in [
            "a:has-text('Continue')", "button:has-text('Continue')",
            "a:has-text('Proceed')", "button:has-text('Proceed')",
            "a:has-text('Go to site')", "button:has-text('Go to site')",
            "a:has-text('Yes, proceed')", "a:has-text('Yes, I agree')",
            "[data-tracking-control-name*='continue']",
            "[class*='safety'] a:not([href*='linkedin'])",
        ]:
            try:
                btn = ext_page.locator(sel).first
                if btn.is_visible(timeout=1200):
                    btn.click()
                    ext_page.wait_for_url(
                        lambda url: "linkedin.com" not in url,
                        timeout=12000
                    )
                    _log(task_input,
                         f"External apply: safety redirect cleared → {ext_page.url[:80]}",
                         "info", "navigation")
                    return
            except Exception:
                continue

        # ── Strategy 3: wait for JS auto-redirect ──
        try:
            ext_page.wait_for_url(
                lambda url: "linkedin.com" not in url,
                timeout=6000
            )
            _log(task_input,
                 f"External apply: auto-redirect landed on {ext_page.url[:80]}",
                 "info", "navigation")
        except Exception:
            _log(task_input,
                 "External apply: safety page not resolved — will attempt to continue",
                 "warning", "navigation")
    except Exception:
        pass


def _apply_external_job(page, apply_href: str, task_input: dict) -> bool:
    """
    Open the company application portal in a new browser tab, navigate to the
    form, fill every field with Claude AI, and submit.

    Handles ALL major ATS scenarios:
      1. Direct form page (fields already visible → fill + submit)
      2. Job-description page (click Apply CTA → form loads)
      3. Application-method chooser (Greenhouse / Lever / Ashby)
      4. LinkedIn SSO login wall (OAuth popup → auto-approves → form loads)
      5. Account-creation / registration wall (logs warn, cannot auto-handle)
      6. Upload-only screen (Cisco / Phenom) → upload resume, skip to form
      7. Multi-step forms → fill each step, Next → … → Submit
      8. Popup / new-tab form (switch to new tab, continue full flow there)

    Returns True if successfully submitted, False otherwise.
    """
    try:
        from automation.ai_client import fill_external_form_fields as _fill_fields
    except ImportError:
        _log(task_input, "External apply: ai_client unavailable", "error", "error")
        return False

    _log(task_input, "🌐 External apply — opening company portal…", "info", "navigation", {"url": apply_href})
    ext_page = None
    try:
        ext_page = page.context.new_page()
        # Use 'load' so the HTML + inline scripts fire, then wait for networkidle
        # so React/Vue SPAs have time to render the form.
        ext_page.goto(apply_href, wait_until="load", timeout=30000)
        try:
            ext_page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass  # timeout OK — continue with whatever rendered

        # ── Handle LinkedIn safety/interstitial redirect page ──
        # Navigating to a LinkedIn safety URL (linkedin.com/safety/go?url=...)
        # lands on an interstitial. Resolve it to the real company portal first.
        _handle_linkedin_safety_redirect(ext_page, task_input)
        human_sleep(1.5, 2.5)

        # ── Dismiss cookie / consent banners before doing anything ──
        _dismiss_cookie_banner(ext_page, task_input)

        # ── Handle login walls (LinkedIn SSO, email/password, create-account screens) ──
        _handle_portal_login(ext_page, task_input, orig_page=page)
        human_sleep(0.5, 1.0)

        # ── Handle Cloudflare Turnstile / CAPTCHA after login ──
        _handle_captcha(ext_page, task_input)

        # ── Handle "How would you like to apply?" chooser screens ──
        _handle_application_method_chooser(ext_page, task_input)
        human_sleep(0.3, 0.7)

        # ── If this is a job description page (no form yet), click 'Apply' CTA ──
        # e.g. Ashby, Lever, Greenhouse all show a description page with an
        # 'Apply for this Job' / 'Apply Now' button that leads to the actual form.
        _clicked_apply_cta = False
        for _cta_sel in [
            # Text-based — most common across all portals
            "a:has-text('Apply for this Job')",
            "a:has-text('Apply for this Position')",
            "button:has-text('Apply for this Job')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Online')",
            "button:has-text('Apply Online')",
            "a:has-text('Apply Here')",
            "button:has-text('Apply Here')",
            "a:has-text('Apply Today')",
            "button:has-text('Apply Today')",
            "button:has-text('Apply To Job')",
            "button:has-text('Apply to Job')",
            "button:has-text('Apply for Job')",
            "button:has-text('Apply for Position')",
            "button:has-text('Start Application')",
            "button:has-text('Begin Application')",
            "a:has-text('Start Application')",
            "button:has-text('Submit Application')",  # some portals use this as CTA
            "a:has-text('Apply')",                    # broad fallback — links only (safer)
            # Attribute-based — framework-agnostic
            "button[data-job-id]",                    # custom career portals (Husky, etc.)
            "button.openModal:has-text('Apply')",     # Bootstrap modal trigger
            "[data-action*='apply']",                 # custom data-action attributes
            "[data-testid*='apply-button']",
            "[data-testid*='apply_button']",
            "[data-testid='job-apply-button']",
            "[aria-label*='Apply for']",
            "[aria-label*='Apply Now']",
            # href-based — exclude all social share URLs
            "a[href*='/application']:not([href*='facebook']):not([href*='twitter']):not([href*='sharer']):not([href*='linkedin.com/share'])",
            "a[href*='/apply']:not([href*='facebook']):not([href*='twitter']):not([href*='sharer']):not([href*='mailto'])",
        ]:
            try:
                _cta = ext_page.locator(_cta_sel).first
                if _cta.is_visible(timeout=1200):
                    _log(task_input, f"External apply: clicking apply CTA ({_cta_sel})", "info", "navigation")
                    _pre_cta_url = ext_page.url
                    _cta.click()
                    import time as _time; _time.sleep(0.8)
                    # Check if click opened a popup/new tab — switch to it
                    _ctx_pages = page.context.pages
                    if len(_ctx_pages) > 1 and _ctx_pages[-1] is not ext_page:
                        _log(task_input, "External apply: CTA opened popup — switching to popup page", "info", "navigation")
                        ext_page = _ctx_pages[-1]
                        try:
                            ext_page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        # Wait for at least one form element to appear (SPA renders async after networkidle)
                        try:
                            ext_page.wait_for_selector("input, textarea, select", state="visible", timeout=9000)
                        except Exception:
                            pass
                    else:
                        # Check if a modal appeared on the same page (modal-based portals)
                        _modal_appeared = False
                        _modal_sels = [
                            # Role-based (most reliable)
                            "[role='dialog']:not([aria-hidden='true'])",
                            "[role='alertdialog']:not([aria-hidden='true'])",
                            # Bootstrap / jQuery plugins
                            ".modal.show",
                            ".modal.fade.show",
                            ".modal.in",
                            ".modal.openModal",
                            # Material UI / MUI
                            ".MuiDialog-paper",
                            # jQuery UI
                            ".ui-dialog-content",
                            # Foundation
                            ".reveal",
                            # Workday / Oracle
                            "[data-automation-id*='modal']",
                            "[data-automation-id*='dialog']",
                            # Radix UI (many modern portals)
                            "[data-radix-dialog-content]",
                            "[data-state='open'][role='dialog']",
                            # Generic patterns
                            "[class*='modal-content']:not([aria-hidden='true'])",
                            "[class*='modal-dialog']",
                            # Named portal modals
                            "#careerPortalModal",
                        ]
                        for _ms in _modal_sels:
                            try:
                                if ext_page.locator(_ms).first.is_visible(timeout=1500):
                                    _modal_appeared = True
                                    _log(task_input, f"External apply: modal appeared on same page ({_ms})", "info", "navigation")
                                    break
                            except Exception:
                                continue
                        if not _modal_appeared:
                            # URL change means navigate (not modal) — wait for form
                            if ext_page.url != _pre_cta_url:
                                try:
                                    ext_page.wait_for_load_state("networkidle", timeout=10000)
                                except Exception:
                                    pass
                            try:
                                ext_page.wait_for_selector("input, textarea, select", state="visible", timeout=9000)
                            except Exception:
                                pass
                    human_sleep(1.0, 1.8)
                    _dismiss_cookie_banner(ext_page, task_input)
                    _clicked_apply_cta = True
                    break
            except Exception:
                continue

        resume_text = task_input.get("resume_text", "")
        jd_text     = task_input.get("_current_jd_text", "")
        resume_path = task_input.get("resume_path", "")
        # Build flat profile dict (no internal _ keys, no complex objects)
        user_profile = {k: v for k, v in task_input.items()
                        if not k.startswith("_") and isinstance(v, (str, int, float))}

        # JS that returns all interactive form fields including radio/checkbox groups.
        # Accepts an optional rootSel parameter — when a modal/dialog is open, pass its
        # CSS selector so only the modal's fields are scanned (prevents filling background
        # page search forms, job listing filters, etc.).
        FIELD_JS = """(rootSel) => {
            // Scope to active modal when one is open, otherwise scan whole document
            const root = rootSel ? (document.querySelector(rootSel) || document) : document;
            const fields = [], seen = new Set();
            const isVisible = (el) => {
                // Skip truly hidden elements — display:none, visibility:hidden, or detached
                if (!el || el.offsetParent === null) return false;
                const s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            const getLabel = (el) => {
                if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
                if (el.id) {
                    const l = document.querySelector('label[for="' + el.id + '"]');
                    if (l) return l.innerText.replace(/\\s+/g,' ').trim();
                }
                const lid = el.getAttribute('aria-labelledby');
                if (lid) { const l = document.getElementById(lid); if (l) return l.innerText.replace(/\\s+/g,' ').trim(); }
                if (el.placeholder) return el.placeholder.trim();
                // Walk up ancestors (8 levels) to find an associated <label> element.
                // Handles Angular/custom components where the label is a cousin/uncle element,
                // not a direct parent or pointed-to via `for`. E.g. Unstop, Workday, iCIMS.
                let _anc = el.parentElement;
                for (let _i = 0; _i < 8 && _anc; _i++) {
                    // Direct <label> children of this ancestor that are not wrapping our input
                    for (const _ch of _anc.children) {
                        if (_ch.tagName === 'LABEL' && !_ch.contains(el)) {
                            const _t = (_ch.innerText||_ch.textContent||'').replace(/[*]/g,'').replace(/\\s+/g,' ').trim();
                            if (_t && _t.length < 100) return _t;
                        }
                    }
                    // Within first 4 ancestor levels also check nested <label> elements
                    if (_i < 4) {
                        for (const _lbl of _anc.querySelectorAll('label')) {
                            if (!_lbl.contains(el) && (!_lbl.htmlFor || _lbl.htmlFor === el.id)) {
                                const _t = (_lbl.innerText||_lbl.textContent||'').replace(/[*]/g,'').replace(/\\s+/g,' ').trim();
                                if (_t && _t.length < 100) return _t;
                            }
                        }
                    }
                    if (_anc.tagName === 'LABEL') {
                        const _t = (_anc.innerText||'').replace(/[*]/g,'').replace(/\\s+/g,' ').trim();
                        if (_t && _t.length < 100) return _t;
                    }
                    _anc = _anc.parentElement;
                }
                return '';
            };
            for (const el of root.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]), textarea, select'
            )) {
                if (!isVisible(el)) continue;  // skip hidden/invisible inputs
                const key = el.id || el.name || (el.type+'_'+fields.length);
                if (seen.has(key)) continue; seen.add(key);
                const tag = el.tagName.toLowerCase();
                // detect Oracle cx-select combobox vs plain text
                const role = el.getAttribute('role') || '';
                // detect Angular app-autocomplete (Unstop) — input with <ul.autocomplete-content> sibling
                const _isAC = !!(el.closest('app-autocomplete') ||
                    (el.parentElement && el.parentElement.querySelector('ul.autocomplete-content, ul[id*="_select_list"]')));
                const type = tag==='select'?'select':tag==='textarea'?'textarea':
                    (role==='combobox'?'combobox':(_isAC?'ac_dropdown':(el.type||'text')));
                const opts = type==='select' ? Array.from(el.options).filter(o=>o.value!=='').map(o=>o.text.trim()) : [];
                fields.push({ id: key, name: el.name||'', label: getLabel(el), type, options: opts,
                              required: el.required||el.getAttribute('aria-required')==='true',
                              placeholder: el.placeholder||'' });
            }
            const groups = {};
            for (const el of root.querySelectorAll('input[type="radio"], input[type="checkbox"]')) {
                if (!isVisible(el)) continue;  // skip hidden checkboxes/radios
                const g = el.name || ('grp_'+el.id);
                if (!g) continue;
                if (!groups[g]) groups[g]={ id:g, name:g, label:getLabel(el), type:el.type, options:[], required:el.required };
                const optLbl = el.labels&&el.labels[0] ? el.labels[0].innerText.trim()
                             : el.nextSibling&&el.nextSibling.textContent ? el.nextSibling.textContent.trim() : el.value;
                groups[g].options.push(optLbl||el.value);
            }
            for (const g of Object.values(groups)) { if (!seen.has(g.id)) fields.push(g); }
            // ── ARIA custom radio groups (role="radiogroup" + role="radio" divs) ──
            // Used by Lever, Ashby, and many modern ATS platforms instead of real <input type=radio>
            for (const grp of root.querySelectorAll('[role="radiogroup"]')) {
                if (!isVisible(grp)) continue;
                const gid = grp.getAttribute('data-ui') || grp.id || grp.getAttribute('name') || grp.getAttribute('data-test') || ('aria_rg_' + fields.length);
                const lblId = grp.getAttribute('aria-labelledby');
                const lblEl = lblId ? document.getElementById(lblId) : null;
                let label = lblEl ? lblEl.innerText.trim() : (grp.getAttribute('aria-label') || '');
                // When label is missing (Angular un-radio-group has no aria-labelledby),
                // walk up ancestors to find an associated <label> element
                if (!label) {
                    let _ganc = grp.parentElement;
                    for (let _gi = 0; _gi < 5 && _ganc && !label; _gi++) {
                        for (const _gch of _ganc.children) {
                            if (_gch.tagName === 'LABEL' && !_gch.contains(grp)) {
                                label = (_gch.innerText||_gch.textContent||'').replace(/[*]/g,'').replace(/\\s+/g,' ').trim();
                                if (label && label.length < 100) break;
                                else label = '';
                            }
                        }
                        _ganc = _ganc.parentElement;
                    }
                }
                if (!label) label = gid;  // final fallback: use name/data-test attribute
                // Options: standard [role="radio"] (Lever/Ashby) OR native inputs (Angular un-radio-group)
                const _ariaOpts = Array.from(grp.querySelectorAll('[role="radio"]'));
                const options = _ariaOpts.length > 0
                    ? _ariaOpts.map(opt => {
                        const lblIds = (opt.getAttribute('aria-labelledby') || '').split(' ');
                        const optLblEl = lblIds.map(id => document.getElementById(id)).find(el => el && el.innerText.trim());
                        return optLblEl ? optLblEl.innerText.trim()
                                       : (opt.getAttribute('aria-label') || opt.innerText.trim());
                    }).filter(Boolean)
                    : Array.from(grp.querySelectorAll('input[type="radio"]')).map(inp => {
                        const lbl = inp.id ? document.querySelector('label[for="'+inp.id+'"]') : null;
                        return lbl ? (lbl.innerText||lbl.textContent||'').replace(/[*]/g,'').replace(/\\s+/g,' ').trim() : inp.value;
                    }).filter(Boolean);
                const k = 'aria_rg_' + gid;
                if (!seen.has(k) && options.length > 0) {
                    seen.add(k);
                    seen.add(gid);  // block standard radio/checkbox dup for same group name
                    // Remove any already-added standard radio/checkbox group with this name
                    for (let _di = fields.length - 1; _di >= 0; _di--) {
                        if (fields[_di].name === gid && fields[_di].type !== 'aria_radio') {
                            fields.splice(_di, 1); break;
                        }
                    }
                    fields.push({ id: k, name: gid, label, type: 'aria_radio', options,
                                  required: grp.getAttribute('aria-required') === 'true' || grp.hasAttribute('required'),
                                  placeholder: '' });
                }
            }
            // ── Oracle Fusion / Taleo cx-select-pills (button-group pill selectors) ──
            for (const ul of root.querySelectorAll('ul.cx-select-pills-container')) {
                if (!isVisible(ul)) continue;
                const label = (ul.getAttribute('aria-label') || '').trim();
                if (!label) continue;
                const options = Array.from(ul.querySelectorAll('button .cx-select-pill-name'))
                                    .map(s => s.textContent.trim()).filter(Boolean);
                const key = 'cxpill_' + label.replace(/\\W+/g,'_').substring(0,40);
                if (!seen.has(key)) {
                    seen.add(key);
                    fields.push({ id: key, name: key, label, type: 'cx_pills', options, required: true, placeholder: '' });
                }
            }
            // ── Oracle Fusion / Taleo — hidden required T&C / legal-disclaimer checkboxes ──
            for (const inp of root.querySelectorAll('input[type="checkbox"].input-row__hidden-control')) {
                if (inp.checked) continue;  // already accepted
                const lbl = inp.id ? document.querySelector('label[for="'+inp.id+'"]') : inp.closest('label');
                const text = lbl ? (lbl.innerText||'').replace(/\\s+/g,' ').trim().substring(0,80) : (inp.id||'legal_checkbox');
                const key = 'legalchk_' + (inp.id || inp.name || 'chk');
                if (!seen.has(key)) {
                    seen.add(key);
                    fields.push({ id: inp.id||inp.name, name: inp.name||inp.id, label: text, type: 'legal_checkbox', options: [], required: true, placeholder: '' });
                }
            }
            // ── intl-tel-input phone country selector (Greenhouse, Lever, etc.) ──
            for (const btn of root.querySelectorAll('button.iti__selected-country')) {
                if (!isVisible(btn)) continue;
                const container = btn.closest('.iti');
                const phoneInp = container ? container.querySelector('input[type="tel"],input[type="phone"],input[name*="phone"],input[id*="phone"]') : null;
                const key = 'iti_phone_' + (phoneInp ? (phoneInp.id || phoneInp.name || 'phone') : 'phone');
                if (!seen.has(key)) {
                    seen.add(key);
                    fields.push({ id: key, name: key, label: 'Phone Country Code', type: 'iti_phone', options: [], required: false, placeholder: '' });
                }
            }
            return fields;
        }"""

        # JS that detects an active modal/dialog on the page and returns its CSS selector.
        # Covers: Bootstrap (.modal.show / .modal.in), Material UI (.MuiDialog-paper),
        # jQuery UI (.ui-dialog-content), Foundation (.reveal), Workday, iCIMS,
        # generic role="dialog", and custom portal containers.
        MODAL_DETECT_JS = """() => {
            const CANDIDATES = [
                // Role-based (most reliable — framework-agnostic)
                '[role="dialog"]:not([aria-hidden="true"])',
                '[role="alertdialog"]:not([aria-hidden="true"])',
                // Bootstrap / jQuery plugins
                '.modal.show',
                '.modal.fade.show',
                '.modal.in',
                '.modal.openModal',
                // Material UI / MUI
                '.MuiDialog-paper',
                '.MuiModal-root:not([aria-hidden="true"])',
                // jQuery UI
                '.ui-dialog-content',
                '.ui-dialog',
                // Foundation
                '.reveal',
                '.reveal-overlay > .reveal',
                // Workday
                '[data-automation-id*="modal"]',
                '[data-automation-id*="dialog"]',
                // iCIMS
                '.icims-form-modal',
                '.icims-modal',
                // Taleo / Oracle
                '.oracle-modal',
                // Radix UI (used by many modern portals)
                '[data-radix-dialog-content]',
                '[data-state="open"][role="dialog"]',
                // Generic patterns
                '[class*="modal"][class*="open"]:not([aria-hidden="true"])',
                '[class*="dialog"][class*="open"]:not([aria-hidden="true"])',
                '[class*="modal-content"]:not([aria-hidden="true"])',
                '[class*="modal-dialog"]',
                // Named portal modals
                '#careerPortalModal',
            ];
            for (const sel of CANDIDATES) {
                try {
                    const el = document.querySelector(sel);
                    if (!el) continue;
                    if (el.offsetParent === null) continue;  // hidden
                    const r = el.getBoundingClientRect();
                    if (r.width > 100 && r.height > 100) return sel;
                } catch(e) { continue; }
            }
            return null;
        }"""

        for step in range(8):
            # Check for CAPTCHA at start of each step (some ATSes inject Turnstile mid-flow)
            _handle_captcha(ext_page, task_input)

            # Detect if a modal/dialog is currently active — scope field scan to it so we
            # don't accidentally fill background page inputs (search bars, job filters, etc.)
            try:
                _modal_root_sel = ext_page.evaluate(MODAL_DETECT_JS)
            except Exception:
                _modal_root_sel = None
            if _modal_root_sel:
                _log(task_input, f"External apply step {step+1}: scoping field scan to modal ({_modal_root_sel})", "info", "ai_decision")

            fields      = ext_page.evaluate(FIELD_JS, _modal_root_sel)
            file_fields = [f for f in fields if f.get("type") == "file"]
            form_fields = [f for f in fields if f.get("type") not in ("file",)]

            # Full visible page text — gives Claude full context on what the form is asking.
            # Scope to modal when active so Claude sees the form's own text, not the whole page.
            try:
                if _modal_root_sel:
                    page_text = ext_page.evaluate(
                        """(sel) => { const el = document.querySelector(sel); return el ? (el.innerText || '') : (document.body && document.body.innerText) || ''; }""",
                        _modal_root_sel
                    )
                else:
                    page_text = ext_page.evaluate("() => (document.body && document.body.innerText) || ''")
            except Exception:
                page_text = ""

            if not form_fields and not file_fields:
                # Allow up to 3 retries for slow React/SPA portals (Greenhouse, Workday, etc.)
                if step < 3:
                    _log(task_input,
                         f"External apply: no fields yet (attempt {step+1}/3) — waiting for SPA render…",
                         "warning", "ai_decision")
                    try:
                        ext_page.wait_for_selector("input, textarea, select", state="visible", timeout=6000)
                    except Exception:
                        human_sleep(3.0, 4.0)
                    continue  # re-run FIELD_JS on next step iteration
                _log(task_input, f"External apply: no fields after {step+1} attempts — giving up", "warning", "ai_decision")
                break

            _log(task_input,
                 f"External apply step {step+1}: {len(form_fields)} fields, {len(file_fields)} file input(s)",
                 "info", "ai_decision")

            # Fill text/select/radio/checkbox fields via Claude with validation
            if form_fields:
                from automation.external_form_filler import ExternalFormFiller

                answers = _fill_fields(form_fields, user_profile, resume_text, jd_text, page_text=page_text)

                # Save latest answers so the notifier can include them in the alert
                task_input["_last_external_answers"] = dict(answers or {})

                # Create filler with proper validation
                filler = ExternalFormFiller(
                    ext_page,
                    log_fn=lambda msg, lvl="info": _log(task_input, f"External apply: {msg}", lvl, "ai_decision")
                )

                # Separate field handling
                for field in form_fields:
                    fid    = field.get("id", "")
                    fname  = field.get("name", "") or fid
                    ftype  = field.get("type", "text")

                    # ── Legal disclaimer / T&C checkboxes — always auto-accept ──────────
                    if ftype == "legal_checkbox":
                        try:
                            ext_page.evaluate(
                                """(id) => {
                                    const inp = document.getElementById(id)
                                             || document.querySelector('input[name="'+id+'"]');
                                    if (!inp || inp.checked) return;
                                    // Prefer the visual KO toggle button inside the label
                                    const lbl = inp.id
                                        ? document.querySelector('label[for="'+inp.id+'"]')
                                        : inp.closest('label');
                                    if (lbl) {
                                        const span = lbl.querySelector('.apply-flow-input-checkbox__button');
                                        if (span) { span.click(); return; }
                                        lbl.click(); return;
                                    }
                                    inp.click();
                                }""",
                                fid
                            )
                            _log(task_input,
                                 f"External apply: accepted legal/T&C checkbox '{field.get('label','?')[:50]}'",
                                 "info", "ai_decision")
                            human_sleep(0.2, 0.5)
                        except Exception as _lce:
                            _log(task_input, f"External apply: legal checkbox failed ({_lce})", "warning", "ai_decision")
                        continue

                    answer = str(answers.get(fid) or answers.get(fname) or "")
                    if not answer:
                        continue
                    # IDs/names with CSS-special chars ([ ] . # etc.) cannot be used in
                    # attribute selectors directly — always use JS getElementById/querySelector
                    def _has_css_special(s: str) -> bool:
                        return any(c in s for c in ("[", "]", ".", "#", ":", "(", ")", "!", "/"))

                    # Use validated fill for standard field types
                    if ftype in ("text", "textarea", "email", "tel", "number", "url", "search", "select", "radio", "checkbox"):
                        result = filler._fill_one(field, answer)
                        if result["settled"]:
                            _log(task_input, f"External apply: ✓ field '{field.get('label','?')[:40]}' settled", "info", "ai_decision")
                        else:
                            _log(task_input, f"External apply: ⚠ field '{field.get('label','?')[:40]}' failed: {result.get('error_msg', 'no error msg')}", "warning", "ai_decision")
                        human_sleep(0.1, 0.3)
                        continue

                    try:
                        if ftype == "aria_radio":
                            # ARIA custom radio group — two sub-patterns:
                            # 1. Standard: role="radiogroup" + role="radio" divs (Lever, Ashby, Taleo)
                            #    → click the [role="radio"] wrapper div
                            # 2. Angular: un-radio-group[role="radiogroup"] + native <input type="radio">
                            #    with <label class="un-label"> (Unstop etc.)
                            #    → click the <label> element (native input is visually hidden)
                            _filled = ext_page.evaluate(
                                """([name, val]) => {
                                    // Locate group by data-ui, id, name, data-test, or first radiogroup
                                    const grp = document.querySelector('[role="radiogroup"][data-ui="'+name+'"]')
                                             || document.getElementById(name)
                                             || document.querySelector('[role="radiogroup"][name="'+name+'"]')
                                             || document.querySelector('[role="radiogroup"][data-test="'+name+'"]')
                                             || document.querySelector('[role="radiogroup"]');
                                    if (!grp) return false;
                                    const vLo = val.trim().toLowerCase();
                                    // Strategy 1: standard [role="radio"] elements (Lever/Ashby/Taleo)
                                    for (const opt of grp.querySelectorAll('[role="radio"]')) {
                                        const txt = (opt.innerText || opt.textContent || '').trim().toLowerCase();
                                        if (txt === vLo || txt.startsWith(vLo) || vLo.startsWith(txt)) {
                                            if (opt.getAttribute('aria-checked') !== 'true') opt.click();
                                            return true;
                                        }
                                    }
                                    // Strategy 2: Angular un-radio-group — native input[type="radio"] + label
                                    for (const inp of grp.querySelectorAll('input[type="radio"]')) {
                                        const lbl = inp.id ? document.querySelector('label[for="'+inp.id+'"]') : null;
                                        const txt = lbl ? (lbl.innerText||lbl.textContent||'').replace(/[*]/g,'').replace(/\\s+/g,' ').trim().toLowerCase()
                                                        : inp.value.toLowerCase();
                                        if (txt === vLo || txt.startsWith(vLo) || vLo.startsWith(txt) || inp.value.toLowerCase() === vLo) {
                                            if (!inp.checked) {
                                                if (lbl) lbl.click();  // click label — native input may be visually hidden
                                                else inp.click();
                                            }
                                            return true;
                                        }
                                    }
                                    return false;
                                }""",
                                [fname, answer]
                            )
                            if _filled:
                                _log(task_input,
                                     f"External apply: ✓ ARIA radio '{field.get('label','?')[:40]}' = '{answer}'",
                                     "info", "ai_decision")
                            else:
                                _log(task_input,
                                     f"External apply: ⚠ ARIA radio '{field.get('label','?')[:40]}' — no option matched '{answer}'",
                                     "warning", "ai_decision")
                            human_sleep(0.2, 0.4)
                            continue
                        elif ftype == "ac_dropdown":
                            # Angular app-autocomplete (Unstop) — type to trigger suggestions,
                            # then click the matching <li> in the dropdown list.
                            _inp_el = ext_page.locator(f'[id="{fid}"]').first if (fid and not _has_css_special(fid)) else ext_page.locator(f'[name="{fname}"]').first
                            try:
                                _inp_el.fill(answer)
                                human_sleep(0.6, 1.0)  # wait for Angular to populate dropdown
                                _picked = ext_page.evaluate(
                                    """([id, name, val]) => {
                                        const inp = document.getElementById(id) || document.querySelector('[name="'+name+'"]');
                                        if (!inp) return false;
                                        const vLo = val.trim().toLowerCase();
                                        // Find the autocomplete <ul> — either sibling or in parent wrapper
                                        const wrapper = inp.closest('app-autocomplete, .autocomplete-wrapper') || inp.parentElement;
                                        const ul = wrapper && wrapper.querySelector('ul.autocomplete-content, ul[id*="_select_list"]');
                                        if (!ul) return false;
                                        // Find best matching <li> (skip "Cannot Find / Create One")
                                        for (const li of ul.querySelectorAll('li[title]:not(.create-new), li:not(.create-new)')) {
                                            const txt = (li.getAttribute('title') || li.innerText || li.textContent || '').trim();
                                            if (!txt) continue;
                                            if (txt.toLowerCase() === vLo || txt.toLowerCase().includes(vLo) || vLo.includes(txt.toLowerCase())) {
                                                li.click(); return true;
                                            }
                                        }
                                        // No match — click first available suggestion
                                        const first = ul.querySelector('li[title]:not(.create-new), li:not(.create-new)');
                                        if (first) { first.click(); return true; }
                                        return false;
                                    }""",
                                    [fid, fname, answer]
                                )
                                if _picked:
                                    _log(task_input, f"External apply: ✓ autocomplete '{field.get('label','?')[:40]}' = '{answer}'", "info", "ai_decision")
                                else:
                                    _log(task_input, f"External apply: ⚠ autocomplete '{field.get('label','?')[:40]}' — no dropdown match for '{answer}'", "warning", "ai_decision")
                            except Exception as _ace:
                                _log(task_input, f"External apply: autocomplete '{field.get('label','?')[:40]}' failed ({_ace})", "warning", "ai_decision")
                            human_sleep(0.2, 0.5)
                            continue
                        elif ftype == "iti_phone":
                            # intl-tel-input phone country selector (Greenhouse, Lever, etc.)
                            country_code = (user_profile.get("phone_country_code") or "us").lower()
                            ext_page.evaluate(
                                """([code]) => {
                                    const btn = document.querySelector('button.iti__selected-country');
                                    if (!btn) return;
                                    btn.click();
                                    return new Promise(resolve => setTimeout(() => {
                                        const li = document.querySelector('[data-country-code="'+code+'"]')
                                                || document.querySelector('[data-dial-code]')
                                                        ?.closest('ul')?.querySelector('li[id*="'+code+'"]');
                                        if (li) li.click();
                                        resolve();
                                    }, 350));
                                }""",
                                [country_code]
                            )
                            human_sleep(0.5, 0.8)
                            continue
                        elif ftype == "cx_pills":
                            # Oracle Fusion ATS pill-button selector
                            _filled = ext_page.evaluate(
                                """([label, val]) => {
                                    for (const ul of document.querySelectorAll('ul.cx-select-pills-container')) {
                                        const lbl = (ul.getAttribute('aria-label')||'').trim();
                                        if (lbl !== label) continue;
                                        for (const btn of ul.querySelectorAll('button.cx-select-pill-section')) {
                                            const txt = (btn.querySelector('.cx-select-pill-name')?.textContent||'').trim();
                                            const vLo = val.trim().toLowerCase();
                                            if (txt===val||txt.replace(/^\\s+/,'')===val
                                                ||txt.toLowerCase()===vLo
                                                ||txt.replace(/^\\s+/,'').toLowerCase()===vLo) {
                                                if (btn.getAttribute('aria-pressed')!=='true') btn.click();
                                                return true;
                                            }
                                        }
                                    }
                                    return false;
                                }""",
                                [field.get("label", ""), answer]
                            )
                            if not _filled:
                                _log(task_input,
                                     f"External apply: cx-pills '{field.get('label','?')[:40]}' — no pill matched '{answer}'",
                                     "warning", "ai_decision")
                            human_sleep(0.1, 0.3)
                            continue
                        elif ftype == "combobox":
                            # Oracle cx-select combobox: toggle open → pick option from listbox
                            try:
                                _tog = f"{fid}-toggle-button"
                                ext_page.evaluate(
                                    "(id) => { const b=document.getElementById(id); if(b) b.click(); }", _tog
                                )
                                human_sleep(0.4, 0.7)
                                _picked = ext_page.evaluate(
                                    """([cid, val]) => {
                                        const lb = document.getElementById(cid+'-listbox')
                                                || document.querySelector('[role="listbox"],[role="grid"]');
                                        if (!lb) return false;
                                        const vLo = val.toLowerCase();
                                        for (const opt of lb.querySelectorAll('[role="option"],[role="row"],[role="gridcell"]')) {
                                            const t = (opt.textContent||'').trim();
                                            if (t===val||t.toLowerCase()===vLo||t.toLowerCase().includes(vLo)) {
                                                opt.click(); return true;
                                            }
                                        }
                                        return false;
                                    }""",
                                    [fid, answer]
                                )
                                if not _picked and not _has_css_special(fid):
                                    # Fallback: type into input, autocomplete will suggest
                                    _cinp = ext_page.locator(f'[id="{fid}"]').first
                                    if _cinp.count():
                                        _cinp.fill(answer)
                                        human_sleep(0.5, 0.8)
                                        ext_page.evaluate(
                                            """([cid, val]) => {
                                                const lb = document.querySelector('[role="listbox"],[role="grid"]');
                                                if (!lb) return;
                                                const vLo = val.toLowerCase();
                                                for (const opt of lb.querySelectorAll('[role="option"],[role="row"],[role="gridcell"]')) {
                                                    const t=(opt.textContent||'').trim();
                                                    if (t===val||t.toLowerCase()===vLo||t.toLowerCase().includes(vLo)) {
                                                        opt.click(); return;
                                                    }
                                                }
                                            }""",
                                            [fid, answer]
                                        )
                            except Exception as _cbe:
                                _log(task_input, f"External apply: combobox '{field.get('label','?')[:40]}' failed ({_cbe})", "warning", "ai_decision")
                            human_sleep(0.1, 0.3)
                            continue
                        elif ftype == "select":
                            if fid and not fid.startswith("grp_") and not _has_css_special(fid):
                                _sel = f'[id="{fid}"]'
                            else:
                                _sel = f'[name="{fname}"]'
                            # Try by label text first (most robust for <select>), fallback to value
                            _filled = False
                            for _try in ("label", "value"):
                                try:
                                    if _try == "label":
                                        ext_page.locator(_sel).select_option(label=answer)
                                    else:
                                        ext_page.locator(_sel).select_option(value=answer)
                                    _filled = True
                                    break
                                except Exception:
                                    continue
                            if not _filled:
                                # Last resort: JS select by text
                                ext_page.evaluate(
                                    """([id, name, val]) => {
                                        const el = document.getElementById(id) ||
                                                   document.querySelector('[name="'+name+'"]');
                                        if (!el) return;
                                        for (const opt of el.options) {
                                            if (opt.text.trim()===val||opt.value===val) {
                                                el.value=opt.value;
                                                el.dispatchEvent(new Event('change',{bubbles:true}));
                                                break;
                                            }
                                        }
                                    }""",
                                    [fid, fname, answer]
                                )
                        elif ftype in ("radio", "checkbox"):
                            ext_page.evaluate(
                                """([name, val]) => {
                                    for (const inp of document.querySelectorAll('input[name="'+name+'"]')) {
                                        if (!inp.offsetParent) continue;  // skip hidden
                                        const lbl = inp.labels&&inp.labels[0] ? inp.labels[0].innerText.trim()
                                                  : inp.nextSibling ? (inp.nextSibling.textContent||'').trim() : inp.value;
                                        if (inp.value===val||lbl===val) { inp.click(); break; }
                                    }
                                }""",
                                [fname, answer]
                            )
                        else:
                            # Use JS fill for IDs with special chars; Playwright locator for clean IDs
                            if fid and not fid.startswith("grp_") and not _has_css_special(fid):
                                el = ext_page.locator(f'[id="{fid}"]').first
                                if el.count() > 0:
                                    el.fill(answer)
                            else:
                                ext_page.evaluate(
                                    """([id, name, val]) => {
                                        const el = document.getElementById(id) ||
                                                   document.querySelector('[name="'+name+'"]');
                                        if (el) {
                                            el.focus();
                                            el.value = val;
                                            el.dispatchEvent(new Event('input',{bubbles:true}));
                                            el.dispatchEvent(new Event('change',{bubbles:true}));
                                        }
                                    }""",
                                    [fid, fname, answer]
                                )
                        human_sleep(0.05, 0.2)
                    except Exception as _fe:
                        _log(task_input,
                             f"External apply: field '{field.get('label','?')}' fill failed ({_fe})",
                             "warning", "ai_decision")

            # Resume upload — detect visible file inputs directly (not relying on FIELD_JS alone)
            _file_inp_visible = False
            try:
                for _fi in ext_page.locator('input[type="file"]').all():
                    try:
                        if _fi.is_visible(timeout=300):
                            _file_inp_visible = True
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            if _file_inp_visible or file_fields:
                if resume_path and os.path.isfile(resume_path):
                    try:
                        ext_page.locator('input[type="file"]').first.set_input_files(resume_path)
                        human_sleep(1.0, 2.0)
                        _log(task_input, "External apply: resume uploaded", "success", "ai_decision")
                    except Exception as _ue:
                        _log(task_input, f"External apply: resume upload failed ({_ue})", "warning", "ai_decision")
                        if not task_input.get("_ext_stuck_reason"):
                            task_input["_ext_stuck_reason"] = f"Resume upload failed: {str(_ue)[:80]}"
                elif _file_inp_visible:
                    _log(task_input,
                         "External apply: resume upload field found but no resume file available",
                         "warning", "ai_decision")
                    if not task_input.get("_ext_stuck_reason"):
                        task_input["_ext_stuck_reason"] = (
                            "Resume upload required but no resume file is available — "
                            "please upload your resume manually"
                        )

            # ── Before advancing: auto-accept any remaining unchecked legal/T&C checkboxes ──
            # (catches checkboxes that FIELD_JS missed or that appeared after fills)
            try:
                _n_legal = ext_page.evaluate("""
                    () => {
                        let n = 0;
                        for (const inp of document.querySelectorAll('input[type="checkbox"].input-row__hidden-control')) {
                            if (inp.checked) continue;
                            const lbl = inp.id
                                ? document.querySelector('label[for="'+inp.id+'"]')
                                : inp.closest('label');
                            if (lbl) {
                                const span = lbl.querySelector('.apply-flow-input-checkbox__button');
                                if (span) { span.click(); n++; continue; }
                                lbl.click(); n++;
                            }
                        }
                        return n;
                    }
                """)
                if _n_legal:
                    _log(task_input, f"External apply: auto-accepted {_n_legal} legal/T&C checkbox(es)", "info", "ai_decision")
                    human_sleep(0.5, 1.0)
            except Exception:
                pass

            # ── Pre-submit: only validate when a submit button is actually present ──
            # Check if a submit button is visible on this step before doing validation
            _submit_btn_visible = False
            try:
                for _scheck_sel in ["button[type='submit']", "input[type='submit']",
                                    "button:has-text('Submit Application')", "button:has-text('Submit')",
                                    "button:has-text('Apply Now')"]:
                    try:
                        if ext_page.locator(_scheck_sel).first.is_visible(timeout=500):
                            _submit_btn_visible = True
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            if _submit_btn_visible:
                # If stuck reason already set (e.g. resume upload failed), bail out early
                if task_input.get("_ext_stuck_reason"):
                    _log(task_input,
                         f"External apply: aborting submit — stuck: {task_input['_ext_stuck_reason']}",
                         "warning", "navigation")
                    break

                # Scan for required text/select/textarea fields still empty on this step
                try:
                    _required_empty = ext_page.evaluate("""() => {
                        const empty = [];
                        for (const el of document.querySelectorAll(
                            'input[required]:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="file"]):not([type="checkbox"]):not([type="radio"]),'
                            + 'select[required], textarea[required]'
                        )) {
                            if (!el.offsetParent) continue;
                            if (!el.value || !el.value.trim()) {
                                const lbl = el.getAttribute('aria-label') ||
                                            el.getAttribute('placeholder') ||
                                            el.name || el.id || el.type;
                                empty.push(String(lbl).substring(0, 50));
                            }
                        }
                        // Also check for visible file inputs still empty (resume upload)
                        for (const fi of document.querySelectorAll('input[type="file"]')) {
                            if (!fi.offsetParent) continue;
                            if (!fi.files || fi.files.length === 0) {
                                const lbl = fi.getAttribute('aria-label') || fi.name || fi.id || 'resume';
                                empty.push('File upload: ' + String(lbl).substring(0, 40));
                            }
                        }
                        return empty;
                    }""")
                    if _required_empty:
                        _log(task_input,
                             f"External apply: {len(_required_empty)} required field(s) still empty: {_required_empty[:5]}",
                             "warning", "ai_decision")
                        if not task_input.get("_ext_stuck_reason"):
                            task_input["_ext_stuck_reason"] = (
                                f"Required fields not filled: {', '.join(str(r) for r in _required_empty[:3])}"
                            )
                        break  # exit step loop → manual notification triggered below
                except Exception:
                    pass  # if JS fails, proceed anyway

            # Try Submit — safe selectors only (avoid social-share/easy-apply buttons)
            _submitted = False
            for submit_sel in [
                "button[type='submit']", "input[type='submit']",
                "button:has-text('Submit Application')",
                "button:has-text('Submit')",
                "button:has-text('Apply Now')", "button:has-text('Apply')",
                "button:has-text('Send Application')", "button:has-text('Send')",
                "button:has-text('Complete Application')", "button:has-text('Finish')",
                "button:has-text('Done')", "button:has-text('Confirm')",
                "a:has-text('Submit Application')", "a:has-text('Apply Now')",
                "[data-testid='submit-application']", "[data-testid='submit']",
                "[class='apply-btn']", "button.submit-btn",
            ]:
                try:
                    btn = ext_page.locator(submit_sel).first
                    if btn.is_visible(timeout=800):
                        # Wait for disabled submit buttons to become enabled
                        try:
                            if btn.is_disabled():
                                btn.wait_for(state="enabled", timeout=15000)
                        except Exception:
                            pass
                        _pre_url = ext_page.url
                        human_click(ext_page, locator=btn)
                        human_sleep(2.5, 4.0)
                        _post_url = ext_page.url
                        # Verify actual submission via URL change or on-page confirmation
                        _confirmed = _post_url != _pre_url
                        # Even if URL changed, check for validation errors — many portals
                        # navigate to an error/next page when required fields are missing
                        if _confirmed:
                            try:
                                _has_validation_errors = ext_page.evaluate("""() => {
                                    const txt = ((document.body && document.body.innerText) || '').toLowerCase();
                                    const errPatterns = [
                                        'required field', 'field is required', 'please fill',
                                        'please complete', 'cannot be blank', 'please select a',
                                        'please upload', 'upload your resume', 'select a language',
                                        'please choose your language', 'missing required',
                                        'fill out all required', 'fill in all required'
                                    ];
                                    if (errPatterns.some(p => txt.includes(p))) return true;
                                    return !!(document.querySelector(
                                        'input[aria-invalid="true"], select[aria-invalid="true"], '
                                        + 'textarea[aria-invalid="true"], '
                                        + '.field-error:not([aria-hidden="true"]), '
                                        + '.error-message:not([aria-hidden="true"]), '
                                        + '[class*="has-error"]:not([aria-hidden="true"])'
                                    ));
                                }""")
                                if _has_validation_errors:
                                    _log(task_input,
                                         "⚠️ Submit: URL changed but validation errors on page — form incomplete",
                                         "warning", "navigation")
                                    if not task_input.get("_ext_stuck_reason"):
                                        task_input["_ext_stuck_reason"] = (
                                            "Validation errors after submit — required fields not filled "
                                            "(check resume upload, language selection, or other required fields)"
                                        )
                                    _confirmed = False
                            except Exception:
                                pass
                        if not _confirmed:
                            try:
                                _confirmed = bool(ext_page.evaluate(
                                    """() => {
                                        const txt = ((document.body && document.body.innerText) || '').toLowerCase();
                                        return txt.includes('thank you') ||
                                               txt.includes('application submitted') ||
                                               txt.includes('successfully submitted') ||
                                               txt.includes('application received') ||
                                               txt.includes('we received your application') ||
                                               txt.includes('application complete') ||
                                               !!document.querySelector('.confirmation,[class*=confirmation],[data-testid*=confirmation]');
                                    }"""
                                ))
                            except Exception:
                                pass
                        if _confirmed:
                            _log(task_input, "✅ External application submitted", "success", "applied")
                            task_input["_last_apply_type"] = "external"
                            ext_page.close()
                            return True
                        else:
                            _log(task_input,
                                 f"⚠️ Submit clicked but no confirmation detected (URL: {_post_url[:80]})",
                                 "warning", "ai_decision")
                            # Wait an extra 2s for slow SPA confirmation and re-check
                            human_sleep(2.0, 3.0)
                            try:
                                _recheck = bool(ext_page.evaluate(
                                    """() => {
                                        const txt = ((document.body && document.body.innerText) || '').toLowerCase();
                                        return txt.includes('thank you') ||
                                               txt.includes('application submitted') ||
                                               txt.includes('successfully submitted') ||
                                               txt.includes('application received') ||
                                               txt.includes('we received your application') ||
                                               txt.includes('application complete') ||
                                               txt.includes('your application has been') ||
                                               txt.includes('successfully applied') ||
                                               !!document.querySelector('.confirmation,[class*=confirmation],[data-testid*=confirmation],[class*=success-message]');
                                    }"""
                                ))
                                if _recheck:
                                    _log(task_input, "✅ External application submitted (delayed confirmation)", "success", "applied")
                                    task_input["_last_apply_type"] = "external"
                                    ext_page.close()
                                    return True
                            except Exception:
                                pass
                            # Don't return — may be multi-step; continue outer loop
                except Exception:
                    continue

            # Try Next / Continue
            advanced = False
            for next_sel in [
                "button:has-text('Next')", "button:has-text('Continue')",
                "button:has-text('Next Step')", "button:has-text('Proceed')",
                "button:has-text('Save & Continue')", "button:has-text('Save and Continue')",
                "button:has-text('Go to next')", "button[aria-label*='Next']",
                "button[aria-label*='Continue']", "a:has-text('Next')",
                "a:has-text('Continue')", "[data-testid*='next']",
                "[data-testid*='continue']",
            ]:
                try:
                    btn = ext_page.locator(next_sel).first
                    if btn.is_visible(timeout=800):
                        # Modal forms (e.g. Husky Technologies) use disabled Next buttons
                        # that only enable after required fields are filled + CAPTCHA passes.
                        # Poll up to 15s for the button to become enabled before clicking.
                        try:
                            if btn.is_disabled():
                                _log(task_input,
                                     f"External apply: Next button disabled — waiting up to 15s for enable…",
                                     "info", "navigation")
                                btn.wait_for(state="enabled", timeout=15000)
                        except Exception:
                            pass  # timed out or error — try clicking anyway
                        human_click(ext_page, locator=btn)
                        human_sleep(1.5, 2.5)
                        # Re-dismiss any cookie banner that might appear on new step
                        _dismiss_cookie_banner(ext_page, task_input)
                        _log(task_input, "External apply: moving to next step…", "info", "navigation")
                        advanced = True
                        break
                except Exception:
                    continue

            if not advanced:
                # Last resort: ask JS to find the most prominent non-back button
                # Strictly exclude social share buttons/links to avoid opening Facebook/Twitter
                try:
                    clicked = ext_page.evaluate("""() => {
                        const SOCIAL_SHARE = [
                            'facebook.com/sharer','twitter.com/share','linkedin.com/shareArticle',
                            'plus.google.com','pinterest.com/pin','mailto:','whatsapp://','t.me/'
                        ];
                        const SKIP_TEXT = ['back','cancel','close','decline','reject','dismiss',
                                           'no thanks','share','tweet','post','facebook','twitter',
                                           'linkedin','google','email','copy link','print'];
                        const candidates = Array.from(document.querySelectorAll(
                            'button[type="submit"], input[type="submit"], button.submit, button.next, button.continue'
                        )).filter(el => {
                            const txt = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
                            const href = (el.href || '').toLowerCase();
                            const rect = el.getBoundingClientRect();
                            return el.offsetParent !== null
                                && !el.disabled
                                && rect.width > 40 && rect.height > 20
                                && !SKIP_TEXT.some(w => txt.includes(w))
                                && !SOCIAL_SHARE.some(s => href.includes(s));
                        });
                        if (candidates.length > 0) { candidates[0].click(); return true; }
                        return false;
                    }""")
                    if clicked:
                        human_sleep(1.5, 2.5)
                        _dismiss_cookie_banner(ext_page, task_input)
                        _log(task_input, "External apply: advanced via JS fallback button", "info", "navigation")
                        advanced = True
                except Exception:
                    pass

            if not advanced:
                _log(task_input, "External apply: no Submit/Next found — cannot progress", "warning", "navigation")
                break

        _log(task_input, "External apply: could not complete submission", "warning", "navigation")
        try:
            from automation.notifier import notify_manual_required
            _ss = task_input.get("_session_stats", {})
            _applied_so_far = _ss.get("easy_applied", 0) + _ss.get("external_applied", 0)
            _manual_answers = dict(task_input.get("_last_external_answers") or {})
            if task_input.get("_tailored_resume_url"):
                _manual_answers["tailored_resume_pdf"] = task_input["_tailored_resume_url"]
            if task_input.get("_tailored_resume_text"):
                _manual_answers["tailored_resume_text_preview"] = task_input["_tailored_resume_text"][:500] + "…"
            notify_manual_required(
                task_input   = task_input,
                company      = task_input.get("_page_company") or task_input.get("company") or "Unknown Company",
                job_title    = task_input.get("_page_job_title") or "Unknown Position",
                apply_url    = apply_href,
                stuck_reason = task_input.get("_ext_stuck_reason") or "Could not complete submission — no Submit/Next button found",
                answers      = _manual_answers,
                linkedin_url = task_input.get("_current_job_url") or "",
                applied_today= _applied_so_far,
            )
            # Track in session stats
            _stats = task_input.setdefault("_session_stats", {})
            _stats["manual_needed"] = _stats.get("manual_needed", 0) + 1
            _stats.setdefault("manual_jobs", []).append({
                "company": task_input.get("_page_company") or task_input.get("company") or "Unknown",
                "title":   task_input.get("_page_job_title") or "Unknown",
                "url":     apply_href,
            })
            # Clear stuck reason so it doesn't bleed into the next job
            task_input.pop("_ext_stuck_reason", None)
        except Exception as _ne:
            print(f"  [NOTIFY] Notification send failed: {_ne}")

        # ── Wait for user to complete manually or skip ────────────
        _ext_is_rail = os.environ.get("TASK_RUNNER_ENV") == "railway"
        _ext_app_url = (os.environ.get("RAILWAY_STATIC_URL", "") or
                        os.environ.get("NEXT_PUBLIC_APP_URL", "")).rstrip("/")
        if _ext_is_rail and _ext_app_url:
            _ext_sid = task_input.get("session_id", "")
            _ext_vnc_path = f"../vnc-ws%3Fsession%3D{_ext_sid}" if _ext_sid else "../vnc-ws"
            _ext_vnc = f"{_ext_app_url}/novnc/?path={_ext_vnc_path}&autoconnect=1&resize=scale"
            _ext_wait_msg = (
                f"👆 <b>Action needed</b> — open the live browser to complete it:\n<a href=\"{_ext_vnc}\">{_ext_vnc}</a>\n\n"
                f"Reply <b>done</b> when submitted · <b>skip</b> to skip · <b>stop</b> to stop all\n"
                f"⏳ Waiting 10 min…"
            )
        else:
            _ext_wait_msg = (
                f"👆 <b>Action needed</b> — complete the application in the "
                f"<b>browser window on your screen</b>.\n\n"
                f"Reply <b>done</b> when submitted · <b>skip</b> to skip · <b>stop</b> to stop all\n"
                f"⏳ Waiting 10 min…"
            )
        _ext_result = _wait_for_resolution(ext_page, task_input, _ext_wait_msg,
                                           wait_minutes=10, check_url_exit=False)
        if _ext_result == "stop":
            task_input["_stop_requested"] = True
        elif _ext_result == "resolved":
            # User completed the form manually
            _log(task_input, "✅ External apply completed manually by user", "success", "external")
            _stats2 = task_input.setdefault("_session_stats", {})
            _stats2["external_applied"] = _stats2.get("external_applied", 0) + 1
            # Remove from manual_jobs list since it was actually completed
            _manual_list = _stats2.get("manual_jobs", [])
            if _manual_list:
                _stats2["manual_jobs"] = _manual_list[:-1]
                _stats2["manual_needed"] = max(0, _stats2.get("manual_needed", 1) - 1)
            ext_page.close()
            return True
        ext_page.close()
        return False

    except Exception as _e:
        _log(task_input, f"External apply error: {_e}", "error", "error")
        try:
            from automation.notifier import notify_manual_required
            _ss2 = task_input.get("_session_stats", {})
            _applied_so_far2 = _ss2.get("easy_applied", 0) + _ss2.get("external_applied", 0)
            _manual_answers2 = dict(task_input.get("_last_external_answers") or {})
            if task_input.get("_tailored_resume_url"):
                _manual_answers2["tailored_resume_pdf"] = task_input["_tailored_resume_url"]
            if task_input.get("_tailored_resume_text"):
                _manual_answers2["tailored_resume_text_preview"] = task_input["_tailored_resume_text"][:500] + "…"
            notify_manual_required(
                task_input   = task_input,
                company      = task_input.get("_page_company") or task_input.get("company") or "Unknown Company",
                job_title    = task_input.get("_page_job_title") or "Unknown Position",
                apply_url    = apply_href,
                stuck_reason = f"Automation error: {str(_e)[:120]}",
                answers      = _manual_answers2,
                linkedin_url = task_input.get("_current_job_url") or "",
                applied_today= _applied_so_far2,
            )
            _stats = task_input.setdefault("_session_stats", {})
            _stats["manual_needed"] = _stats.get("manual_needed", 0) + 1
            _stats.setdefault("manual_jobs", []).append({
                "company": task_input.get("_page_company") or task_input.get("company") or "Unknown",
                "title":   task_input.get("_page_job_title") or "Unknown",
                "url":     apply_href,
            })
            task_input.pop("_ext_stuck_reason", None)
            # Wait for user to complete manually or skip (same as the main stuck path)
            _exc_is_rail = os.environ.get("TASK_RUNNER_ENV") == "railway"
            _exc_app_url = (os.environ.get("RAILWAY_STATIC_URL", "") or
                            os.environ.get("NEXT_PUBLIC_APP_URL", "")).rstrip("/")
            if _exc_is_rail and _exc_app_url:
                _exc_sid = task_input.get("session_id", "")
                _exc_vnc_path = f"../vnc-ws%3Fsession%3D{_exc_sid}" if _exc_sid else "../vnc-ws"
                _exc_vnc = f"{_exc_app_url}/novnc/?path={_exc_vnc_path}&autoconnect=1&resize=scale"
                _exc_wait_msg = (
                    f"👆 <b>Action needed</b> — open the live browser:\n<a href=\"{_exc_vnc}\">{_exc_vnc}</a>\n\n"
                    f"Reply <b>done</b> when submitted · <b>skip</b> to skip · <b>stop</b> to stop all\n"
                    f"⏳ Waiting 10 min…"
                )
            else:
                _exc_wait_msg = (
                    f"👆 <b>Action needed</b> — complete the application in the "
                    f"<b>browser window on your screen</b>.\n\n"
                    f"Reply <b>done</b> when submitted · <b>skip</b> to skip · <b>stop</b> to stop all\n"
                    f"⏳ Waiting 10 min…"
                )
            try:
                _exc_result = _wait_for_resolution(ext_page, task_input, _exc_wait_msg,
                                                   wait_minutes=10, check_url_exit=False)
                if _exc_result == "stop":
                    task_input["_stop_requested"] = True
                elif _exc_result == "resolved":
                    _log(task_input, "✅ External apply completed manually by user", "success", "external")
                    _stats3 = task_input.setdefault("_session_stats", {})
                    _stats3["external_applied"] = _stats3.get("external_applied", 0) + 1
                    ext_page.close()
                    return True
            except Exception:
                pass
        except Exception:
            pass
        try:
            if ext_page:
                ext_page.close()
        except Exception:
            pass
        return False


def _li_tailor_and_persist(task_input: dict, jd_text: str) -> bool:
    """
    Run the tailoring refinement loop for the current job, then:
    - Set task_input["resume_path"] / ["_tailored_pdf"] to the tailored PDF
    - Set task_input["_tailored_resume_text"] for notifications
    - Upload PDF to Supabase Storage and save version record to DB
    Returns True if tailoring succeeded and resume_path was updated.
    """
    resume_path  = task_input.get("resume_path", "")
    resume_text  = task_input.get("resume_text", "")
    if not (resume_path or resume_text) or not jd_text.strip():
        return False

    company       = task_input.get("_page_company") or task_input.get("company") or ""
    role          = task_input.get("_page_job_title") or task_input.get("role") or task_input.get("keywords") or ""
    custom_prompt = task_input.get("tailor_custom_prompt", "")
    match_thresh  = int(task_input.get("match_threshold", 70))
    # Target must be strictly above smart-match threshold (and at least 75 %)
    target_score  = max(match_thresh + 5, int(task_input.get("tailor_target_score", 90)))

    source = resume_path if (resume_path and os.path.isfile(resume_path)) else resume_text
    if not source:
        return False

    _log(task_input,
         f"Tailoring resume for '{role or 'this role'}' at '{company or 'this company'}' "
         f"(target {target_score}%)…",
         "info", "tailor", {"company": company, "job_title": role, "target": target_score})
    try:
        from automation.resume_tailor import tailor_until_target
        tr = tailor_until_target(
            resume_source=source,
            jd_text=jd_text,
            target_score=target_score,
            custom_prompt=custom_prompt,
            company=company,
            role=role,
            max_attempts=3,
        )
        _log(task_input,
             f"Tailoring done — {tr.score_before:.0f}%→{tr.score_after:.0f}% "
             f"({'✅' if tr.score_after >= target_score else '⚠️ below target'})",
             "success" if tr.score_after >= target_score else "warning", "tailor",
             {"score": tr.score_after, "score_before": tr.score_before, "target": target_score,
              "company": company, "job_title": role})

        if tr.tailored_pdf_path and os.path.isfile(tr.tailored_pdf_path):
            task_input["resume_path"]            = tr.tailored_pdf_path
            task_input["_tailored_pdf"]          = tr.tailored_pdf_path
        task_input["_tailored_resume_text"]      = tr.tailored_text

        # ── Persist to Supabase ─────────────────────────────────────
        _uid = task_input.get("user_id", "")
        if _uid:
            try:
                from api_client import save_resume_version, upload_file_to_storage
                _slug = lambda s: re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")[:25]
                _vname = (f"{_slug(company)}_{_slug(role)}" if (company or role) else "tailored").strip("_") or "tailored"
                # Upload PDF to storage
                _file_url = ""
                if tr.tailored_pdf_path and os.path.isfile(tr.tailored_pdf_path):
                    _fname = f"{_vname}.pdf"
                    _file_url = upload_file_to_storage(tr.tailored_pdf_path, _uid, _fname)
                _ver_id = save_resume_version(
                    user_id=_uid, version_name=_vname,
                    original_text=tr.original_text, tailored_text=tr.tailored_text,
                    tailored_content={"bullets": tr.tailored_bullets, "summary": tr.tailored_summary,
                                      "improvements": tr.improvements, "added_keywords": tr.added_keywords,
                                      "missing_skills": tr.missing_skills, "score_before": tr.score_before,
                                      "score_after": tr.score_after, "ats_score": tr.ats_score},
                    ats_score=tr.ats_score, missing_skills=tr.missing_skills, file_url=_file_url,
                )
                if _ver_id:
                    task_input["_resume_version_id"] = _ver_id   # passed to record_application
                if _file_url:
                    task_input["_tailored_resume_url"] = _file_url
                _log(task_input, f"Tailored resume saved: '{_vname}'" + (f" (PDF: {_file_url[:60]})" if _file_url else ""),
                     "info", "tailor", {"version_name": _vname, "file_url": _file_url})
            except Exception as _sve:
                _log(task_input, f"Resume save failed ({_sve})", "warning", "tailor")
        return True
    except Exception as _te:
        _log(task_input, f"Tailoring failed ({_te}) — using original resume", "warning", "tailor")
        return False


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
        # ── Extract job title & company from page ────────────────
        _page_job_title = ""
        # Always start fresh — do NOT seed from task_input["company"] here.
        # That key is shared across all jobs in the loop, so seeding from it
        # causes the previous job's company to bleed into this job.
        # company_hint fallback is applied AFTER all strategies fail.
        _page_company = ""

        # Strategy 1: CSS selectors (try each, stop at first hit)
        try:
            for _title_sel in [
                # Current LinkedIn DOM (2024-2026)
                "h1.job-details-jobs-unified-top-card__job-title",
                "h1.job-details-jobs-unified-top-card__job-title--clickable",
                "div.job-details-jobs-unified-top-card__job-title h1",
                "h1[class*='job-details'][class*='title']",
                "h1[class*='unified-top-card'][class*='title']",
                # Legacy selectors
                "h1.t-24.t-bold", "h1.t-24",
                "h1.jobs-unified-top-card__job-title",
                "h1[class*='topcard__title']", "h1.job-title",
                "h2.t-24",
                # Broad fallback — grab any h1 on job page
                "div.job-view-layout h1",
                "main h1",
                "h1",
            ]:
                _title_el = page.locator(_title_sel).first
                if _title_el.count() > 0:
                    _t = (_title_el.text_content() or "").strip()[:120]
                    # Skip generic/nav h1s (very short or LinkedIn brand header)
                    if _t and len(_t) > 2 and "linkedin" not in _t.lower():
                        _page_job_title = _t
                        break
        except Exception:
            pass

        if not _page_company:
            try:
                for _co_sel in [
                    # Current LinkedIn DOM (2024-2026)
                    "div.job-details-jobs-unified-top-card__company-name a",
                    "div.job-details-jobs-unified-top-card__primary-description-container a",
                    "span.job-details-jobs-unified-top-card__company-name",
                    "a[class*='job-details'][class*='company']",
                    # Legacy
                    "a.ember-view.t-black.t-normal span",
                    "span.jobs-unified-top-card__company-name",
                    "a[class*='topcard__org-name-link']",
                    "a[class*='company-name']",
                    # Broad fallback
                    "div.jobs-unified-top-card a.app-aware-link",
                ]:
                    _co_el = page.locator(_co_sel).first
                    if _co_el.count() > 0:
                        _c = (_co_el.text_content() or "").strip()[:80]
                        if len(_c) >= 2:  # guard against '.' or single-char junk
                            _page_company = _c
                            break
            except Exception:
                pass

        # Strategy 2: JavaScript DOM walk — resilient to class-name changes
        if not _page_job_title or not _page_company:
            try:
                _extracted = page.evaluate("""() => {
                    // Title: look for h1 elements that aren't navigation/brand
                    let title = '';
                    for (const h1 of document.querySelectorAll('h1')) {
                        const t = (h1.innerText || '').trim();
                        if (t.length > 2 && t.length < 150 && !t.toLowerCase().includes('linkedin')) {
                            title = t;
                            break;
                        }
                    }
                    // Company strategy A: aria-label="Company, Concentrix."
                    // LinkedIn always puts this on the company logo wrapper div
                    let company = '';
                    const companyEl = document.querySelector('[aria-label^="Company,"]');
                    if (companyEl) {
                        const lbl = companyEl.getAttribute('aria-label') || '';
                        const parsed = lbl.replace(/^Company,\\s*/i, '').replace(/\\.?\\s*$/, '').trim();
                        if (parsed.length >= 2) company = parsed;
                    }
                    // Company strategy B: img alt / svg aria-label "Company logo for, ..."
                    if (!company) {
                        for (const el of document.querySelectorAll('img[alt], svg[aria-label], img[aria-label]')) {
                            const alt = el.getAttribute('alt') || el.getAttribute('aria-label') || '';
                            const m = alt.match(/company logo for[,\\s]+(.+?)(\\.)?\\s*$/i);
                            if (m && m[1].trim().length >= 2) { company = m[1].trim(); break; }
                        }
                    }
                    // Company strategy C: first /company/ link text (min 2 chars)
                    if (!company) {
                        for (const a of document.querySelectorAll('a[href*="/company/"]')) {
                            const t = (a.innerText || '').trim();
                            if (t && t.length >= 2 && t.length < 100) { company = t; break; }
                        }
                    }
                    // NOTE: No DOM-walk title fallback here — it incorrectly picks up
                    // company names from the sidebar job list as job titles.
                    // Strategy 3 (tab title) reliably handles the title-missing case.
                    return {title, company};
                }""")
                if not _page_job_title and _extracted.get("title"):
                    _t = _extracted["title"].strip()
                    if len(_t) >= 2:
                        _page_job_title = _t[:120]
                if not _page_company and _extracted.get("company"):
                    _c = _extracted["company"].strip()
                    if len(_c) >= 2:
                        _page_company = _c[:80]
            except Exception:
                pass

        # Strategy 3: Parse browser tab title — LinkedIn formats it as
        #   "Job Title at Company | LinkedIn" or "Company: Job Title | LinkedIn"
        if not _page_job_title or not _page_company:
            try:
                tab_title = page.title() or ""
                # "Email Developer at WPP Production India | LinkedIn"
                import re as _re
                m = _re.match(r"^(.+?) at (.+?)\s*[\|·—]\s*LinkedIn", tab_title)
                if m:
                    if not _page_job_title:
                        _t = m.group(1).strip()
                        if len(_t) >= 2:
                            _page_job_title = _t[:120]
                    if not _page_company:
                        _c = m.group(2).strip()
                        if len(_c) >= 2:
                            _page_company = _c[:80]
                elif " | " in tab_title:
                    # Fallback: first segment before " | "
                    seg = tab_title.split(" | ")[0].strip()
                    if not _page_job_title and len(seg) >= 2:
                        _page_job_title = seg[:120]
            except Exception:
                pass

        # Last-resort fallback: use company_hint from task_input if all strategies failed
        if not _page_company:
            _page_company = task_input.get("company", "")

        # Store in task_input for downstream use (logs, tailoring, report, etc.)
        # NOTE: mutate directly — do NOT use dict(task_input) copy here or
        # the caller's task_input won't see these values when building the report.
        if _page_job_title:
            task_input["_page_job_title"] = _page_job_title
        # Always overwrite _page_company so the report always gets the fresh value
        # for this specific job (prevents previous job's company from bleeding through).
        task_input["_page_company"] = _page_company
        # Only update the shared "company" hint if it wasn't already set by the caller
        if _page_company and not task_input.get("company"):
            task_input["company"] = _page_company

        _log(task_input, f"Reviewing: {_page_job_title or 'untitled'} at {_page_company or 'unknown company'}",
             "info", "navigation", {"job_title": _page_job_title, "company": _page_company, "url": job_url})
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
                    task_input["_last_match_score"] = score
                except Exception as _me:
                    _log(task_input, f"Match scoring failed ({_me}) — applying anyway", "warning", "ai_decision")
            else:
                _log(task_input, "Smart match skipped — no resume text available", "warning", "ai_decision")

        # Store jd_text in task_input so _fill_additional_questions can use it for AI cover note
        if jd_text:
            task_input["_current_jd_text"] = jd_text

        # ── Detect apply button type and route per user preference ──────────
        _linkedin_apply_types = task_input.get("linkedin_apply_types", "easy_apply_only")

        # Always look for Easy Apply button
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

        # Look for external "Apply on company website" button
        external_apply_href = None
        if _linkedin_apply_types in ("external_only", "both"):
            for ext_sel in [
                "a[aria-label='Apply on company website']",
                "a[aria-label*='Apply on company']",
                "a[aria-label='Apply'][target='_blank']",
            ]:
                try:
                    btn = page.locator(ext_sel).first
                    if btn.is_visible(timeout=2000):
                        _href = btn.get_attribute("href") or ""
                        if _href:
                            # Unwrap LinkedIn safety/tracking redirect to get real company URL
                            _href = _unwrap_linkedin_apply_url(_href)
                            external_apply_href = _href
                            print(f"  [LINKEDIN] External apply button found: {ext_sel} → {_href[:80]}")
                            break
                except Exception:
                    continue

        # Route based on preference
        if _linkedin_apply_types == "easy_apply_only":
            if easy_apply_btn is None:
                _log(task_input, "No Easy Apply button — skipping (preference: Easy Apply only)", "skip", "skip")
                return False
            # Fall through to Easy Apply flow below
        elif _linkedin_apply_types == "external_only":
            if not external_apply_href:
                _log(task_input, "No external Apply button — skipping (preference: External Apply only)", "skip", "skip")
                return False
            # ── Tailor before external apply ──────────────────────────
            if task_input.get("tailor_resume") and jd_text:
                _li_tailor_and_persist(task_input, jd_text)
            task_input["_current_job_url"] = job_url
            return _apply_external_job(page, external_apply_href, task_input)
        else:  # "both" — prefer Easy Apply, fall back to external
            if easy_apply_btn is None and external_apply_href:
                # ── Tailor before external apply ──────────────────────
                if task_input.get("tailor_resume") and jd_text:
                    _li_tailor_and_persist(task_input, jd_text)
                task_input["_current_job_url"] = job_url
                return _apply_external_job(page, external_apply_href, task_input)
            elif easy_apply_btn is None:
                _log(task_input, "No apply button found — skipping", "skip", "skip")
                return False
            # else: easy_apply_btn found, fall through to Easy Apply flow

        human_click(page, locator=easy_apply_btn)
        idle_jiggle(page, duration=random.uniform(3.0, 5.5))   # jiggle while modal loads

        # ── Easy Apply: tailor only if a resume upload field exists in the modal ──
        if task_input.get("tailor_resume") and jd_text:
            _li_has_upload = False
            try:
                human_sleep(1.0, 2.0)   # wait briefly for modal DOM to settle
                for _usel in [
                    "input[id*='jobs-document-upload-file-input-upload-resume']",
                    "input[type='file'][name*='resume']",
                    "input[type='file']",
                ]:
                    try:
                        if page.locator(_usel).first.count() > 0:
                            _li_has_upload = True
                            break
                    except Exception:
                        pass
            except Exception:
                pass
            if _li_has_upload:
                _li_tailor_and_persist(task_input, jd_text)
            else:
                _log(task_input, "Easy Apply: no resume upload field — applying with original resume", "info", "tailor")

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
                        task_input["_last_apply_type"] = "easy_apply"
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
                    task_input["_last_apply_type"] = "easy_apply"
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

            # No button found — notify user and wait for them to fix it or skip
            print(f"  [LINKEDIN] No actionable button on step {step + 1} — notifying user")
            _ea_job_title = task_input.get("_page_job_title") or "Unknown Position"
            _ea_company   = task_input.get("_page_company")   or "Unknown Company"
            _ea_is_rail   = os.environ.get("TASK_RUNNER_ENV") == "railway"
            _ea_app_url   = (os.environ.get("RAILWAY_STATIC_URL", "") or
                             os.environ.get("NEXT_PUBLIC_APP_URL", "")).rstrip("/")
            if _ea_is_rail and _ea_app_url:
                _ea_sid = task_input.get("session_id", "")
                _ea_vnc_path = f"../vnc-ws%3Fsession%3D{_ea_sid}" if _ea_sid else "../vnc-ws"
                _ea_vnc = f"{_ea_app_url}/novnc/?path={_ea_vnc_path}&autoconnect=1&resize=scale"
                _ea_msg = (
                    f"⚠️ <b>Easy Apply Stuck — Step {step + 1}</b>\n\n"
                    f"<b>{_ea_company}</b> — {_ea_job_title}\n\n"
                    f"Bot couldn't find the Next / Submit button.\n"
                    f"👉 <b>Open the live browser to fix it:</b>\n<a href=\"{_ea_vnc}\">{_ea_vnc}</a>\n\n"
                    f"Reply <b>done</b> when you've submitted · <b>skip</b> to skip · <b>stop</b> to stop all\n"
                    f"⏳ Waiting 10 min…"
                )
            else:
                _ea_msg = (
                    f"⚠️ <b>Easy Apply Stuck — Step {step + 1}</b>\n\n"
                    f"<b>{_ea_company}</b> — {_ea_job_title}\n\n"
                    f"Bot couldn't find the Next / Submit button.\n"
                    f"👉 Complete the application in the <b>browser window on your screen</b>.\n\n"
                    f"Reply <b>done</b> when you've submitted · <b>skip</b> to skip · <b>stop</b> to stop all\n"
                    f"⏳ Waiting 10 min…"
                )
            _log(task_input,
                 f"⚠️ Easy Apply stuck on step {step + 1} for {_ea_company} — {_ea_job_title}",
                 "warning", "stuck")
            _ea_result = _wait_for_resolution(page, task_input, _ea_msg,
                                              wait_minutes=10, check_url_exit=False)
            if _ea_result == "stop":
                task_input["_stop_requested"] = True
                break
            if _ea_result == "resolved":
                # User manually submitted — check if we're off the form modal
                try:
                    _ea_url = page.url or ""
                    _still_modal = page.locator(
                        "div.jobs-easy-apply-modal, div[data-test-modal]"
                    ).first.is_visible(timeout=2000)
                    if not _still_modal:
                        task_input["_last_apply_type"] = "easy_apply"
                        _close_modal(page)
                        return True
                except Exception:
                    pass
                continue  # User may have clicked Next — re-run the button check loop
            break  # skip / timeout — give up on this job

    except Exception as e:
        print(f"  [LINKEDIN] Apply error on {job_url}: {e}")
        import traceback; traceback.print_exc()

    _close_modal(page)
    # Clean up temp tailored PDF (it lives in the versioned output dir — keep it)
    return False
