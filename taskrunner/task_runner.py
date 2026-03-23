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
    from api_client import check_quota

    task_type  = task.get("type", "UNKNOWN")
    task_id    = task.get("id", "")
    task_input = dict(task.get("input") or {})
    # Inject user_id and task_id so automation layers can push live logs
    task_input["user_id"] = task.get("user_id", "")
    task_input["task_id"] = task_id
    user_id = task_input["user_id"]

    print(f"  [RUNNER] type={task_type}  user_id={user_id}")

    # ── Super admin bypass ────────────────────────────────────
    SUPER_ADMIN_IDS = [
        "7488cae8-328b-4ffc-8136-42a0c18ed06d",  # kaviyasaravanan01@gmail.com
    ]

    # ── Quota gate ────────────────────────────────────────────
    quota_map = {
        "AUTO_APPLY":       "auto_apply",
        "TAILOR_AND_APPLY": "semi_auto",
        "TAILOR_RESUME":    "ai_tailor",
        "GMAIL_DAILY_CHECK":"gmail_scan",
    }
    action_type = quota_map.get(task_type)
    if action_type and user_id and user_id not in SUPER_ADMIN_IDS:
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

    platform = task_input.get("platform", "linkedin")
    user_id  = task_input.get("user_id", "")

    # ── AI company-site apply quota (free=2, paid=unlimited) ───
    if user_id and "_ai_company_site_limit" not in task_input:
        tier = fetch_user_tier(user_id)
        task_input["_ai_company_site_limit"] = 2 if tier == "free" else 999
    task_input.setdefault("_ai_company_site_used", 0)

    # Attach resume URL and parsed text if not already set
    if user_id and not task_input.get("resume_url"):
        resume = fetch_latest_resume(user_id)
        if resume:
            content = resume.get("content") or {}
            task_input["resume_url"]      = content.get("file_url", "")
            task_input["resume_filename"] = content.get("file_name", resume.get("title", "resume.pdf"))
            # Pass parsed_text as fallback for tailoring (no re-download required)
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
