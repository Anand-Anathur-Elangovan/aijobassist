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


def _is_in_schedule_window(task: dict) -> bool:
    """Return True if current hour falls within task's schedule window (if any)."""
    task_input = task.get("input") or {}
    start_hour = task_input.get("schedule_start_hour")
    end_hour   = task_input.get("schedule_end_hour")
    if start_hour is None and end_hour is None:
        return True  # no schedule configured → run any time
    now_hour   = datetime.now().hour
    start_hour = int(start_hour) if start_hour is not None else 0
    end_hour   = int(end_hour)   if end_hour   is not None else 23
    if start_hour <= end_hour:
        return start_hour <= now_hour < end_hour
    # Overnight window e.g. 22–06
    return now_hour >= start_hour or now_hour < end_hour


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

    # Track if we've executed at least one task (for exit-after-run mode)
    ran_any_task = False

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

            # ── Schedule window gate ───────────────────────────
            if task.get("type") in ("AUTO_APPLY", "TAILOR_AND_APPLY"):
                if not _is_in_schedule_window(task):
                    print(f"[SCHED] Task {task_id} outside schedule window — will retry next poll")
                    time.sleep(POLL_INTERVAL)
                    continue  # Leave task as PENDING; try again next poll

            update_task(task_id, "RUNNING")
            print(f"[STATUS] {task_id} → RUNNING")

            try:
                output = run_task(task)
                update_task(task_id, "DONE", output=output)
                print(f"[STATUS] {task_id} → DONE  output={output}")
                ran_any_task = True

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
                ran_any_task = True

        else:
            # No pending tasks
            if ran_any_task and os.environ.get("TASK_RUNNER_ENV") != "railway":
                # Local agent exits after completing all tasks
                print("\n" + "=" * 50)
                print("  All tasks completed. Exiting.")
                print("=" * 50)
                break
            elif ran_any_task:
                # On Railway: reset flag and keep polling for more tasks
                ran_any_task = False
            print("[IDLE]  No pending tasks. Sleeping...")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
