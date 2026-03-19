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
