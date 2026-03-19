"""UT-002 — OSPF normalizers: neighbors, details, and helpers."""
import pytest
from validation.normalizers import (
    normalize_ospf_neighbors,
    normalize_ospf_details,
    _normalize_ospf_state,
    _area_id_to_int,
)


# ── IOS OSPF neighbor fixture ─────────────────────────────────────────────────
IOS_OSPF_NBR = """\
Neighbor ID     Pri   State           Dead Time   Address         Interface
11.11.11.11       1   FULL/DR         00:00:37    10.0.0.5        Ethernet1/3
22.22.22.11       1   FULL/BDR        00:00:38    10.0.0.9        Ethernet1/2
3.3.3.3           1   INIT/           00:00:30    10.1.1.17       Ethernet0/3
"""

# ── EOS OSPF neighbor fixture ─────────────────────────────────────────────────
EOS_OSPF_NBR = """\
Neighbor ID     VRF      Pri State      Dead Time   Address         Interface
11.11.11.11     default  1   FULL/DR    00:00:34    10.0.0.5        Ethernet3
22.22.22.22     default  1   FULL/BDR   00:00:30    10.0.0.17       Ethernet2
3.3.3.3         default  1   INIT       00:00:25    10.0.0.21       Ethernet4
"""

# ── JunOS OSPF neighbor fixture ───────────────────────────────────────────────
JUNOS_OSPF_NBR = """\
Address          Interface              State     ID               Pri  Dead
10.0.0.5         et-0/0/4.0             Full      11.11.11.11       128    31
10.0.0.13        et-0/0/3.0             Full      11.11.11.22       128    37
10.0.0.21        et-0/0/2.0             ExStart   22.22.22.22       128    39
"""

# ── AOS OSPF neighbor fixture ─────────────────────────────────────────────────
AOS_OSPF_NBR = """\
Neighbor ID     Pri State            NbrAddress      Interface
11.11.11.11       1 FULL/DR         10.1.1.6        1/1/2
11.11.11.22       1 FULL            10.0.0.13       1/1/7
2.2.2.2           1 INIT            10.1.1.13       1/1/3
"""

# ── RouterOS OSPF neighbor fixture ───────────────────────────────────────────
ROS_OSPF_NBR = """\
 0 router-id=11.11.11.11 address=10.0.0.5 state=full interface=bridge1
 1 router-id=22.22.22.11 address=10.0.0.25 state=full interface=ether2
 2 router-id=3.3.3.3 address=10.1.1.1 state=init interface=ether3
"""

# ── VyOS OSPF neighbor fixture ────────────────────────────────────────────────
VYOS_OSPF_NBR = """\
Neighbor ID     Pri State           Dead Time Address         Interface         \
    RXmtL RqstL DBsmL
2.2.2.2           1 Full/DROther      37.672s 10.1.1.9        eth1:10.1.1.13   \
            0     0     0
11.11.11.11       1 Full/DR           39.100s 10.0.0.5        eth0:10.0.0.42   \
            0     0     0
3.3.3.3           1 Init              29.000s 10.0.0.9        eth2:10.0.0.10   \
            0     0     0
"""

# ── IOS OSPF detail fixtures ──────────────────────────────────────────────────
IOS_OSPF_DETAIL = """\
 Routing Process "ospf 1" with ID 11.11.11.11
 Start time: 00:01:13.232, Time elapsed: 1d05h

    Area BACKBONE(0)
        Number of interfaces in this area is 3
    Area 1
        It is a stub area
        Number of interfaces in this area is 4
"""
IOS_OSPF_DETAIL_DEFLT = """\
 Routing Process "ospf 1" with ID 33.33.33.11
 default-information originate always
    Area BACKBONE(0)
"""

# ── EOS OSPF detail fixtures ──────────────────────────────────────────────────
EOS_OSPF_DETAIL = """\
 Router OSPF 1 with ID 22.22.22.22 and Name default
 Area 0 is active, has 5 interfaces (Stub)
 Area 1 is active, has 4 interfaces (NSSA)
"""

# ── JunOS OSPF detail fixture ─────────────────────────────────────────────────
JUNOS_OSPF_DETAIL = """\
 Instance: master
   Router ID: 22.22.22.11
   Route table index: 0
   Area: 0.0.0.0
     Stub type: Not Stub
   Area: 0.0.0.1
     Stub type: Stub
"""

# ── AOS OSPF detail fixture ───────────────────────────────────────────────────
AOS_OSPF_DETAIL = """\
 OSPF Process 1 with Router ID: 11.11.11.22
 Area  : 0.0.0.0
   Area type : normal
 Area  : 0.0.0.1
   Area Type : Stub
"""

# ── RouterOS OSPF detail fixture ──────────────────────────────────────────────
ROS_OSPF_DETAIL = """\
 0 name="default" router-id=1.1.1.1 distribute-default=never
"""
ROS_OSPF_AREA_CFG = """\
 0 name="area1" area-id=0.0.0.1 type=stub
 1 name="backbone" area-id=0.0.0.0 type=default
"""
ROS_OSPF_DETAIL_DEFLT = """\
 0 name="default" router-id=33.33.33.11 distribute-default=always
"""

# ── VyOS OSPF detail fixture ──────────────────────────────────────────────────
VYOS_OSPF_DETAIL = """\
 OSPF Routing Process, Router ID: 10.9.9.1
 Area ID: 0.0.0.0 [Backbone]
 Area ID: 0.0.0.1 [Stub]
"""


# ── IOS neighbor tests ────────────────────────────────────────────────────────

def test_ios_ospf_neighbor_full():
    result = normalize_ospf_neighbors({"raw": IOS_OSPF_NBR, "cli_style": "ios"})
    full = [n for n in result if n["neighbor_id"] == "11.11.11.11"]
    assert len(full) == 1
    assert full[0]["state"] == "FULL"


def test_ios_ospf_neighbor_interface():
    result = normalize_ospf_neighbors({"raw": IOS_OSPF_NBR, "cli_style": "ios"})
    n = next(n for n in result if n["neighbor_id"] == "11.11.11.11")
    assert n["interface"] == "Ethernet1/3"


def test_ios_ospf_neighbor_init():
    result = normalize_ospf_neighbors({"raw": IOS_OSPF_NBR, "cli_style": "ios"})
    init = [n for n in result if n["state"] == "INIT"]
    assert len(init) == 1
    assert init[0]["neighbor_id"] == "3.3.3.3"


def test_ios_ospf_neighbor_count():
    result = normalize_ospf_neighbors({"raw": IOS_OSPF_NBR, "cli_style": "ios"})
    assert len(result) == 3


def test_ios_ospf_neighbor_header_skipped():
    result = normalize_ospf_neighbors({"raw": IOS_OSPF_NBR, "cli_style": "ios"})
    assert len(result) == 3
    assert all(_is_ip(n["neighbor_id"]) for n in result)


# ── EOS neighbor tests ────────────────────────────────────────────────────────

def test_eos_ospf_neighbor_full():
    result = normalize_ospf_neighbors({"raw": EOS_OSPF_NBR, "cli_style": "eos"})
    full = [n for n in result if n["state"] == "FULL"]
    assert len(full) == 2


def test_eos_ospf_neighbor_interface():
    result = normalize_ospf_neighbors({"raw": EOS_OSPF_NBR, "cli_style": "eos"})
    n = next(n for n in result if n["neighbor_id"] == "11.11.11.11")
    assert n["interface"] == "Ethernet3"


def test_eos_ospf_neighbor_init():
    result = normalize_ospf_neighbors({"raw": EOS_OSPF_NBR, "cli_style": "eos"})
    init = [n for n in result if n["state"] == "INIT"]
    assert len(init) == 1


# ── JunOS neighbor tests ──────────────────────────────────────────────────────

def test_junos_ospf_neighbor_full():
    result = normalize_ospf_neighbors({"raw": JUNOS_OSPF_NBR, "cli_style": "junos"})
    full = [n for n in result if n["state"] == "FULL"]
    assert len(full) == 2


def test_junos_ospf_neighbor_id():
    result = normalize_ospf_neighbors({"raw": JUNOS_OSPF_NBR, "cli_style": "junos"})
    n = next(n for n in result if n["interface"] == "et-0/0/4")
    assert n["neighbor_id"] == "11.11.11.11"


def test_junos_ospf_unit_suffix_stripped():
    result = normalize_ospf_neighbors({"raw": JUNOS_OSPF_NBR, "cli_style": "junos"})
    assert len(result) == 3
    for n in result:
        assert "." not in n["interface"]


def test_junos_ospf_exstart():
    result = normalize_ospf_neighbors({"raw": JUNOS_OSPF_NBR, "cli_style": "junos"})
    exstart = [n for n in result if n["state"] == "EXSTART"]
    assert len(exstart) == 1


# ── AOS neighbor tests ────────────────────────────────────────────────────────

def test_aos_ospf_neighbor_full():
    result = normalize_ospf_neighbors({"raw": AOS_OSPF_NBR, "cli_style": "aos"})
    full = [n for n in result if n["state"] == "FULL"]
    assert len(full) == 2


def test_aos_ospf_neighbor_interface():
    result = normalize_ospf_neighbors({"raw": AOS_OSPF_NBR, "cli_style": "aos"})
    n = next(n for n in result if n["neighbor_id"] == "11.11.11.11")
    assert n["interface"] == "1/1/2"


# ── RouterOS neighbor tests ───────────────────────────────────────────────────

def test_routeros_ospf_neighbor_full():
    result = normalize_ospf_neighbors({"raw": ROS_OSPF_NBR, "cli_style": "routeros"})
    full = [n for n in result if n["state"] == "FULL"]
    assert len(full) == 2


def test_routeros_ospf_neighbor_id():
    result = normalize_ospf_neighbors({"raw": ROS_OSPF_NBR, "cli_style": "routeros"})
    n = next(n for n in result if n["neighbor_id"] == "11.11.11.11")
    assert n["interface"] == "bridge1"


def test_routeros_ospf_neighbor_address():
    result = normalize_ospf_neighbors({"raw": ROS_OSPF_NBR, "cli_style": "routeros"})
    n = next(n for n in result if n["neighbor_id"] == "11.11.11.11")
    assert n["address"] == "10.0.0.5"


def test_routeros_ospf_neighbor_init():
    result = normalize_ospf_neighbors({"raw": ROS_OSPF_NBR, "cli_style": "routeros"})
    init = [n for n in result if n["state"] == "INIT"]
    assert len(init) == 1


# ── VyOS neighbor tests ───────────────────────────────────────────────────────

def test_vyos_ospf_neighbor_full():
    result = normalize_ospf_neighbors({"raw": VYOS_OSPF_NBR, "cli_style": "vyos"})
    full = [n for n in result if n["state"] == "FULL"]
    assert len(full) == 2


def test_vyos_ospf_interface_colon_stripped():
    result = normalize_ospf_neighbors({"raw": VYOS_OSPF_NBR, "cli_style": "vyos"})
    assert len(result) == 3
    for n in result:
        assert ":" not in n["interface"]


def test_vyos_ospf_neighbor_id():
    result = normalize_ospf_neighbors({"raw": VYOS_OSPF_NBR, "cli_style": "vyos"})
    assert any(n["neighbor_id"] == "2.2.2.2" for n in result)


# ── IOS detail tests ──────────────────────────────────────────────────────────

def test_ios_ospf_detail_router_id():
    result = normalize_ospf_details({"raw": IOS_OSPF_DETAIL, "cli_style": "ios"})
    assert result["router_id"] == "11.11.11.11"


def test_ios_ospf_detail_stub_area():
    result = normalize_ospf_details({"raw": IOS_OSPF_DETAIL, "cli_style": "ios"})
    assert result["areas"].get("1") == "stub"


def test_ios_ospf_detail_default_originate_from_config():
    result = normalize_ospf_details(
        {"raw": IOS_OSPF_DETAIL_DEFLT, "cli_style": "ios"},
        config_raw="default-information originate always",
    )
    assert result["default_originate"] is True


def test_ios_ospf_detail_no_default_originate():
    result = normalize_ospf_details({"raw": IOS_OSPF_DETAIL, "cli_style": "ios"})
    assert result["default_originate"] is False


# ── EOS detail tests ──────────────────────────────────────────────────────────

def test_eos_ospf_detail_router_id():
    result = normalize_ospf_details({"raw": EOS_OSPF_DETAIL, "cli_style": "eos"})
    assert result["router_id"] == "22.22.22.22"


def test_eos_ospf_detail_stub_area():
    result = normalize_ospf_details({"raw": EOS_OSPF_DETAIL, "cli_style": "eos"})
    assert result["areas"].get("0") == "stub"


def test_eos_ospf_detail_nssa_area():
    result = normalize_ospf_details({"raw": EOS_OSPF_DETAIL, "cli_style": "eos"})
    assert result["areas"].get("1") == "nssa"


# ── JunOS detail tests ────────────────────────────────────────────────────────

def test_junos_ospf_detail_router_id():
    result = normalize_ospf_details({"raw": JUNOS_OSPF_DETAIL, "cli_style": "junos"})
    assert result["router_id"] == "22.22.22.11"


def test_junos_ospf_detail_stub_area():
    result = normalize_ospf_details({"raw": JUNOS_OSPF_DETAIL, "cli_style": "junos"})
    assert result["areas"].get("1") == "stub"


def test_junos_ospf_detail_normal_area():
    result = normalize_ospf_details({"raw": JUNOS_OSPF_DETAIL, "cli_style": "junos"})
    assert result["areas"].get("0") == "normal"


# ── AOS detail tests ──────────────────────────────────────────────────────────

def test_aos_ospf_detail_router_id():
    result = normalize_ospf_details({"raw": AOS_OSPF_DETAIL, "cli_style": "aos"})
    assert result["router_id"] == "11.11.11.22"


def test_aos_ospf_detail_stub_area():
    result = normalize_ospf_details({"raw": AOS_OSPF_DETAIL, "cli_style": "aos"})
    assert result["areas"].get("1") == "stub"


# ── RouterOS detail tests ─────────────────────────────────────────────────────

def test_routeros_ospf_detail_router_id():
    result = normalize_ospf_details({"raw": ROS_OSPF_DETAIL, "cli_style": "routeros"})
    assert result["router_id"] == "1.1.1.1"


def test_routeros_ospf_detail_stub_area():
    result = normalize_ospf_details(
        {"raw": ROS_OSPF_DETAIL, "cli_style": "routeros"},
        config_raw=ROS_OSPF_AREA_CFG,
    )
    assert result["areas"].get("1") == "stub"


def test_routeros_ospf_detail_default_originate_never():
    result = normalize_ospf_details({"raw": ROS_OSPF_DETAIL, "cli_style": "routeros"})
    assert result["default_originate"] is False


def test_routeros_ospf_detail_default_originate_always():
    result = normalize_ospf_details({"raw": ROS_OSPF_DETAIL_DEFLT, "cli_style": "routeros"})
    assert result["default_originate"] is True


# ── VyOS detail tests ─────────────────────────────────────────────────────────

def test_vyos_ospf_detail_router_id():
    result = normalize_ospf_details({"raw": VYOS_OSPF_DETAIL, "cli_style": "vyos"})
    assert result["router_id"] == "10.9.9.1"


def test_vyos_ospf_detail_stub_area():
    result = normalize_ospf_details({"raw": VYOS_OSPF_DETAIL, "cli_style": "vyos"})
    assert result["areas"].get("1") == "stub"


# ── Empty-output tests ────────────────────────────────────────────────────────

@pytest.mark.parametrize("cli_style", ["ios", "eos", "junos", "aos", "routeros", "vyos"])
def test_ospf_neighbors_empty_raw(cli_style):
    result = normalize_ospf_neighbors({"raw": "", "cli_style": cli_style})
    assert result == []


@pytest.mark.parametrize("cli_style", ["ios", "eos", "junos", "aos", "routeros", "vyos"])
def test_ospf_details_empty_raw(cli_style):
    result = normalize_ospf_details({"raw": "", "cli_style": cli_style})
    assert result["router_id"] == ""
    assert result["areas"] == {}
    assert result["default_originate"] is False


# ── NSSA area-type fixtures ────────────────────────────────────────────────────

JUNOS_OSPF_DETAIL_NSSA = """\
 Instance: master
   Router ID: 22.22.22.11
   Area: 0.0.0.0
     Stub type: Not Stub
   Area: 0.0.0.2
     Stub type: NSSA
"""

AOS_OSPF_DETAIL_NSSA = """\
 OSPF Process 1 with Router ID: 11.11.11.22
 Area  : 0.0.0.0
   Area type : normal
 Area  : 0.0.0.2
   Area Type : NSSA
"""

ROS_OSPF_AREA_CFG_NSSA = """\
 0 name="area2" area-id=0.0.0.2 type=nssa
 1 name="backbone" area-id=0.0.0.0 type=default
"""

VYOS_OSPF_DETAIL_NSSA = """\
 OSPF Routing Process, Router ID: 10.9.9.1
 Area ID: 0.0.0.0 [Backbone]
 Area ID: 0.0.0.2 [NSSA]
"""


# ── NSSA area-type tests ───────────────────────────────────────────────────────

def test_junos_ospf_detail_nssa_area():
    result = normalize_ospf_details({"raw": JUNOS_OSPF_DETAIL_NSSA, "cli_style": "junos"})
    assert result["areas"].get("2") == "nssa"


def test_aos_ospf_detail_nssa_area():
    result = normalize_ospf_details({"raw": AOS_OSPF_DETAIL_NSSA, "cli_style": "aos"})
    assert result["areas"].get("2") == "nssa"


def test_routeros_ospf_detail_nssa_area():
    result = normalize_ospf_details(
        {"raw": ROS_OSPF_DETAIL, "cli_style": "routeros"},
        config_raw=ROS_OSPF_AREA_CFG_NSSA,
    )
    assert result["areas"].get("2") == "nssa"


def test_vyos_ospf_detail_nssa_area():
    result = normalize_ospf_details({"raw": VYOS_OSPF_DETAIL_NSSA, "cli_style": "vyos"})
    assert result["areas"].get("2") == "nssa"


# ── Default-originate tests for EOS / JunOS / AOS / VyOS ──────────────────────

def test_eos_ospf_detail_default_originate():
    result = normalize_ospf_details(
        {"raw": EOS_OSPF_DETAIL, "cli_style": "eos"},
        config_raw="default-information originate always",
    )
    assert result["default_originate"] is True


def test_eos_ospf_detail_no_default_originate():
    result = normalize_ospf_details({"raw": EOS_OSPF_DETAIL, "cli_style": "eos"})
    assert result["default_originate"] is False


def test_junos_ospf_detail_default_originate():
    result = normalize_ospf_details(
        {"raw": JUNOS_OSPF_DETAIL, "cli_style": "junos"},
        config_raw="generate-default { policy default-route; }",
    )
    assert result["default_originate"] is True


def test_junos_ospf_detail_no_default_originate():
    result = normalize_ospf_details({"raw": JUNOS_OSPF_DETAIL, "cli_style": "junos"})
    assert result["default_originate"] is False


def test_aos_ospf_detail_default_originate():
    result = normalize_ospf_details(
        {"raw": AOS_OSPF_DETAIL, "cli_style": "aos"},
        config_raw="default-information originate",
    )
    assert result["default_originate"] is True


def test_aos_ospf_detail_no_default_originate():
    result = normalize_ospf_details({"raw": AOS_OSPF_DETAIL, "cli_style": "aos"})
    assert result["default_originate"] is False


def test_vyos_ospf_detail_default_originate():
    result = normalize_ospf_details(
        {"raw": VYOS_OSPF_DETAIL, "cli_style": "vyos"},
        config_raw="set protocols ospf default-information originate",
    )
    assert result["default_originate"] is True


def test_vyos_ospf_detail_no_default_originate():
    result = normalize_ospf_details({"raw": VYOS_OSPF_DETAIL, "cli_style": "vyos"})
    assert result["default_originate"] is False


# ── _normalize_ospf_state parametrize ─────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("FULL/DR",       "FULL"),
    ("FULL/BDR",      "FULL"),
    ("Full",          "FULL"),
    ("full",          "FULL"),
    ("INIT/",         "INIT"),
    ("INIT",          "INIT"),
    ("2WAY/DROTHER",  "2WAY"),
    ("TWO-WAY",       "2WAY"),
    ("2way",          "2WAY"),
    ("EXSTART",       "EXSTART"),
    ("EXCHANGE",      "EXCHANGE"),
    ("DOWN",          "DOWN"),
    ("LOADING",       "LOADING"),
])
def test_normalize_ospf_state(raw, expected):
    assert _normalize_ospf_state(raw) == expected


# ── _area_id_to_int parametrize ────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("0.0.0.1",  "1"),
    ("0.0.0.0",  "0"),
    ("0.0.1.0",  "256"),
    ("1",        "1"),
    ("0",        "0"),
    ("10",       "10"),
])
def test_area_id_to_int(raw, expected):
    assert _area_id_to_int(raw) == expected


# ── helper ────────────────────────────────────────────────────────────────────

def _is_ip(s: str) -> bool:
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)
