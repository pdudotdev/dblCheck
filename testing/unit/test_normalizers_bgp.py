"""UT-003 — BGP summary normalizers for all 6 vendors + state helper."""
import pytest
from validation.normalizers import normalize_bgp_summary, _normalize_bgp_state


# ── IOS BGP summary fixture ───────────────────────────────────────────────────
IOS_BGP_SUMMARY = """\
BGP router identifier 33.33.33.11, local AS number 1010
BGP table version is 12, main routing table version 12

Neighbor        V           AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
200.40.40.2     4         4040      15      14       12    0    0 00:10:30        5
200.50.50.2     4         5050       8       7       12    0    0 00:05:10        3
10.0.0.1        4         1010       0       0        0    0    0 00:00:10 Active
"""

# ── EOS BGP summary fixture ───────────────────────────────────────────────────
EOS_BGP_SUMMARY = """\
BGP summary information for VRF default
Router identifier 22.22.22.22, local AS number 1010
Neighbor Status Codes: m - Under maintenance
  Neighbor         V AS           MsgRcvd   MsgSent  InQ OutQ  Up/Down State   PfxRcd PfxAcc
  200.40.40.1      4 4040              10        10    0    0  00:08:30 Estab   4      4
  200.50.50.1      4 5050               5         5    0    0  00:04:00 Estab   2      2
  10.0.0.5         4 1010               0         0    0    0  never    Active
"""

# ── JunOS BGP summary fixture ─────────────────────────────────────────────────
JUNOS_BGP_SUMMARY = """\
Groups: 2 Peers: 3 Down peers: 1
Table          Tot Paths  Act Paths Suppressed    History Damp State    Pending
inet.0               12          8          0          0          0          0
Peer                     AS      InPkt     OutPkt    OutQ   Flaps LastUp/Dwn State|#Active/Received/Accepted/Damped...
200.40.40.2           4040         25         20        0       0       11:22 6/8/6/0
200.50.50.2           5050         12         10        0       0        5:10 3/4/3/0
10.0.0.25              100          0          0        0       1        3:00 Active
"""

# ── AOS BGP summary fixture ───────────────────────────────────────────────────
AOS_BGP_SUMMARY = """\
Status codes: s suppressed, d damped, h history, * valid, > best, i internal
Neighbor        RemoteAS State     Up-Time   ...
200.40.40.1     4040     Established  00:10:30
200.50.50.1     5050     Established  00:06:00
10.0.0.1        1010     Active
"""

# ── RouterOS BGP session fixture ──────────────────────────────────────────────
ROS_BGP_SUMMARY = """\
Flags: E - established
 0 E 4040 200.40.40.2
 1 E 5050 200.50.50.2
 2   1010 10.0.0.5 active
"""

# ── VyOS BGP summary — delegates to IOS parser ───────────────────────────────
VYOS_BGP_SUMMARY = """\
BGP router identifier 10.9.9.1, local AS number 1010

Neighbor        V         AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
10.0.0.42       4       1010      22      20        5    0    0 01:00:00       12
10.0.0.1        4       1010       0       0        0    0    0 00:00:05 Idle
"""


# ── IOS tests ─────────────────────────────────────────────────────────────────

def test_ios_bgp_established():
    result = normalize_bgp_summary({"raw": IOS_BGP_SUMMARY, "cli_style": "ios"})
    estab = [n for n in result if n["neighbor_ip"] == "200.40.40.2"]
    assert len(estab) == 1
    assert estab[0]["state"] == "Established"


def test_ios_bgp_as_number():
    result = normalize_bgp_summary({"raw": IOS_BGP_SUMMARY, "cli_style": "ios"})
    n = next(n for n in result if n["neighbor_ip"] == "200.40.40.2")
    assert n["as"] == 4040


def test_ios_bgp_active_state():
    result = normalize_bgp_summary({"raw": IOS_BGP_SUMMARY, "cli_style": "ios"})
    active = [n for n in result if n["neighbor_ip"] == "10.0.0.1"]
    assert len(active) == 1
    assert active[0]["state"] == "Active"


def test_ios_bgp_multiple_peers():
    result = normalize_bgp_summary({"raw": IOS_BGP_SUMMARY, "cli_style": "ios"})
    assert len(result) == 3


def test_ios_bgp_header_skipped():
    result = normalize_bgp_summary({"raw": IOS_BGP_SUMMARY, "cli_style": "ios"})
    assert all(n["neighbor_ip"].count(".") == 3 for n in result)


# ── EOS tests ─────────────────────────────────────────────────────────────────

def test_eos_bgp_estab_abbreviation():
    result = normalize_bgp_summary({"raw": EOS_BGP_SUMMARY, "cli_style": "eos"})
    n = next(n for n in result if n["neighbor_ip"] == "200.40.40.1")
    assert n["state"] == "Established"


def test_eos_bgp_as_number():
    result = normalize_bgp_summary({"raw": EOS_BGP_SUMMARY, "cli_style": "eos"})
    n = next(n for n in result if n["neighbor_ip"] == "200.40.40.1")
    assert n["as"] == 4040


def test_eos_bgp_active():
    result = normalize_bgp_summary({"raw": EOS_BGP_SUMMARY, "cli_style": "eos"})
    active = [n for n in result if n["state"] == "Active"]
    assert len(active) == 1
    assert active[0]["neighbor_ip"] == "10.0.0.5"


def test_eos_bgp_count():
    result = normalize_bgp_summary({"raw": EOS_BGP_SUMMARY, "cli_style": "eos"})
    assert len(result) == 3


# ── JunOS tests ───────────────────────────────────────────────────────────────

def test_junos_bgp_counter_format_established():
    result = normalize_bgp_summary({"raw": JUNOS_BGP_SUMMARY, "cli_style": "junos"})
    n = next(n for n in result if n["neighbor_ip"] == "200.40.40.2")
    assert n["state"] == "Established"


def test_junos_bgp_as_number():
    result = normalize_bgp_summary({"raw": JUNOS_BGP_SUMMARY, "cli_style": "junos"})
    n = next(n for n in result if n["neighbor_ip"] == "200.40.40.2")
    assert n["as"] == 4040


def test_junos_bgp_active():
    result = normalize_bgp_summary({"raw": JUNOS_BGP_SUMMARY, "cli_style": "junos"})
    active = [n for n in result if n["state"] == "Active"]
    assert len(active) == 1


def test_junos_bgp_count():
    result = normalize_bgp_summary({"raw": JUNOS_BGP_SUMMARY, "cli_style": "junos"})
    assert len(result) == 3


# ── AOS tests ─────────────────────────────────────────────────────────────────

def test_aos_bgp_established():
    result = normalize_bgp_summary({"raw": AOS_BGP_SUMMARY, "cli_style": "aos"})
    estab = [n for n in result if n["state"] == "Established"]
    assert len(estab) == 2


def test_aos_bgp_as_number():
    result = normalize_bgp_summary({"raw": AOS_BGP_SUMMARY, "cli_style": "aos"})
    n = next(n for n in result if n["neighbor_ip"] == "200.40.40.1")
    assert n["as"] == 4040


def test_aos_bgp_active():
    result = normalize_bgp_summary({"raw": AOS_BGP_SUMMARY, "cli_style": "aos"})
    active = [n for n in result if n["state"] == "Active"]
    assert len(active) == 1


# ── RouterOS tests ────────────────────────────────────────────────────────────

def test_routeros_bgp_e_flag_established():
    result = normalize_bgp_summary({"raw": ROS_BGP_SUMMARY, "cli_style": "routeros"})
    estab = [n for n in result if n["state"] == "Established"]
    assert len(estab) == 2


def test_routeros_bgp_neighbor_ip():
    result = normalize_bgp_summary({"raw": ROS_BGP_SUMMARY, "cli_style": "routeros"})
    n = next(n for n in result if n["neighbor_ip"] == "200.40.40.2")
    assert n["as"] == 4040


def test_routeros_bgp_no_flag():
    result = normalize_bgp_summary({"raw": ROS_BGP_SUMMARY, "cli_style": "routeros"})
    non_estab = [n for n in result if n["state"] != "Established"]
    assert len(non_estab) == 1
    assert non_estab[0]["neighbor_ip"] == "10.0.0.5"
    assert non_estab[0]["state"] == "Active"


# ── VyOS tests ────────────────────────────────────────────────────────────────

def test_vyos_bgp_established():
    result = normalize_bgp_summary({"raw": VYOS_BGP_SUMMARY, "cli_style": "vyos"})
    n = next(n for n in result if n["neighbor_ip"] == "10.0.0.42")
    assert n["state"] == "Established"


def test_vyos_bgp_idle():
    result = normalize_bgp_summary({"raw": VYOS_BGP_SUMMARY, "cli_style": "vyos"})
    n = next(n for n in result if n["neighbor_ip"] == "10.0.0.1")
    assert n["state"] == "Idle"


# ── _normalize_bgp_state parametrize ──────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("42",          "Established"),
    ("0",           "Established"),
    ("Estab",       "Established"),
    ("Establ",      "Established"),
    ("Established", "Established"),
    ("established", "Established"),
    ("Active",      "Active"),
    ("active",      "Active"),
    ("Idle",        "Idle"),
    ("idle",        "Idle"),
    ("Connect",     "Connect"),
    ("OpenSent",    "OpenSent"),
    ("OpenConfirm", "OpenConfirm"),
    ("",            "Unknown"),
])
def test_normalize_bgp_state(raw, expected):
    assert _normalize_bgp_state(raw) == expected
