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

SUBPROCESS_TIMEOUT = 600  # seconds — hard watchdog for the validation subprocess

# ── Stop support ──────────────────────────────────────────────────────────────
_current_proc = None   # asyncio.subprocess.Process | None
_stop_requested: bool = False


def request_stop() -> bool:
    """Terminate the current validation subprocess. Called from the bridge HTTP handler."""
    global _stop_requested
    if _current_proc is not None and _current_proc.returncode is None:
        _stop_requested = True
        _current_proc.terminate()
        log.info("Stop requested — sent SIGTERM to validation subprocess")
        return True
    return False


def _patch_scheduling_state() -> None:
    """Append interval and next_run_at to the idle state file for the dashboard."""
    try:
        state = json.loads(_STATE_FILE.read_text())
        state["interval"] = INTERVAL
        state["next_run_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=INTERVAL)
        ).isoformat()
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state))
        tmp.rename(_STATE_FILE)
    except Exception as e:
        log.warning("Failed to patch scheduling state: %s", e)


def _force_idle_state(error: str) -> None:
    """Force the state file to idle — defense-in-depth when the subprocess dies abnormally."""
    try:
        existing: dict = {}
        try:
            existing = json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
        idle = {
            "state": "idle",
            "error": error,
            **{k: v for k, v in existing.items()
               if k in ("last_run", "last_run_file", "session_file")},
        }
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(idle))
        tmp.rename(_STATE_FILE)
    except Exception as e:
        log.warning("Failed to force idle state: %s", e)


async def _validation_loop() -> None:
    """Run validation every INTERVAL seconds.

    Each run is a subprocess (python cli/dblcheck.py --headless) so that
    validation has its own event loop with no GIL sharing with the bridge.
    Running validation in a thread via asyncio.to_thread caused VyOS per-command
    SSH connections to time out due to GIL contention from the bridge event loop.
    """
    log.info("Validation loop starting — interval %ds", INTERVAL)
    while True:
        global _current_proc, _stop_requested
        proc = None
        try:
            log.info("Starting scheduled validation run")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(_PROJECT_ROOT / "cli" / "dblcheck.py"),
                "--headless",
            )
            _current_proc = proc
            try:
                returncode = await asyncio.wait_for(proc.wait(), timeout=SUBPROCESS_TIMEOUT)
            except asyncio.TimeoutError:
                log.error("Validation subprocess timed out after %ds — terminating", SUBPROCESS_TIMEOUT)
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                returncode = -1
            _current_proc = None
            if _stop_requested:
                _stop_requested = False
                _force_idle_state("Stopped by user")
            elif returncode == -1:
                _force_idle_state(
                    f"Validation subprocess timed out after {SUBPROCESS_TIMEOUT}s"
                )
            elif returncode not in (0, 2):
                log.warning("Validation subprocess exited with code %d", returncode)
                _force_idle_state(f"Validation failed (exit code {returncode})")
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
        register_stop_callback,
    )
    register_stop_callback(request_stop)
    log.info("Dashboard bridge starting on port %d", PORT)
    async with serve(ws_handler, HOST, PORT, process_request=_http_handler,
                     reuse_address=True):
        log.info("Dashboard listening on http://%s:%d", HOST, PORT)
        await watch_state_file()


async def _supervise(name: str, coro_fn) -> None:
    """Run a coroutine in a restart loop, logging and recovering from crashes."""
    while True:
        try:
            await coro_fn()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("Coroutine %s crashed: %s — restarting in 10s", name, e)
            await asyncio.sleep(10)


async def main() -> None:
    await asyncio.gather(
        _supervise("bridge", _bridge),
        _supervise("validation_loop", _validation_loop),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Daemon stopped")
