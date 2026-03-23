PLATFORM_MAP = {
    # ── Cisco IOS-XE ──────────────────────────────────────────────────────────
    # VRF-sensitive queries use dual-entry: {"default": "<global cmd>", "vrf": "<vrf cmd>"}
    "ios": {
        "ospf": {
            "neighbors":  "show ip ospf neighbor",
            "database":   "show ip ospf database",
            "borders":    "show ip ospf border-routers",
            "config":     "show running-config | section ospf",
            "interfaces": "show ip ospf interface",
            "details":    "show ip ospf",
        },
        "bgp": {
            "summary":   {"default": "show ip bgp summary",               "vrf": "show ip bgp vpnv4 vrf {vrf} summary"},
            "table":     {"default": "show ip bgp",                       "vrf": "show ip bgp vpnv4 vrf {vrf}"},
            "config":    {"default": "show running-config | section bgp", "vrf": "show running-config | section bgp"},
            "neighbors": {"default": "show ip bgp neighbors",             "vrf": "show ip bgp vpnv4 vrf {vrf} neighbors"},
        },
        "eigrp": {
            "neighbors":  {"default": "show ip eigrp neighbors",  "vrf": "show ip eigrp vrf {vrf} neighbors"},
            "interfaces": {"default": "show ip eigrp interfaces", "vrf": "show ip eigrp vrf {vrf} interfaces"},
            "config":     "show running-config | section eigrp",
            "topology":   {"default": "show ip eigrp topology",   "vrf": "show ip eigrp vrf {vrf} topology"},
        },
        "routing_table": {
            "ip_route":  {"default": "show ip route",                     "vrf": "show ip route vrf {vrf}"},
        },
        "routing_policies": {
            "redistribution":       "show run | section redistribute",
            "route_maps":           "show route-map",
            "prefix_lists":         "show ip prefix-list",
            "policy_based_routing": "show ip policy",
            "access_lists":         "show ip access-lists",
        },
        "interfaces": {
            "interface_status": "show ip interface brief",
        },
    },

    # ── Arista EOS ────────────────────────────────────────────────────────────
    # IOS-like syntax. "section" is an EOS keyword — no pipe needed.
    # VRF keyword goes at the end of the command.
    "eos": {
        "ospf": {
            "neighbors":  {"default": "show ip ospf neighbor",       "vrf": "show ip ospf neighbor vrf {vrf}"},
            "database":   {"default": "show ip ospf database",       "vrf": "show ip ospf database vrf {vrf}"},
            "borders":    {"default": "show ip ospf border-routers", "vrf": "show ip ospf border-routers vrf {vrf}"},
            "config":     "show running-config section ospf",
            "interfaces": {"default": "show ip ospf interface",      "vrf": "show ip ospf interface vrf {vrf}"},
            "details":    {"default": "show ip ospf",                "vrf": "show ip ospf vrf {vrf}"},
        },
        "bgp": {
            "summary":   {"default": "show ip bgp summary",   "vrf": "show ip bgp summary vrf {vrf}"},
            "table":     {"default": "show ip bgp",           "vrf": "show ip bgp vrf {vrf}"},
            "config":    "show running-config section bgp",
            "neighbors": {"default": "show ip bgp neighbors", "vrf": "show ip bgp neighbors vrf {vrf}"},
        },
        "routing_table": {
            "ip_route":  {"default": "show ip route",         "vrf": "show ip route vrf {vrf}"},
        },
        "routing_policies": {
            "redistribution":       "show running-config section redistribute",
            "route_maps":           "show route-map",
            "prefix_lists":         "show ip prefix-list",
            "policy_based_routing": "show policy-map type pbr",
            "access_lists":         "show ip access-lists",
        },
        "interfaces": {
            "interface_status": "show ip interface brief",
        },
    },

    # ── Juniper JunOS ─────────────────────────────────────────────────────────
    # No "ip" prefix on protocol commands. VRF = routing-instance via "instance {vrf}".
    # Routing table VRF: "show route table {vrf}.inet.0".
    "junos": {
        "ospf": {
            "neighbors":  {"default": "show ospf neighbor",  "vrf": "show ospf neighbor instance {vrf}"},
            "database":   {"default": "show ospf database",  "vrf": "show ospf database instance {vrf}"},
            "borders":    {"default": "show ospf route abr", "vrf": "show ospf route abr instance {vrf}"},
            "config":     {"default": "show ospf overview",  "vrf": "show ospf overview instance {vrf}"},
            "interfaces": {"default": "show ospf interface", "vrf": "show ospf interface instance {vrf}"},
            "details":    {"default": "show ospf overview",  "vrf": "show ospf overview instance {vrf}"},
        },
        "bgp": {
            "summary":   {"default": "show bgp summary",        "vrf": "show bgp summary instance {vrf}"},
            "table":     {"default": "show route protocol bgp", "vrf": "show route protocol bgp table {vrf}.inet.0"},
            "config":    {"default": "show bgp summary",        "vrf": "show bgp summary instance {vrf}"},
            "neighbors": {"default": "show bgp neighbor",       "vrf": "show bgp neighbor instance {vrf}"},
        },
        "routing_table": {
            "ip_route":  {"default": "show route",              "vrf": "show route table {vrf}.inet.0"},
        },
        "routing_policies": {
            "redistribution":       "show configuration policy-options",
            "route_maps":           "show configuration policy-options",
            "prefix_lists":         "show configuration policy-options",
            "policy_based_routing": "show configuration routing-options",
            "access_lists":         "show configuration firewall",
        },
        "interfaces": {
            "interface_status": "show interfaces terse",
        },
    },

    # ── Aruba AOS-CX ─────────────────────────────────────────────────────────
    # BGP uses "show bgp" (not "show ip bgp"). OSPF uses plural "neighbors".
    # No "| section" filter — config queries return full running-config.
    # VRF: at end for OSPF/routing, before AFI keyword for BGP.
    "aos": {
        "ospf": {
            "neighbors":  {"default": "show ip ospf neighbors",      "vrf": "show ip ospf neighbors vrf {vrf}"},
            "database":   {"default": "show ip ospf lsdb",       "vrf": "show ip ospf lsdb vrf {vrf}"},
            "borders":    {"default": "show ip ospf border-routers", "vrf": "show ip ospf border-routers vrf {vrf}"},
            "config":     {"default": "show ip ospf",                "vrf": "show ip ospf vrf {vrf}"},
            "interfaces": {"default": "show ip ospf interface",      "vrf": "show ip ospf interface vrf {vrf}"},
            "details":    {"default": "show ip ospf",                "vrf": "show ip ospf vrf {vrf}"},
        },
        "bgp": {
            "summary":   {"default": "show bgp ipv4 unicast summary",   "vrf": "show bgp vrf {vrf} ipv4 unicast summary"},
            "table":     {"default": "show bgp ipv4 unicast",           "vrf": "show bgp vrf {vrf} ipv4 unicast"},
            "config":    {"default": "show bgp ipv4 unicast",           "vrf": "show bgp vrf {vrf} ipv4 unicast"},
            "neighbors": {"default": "show bgp ipv4 unicast neighbors", "vrf": "show bgp vrf {vrf} ipv4 unicast neighbors"},
        },
        "routing_table": {
            "ip_route":  {"default": "show ip route",                   "vrf": "show ip route vrf {vrf}"},
        },
        "routing_policies": {
            "redistribution":       "show running-config",
            "route_maps":           "show route-map",
            "prefix_lists":         "show ip prefix-list",
            "policy_based_routing": "show pbr summary",
            "access_lists":         "show access-list",
        },
        "interfaces": {
            "interface_status": "show interface brief",
        },
    },

    # ── MikroTik RouterOS 7 ───────────────────────────────────────────────────
    # Path-based CLI. Space-separated form used for NTC Template matching.
    # All commands need "without-paging" to disable pagination over SSH.
    # BGP: ROS7 uses "session"/"connection" (not "peer" from ROS6).
    # VRF = routing-table, filtered via "where routing-table={vrf}".
    "routeros": {
        "ospf": {
            "neighbors":  "/routing ospf neighbor print terse without-paging",
            "database":   "/routing ospf lsa print without-paging",
            "borders":    "/routing ospf instance print without-paging",
            "config":     "/routing ospf area print detail without-paging",
            "interfaces": "/routing ospf interface print terse without-paging",
            "details":    "/routing ospf instance print detail without-paging",
        },
        "bgp": {
            "summary":   "/routing bgp session print without-paging",
            "table":     "/routing bgp advertisements print without-paging",
            "config":    "/routing bgp connection print detail without-paging",
            "neighbors": "/routing bgp session print detail without-paging",
        },
        "routing_table": {
            "ip_route":  {"default": "/ip route print terse without-paging",
                          "vrf":     "/ip route print terse without-paging where routing-table={vrf}"},
        },
        "routing_policies": {
            "redistribution":       "/routing ospf instance print detail without-paging",
            "route_maps":           "/routing filter rule print without-paging",
            "prefix_lists":         "/routing filter rule print without-paging",
            "policy_based_routing": "/routing rule print without-paging",
            "access_lists":         "/ip firewall filter print without-paging",
        },
        "interfaces": {
            "interface_status": "/interface print brief without-paging",
        },
    },

    # ── VyOS (FRRouting) ─────────────────────────────────────────────────────
    # FRR-backed. IOS-like show commands. No "show ip interface brief" — use "show interfaces".
    # No "show configuration protocols ospf" in operational mode — use config-match filter.
    # VRF keyword: "vrf {vrf}" before sub-command for OSPF/BGP; after base command for routing.
    "vyos": {
        "ospf": {
            "neighbors":  {"default": "show ip ospf neighbor",       "vrf": "show ip ospf vrf {vrf} neighbor"},
            "database":   {"default": "show ip ospf database",       "vrf": "show ip ospf vrf {vrf} database"},
            "borders":    {"default": "show ip ospf border-routers", "vrf": "show ip ospf vrf {vrf} border-routers"},
            "config":     "show configuration commands | match ospf",
            "interfaces": {"default": "show ip ospf interface",      "vrf": "show ip ospf vrf {vrf} interface"},
            "details":    {"default": "show ip ospf",                "vrf": "show ip ospf vrf {vrf}"},
        },
        "bgp": {
            "summary":   {"default": "show ip bgp summary",   "vrf": "show ip bgp vrf {vrf} summary"},
            "table":     {"default": "show ip bgp",           "vrf": "show ip bgp vrf {vrf}"},
            "config":    "show configuration commands | match bgp",
            "neighbors": {"default": "show ip bgp neighbors", "vrf": "show ip bgp vrf {vrf} neighbors"},
        },
        "routing_table": {
            "ip_route":  {"default": "show ip route",         "vrf": "show ip route vrf {vrf}"},
        },
        "routing_policies": {
            "redistribution":       "show configuration commands | match redistribute",
            "route_maps":           "show ip protocol",
            "prefix_lists":         "show ip prefix-list",
            "policy_based_routing": "show configuration commands | match policy",
            "access_lists":         "show ip access-list",
        },
        "interfaces": {
            "interface_status": "show interfaces",
        },
    },

}


def _apply_vrf(action, vrf_name: str | None):
    """Apply VRF substitution to an action entry."""
    # Dual-entry CLI format: {"default": "...", "vrf": "..."}
    if isinstance(action, dict) and "default" in action and "vrf" in action:
        template = action["vrf"] if vrf_name else action["default"]
        return template.replace("{vrf}", vrf_name) if vrf_name else template

    # Plain CLI string with {vrf} template
    if isinstance(action, str) and vrf_name and "{vrf}" in action:
        return action.replace("{vrf}", vrf_name)

    return action


def get_action(device: dict, category: str, query: str, vrf: str | None = None):
    """Look up command/action from PLATFORM_MAP.

    Returns a plain CLI string or dual-entry dict (resolved to a string via VRF logic).

    Args:
        device:   Inventory entry dict (must have 'cli_style' key).
        category: Top-level PLATFORM_MAP section (e.g. 'ospf', 'interfaces').
        query:    Sub-key within that section (e.g. 'neighbors', 'interface_status').
        vrf:      Optional VRF name. If None, global routing table is used.

    Raises:
        KeyError: If the platform or category/query is not found in PLATFORM_MAP.
    """
    vrf_name = vrf or device.get("vrf")

    map_entry = PLATFORM_MAP.get(device["cli_style"])
    if not map_entry:
        raise KeyError(f"No platform map entry for cli_style={device['cli_style']!r}")

    action = map_entry[category][query]
    return _apply_vrf(action, vrf_name)
