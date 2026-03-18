"""UT-005 — Assertion derivation from INTENT.json."""
import json
from pathlib import Path

import pytest

from validation.assertions import AssertionType
from validation.derivation import derive_assertions


_INTENT = json.loads((Path(__file__).parent.parent.parent / "legacy" / "INTENT.json").read_text())


def test_derive_total_count_reasonable():
    result = derive_assertions(_INTENT)
    assert len(result) >= 50


def test_derive_contains_interface_type():
    result = derive_assertions(_INTENT)
    types = {a.type for a in result}
    assert AssertionType.INTERFACE_UP in types


def test_derive_contains_ospf_neighbor_type():
    result = derive_assertions(_INTENT)
    types = {a.type for a in result}
    assert AssertionType.OSPF_NEIGHBOR in types


def test_derive_contains_bgp_session_type():
    result = derive_assertions(_INTENT)
    types = {a.type for a in result}
    assert AssertionType.BGP_SESSION in types


def test_derive_contains_eigrp_neighbor_type():
    result = derive_assertions(_INTENT)
    types = {a.type for a in result}
    assert AssertionType.EIGRP_NEIGHBOR in types


def test_derive_contains_ospf_router_id_type():
    result = derive_assertions(_INTENT)
    types = {a.type for a in result}
    assert AssertionType.OSPF_ROUTER_ID in types


def test_derive_contains_ospf_area_type():
    result = derive_assertions(_INTENT)
    types = {a.type for a in result}
    assert AssertionType.OSPF_AREA_TYPE in types


def test_derive_contains_ospf_default_originate():
    result = derive_assertions(_INTENT)
    types = {a.type for a in result}
    assert AssertionType.OSPF_DEFAULT_ORIG in types


# ── Protocol filter ───────────────────────────────────────────────────────────

def test_protocol_filter_ospf_only():
    result = derive_assertions(_INTENT, protocol_filter="ospf")
    types = {a.type for a in result}
    assert types.issubset({
        AssertionType.OSPF_NEIGHBOR,
        AssertionType.OSPF_ROUTER_ID,
        AssertionType.OSPF_AREA_TYPE,
        AssertionType.OSPF_DEFAULT_ORIG,
    })
    assert AssertionType.BGP_SESSION not in types
    assert AssertionType.INTERFACE_UP not in types


def test_protocol_filter_bgp_only():
    result = derive_assertions(_INTENT, protocol_filter="bgp")
    types = {a.type for a in result}
    assert AssertionType.BGP_SESSION in types
    assert AssertionType.OSPF_NEIGHBOR not in types
    assert AssertionType.INTERFACE_UP not in types


def test_protocol_filter_eigrp_only():
    result = derive_assertions(_INTENT, protocol_filter="eigrp")
    types = {a.type for a in result}
    assert AssertionType.EIGRP_NEIGHBOR in types
    assert AssertionType.OSPF_NEIGHBOR not in types


def test_protocol_filter_interface_only():
    result = derive_assertions(_INTENT, protocol_filter="interface")
    types = {a.type for a in result}
    assert types == {AssertionType.INTERFACE_UP}


# ── Device filter ─────────────────────────────────────────────────────────────

def test_device_filter_d1c_only():
    result = derive_assertions(_INTENT, device_filter={"D1C"})
    assert all(a.device == "D1C" for a in result)
    assert len(result) > 0


def test_device_filter_unknown_device():
    result = derive_assertions(_INTENT, device_filter={"NONEXISTENT"})
    assert result == []


# ── EIGRP only on D1C / B1C / B2C ────────────────────────────────────────────

def test_eigrp_only_on_expected_devices():
    result = derive_assertions(_INTENT, protocol_filter="eigrp")
    eigrp_devices = {a.device for a in result}
    # Only D1C, B1C, B2C have EIGRP in this topology
    assert eigrp_devices.issubset({"D1C", "B1C", "B2C"})
    assert "A1M" not in eigrp_devices
    assert "C1J" not in eigrp_devices


def test_eigrp_b1c_present():
    result = derive_assertions(_INTENT, protocol_filter="eigrp")
    devices = {a.device for a in result}
    assert "B1C" in devices
    assert "B2C" in devices
    assert "D1C" in devices


# ── BGP neighbor IPs match intent ────────────────────────────────────────────

def test_bgp_e1c_isp_a_peer_ip():
    result = derive_assertions(_INTENT, device_filter={"E1C"}, protocol_filter="bgp")
    ips = {a.neighbor_ip for a in result}
    assert "200.40.40.2" in ips


def test_bgp_e1c_isp_b_peer_ip():
    result = derive_assertions(_INTENT, device_filter={"E1C"}, protocol_filter="bgp")
    ips = {a.neighbor_ip for a in result}
    assert "200.50.50.2" in ips


def test_bgp_x1c_peers():
    result = derive_assertions(_INTENT, device_filter={"X1C"}, protocol_filter="bgp")
    ips = {a.neighbor_ip for a in result}
    assert "200.40.8.2" in ips
    assert "200.50.8.2" in ips


# ── OSPF area types ───────────────────────────────────────────────────────────

def test_ospf_area_type_stub_present():
    result = derive_assertions(_INTENT, protocol_filter="ospf")
    area_types = [a for a in result if a.type == AssertionType.OSPF_AREA_TYPE]
    stub_areas = [a for a in area_types if a.expected == "stub"]
    assert len(stub_areas) > 0


def test_ospf_area1_is_stub_on_d1c():
    result = derive_assertions(_INTENT, device_filter={"D1C"}, protocol_filter="ospf")
    area_types = [a for a in result if a.type == AssertionType.OSPF_AREA_TYPE]
    area1 = [a for a in area_types if a.area == "1"]
    assert len(area1) == 1
    assert area1[0].expected == "stub"


# ── Default originate ─────────────────────────────────────────────────────────

def test_ospf_default_originate_on_e1c():
    result = derive_assertions(_INTENT, device_filter={"E1C"}, protocol_filter="ospf")
    do_asserts = [a for a in result if a.type == AssertionType.OSPF_DEFAULT_ORIG]
    assert len(do_asserts) == 1
    assert do_asserts[0].expected is True


# ── Bidirectional links ───────────────────────────────────────────────────────

def test_interface_assertions_are_bidirectional():
    result = derive_assertions(_INTENT, protocol_filter="interface")
    # D1C→A1M and A1M→D1C both appear
    d1c_to_a1m = [a for a in result if a.device == "D1C" and a.peer == "A1M"]
    a1m_to_d1c = [a for a in result if a.device == "A1M" and a.peer == "D1C"]
    assert len(d1c_to_a1m) == 1
    assert len(a1m_to_d1c) == 1
    assert d1c_to_a1m[0].interface != ""
    assert a1m_to_d1c[0].interface != ""


def test_ospf_neighbor_assertions_are_bidirectional():
    result = derive_assertions(_INTENT, protocol_filter="ospf")
    nbr = [a for a in result if a.type == AssertionType.OSPF_NEIGHBOR]
    d1c_c1j = [a for a in nbr if a.device == "D1C" and a.peer == "C1J"]
    c1j_d1c = [a for a in nbr if a.device == "C1J" and a.peer == "D1C"]
    assert len(d1c_c1j) == 1
    assert len(c1j_d1c) == 1
    assert d1c_c1j[0].interface != ""
    assert c1j_d1c[0].interface != ""


# ── Router IDs ────────────────────────────────────────────────────────────────

def test_ospf_router_id_d1c():
    result = derive_assertions(_INTENT, device_filter={"D1C"}, protocol_filter="ospf")
    rid = [a for a in result if a.type == AssertionType.OSPF_ROUTER_ID]
    assert len(rid) == 1
    assert rid[0].expected == "11.11.11.11"


def test_ospf_router_id_a1m():
    result = derive_assertions(_INTENT, device_filter={"A1M"}, protocol_filter="ospf")
    rid = [a for a in result if a.type == AssertionType.OSPF_ROUTER_ID]
    assert len(rid) == 1
    assert rid[0].expected == "1.1.1.1"


# ── Empty intent ──────────────────────────────────────────────────────────────

def test_derive_empty_intent():
    result = derive_assertions({"routers": {}})
    assert result == []


def test_derive_missing_routers_key():
    result = derive_assertions({})
    assert result == []
