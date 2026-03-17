#!/usr/bin/env python3
"""dblCheck Daemon — scheduled validation + WebSocket dashboard bridge.

Runs validation every INTERVAL seconds (headless) and concurrently serves
the WebSocket dashboard bridge on DASHBOARD_PORT.

Environment:
    INTERVAL        — validation interval in seconds (default 300)
    DASHBOARD_PORT  — WebSocket/HTTP port (default 5556)
"""
import asyncio
import logging
import os
import sys
import types
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.logging_config import setup_logging
setup_logging()

log = logging.getLogger("dblcheck.daemon")

try:
    INTERVAL = max(10, int(os.getenv("INTERVAL", "300")))
except ValueError:
    raise ValueError(
        f"INTERVAL must be an integer number of seconds, got: {os.getenv('INTERVAL')!r}"
    )


def _headless_args() -> types.SimpleNamespace:
    """Build a fake args namespace for headless daemon runs."""
    return types.SimpleNamespace(
        device=[],
        protocol=None,
        output_format="text",
        no_diagnose=False,
        headless=True,
    )


async def _validation_loop() -> None:
    """Run validation every INTERVAL seconds."""
    from cli.dblcheck import _run
    log.info("Validation loop starting — interval %ds", INTERVAL)
    while True:
        try:
            log.info("Starting scheduled validation run")
            await _run(_headless_args())
        except Exception as e:
            log.error("Validation run failed: %s", e)
        log.info("Next run in %ds", INTERVAL)
        await asyncio.sleep(INTERVAL)


async def _bridge() -> None:
    """Run the WebSocket dashboard bridge."""
    from websockets.asyncio.server import serve
    from dashboard.ws_bridge import (
        ws_handler, _http_handler, watch_state_file, PORT, HOST,
    )
    log.info("Dashboard bridge starting on port %d", PORT)
    async with serve(ws_handler, HOST, PORT, process_request=_http_handler):
        log.info("Dashboard listening on http://%s:%d", HOST, PORT)
        await watch_state_file()


async def main() -> None:
    await asyncio.gather(
        _bridge(),
        _validation_loop(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Daemon stopped")
