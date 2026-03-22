import time
import os
import sys
import requests
from datetime import datetime, timezone, timedelta

# ── Load .env from project root ─────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment

from api_client import fetch_pending_tasks, update_task, SUPABASE_URL, HEADERS, increment_usage
from task_runner import run_task

POLL_INTERVAL  = 10   # seconds between task polls
GMAIL_INTERVAL = 86400  # 24 hours in seconds


def _trigger_gmail_daily_checks():
    """Create a GMAIL_DAILY_CHECK task for every user who has gmail_settings configured."""
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/gmail_settings?active=eq.true&select=user_id", headers=HEADERS)
    if not resp.ok:
        return
    for row in resp.json():
        uid = row["user_id"]
        requests.post(
            f"{SUPABASE_URL}/rest/v1/tasks",
            headers=HEADERS,
            json={"user_id": uid, "type": "GMAIL_DAILY_CHECK", "status": "PENDING", "input": {}},
        )
    print(f"[GMAIL] Queued daily check for {len(resp.json())} user(s)")


def main():
    print("=" * 50)
    print("  VantaHire Task Runner — Started")
    print("=" * 50)

    last_gmail_check = datetime.now(timezone.utc) - timedelta(seconds=GMAIL_INTERVAL)  # run on first boot

    while True:
        # ── Daily Gmail check ──────────────────────────────────
        now = datetime.now(timezone.utc)
        if (now - last_gmail_check).total_seconds() >= GMAIL_INTERVAL:
            print("\n[GMAIL] Triggering daily Gmail checks…")
            _trigger_gmail_daily_checks()
            last_gmail_check = now

        # ── Regular task poll ──────────────────────────────────
        print("\n[POLL] Checking for pending tasks...")
        tasks = fetch_pending_tasks()

        if tasks:
            task = tasks[0]
            task_id = task["id"]
            print(f"[FOUND] Task {task_id}  type={task['type']}")

            update_task(task_id, "RUNNING")
            print(f"[STATUS] {task_id} → RUNNING")

            try:
                output = run_task(task)
                update_task(task_id, "DONE", output=output)
                print(f"[STATUS] {task_id} → DONE  output={output}")

                # Record usage for quota tracking
                quota_map = {
                    "AUTO_APPLY":       "auto_apply",
                    "TAILOR_AND_APPLY": "semi_auto_apply",
                    "TAILOR_RESUME":    "ai_tailor",
                    "GMAIL_DAILY_CHECK":"gmail_send",
                }
                action = quota_map.get(task.get("type", ""))
                uid = task.get("user_id", "")
                if action and uid:
                    increment_usage(uid, action)

            except Exception as e:
                error_msg = str(e)
                update_task(task_id, "FAILED", error=error_msg)
                print(f"[STATUS] {task_id} → FAILED  error={error_msg}")

        else:
            print("[IDLE]  No pending tasks. Sleeping...")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
