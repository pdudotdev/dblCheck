"""IT-002 — End-to-end pipeline: derive → evaluate → report.

Uses a synthetic two-device intent to avoid SSH connections.
Verifies all-healthy (all PASS) and broken (FAIL present) scenarios.
"""
import json

import pytest

from validation.assertions import AssertionType, AssertionResult, DeviceState
from validation.derivation import derive_assertions
from validation.evaluator import evaluate
from validation.report import format_text, format_run_dict


# ── Minimal synthetic intent ──────────────────────────────────────────────────
# Two routers connected via 10.0.0.0/30, running OSPF area 0.
# R1 also originates the default route. R2 is in area 1 (stub).
MINIMAL_INTENT = {
    "routers": {
        "R1": {
            "direct_links": {
                "R2": {
                    "local_interface": "eth0",
                    "local_ip": "10.0.0.1",
                    "remote_ip": "10.0.0.2",
                    "subnet": "10.0.0.0/30",
                }
            },
            "igp": {
                "ospf": {
                    "router_id": "1.1.1.1",
                    "areas": {"0": ["10.0.0.0/30"]},
                    "default_originate": {"enabled": True},
                }
            },
        },
        "R2": {
            "direct_links": {
                "R1": {
                    "local_interface": "eth1",
                    "local_ip": "10.0.0.2",
                    "remote_ip": "10.0.0.1",
                    "subnet": "10.0.0.0/30",
                }
            },
            "igp": {
                "ospf": {
                    "router_id": "2.2.2.2",
                    "areas": {"0": ["10.0.0.0/30"]},
                }
            },
        },
    }
}


# ── Healthy device state ───────────────────────────────────────────────────────

def _healthy_state() -> dict[str, DeviceState]:
    return {
        "R1": DeviceState(
            interfaces={"eth0": "up/up"},
            ospf_neighbors=[{"neighbor_id": "2.2.2.2", "state": "FULL", "interface": "eth0", "area": ""}],
            ospf_details={"router_id": "1.1.1.1", "areas": {}, "default_originate": True},
        ),
        "R2": DeviceState(
            interfaces={"eth1": "up/up"},
            ospf_neighbors=[{"neighbor_id": "1.1.1.1", "state": "FULL", "interface": "eth1", "area": ""}],
            ospf_details={"router_id": "2.2.2.2", "areas": {}, "default_originate": False},
        ),
    }


# ── Broken device state ────────────────────────────────────────────────────────

def _broken_state() -> dict[str, DeviceState]:
    return {
        "R1": DeviceState(
            interfaces={"eth0": "down/down"},
            ospf_neighbors=[],
            ospf_details={"router_id": "1.1.1.1", "areas": {}, "default_originate": False},
        ),
        "R2": DeviceState(
            interfaces={"eth1": "down/down"},
            ospf_neighbors=[],
            ospf_details={"router_id": "2.2.2.2", "areas": {}, "default_originate": False},
        ),
    }


# ── Derive tests ──────────────────────────────────────────────────────────────

def test_derive_minimal_intent_not_empty():
    assertions = derive_assertions(MINIMAL_INTENT)
    assert len(assertions) > 0


def test_derive_minimal_interface_assertions():
    assertions = derive_assertions(MINIMAL_INTENT)
    intf = [a for a in assertions if a.type == AssertionType.INTERFACE_UP]
    assert len(intf) == 2  # R1→R2 and R2→R1


def test_derive_minimal_ospf_neighbor_assertions():
    assertions = derive_assertions(MINIMAL_INTENT)
    nbr = [a for a in assertions if a.type == AssertionType.OSPF_NEIGHBOR]
    assert len(nbr) == 2  # bidirectional


def test_derive_minimal_router_ids():
    assertions = derive_assertions(MINIMAL_INTENT)
    rids = [a for a in assertions if a.type == AssertionType.OSPF_ROUTER_ID]
    rid_expected = {a.expected for a in rids}
    assert "1.1.1.1" in rid_expected
    assert "2.2.2.2" in rid_expected


def test_derive_minimal_default_originate():
    assertions = derive_assertions(MINIMAL_INTENT)
    do = [a for a in assertions if a.type == AssertionType.OSPF_DEFAULT_ORIG]
    assert len(do) == 1
    assert do[0].device == "R1"


# ── All-healthy scenario ──────────────────────────────────────────────────────

def test_healthy_scenario_all_pass():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _healthy_state()
    results = evaluate(assertions, state)
    assert len(results) == len(assertions), "evaluate() dropped assertions"
    failed = [r for r in results if r.result != AssertionResult.PASS]
    assert not failed, f"Unexpected failures: {[r.assertion.description for r in failed]}"


def test_healthy_scenario_no_errors():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _healthy_state()
    results = evaluate(assertions, state)
    errors = [r for r in results if r.result == AssertionResult.ERROR]
    assert not errors


def test_healthy_scenario_report_no_fail_tag():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _healthy_state()
    results = evaluate(assertions, state)
    assert len(results) > 0
    text = format_text(results, 0.1, color=False)
    assert "[FAIL]" not in text
    assert "All assertions passed" in text


def test_healthy_scenario_run_dict_all_pass():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _healthy_state()
    results = evaluate(assertions, state)
    run_dict = format_run_dict(results, 0.1)
    assert run_dict["summary"]["failed"] == 0
    assert run_dict["summary"]["errors"] == 0
    assert run_dict["summary"]["passed"] == run_dict["summary"]["total"]


# ── Broken scenario ───────────────────────────────────────────────────────────

def test_broken_scenario_has_failures():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _broken_state()
    results = evaluate(assertions, state)
    failed = [r for r in results if r.result == AssertionResult.FAIL]
    # 2 interface_up + 2 ospf_neighbor + 1 ospf_default_originate = at least 5
    assert len(failed) >= 5


def test_broken_scenario_interface_fails():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _broken_state()
    results = evaluate(assertions, state)
    intf_results = [r for r in results if r.assertion.type == AssertionType.INTERFACE_UP]
    assert len(intf_results) == 2
    assert all(r.result == AssertionResult.FAIL for r in intf_results)


def test_broken_scenario_ospf_neighbor_fails():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _broken_state()
    results = evaluate(assertions, state)
    nbr_results = [r for r in results if r.assertion.type == AssertionType.OSPF_NEIGHBOR]
    assert len(nbr_results) == 2
    assert all(r.result == AssertionResult.FAIL for r in nbr_results)


def test_broken_scenario_report_contains_fail_tag():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _broken_state()
    results = evaluate(assertions, state)
    text = format_text(results, 0.1, color=False)
    assert "[FAIL]" in text


def test_broken_scenario_report_contains_device_names():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _broken_state()
    results = evaluate(assertions, state)
    text = format_text(results, 0.1, color=False)
    assert "R1" in text
    assert "R2" in text


def test_broken_scenario_run_dict_has_failures():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _broken_state()
    results = evaluate(assertions, state)
    run_dict = format_run_dict(results, 0.1)
    assert run_dict["summary"]["failed"] > 0


# ── Run dict ──────────────────────────────────────────────────────────────────

def test_run_dict_healthy():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _healthy_state()
    results = evaluate(assertions, state)
    d = format_run_dict(results, 0.5)
    assert d["summary"]["failed"] == 0
    assert d["summary"]["total"] == len(assertions)


def test_run_dict_broken():
    assertions = derive_assertions(MINIMAL_INTENT)
    state = _broken_state()
    results = evaluate(assertions, state)
    d = format_run_dict(results, 0.5)
    assert d["summary"]["failed"] > 0
    assert "R1" in d["per_device"]
    assert "R2" in d["per_device"]


# ── BGP + EIGRP intent ────────────────────────────────────────────────────────
# B1 peers with an external BGP neighbor.
# B1 and B2 share an EIGRP link. No OSPF in this topology.

BGP_EIGRP_INTENT = {
    "routers": {
        "B1": {
            "direct_links": {
                "B2": {
                    "local_interface": "eth0",
                    "local_ip": "10.2.0.1",
                    "remote_ip": "10.2.0.2",
                    "subnet": "10.2.0.0/30",
                }
            },
            "igp": {
                "eigrp": {
                    "as_number": 200,
                    "networks": ["10.2.0.0/30"],
                }
            },
            "bgp": {
                "neighbors": {
                    "ISP": {"peer": "203.0.113.1", "as": 64500}
                }
            },
        },
        "B2": {
            "direct_links": {
                "B1": {
                    "local_interface": "eth1",
                    "local_ip": "10.2.0.2",
                    "remote_ip": "10.2.0.1",
                    "subnet": "10.2.0.0/30",
                }
            },
            "igp": {
                "eigrp": {
                    "as_number": 200,
                    "networks": ["10.2.0.0/30"],
                }
            },
        },
    }
}


def _bgp_eigrp_healthy_state() -> dict[str, DeviceState]:
    return {
        "B1": DeviceState(
            interfaces={"eth0": "up/up"},
            bgp_summary=[{"neighbor_ip": "203.0.113.1", "state": "Established", "as": 64500}],
            eigrp_neighbors=[{"neighbor_ip": "10.2.0.2", "interface": "eth0"}],
        ),
        "B2": DeviceState(
            interfaces={"eth1": "up/up"},
            eigrp_neighbors=[{"neighbor_ip": "10.2.0.1", "interface": "eth1"}],
        ),
    }


def _bgp_eigrp_broken_state() -> dict[str, DeviceState]:
    return {
        "B1": DeviceState(
            interfaces={"eth0": "down/down"},
            bgp_summary=[{"neighbor_ip": "203.0.113.1", "state": "Active", "as": 64500}],
            eigrp_neighbors=[],
        ),
        "B2": DeviceState(
            interfaces={"eth1": "down/down"},
            eigrp_neighbors=[],
        ),
    }


# ── BGP + EIGRP derive tests ──────────────────────────────────────────────────

def test_derive_bgp_eigrp_has_bgp_session():
    assertions = derive_assertions(BGP_EIGRP_INTENT)
    bgp = [a for a in assertions if a.type == AssertionType.BGP_SESSION]
    assert len(bgp) == 1
    assert bgp[0].device == "B1"
    assert bgp[0].neighbor_ip == "203.0.113.1"


def test_derive_bgp_eigrp_has_eigrp_neighbors():
    assertions = derive_assertions(BGP_EIGRP_INTENT)
    eigrp = [a for a in assertions if a.type == AssertionType.EIGRP_NEIGHBOR]
    assert len(eigrp) == 2  # B1→B2 and B2→B1


# ── BGP + EIGRP healthy scenario ──────────────────────────────────────────────

def test_bgp_eigrp_healthy_all_pass():
    assertions = derive_assertions(BGP_EIGRP_INTENT)
    state = _bgp_eigrp_healthy_state()
    results = evaluate(assertions, state)
    assert len(results) == len(assertions), "evaluate() dropped assertions"
    failed = [r for r in results if r.result != AssertionResult.PASS]
    assert not failed, f"Unexpected failures: {[r.assertion.description for r in failed]}"


def test_bgp_session_healthy_evaluates_established():
    assertions = derive_assertions(BGP_EIGRP_INTENT)
    state = _bgp_eigrp_healthy_state()
    results = evaluate(assertions, state)
    bgp_results = [r for r in results if r.assertion.type == AssertionType.BGP_SESSION]
    assert len(bgp_results) == 1
    assert bgp_results[0].result == AssertionResult.PASS


def test_eigrp_neighbor_healthy_evaluates_pass():
    assertions = derive_assertions(BGP_EIGRP_INTENT)
    state = _bgp_eigrp_healthy_state()
    results = evaluate(assertions, state)
    eigrp_results = [r for r in results if r.assertion.type == AssertionType.EIGRP_NEIGHBOR]
    assert len(eigrp_results) == 2
    assert all(r.result == AssertionResult.PASS for r in eigrp_results)


# ── BGP + EIGRP broken scenario ───────────────────────────────────────────────

def test_bgp_session_broken_evaluates_fail():
    assertions = derive_assertions(BGP_EIGRP_INTENT)
    state = _bgp_eigrp_broken_state()
    results = evaluate(assertions, state)
    bgp_results = [r for r in results if r.assertion.type == AssertionType.BGP_SESSION]
    assert len(bgp_results) == 1
    assert bgp_results[0].result == AssertionResult.FAIL
    assert bgp_results[0].actual == "Active"


def test_eigrp_neighbor_broken_evaluates_fail():
    assertions = derive_assertions(BGP_EIGRP_INTENT)
    state = _bgp_eigrp_broken_state()
    results = evaluate(assertions, state)
    eigrp_results = [r for r in results if r.assertion.type == AssertionType.EIGRP_NEIGHBOR]
    assert len(eigrp_results) == 2
    assert all(r.result == AssertionResult.FAIL for r in eigrp_results)
