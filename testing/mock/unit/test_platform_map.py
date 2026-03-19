"""UT-008 — PLATFORM_MAP structure and get_action() behaviour."""
import pytest

from platforms.platform_map import PLATFORM_MAP, get_action, _apply_vrf


_VENDORS = ["ios", "eos", "junos", "aos", "routeros", "vyos"]
_REQUIRED_CATEGORIES = ["ospf", "bgp", "routing_table", "routing_policies", "interfaces"]


# ── All vendors present ───────────────────────────────────────────────────────

def test_all_vendors_present():
    for vendor in _VENDORS:
        assert vendor in PLATFORM_MAP, f"Vendor {vendor!r} missing from PLATFORM_MAP"


# ── All 5 required categories per vendor ──────────────────────────────────────

@pytest.mark.parametrize("vendor", _VENDORS)
def test_vendor_has_all_required_categories(vendor):
    entry = PLATFORM_MAP[vendor]
    for cat in _REQUIRED_CATEGORIES:
        assert cat in entry, f"{vendor} missing category {cat!r}"


# ── IOS has eigrp ─────────────────────────────────────────────────────────────

def test_ios_has_eigrp():
    assert "eigrp" in PLATFORM_MAP["ios"]


@pytest.mark.parametrize("vendor", ["eos", "junos", "aos", "routeros", "vyos"])
def test_non_ios_has_no_eigrp(vendor):
    assert "eigrp" not in PLATFORM_MAP[vendor]


# ── No empty command strings ──────────────────────────────────────────────────

@pytest.mark.parametrize("vendor", _VENDORS)
def test_no_empty_commands(vendor):
    entry = PLATFORM_MAP[vendor]
    for cat, queries in entry.items():
        for query, action in queries.items():
            if isinstance(action, str):
                assert action.strip() != "", f"{vendor}/{cat}/{query} has empty command"
            elif isinstance(action, dict):
                for key, cmd in action.items():
                    assert isinstance(cmd, str), f"{vendor}/{cat}/{query}/{key} not a string"
                    assert cmd.strip() != "", f"{vendor}/{cat}/{query}/{key} has empty command"


# ── Dual-entry dicts have both keys ──────────────────────────────────────────

@pytest.mark.parametrize("vendor", _VENDORS)
def test_dual_entry_dicts_have_both_keys(vendor):
    entry = PLATFORM_MAP[vendor]
    for cat, queries in entry.items():
        for query, action in queries.items():
            if isinstance(action, dict):
                assert "default" in action, f"{vendor}/{cat}/{query} missing 'default' key"
                assert "vrf" in action, f"{vendor}/{cat}/{query} missing 'vrf' key"


# ── VRF templates contain {vrf} when command varies by VRF ────────────────────

@pytest.mark.parametrize("vendor", _VENDORS)
def test_vrf_templates_contain_placeholder_when_different(vendor):
    entry = PLATFORM_MAP[vendor]
    for cat, queries in entry.items():
        for query, action in queries.items():
            if isinstance(action, dict) and "vrf" in action and "default" in action:
                vrf_cmd = action["vrf"]
                default_cmd = action["default"]
                # When VRF template differs from default, it must contain {vrf}
                if vrf_cmd != default_cmd:
                    assert "{vrf}" in vrf_cmd, (
                        f"{vendor}/{cat}/{query} VRF template differs from default "
                        f"but missing {{vrf}}: {vrf_cmd!r}"
                    )


# ── get_action returns correct strings ────────────────────────────────────────

def test_get_action_ios_ospf_neighbors():
    device = {"cli_style": "ios", "transport": "asyncssh"}
    result = get_action(device, "ospf", "neighbors")
    assert result == "show ip ospf neighbor"


def test_get_action_junos_interfaces():
    device = {"cli_style": "junos", "transport": "asyncssh"}
    result = get_action(device, "interfaces", "interface_status")
    assert result == "show interfaces terse"


def test_get_action_routeros_bgp_summary():
    device = {"cli_style": "routeros", "transport": "asyncssh"}
    result = get_action(device, "bgp", "summary")
    assert result == "/routing bgp session print without-paging"


def test_get_action_aos_ospf_neighbors():
    device = {"cli_style": "aos", "transport": "asyncssh"}
    result = get_action(device, "ospf", "neighbors")
    assert result == "show ip ospf neighbors"


def test_get_action_eos_interfaces():
    device = {"cli_style": "eos", "transport": "asyncssh"}
    result = get_action(device, "interfaces", "interface_status")
    assert result == "show ip interface brief"


def test_get_action_vyos_ospf_detail():
    device = {"cli_style": "vyos", "transport": "asyncssh"}
    result = get_action(device, "ospf", "details")
    # No VRF → default command
    assert result == "show ip ospf"


# ── VRF resolution via get_action ─────────────────────────────────────────────

def test_get_action_vrf_explicit():
    device = {"cli_style": "ios", "transport": "asyncssh", "vrf": None}
    result = get_action(device, "bgp", "summary", vrf="VRF1")
    assert "VRF1" in result
    assert "vpnv4" in result


def test_get_action_vrf_from_device():
    device = {"cli_style": "ios", "transport": "asyncssh", "vrf": "VRF1"}
    result = get_action(device, "bgp", "summary")
    assert "VRF1" in result


def test_get_action_no_vrf_uses_default():
    device = {"cli_style": "ios", "transport": "asyncssh", "vrf": None}
    result = get_action(device, "bgp", "summary")
    assert result == "show ip bgp summary"


def test_get_action_unknown_cli_style_raises():
    device = {"cli_style": "unknown_vendor", "transport": "asyncssh"}
    with pytest.raises(KeyError):
        get_action(device, "ospf", "neighbors")


# ── _apply_vrf ────────────────────────────────────────────────────────────────

def test_apply_vrf_dual_entry_with_vrf():
    action = {"default": "show ip bgp summary", "vrf": "show ip bgp vpnv4 vrf {vrf} summary"}
    result = _apply_vrf(action, "VRF1")
    assert result == "show ip bgp vpnv4 vrf VRF1 summary"


def test_apply_vrf_dual_entry_no_vrf():
    action = {"default": "show ip bgp summary", "vrf": "show ip bgp vpnv4 vrf {vrf} summary"}
    result = _apply_vrf(action, None)
    assert result == "show ip bgp summary"


def test_apply_vrf_plain_string_with_template_and_vrf():
    result = _apply_vrf("show ip route vrf {vrf}", "VRF1")
    assert result == "show ip route vrf VRF1"


def test_apply_vrf_plain_string_no_vrf():
    result = _apply_vrf("show ip ospf neighbor", "VRF1")
    assert result == "show ip ospf neighbor"


def test_apply_vrf_plain_string_no_template():
    result = _apply_vrf("show ip ospf neighbor", None)
    assert result == "show ip ospf neighbor"
