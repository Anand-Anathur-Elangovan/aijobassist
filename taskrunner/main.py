import time
import os
import sys
import requests
import concurrent.futures
from datetime import datetime, timezone, timedelta

# ── Load .env from project root ─────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment

from api_client import fetch_pending_tasks, update_task, SUPABASE_URL, HEADERS, increment_usage, record_railway_usage
from task_runner import run_task

POLL_INTERVAL  = 10   # seconds between task polls
GMAIL_INTERVAL = 86400  # 24 hours in seconds
# Maximum wall-clock time a single task may run before being force-failed.
# Default 2 hours; override via TASK_TIMEOUT_SECONDS env var.
TASK_TIMEOUT   = int(os.environ.get("TASK_TIMEOUT_SECONDS", 7200))


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

    is_railway = os.environ.get("TASK_RUNNER_ENV") == "railway"

    # Track if we've executed at least one task (for exit-after-run mode)
    ran_any_task = False

    last_gmail_check = datetime.now(timezone.utc) - timedelta(seconds=GMAIL_INTERVAL)  # run on first boot
    # On Railway: only print idle status every 5 minutes to keep logs clean
    last_idle_log    = datetime.now(timezone.utc) - timedelta(seconds=300)

    # ── Startup: heal any tasks stuck in RUNNING (e.g. from a previous crash) ──
    if is_railway:
        try:
            import requests as _req
            from api_client import SUPABASE_URL, HEADERS
            _req.patch(
                f"{SUPABASE_URL}/rest/v1/tasks?status=eq.RUNNING&execution_mode=eq.railway",
                headers={**HEADERS, "Prefer": "return=minimal"},
                json={"status": "FAILED", "error": "Task runner restarted — marked stale RUNNING tasks as FAILED"},
            )
            print("[STARTUP] Stale RUNNING tasks reset to FAILED")
        except Exception as _e:
            print(f"[STARTUP] Could not reset stale tasks: {_e}")

    while True:
        # ── Daily Gmail check ──────────────────────────────────
        now = datetime.now(timezone.utc)
        if (now - last_gmail_check).total_seconds() >= GMAIL_INTERVAL:
            print("\n[GMAIL] Triggering daily Gmail checks…")
            _trigger_gmail_daily_checks()
            last_gmail_check = now

        # ── Regular task poll (silent unless Railway idle log interval reached) ──
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
            task_start_time = datetime.now(timezone.utc)

            # Mark session as running with started_at (authoritative start time for billing)
            if is_railway:
                session_id = (task.get("input") or {}).get("session_id", "")
                if session_id:
                    try:
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/railway_sessions?id=eq.{session_id}",
                            headers={**HEADERS, "Prefer": "return=minimal"},
                            json={"status": "running", "started_at": task_start_time.isoformat()},
                        )
                    except Exception:
                        pass

            try:
                # ── Run task in a thread so we can enforce a hard timeout ──────
                # If the Railway pod doesn't crash but gets stuck (e.g. infinite
                # Playwright wait), the future times out and we force-fail the task.
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _exec:
                    _future = _exec.submit(run_task, task)
                    try:
                        output = _future.result(timeout=TASK_TIMEOUT)
                    except concurrent.futures.TimeoutError:
                        _future.cancel()
                        raise TimeoutError(
                            f"Task exceeded {TASK_TIMEOUT}s timeout — force-failed"
                        )

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

                # Record Railway minutes used (only on Railway container)
                if is_railway and uid:
                    duration = int((datetime.now(timezone.utc) - task_start_time).total_seconds())
                    session_id = (task.get("input") or {}).get("session_id", "")
                    record_railway_usage(uid, session_id, duration, status="completed")

            except Exception as e:
                error_msg = str(e)
                update_task(task_id, "FAILED", error=error_msg)
                print(f"[STATUS] {task_id} → FAILED  error={error_msg}")
                ran_any_task = True

                # On timeout: also mark the railway_session as timed_out
                if isinstance(e, TimeoutError) and is_railway:
                    _s_id = (task.get("input") or {}).get("session_id", "")
                    if _s_id:
                        try:
                            requests.patch(
                                f"{SUPABASE_URL}/rest/v1/railway_sessions?id=eq.{_s_id}",
                                headers={**HEADERS, "Prefer": "return=minimal"},
                                json={"status": "timed_out",
                                      "ended_at": datetime.now(timezone.utc).isoformat()},
                            )
                        except Exception:
                            pass

                # Record Railway minutes even on failure (user still consumed time)
                if is_railway:
                    uid = task.get("user_id", "")
                    if uid:
                        duration = int((datetime.now(timezone.utc) - task_start_time).total_seconds())
                        session_id = (task.get("input") or {}).get("session_id", "")
                        record_railway_usage(uid, session_id, duration, status="failed")

        else:
            # No pending tasks
            if ran_any_task and not is_railway:
                # Local agent exits after completing all tasks
                print("\n" + "=" * 50)
                print("  All tasks completed. Exiting.")
                print("=" * 50)
                break
            elif ran_any_task:
                # On Railway: reset flag and keep polling for more tasks
                ran_any_task = False
            # Only print idle message every 5 minutes on Railway (suppress log spam)
            if not is_railway or (datetime.now(timezone.utc) - last_idle_log).total_seconds() >= 300:
                print("[IDLE]  No pending tasks. Sleeping...")
                last_idle_log = datetime.now(timezone.utc)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
