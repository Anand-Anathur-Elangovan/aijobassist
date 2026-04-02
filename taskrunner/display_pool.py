"""
taskrunner/display_pool.py
--------------------------
Per-session Xvfb + x11vnc display pool for Railway multi-user isolation.
Each active task gets its own virtual display (:100-:109) and VNC port (5901-5910).
Imported by server.py (allocation on /trigger) and main.py (release after task ends).
"""

import os
import subprocess
import threading
import time
from typing import Optional

_IS_RAILWAY = os.environ.get("TASK_RUNNER_ENV") == "railway"

# Pool of available display numbers (:100–:109 → VNC ports 5901–5910)
# :99/5900 is the system fallback — never allocated to tasks.
_POOL: list = list(range(100, 110))   # 10 concurrent sessions max
_lock = threading.Lock()
_active: dict = {}                     # session_id → {display, vnc_port, procs}


def allocate(session_id: str) -> Optional[tuple]:
    """
    Allocate a dedicated Xvfb display + x11vnc for one session.
    Returns (display_num, vnc_port) on success, None if pool is exhausted
    or not running on Railway.
    """
    if not _IS_RAILWAY or not session_id:
        return None

    with _lock:
        if not _POOL:
            print(f"[display-pool] Pool exhausted — {session_id[:8]} falls back to shared display")
            return None
        display_num = _POOL.pop(0)

    vnc_port = 5900 + (display_num - 99)   # :100→5901, :101→5902, …
    procs: list = []
    try:
        procs.append(subprocess.Popen(
            ["Xvfb", f":{display_num}", "-screen", "0", "1920x1080x24", "-ac"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        time.sleep(1.2)

        procs.append(subprocess.Popen(
            ["x11vnc", "-display", f":{display_num}",
             "-forever", "-nopw", "-listen", "127.0.0.1",
             "-rfbport", str(vnc_port), "-quiet", "-noncache"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        time.sleep(0.8)

        with _lock:
            _active[session_id] = {
                "display":  display_num,
                "vnc_port": vnc_port,
                "procs":    procs,
            }
        print(f"[display-pool] + Allocated :{display_num} port={vnc_port} "
              f"for session {session_id[:8]} (pool left: {len(_POOL)})")
        return display_num, vnc_port

    except Exception as exc:
        for p in procs:
            try: p.terminate()
            except Exception: pass
        with _lock:
            _POOL.append(display_num)
        print(f"[display-pool] Allocation failed for {session_id[:8]}: {exc}")
        return None


def release(session_id: str) -> None:
    """
    Kill Xvfb + x11vnc for the session and return the display to the pool.
    Safe to call even if the session was never allocated.
    """
    with _lock:
        info = _active.pop(session_id, None)
        if not info:
            return
        _POOL.append(info["display"])

    for proc in info.get("procs", []):
        try: proc.terminate()
        except Exception: pass
    print(f"[display-pool] - Released :{info['display']} port={info['vnc_port']} "
          f"session {session_id[:8]} (pool left: {len(_POOL)})")


def get_vnc_port(session_id: str) -> Optional[int]:
    """Return VNC port for a session, or None if not allocated."""
    info = _active.get(session_id)
    return info["vnc_port"] if info else None


def get_display(session_id: str) -> Optional[str]:
    """Return display string e.g. ':101' for a session, or None."""
    info = _active.get(session_id)
    return f":{info['display']}" if info else None
