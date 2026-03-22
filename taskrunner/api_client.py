import os
import requests
import json as _json
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://feqhdpxnzlctpwvvjxui.supabase.co")
# Service role key — bypasses RLS for backend agent use
SUPABASE_API_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk"
)

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}


def fetch_pending_tasks():
    """Fetch all PENDING tasks from Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/tasks?status=eq.PENDING&order=created_at.asc"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"[ERROR] fetch_pending_tasks: {response.status_code} {response.text}")
        return []


def fetch_latest_resume(user_id: str):
    """Fetch the most recent resume row for a user (includes content.file_url)."""
    url = f"{SUPABASE_URL}/rest/v1/resumes?user_id=eq.{user_id}&order=created_at.desc&limit=1"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        rows = response.json()
        return rows[0] if rows else None
    else:
        print(f"[ERROR] fetch_latest_resume: {response.status_code} {response.text}")
        return None


def update_task(task_id: str, status: str, output: dict = None, error: str = None):
    """Update a task's status (and optionally output/error) in Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}"
    data = {"status": status}
    if output is not None:
        data["output"] = output
    if error is not None:
        data["error"] = error
    if status in ("DONE", "FAILED"):
        data["completed_at"] = datetime.now(timezone.utc).isoformat()

    response = requests.patch(url, headers=HEADERS, json=data)
    if response.status_code not in (200, 204):
        print(f"[ERROR] update_task: {response.status_code} {response.text}")


def push_log(task_id: str, msg: str, level: str = "info") -> None:
    """
    Append a single log line to tasks.logs  (JSONB array).
    Each entry: { "ts": "<ISO>", "level": "info|warn|error|success", "msg": "..." }
    Uses Supabase RPC so we can atomically append without a read-modify-write race.
    Falls back to a simple PATCH if the RPC is not installed yet.
    """
    entry = {
        "ts":    datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": level,
        "msg":   msg,
    }
    # Try RPC approach first (requires fn append_task_log in Supabase)
    rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/append_task_log"
    resp = requests.post(
        rpc_url,
        headers=HEADERS,
        json={"p_task_id": task_id, "p_entry": entry},
    )
    if resp.status_code in (200, 204):
        return
    # Fallback: fetch current logs array, append, write back
    get_url = f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}&select=logs"
    gr = requests.get(get_url, headers=HEADERS)
    current = []
    if gr.ok:
        rows = gr.json()
        if rows:
            current = rows[0].get("logs") or []
    current.append(entry)
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
        headers=HEADERS,
        json={"logs": current},
    )


def update_task_progress(task_id: str, progress: int, current_job: str = None) -> None:
    """Update the live progress bar and current job label."""
    data: dict = {"progress": max(0, min(100, progress))}
    if current_job is not None:
        data["current_job"] = current_job
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
        headers=HEADERS,
        json=data,
    )


def fetch_task_control(task_id: str) -> dict:
    """
    Returns { paused, stop_requested, custom_prompt_override } for the task.
    The bot calls this before each new application to honour user control changes.
    """
    url = f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}&select=paused,stop_requested,custom_prompt_override"
    resp = requests.get(url, headers=HEADERS)
    if resp.ok:
        rows = resp.json()
        if rows:
            return rows[0]
    return {"paused": False, "stop_requested": False, "custom_prompt_override": None}


# ── Quota helpers ──────────────────────────────────────────────
def check_quota(user_id: str, action_type: str) -> dict:
    """Call the check_quota RPC and return {allowed, current_count, daily_limit}."""
    rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/check_quota"
    resp = requests.post(
        rpc_url, headers=HEADERS,
        json={"p_user_id": user_id, "p_action_type": action_type},
    )
    if resp.ok:
        rows = resp.json()
        if isinstance(rows, list) and rows:
            return rows[0]
        if isinstance(rows, dict):
            return rows
    return {"allowed": True, "current_count": 0, "daily_limit": 999}


def increment_usage(user_id: str, action_type: str) -> bool:
    """Record one usage event. Returns True on success."""
    rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/increment_usage"
    resp = requests.post(
        rpc_url, headers=HEADERS,
        json={"p_user_id": user_id, "p_action_type": action_type},
    )
    return resp.ok


def record_application(user_id: str, company: str, role: str, job_url: str,
                        followup_days: int = 3, ats_score: int = None,
                        resume_id: str = None) -> str | None:
    """
    Upsert a job row then insert an application row.
    Returns the application id, or None on failure.
    """
    from datetime import timedelta
    # 1. Check for existing job with this URL
    existing = requests.get(
        f"{SUPABASE_URL}/rest/v1/jobs?user_id=eq.{user_id}&url=eq.{requests.utils.quote(job_url, safe='')}&limit=1",
        headers=HEADERS,
    )
    job_id = None
    if existing.ok and existing.json():
        job_id = existing.json()[0]["id"]
    else:
        ins = requests.post(
            f"{SUPABASE_URL}/rest/v1/jobs",
            headers=HEADERS,
            json={"user_id": user_id, "company": company, "role": role,
                  "url": job_url, "status": "APPLYING"},
        )
        if ins.ok and ins.json():
            job_id = ins.json()[0]["id"]

    if not job_id:
        print(f"[ERROR] record_application: could not obtain job_id for {job_url}")
        return None

    # 2. Insert application (ignore duplicate user+job)
    follow_up_at = (datetime.now(timezone.utc) + timedelta(days=followup_days)).isoformat()
    payload: dict = {
        "user_id": user_id,
        "job_id": job_id,
        "stage": "APPLIED",
        "follow_up_at": follow_up_at,
    }
    if ats_score is not None:
        payload["ats_score"] = ats_score
    if resume_id:
        payload["resume_id"] = resume_id

    app_resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/applications",
        headers={**HEADERS, "Prefer": "resolution=ignore-duplicates,return=representation"},
        json=payload,
    )
    if app_resp.ok and app_resp.json():
        return app_resp.json()[0].get("id")
    if app_resp.status_code in (200, 201, 204):
        return None  # duplicate ignored
    print(f"[ERROR] record_application applications insert: {app_resp.status_code} {app_resp.text}")
    return None


def fetch_gmail_settings(user_id: str) -> dict | None:
    """Fetch gmail_settings row for a user."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/gmail_settings?user_id=eq.{user_id}&limit=1",
        headers=HEADERS,
    )
    if resp.ok and resp.json():
        return resp.json()[0]
    return None


def fetch_applications_for_followup(user_id: str) -> list:
    """
    Return APPLIED applications whose follow_up_at is in the past
    and that have no FOLLOWUP_SENT email thread yet.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/applications"
        f"?user_id=eq.{user_id}&stage=eq.APPLIED"
        f"&follow_up_at=lte.{now_iso}"
        f"&select=id,job_id,jobs(company,role,url)",
        headers=HEADERS,
    )
    if resp.ok:
        return resp.json()
    return []


def record_email_thread(user_id: str, application_id: str | None, thread_id: str,
                         subject: str, from_address: str, received_at: str,
                         classification: str, ai_summary: str = "",
                         ai_reply_text: str = "", ai_reply_sent: bool = False) -> None:
    """Insert a row into email_threads."""
    requests.post(
        f"{SUPABASE_URL}/rest/v1/email_threads",
        headers={**HEADERS, "Prefer": "resolution=ignore-duplicates"},
        json={
            "user_id": user_id,
            "application_id": application_id,
            "thread_id": thread_id,
            "subject": subject,
            "from_address": from_address,
            "received_at": received_at,
            "classification": classification,
            "ai_summary": ai_summary,
            "ai_reply_text": ai_reply_text,
            "ai_reply_sent": ai_reply_sent,
        },
    )


def update_application_stage(application_id: str, stage: str) -> None:
    """Update the stage of an application."""
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/applications?id=eq.{application_id}",
        headers=HEADERS,
        json={"stage": stage},
    )


def save_notification(user_id: str, notif_type: str, title: str, message: str,
                       metadata: dict = None) -> None:
    """Insert an in-app notification."""
    requests.post(
        f"{SUPABASE_URL}/rest/v1/notifications",
        headers=HEADERS,
        json={
            "user_id": user_id,
            "type": notif_type,
            "title": title,
            "message": message,
            "metadata": metadata or {},
        },
    )

