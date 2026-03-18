"""UT-010 — Report formatting: text, JSON, and run_dict."""
import json

import pytest

from validation.assertions import (
    Assertion, AssertionType, AssertionResult, EvaluatedAssertion,
)
from validation.report import format_text, format_run_dict


def _make_pass(device="R1", interface="eth0"):
    a = Assertion(
        type=AssertionType.INTERFACE_UP,
        device=device,
        description=f"{device} {interface} should be up/up",
        expected="up/up",
        protocol="interface",
        interface=interface,
    )
    return EvaluatedAssertion(a, AssertionResult.PASS, actual="up/up")


def _make_fail(device="R2", interface="eth0"):
    a = Assertion(
        type=AssertionType.INTERFACE_UP,
        device=device,
        description=f"{device} {interface} should be up/up",
        expected="up/up",
        protocol="interface",
        interface=interface,
    )
    return EvaluatedAssertion(a, AssertionResult.FAIL, actual="down/down",
                               detail="Expected up/up, got down/down")


def _make_error(device="R3"):
    a = Assertion(
        type=AssertionType.OSPF_NEIGHBOR,
        device=device,
        description=f"{device} OSPF neighbor",
        expected="FULL",
        protocol="ospf",
    )
    return EvaluatedAssertion(a, AssertionResult.ERROR, detail="interfaces data not collected")


# ── format_run_dict ───────────────────────────────────────────────────────────

def test_run_dict_summary_counts():
    results = [_make_pass(), _make_fail(), _make_error()]
    d = format_run_dict(results, 1.5)
    assert d["summary"]["total"] == 3
    assert d["summary"]["passed"] == 1
    assert d["summary"]["failed"] == 1
    assert d["summary"]["errors"] == 1


def test_run_dict_duration():
    d = format_run_dict([_make_pass()], 2.75)
    assert d["duration_sec"] == 2.75


def test_run_dict_has_timestamp():
    d = format_run_dict([_make_pass()], 1.0)
    assert "timestamp" in d
    assert d["timestamp"].endswith("Z")


def test_run_dict_per_device_counts():
    results = [
        _make_pass("R1"), _make_pass("R1"),
        _make_fail("R2"), _make_error("R2"),
    ]
    d = format_run_dict(results, 1.0)
    assert d["per_device"]["R1"]["pass"] == 2
    assert d["per_device"]["R1"]["fail"] == 0
    assert d["per_device"]["R2"]["pass"] == 0
    assert d["per_device"]["R2"]["fail"] == 1
    assert d["per_device"]["R2"]["error"] == 1


def test_run_dict_assertions_list():
    results = [_make_pass(), _make_fail()]
    d = format_run_dict(results, 1.0)
    assert len(d["assertions"]) == 2


def test_run_dict_assertion_fields():
    results = [_make_fail()]
    d = format_run_dict(results, 1.0)
    a = d["assertions"][0]
    assert a["type"] == "interface_up"
    assert a["device"] == "R2"
    assert a["result"] == "fail"
    assert a["expected"] == "up/up"
    assert a["actual"] == "down/down"
    assert "description" in a


def test_run_dict_result_values():
    results = [_make_pass(), _make_fail(), _make_error()]
    d = format_run_dict(results, 1.0)
    result_vals = {a["result"] for a in d["assertions"]}
    assert "pass" in result_vals
    assert "fail" in result_vals
    assert "error" in result_vals


def test_run_dict_all_pass():
    results = [_make_pass("R1"), _make_pass("R2"), _make_pass("R3")]
    d = format_run_dict(results, 1.0)
    assert d["summary"]["passed"] == 3
    assert d["summary"]["failed"] == 0
    assert d["summary"]["errors"] == 0


# ── format_text ───────────────────────────────────────────────────────────────

def test_format_text_header():
    text = format_text([_make_pass()], 1.0)
    assert "dblCheck Validation Report" in text


def test_format_text_all_passed():
    text = format_text([_make_pass()], 1.0)
    assert "All assertions passed" in text


def test_format_text_no_fail_tag_when_all_pass():
    text = format_text([_make_pass(), _make_pass("R2")], 1.0)
    assert "[FAIL]" not in text


def test_format_text_fail_tag_present():
    text = format_text([_make_pass(), _make_fail()], 1.0, color=False)
    assert "[FAIL]" in text


def test_format_text_error_tag_present():
    text = format_text([_make_error()], 1.0, color=False)
    assert "[ERR ]" in text


def test_format_text_summary_counts():
    results = [_make_pass(), _make_fail(), _make_error()]
    text = format_text(results, 1.0, color=False)
    assert "Total: 3" in text
    assert "Passed: 1" in text
    assert "Failed: 1" in text
    assert "Errors: 1" in text


def test_format_text_device_table_present():
    text = format_text([_make_pass("R1"), _make_fail("R2")], 1.0, color=False)
    assert "R1" in text
    assert "R2" in text


def test_format_text_duration():
    text = format_text([_make_pass()], 3.5, color=False)
    assert "3.5s" in text


def test_format_text_empty_results():
    # format_text([]) must not raise; no per-device table rendered
    text = format_text([], 0.0, color=False)
    assert "dblCheck Validation Report" in text
    assert "Total: 0" in text
    assert "[FAIL]" not in text
    assert "[ERR ]" not in text


