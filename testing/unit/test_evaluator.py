"""UT-006 — Assertion evaluator: all 7 types, PASS/FAIL/ERROR."""
import pytest

from validation.assertions import (
    Assertion, AssertionType, AssertionResult, DeviceState,
)
from validation.evaluator import evaluate, _interface_matches


# ── INTERFACE_UP ──────────────────────────────────────────────────────────────

def _intf_assertion(interface="eth0"):
    return Assertion(
        type=AssertionType.INTERFACE_UP,
        device="R1",
        description="R1 eth0 should be up/up",
        expected="up/up",
        protocol="interface",
        interface=interface,
    )


def test_interface_pass():
    ds = DeviceState(interfaces={"eth0": "up/up"})
    result = evaluate([_intf_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.PASS
    assert result[0].actual == "up/up"


def test_interface_fail_down():
    ds = DeviceState(interfaces={"eth0": "down/down"})
    result = evaluate([_intf_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "down/down"


def test_interface_fail_not_found():
    ds = DeviceState(interfaces={"eth1": "up/up"})
    result = evaluate([_intf_assertion("eth0")], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "not found"


def test_interface_fuzzy_match_gi():
    ds = DeviceState(interfaces={"GigabitEthernet2": "up/up"})
    result = evaluate([_intf_assertion("Gi2")], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_interface_fuzzy_match_ethernet():
    ds = DeviceState(interfaces={"Ethernet0/1": "up/up"})
    result = evaluate([_intf_assertion("Et0/1")], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_interface_error_no_data():
    ds = DeviceState(interfaces=None)
    result = evaluate([_intf_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.ERROR


def test_interface_error_device_not_in_state():
    result = evaluate([_intf_assertion()], {})
    assert result[0].result == AssertionResult.ERROR


# ── OSPF_NEIGHBOR ─────────────────────────────────────────────────────────────

def _ospf_nbr_assertion(interface="eth0", neighbor_ip="10.0.0.2"):
    return Assertion(
        type=AssertionType.OSPF_NEIGHBOR,
        device="R1",
        description="R1 should have OSPF FULL neighbor on eth0",
        expected="FULL",
        protocol="ospf",
        interface=interface,
        neighbor_ip=neighbor_ip,
    )


def test_ospf_neighbor_pass():
    ds = DeviceState(ospf_neighbors=[
        {"neighbor_id": "2.2.2.2", "state": "FULL", "interface": "eth0", "area": ""}
    ])
    result = evaluate([_ospf_nbr_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.PASS
    assert result[0].actual == "FULL"


def test_ospf_neighbor_fail_init():
    ds = DeviceState(ospf_neighbors=[
        {"neighbor_id": "2.2.2.2", "state": "INIT", "interface": "eth0", "area": ""}
    ])
    result = evaluate([_ospf_nbr_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "INIT"


def test_ospf_neighbor_fail_missing():
    ds = DeviceState(ospf_neighbors=[])
    result = evaluate([_ospf_nbr_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "no neighbor on interface"


def test_ospf_neighbor_fallback_by_ip():
    # RouterOS: no interface in neighbor entry, match by address
    ds = DeviceState(ospf_neighbors=[
        {"neighbor_id": "2.2.2.2", "state": "FULL", "interface": "", "address": "10.0.0.2", "area": ""}
    ])
    result = evaluate([_ospf_nbr_assertion(interface="bridge1", neighbor_ip="10.0.0.2")], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_ospf_neighbor_error_no_data():
    ds = DeviceState(ospf_neighbors=None)
    result = evaluate([_ospf_nbr_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.ERROR


# ── OSPF_ROUTER_ID ────────────────────────────────────────────────────────────

def _router_id_assertion(expected="1.1.1.1"):
    return Assertion(
        type=AssertionType.OSPF_ROUTER_ID,
        device="R1",
        description="R1 OSPF router-id should be 1.1.1.1",
        expected=expected,
        protocol="ospf",
    )


def test_ospf_router_id_pass():
    ds = DeviceState(ospf_details={"router_id": "1.1.1.1", "areas": {}, "default_originate": False})
    result = evaluate([_router_id_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_ospf_router_id_fail_wrong():
    ds = DeviceState(ospf_details={"router_id": "9.9.9.9", "areas": {}, "default_originate": False})
    result = evaluate([_router_id_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "9.9.9.9"


def test_ospf_router_id_fail_not_found():
    ds = DeviceState(ospf_details={"router_id": "", "areas": {}, "default_originate": False})
    result = evaluate([_router_id_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "not found"


def test_ospf_router_id_error_no_data():
    ds = DeviceState(ospf_details=None)
    result = evaluate([_router_id_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.ERROR


# ── OSPF_AREA_TYPE ────────────────────────────────────────────────────────────

def _area_type_assertion(area="1", expected="stub"):
    return Assertion(
        type=AssertionType.OSPF_AREA_TYPE,
        device="R1",
        description="R1 area 1 should be stub",
        expected=expected,
        protocol="ospf",
        area=area,
    )


def test_ospf_area_type_pass():
    ds = DeviceState(ospf_details={"router_id": "", "areas": {"1": "stub"}, "default_originate": False})
    result = evaluate([_area_type_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_ospf_area_type_fail_wrong():
    ds = DeviceState(ospf_details={"router_id": "", "areas": {"1": "nssa"}, "default_originate": False})
    result = evaluate([_area_type_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "nssa"


def test_ospf_area_type_fail_not_found():
    ds = DeviceState(ospf_details={"router_id": "", "areas": {}, "default_originate": False})
    result = evaluate([_area_type_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "not found"


def test_ospf_area_type_case_insensitive():
    ds = DeviceState(ospf_details={"router_id": "", "areas": {"1": "Stub"}, "default_originate": False})
    result = evaluate([_area_type_assertion(expected="stub")], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_ospf_area_type_error_no_data():
    ds = DeviceState(ospf_details=None)
    result = evaluate([_area_type_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.ERROR


# ── OSPF_DEFAULT_ORIG ─────────────────────────────────────────────────────────

def _deflt_assertion():
    return Assertion(
        type=AssertionType.OSPF_DEFAULT_ORIG,
        device="R1",
        description="R1 should originate OSPF default route",
        expected=True,
        protocol="ospf",
    )


def test_ospf_default_orig_pass():
    ds = DeviceState(ospf_details={"router_id": "", "areas": {}, "default_originate": True})
    result = evaluate([_deflt_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.PASS
    assert result[0].actual is True


def test_ospf_default_orig_fail():
    ds = DeviceState(ospf_details={"router_id": "", "areas": {}, "default_originate": False})
    result = evaluate([_deflt_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual is False


def test_ospf_default_orig_error_no_data():
    ds = DeviceState(ospf_details=None)
    result = evaluate([_deflt_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.ERROR


# ── BGP_SESSION ───────────────────────────────────────────────────────────────

def _bgp_assertion(neighbor_ip="200.40.40.2"):
    return Assertion(
        type=AssertionType.BGP_SESSION,
        device="R1",
        description="R1 BGP session with ISP should be Established",
        expected="Established",
        protocol="bgp",
        neighbor_ip=neighbor_ip,
    )


def test_bgp_session_pass():
    ds = DeviceState(bgp_summary=[
        {"neighbor_ip": "200.40.40.2", "state": "Established", "as": 4040}
    ])
    result = evaluate([_bgp_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.PASS
    assert result[0].actual == "Established"


def test_bgp_session_fail_active():
    ds = DeviceState(bgp_summary=[
        {"neighbor_ip": "200.40.40.2", "state": "Active", "as": 4040}
    ])
    result = evaluate([_bgp_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "Active"


def test_bgp_session_fail_not_found():
    ds = DeviceState(bgp_summary=[])
    result = evaluate([_bgp_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "not found"


def test_bgp_session_error_no_data():
    ds = DeviceState(bgp_summary=None)
    result = evaluate([_bgp_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.ERROR


# ── EIGRP_NEIGHBOR ────────────────────────────────────────────────────────────

def _eigrp_assertion(interface="Et0/1", neighbor_ip="10.10.10.1"):
    return Assertion(
        type=AssertionType.EIGRP_NEIGHBOR,
        device="R1",
        description="R1 EIGRP neighbor on Et0/1",
        expected="up",
        protocol="eigrp",
        interface=interface,
        neighbor_ip=neighbor_ip,
    )


def test_eigrp_neighbor_pass():
    ds = DeviceState(eigrp_neighbors=[
        {"neighbor_ip": "10.10.10.1", "interface": "Et0/1"}
    ])
    result = evaluate([_eigrp_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.PASS
    assert result[0].actual == "up"


def test_eigrp_neighbor_pass_full_name():
    ds = DeviceState(eigrp_neighbors=[
        {"neighbor_ip": "10.10.10.1", "interface": "Ethernet0/1"}
    ])
    result = evaluate([_eigrp_assertion(interface="Et0/1")], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_eigrp_neighbor_fail_missing():
    ds = DeviceState(eigrp_neighbors=[])
    result = evaluate([_eigrp_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.FAIL
    assert result[0].actual == "no neighbor"


def test_eigrp_neighbor_fallback_by_ip():
    ds = DeviceState(eigrp_neighbors=[
        {"neighbor_ip": "10.10.10.1", "interface": ""}
    ])
    result = evaluate([_eigrp_assertion(interface="UNKNOWN_INTF", neighbor_ip="10.10.10.1")], {"R1": ds})
    assert result[0].result == AssertionResult.PASS


def test_eigrp_neighbor_error_no_data():
    ds = DeviceState(eigrp_neighbors=None)
    result = evaluate([_eigrp_assertion()], {"R1": ds})
    assert result[0].result == AssertionResult.ERROR


# ── _interface_matches parametrize ────────────────────────────────────────────

@pytest.mark.parametrize("actual,expected,should_match", [
    ("GigabitEthernet2",  "Gi2",              True),
    ("GigabitEthernet2",  "GigabitEthernet2", True),
    ("Ethernet0/1",       "Et0/1",            True),
    ("Ethernet1/3",       "Et1/3",            True),
    ("1/1/2",             "1/1/2",            True),
    ("et-0/0/4",          "et-0/0/4",         True),
    ("GigabitEthernet2",  "Gi3",              False),
    ("GigabitEthernet2",  "Fa2",              False),
    ("Ethernet0/1",       "Ethernet0/2",      False),
    ("GigabitEthernet2",  "GigabitEthernet3", False),
])
def test_interface_matches(actual, expected, should_match):
    assert _interface_matches(actual, expected) == should_match


# ── Multiple assertions evaluated together ───────────────────────────────────

def test_evaluate_multiple_assertions():
    assertions = [
        Assertion(
            type=AssertionType.INTERFACE_UP, device="R1",
            description="R1 eth0", expected="up/up", protocol="interface", interface="eth0",
        ),
        Assertion(
            type=AssertionType.INTERFACE_UP, device="R1",
            description="R1 eth1", expected="up/up", protocol="interface", interface="eth1",
        ),
    ]
    ds = DeviceState(interfaces={"eth0": "up/up", "eth1": "down/down"})
    results = evaluate(assertions, {"R1": ds})
    assert len(results) == 2
    assert results[0].result == AssertionResult.PASS
    assert results[1].result == AssertionResult.FAIL
