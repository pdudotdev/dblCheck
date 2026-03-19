"""UT-017 — Transport dispatcher (transport/__init__.py).

Tests execute_command() error wrapping, unknown-device handling, and
the structured result shape — using a mock at the ssh layer (one level deeper
than the conftest replacement) so the actual dispatcher code runs.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ── Stub dependencies the transport module imports ────────────────────────────
# core.settings and core.inventory are already stubbed by conftest;
# we need to ensure the transport.__init__ module can be loaded with
# those stubs without the SSH layer making real connections.

# Ensure core.settings is stubbed
if "core.settings" not in sys.modules:
    _settings = ModuleType("core.settings")
    _settings.USERNAME = "test"
    _settings.PASSWORD = "test"
    _settings.SSH_TIMEOUT_OPS = 30
    _settings.SSH_RETRIES = 1
    _settings.SSH_RETRY_DELAY = 2
    _settings.SSH_MAX_CONCURRENT = 5
    sys.modules["core.settings"] = _settings

# Stub transport.ssh so the real SSH code never runs
_ssh_mod = ModuleType("transport.ssh")
_ssh_mod.execute_ssh = AsyncMock(return_value="raw device output")
_ssh_mod.open_session = AsyncMock()
_ssh_mod.close_session = AsyncMock()
sys.modules["transport.ssh"] = _ssh_mod

# Now load transport/__init__.py directly
# (conftest replaces the whole "transport" module; we load it from disk here)
_spec = importlib.util.spec_from_file_location(
    "_real_transport", _ROOT / "transport" / "__init__.py"
)
_transport = importlib.util.module_from_spec(_spec)
# Inject the stubs the module imports
_transport.__dict__["asyncio"] = asyncio

# Patch sys.modules so imports inside the module resolve correctly
with patch.dict("sys.modules", {
    "core.inventory": sys.modules.get("core.inventory"),
    "core.settings": sys.modules["core.settings"],
    "transport.ssh": _ssh_mod,
}):
    _spec.loader.exec_module(_transport)

execute_command = _transport.execute_command

# Use the inventory from conftest (already populated with NETWORK.json devices)
_DEVICES = sys.modules["core.inventory"].devices


# ── Unknown device ────────────────────────────────────────────────────────────

def test_execute_command_unknown_device_returns_error():
    result = asyncio.run(execute_command("TOTALLY_UNKNOWN_DEVICE", "show version"))
    assert "error" in result
    assert result["error"] == "Unknown device"


def test_execute_command_unknown_device_no_raw_field():
    result = asyncio.run(execute_command("TOTALLY_UNKNOWN_DEVICE", "show version"))
    assert "raw" not in result


# ── Successful execution ───────────────────────────────────────────────────────

def test_execute_command_known_device_returns_raw(monkeypatch):
    _ssh_mod.execute_ssh.reset_mock()
    _ssh_mod.execute_ssh.return_value = "some raw output"
    # Use a device we know is in the test inventory
    device_name = next(iter(_DEVICES))
    result = asyncio.run(execute_command(device_name, "show version"))
    assert "error" not in result
    assert result["raw"] == "some raw output"
    assert result["device"] == device_name


def test_execute_command_result_contains_cli_style(monkeypatch):
    _ssh_mod.execute_ssh.reset_mock()
    _ssh_mod.execute_ssh.return_value = "output"
    device_name = next(iter(_DEVICES))
    result = asyncio.run(execute_command(device_name, "show version"))
    assert "cli_style" in result
    assert result["cli_style"] == _DEVICES[device_name]["cli_style"]


def test_execute_command_result_contains_command(monkeypatch):
    _ssh_mod.execute_ssh.reset_mock()
    _ssh_mod.execute_ssh.return_value = "output"
    device_name = next(iter(_DEVICES))
    result = asyncio.run(execute_command(device_name, "show ip ospf neighbor"))
    assert result.get("_command") == "show ip ospf neighbor"


# ── Error wrapping ─────────────────────────────────────────────────────────────

def test_execute_command_ssh_exception_returns_error_dict():
    _ssh_mod.execute_ssh.reset_mock()
    _ssh_mod.execute_ssh.side_effect = Exception("SSH timeout")
    device_name = next(iter(_DEVICES))
    result = asyncio.run(execute_command(device_name, "show version"))
    assert "error" in result
    assert "SSH timeout" in result["error"]
    assert result["device"] == device_name
    assert result["cli_style"] == _DEVICES[device_name]["cli_style"]
    # Reset for other tests
    _ssh_mod.execute_ssh.side_effect = None
    _ssh_mod.execute_ssh.return_value = "output"


def test_execute_command_ssh_exception_no_raw_field():
    _ssh_mod.execute_ssh.reset_mock()
    _ssh_mod.execute_ssh.side_effect = RuntimeError("connection refused")
    device_name = next(iter(_DEVICES))
    result = asyncio.run(execute_command(device_name, "show version"))
    assert "raw" not in result
    _ssh_mod.execute_ssh.side_effect = None
    _ssh_mod.execute_ssh.return_value = "output"
