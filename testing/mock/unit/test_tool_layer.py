"""UT-011 — Tool layer: known/unknown devices, platform restrictions."""
import asyncio
import sys

import pytest

# Import tools after conftest has injected mocks
from tools.protocol import get_ospf, get_bgp, get_eigrp
from tools.operational import get_interfaces
from tools.routing import get_routing, get_routing_policies
from input_models.models import OspfQuery, BgpQuery, EigrpQuery, InterfacesQuery, RoutingQuery, RoutingPolicyQuery


def _get_mock_execute():
    """Return the mocked execute_command from sys.modules['transport']."""
    return sys.modules["transport"].execute_command


# ── get_ospf ──────────────────────────────────────────────────────────────────

def test_ospf_known_device_no_error():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "output", "cli_style": "ios", "device": "D1C"}
    result = asyncio.run(get_ospf(OspfQuery(device="D1C", query="neighbors")))
    assert "error" not in result
    assert result["raw"] == "output"
    assert result["device"] == "D1C"
    assert result["cli_style"] == "ios"
    mock_execute.assert_called_once_with("D1C", "show ip ospf neighbor")


def test_ospf_unknown_device_returns_error():
    result = asyncio.run(get_ospf(OspfQuery(device="UNKNOWN_DEVICE", query="neighbors")))
    assert "error" in result
    assert "Unknown device" in result["error"]


def test_ospf_detail_known_device():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "ospf detail", "cli_style": "ios", "device": "D1C"}
    result = asyncio.run(get_ospf(OspfQuery(device="D1C", query="details")))
    assert "error" not in result
    assert result["raw"] == "ospf detail"
    assert result["device"] == "D1C"
    assert result["cli_style"] == "ios"
    mock_execute.assert_called_once_with("D1C", "show ip ospf")


# ── get_bgp ───────────────────────────────────────────────────────────────────

def test_bgp_known_device_no_error():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "bgp output", "cli_style": "ios", "device": "E1C"}
    result = asyncio.run(get_bgp(BgpQuery(device="E1C", query="summary")))
    assert "error" not in result
    assert result["raw"] == "bgp output"
    assert result["device"] == "E1C"
    assert result["cli_style"] == "ios"
    mock_execute.assert_called_once_with("E1C", "show ip bgp vpnv4 vrf VRF1 summary")


def test_bgp_unknown_device_returns_error():
    result = asyncio.run(get_bgp(BgpQuery(device="GHOST_DEVICE", query="summary")))
    assert "error" in result
    assert "Unknown device" in result["error"]


def test_bgp_device_name_in_error():
    result = asyncio.run(get_bgp(BgpQuery(device="GHOST_DEVICE", query="summary")))
    assert result.get("device") == "GHOST_DEVICE"


# ── get_eigrp ─────────────────────────────────────────────────────────────────

def test_eigrp_ios_device_no_error():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "eigrp output", "cli_style": "ios", "device": "D1C"}
    result = asyncio.run(get_eigrp(EigrpQuery(device="D1C", query="neighbors")))
    assert "error" not in result
    assert result["raw"] == "eigrp output"
    assert result["device"] == "D1C"
    assert result["cli_style"] == "ios"
    mock_execute.assert_called_once_with("D1C", "show ip eigrp vrf VRF1 neighbors")


def test_eigrp_unknown_device_returns_error():
    result = asyncio.run(get_eigrp(EigrpQuery(device="NO_SUCH_DEVICE", query="neighbors")))
    assert "error" in result
    assert "Unknown device" in result["error"]


def test_eigrp_eos_device_not_supported():
    # C2A is EOS — no eigrp in PLATFORM_MAP for eos
    result = asyncio.run(get_eigrp(EigrpQuery(device="C2A", query="neighbors")))
    assert "error" in result
    assert "not supported" in result["error"].lower() or "EIGRP" in result["error"]


def test_eigrp_junos_device_not_supported():
    # C1J is JunOS — no eigrp in PLATFORM_MAP for junos
    result = asyncio.run(get_eigrp(EigrpQuery(device="C1J", query="neighbors")))
    assert "error" in result
    assert "not supported" in result["error"].lower() or "EIGRP" in result["error"]


def test_eigrp_routeros_device_not_supported():
    # A1M is RouterOS — no eigrp in PLATFORM_MAP for routeros
    result = asyncio.run(get_eigrp(EigrpQuery(device="A1M", query="neighbors")))
    assert "error" in result
    assert "not supported" in result["error"].lower() or "EIGRP" in result["error"]


# ── get_interfaces ────────────────────────────────────────────────────────────

def test_interfaces_known_device_no_error():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "intf output", "cli_style": "ios", "device": "D1C"}
    result = asyncio.run(get_interfaces(InterfacesQuery(device="D1C")))
    assert "error" not in result
    assert result["raw"] == "intf output"
    assert result["device"] == "D1C"
    assert result["cli_style"] == "ios"
    mock_execute.assert_called_once_with("D1C", "show ip interface brief")


def test_interfaces_unknown_device_returns_error():
    result = asyncio.run(get_interfaces(InterfacesQuery(device="FAKE_DEVICE")))
    assert "error" in result
    assert "Unknown device" in result["error"]


def test_interfaces_routeros_device():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {
        "raw": " 0 R ether1 ether 1500",
        "cli_style": "routeros",
        "device": "A1M",
    }
    result = asyncio.run(get_interfaces(InterfacesQuery(device="A1M")))
    assert "error" not in result
    assert result["raw"] == " 0 R ether1 ether 1500"
    assert result["device"] == "A1M"
    assert result["cli_style"] == "routeros"
    mock_execute.assert_called_once_with("A1M", "/interface print brief without-paging")


# ── get_bgp neighbor IP append (B6) ──────────────────────────────────────────

def test_bgp_neighbor_query_appends_ip():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "bgp neighbor detail", "cli_style": "ios", "device": "E1C"}
    result = asyncio.run(get_bgp(BgpQuery(device="E1C", query="neighbors", neighbor="10.0.0.1")))
    assert "error" not in result
    assert result["raw"] == "bgp neighbor detail"
    assert result["device"] == "E1C"
    assert result["cli_style"] == "ios"
    # E1C has vrf=VRF1; IOS vpnv4 vrf neighbors command + neighbor IP appended
    mock_execute.assert_called_once_with("E1C", "show ip bgp vpnv4 vrf VRF1 neighbors 10.0.0.1")


# ── get_routing (B5) ──────────────────────────────────────────────────────────

def test_routing_known_device_no_prefix():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "routing table", "cli_style": "ios", "device": "D1C"}
    result = asyncio.run(get_routing(RoutingQuery(device="D1C")))
    assert "error" not in result
    assert result["raw"] == "routing table"
    assert result["device"] == "D1C"
    assert result["cli_style"] == "ios"
    # D1C has vrf=VRF1 → VRF-aware command
    mock_execute.assert_called_once_with("D1C", "show ip route vrf VRF1")


def test_routing_known_device_with_prefix():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "route entry", "cli_style": "ios", "device": "D1C"}
    result = asyncio.run(get_routing(RoutingQuery(device="D1C", prefix="10.0.0.0/24")))
    assert "error" not in result
    assert result["raw"] == "route entry"
    assert result["device"] == "D1C"
    assert result["cli_style"] == "ios"
    mock_execute.assert_called_once_with("D1C", "show ip route vrf VRF1 10.0.0.0/24")


def test_routing_routeros_with_prefix_uses_where_clause():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "route entry", "cli_style": "routeros", "device": "A1M"}
    result = asyncio.run(get_routing(RoutingQuery(device="A1M", prefix="10.0.0.0/24")))
    assert "error" not in result
    assert result["raw"] == "route entry"
    assert result["device"] == "A1M"
    assert result["cli_style"] == "routeros"
    # A1M has vrf=VRF1 → base cmd contains "where routing-table=VRF1" → condition appended
    mock_execute.assert_called_once_with(
        "A1M",
        "/ip route print terse without-paging where routing-table=VRF1 dst-address=10.0.0.0/24",
    )


def test_routing_unknown_device_returns_error():
    result = asyncio.run(get_routing(RoutingQuery(device="NO_SUCH_DEVICE")))
    assert "error" in result
    assert "Unknown device" in result["error"]


# ── get_routing_policies (B5) ─────────────────────────────────────────────────

def test_routing_policies_known_device():
    mock_execute = _get_mock_execute()
    mock_execute.reset_mock()
    mock_execute.return_value = {"raw": "redistribute output", "cli_style": "ios", "device": "D1C"}
    result = asyncio.run(get_routing_policies(RoutingPolicyQuery(device="D1C", query="redistribution")))
    assert "error" not in result
    assert result["raw"] == "redistribute output"
    assert result["device"] == "D1C"
    assert result["cli_style"] == "ios"
    mock_execute.assert_called_once_with("D1C", "show run | section redistribute")


def test_routing_policies_unknown_device_returns_error():
    result = asyncio.run(get_routing_policies(RoutingPolicyQuery(device="NO_SUCH_DEVICE", query="route_maps")))
    assert "error" in result
    assert "Unknown device" in result["error"]
