"""
taskrunner/server.py
--------------------
HTTP server that runs inside the Railway container.
Exposes /health, /trigger, /stop for the Next.js app (lib/railway.ts).
Starts the Supabase polling loop in a background thread on first /trigger call.
"""

import os
import sys
import select as _select
import socket as _socket
import subprocess
import threading
import time as _time
import requests as _req
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_sock import Sock

# ── Path setup ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))          # taskrunner/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # project root

from api_client import SUPABASE_URL, HEADERS
import display_pool as _dpool

# ── Display services (Xvfb + x11vnc for headed browser on Railway) ───────────
_IS_RAILWAY  = os.environ.get("TASK_RUNNER_ENV") == "railway"
_NOVNC_PATHS = ["/usr/share/novnc", "/usr/share/noVNC"]
# Fallback shared display used only when pool is exhausted
_FALLBACK_VNC_PORT = 5900


def _find_novnc_dir() -> str | None:
    for p in _NOVNC_PATHS:
        if os.path.isdir(p):
            return p
    return None


# ── Auth ─────────────────────────────────────────────────────
RAILWAY_API_TOKEN = os.environ.get("RAILWAY_API_TOKEN", "")

def _authorized(req) -> bool:
    if not RAILWAY_API_TOKEN:
        return True  # no token configured — open (dev mode)
    token = req.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return token == RAILWAY_API_TOKEN

# ── Session health watchdog ──────────────────────────────────
# If Railway pod restarts silently, sessions stuck in "running" would
# stay that way forever.  This watchdog runs every 5 minutes and marks
# any session (and its associated task) that has been running for longer
# than SESSION_STALE_SECONDS as failed.
SESSION_STALE_SECONDS = int(os.environ.get("SESSION_STALE_SECONDS", 7200))  # 2 hours
_WATCHDOG_INTERVAL    = 300   # check every 5 minutes

def _session_watchdog():
    """Background thread: heal stale railway_sessions and their tasks."""
    while True:
        _time.sleep(_WATCHDOG_INTERVAL)
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=SESSION_STALE_SECONDS)).isoformat()
            # Find sessions running longer than the stale threshold
            resp = _req.get(
                f"{SUPABASE_URL}/rest/v1/railway_sessions"
                f"?status=eq.running&started_at=lte.{cutoff}&select=id,task_id",
                headers=HEADERS,
            )
            if not resp.ok or not resp.json():
                continue
            stale = resp.json()
            print(f"[watchdog] Found {len(stale)} stale session(s) — marking failed")
            now_iso = datetime.now(timezone.utc).isoformat()
            for row in stale:
                sid = row.get("id", "")
                tid = row.get("task_id", "")
                # Mark session failed
                _req.patch(
                    f"{SUPABASE_URL}/rest/v1/railway_sessions?id=eq.{sid}",
                    headers={**HEADERS, "Prefer": "return=minimal"},
                    json={"status": "failed", "ended_at": now_iso},
                )
                # Mark associated task failed (only if still RUNNING)
                if tid:
                    _req.patch(
                        f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{tid}&status=eq.RUNNING",
                        headers={**HEADERS, "Prefer": "return=minimal"},
                        json={"status": "FAILED",
                              "error": "Session watchdog: pod became unresponsive",
                              "completed_at": now_iso},
                    )
                # Release allocated display back to pool
                _dpool.release(sid)
        except Exception as _we:
            print(f"[watchdog] Error: {_we}")


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
sock = Sock(app)


# ── noVNC static files ────────────────────────────────────────
@app.route("/novnc/", defaults={"path": "vnc.html"})
@app.route("/novnc/<path:path>")
def vnc_static(path):
    """Serve the noVNC web client from the system package path."""
    novnc_dir = _find_novnc_dir()
    if not novnc_dir:
        return "noVNC not installed on this server", 404
    return send_from_directory(novnc_dir, path)


# Legacy /vnc/ redirect for old bookmarks
@app.route("/vnc/", defaults={"path": ""})
@app.route("/vnc/<path:path>")
def vnc_legacy_redirect(path):
    return app.redirect(f"/novnc/{path}" if path else "/novnc/")


def _run_vnc_proxy(ws, port: int):
    """
    WebSocket → raw-TCP proxy to x11vnc on localhost:<port>.
    noVNC speaks RFB (VNC) protocol over WebSocket binary frames.
    """
    try:
        vnc = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        vnc.connect(("127.0.0.1", port))
    except Exception as e:
        print(f"[vnc-ws] Cannot connect to VNC ({_VNC_PORT}): {e}")
        return

    stop = threading.Event()

    def _vnc_to_ws():
        while not stop.is_set():
            try:
                readable, _, _ = _select.select([vnc], [], [], 0.5)
                if readable:
                    data = vnc.recv(65536)
                    if not data:
                        break
                    ws.send(data)
            except Exception:
                break
        stop.set()

    reader = threading.Thread(target=_vnc_to_ws, daemon=True)
    reader.start()

    try:
        while not stop.is_set():
            msg = ws.receive()
            if msg is None:
                break
            if isinstance(msg, str):
                msg = msg.encode("latin-1")
            vnc.sendall(msg)
    except Exception:
        pass
    finally:
        stop.set()
        try:
            vnc.close()
        except Exception:
            pass


@sock.route("/vnc-ws")
def vnc_ws_proxy(ws):
    """Route this WebSocket to the correct per-session VNC port.
    noVNC connects as: /vnc-ws?session=SESSION_ID
    Falls back to the shared :99 display (port 5900) if no session param.
    """
    session_id = request.args.get("session", "")
    port = _dpool.get_vnc_port(session_id) if session_id else None
    if port is None:
        port = _FALLBACK_VNC_PORT
    _run_vnc_proxy(ws, port)


# ── Health / control routes ───────────────────────────────────

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

    # Allocate a dedicated Xvfb + x11vnc display for this session (Railway only).
    # The allocated display/port are injected into the task's input row so the
    # automation script can launch Chromium on the right display.
    alloc = _dpool.allocate(session_id)
    if alloc:
        display_num, vnc_port = alloc
        display_str = f":{display_num}"
        # Inject display info into the task's input so automation can use it.
        # Spread data["task_input"] (flat user prefs) — NOT raw data (which would
        # nest all prefs under a "task_input" key and break the bot).
        _task_prefs = data.get("task_input") or {}
        _req.patch(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
            headers={**HEADERS, "Prefer": "return=minimal"},
            json={"input": {
                **_task_prefs,
                "session_id":      session_id,
                "session_display": display_str,
                "vnc_port":        vnc_port,
            }},
        )
        # Store vnc_port in railway_sessions so the frontend can build the right URL
        _req.patch(
            f"{SUPABASE_URL}/rest/v1/railway_sessions?id=eq.{session_id}",
            headers={**HEADERS, "Prefer": "return=minimal"},
            json={"vnc_port": vnc_port},
        )
        print(f"[server] /trigger  task_id={task_id}  session_id={session_id}  display={display_str}  vnc_port={vnc_port}")
    else:
        print(f"[server] /trigger  task_id={task_id}  session_id={session_id}  (shared display fallback)")

    # Task is already PENDING in Supabase; ensure the polling loop is running
    _ensure_polling_thread()

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

    # ── Start fallback Xvfb on :99 (used when display pool is exhausted or race condition) ──
    if _IS_RAILWAY:
        try:
            subprocess.Popen(
                ["Xvfb", ":99", "-screen", "0", "1920x1080x24", "-ac"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            _time.sleep(1.0)
            # Start x11vnc on the fallback display so it's also watchable
            subprocess.Popen(
                ["x11vnc", "-display", ":99",
                 "-forever", "-nopw", "-listen", "127.0.0.1",
                 "-rfbport", str(_FALLBACK_VNC_PORT), "-quiet", "-noncache"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print("[server] Fallback Xvfb :99 + x11vnc started")
        except Exception as _e:
            print(f"[server] Warning: could not start fallback Xvfb: {_e}")

    # Start polling loop immediately on boot (picks up any PENDING tasks)
    _ensure_polling_thread()

    # Start session health watchdog
    _wdog = threading.Thread(target=_session_watchdog, daemon=True, name="session-watchdog")
    _wdog.start()
    print("[server] Session health watchdog started")

    app.run(host="0.0.0.0", port=port, threaded=True)
