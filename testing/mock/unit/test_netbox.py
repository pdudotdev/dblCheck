"""UT-016 — NetBox loader: load_devices() and load_intent()."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Stub core.vault
if "core.vault" not in sys.modules:
    _vault = ModuleType("core.vault")
    _vault.get_secret = lambda *a, **kw: None
    sys.modules["core.vault"] = _vault
else:
    sys.modules["core.vault"].get_secret = lambda *a, **kw: None

_spec = importlib.util.spec_from_file_location(
    "_real_netbox", _ROOT / "core" / "netbox.py"
)
_netbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_netbox)

load_devices = _netbox.load_devices
load_intent = _netbox.load_intent


# ── load_devices ──────────────────────────────────────────────────────────────

def _make_device(name, ip="10.0.0.1/32", platform_slug="cisco_ios",
                 transport="asyncssh", cli_style="ios", site="DC1",
                 vrf=""):
    dev = MagicMock()
    dev.name = name
    dev.primary_ip = MagicMock()
    dev.primary_ip.address = ip
    dev.platform = MagicMock()
    dev.platform.slug = platform_slug
    dev.custom_fields = {"transport": transport, "cli_style": cli_style, "vrf": vrf}
    dev.site = MagicMock()
    dev.site.name = site
    return dev


def test_load_devices_no_url_returns_none(monkeypatch):
    monkeypatch.delenv("NETBOX_URL", raising=False)
    result = load_devices()
    assert result is None


def test_load_devices_no_token_returns_none(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    with patch.object(_netbox, "get_secret", return_value=None):
        result = load_devices()
    assert result is None


def test_load_devices_maps_valid_device(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    dev = _make_device("R1", ip="192.168.1.1/32", cli_style="ios")
    nb_mock = MagicMock()
    nb_mock.dcim.devices.all.return_value = [dev]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_devices()
    assert result is not None
    assert "R1" in result
    assert result["R1"]["host"] == "192.168.1.1"
    assert result["R1"]["cli_style"] == "ios"


def test_load_devices_skips_device_without_primary_ip(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    dev = _make_device("R1")
    dev.primary_ip = None
    nb_mock = MagicMock()
    nb_mock.dcim.devices.all.return_value = [dev]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_devices()
    assert result is None  # no valid devices → None


def test_load_devices_skips_device_missing_cli_style(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    dev = _make_device("R1")
    dev.custom_fields = {"transport": "asyncssh", "cli_style": "", "vrf": ""}
    nb_mock = MagicMock()
    nb_mock.dcim.devices.all.return_value = [dev]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_devices()
    assert result is None  # skipped → None


def test_load_devices_strips_cidr_from_ip(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    dev = _make_device("R1", ip="10.1.2.3/24")
    nb_mock = MagicMock()
    nb_mock.dcim.devices.all.return_value = [dev]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_devices()
    assert result["R1"]["host"] == "10.1.2.3"


def test_load_devices_includes_vrf_when_set(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    dev = _make_device("R1", vrf="MGMT")
    nb_mock = MagicMock()
    nb_mock.dcim.devices.all.return_value = [dev]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_devices()
    assert result["R1"]["vrf"] == "MGMT"


def test_load_devices_omits_vrf_when_empty(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    dev = _make_device("R1", vrf="")
    nb_mock = MagicMock()
    nb_mock.dcim.devices.all.return_value = [dev]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_devices()
    assert "vrf" not in result["R1"]


def test_load_devices_netbox_unreachable_returns_none(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", side_effect=Exception("connection refused")):
            result = load_devices()
    assert result is None


# ── load_intent ───────────────────────────────────────────────────────────────

def _make_context(name, data):
    ctx = MagicMock()
    ctx.name = name
    ctx.data = data
    return ctx


def test_load_intent_no_url_returns_none(monkeypatch):
    monkeypatch.delenv("NETBOX_URL", raising=False)
    result = load_intent()
    assert result is None


def test_load_intent_no_contexts_returns_none(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    nb_mock = MagicMock()
    nb_mock.extras.config_contexts.filter.return_value = []
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_intent()
    assert result is None


def test_load_intent_builds_routers_from_device_contexts(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    ctx1 = _make_context("dblcheck-R1", {"igp": {"ospf": {}}})
    ctx2 = _make_context("dblcheck-R2", {"bgp": {}})
    nb_mock = MagicMock()
    nb_mock.extras.config_contexts.filter.return_value = [ctx1, ctx2]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_intent()
    assert result is not None
    assert "R1" in result["routers"]
    assert "R2" in result["routers"]


def test_load_intent_parses_global_context_as_autonomous_systems(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    global_ctx = _make_context("dblcheck-global", {"autonomous_systems": {"65001": {"name": "ISP"}}})
    dev_ctx = _make_context("dblcheck-R1", {})
    nb_mock = MagicMock()
    nb_mock.extras.config_contexts.filter.return_value = [global_ctx, dev_ctx]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_intent()
    assert "autonomous_systems" in result
    assert "65001" in result["autonomous_systems"]


def test_load_intent_no_device_contexts_returns_none(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "http://netbox.example.com")
    # Only global context, no per-device contexts
    global_ctx = _make_context("dblcheck-global", {"autonomous_systems": {}})
    nb_mock = MagicMock()
    nb_mock.extras.config_contexts.filter.return_value = [global_ctx]
    with patch.object(_netbox, "get_secret", return_value="fake_token"):
        with patch("pynetbox.api", return_value=nb_mock):
            result = load_intent()
    assert result is None
