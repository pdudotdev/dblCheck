#!/usr/bin/env python3
"""dblCheck Daemon — scheduled validation + WebSocket dashboard bridge.

Runs validation every INTERVAL seconds (headless) and concurrently serves
the WebSocket dashboard bridge on DASHBOARD_PORT.

Environment:
    INTERVAL        — validation interval in seconds (default 300)
    DASHBOARD_PORT  — WebSocket/HTTP port (default 5556)
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_STATE_FILE = _PROJECT_ROOT / "data" / "dashboard_state.json"

from core.logging_config import setup_logging
setup_logging()

log = logging.getLogger("dblcheck.daemon")

try:
    INTERVAL = max(10, int(os.getenv("INTERVAL", "300")))
except ValueError:
    raise ValueError(
        f"INTERVAL must be an integer number of seconds, got: {os.getenv('INTERVAL')!r}"
    )


def _patch_scheduling_state() -> None:
    """Append interval and next_run_at to the idle state file for the dashboard."""
    try:
        state = json.loads(_STATE_FILE.read_text())
        state["interval"] = INTERVAL
        state["next_run_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=INTERVAL)
        ).isoformat()
        _STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass  # state file may not exist on the very first run


async def _validation_loop() -> None:
    """Run validation every INTERVAL seconds.

    Each run is a subprocess (python cli/dblcheck.py --headless) so that
    validation has its own event loop with no GIL sharing with the bridge.
    Running validation in a thread via asyncio.to_thread caused VyOS per-command
    SSH connections to time out due to GIL contention from the bridge event loop.
    """
    log.info("Validation loop starting — interval %ds", INTERVAL)
    while True:
        proc = None
        try:
            log.info("Starting scheduled validation run")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(_PROJECT_ROOT / "cli" / "dblcheck.py"),
                "--headless",
            )
            returncode = await proc.wait()
            if returncode not in (0, 2):
                log.warning("Validation subprocess exited with code %d", returncode)
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
            raise
        except Exception as e:
            log.error("Validation run failed: %s", e)
        _patch_scheduling_state()
        log.info("Next run in %ds", INTERVAL)
        await asyncio.sleep(INTERVAL)


async def _bridge() -> None:
    """Run the WebSocket dashboard bridge."""
    from websockets.asyncio.server import serve
    from dashboard.ws_bridge import (
        ws_handler, _http_handler, watch_state_file, PORT, HOST,
    )
    log.info("Dashboard bridge starting on port %d", PORT)
    async with serve(ws_handler, HOST, PORT, process_request=_http_handler,
                     reuse_address=True):
        log.info("Dashboard listening on http://%s:%d", HOST, PORT)
        await watch_state_file()


async def main() -> None:
    results = await asyncio.gather(
        _bridge(),
        _validation_loop(),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            log.error("Coroutine failed: %s", r)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Daemon stopped")
