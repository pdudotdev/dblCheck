"""UT-004 — EIGRP neighbor normalizer (IOS only)."""
from validation.normalizers import normalize_eigrp_neighbors


# ── Fixtures ──────────────────────────────────────────────────────────────────

EIGRP_SINGLE = """\
EIGRP-IPv4 Neighbors for AS(10)
H   Address         Interface        Hold Uptime   SRTT   RTO  Q  Seq
                                      (sec)         (ms)       Cnt Num
0   10.10.10.1      Et0/1              13 00:05:32    3   100  0  3
"""

EIGRP_MULTI = """\
EIGRP-IPv4 Neighbors for AS(10)
H   Address         Interface        Hold Uptime   SRTT   RTO  Q  Seq
                                      (sec)         (ms)       Cnt Num
0   10.10.10.1      Et0/1              13 00:05:32    3   100  0  3
1   10.10.10.5      Et0/2              12 00:03:10    5   200  0  7
2   10.10.10.9      Ethernet0/3        11 01:00:00    2    50  0  12
"""

EIGRP_EMPTY = """\
EIGRP-IPv4 Neighbors for AS(10)
H   Address         Interface        Hold Uptime   SRTT   RTO  Q  Seq
                                      (sec)         (ms)       Cnt Num
"""

EIGRP_HEADER_ONLY = """\
EIGRP-IPv4 Neighbors for AS(10)
"""


# ── Single neighbor ────────────────────────────────────────────────────────────

def test_eigrp_single_neighbor_ip():
    result = normalize_eigrp_neighbors({"raw": EIGRP_SINGLE, "cli_style": "ios"})
    assert len(result) == 1
    assert result[0]["neighbor_ip"] == "10.10.10.1"


def test_eigrp_single_neighbor_interface():
    result = normalize_eigrp_neighbors({"raw": EIGRP_SINGLE, "cli_style": "ios"})
    assert result[0]["interface"] == "Et0/1"


# ── Multiple neighbors ────────────────────────────────────────────────────────

def test_eigrp_multi_count():
    result = normalize_eigrp_neighbors({"raw": EIGRP_MULTI, "cli_style": "ios"})
    assert len(result) == 3


def test_eigrp_multi_neighbor_ips():
    result = normalize_eigrp_neighbors({"raw": EIGRP_MULTI, "cli_style": "ios"})
    ips = {n["neighbor_ip"] for n in result}
    assert "10.10.10.1" in ips
    assert "10.10.10.5" in ips
    assert "10.10.10.9" in ips


def test_eigrp_multi_interfaces():
    result = normalize_eigrp_neighbors({"raw": EIGRP_MULTI, "cli_style": "ios"})
    intfs = {n["interface"] for n in result}
    assert "Et0/1" in intfs
    assert "Et0/2" in intfs
    assert "Ethernet0/3" in intfs


# ── Empty / header-only ───────────────────────────────────────────────────────

def test_eigrp_empty_output():
    result = normalize_eigrp_neighbors({"raw": EIGRP_EMPTY, "cli_style": "ios"})
    assert result == []


def test_eigrp_header_only():
    result = normalize_eigrp_neighbors({"raw": EIGRP_HEADER_ONLY, "cli_style": "ios"})
    assert result == []


def test_eigrp_completely_empty():
    result = normalize_eigrp_neighbors({"raw": "", "cli_style": "ios"})
    assert result == []


# ── Non-string raw ────────────────────────────────────────────────────────────

def test_eigrp_non_string_raw():
    result = normalize_eigrp_neighbors({"raw": None, "cli_style": "ios"})
    assert result == []


# ── Header line not included ──────────────────────────────────────────────────

def test_eigrp_header_lines_skipped():
    result = normalize_eigrp_neighbors({"raw": EIGRP_MULTI, "cli_style": "ios"})
    for n in result:
        assert n["neighbor_ip"].count(".") == 3
        assert all(part.isdigit() for part in n["neighbor_ip"].split("."))
