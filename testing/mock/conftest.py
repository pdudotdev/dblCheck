"""
Patch network-dependent modules via sys.modules before any project code is imported.

Loaded by pytest before any test file in testing/mock/unit/ or testing/mock/integration/.
All sys.modules injections happen at module level — before any test import.
"""
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Project root on sys.path ───────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Step 1: core package stub (required before core.* submodules) ──────────────
if "core" not in sys.modules:
    _core_mod = ModuleType("core")
    sys.modules["core"] = _core_mod

# core.vault — prevent Vault connections
_vault_mod = ModuleType("core.vault")
_vault_mod.get_secret = lambda path, key, fallback_env=None, quiet=False: "test"
_vault_mod.credential_source = lambda: ".env"
sys.modules["core.vault"] = _vault_mod

# core.settings — prevent loading from Vault / .env
_settings_mod = ModuleType("core.settings")
_settings_mod.USERNAME = "test"
_settings_mod.PASSWORD = "test"
_settings_mod.SSH_TIMEOUT_OPS = 30
_settings_mod.SSH_RETRIES = 1
_settings_mod.SSH_RETRY_DELAY = 2
_settings_mod.SSH_MAX_CONCURRENT = 5
_settings_mod.SSH_STRICT_HOST_KEY = False
sys.modules["core.settings"] = _settings_mod

# core.logging_config — prevent logging side effects at import time
_logging_mod = ModuleType("core.logging_config")
_logging_mod.setup_logging = lambda: None
sys.modules["core.logging_config"] = _logging_mod

# core.jira_client — not used in tests
_jira_mod = ModuleType("core.jira_client")
_jira_mod._is_configured = lambda: False
_jira_mod.create_issue = AsyncMock(return_value=None)
_jira_mod.add_comment = AsyncMock(return_value=None)
sys.modules["core.jira_client"] = _jira_mod

# ── Step 2: Load NETWORK.json as mock device inventory ────────────────────────
_NETWORK_JSON = _ROOT / "testing" / "mock" / "resources" / "NETWORK.json"
MOCK_DEVICES: dict = json.loads(_NETWORK_JSON.read_text())

# core.netbox — prevent NetBox connections
_netbox_mod = ModuleType("core.netbox")
_netbox_mod.load_devices = lambda: dict(MOCK_DEVICES)
_netbox_mod.load_intent = MagicMock(return_value={})
sys.modules["core.netbox"] = _netbox_mod

# core.inventory — pre-populate devices dict with NETWORK.json data
_inventory_mod = ModuleType("core.inventory")
_inventory_mod.devices = dict(MOCK_DEVICES)
_inventory_mod.inventory_source = "test"
sys.modules["core.inventory"] = _inventory_mod

# ── Step 3: Mock transport ─────────────────────────────────────────────────────
_transport_mod = ModuleType("transport")
_transport_execute = AsyncMock(
    return_value={"raw": "", "cli_style": "ios", "device": "TEST"}
)
_transport_mod.execute_command = _transport_execute
_transport_mod.open_device_session = AsyncMock()
_transport_mod.close_device_session = AsyncMock()
sys.modules["transport"] = _transport_mod

# ── Step 4: Load legacy/INTENT.json as mock intent ────────────────────────────
_INTENT_JSON = _ROOT / "testing" / "mock" / "resources" / "INTENT.json"
MOCK_INTENT: dict = json.loads(_INTENT_JSON.read_text())


# ── pytest fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_devices() -> dict:
    """Device inventory from legacy/NETWORK.json."""
    return dict(MOCK_DEVICES)


@pytest.fixture
def mock_intent() -> dict:
    """Network intent from legacy/INTENT.json."""
    return dict(MOCK_INTENT)
