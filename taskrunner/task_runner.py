import sys
import os

# Allow imports from the project root (automation/ package lives there)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from automation.linkedin import apply_linkedin_jobs
from automation.naukri import apply_naukri_jobs


def run_task(task: dict) -> dict:
    """
    Execute the task based on its type.
    Returns an output dict that gets saved to tasks.output in Supabase.
    Raises an exception on failure so main.py can mark it FAILED.
    """
    # ── Railway guard: local agent must never pick up cloud tasks ───
    # On the Railway container (TASK_RUNNER_ENV=railway) we intentionally DO run them.
    if task.get("execution_mode") == "railway" and os.environ.get("TASK_RUNNER_ENV") != "railway":
        print(f"  [RUNNER] Skipping task {task.get('id', '')} — execution_mode=railway (handled by cloud)")
        return {"skipped": True, "reason": "railway_execution_mode"}

    from api_client import check_quota, fetch_user_email

    task_type  = task.get("type", "UNKNOWN")
    task_id    = task.get("id", "")
    task_input = dict(task.get("input") or {})
    # Inject user_id and task_id so automation layers can push live logs
    task_input["user_id"] = task.get("user_id", "")
    task_input["task_id"] = task_id
    user_id = task_input["user_id"]

    # ── Inject Telegram notification config ──────────────────────────────────
    # Bot token is a server env var (shared for all users).
    # Chat ID is per-user, stored in user_profiles.
    if not task_input.get("telegram_bot_token"):
        task_input["telegram_bot_token"] = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if user_id and not task_input.get("telegram_chat_id"):
        from api_client import fetch_user_profile
        profile = fetch_user_profile(user_id)
        chat_id = profile.get("telegram_chat_id", "")
        if chat_id:
            task_input["telegram_chat_id"] = chat_id

    print(f"  [RUNNER] type={task_type}  user_id={user_id}")

    # ── Super admin bypass (by email — matches lib/api-auth.ts) ──
    SUPER_ADMIN_EMAILS = [
        "kaviyasaravanan01@gmail.com",
        "anandanathurelangovan94@gmail.com",
    ]
    user_email = fetch_user_email(user_id) if user_id else ""
    is_super_admin = user_email.lower() in SUPER_ADMIN_EMAILS

    # Propagate admin flag so sub-handlers can enforce correct limits
    task_input["_is_super_admin"] = is_super_admin

    # ── Quota gate ────────────────────────────────────────────
    quota_map = {
        "AUTO_APPLY":       "auto_apply",
        "TAILOR_AND_APPLY": "semi_auto",
        "URL_APPLY":        "url_apply",
        "TAILOR_RESUME":    "ai_tailor",
        "GMAIL_DAILY_CHECK":"gmail_scan",
    }
    action_type = quota_map.get(task_type)
    if action_type and user_id and not is_super_admin:
        quota = check_quota(user_id, action_type)
        if not quota.get("allowed", True):
            raise ValueError(
                f"Daily quota exceeded for {action_type} "
                f"({quota.get('used', '?')}/{quota.get('limit', '?')})"
            )

    if task_type == "AUTO_APPLY":
        return _handle_auto_apply(task_input)
    elif task_type == "TAILOR_AND_APPLY":
        return _handle_tailor_and_apply(task_input)
    elif task_type == "URL_APPLY":
        return _handle_url_apply(task_input)
    elif task_type == "TAILOR_RESUME":
        return _handle_tailor_resume(task_input)
    elif task_type == "GMAIL_DAILY_CHECK":
        return _handle_gmail_daily_check(task_input)
    else:
        raise ValueError(f"Unknown task type: {task_type}")


def _handle_tailor_and_apply(task_input: dict) -> dict:
    """
    TAILOR_AND_APPLY: same as AUTO_APPLY but sets tailor_resume=True so that
    linkedin.py/naukri.py will tailor the uploaded resume to each JD before applying.
    """
    enriched = dict(task_input)
    enriched["tailor_resume"] = True
    return _handle_auto_apply(enriched)


def _handle_url_apply(task_input: dict) -> dict:
    """
    URL_APPLY: user provides specific LinkedIn / Naukri job URLs.
    For each URL the bot:
      1. Opens the job page and extracts the JD
      2. If tailor_resume=True AND score < match_threshold (default 70), tailors
         the resume to match the JD (preserving source PDF style)
      3. Applies using the (tailored) resume

    task_input extra keys:
        manual_urls   list[str]  explicit job page URLs (LinkedIn or Naukri)
        tailor_resume bool       if True, tailor resume per-JD before applying
        match_threshold int      score below which tailoring is triggered (default 70)
    """
    from api_client import fetch_latest_resume, fetch_user_tier

    manual_urls = task_input.get("manual_urls", [])
    if not manual_urls:
        return {"applied_count": 0, "skipped_count": 0,
                "message": "No URLs provided for URL_APPLY task"}

    user_id        = task_input.get("user_id", "")
    is_super_admin = task_input.get("_is_super_admin", False)
    task_input     = dict(task_input)

    # ── Per-tier max_apply limits (same tiers as AUTO_APPLY) ──────────
    _TIER_MAX_APPLY = {
        "free": 10, "starter": 30, "pro": 50, "premium": 50, "enterprise": 50,
    }
    tier = fetch_user_tier(user_id) if user_id else "free"
    tier_limit = 100 if is_super_admin else _TIER_MAX_APPLY.get(tier, 10)
    requested_max = int(task_input.get("max_apply", tier_limit))
    task_input["max_apply"] = min(requested_max, tier_limit)
    print(f"  [URL_APPLY] Tier={tier}  max_apply={task_input['max_apply']}/{tier_limit}")

    # ── Attach resume URL / text (same as AUTO_APPLY) ─────────────────
    if user_id and not task_input.get("resume_url"):
        resume = fetch_latest_resume(user_id)
        if resume:
            content = resume.get("content") or {}
            task_input["resume_url"]      = content.get("file_url", "")
            task_input["resume_filename"] = content.get("file_name", resume.get("title", "resume.pdf"))
            task_input["resume_id"]       = resume.get("id", "")   # for application tracking
            if resume.get("parsed_text") and not task_input.get("resume_text"):
                task_input["resume_text"] = resume["parsed_text"]
            print(f"  [URL_APPLY] Resume: {task_input['resume_filename']}")

    # ── AI company-site quota ──────────────────────────────────────────
    if "_ai_company_site_limit" not in task_input:
        task_input["_ai_company_site_limit"] = 2 if tier == "free" else 999
    task_input.setdefault("_ai_company_site_used", 0)

    # ── Split URLs by platform ─────────────────────────────────────────
    linkedin_urls = [u for u in manual_urls if "linkedin.com" in u.lower()]
    naukri_urls   = [u for u in manual_urls if "naukri.com"   in u.lower()]
    other_urls    = [u for u in manual_urls
                     if u not in linkedin_urls and u not in naukri_urls]
    if other_urls:
        print(f"  [URL_APPLY] ⚠️  {len(other_urls)} URL(s) are not LinkedIn or Naukri and will be skipped: {other_urls[:3]}")

    total_applied = 0
    total_skipped = 0
    messages: list[str] = []
    full_report: list[dict] = []

    if linkedin_urls:
        li_input = dict(task_input)
        li_input["platform"]      = "linkedin"
        li_input["specific_urls"] = linkedin_urls
        print(f"  [URL_APPLY] Processing {len(linkedin_urls)} LinkedIn URL(s)…")
        result = apply_linkedin_jobs(li_input)
        total_applied += result.get("applied_count", 0)
        total_skipped += result.get("skipped_count", 0)
        full_report.extend(result.get("report", []))
        messages.append(f"LinkedIn: {result.get('applied_count', 0)} applied")

    if naukri_urls:
        nk_input = dict(task_input)
        nk_input["platform"]      = "naukri"
        nk_input["specific_urls"] = naukri_urls
        print(f"  [URL_APPLY] Processing {len(naukri_urls)} Naukri URL(s)…")
        result = apply_naukri_jobs(nk_input)
        total_applied += result.get("applied_count", 0)
        total_skipped += result.get("skipped_count", 0)
        full_report.extend(result.get("report", []))
        messages.append(f"Naukri: {result.get('applied_count', 0)} applied")

    return {
        "applied_count": total_applied,
        "skipped_count": total_skipped,
        "message": " | ".join(messages) if messages else "No URLs processed",
        "report": full_report,
    }


def _handle_tailor_resume(task_input: dict) -> dict:
    """Call AI to tailor a resume to a JD, then save the version to Supabase."""
    import json, requests
    from automation.ai_client import tailor_resume
    from api_client import SUPABASE_URL, HEADERS

    resume_text  = task_input.get("resume_text", "")
    jd_text      = task_input.get("jd_text", "")
    version_name = task_input.get("version_name", "AI_Tailored_v1")
    user_id      = task_input.get("user_id", "")
    resume_id    = task_input.get("resume_id")
    job_id       = task_input.get("job_id")

    if not resume_text or not jd_text:
        raise ValueError("Both resume_text and jd_text are required for TAILOR_RESUME")

    result = tailor_resume(resume_text, jd_text)

    if user_id:
        payload = {
            "user_id":       user_id,
            "version_name":  version_name,
            "original_text": resume_text,
            "tailored_text": result["tailored_text"],
            "tailored_content": result,
            "ats_score":     result.get("ats_score"),
            "missing_skills": [],
        }
        if resume_id:
            payload["resume_id"] = resume_id
        if job_id:
            payload["job_id"] = job_id
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/resume_versions",
            headers={**HEADERS, "Prefer": "return=representation"},
            json=payload,
        )
        if resp.ok:
            saved = resp.json()
            result["version_id"] = saved[0].get("id") if saved else None

    return result


def _handle_auto_apply(task_input: dict) -> dict:
    """Fetch resume from Supabase then launch LinkedIn browser automation."""
    from api_client import fetch_latest_resume, fetch_user_tier

    platform       = task_input.get("platform", "linkedin")
    user_id        = task_input.get("user_id", "")
    is_super_admin = task_input.get("_is_super_admin", False)

    # ── Per-tier max_apply limits ──────────────────────────────────
    # Free=10, Starter=30, Pro/Premium=50, Enterprise=50, Admin=100
    _TIER_MAX_APPLY = {
        "free":       10,
        "starter":    30,
        "pro":        50,
        "premium":    50,
        "enterprise": 50,
    }
    tier = "free"
    if user_id:
        tier = fetch_user_tier(user_id)
    tier_limit = 100 if is_super_admin else _TIER_MAX_APPLY.get(tier, 10)

    # AI company-site apply quota (free=2, paid=unlimited)
    if "_ai_company_site_limit" not in task_input:
        task_input["_ai_company_site_limit"] = 2 if tier == "free" else 999
    task_input.setdefault("_ai_company_site_used", 0)

    # Cap user-requested max_apply at the tier limit — never exceed it
    requested_max = int(task_input.get("max_apply", tier_limit))
    task_input["max_apply"] = min(requested_max, tier_limit)
    print(f"  [RUNNER] Tier={tier}  max_apply={task_input['max_apply']}/{tier_limit}"
          + (" (admin)" if is_super_admin else ""))

    # Attach resume URL and parsed text if not already set
    if user_id and not task_input.get("resume_url"):
        resume = fetch_latest_resume(user_id)
        if resume:
            content = resume.get("content") or {}
            task_input["resume_url"]      = content.get("file_url", "")
            task_input["resume_filename"] = content.get("file_name", resume.get("title", "resume.pdf"))
            task_input["resume_id"]       = resume.get("id", "")   # for application tracking
            if resume.get("parsed_text") and not task_input.get("resume_text"):
                task_input["resume_text"] = resume["parsed_text"]
            print(f"  [RUNNER] Resume: {task_input['resume_filename']}")
        else:
            print("  [RUNNER] No resume found in Supabase — will skip resume upload")

    print(f"  [AUTO_APPLY] platform={platform}  years_exp={task_input.get('years_experience', 2)}")

    if platform == "linkedin":
        return apply_linkedin_jobs(task_input)
    elif platform == "naukri":
        return apply_naukri_jobs(task_input)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def _handle_gmail_daily_check(task_input: dict) -> dict:
    """
    Scan the user's Gmail for job-related emails.
    For each email:
      - Classify it (ACKNOWLEDGMENT / INTERVIEW_INVITE / REJECTION / SCHEDULE_REQUEST / OFFER / GENERAL)
      - Match to an application by company name
      - Generate and send an AI reply for actionable emails
      - Update application stage when appropriate
      - Save an in-app notification for the user
    For APPLIED applications past their follow_up_at:
      - Send a follow-up email to the recruiter if their address is known
    """
    from automation.gmail_client import (
        scan_job_emails, generate_and_send_reply, send_followup_email,
    )
    from api_client import (
        fetch_gmail_settings, fetch_applications_for_followup,
        record_email_thread, update_application_stage, save_notification,
    )

    user_id = task_input.get("user_id", "")
    if not user_id:
        return {"message": "No user_id — skipping"}

    # Fetch stored gmail credentials
    settings = fetch_gmail_settings(user_id)
    if not settings:
        return {"message": "No Gmail settings configured"}

    gmail_address = settings.get("gmail_address", "")
    app_password  = settings.get("app_password", "")
    followup_days = int(settings.get("followup_days", 3))
    applicant_name = task_input.get("applicant_name", gmail_address.split("@")[0])

    if not gmail_address or not app_password:
        return {"message": "Gmail credentials incomplete"}

    print(f"  [GMAIL] Starting daily check for {gmail_address}")

    # Fetch known companies from recent applications to help matching
    from api_client import SUPABASE_URL, HEADERS
    import requests
    apps_resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/applications"
        f"?user_id=eq.{user_id}&select=id,stage,jobs(company,role,url)",
        headers=HEADERS,
    )
    applications = apps_resp.json() if apps_resp.ok else []
    known_companies = list({
        a["jobs"]["company"] for a in applications
        if a.get("jobs") and a["jobs"].get("company")
    })

    # ── STEP 1: Scan inbox ────────────────────────────────────
    emails = scan_job_emails(
        gmail_address, app_password,
        since_days=14,
        known_companies=known_companies,
    )
    print(f"  [GMAIL] Found {len(emails)} job-related emails")

    processed = 0
    for eml in emails:
        classification = eml["classification"]
        subject        = eml["subject"]
        from_address   = eml["from_address"]
        body           = eml["body"]
        received_at    = eml["received_at"]
        thread_id      = eml["thread_id"]
        summary        = eml["summary"]

        # Match to application by company name in subject/body
        matched_app_id = None
        matched_company = ""
        matched_role    = ""
        for app in applications:
            if not app.get("jobs"):
                continue
            company = app["jobs"].get("company", "")
            role    = app["jobs"].get("role", "")
            if company and company.lower() in (subject + " " + body[:300]).lower():
                matched_app_id  = app["id"]
                matched_company = company
                matched_role    = role
                break

        # Update application stage based on classification
        stage_map = {
            "INTERVIEW_INVITE":  "INTERVIEW",
            "SCHEDULE_REQUEST":  "SCREENING",
            "OFFER":             "OFFER",
            "REJECTION":         "REJECTED",
        }
        if matched_app_id and classification in stage_map:
            update_application_stage(matched_app_id, stage_map[classification])

        # Generate + send AI reply for actionable emails
        reply_text = ""
        reply_sent = False
        if classification in ("INTERVIEW_INVITE", "SCHEDULE_REQUEST", "OFFER", "REJECTION"):
            reply_sent, reply_text = generate_and_send_reply(
                gmail_address=gmail_address,
                app_password=app_password,
                to_address=from_address,
                original_subject=subject,
                original_body=body,
                classification=classification,
                company=matched_company or "the company",
                role=matched_role or "the position",
                applicant_name=applicant_name,
            )

        # Record in email_threads
        record_email_thread(
            user_id=user_id,
            application_id=matched_app_id,
            thread_id=thread_id,
            subject=subject,
            from_address=from_address,
            received_at=received_at,
            classification=classification,
            ai_summary=summary,
            ai_reply_text=reply_text,
            ai_reply_sent=reply_sent,
        )

        # Notify user
        notif_titles = {
            "INTERVIEW_INVITE": "🎉 Interview Invite!",
            "OFFER":            "🏆 Job Offer Received!",
            "REJECTION":        "📋 Application Update",
            "SCHEDULE_REQUEST": "📅 Scheduling Request",
            "ACKNOWLEDGMENT":   "✉️ Application Acknowledged",
        }
        title = notif_titles.get(classification, "📧 Job Email Received")
        save_notification(
            user_id=user_id,
            notif_type=classification.lower(),
            title=title,
            message=summary,
            metadata={"from": from_address, "subject": subject,
                       "application_id": matched_app_id or ""},
        )
        processed += 1

    # ── STEP 2: Send follow-ups for overdue applications ─────
    overdue = fetch_applications_for_followup(user_id)
    followups_sent = 0
    for app in overdue:
        # Only send if we have a recruiter email from a prior email thread
        app_id = app["id"]
        company = (app.get("jobs") or {}).get("company", "the company") if isinstance(app.get("jobs"), dict) else "the company"
        role = (app.get("jobs") or {}).get("role", "the position") if isinstance(app.get("jobs"), dict) else "the position"

        # Check if we have a recruiter email from email_threads
        threads_resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/email_threads"
            f"?application_id=eq.{app_id}&select=from_address&limit=1",
            headers=HEADERS,
        )
        recruiter_email = None
        if threads_resp.ok and threads_resp.json():
            recruiter_email = threads_resp.json()[0].get("from_address")

        if recruiter_email:
            sent = send_followup_email(
                gmail_address=gmail_address,
                app_password=app_password,
                to_address=recruiter_email,
                company=company,
                role=role,
                applicant_name=applicant_name,
            )
            if sent:
                record_email_thread(
                    user_id=user_id,
                    application_id=app_id,
                    thread_id=f"followup-{app_id}",
                    subject=f"Follow-up: {role} Application at {company}",
                    from_address=gmail_address,
                    received_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                    classification="FOLLOWUP_SENT",
                    ai_summary=f"Sent follow-up email to {recruiter_email}",
                )
                followups_sent += 1

    return {
        "emails_processed": processed,
        "followups_sent":   followups_sent,
        "message": f"Checked Gmail: {processed} emails processed, {followups_sent} follow-ups sent",
    }
