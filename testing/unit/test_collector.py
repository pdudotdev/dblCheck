"""UT-009 — Collector query planner (_plan_queries)."""
import pytest

from validation.assertions import Assertion, AssertionType
from validation.collector import _plan_queries


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
