"""
LT-001 — Platform Map Live Coverage

Tests every PLATFORM_MAP query against one representative device per vendor,
using the real SSH transport. Results saved to platform_coverage_results.md.

Representative devices (one per vendor):
  D1C — Cisco IOS-XE   (ios)
  C2A — Arista EOS     (eos)
  C1J — Juniper JunOS  (junos)
  D2B — Aruba AOS-CX   (aos)
  A1M — MikroTik       (routeros)

Result classification:
  PASS  — valid data returned
  EMPTY — transport succeeded but no data (feature not configured on device)
  FAIL  — transport error or unexpected empty when data was expected

Requires live device access. Set NO_LAB=0 to enable.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Project root already on sys.path via conftest.py

pytestmark = pytest.mark.skipif(
    os.environ.get("NO_LAB", "1") == "1",
    reason="Lab not running — set NO_LAB=0 to enable live tests",
)

from input_models.models import (
    BgpQuery,
    EigrpQuery,
    InterfacesQuery,
    OspfQuery,
    RoutingPolicyQuery,
    RoutingQuery,
)
from platforms.platform_map import PLATFORM_MAP
from tools.operational import get_interfaces
from tools.protocol import get_bgp, get_eigrp, get_ospf
from tools.routing import get_routing, get_routing_policies

# ── Representative devices (1 per vendor) ─────────────────────────────────────

DEVICES = {
    "D1C": {"cli_style": "ios",      "platform": "Cisco IOS-XE",          "location": "Distribution"},
    "C2A": {"cli_style": "eos",      "platform": "Arista EOS",             "location": "Core"},
    "C1J": {"cli_style": "junos",    "platform": "Juniper JunOS",          "location": "Core"},
    "D2B": {"cli_style": "aos",      "platform": "Aruba AOS-CX",           "location": "Distribution"},
    "A1M": {"cli_style": "routeros", "platform": "MikroTik RouterOS",      "location": "Access"},
}

DEVICE_ORDER = ["D1C", "C2A", "C1J", "D2B", "A1M"]

CATEGORIES = ["ospf", "bgp", "routing_table", "routing_policies", "interfaces"]


# ── Queries that MUST return real data (EMPTY = test fail) ────────────────────

MUST_HAVE_DATA = {
    # Every device should have at least some interfaces
    ("D1C", "interfaces", "interface_status"),
    ("C2A", "interfaces", "interface_status"),
    ("C1J", "interfaces", "interface_status"),
    ("D2B", "interfaces", "interface_status"),
    ("A1M", "interfaces", "interface_status"),
    # OSPF neighbors — D1C and C1J are core OSPF speakers in this topology
    ("D1C", "ospf", "neighbors"),
    ("D1C", "ospf", "details"),
    ("C1J", "ospf", "neighbors"),
    ("C1J", "ospf", "details"),
    # Routing table — every routed device has routes
    ("D1C", "routing_table", "ip_route"),
    ("C2A", "routing_table", "ip_route"),
    ("C1J", "routing_table", "ip_route"),
}


# ── Result classification ─────────────────────────────────────────────────────

def classify_result(result) -> tuple[str, str]:
    """Return (status, error_msg) where status is PASS, EMPTY, or FAIL."""
    if result is None:
        return "FAIL", "Tool returned None"

    if "error" in result and "raw" not in result:
        err = str(result["error"]).strip()
        return ("EMPTY", "") if not err else ("FAIL", err)

    raw = result.get("raw", "")

    if isinstance(raw, str) and "% Invalid input" in raw:
        return "FAIL", raw.strip()[:200]

    # IOS/EOS "% <msg>" = feature not configured → EMPTY (not a command error)
    if isinstance(raw, str) and raw.strip().startswith("% "):
        return "EMPTY", ""

    return "PASS", ""


# ── Results collection ────────────────────────────────────────────────────────

RESULTS: list[dict] = []
_RESULTS_FILE = Path(__file__).parent / "platform_coverage_results.md"


def truncate_output(output, max_lines: int = 100) -> str:
    if output is None:
        return "(no output)"
    text = str(output.get("raw", output) if isinstance(output, dict) else output)
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n(truncated)"


def record(device: str, category: str, query: str,
           status: str, output, error: str | None) -> None:
    RESULTS.append({
        "device":   device,
        "category": category,
        "query":    query,
        "status":   status,
        "output":   output,
        "error":    error,
    })


# ── Markdown report writer ────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="session")
def write_results_file():
    yield  # all tests run first

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    total  = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    empty  = sum(1 for r in RESULTS if r["status"] == "EMPTY")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")

    lines = [
        "# Platform Coverage Results",
        f"*Generated: {timestamp} UTC*",
        "",
        "## Summary",
        "",
        "| Device | Platform | Tests | Passed | Empty | Failed |",
        "|--------|----------|-------|--------|-------|--------|",
    ]

    for dev in DEVICE_ORDER:
        meta = DEVICES[dev]
        dev_entries = [r for r in RESULTS if r["device"] == dev]
        if not dev_entries:
            continue
        n = len(dev_entries)
        p = sum(1 for e in dev_entries if e["status"] == "PASS")
        e = sum(1 for e in dev_entries if e["status"] == "EMPTY")
        f = sum(1 for e in dev_entries if e["status"] == "FAIL")
        lines.append(
            f"| {dev} | {meta['platform']} ({meta['cli_style']}) | {n} | {p} | {e} | {f} |"
        )

    lines.append(
        f"| **Total** | | **{total}** | **{passed}** | **{empty}** | **{failed}** |"
    )
    lines += ["", "---", "", "## Detailed Results", ""]

    for dev in DEVICE_ORDER:
        dev_entries = [r for r in RESULTS if r["device"] == dev]
        if not dev_entries:
            continue
        meta = DEVICES[dev]
        lines.append(f"### {dev} — {meta['platform']} ({meta['cli_style']})")
        lines.append("")
        for i, entry in enumerate(dev_entries, 1):
            status = entry["status"]
            lines.append(
                f"#### {i}. {entry['category']} — {entry['query']} — {status}"
            )
            if entry["error"]:
                lines.append(f"**Error:** {entry['error']}")
            else:
                lines.append("```")
                lines.append(truncate_output(entry["output"]))
                lines.append("```")
            lines.append("")

    _RESULTS_FILE.write_text("\n".join(lines), encoding="utf-8")


# ── Helper ────────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.run(coro)


def _dispatch(device: str, cli_style: str, category: str, query: str):
    """Call the appropriate tool function for the given category/query."""
    if category == "ospf":
        return run(get_ospf(OspfQuery(device=device, query=query)))
    if category == "bgp":
        return run(get_bgp(BgpQuery(device=device, query=query)))
    if category == "eigrp":
        return run(get_eigrp(EigrpQuery(device=device, query=query)))
    if category == "routing_table":
        return run(get_routing(RoutingQuery(device=device)))
    if category == "routing_policies":
        return run(get_routing_policies(RoutingPolicyQuery(device=device, query=query)))
    if category == "interfaces":
        return run(get_interfaces(InterfacesQuery(device=device)))
    raise ValueError(f"Unknown category: {category}")


def _run_case(device: str, cli_style: str, category: str, query: str) -> None:
    """Execute one test case, record result, and assert on outcome."""
    result = error_msg = None
    status = "FAIL"
    try:
        result = _dispatch(device, cli_style, category, query)
        status, err = classify_result(result)
        if err:
            error_msg = err

        if status == "FAIL":
            pytest.fail(f"{device} {category}/{query}: {error_msg}")

        key = (device, category, query)
        if key in MUST_HAVE_DATA and status == "EMPTY":
            pytest.fail(
                f"{device} {category}/{query}: Expected data but got EMPTY "
                f"— protocol may not be configured or no output returned"
            )

    except (AssertionError, pytest.fail.Exception):
        status = "FAIL"
        raise
    except Exception as exc:
        status = "FAIL"
        error_msg = str(exc)
        pytest.fail(f"{device} {category}/{query}: {exc}")
    finally:
        record(device, category, query, status, result, error_msg)


# ── Build parametrized cases from PLATFORM_MAP ────────────────────────────────

def _cases_for(cli_style: str, categories: list[str]) -> list[tuple[str, str]]:
    cases = []
    for cat in categories:
        for q in PLATFORM_MAP.get(cli_style, {}).get(cat, {}):
            cases.append((cat, q))
    return cases


D1C_CASES = _cases_for("ios", CATEGORIES + ["eigrp"])
C2A_CASES = _cases_for("eos", CATEGORIES)
C1J_CASES = _cases_for("junos", CATEGORIES)
D2B_CASES = _cases_for("aos", CATEGORIES)
A1M_CASES = _cases_for("routeros", CATEGORIES)


# ── LT-001a: D1C — Cisco IOS-XE ──────────────────────────────────────────────

@pytest.mark.parametrize("category,query", D1C_CASES)
def test_d1c(category, query):
    _run_case("D1C", "ios", category, query)


# ── LT-001b: C2A — Arista EOS ─────────────────────────────────────────────────

@pytest.mark.parametrize("category,query", C2A_CASES)
def test_c2a(category, query):
    _run_case("C2A", "eos", category, query)


# ── LT-001c: C1J — Juniper JunOS ─────────────────────────────────────────────

@pytest.mark.parametrize("category,query", C1J_CASES)
def test_c1j(category, query):
    _run_case("C1J", "junos", category, query)


# ── LT-001d: D2B — Aruba AOS-CX ──────────────────────────────────────────────

@pytest.mark.parametrize("category,query", D2B_CASES)
def test_d2b(category, query):
    _run_case("D2B", "aos", category, query)


# ── LT-001e: A1M — MikroTik RouterOS ─────────────────────────────────────────

@pytest.mark.parametrize("category,query", A1M_CASES)
def test_a1m(category, query):
    _run_case("A1M", "routeros", category, query)


