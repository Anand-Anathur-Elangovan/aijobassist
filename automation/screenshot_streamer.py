"""
automation/screenshot_streamer.py
----------------------------------
Runs inside the Railway container alongside the automation bot.
Takes a screenshot every SCREENSHOT_INTERVAL seconds and pushes the
base64-encoded JPEG to Supabase (railway_sessions.latest_screenshot).

The Next.js SSE route (/api/railway/stream) polls this column every
second and forwards updates to the browser client.

Usage (called from within automation, not standalone):
    import asyncio
    from automation.screenshot_streamer import start_streaming, stop_streaming

    asyncio.create_task(start_streaming(page, session_id))
    # ... automation runs ...
    stop_streaming()
"""

import asyncio
import base64
import os
import logging

logger = logging.getLogger(__name__)

# How often to capture + push a screenshot (seconds)
SCREENSHOT_INTERVAL = 1.0

# Supabase REST endpoint and service key from environment
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Internal stop signal
_stop_event = asyncio.Event()


def stop_streaming() -> None:
    """Signal the streaming coroutine to stop on its next iteration."""
    _stop_event.set()


async def start_streaming(page: object, session_id: str) -> None:
    """
    Main streaming loop.

    Args:
        page:       A Playwright Page object (playwright.async_api.Page).
        session_id: The railway_sessions.id row to update.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.warning("[streamer] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set — screenshots disabled")
        return

    _stop_event.clear()
    screenshot_count = 0

    logger.info(f"[streamer] Starting screenshot stream for session {session_id}")

    try:
        import httpx  # type: ignore
    except ImportError:
        logger.warning("[streamer] httpx not installed — screenshots disabled. Run: pip install httpx")
        return

    async with httpx.AsyncClient(timeout=5.0) as client:
        while not _stop_event.is_set():
            try:
                # Capture screenshot as bytes (JPEG, quality 60 for bandwidth)
                screenshot_bytes: bytes = await page.screenshot(  # type: ignore[attr-defined]
                    type="jpeg",
                    quality=60,
                    full_page=False,
                )
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                screenshot_count += 1

                # Push to Supabase via REST PATCH
                url = f"{SUPABASE_URL}/rest/v1/railway_sessions?id=eq.{session_id}"
                headers = {
                    "apikey":         SUPABASE_SERVICE_KEY,
                    "Authorization":  f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type":   "application/json",
                    "Prefer":         "return=minimal",
                }
                payload = {
                    "latest_screenshot": screenshot_b64,
                    "screenshot_count":  screenshot_count,
                }

                resp = await client.patch(url, headers=headers, json=payload)
                if resp.status_code not in (200, 204):
                    logger.warning(f"[streamer] Supabase PATCH failed: {resp.status_code} {resp.text[:120]}")

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug(f"[streamer] Screenshot error (skipping): {exc}")

            await asyncio.sleep(SCREENSHOT_INTERVAL)

    # Mark session status = 'completed' when streaming stops normally
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"{SUPABASE_URL}/rest/v1/railway_sessions?id=eq.{session_id}"
            headers = {
                "apikey":        SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            }
            await client.patch(url, headers=headers, json={"status": "completed"})
    except Exception as exc:
        logger.warning(f"[streamer] Failed to mark session completed: {exc}")

    logger.info(f"[streamer] Streaming stopped. Total screenshots: {screenshot_count}")


# ── Health endpoint (optional — for /health ping from Railway status API) ────
# If you run this as a standalone FastAPI service, import and mount this router.

def create_health_app():  # pragma: no cover
    """
    Create a minimal FastAPI app with /health, /trigger, /stop endpoints.
    Used when the Railway service is deployed as a standalone HTTP server.
    
    Install: pip install fastapi uvicorn
    Run:     uvicorn automation.screenshot_streamer:app --host 0.0.0.0 --port 8000
    """
    try:
        from fastapi import FastAPI, HTTPException  # type: ignore
        from pydantic import BaseModel              # type: ignore
    except ImportError:
        raise RuntimeError("FastAPI not installed. Run: pip install fastapi uvicorn pydantic")

    app = FastAPI(title="VantaHire Railway Service")

    class TriggerRequest(BaseModel):
        task_id:    str
        session_id: str
        task_input: dict = {}

    class StopRequest(BaseModel):
        run_id: str

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "vantahire-railway"}

    @app.post("/trigger")
    async def trigger(req: TriggerRequest):
        """
        Start an automation run.
        In a real deployment, this would launch the linkedin/naukri automation
        in a background asyncio task alongside the screenshot streamer.
        """
        # TODO: import and call the appropriate automation function based on task_input.type
        # For now, acknowledge receipt and return a run_id
        run_id = f"run_{req.task_id[:8]}"
        logger.info(f"[server] Trigger received: task_id={req.task_id} session_id={req.session_id}")
        return {"run_id": run_id, "status": "started"}

    @app.post("/stop")
    def stop(req: StopRequest):
        """Signal the streaming loop and automation to stop."""
        stop_streaming()
        return {"status": "stopping", "run_id": req.run_id}

    return app


# Only create the FastAPI app when this file is run as a server entry point
# (not when imported as a module from within the automation code)
import sys as _sys
if __name__ == "__main__" or (len(_sys.argv) > 0 and "uvicorn" in _sys.argv[0]):
    app = create_health_app()
