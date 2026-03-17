"""Translate device tool output into standard dicts the evaluator can compare.

Each normalizer function takes the result dict returned by a tool function
(which contains 'raw', optionally 'parsed', 'cli_style', etc.) and returns
a clean, vendor-neutral structure.

For SSH devices, the 'parsed' field (Genie-parsed dict) is the primary source.
Raw text fallback parsers handle cases where Genie parsing fails.
"""
import re
import socket


# ─── Interfaces ──────────────────────────────────────────────────────────────

def normalize_interfaces(result: dict) -> dict[str, str]:
    """Return {interface_name: "up/up" | "up/down" | "down/down" | ...}."""
    parsed = result.get("parsed")
    if parsed:
        return _interfaces_from_genie(parsed)
    raw = result.get("raw", "")
    if isinstance(raw, str):
        return _interfaces_from_raw(raw)
    return {}


def _interfaces_from_genie(parsed: dict) -> dict[str, str]:
    """Genie parses 'show ip interface brief' into:
    {"interface": {"GigabitEthernet2": {"ip_address": "...", "status": "up", "protocol": "up"}}}
    """
    out = {}
    for intf_name, intf_data in parsed.get("interface", {}).items():
        status = intf_data.get("status", "unknown").lower()
        protocol = intf_data.get("protocol", "unknown").lower()
        out[intf_name] = f"{status}/{protocol}"
    return out


def _interfaces_from_raw(raw: str) -> dict[str, str]:
    """Fallback: parse 'show ip interface brief' text output.

    Example line:
    GigabitEthernet2    10.1.1.6    YES NVRAM up    up
    """
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0][0].isalpha():
            # Last two columns are status and protocol
            out[parts[0]] = f"{parts[-2].lower()}/{parts[-1].lower()}"
    return out


# ─── OSPF neighbors ──────────────────────────────────────────────────────────

def normalize_ospf_neighbors(result: dict) -> list[dict]:
    """Return [{"state": "FULL", "interface": "GigabitEthernet2", "area": "0"}]."""
    parsed = result.get("parsed")
    if parsed:
        return _ospf_neighbors_from_genie(parsed)
    raw = result.get("raw", "")
    if isinstance(raw, str):
        return _ospf_neighbors_from_raw(raw)
    return []


def _ospf_neighbors_from_genie(parsed: dict) -> list[dict]:
    """Genie parses 'show ip ospf neighbor' into:
    {"interfaces": {"GigabitEthernet2": {"neighbors": {"10.1.1.5": {"state": "FULL/DR", ...}}}}}
    """
    neighbors = []
    for intf_name, intf_data in parsed.get("interfaces", {}).items():
        for nbr_id, nbr_data in intf_data.get("neighbors", {}).items():
            raw_state = nbr_data.get("state", "")
            neighbors.append({
                "neighbor_id": nbr_id,
                "state": _normalize_ospf_state(raw_state),
                "interface": intf_name,
                "area": str(nbr_data.get("area", "")),
            })
    return neighbors


def _ospf_neighbors_from_raw(raw: str) -> list[dict]:
    """Fallback: parse 'show ip ospf neighbor' text output.

    Example line:
    10.1.1.5    1   FULL/DR    00:00:32  10.1.1.5  GigabitEthernet2
    """
    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 6 and _looks_like_ip(parts[0]):
            neighbors.append({
                "neighbor_id": parts[0],
                "state": _normalize_ospf_state(parts[2]),
                "interface": parts[5],
                "area": "",
            })
    return neighbors


def _normalize_ospf_state(raw_state: str) -> str:
    """Normalize OSPF neighbor state to a canonical string.

    Genie uses "FULL/DR", "FULL/BDR", "FULL/ -", "2WAY/DROTHER", etc.
    We strip the DR role suffix and normalize to uppercase.
    """
    s = raw_state.upper().split("/")[0].strip()
    # Map common variations
    if s in ("FULL", "2WAY", "INIT", "DOWN", "EXSTART", "EXCHANGE", "LOADING"):
        return s
    # Partial matches
    if "FULL" in s:
        return "FULL"
    if "2WAY" in s or "TWO" in s:
        return "2WAY"
    if "INIT" in s:
        return "INIT"
    if "DOWN" in s:
        return "DOWN"
    return s


# ─── OSPF details (router-id, area types, default-originate) ─────────────────

def normalize_ospf_details(result: dict, config_raw: str = "") -> dict:
    """Return {"router_id": "...", "areas": {"0": "normal", "1": "stub"}, "default_originate": bool}.

    config_raw: optional raw text from 'show run | section ospf', used to detect
    default-information originate which is not present in 'show ip ospf' output.
    """
    parsed = result.get("parsed")
    raw = result.get("raw", "")
    if parsed:
        out = _ospf_details_from_genie(parsed)
        # 'show ip ospf' doesn't include default-information originate.
        # Check the config raw text if provided, else fall back to the details raw text.
        supplement = config_raw or (raw if isinstance(raw, str) else "")
        if not out["default_originate"] and "default-information originate" in supplement.lower():
            out["default_originate"] = True
        return out
    if isinstance(raw, str):
        return _ospf_details_from_raw(raw)
    return {}


def _area_id_to_int(area_id: str) -> str:
    """Convert dotted-decimal OSPF area ID to integer string.

    Genie returns area IDs in dotted-decimal (e.g. "0.0.0.1"), but INTENT.json
    uses integer strings (e.g. "1"). Convert so lookups match.
    """
    if "." in str(area_id):
        try:
            packed = socket.inet_aton(str(area_id))
            return str(int.from_bytes(packed, "big"))
        except OSError:
            pass
    return str(area_id)


def _ospf_details_from_genie(parsed: dict) -> dict:
    """Genie parses 'show ip ospf' into a nested dict with vrf/instance structure."""
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    # Genie structure: {"vrf": {"default": {"address_family": {"ipv4": {"instance": {"1": {...}}}}}}}
    for vrf_data in parsed.get("vrf", {}).values():
        for af_data in vrf_data.get("address_family", {}).values():
            for instance_data in af_data.get("instance", {}).values():
                if not out["router_id"]:
                    out["router_id"] = instance_data.get("router_id", "")
                if instance_data.get("generate_default_route_info", {}).get("always"):
                    out["default_originate"] = True
                elif instance_data.get("default_information", {}).get("enabled"):
                    out["default_originate"] = True
                for area_id, area_data in instance_data.get("areas", {}).items():
                    area_type = area_data.get("area_type", "normal").lower()
                    # Convert dotted-decimal ("0.0.0.1") to integer string ("1")
                    out["areas"][_area_id_to_int(area_id)] = area_type
    return out


def _ospf_details_from_raw(raw: str) -> dict:
    """Fallback: parse 'show ip ospf' text output."""
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    # Router ID
    rid_match = re.search(r"Router ID\s+(\d+\.\d+\.\d+\.\d+)", raw)
    if rid_match:
        out["router_id"] = rid_match.group(1)

    # Area types
    for m in re.finditer(r"Area\s+(\S+).*?\((stub|nssa)", raw, re.IGNORECASE):
        out["areas"][m.group(1).strip(",")] = m.group(2).lower()

    # Default originate
    if "default-information originate" in raw.lower():
        out["default_originate"] = True

    return out


# ─── BGP summary ─────────────────────────────────────────────────────────────

def normalize_bgp_summary(result: dict) -> list[dict]:
    """Return [{"neighbor_ip": "...", "state": "Established", "as": 4040}]."""
    parsed = result.get("parsed")
    if parsed:
        return _bgp_summary_from_genie(parsed)
    raw = result.get("raw", "")
    if isinstance(raw, str):
        return _bgp_summary_from_raw(raw)
    return []


def _bgp_summary_from_genie(parsed: dict) -> list[dict]:
    """Genie parses 'show ip bgp summary'.

    Two cases depending on session state and config style:
    - NOT established: session_state key at neighbor level ("Idle", "Active", etc.)
    - Established: data inside address_family sub-dict; state_pfxrcd is a digit (prefix count)

    address_family key is "" (classic BGP) or "ipv4 unicast" (address-family config).
    AS may be at neighbor level (remote_as) or inside address_family (as).
    """
    neighbors = []
    for vrf_data in parsed.get("vrf", {}).values():
        for nbr_ip, nbr_data in vrf_data.get("neighbor", {}).items():
            # Session NOT established: state_state at neighbor level
            session_state = nbr_data.get("session_state", "")

            # AS: try neighbor level first
            peer_as = nbr_data.get("remote_as", 0)

            # Session established: drill into address_family for state_pfxrcd
            if not session_state:
                for af_data in nbr_data.get("address_family", {}).values():
                    pfx = str(af_data.get("state_pfxrcd", ""))
                    if pfx.isdigit():
                        session_state = "Established"
                    if not peer_as:
                        peer_as = af_data.get("as", af_data.get("remote_as", 0))
                    if session_state:
                        break

            # AS fallback: inside address_family if not found at neighbor level
            if not peer_as:
                for af_data in nbr_data.get("address_family", {}).values():
                    peer_as = af_data.get("as", af_data.get("remote_as", 0))
                    if peer_as:
                        break

            neighbors.append({
                "neighbor_ip": nbr_ip,
                "state": _normalize_bgp_state(session_state),
                "as": peer_as,
            })
    return neighbors


def _bgp_summary_from_raw(raw: str) -> list[dict]:
    """Fallback: parse 'show ip bgp summary' text output.

    Neighbor column is first, AS is second, State/PfxRcd is last.
    A numeric state means Established (shows prefix count); otherwise it's a state string.
    """
    neighbors = []
    in_table = False
    for line in raw.splitlines():
        if line.strip().startswith("Neighbor"):
            in_table = True
            continue
        if not in_table:
            continue
        parts = line.split()
        if len(parts) >= 9 and _looks_like_ip(parts[0]):
            peer_as = int(parts[2]) if parts[2].isdigit() else 0
            last_col = parts[-1]
            state = "Established" if last_col.isdigit() else _normalize_bgp_state(last_col)
            neighbors.append({
                "neighbor_ip": parts[0],
                "state": state,
                "as": peer_as,
            })
    return neighbors


def _normalize_bgp_state(raw_state: str) -> str:
    """Normalize BGP session state to a canonical string."""
    s = raw_state.strip()
    # Numeric = prefix count = Established
    if s.isdigit():
        return "Established"
    sl = s.lower()
    if "established" in sl:
        return "Established"
    if "idle" in sl:
        return "Idle"
    if "active" in sl:
        return "Active"
    if "connect" in sl:
        return "Connect"
    if "opensent" in sl:
        return "OpenSent"
    if "openconfirm" in sl:
        return "OpenConfirm"
    if "fsm-established" in sl:
        return "Established"
    return s.capitalize() if s else "Unknown"


# ─── Utility ─────────────────────────────────────────────────────────────────

def _looks_like_ip(s: str) -> bool:
    """Quick check: does this string look like an IPv4 address?"""
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)
