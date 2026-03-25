"""
taskrunner/server.py
--------------------
HTTP server that runs inside the Railway container.
Exposes /health, /trigger, /stop for the Next.js app (lib/railway.ts).
Starts the Supabase polling loop in a background thread on first /trigger call.
"""

import os
import sys
import threading
import requests as _req
from flask import Flask, request, jsonify

# ── Path setup ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))          # taskrunner/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # project root

from api_client import SUPABASE_URL, HEADERS

# ── Auth ─────────────────────────────────────────────────────
RAILWAY_API_TOKEN = os.environ.get("RAILWAY_API_TOKEN", "")

def _authorized(req) -> bool:
    if not RAILWAY_API_TOKEN:
        return True  # no token configured — open (dev mode)
    token = req.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return token == RAILWAY_API_TOKEN

# ── Polling thread management ────────────────────────────────
_poll_thread: threading.Thread | None = None
_poll_lock = threading.Lock()

def _ensure_polling_thread():
    global _poll_thread
    with _poll_lock:
        if _poll_thread is None or not _poll_thread.is_alive():
            from main import main as _run_main
            _poll_thread = threading.Thread(target=_run_main, daemon=True, name="task-poller")
            _poll_thread.start()
            print("[server] Polling thread started")

# ── Flask app ─────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "polling": _poll_thread is not None and _poll_thread.is_alive()})


@app.route("/trigger", methods=["POST"])
def trigger():
    if not _authorized(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    task_id    = data.get("task_id", "")
    session_id = data.get("session_id", task_id)

    # Task is already PENDING in Supabase; ensure the polling loop is running
    _ensure_polling_thread()

    print(f"[server] /trigger  task_id={task_id}  session_id={session_id}")
    return jsonify({"run_id": session_id, "status": "queued"})


@app.route("/stop", methods=["POST"])
def stop():
    if not _authorized(request):
        return jsonify({"error": "Unauthorized"}), 401

    data   = request.get_json(silent=True) or {}
    run_id = data.get("run_id", "")

    if run_id:
        # Signal the bot to stop by setting stop_requested in Supabase
        resp = _req.patch(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{run_id}",
            headers=HEADERS,
            json={"stop_requested": True},
        )
        print(f"[server] /stop  run_id={run_id}  status={resp.status_code}")

    return jsonify({"stopped": True, "run_id": run_id})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[server] VantaHire Railway service starting on port {port}")

    # Start polling loop immediately on boot (picks up any PENDING tasks)
    _ensure_polling_thread()

    app.run(host="0.0.0.0", port=port, threaded=True)
