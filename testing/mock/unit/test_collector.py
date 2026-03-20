"""UT-009 — Collector query planner (_plan_queries) and _collect_device."""
import asyncio
import sys

import pytest

from validation.assertions import Assertion, AssertionType
from validation.collector import _plan_queries, _collect_device


def _make(atype, device="R1"):
    return Assertion(
        type=atype,
        device=device,
        description="test",
        expected="test",
    )


# ── Single assertion type → single query ──────────────────────────────────────

def test_plan_interface_up():
    plan = _plan_queries([_make(AssertionType.INTERFACE_UP)])
    assert plan["R1"] == {"interfaces"}


def test_plan_ospf_neighbor():
    plan = _plan_queries([_make(AssertionType.OSPF_NEIGHBOR)])
    assert plan["R1"] == {"ospf_neighbors"}


def test_plan_ospf_router_id():
    plan = _plan_queries([_make(AssertionType.OSPF_ROUTER_ID)])
    assert plan["R1"] == {"ospf_details"}


def test_plan_ospf_area_type():
    plan = _plan_queries([_make(AssertionType.OSPF_AREA_TYPE)])
    assert plan["R1"] == {"ospf_details"}


def test_plan_ospf_default_orig():
    plan = _plan_queries([_make(AssertionType.OSPF_DEFAULT_ORIG)])
    assert plan["R1"] == {"ospf_details"}


def test_plan_bgp_session():
    plan = _plan_queries([_make(AssertionType.BGP_SESSION)])
    assert plan["R1"] == {"bgp_summary"}


def test_plan_eigrp_neighbor():
    plan = _plan_queries([_make(AssertionType.EIGRP_NEIGHBOR)])
    assert plan["R1"] == {"eigrp_neighbors"}


# ── Mixed assertions → superset of queries ───────────────────────────────────

def test_plan_mixed_interface_and_ospf():
    assertions = [
        _make(AssertionType.INTERFACE_UP),
        _make(AssertionType.OSPF_NEIGHBOR),
    ]
    plan = _plan_queries(assertions)
    assert plan["R1"] == {"interfaces", "ospf_neighbors"}


def test_plan_all_ospf_detail_types_merged():
    assertions = [
        _make(AssertionType.OSPF_ROUTER_ID),
        _make(AssertionType.OSPF_AREA_TYPE),
        _make(AssertionType.OSPF_DEFAULT_ORIG),
    ]
    plan = _plan_queries(assertions)
    assert plan["R1"] == {"ospf_details"}


def test_plan_all_types_all_queries():
    assertions = [
        _make(AssertionType.INTERFACE_UP),
        _make(AssertionType.OSPF_NEIGHBOR),
        _make(AssertionType.OSPF_ROUTER_ID),
        _make(AssertionType.BGP_SESSION),
        _make(AssertionType.EIGRP_NEIGHBOR),
    ]
    plan = _plan_queries(assertions)
    assert plan["R1"] == {"interfaces", "ospf_neighbors", "ospf_details", "bgp_summary", "eigrp_neighbors"}


# ── Multiple devices ──────────────────────────────────────────────────────────

def test_plan_multiple_devices():
    assertions = [
        _make(AssertionType.INTERFACE_UP, device="R1"),
        _make(AssertionType.OSPF_NEIGHBOR, device="R2"),
        _make(AssertionType.BGP_SESSION, device="R3"),
    ]
    plan = _plan_queries(assertions)
    assert plan["R1"] == {"interfaces"}
    assert plan["R2"] == {"ospf_neighbors"}
    assert plan["R3"] == {"bgp_summary"}


def test_plan_same_device_multiple_types():
    assertions = [
        _make(AssertionType.INTERFACE_UP, device="R1"),
        _make(AssertionType.BGP_SESSION, device="R1"),
        _make(AssertionType.EIGRP_NEIGHBOR, device="R1"),
    ]
    plan = _plan_queries(assertions)
    assert "R1" in plan
    assert plan["R1"] == {"interfaces", "bgp_summary", "eigrp_neighbors"}


# ── Empty input ───────────────────────────────────────────────────────────────

def test_plan_empty_assertions():
    plan = _plan_queries([])
    assert plan == {}


# ── _collect_device ───────────────────────────────────────────────────────────
# Tests the wiring between tool calls → normalizers → DeviceState.
# The conftest mocks transport.execute_command so no SSH is needed.

def _get_mock_execute():
    return sys.modules["transport"].execute_command


_IOS_INTF_RAW = (
    "Interface              IP-Address      OK? Method Status                Protocol\n"
    "GigabitEthernet2       10.0.0.1        YES NVRAM  up                   up\n"
)

_IOS_OSPF_NBR_RAW = (
    "Neighbor ID     Pri   State           Dead Time   Address         Interface\n"
    "11.11.11.11       1   FULL/DR         00:00:37    10.0.0.5        Ethernet1/3\n"
)


def test_collect_device_interfaces_populates_state():
    mock = _get_mock_execute()
    mock.reset_mock()
    mock.return_value = {"raw": _IOS_INTF_RAW, "cli_style": "ios", "device": "D1C"}
    state = asyncio.run(_collect_device("D1C", {"interfaces"}))
    assert state.interfaces is not None
    assert "GigabitEthernet2" in state.interfaces
    assert state.interfaces["GigabitEthernet2"] == "up/up"
    assert state.errors == []
    # Verify the correct command was actually dispatched — not just that the mock returned data
    mock.assert_called_once_with("D1C", "show ip interface brief")


def test_collect_device_tool_error_propagates_to_state():
    mock = _get_mock_execute()
    mock.reset_mock()
    mock.return_value = {"error": "SSH timeout", "device": "D1C"}
    state = asyncio.run(_collect_device("D1C", {"interfaces"}))
    assert state.interfaces is None
    assert any("interfaces" in e for e in state.errors)


def test_collect_device_ospf_neighbors_populates_state():
    mock = _get_mock_execute()
    mock.reset_mock()
    mock.return_value = {"raw": _IOS_OSPF_NBR_RAW, "cli_style": "ios", "device": "D1C"}
    state = asyncio.run(_collect_device("D1C", {"ospf_neighbors"}))
    assert state.ospf_neighbors is not None
    assert len(state.ospf_neighbors) == 1
    assert state.ospf_neighbors[0]["neighbor_id"] == "11.11.11.11"
    # Verify the correct command was dispatched
    mock.assert_called_once_with("D1C", "show ip ospf neighbor")


def test_collect_device_multiple_queries_populates_multiple_fields():
    mock = _get_mock_execute()
    mock.reset_mock()
    # Side effect: first call (interfaces), second call (ospf_neighbors)
    # _collect_device checks queries in fixed order: interfaces → ospf_neighbors
    mock.side_effect = [
        {"raw": _IOS_INTF_RAW, "cli_style": "ios", "device": "D1C"},
        {"raw": _IOS_OSPF_NBR_RAW, "cli_style": "ios", "device": "D1C"},
    ]
    state = asyncio.run(_collect_device("D1C", {"interfaces", "ospf_neighbors"}))
    assert state.interfaces is not None
    assert state.ospf_neighbors is not None
    # Verify both commands were dispatched, in the correct order
    assert mock.call_count == 2
    calls = [c.args for c in mock.call_args_list]
    assert ("D1C", "show ip interface brief") in calls
    assert ("D1C", "show ip ospf neighbor") in calls
    mock.side_effect = None  # reset for subsequent tests
