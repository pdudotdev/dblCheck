"""UT-014 — WebSocket bridge: pure functions and security-critical paths.

Tests parse_ndjson_line(), _flatten_content(), _strip_tool_prefix(),
_token_from_path(), and the _http_handler() path-traversal guard and token auth.
"""
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

# ── Load the real ws_bridge module with its optional dependencies mocked ──────
# ws_bridge imports websockets and core.vault at module level.
# We stub those so we can import the pure functions without a running server.

_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Stub websockets before import
_ws_mod = ModuleType("websockets")
_ws_asyncio = ModuleType("websockets.asyncio")
_ws_asyncio_server = ModuleType("websockets.asyncio.server")
_ws_asyncio_server.serve = MagicMock()
_ws_asyncio_server.broadcast = MagicMock()
_ws_datastructures = ModuleType("websockets.datastructures")

class _Headers(dict):
    pass
_ws_datastructures.Headers = _Headers

_ws_http11 = ModuleType("websockets.http11")
class _Response:
    def __init__(self, status, reason, headers, body):
        self.status_code = status
        self.reason = reason
        self.headers = headers
        self.body = body
_ws_http11.Response = _Response

for _name, _mod in [
    ("websockets", _ws_mod),
    ("websockets.asyncio", _ws_asyncio),
    ("websockets.asyncio.server", _ws_asyncio_server),
    ("websockets.datastructures", _ws_datastructures),
    ("websockets.http11", _ws_http11),
]:
    if _name not in sys.modules:
        sys.modules[_name] = _mod

# Stub core.vault (may already be stubbed by conftest, but be safe)
if "core.vault" not in sys.modules:
    _vault = ModuleType("core.vault")
    _vault.get_secret = lambda *a, **kw: None
    sys.modules["core.vault"] = _vault
else:
    sys.modules["core.vault"].get_secret = lambda *a, **kw: None

# Now load the real ws_bridge
_spec = importlib.util.spec_from_file_location(
    "_real_ws_bridge", _ROOT / "dashboard" / "ws_bridge.py"
)
_bridge = importlib.util.module_from_spec(_spec)
_bridge._DASHBOARD_TOKEN = ""  # disable auth for most tests
_spec.loader.exec_module(_bridge)

parse_ndjson_line = _bridge.parse_ndjson_line
_flatten_content = _bridge._flatten_content
_strip_tool_prefix = _bridge._strip_tool_prefix
_token_from_path = _bridge._token_from_path
_get_run_history = _bridge._get_run_history


# ── _flatten_content ──────────────────────────────────────────────────────────

def test_flatten_content_plain_string():
    assert _flatten_content("hello") == "hello"


def test_flatten_content_list_of_dicts():
    content = [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}]
    result = _flatten_content(content)
    assert "part1" in result
    assert "part2" in result


def test_flatten_content_empty_list():
    assert _flatten_content([]) == ""


def test_flatten_content_list_skips_non_dicts():
    content = [{"type": "text", "text": "valid"}, "not_a_dict"]
    result = _flatten_content(content)
    assert "valid" in result


# ── _strip_tool_prefix ────────────────────────────────────────────────────────

def test_strip_tool_prefix_mcp_tool():
    name, is_mcp = _strip_tool_prefix("mcp__dblcheck__get_ospf")
    assert name == "get_ospf"
    assert is_mcp is True


def test_strip_tool_prefix_non_mcp():
    name, is_mcp = _strip_tool_prefix("some_other_tool")
    assert name == "some_other_tool"
    assert is_mcp is False


def test_strip_tool_prefix_empty():
    name, is_mcp = _strip_tool_prefix("")
    assert name == ""
    assert is_mcp is False


# ── _token_from_path ──────────────────────────────────────────────────────────

def test_token_from_path_extracts_token():
    token = _token_from_path("/?token=mysecrettoken")
    assert token == "mysecrettoken"


def test_token_from_path_no_token():
    token = _token_from_path("/")
    assert token is None


def test_token_from_path_other_params():
    token = _token_from_path("/api/run/run-001?other=value")
    assert token is None


def test_token_from_path_token_with_other_params():
    token = _token_from_path("/?foo=bar&token=abc123&baz=qux")
    assert token == "abc123"


# ── parse_ndjson_line ─────────────────────────────────────────────────────────

def _clear_tool_inputs():
    """Reset module-level _tool_inputs state between tests."""
    _bridge._tool_inputs.clear()
    _bridge._thinking_emitted = False


def test_parse_ndjson_invalid_json():
    _clear_tool_inputs()
    result = parse_ndjson_line("not valid json")
    assert result == []


def test_parse_ndjson_empty_string():
    _clear_tool_inputs()
    assert parse_ndjson_line("") == []


def test_parse_ndjson_result_event():
    _clear_tool_inputs()
    line = json.dumps({"type": "result", "total_cost_usd": 0.05})
    events = parse_ndjson_line(line)
    assert len(events) == 1
    assert events[0]["ui_type"] == "session_end"
    assert events[0]["cost"] == 0.05


def test_parse_ndjson_text_delta():
    _clear_tool_inputs()
    line = json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Finding 1"}
        }
    })
    events = parse_ndjson_line(line)
    assert len(events) == 1
    assert events[0]["ui_type"] == "reasoning"
    assert events[0]["text"] == "Finding 1"


def test_parse_ndjson_empty_text_delta_produces_no_event():
    _clear_tool_inputs()
    line = json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": ""}
        }
    })
    events = parse_ndjson_line(line)
    assert events == []


def test_parse_ndjson_tool_start():
    _clear_tool_inputs()
    line = json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "tool_abc",
                "name": "mcp__dblcheck__get_ospf",
            }
        }
    })
    events = parse_ndjson_line(line)
    assert len(events) == 1
    e = events[0]
    assert e["ui_type"] == "tool_start"
    assert e["tool"] == "get_ospf"
    assert e["id"] == "tool_abc"
    assert e["is_mcp"] is True


def test_parse_ndjson_tool_input_complete():
    _clear_tool_inputs()
    # Simulate: tool_start followed by input_json_delta then content_block_stop
    start_line = json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_start",
            "index": 2,
            "content_block": {"type": "tool_use", "id": "tid1", "name": "mcp__dblcheck__get_bgp"}
        }
    })
    parse_ndjson_line(start_line)

    delta_line = json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "index": 2,
            "delta": {"type": "input_json_delta", "partial_json": '{"device":"R1","query":"summary"}'}
        }
    })
    parse_ndjson_line(delta_line)

    stop_line = json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 2}
    })
    events = parse_ndjson_line(stop_line)
    assert len(events) == 1
    e = events[0]
    assert e["ui_type"] == "tool_input_complete"
    assert e["tool"] == "get_bgp"
    assert e["input"]["device"] == "R1"
    assert e["input"]["query"] == "summary"
    assert e["is_mcp"] is True


def test_parse_ndjson_thinking_delta_emitted_once():
    _clear_tool_inputs()
    line = json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "..."}
        }
    })
    events1 = parse_ndjson_line(line)
    events2 = parse_ndjson_line(line)
    # First thinking_delta → reasoning_status event
    assert any(e.get("ui_type") == "reasoning_status" for e in events1)
    # Second thinking_delta → no event (already emitted)
    assert not any(e.get("ui_type") == "reasoning_status" for e in events2)


def test_parse_ndjson_unknown_type_returns_empty():
    _clear_tool_inputs()
    line = json.dumps({"type": "unknown_event_type"})
    assert parse_ndjson_line(line) == []


def test_parse_ndjson_tool_result_from_user_message():
    _clear_tool_inputs()
    line = json.dumps({
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": "tid99", "content": "show output here"}
            ]
        }
    })
    events = parse_ndjson_line(line)
    assert len(events) == 1
    assert events[0]["ui_type"] == "tool_result"
    assert events[0]["id"] == "tid99"
    assert events[0]["output"] == "show output here"


# ── _http_handler path traversal guard ───────────────────────────────────────

def _make_request(path: str, method: str = "GET"):
    req = MagicMock()
    req.path = path
    req.method = method
    req.headers = MagicMock()
    req.headers.get = MagicMock(return_value="")
    return req


def test_http_handler_path_traversal_blocked(tmp_path):
    # Temporarily point RUNS_DIR to a real temp directory
    original_runs_dir = _bridge.RUNS_DIR
    _bridge.RUNS_DIR = tmp_path / "runs"
    _bridge.RUNS_DIR.mkdir()
    _bridge._DASHBOARD_TOKEN = ""
    try:
        req = _make_request("/api/run/../../etc/passwd")
        resp = _bridge._http_handler(None, req)
        assert resp.status_code == 404
    finally:
        _bridge.RUNS_DIR = original_runs_dir


def test_http_handler_valid_run_file_returns_200(tmp_path):
    original_runs_dir = _bridge.RUNS_DIR
    _bridge.RUNS_DIR = tmp_path / "runs"
    _bridge.RUNS_DIR.mkdir()
    _bridge._DASHBOARD_TOKEN = ""
    run_file = _bridge.RUNS_DIR / "run-20260101T000000Z.json"
    run_file.write_text('{"summary": {"total": 5}}')
    try:
        req = _make_request("/api/run/run-20260101T000000Z")
        resp = _bridge._http_handler(None, req)
        assert resp.status_code == 200
        assert b"total" in resp.body
    finally:
        _bridge.RUNS_DIR = original_runs_dir


def test_http_handler_missing_run_returns_404(tmp_path):
    original_runs_dir = _bridge.RUNS_DIR
    _bridge.RUNS_DIR = tmp_path / "runs"
    _bridge.RUNS_DIR.mkdir()
    _bridge._DASHBOARD_TOKEN = ""
    try:
        req = _make_request("/api/run/run-nonexistent")
        resp = _bridge._http_handler(None, req)
        assert resp.status_code == 404
    finally:
        _bridge.RUNS_DIR = original_runs_dir


def test_http_handler_token_auth_rejects_wrong_token():
    _bridge._DASHBOARD_TOKEN = "correct-token"
    try:
        req = _make_request("/?token=wrong-token")
        resp = _bridge._http_handler(None, req)
        assert resp.status_code == 401
    finally:
        _bridge._DASHBOARD_TOKEN = ""


def test_http_handler_token_auth_accepts_correct_token(tmp_path):
    _bridge._DASHBOARD_TOKEN = "correct-token"
    original_index = _bridge.INDEX_HTML
    index_file = tmp_path / "index.html"
    index_file.write_bytes(b"<html></html>")
    _bridge.INDEX_HTML = index_file
    try:
        req = _make_request("/?token=correct-token")
        resp = _bridge._http_handler(None, req)
        assert resp.status_code == 200
    finally:
        _bridge._DASHBOARD_TOKEN = ""
        _bridge.INDEX_HTML = original_index


def test_http_handler_websocket_upgrade_passes_through():
    _bridge._DASHBOARD_TOKEN = "correct-token"
    try:
        req = _make_request("/")
        req.headers.get = MagicMock(return_value="websocket")
        resp = _bridge._http_handler(None, req)
        assert resp is None  # WebSocket upgrade: pass through to ws_handler
    finally:
        _bridge._DASHBOARD_TOKEN = ""


def test_http_handler_favicon_returns_204():
    _bridge._DASHBOARD_TOKEN = ""
    req = _make_request("/favicon.ico")
    resp = _bridge._http_handler(None, req)
    assert resp.status_code == 204


def test_http_handler_unknown_path_returns_404():
    _bridge._DASHBOARD_TOKEN = ""
    req = _make_request("/not/a/real/path")
    resp = _bridge._http_handler(None, req)
    assert resp.status_code == 404
