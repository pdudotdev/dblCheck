#!/usr/bin/env python3
"""dblCheck Dashboard WebSocket Bridge

Polls data/dashboard_state.json for run lifecycle events. When a validation run
completes, broadcasts assertion results to connected clients. When diagnosis
runs, tail-follows the NDJSON session file and streams parsed events.

Also serves dashboard/index.html over HTTP on the same port.

Communication with cli/dblcheck.py is filesystem-only:
  data/dashboard_state.json   — lifecycle state (idle/validating/diagnosing)
  data/runs/run-*.json        — assertion results per run
  data/sessions/session-*.ndjson — claude stream-json per diagnosis session

Port: DASHBOARD_PORT env var (default 5556)
"""

import asyncio
import collections
import hmac
import json
import logging
import os
import sys
import urllib.parse
from pathlib import Path

from websockets.asyncio.server import serve, broadcast as ws_broadcast
from websockets.datastructures import Headers
from websockets.http11 import Response

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_DIR   = Path(__file__).parent.parent
DASHBOARD_DIR = Path(__file__).parent
DATA_DIR      = PROJECT_DIR / "data"
RUNS_DIR      = DATA_DIR / "runs"
STATE_FILE    = DATA_DIR / "dashboard_state.json"
INDEX_HTML    = DASHBOARD_DIR / "index.html"

try:
    PORT = int(os.getenv("DASHBOARD_PORT", "5556"))
except ValueError:
    raise ValueError(
        f"DASHBOARD_PORT must be an integer, got: {os.getenv('DASHBOARD_PORT')!r}"
    )
HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")

# ── Optional token auth ───────────────────────────────────────────────────────
# If configured, all HTTP and WebSocket connections must supply ?token=<value>.
# Stored in Vault at dblcheck/dashboard key "token", or DASHBOARD_TOKEN env var.
sys.path.insert(0, str(PROJECT_DIR))
from core.vault import get_secret as _get_secret
_DASHBOARD_TOKEN: str = _get_secret("dblcheck/dashboard", "token",
                                     fallback_env="DASHBOARD_TOKEN", quiet=True) or ""

BUFFER_SIZE       = 200
TAIL_POLL_INTERVAL = 0.1   # seconds
RUN_HISTORY_MAX   = 20

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("dblcheck.dashboard")
logging.getLogger("websockets.server").setLevel(logging.WARNING)

# ── Shared state ──────────────────────────────────────────────────────────────
CLIENTS: set = set()
EVENT_BUFFER: collections.deque = collections.deque(maxlen=BUFFER_SIZE)
SESSION_STATE: dict = {"state": "idle"}

# Pending tool inputs accumulated across content_block_delta chunks
_tool_inputs: dict[int, dict] = {}

_MCP_PREFIX = "mcp__dblcheck__"


# ── Event parsing ─────────────────────────────────────────────────────────────

def _strip_tool_prefix(name: str) -> tuple[str, bool]:
    """Return (display_name, is_mcp) for a tool name."""
    if name.startswith(_MCP_PREFIX):
        return name[len(_MCP_PREFIX):], True
    return name, False


def parse_ndjson_line(raw: str) -> list[dict]:
    """Parse one stream-json NDJSON line into zero or more UI events.

    Claude CLI stream-json format:
      {"type": "stream_event", "event": {"type": "...", ...}}
      {"type": "result", "total_cost_usd": ..., ...}
    """
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []

    t = obj.get("type")

    if t == "result":
        return [{"ui_type": "session_end", "cost": obj.get("total_cost_usd")}]

    if t != "stream_event":
        return []

    ev = obj.get("event", {})
    ev_type = ev.get("type", "")

    if ev_type == "content_block_delta":
        delta = ev.get("delta", {})
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if text:
                return [{"ui_type": "reasoning", "text": text}]
        elif delta.get("type") == "input_json_delta":
            idx = ev.get("index", -1)
            partial = delta.get("partial_json", "")
            if idx not in _tool_inputs:
                _tool_inputs[idx] = {"json_buf": "", "id": None, "name": None}
            _tool_inputs[idx]["json_buf"] += partial

    elif ev_type == "content_block_start":
        cb = ev.get("content_block", {})
        if cb.get("type") == "tool_use":
            idx = ev.get("index", -1)
            tool_id = cb.get("id", "")
            name, is_mcp = _strip_tool_prefix(cb.get("name", ""))
            _tool_inputs[idx] = {"json_buf": "", "id": tool_id, "name": name, "is_mcp": is_mcp}
            return [{"ui_type": "tool_start", "tool": name, "id": tool_id, "is_mcp": is_mcp}]
        elif cb.get("type") == "tool_result":
            tool_use_id = cb.get("tool_use_id", "")
            content = cb.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            return [{"ui_type": "tool_result", "id": tool_use_id, "output": str(content)}]

    elif ev_type == "content_block_stop":
        idx = ev.get("index", -1)
        if idx in _tool_inputs:
            entry = _tool_inputs.pop(idx)
            if entry.get("id"):
                try:
                    input_obj = json.loads(entry["json_buf"]) if entry["json_buf"] else {}
                except json.JSONDecodeError:
                    input_obj = {"raw": entry["json_buf"]}
                return [{
                    "ui_type": "tool_input_complete",
                    "tool": entry.get("name", ""),
                    "id": entry["id"],
                    "input": input_obj,
                    "is_mcp": entry.get("is_mcp", False),
                }]

    return []


# ── Session file tail-follower ─────────────────────────────────────────────────

async def _tail_session_file(path: Path) -> None:
    """Tail-follow a diagnosis session NDJSON file and broadcast parsed events."""
    log.info("Tail-following session file: %s", path)
    for _ in range(50):  # wait up to 5 seconds for file to appear
        if path.exists():
            break
        await asyncio.sleep(0.1)
    else:
        log.warning("Session file never appeared: %s", path)
        return

    _tool_inputs.clear()
    position = 0

    while True:
        if SESSION_STATE.get("state") != "diagnosing":
            # Drain remaining lines before stopping
            try:
                with open(path, errors="replace") as fh:
                    fh.seek(position)
                    remainder = fh.read()
                for line in remainder.splitlines():
                    line = line.strip()
                    if line:
                        for ui_event in parse_ndjson_line(line):
                            await _broadcast(ui_event)
                            EVENT_BUFFER.append(ui_event)
            except Exception:
                pass
            log.info("Diagnosis ended — stopping tail")
            return

        try:
            with open(path, errors="replace") as fh:
                fh.seek(position)
                new_text = fh.read()
        except FileNotFoundError:
            await asyncio.sleep(TAIL_POLL_INTERVAL)
            continue

        if new_text:
            lines = new_text.split("\n")
            if not new_text.endswith("\n"):
                lines_to_process = lines[:-1]
                consumed = len("\n".join(lines_to_process))
                if lines_to_process:
                    consumed += 1
            else:
                lines_to_process = lines[:-1]
                consumed = len(new_text)

            for line in lines_to_process:
                line = line.strip()
                if not line:
                    continue
                for ui_event in parse_ndjson_line(line):
                    await _broadcast(ui_event)
                    EVENT_BUFFER.append(ui_event)

            position += consumed

        await asyncio.sleep(TAIL_POLL_INTERVAL)


# ── State file watcher ─────────────────────────────────────────────────────────

async def watch_state_file() -> None:
    """Poll dashboard_state.json and drive the session lifecycle."""
    global SESSION_STATE
    tail_task: asyncio.Task | None = None
    last_run_name: str | None = None

    log.info("Watching state file: %s", STATE_FILE)
    while True:
        try:
            raw = STATE_FILE.read_text()
            state = json.loads(raw)
        except FileNotFoundError:
            state = {"state": "idle"}
        except (json.JSONDecodeError, OSError):
            state = {"state": "idle"}

        state_changed = state != SESSION_STATE
        SESSION_STATE = state
        s = state.get("state")

        if s == "validating" and state_changed:
            run_name = state.get("run_name")
            if run_name != last_run_name:
                if tail_task and not tail_task.done():
                    tail_task.cancel()
                    try:
                        await tail_task
                    except asyncio.CancelledError:
                        pass
                last_run_name = run_name
                EVENT_BUFFER.clear()
                # _tool_inputs is cleared by _tail_session_file at its start;
                # clearing here would race with an in-progress tail task.
                await _broadcast({
                    "ui_type": "validation_start",
                    "run_name": run_name,
                    "started_at": state.get("started_at"),
                })

        elif s == "diagnosing" and state_changed:
            # Run file is ready — broadcast validation results first
            run_file = state.get("run_file")
            if run_file:
                try:
                    run_data = json.loads(Path(run_file).read_text())
                    event = {"ui_type": "validation_results", **run_data}
                    await _broadcast(event)
                    EVENT_BUFFER.append(event)
                except Exception as e:
                    log.warning("Could not read run file: %s", e)

            # Start tail-following the diagnosis session file
            session_file = state.get("session_file")
            if session_file:
                if tail_task and not tail_task.done():
                    tail_task.cancel()
                    try:
                        await tail_task
                    except asyncio.CancelledError:
                        pass
                await _broadcast({"ui_type": "session_start", **state})
                tail_task = asyncio.create_task(
                    _tail_session_file(Path(session_file))
                )

        elif s == "idle" and state_changed:
            if tail_task and not tail_task.done():
                tail_task.cancel()
                try:
                    await tail_task
                except asyncio.CancelledError:
                    pass

            # Broadcast final validation results (covers no-failure runs)
            last_run_file = state.get("last_run_file")
            if last_run_file:
                try:
                    run_data = json.loads(Path(last_run_file).read_text())
                    event = {"ui_type": "validation_results", **run_data}
                    await _broadcast(event)
                    EVENT_BUFFER.append(event)
                except Exception:
                    pass

            await _broadcast({"ui_type": "session_idle"})

        await asyncio.sleep(0.5)


# ── Broadcast ─────────────────────────────────────────────────────────────────

async def _broadcast(event: dict) -> None:
    if not CLIENTS:
        return
    ws_broadcast(CLIENTS, json.dumps(event))


# ── HTTP handler ──────────────────────────────────────────────────────────────

def _get_run_history() -> list[dict]:
    """Return summary of the last RUN_HISTORY_MAX runs, newest first."""
    if not RUNS_DIR.exists():
        return []
    runs = sorted(RUNS_DIR.glob("run-*.json"), key=lambda p: p.name, reverse=True)
    history = []
    for path in runs[:RUN_HISTORY_MAX]:
        try:
            data = json.loads(path.read_text())
            history.append({
                "name": path.stem,
                "timestamp": data.get("timestamp"),
                "summary": data.get("summary", {}),
            })
        except Exception:
            pass
    return history


def _token_from_path(path: str) -> str | None:
    """Extract the 'token' query parameter from a URL path."""
    return urllib.parse.parse_qs(
        urllib.parse.urlparse(path).query
    ).get("token", [None])[0]


def _http_handler(connection, request):
    """Serve HTTP requests; pass WebSocket upgrade requests through."""
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None  # token auth happens in ws_handler

    if _DASHBOARD_TOKEN:
        if not hmac.compare_digest(_token_from_path(request.path) or "", _DASHBOARD_TOKEN):
            headers = Headers({"Content-Type": "text/plain"})
            return Response(401, "Unauthorized", headers, b"Unauthorized")

    # Strip token from path for routing (e.g. /?token=xxx → /)
    clean_path = urllib.parse.urlparse(request.path).path

    if clean_path in ("/", "/index.html"):
        try:
            body = INDEX_HTML.read_bytes()
            headers = Headers({"Content-Type": "text/html; charset=utf-8"})
            return Response(200, "OK", headers, body)
        except FileNotFoundError:
            headers = Headers({"Content-Type": "text/plain"})
            return Response(404, "Not Found", headers, b"Dashboard not found")

    if clean_path.startswith("/api/run/"):
        run_name = clean_path[len("/api/run/"):]
        run_file = RUNS_DIR / f"{run_name}.json"
        # Guard against path traversal (e.g. /api/run/../../etc/passwd)
        try:
            if not run_file.resolve().is_relative_to(RUNS_DIR.resolve()):
                headers = Headers({"Content-Type": "text/plain"})
                return Response(404, "Not Found", headers, b"Run not found")
        except ValueError:
            headers = Headers({"Content-Type": "text/plain"})
            return Response(404, "Not Found", headers, b"Run not found")
        try:
            body = run_file.read_bytes()
            headers = Headers({"Content-Type": "application/json"})
            return Response(200, "OK", headers, body)
        except FileNotFoundError:
            headers = Headers({"Content-Type": "text/plain"})
            return Response(404, "Not Found", headers, b"Run not found")

    if clean_path == "/favicon.ico":
        return Response(204, "No Content", Headers({}), b"")

    headers = Headers({"Content-Type": "text/plain"})
    return Response(404, "Not Found", headers, b"Not found")


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def ws_handler(websocket) -> None:
    if _DASHBOARD_TOKEN:
        client_token = _token_from_path(websocket.request.path)
        if not hmac.compare_digest(client_token or "", _DASHBOARD_TOKEN):
            await websocket.close(4001, "Unauthorized")
            return

    remote = websocket.remote_address
    log.info("WebSocket client connected: %s", remote)
    CLIENTS.add(websocket)
    try:
        run_history = _get_run_history()

        # Include last run data for late joiners
        last_run = None
        run_file_path = (SESSION_STATE.get("run_file") or
                         SESSION_STATE.get("last_run_file"))
        if run_file_path:
            try:
                last_run = json.loads(Path(run_file_path).read_text())
            except Exception:
                pass

        init_msg = {
            "ui_type": "init",
            "state": SESSION_STATE,
            "buffer": list(EVENT_BUFFER),
            "last_run": last_run,
            "run_history": run_history,
        }
        await websocket.send(json.dumps(init_msg))

        async for _ in websocket:
            pass  # no commands accepted — dashboard is read-only
    except Exception as e:
        # Log unexpected errors; normal disconnects raise ConnectionClosed which is fine
        log.debug("WebSocket handler error for %s: %s", remote, e)
    finally:
        CLIENTS.discard(websocket)
        log.info("WebSocket client disconnected: %s", remote)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    log.info("dblCheck Dashboard bridge starting on port %d", PORT)
    async with serve(ws_handler, HOST, PORT, process_request=_http_handler):
        log.info("Listening on http://%s:%d  (HTTP + WebSocket)", HOST, PORT)
        await watch_state_file()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Dashboard bridge stopped")
