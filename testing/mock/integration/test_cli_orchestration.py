"""IT-003 — CLI _run() orchestration: gate logic and exit codes.

Tests the credential validation gate, inventory gate, intent gate,
and exit-code contract — without running real SSH or the AI diagnosis subprocess.
"""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ── Load cli/dblcheck.py for testing ─────────────────────────────────────────
# We import the module directly and patch the heavy IO at the function level.

# Make sure core stubs are in place (conftest does this for mock/ tests)
# but we need core.vault and core.settings present.
for _name in ("core", "core.vault", "core.settings", "core.logging_config",
              "core.inventory", "core.netbox", "core.jira_client"):
    if _name not in sys.modules:
        _m = ModuleType(_name)
        sys.modules[_name] = _m

sys.modules["core.vault"].get_secret = lambda *a, **kw: "test"
sys.modules["core.vault"].credential_source = lambda: ".env"
sys.modules["core.settings"].USERNAME = "test"
sys.modules["core.settings"].PASSWORD = "test"
sys.modules["core.settings"].SSH_MAX_CONCURRENT = 5
sys.modules["core.settings"].SSH_TIMEOUT_OPS = 30
sys.modules["core.settings"].SSH_RETRIES = 1
sys.modules["core.settings"].SSH_RETRY_DELAY = 2
sys.modules["core.logging_config"].setup_logging = lambda: None
sys.modules["core.jira_client"]._is_configured = lambda: False
sys.modules["core.jira_client"].create_issue = AsyncMock(return_value=None)
sys.modules["core.jira_client"].add_comment = AsyncMock()

# Stub transport
if "transport" not in sys.modules:
    _t = ModuleType("transport")
    _t.execute_command = AsyncMock(return_value={"raw": "", "cli_style": "ios", "device": "TEST"})
    _t.open_device_session = AsyncMock()
    _t.close_device_session = AsyncMock()
    sys.modules["transport"] = _t

_spec = importlib.util.spec_from_file_location(
    "_real_cli", _ROOT / "cli" / "dblcheck.py"
)
_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cli)

_run = _cli._run
_failure_fingerprint = _cli._failure_fingerprint

# ── Arg stub ──────────────────────────────────────────────────────────────────

def _args(headless=True, no_diagnose=True):
    a = MagicMock()
    a.headless = headless
    a.no_diagnose = no_diagnose
    return a


# ── Credential gate ────────────────────────────────────────────────────────────

def test_run_exits_1_when_no_username(tmp_path):
    with (
        patch.object(sys.modules["core.settings"], "USERNAME", ""),
        patch.object(sys.modules["core.settings"], "PASSWORD", "test"),
        patch.object(_cli, "DATA_DIR", tmp_path),
        patch.object(_cli, "RUNS_DIR", tmp_path / "runs"),
        patch.object(_cli, "STATE_FILE", tmp_path / "state.json"),
        patch.object(_cli, "LOCK_FILE", tmp_path / ".lock"),
    ):
        code = asyncio.run(_run(_args()))
    assert code == 1


def test_run_exits_1_when_no_password(tmp_path):
    with (
        patch.object(sys.modules["core.settings"], "USERNAME", "test"),
        patch.object(sys.modules["core.settings"], "PASSWORD", ""),
        patch.object(_cli, "DATA_DIR", tmp_path),
        patch.object(_cli, "STATE_FILE", tmp_path / "state.json"),
        patch.object(_cli, "LOCK_FILE", tmp_path / ".lock"),
    ):
        code = asyncio.run(_run(_args()))
    assert code == 1


# ── Inventory gate ─────────────────────────────────────────────────────────────

def test_run_exits_1_when_no_devices(tmp_path):
    with (
        patch.object(sys.modules["core.settings"], "USERNAME", "test"),
        patch.object(sys.modules["core.settings"], "PASSWORD", "test"),
        patch.object(sys.modules["core.inventory"], "devices", {}),
        patch.object(_cli, "DATA_DIR", tmp_path),
        patch.object(_cli, "STATE_FILE", tmp_path / "state.json"),
        patch.object(_cli, "LOCK_FILE", tmp_path / ".lock"),
    ):
        code = asyncio.run(_run(_args()))
    assert code == 1


# ── Intent gate ────────────────────────────────────────────────────────────────

def test_run_exits_1_when_intent_unavailable(tmp_path):
    with (
        patch.object(sys.modules["core.settings"], "USERNAME", "test"),
        patch.object(sys.modules["core.settings"], "PASSWORD", "test"),
        patch.object(sys.modules["core.inventory"], "devices", {"R1": {"host": "10.0.0.1"}}),
        patch.object(sys.modules["core.inventory"], "inventory_source", "test"),
        patch.object(_cli, "load_intent", return_value=None),
        patch.object(_cli, "DATA_DIR", tmp_path),
        patch.object(_cli, "RUNS_DIR", tmp_path / "runs"),
        patch.object(_cli, "STATE_FILE", tmp_path / "state.json"),
        patch.object(_cli, "LOCK_FILE", tmp_path / ".lock"),
    ):
        code = asyncio.run(_run(_args()))
    assert code == 1


# ── Exit code contract ─────────────────────────────────────────────────────────

def test_run_exits_0_when_all_pass(tmp_path):
    """Exit 0 when there are no failures."""
    from validation.assertions import AssertionResult
    passing_result = MagicMock()
    passing_result.result = AssertionResult.PASS

    with (
        patch.object(sys.modules["core.settings"], "USERNAME", "test"),
        patch.object(sys.modules["core.settings"], "PASSWORD", "test"),
        patch.object(sys.modules["core.inventory"], "devices", {"R1": {"host": "10.0.0.1"}}),
        patch.object(sys.modules["core.inventory"], "inventory_source", "test"),
        patch.object(_cli, "load_intent", return_value={"routers": {"R1": {}}}),
        patch.object(_cli, "derive_assertions", return_value=[MagicMock()]),
        patch.object(_cli, "collect_state", new_callable=AsyncMock, return_value={}),
        patch.object(_cli, "evaluate", return_value=[passing_result]),
        patch.object(_cli, "format_run_dict", return_value={"summary": {}, "assertions": [], "timestamp": "T", "duration_sec": 0.1}),
        patch.object(_cli, "format_text", return_value=""),
        patch.object(_cli, "DATA_DIR", tmp_path),
        patch.object(_cli, "RUNS_DIR", tmp_path / "runs"),
        patch.object(_cli, "SESSIONS_DIR", tmp_path / "sessions"),
        patch.object(_cli, "STATE_FILE", tmp_path / "state.json"),
        patch.object(_cli, "LOCK_FILE", tmp_path / ".lock"),
        patch.object(_cli, "INCIDENT_FILE", tmp_path / "incident.json"),
        patch.object(_cli, "_cleanup_old_files"),
    ):
        (tmp_path / "runs").mkdir(exist_ok=True)
        (tmp_path / "sessions").mkdir(exist_ok=True)
        code = asyncio.run(_run(_args()))
    assert code == 0


def test_run_exits_2_when_failures_present(tmp_path):
    """Exit 2 when one or more assertions fail."""
    from validation.assertions import AssertionResult
    failing_result = MagicMock()
    failing_result.result = AssertionResult.FAIL
    failing_result.assertion = MagicMock()
    failing_result.assertion.device = "R1"
    failing_result.assertion.type = MagicMock()
    failing_result.assertion.type.value = "interface_up"
    failing_result.assertion.expected = "up/up"

    with (
        patch.object(sys.modules["core.settings"], "USERNAME", "test"),
        patch.object(sys.modules["core.settings"], "PASSWORD", "test"),
        patch.object(sys.modules["core.inventory"], "devices", {"R1": {"host": "10.0.0.1"}}),
        patch.object(sys.modules["core.inventory"], "inventory_source", "test"),
        patch.object(_cli, "load_intent", return_value={"routers": {"R1": {}}}),
        patch.object(_cli, "derive_assertions", return_value=[MagicMock()]),
        patch.object(_cli, "collect_state", new_callable=AsyncMock, return_value={}),
        patch.object(_cli, "evaluate", return_value=[failing_result]),
        patch.object(_cli, "format_run_dict", return_value={"summary": {}, "assertions": [], "timestamp": "T", "duration_sec": 0.1}),
        patch.object(_cli, "format_text", return_value=""),
        patch.object(_cli, "DATA_DIR", tmp_path),
        patch.object(_cli, "RUNS_DIR", tmp_path / "runs"),
        patch.object(_cli, "SESSIONS_DIR", tmp_path / "sessions"),
        patch.object(_cli, "STATE_FILE", tmp_path / "state.json"),
        patch.object(_cli, "LOCK_FILE", tmp_path / ".lock"),
        patch.object(_cli, "INCIDENT_FILE", tmp_path / "incident.json"),
        patch.object(_cli, "_cleanup_old_files"),
    ):
        (tmp_path / "runs").mkdir(exist_ok=True)
        (tmp_path / "sessions").mkdir(exist_ok=True)
        code = asyncio.run(_run(_args()))
    assert code == 2


# ── Fingerprint / diagnosis skip ──────────────────────────────────────────────

def test_failure_fingerprint_stable():
    """Same failure set always produces the same fingerprint."""
    from validation.assertions import AssertionType, Assertion, AssertionResult, EvaluatedAssertion
    a = Assertion(
        type=AssertionType.INTERFACE_UP,
        device="R1",
        description="R1 Gi2 should be up/up",
        expected="up/up",
        interface="GigabitEthernet2",
    )
    ea = EvaluatedAssertion(assertion=a, result=AssertionResult.FAIL, actual="down/down")
    fp1 = _failure_fingerprint([ea])
    fp2 = _failure_fingerprint([ea])
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_failure_fingerprint_differs_for_different_failures():
    from validation.assertions import AssertionType, Assertion, AssertionResult, EvaluatedAssertion
    a1 = Assertion(type=AssertionType.INTERFACE_UP, device="R1",
                   description="", expected="up/up")
    a2 = Assertion(type=AssertionType.BGP_SESSION, device="R2",
                   description="", expected="Established")
    ea1 = EvaluatedAssertion(assertion=a1, result=AssertionResult.FAIL)
    ea2 = EvaluatedAssertion(assertion=a2, result=AssertionResult.FAIL)
    assert _failure_fingerprint([ea1]) != _failure_fingerprint([ea2])
