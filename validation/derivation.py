"""Read network intent and build a checklist of assertions.

No devices are contacted here — this is pure intent reading.
"""
from validation.assertions import Assertion, AssertionType


def derive_assertions(intent: dict) -> list[Assertion]:
    """Derive all validation assertions from an intent dict.

    Args:
        intent: Parsed intent dict (from NetBox config contexts).
    """
    routers = intent.get("routers", {})
    assertions: list[Assertion] = []

    for device, cfg in routers.items():
        assertions.extend(_derive_interfaces(device, cfg))
        assertions.extend(_derive_ospf(device, cfg, routers))
        assertions.extend(_derive_bgp(device, cfg))
        assertions.extend(_derive_eigrp(device, cfg, routers))

    return assertions


# ─── Interface assertions ────────────────────────────────────────────────────

def _derive_interfaces(device: str, cfg: dict) -> list[Assertion]:
    """Each entry in direct_links means that interface should be up/up."""
    assertions = []
    for peer, link in cfg.get("direct_links", {}).items():
        intf = link.get("local_interface", "")
        if not intf:
            continue
        assertions.append(Assertion(
            type=AssertionType.INTERFACE_UP,
            device=device,
            description=f"{device} {intf} (link to {peer}) should be up/up",
            expected="up/up",
            protocol="interface",
            peer=peer,
            interface=intf,
        ))
    return assertions


# ─── OSPF assertions ─────────────────────────────────────────────────────────

def _derive_ospf(device: str, cfg: dict, all_routers: dict) -> list[Assertion]:
    assertions = []
    ospf = cfg.get("igp", {}).get("ospf", {})
    if not ospf:
        return assertions

    assertions.extend(_derive_ospf_neighbors(device, cfg, ospf, all_routers))
    assertions.extend(_derive_ospf_router_id(device, ospf))
    assertions.extend(_derive_ospf_area_types(device, cfg, ospf))
    assertions.extend(_derive_ospf_default_originate(device, ospf))
    return assertions


def _derive_ospf_neighbors(device: str, cfg: dict, ospf: dict,
                           all_routers: dict) -> list[Assertion]:
    """For each link that both sides run OSPF on, expect a FULL adjacency."""
    assertions = []
    areas = ospf.get("areas", {})
    links = cfg.get("direct_links", {})

    # Build flat set of all subnets this device runs OSPF on
    my_subnets: set[str] = {s for subnets in areas.values() for s in subnets}

    for peer, link in links.items():
        subnet = link.get("subnet", "")
        if subnet not in my_subnets:
            continue  # This link is not in any OSPF area for this device

        # Verify the peer also runs OSPF on this subnet
        peer_cfg = all_routers.get(peer, {})
        peer_ospf = peer_cfg.get("igp", {}).get("ospf", {})
        peer_subnets: set[str] = {
            s for subnets in peer_ospf.get("areas", {}).values() for s in subnets
        }
        if subnet not in peer_subnets:
            continue  # Peer doesn't run OSPF on this subnet — no adjacency expected

        # Find which area this link belongs to on our side
        area_id = next(
            (aid for aid, subnets in areas.items() if subnet in subnets),
            "unknown",
        )

        intf = link.get("local_interface", "")
        assertions.append(Assertion(
            type=AssertionType.OSPF_NEIGHBOR,
            device=device,
            description=f"{device} should have OSPF FULL neighbor {peer} on {intf} (area {area_id})",
            expected="FULL",
            protocol="ospf",
            peer=peer,
            interface=intf,
            area=area_id,
            neighbor_ip=link.get("remote_ip", ""),
        ))
    return assertions


def _derive_ospf_router_id(device: str, ospf: dict) -> list[Assertion]:
    """Emit a router-id assertion only if INTENT.json explicitly declares one."""
    rid = ospf.get("router_id")
    if not rid:
        return []
    return [Assertion(
        type=AssertionType.OSPF_ROUTER_ID,
        device=device,
        description=f"{device} OSPF router-id should be {rid}",
        expected=rid,
        protocol="ospf",
    )]


def _derive_ospf_area_types(device: str, cfg: dict, ospf: dict) -> list[Assertion]:
    """Emit area type assertions for non-backbone areas."""
    assertions = []

    # Multi-area routers (ABRs): use "area_types" dict
    area_types = ospf.get("area_types", {})
    for area_id, area_type in area_types.items():
        if area_id == "0":
            continue  # backbone is always "normal", no need to assert
        assertions.append(Assertion(
            type=AssertionType.OSPF_AREA_TYPE,
            device=device,
            description=f"{device} OSPF area {area_id} should be {area_type}",
            expected=area_type,
            protocol="ospf",
            area=area_id,
        ))

    # Single-area routers (leaves): use "area_type" (singular) + infer area from "areas" keys
    area_type = ospf.get("area_type")
    if area_type and not area_types:
        areas = ospf.get("areas", {})
        for area_id in areas:
            if area_id == "0":
                continue
            assertions.append(Assertion(
                type=AssertionType.OSPF_AREA_TYPE,
                device=device,
                description=f"{device} OSPF area {area_id} should be {area_type}",
                expected=area_type,
                protocol="ospf",
                area=area_id,
            ))

    return assertions


def _derive_ospf_default_originate(device: str, ospf: dict) -> list[Assertion]:
    """Emit a default-originate assertion if INTENT declares it enabled."""
    do = ospf.get("default_originate", {})
    if not do.get("enabled"):
        return []
    return [Assertion(
        type=AssertionType.OSPF_DEFAULT_ORIG,
        device=device,
        description=f"{device} should originate OSPF default route",
        expected=True,
        protocol="ospf",
    )]


# ─── EIGRP assertions ────────────────────────────────────────────────────────

def _derive_eigrp(device: str, cfg: dict, all_routers: dict) -> list[Assertion]:
    """For each link that both sides list in their EIGRP networks, expect an active neighbor."""
    assertions = []
    eigrp = cfg.get("igp", {}).get("eigrp", {})
    if not eigrp:
        return assertions

    my_networks: set[str] = set(eigrp.get("networks", []))
    links = cfg.get("direct_links", {})

    for peer, link in links.items():
        subnet = link.get("subnet", "")
        if subnet not in my_networks:
            continue

        peer_cfg = all_routers.get(peer, {})
        peer_eigrp = peer_cfg.get("igp", {}).get("eigrp", {})
        peer_networks: set[str] = set(peer_eigrp.get("networks", []))
        if subnet not in peer_networks:
            continue

        intf = link.get("local_interface", "")
        assertions.append(Assertion(
            type=AssertionType.EIGRP_NEIGHBOR,
            device=device,
            description=f"{device} should have EIGRP neighbor {peer} on {intf} (AS {eigrp.get('as_number', '?')})",
            expected="up",
            protocol="eigrp",
            peer=peer,
            interface=intf,
            neighbor_ip=link.get("remote_ip", ""),
        ))
    return assertions


# ─── BGP assertions ──────────────────────────────────────────────────────────

def _derive_bgp(device: str, cfg: dict) -> list[Assertion]:
    """Each entry in bgp.neighbors should have an Established session."""
    assertions = []
    bgp = cfg.get("bgp", {})
    for label, peer_cfg in bgp.get("neighbors", {}).items():
        peer_ip = peer_cfg.get("peer", "")
        peer_as = peer_cfg.get("as", "")
        if not peer_ip:
            continue
        assertions.append(Assertion(
            type=AssertionType.BGP_SESSION,
            device=device,
            description=f"{device} BGP session with {label} ({peer_ip}) AS {peer_as} should be Established",
            expected="Established",
            protocol="bgp",
            peer=label,
            neighbor_ip=peer_ip,
        ))
    return assertions
