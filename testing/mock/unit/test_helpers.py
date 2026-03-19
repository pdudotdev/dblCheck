"""UT-012 — Helper functions: _error_response, _looks_like_ip, box drawing,
_failure_fingerprint, _build_parser, _safe, _extract_diagnosis_text."""
import argparse
import json

import pytest

from tools import _error_response
from validation.normalizers import _looks_like_ip

# Import CLI helpers — conftest.py has mocked core.logging_config so setup_logging() is a no-op
from cli.dblcheck import (
    _box_top, _box_row, _box_bot, _failure_fingerprint, _build_parser,
    _safe, _extract_diagnosis_text,
)
from validation.assertions import (
    Assertion, AssertionType, AssertionResult, EvaluatedAssertion,
)


# ── _error_response ───────────────────────────────────────────────────────────

def test_error_response_with_device():
    resp = _error_response("R1", "Something went wrong")
    assert resp["error"] == "Something went wrong"
    assert resp["device"] == "R1"


def test_error_response_without_device():
    resp = _error_response(None, "No device context")
    assert resp["error"] == "No device context"
    assert "device" not in resp


def test_error_response_empty_message():
    resp = _error_response("R1", "")
    assert "error" in resp
    assert resp["device"] == "R1"


def test_error_response_has_error_key():
    resp = _error_response("R1", "msg")
    assert "error" in resp
    assert resp["error"] == "msg"


# ── _looks_like_ip ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("s", [
    "10.0.0.1",
    "192.168.1.100",
    "0.0.0.0",
    "255.255.255.255",
    "200.40.40.2",
])
def test_looks_like_ip_valid(s):
    assert _looks_like_ip(s) is True


@pytest.mark.parametrize("s", [
    "not-an-ip",
    "GigabitEthernet2",
    "10.0.0",
    "10.0.0.1.2",
    "10.0.0.abc",
    "",
    "Neighbor",
    "::1",
])
def test_looks_like_ip_invalid(s):
    assert _looks_like_ip(s) is False


# ── _box_top / _box_row / _box_bot ────────────────────────────────────────────

def test_box_top_contains_corner():
    line = _box_top()
    assert "┌" in line
    assert "┐" in line


def test_box_top_with_label():
    line = _box_top("dblCheck")
    assert "dblCheck" in line
    assert "┌" in line


def test_box_row_contains_borders():
    line = _box_row("some text")
    assert "│" in line
    assert "some text" in line


def test_box_bot_contains_corner():
    line = _box_bot()
    assert "└" in line
    assert "┘" in line


def test_box_top_width_consistent():
    top = _box_top()
    bot = _box_bot()
    # Both lines should be the same length (60 chars box + 2 indent)
    assert len(top) == len(bot)


def test_box_row_fits_text():
    text = "Inventory    16 devices (test)"
    line = _box_row(text)
    assert text in line


# ── _failure_fingerprint ──────────────────────────────────────────────────────

def _make_evaluated(device, atype, expected, actual):
    a = Assertion(
        type=atype, device=device, description="test", expected=expected,
    )
    return EvaluatedAssertion(a, AssertionResult.FAIL, actual=actual)


def test_failure_fingerprint_returns_string():
    failures = [_make_evaluated("R1", AssertionType.INTERFACE_UP, "up/up", "down/down")]
    fp = _failure_fingerprint(failures)
    assert isinstance(fp, str)
    assert len(fp) == 64  # SHA-256 hex digest


def test_failure_fingerprint_stable():
    failures = [
        _make_evaluated("R1", AssertionType.INTERFACE_UP, "up/up", "down/down"),
        _make_evaluated("R2", AssertionType.BGP_SESSION, "Established", "Active"),
    ]
    fp1 = _failure_fingerprint(failures)
    fp2 = _failure_fingerprint(failures)
    assert fp1 == fp2


def test_failure_fingerprint_different_inputs():
    fp1 = _failure_fingerprint([
        _make_evaluated("R1", AssertionType.INTERFACE_UP, "up/up", "down/down")
    ])
    fp2 = _failure_fingerprint([
        _make_evaluated("R2", AssertionType.BGP_SESSION, "Established", "Active")
    ])
    assert fp1 != fp2


def test_failure_fingerprint_order_independent():
    f1 = _make_evaluated("R1", AssertionType.INTERFACE_UP, "up/up", "down/down")
    f2 = _make_evaluated("R2", AssertionType.BGP_SESSION, "Established", "Active")
    fp_ab = _failure_fingerprint([f1, f2])
    fp_ba = _failure_fingerprint([f2, f1])
    assert fp_ab == fp_ba


def test_failure_fingerprint_empty():
    fp = _failure_fingerprint([])
    assert isinstance(fp, str)
    assert len(fp) == 64


# ── _build_parser ─────────────────────────────────────────────────────────────

def test_build_parser_returns_parser():
    p = _build_parser()
    assert isinstance(p, argparse.ArgumentParser)


def test_build_parser_no_diagnose():
    p = _build_parser()
    args = p.parse_args(["--no-diagnose"])
    assert args.no_diagnose is True


def test_build_parser_headless():
    p = _build_parser()
    args = p.parse_args(["--headless"])
    assert args.headless is True


def test_build_parser_default_no_diagnose_false():
    p = _build_parser()
    args = p.parse_args([])
    assert args.no_diagnose is False


# ── _safe ──────────────────────────────────────────────────────────────────────

def test_safe_passes_clean_text():
    assert _safe("show ip ospf neighbor") == "show ip ospf neighbor"


def test_safe_handles_none():
    assert _safe(None) == ""


def test_safe_strips_control_chars():
    result = _safe("abc\x01\x1bdef")
    assert "\x01" not in result
    assert "\x1b" not in result
    assert "abcdef" in result


def test_safe_preserves_spaces_tabs_newlines():
    result = _safe("line1\n  line2\ttabbed")
    assert "line1" in result
    assert "line2" in result
    assert "\n" in result
    assert "\t" in result


def test_safe_truncates_at_500():
    long_input = "A" * 600
    result = _safe(long_input)
    assert len(result) == 500


def test_safe_converts_non_string():
    assert _safe(12345) == "12345"


# ── _extract_diagnosis_text ────────────────────────────────────────────────────

def _make_ndjson(events: list[dict]) -> str:
    return "\n".join(json.dumps(e) for e in events)


def test_extract_diagnosis_text_basic(tmp_path):
    session = tmp_path / "session.ndjson"
    events = [
        {"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Root cause: link is down."},
        }},
    ]
    session.write_text(_make_ndjson(events))
    result = _extract_diagnosis_text(session)
    assert "Root cause: link is down." in result


def test_extract_diagnosis_text_concatenates_deltas(tmp_path):
    session = tmp_path / "session.ndjson"
    events = [
        {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Part one "}}},
        {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Part two"}}},
    ]
    session.write_text(_make_ndjson(events))
    result = _extract_diagnosis_text(session)
    assert result == "Part one Part two"


def test_extract_diagnosis_text_strips_narration(tmp_path):
    session = tmp_path / "session.ndjson"
    events = [
        {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Preamble narration\n## Finding\nActual diagnosis"}}},
    ]
    session.write_text(_make_ndjson(events))
    result = _extract_diagnosis_text(session)
    assert result.startswith("## Finding")
    assert "Preamble narration" not in result


def test_extract_diagnosis_text_skips_malformed_lines(tmp_path):
    session = tmp_path / "session.ndjson"
    content = (
        "not valid json\n"
        + json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Good line"},
        }})
    )
    session.write_text(content)
    result = _extract_diagnosis_text(session)
    assert result == "Good line"


def test_extract_diagnosis_text_missing_file(tmp_path):
    result = _extract_diagnosis_text(tmp_path / "nonexistent.ndjson")
    assert result == ""


def test_extract_diagnosis_text_empty_file(tmp_path):
    session = tmp_path / "session.ndjson"
    session.write_text("")
    result = _extract_diagnosis_text(session)
    assert result == ""

