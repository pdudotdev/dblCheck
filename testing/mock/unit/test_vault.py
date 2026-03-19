"""UT-013 — Vault client: get_secret() and credential_source()."""
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ── Import the real vault module directly (bypassing conftest stubs) ──────────
# conftest.py replaces core.vault with a stub. We need the real implementation.
# Import it by path before sys.modules is patched.
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

import importlib, types

# Load the real vault source as a standalone module to avoid conftest stub
_vault_spec = importlib.util.spec_from_file_location(
    "_real_vault", _ROOT / "core" / "vault.py"
)
_vault_mod = importlib.util.module_from_spec(_vault_spec)
# Inject a real logging module so vault.py's log = logging.getLogger(...) works
import logging as _logging
_vault_mod.__dict__["logging"] = _logging
_vault_mod.__dict__["os"] = __import__("os")
_vault_spec.loader.exec_module(_vault_mod)

get_secret = _vault_mod.get_secret
credential_source = _vault_mod.credential_source
_VAULT_FAILED = _vault_mod._VAULT_FAILED


def _clear_cache():
    """Reset vault module cache between tests."""
    _vault_mod._cache.clear()


# ── No Vault configured ────────────────────────────────────────────────────────

def test_no_vault_addr_uses_env_fallback(monkeypatch):
    _clear_cache()
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setenv("MY_SECRET", "from_env")
    result = get_secret("some/path", "key", fallback_env="MY_SECRET")
    assert result == "from_env"


def test_no_vault_token_uses_env_fallback(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setenv("MY_SECRET", "env_value")
    result = get_secret("some/path", "key", fallback_env="MY_SECRET")
    assert result == "env_value"


def test_no_vault_no_fallback_env_returns_none(monkeypatch):
    _clear_cache()
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    result = get_secret("some/path", "key")
    assert result is None


# ── Vault configured, successful read ─────────────────────────────────────────

def _make_hvac_mock(data: dict):
    """Build a mock hvac.Client that returns `data` from KV v2 read."""
    client = MagicMock()
    client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": data}
    }
    return client


def test_vault_returns_secret_value(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    mock_client = _make_hvac_mock({"username": "admin", "password": "secret"})
    with patch.dict("sys.modules", {"hvac": MagicMock(Client=MagicMock(return_value=mock_client))}):
        result = get_secret("dblcheck/router", "username")
    assert result == "admin"


def test_vault_missing_key_falls_back_to_env(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    monkeypatch.setenv("MY_KEY", "env_fallback")
    mock_client = _make_hvac_mock({"other_key": "value"})
    with patch.dict("sys.modules", {"hvac": MagicMock(Client=MagicMock(return_value=mock_client))}):
        result = get_secret("dblcheck/router", "missing_key", fallback_env="MY_KEY")
    assert result == "env_fallback"


# ── Cache behavior ─────────────────────────────────────────────────────────────

def test_vault_caches_path_after_first_read(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    mock_client = _make_hvac_mock({"key": "value"})
    hvac_mock = MagicMock(Client=MagicMock(return_value=mock_client))
    with patch.dict("sys.modules", {"hvac": hvac_mock}):
        get_secret("dblcheck/router", "key")
        get_secret("dblcheck/router", "key")
    # Vault read should only be called once — second call uses cache
    assert mock_client.secrets.kv.v2.read_secret_version.call_count == 1


def test_vault_cache_serves_correct_value_on_second_call(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    mock_client = _make_hvac_mock({"username": "cached_user"})
    with patch.dict("sys.modules", {"hvac": MagicMock(Client=MagicMock(return_value=mock_client))}):
        first = get_secret("dblcheck/router", "username")
        second = get_secret("dblcheck/router", "username")
    assert first == second == "cached_user"


# ── _VAULT_FAILED sentinel ─────────────────────────────────────────────────────

def test_vault_unreachable_sets_failed_sentinel_and_uses_env(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    monkeypatch.setenv("ROUTER_USERNAME", "env_user")
    broken_client = MagicMock()
    broken_client.secrets.kv.v2.read_secret_version.side_effect = Exception("connection refused")
    with patch.dict("sys.modules", {"hvac": MagicMock(Client=MagicMock(return_value=broken_client))}):
        result = get_secret("dblcheck/router", "username", fallback_env="ROUTER_USERNAME")
    assert result == "env_user"
    # Sentinel should be set in cache
    assert _vault_mod._cache.get("dblcheck/router") is _VAULT_FAILED


def test_vault_failed_sentinel_uses_env_on_every_subsequent_call(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    monkeypatch.setenv("ROUTER_PASSWORD", "env_pass")
    # Pre-set the sentinel directly
    _vault_mod._cache["dblcheck/router"] = _VAULT_FAILED
    result = get_secret("dblcheck/router", "password", fallback_env="ROUTER_PASSWORD")
    assert result == "env_pass"


# ── credential_source() ────────────────────────────────────────────────────────

def test_credential_source_returns_vault_when_vault_loaded(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    mock_client = _make_hvac_mock({"username": "vaultuser"})
    with patch.dict("sys.modules", {"hvac": MagicMock(Client=MagicMock(return_value=mock_client))}):
        source = credential_source()
    assert source == "Vault"


def test_credential_source_returns_env_when_vault_failed(monkeypatch):
    _clear_cache()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    monkeypatch.setenv("ROUTER_USERNAME", "envuser")
    _vault_mod._cache["dblcheck/router"] = _VAULT_FAILED
    source = credential_source()
    assert source == ".env"


def test_credential_source_returns_env_when_vault_not_configured(monkeypatch):
    _clear_cache()
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setenv("ROUTER_USERNAME", "envuser")
    source = credential_source()
    assert source == ".env"
