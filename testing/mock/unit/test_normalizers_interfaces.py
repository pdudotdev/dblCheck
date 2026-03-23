"""UT-001 — Interface normalizers for all 6 vendors."""
from validation.normalizers import normalize_interfaces

# ── IOS / IOS-XE ──────────────────────────────────────────────────────────────
IOS_INTF_OUTPUT = """\
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet1       192.168.1.1     YES NVRAM  administratively down down
GigabitEthernet2       10.0.0.1        YES NVRAM  up                   up
GigabitEthernet3       10.0.0.5        YES NVRAM  up                   down
GigabitEthernet4       unassigned      YES NVRAM  up                   up
Loopback0              1.1.1.1         YES NVRAM  up                   up
"""

# ── Arista EOS ────────────────────────────────────────────────────────────────
EOS_INTF_OUTPUT = """\
                                                              Address
Interface         IP Address           Status     Protocol    MTU  Owner
Ethernet1         10.0.0.1/30          up         up          1500
Ethernet2         10.0.0.5/30          down       down        1500
Ethernet3         unassigned           up         up          1500
Management1       192.168.1.100/24     up         up          1500
"""

# ── Juniper JunOS ─────────────────────────────────────────────────────────────
JUNOS_INTF_OUTPUT = """\
Interface               Admin Link Proto    Local                 Remote
et-0/0/0                up    up   inet     10.0.0.1/30
et-0/0/0.0              up    up   inet     10.0.0.1/30
et-0/0/1                up    down
et-0/0/1.0              up    down inet
et-0/0/2                down  down
lo0                     up    up
lo0.0                   up    up   inet     1.1.1.1/32
"""

# ── Aruba AOS-CX ──────────────────────────────────────────────────────────────
AOS_INTF_OUTPUT = """\
Port    Native Vlan  Mode   Type    Enabled Status
1/1/2   --           routed L3      yes     up
1/1/3   --           routed L3      yes     down
1/1/4   --           routed L3      no      down
1/1/5   --           routed L3      yes     up
"""

# ── MikroTik RouterOS ─────────────────────────────────────────────────────────
ROS_INTF_OUTPUT = """\
Flags: D - dynamic, X - disabled, R - running, S - slave
 0  R  ether1                  ether    1500
 1  RS ether2                  ether    1500
 2  X  ether3                  ether    1500
 3     ether4                  ether    1500
"""

# ── VyOS / FRR ────────────────────────────────────────────────────────────────
VYOS_INTF_OUTPUT = """\
Codes: S - State, L - Link, u - Up, D - Down, A - Admin Down
Interface        IP Address                        S/L  Description
---------        ----------                        ---  -----------
eth0             192.168.1.1/30                    u/u  WAN
eth1             10.0.0.1/30                       u/u
eth2             -                                 D/D
eth3             -                                 A/D  admin disabled
dum0             10.9.9.1/32                       u/u
"""


# ── IOS tests ────────────────────────────────────────────────────────────────

def test_ios_up_up():
    result = normalize_interfaces({"raw": IOS_INTF_OUTPUT, "cli_style": "ios"})
    assert result["GigabitEthernet2"] == "up/up"


def test_ios_admin_down():
    result = normalize_interfaces({"raw": IOS_INTF_OUTPUT, "cli_style": "ios"})
    assert result["GigabitEthernet1"] == "down/down"


def test_ios_up_down():
    result = normalize_interfaces({"raw": IOS_INTF_OUTPUT, "cli_style": "ios"})
    assert result["GigabitEthernet3"] == "up/down"


def test_ios_loopback():
    result = normalize_interfaces({"raw": IOS_INTF_OUTPUT, "cli_style": "ios"})
    assert result["Loopback0"] == "up/up"


def test_ios_multiple_interfaces():
    result = normalize_interfaces({"raw": IOS_INTF_OUTPUT, "cli_style": "ios"})
    assert len(result) == 5
    assert "Interface" not in result


def test_ios_empty_output():
    result = normalize_interfaces({"raw": "", "cli_style": "ios"})
    assert result == {}


# ── EOS tests ─────────────────────────────────────────────────────────────────

def test_eos_up_up():
    result = normalize_interfaces({"raw": EOS_INTF_OUTPUT, "cli_style": "eos"})
    assert result["Ethernet1"] == "up/up"


def test_eos_down_down():
    result = normalize_interfaces({"raw": EOS_INTF_OUTPUT, "cli_style": "eos"})
    assert result["Ethernet2"] == "down/down"


def test_eos_header_skipped():
    result = normalize_interfaces({"raw": EOS_INTF_OUTPUT, "cli_style": "eos"})
    assert "Interface" not in result


def test_eos_management():
    result = normalize_interfaces({"raw": EOS_INTF_OUTPUT, "cli_style": "eos"})
    assert result["Management1"] == "up/up"


def test_eos_multiple_interfaces():
    result = normalize_interfaces({"raw": EOS_INTF_OUTPUT, "cli_style": "eos"})
    assert len(result) == 4


# ── JunOS tests ───────────────────────────────────────────────────────────────

def test_junos_up_up():
    result = normalize_interfaces({"raw": JUNOS_INTF_OUTPUT, "cli_style": "junos"})
    assert result["et-0/0/0"] == "up/up"


def test_junos_up_down():
    result = normalize_interfaces({"raw": JUNOS_INTF_OUTPUT, "cli_style": "junos"})
    assert result["et-0/0/1"] == "up/down"


def test_junos_down_down():
    result = normalize_interfaces({"raw": JUNOS_INTF_OUTPUT, "cli_style": "junos"})
    assert result["et-0/0/2"] == "down/down"


def test_junos_sub_interfaces_skipped():
    result = normalize_interfaces({"raw": JUNOS_INTF_OUTPUT, "cli_style": "junos"})
    assert "et-0/0/0.0" not in result
    assert "lo0.0" not in result


def test_junos_loopback():
    result = normalize_interfaces({"raw": JUNOS_INTF_OUTPUT, "cli_style": "junos"})
    assert result["lo0"] == "up/up"


# ── AOS tests ─────────────────────────────────────────────────────────────────

def test_aos_up_up():
    result = normalize_interfaces({"raw": AOS_INTF_OUTPUT, "cli_style": "aos"})
    assert result["1/1/2"] == "up/up"


def test_aos_enabled_but_down():
    result = normalize_interfaces({"raw": AOS_INTF_OUTPUT, "cli_style": "aos"})
    assert result["1/1/3"] == "up/down"


def test_aos_disabled():
    result = normalize_interfaces({"raw": AOS_INTF_OUTPUT, "cli_style": "aos"})
    assert result["1/1/4"] == "down/down"


def test_aos_port_format():
    result = normalize_interfaces({"raw": AOS_INTF_OUTPUT, "cli_style": "aos"})
    assert "1/1/5" in result
    assert result["1/1/5"] == "up/up"


# ── RouterOS tests ────────────────────────────────────────────────────────────

def test_routeros_running():
    result = normalize_interfaces({"raw": ROS_INTF_OUTPUT, "cli_style": "routeros"})
    assert result["ether1"] == "up/up"


def test_routeros_running_slave():
    result = normalize_interfaces({"raw": ROS_INTF_OUTPUT, "cli_style": "routeros"})
    assert result["ether2"] == "up/up"


def test_routeros_disabled():
    result = normalize_interfaces({"raw": ROS_INTF_OUTPUT, "cli_style": "routeros"})
    assert result["ether3"] == "down/down"


def test_routeros_no_flags():
    result = normalize_interfaces({"raw": ROS_INTF_OUTPUT, "cli_style": "routeros"})
    assert result["ether4"] == "up/down"


def test_routeros_flags_line_skipped():
    result = normalize_interfaces({"raw": ROS_INTF_OUTPUT, "cli_style": "routeros"})
    assert "Flags:" not in result
    assert "D" not in result


# ── VyOS tests ────────────────────────────────────────────────────────────────

def test_vyos_up_up():
    result = normalize_interfaces({"raw": VYOS_INTF_OUTPUT, "cli_style": "vyos"})
    assert result["eth0"] == "up/up"
    assert result["eth1"] == "up/up"


def test_vyos_down_down():
    result = normalize_interfaces({"raw": VYOS_INTF_OUTPUT, "cli_style": "vyos"})
    assert result["eth2"] == "down/down"


def test_vyos_admin_down():
    result = normalize_interfaces({"raw": VYOS_INTF_OUTPUT, "cli_style": "vyos"})
    assert result["eth3"] == "down/down"


def test_vyos_loopback():
    result = normalize_interfaces({"raw": VYOS_INTF_OUTPUT, "cli_style": "vyos"})
    assert result["dum0"] == "up/up"


def test_vyos_header_skipped():
    result = normalize_interfaces({"raw": VYOS_INTF_OUTPUT, "cli_style": "vyos"})
    assert "Interface" not in result
    assert "Codes:" not in result


# ── Dispatcher tests ──────────────────────────────────────────────────────────

def test_dispatcher_defaults_to_ios():
    result = normalize_interfaces({"raw": IOS_INTF_OUTPUT})
    assert "GigabitEthernet2" in result


def test_dispatcher_unknown_style_falls_back_to_ios():
    result = normalize_interfaces({"raw": IOS_INTF_OUTPUT, "cli_style": "unknown_vendor"})
    assert "GigabitEthernet2" in result


def test_non_string_raw_returns_empty():
    result = normalize_interfaces({"raw": None, "cli_style": "ios"})
    assert result == {}
