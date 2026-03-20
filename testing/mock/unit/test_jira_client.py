"""UT-015 — Jira client: ADF conversion and configuration check.

Tests _to_adf(), _inline_to_adf(), and _is_configured() as pure/near-pure functions.
HTTP functions (create_issue, add_comment, resolve_issue) are tested for the
configuration gate — they return None / do nothing when Jira is not configured.
"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Load the real jira_client, stubbing out hvac/vault dependencies
if "core.vault" not in sys.modules:
    _vault = ModuleType("core.vault")
    _vault.get_secret = lambda *a, **kw: None
    sys.modules["core.vault"] = _vault

# httpx must be real — jira_client imports it
import httpx

_spec = importlib.util.spec_from_file_location(
    "_real_jira_client", _ROOT / "core" / "jira_client.py"
)
_jira = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_jira)

_to_adf = _jira._to_adf
_inline_to_adf = _jira._inline_to_adf
_is_configured = _jira._is_configured


# ── _inline_to_adf ────────────────────────────────────────────────────────────

def test_inline_plain_text():
    nodes = _inline_to_adf("plain text")
    assert len(nodes) == 1
    assert nodes[0] == {"type": "text", "text": "plain text"}


def test_inline_bold():
    nodes = _inline_to_adf("**bold text**")
    assert any(n.get("marks") == [{"type": "strong"}] for n in nodes)
    assert any(n.get("text") == "bold text" for n in nodes)


def test_inline_code():
    nodes = _inline_to_adf("`inline code`")
    assert any(n.get("marks") == [{"type": "code"}] for n in nodes)
    assert any(n.get("text") == "inline code" for n in nodes)


def test_inline_mixed():
    nodes = _inline_to_adf("prefix **bold** middle `code` suffix")
    texts = [n.get("text", "") for n in nodes]
    assert "prefix " in texts
    assert "bold" in texts
    assert any("middle" in t for t in texts)
    assert "code" in texts
    assert any("suffix" in t for t in texts)


def test_inline_empty_returns_placeholder():
    nodes = _inline_to_adf("")
    assert nodes == [{"type": "text", "text": " "}]


# ── _to_adf ───────────────────────────────────────────────────────────────────

def test_to_adf_plain_paragraph():
    doc = _to_adf("Simple paragraph.")
    assert doc["version"] == 1
    assert doc["type"] == "doc"
    paras = [n for n in doc["content"] if n["type"] == "paragraph"]
    assert len(paras) >= 1
    text = paras[0]["content"][0]["text"]
    assert "Simple paragraph." in text


def test_to_adf_heading():
    doc = _to_adf("## Section Title")
    headings = [n for n in doc["content"] if n["type"] == "heading"]
    assert len(headings) == 1
    assert headings[0]["attrs"]["level"] == 2
    assert any("Section Title" in c.get("text", "") for c in headings[0]["content"])


def test_to_adf_code_block():
    doc = _to_adf("```\nshow ip route\n```")
    code_blocks = [n for n in doc["content"] if n["type"] == "codeBlock"]
    assert len(code_blocks) == 1
    assert "show ip route" in code_blocks[0]["content"][0]["text"]


def test_to_adf_full_diagnosis_sample():
    text = (
        "## Failure 1 — R1 OSPF neighbor missing\n\n"
        "**Root cause:** Interface `GigabitEthernet2` is down.\n\n"
        "**Evidence:** `show ip ospf neighbor` returned no neighbors.\n\n"
        "```\nshow ip ospf neighbor\nNeighbor ID  ... 0 interfaces\n```"
    )
    doc = _to_adf(text)
    assert doc["type"] == "doc"
    headings = [n for n in doc["content"] if n["type"] == "heading"]
    assert len(headings) == 1
    code_blocks = [n for n in doc["content"] if n["type"] == "codeBlock"]
    assert len(code_blocks) == 1


def test_to_adf_empty_returns_placeholder():
    doc = _to_adf("")
    assert doc["type"] == "doc"
    assert len(doc["content"]) >= 1


def test_to_adf_empty_lines_skipped():
    doc = _to_adf("line1\n\n\nline2")
    paras = [n for n in doc["content"] if n["type"] == "paragraph"]
    assert len(paras) == 2


# ── _is_configured ────────────────────────────────────────────────────────────

def test_is_configured_false_when_no_env_vars(monkeypatch):
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)
    # Ensure vault returns no token
    sys.modules["core.vault"].get_secret = lambda *a, **kw: None
    assert _is_configured() is False


def test_is_configured_false_when_partial_config(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)
    sys.modules["core.vault"].get_secret = lambda *a, **kw: None
    assert _is_configured() is False


def test_is_configured_true_when_all_fields_present(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "NET")
    sys.modules["core.vault"].get_secret = lambda path, key, **kw: "fake_token" if key == "token" else None
    assert _is_configured() is True


# ── create_issue — unconfigured guard ─────────────────────────────────────────

def test_create_issue_returns_none_when_not_configured(monkeypatch):
    import asyncio
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)
    sys.modules["core.vault"].get_secret = lambda *a, **kw: None
    result = asyncio.run(_jira.create_issue("Test summary", "Test description"))
    assert result is None


# ── HTTP operation tests: create_issue, add_comment, resolve_issue ────────────
# Uses unittest.mock to patch httpx.AsyncClient so no real HTTP is made.

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch as _patch


@pytest.fixture
def configured_jira(monkeypatch):
    """Set all required Jira env vars and reset module state for HTTP tests."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "NET")
    sys.modules["core.vault"].get_secret = lambda *a, **kw: "fake_token"
    _jira._config_warned = False  # reset warning sentinel between tests


def _make_response(status_code, json_data=None, text=""):
    """Create a mock httpx Response-like object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    resp.text = text
    return resp


def _async_client(post=None, get=None, post_side_effect=None, get_side_effect=None):
    """Create a mock httpx.AsyncClient async context manager."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    if post_side_effect is not None:
        client.post = AsyncMock(side_effect=post_side_effect)
    elif post is not None:
        client.post = AsyncMock(return_value=post)
    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    elif get is not None:
        client.get = AsyncMock(return_value=get)
    return client


# ── create_issue ──────────────────────────────────────────────────────────────

def test_create_issue_success_returns_key(configured_jira):
    client = _async_client(post=_make_response(201, {"key": "NET-42"}))
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        result = asyncio.run(_jira.create_issue("Test summary", "Test description"))
    assert result == "NET-42"


def test_create_issue_fallback_to_task_on_400(configured_jira):
    # First POST (configured issue type) → 400; second POST (Task fallback) → 201.
    client = _async_client()
    client.post = AsyncMock(side_effect=[
        _make_response(400),
        _make_response(201, {"key": "NET-43"}),
    ])
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        result = asyncio.run(_jira.create_issue("Test", "Desc"))
    assert result == "NET-43"


def test_create_issue_server_error_returns_none(configured_jira):
    client = _async_client(post=_make_response(500, text="Internal Server Error"))
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        result = asyncio.run(_jira.create_issue("Test", "Desc"))
    assert result is None


def test_create_issue_connection_error_returns_none(configured_jira):
    client = _async_client(post_side_effect=httpx.ConnectError("connection refused"))
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        result = asyncio.run(_jira.create_issue("Test", "Desc"))
    assert result is None


# ── add_comment ───────────────────────────────────────────────────────────────

def test_add_comment_success(configured_jira):
    client = _async_client(post=_make_response(201))
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        asyncio.run(_jira.add_comment("NET-42", "comment text"))  # must not raise


def test_add_comment_server_error_no_crash(configured_jira):
    # A 500 from the Jira server is logged and swallowed — never raised to caller.
    client = _async_client(post=_make_response(500, text="server error"))
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        asyncio.run(_jira.add_comment("NET-42", "comment text"))  # must not raise


# ── resolve_issue ─────────────────────────────────────────────────────────────

def test_resolve_issue_success(configured_jira):
    transitions = {"transitions": [{"id": "31", "name": "Done"}]}
    client = _async_client(
        get=_make_response(200, transitions),
        post=_make_response(204),
    )
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        asyncio.run(_jira.resolve_issue("NET-42", "resolved"))  # must not raise
    client.get.assert_called_once()
    client.post.assert_called_once()


def test_resolve_issue_no_matching_transition_falls_back_to_comment(configured_jira):
    # No "done/resolve/close" keyword — fallback to add_comment.
    transitions = {"transitions": [{"id": "1", "name": "Reopen"}, {"id": "2", "name": "In Progress"}]}
    client = _async_client(
        get=_make_response(200, transitions),
        post=_make_response(201),
    )
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        asyncio.run(_jira.resolve_issue("NET-42", "resolved"))
    # POST called once: the fallback comment (no transition was attempted)
    client.post.assert_called_once()
    comment_url = client.post.call_args[0][0]
    assert "comment" in comment_url


def test_resolve_issue_transition_failure_falls_back_to_comment(configured_jira):
    # Transition found but POST returns 500 → fallback to add_comment.
    transitions = {"transitions": [{"id": "31", "name": "Done"}]}
    client = _async_client(get=_make_response(200, transitions))
    client.post = AsyncMock(side_effect=[
        _make_response(500),   # transition POST fails
        _make_response(201),   # fallback comment POST succeeds
    ])
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        asyncio.run(_jira.resolve_issue("NET-42", "resolved"))
    assert client.post.call_count == 2


def test_resolve_issue_transitions_fetch_fails_falls_back_to_comment(configured_jira):
    # GET transitions returns non-200 → log warning + fallback to add_comment.
    client = _async_client(
        get=_make_response(500),
        post=_make_response(201),
    )
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        asyncio.run(_jira.resolve_issue("NET-42", "resolved"))
    client.post.assert_called_once()


def test_resolve_issue_connection_error_falls_back_to_comment(configured_jira):
    # ConnectError during GET → caught by except clause → add_comment called.
    client = _async_client(
        get_side_effect=httpx.ConnectError("connection refused"),
        post=_make_response(201),
    )
    with _patch.object(_jira.httpx, "AsyncClient", return_value=client):
        asyncio.run(_jira.resolve_issue("NET-42", "resolved"))
    client.post.assert_called_once()
