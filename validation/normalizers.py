"""Translate device tool output into standard dicts the evaluator can compare.

Each normalizer dispatches on result["cli_style"] to a vendor-specific parser.
Every parser converts vendor CLI output into the same normalized structure.
"""
import re
import socket


# ─── Interfaces ──────────────────────────────────────────────────────────────

def normalize_interfaces(result: dict) -> dict[str, str]:
    """Return {interface_name: "up/up" | "up/down" | "down/down"}."""
    raw = result.get("raw", "")
    cli_style = result.get("cli_style", "ios")
    parser = _INTERFACE_PARSERS.get(cli_style, _interfaces_ios)
    return parser(raw) if isinstance(raw, str) else {}


def _interfaces_ios(raw: str) -> dict[str, str]:
    """Parse 'show ip interface brief' (IOS/IOS-XE).

    Example line:
    GigabitEthernet2    10.1.1.6    YES NVRAM up    up
    Last two columns are status and protocol.
    """
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0][0].isalpha():
            out[parts[0]] = f"{parts[-2].lower()}/{parts[-1].lower()}"
    return out


def _interfaces_eos(raw: str) -> dict[str, str]:
    """Parse 'show ip interface brief' (Arista EOS).

    Columns: Interface IP-Address Status Protocol MTU [Owner]
    Status is col 2, Protocol is col 3.
    """
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0][0].isalpha() and parts[0] != "Interface":
            out[parts[0]] = f"{parts[2].lower()}/{parts[3].lower()}"
    return out


def _interfaces_junos(raw: str) -> dict[str, str]:
    """Parse 'show interfaces terse' (Juniper JunOS).

    Columns: Interface Admin Link Proto Local Remote
    Skip sub-interfaces (name contains '.').
    Skip continuation lines by requiring Admin in {"up", "down"}.
    """
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3 and "." not in parts[0] and parts[1] in ("up", "down"):
            out[parts[0]] = f"{parts[1].lower()}/{parts[2].lower()}"
    return out


def _interfaces_aos(raw: str) -> dict[str, str]:
    """Parse 'show interface brief' (Aruba AOS-CX).

    Columns: Port NativeVLAN Mode Type Enabled Status
    Port names start with a digit (e.g. 1/1/2).
    """
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0][0].isdigit():
            enabled = parts[4].lower()
            status = parts[5].lower()
            if enabled == "no":
                out[parts[0]] = "down/down"
            elif status == "up":
                out[parts[0]] = "up/up"
            else:
                out[parts[0]] = "up/down"
    return out


def _interfaces_routeros(raw: str) -> dict[str, str]:
    """Parse '/interface print brief without-paging' (MikroTik RouterOS).

    Lines start with a numeric index. Flags follow: R=running, X=disabled.
    Interface name is the first lowercase token after the index.
    """
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        flags: set[str] = set()
        name = None
        for p in parts[1:]:
            if p and all(c.isupper() for c in p):
                flags.update(p)
            elif p and (p[0].islower() or p[0].isdigit()):
                name = p
                break
        if not name:
            continue
        if "X" in flags:
            out[name] = "down/down"
        elif "R" in flags:
            out[name] = "up/up"
        else:
            out[name] = "up/down"
    return out


def _interfaces_vyos(raw: str) -> dict[str, str]:
    """Parse 'show interfaces' (VyOS/FRR).

    Columns: Interface IPAddress S/L Description
    S/L column contains two single-char codes: u=up, D=down, A=admin-down.
    """
    _sl_map = {"u": "up", "d": "down", "a": "down"}
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0][0].isalpha():
            continue
        for p in parts[1:]:
            m = re.match(r'^([uUdDaA])/([uUdDaA])$', p)
            if m:
                status = _sl_map.get(m.group(1).lower(), "down")
                proto = _sl_map.get(m.group(2).lower(), "down")
                out[parts[0]] = f"{status}/{proto}"
                break
    return out


_INTERFACE_PARSERS: dict = {
    "ios":      _interfaces_ios,
    "eos":      _interfaces_eos,
    "junos":    _interfaces_junos,
    "aos":      _interfaces_aos,
    "routeros": _interfaces_routeros,
    "vyos":     _interfaces_vyos,
}


# ─── OSPF neighbors ──────────────────────────────────────────────────────────

def normalize_ospf_neighbors(result: dict) -> list[dict]:
    """Return [{"neighbor_id": str, "state": str, "interface": str, "area": str}]."""
    raw = result.get("raw", "")
    cli_style = result.get("cli_style", "ios")
    parser = _OSPF_NEIGHBOR_PARSERS.get(cli_style, _ospf_neighbors_ios)
    return parser(raw) if isinstance(raw, str) else []


def _ospf_neighbors_ios(raw: str) -> list[dict]:
    """Parse 'show ip ospf neighbor' (IOS/IOS-XE).

    Columns: NeighborID Pri State DeadTime Address Interface
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


def _ospf_neighbors_eos(raw: str) -> list[dict]:
    """Parse 'show ip ospf neighbor' (Arista EOS).

    Columns: NeighborID [VRF] Pri State DeadTime Address Interface
    Extra VRF column shifts State to index 3; Interface is always last.
    """
    neighbors = []
    ospf_states = {"full", "2way", "init", "down", "exstart", "exchange", "loading", "attempt"}
    for line in raw.splitlines():
        parts = line.split()
        if not parts or not _looks_like_ip(parts[0]):
            continue
        state_raw = ""
        for p in parts[1:]:
            if any(s in p.lower() for s in ospf_states):
                state_raw = p
                break
        if not state_raw:
            continue
        neighbors.append({
            "neighbor_id": parts[0],
            "state": _normalize_ospf_state(state_raw),
            "interface": parts[-1],
            "area": "",
        })
    return neighbors


def _ospf_neighbors_junos(raw: str) -> list[dict]:
    """Parse 'show ospf neighbor' (Juniper JunOS).

    Columns: Address Interface State ID Pri Dead
    Strip unit suffix (.0) from interface name.
    """
    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 4 and _looks_like_ip(parts[0]):
            intf = parts[1].rsplit(".", 1)[0] if "." in parts[1] else parts[1]
            neighbors.append({
                "neighbor_id": parts[3],
                "state": _normalize_ospf_state(parts[2]),
                "interface": intf,
                "area": "",
            })
    return neighbors


def _ospf_neighbors_aos(raw: str) -> list[dict]:
    """Parse 'show ip ospf neighbors' (Aruba AOS-CX).

    Columns: NeighborID Pri State NbrAddress Interface (5 cols — no DeadTime).
    Interface is always the last column.
    """
    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 5 and _looks_like_ip(parts[0]):
            neighbors.append({
                "neighbor_id": parts[0],
                "state": _normalize_ospf_state(parts[2]),
                "interface": parts[-1],
                "area": "",
            })
    return neighbors


def _ospf_neighbors_routeros(raw: str) -> list[dict]:
    """Parse '/routing ospf neighbor print terse without-paging' (MikroTik RouterOS).

    Key=value format. Each entry starts with a numeric index.
    Extract: router-id=, state=, interface=
    """
    neighbors = []
    current: dict = {}

    def _flush() -> None:
        rid = current.get("router-id", "")
        state = current.get("state", "")
        intf = current.get("interface", "")
        addr = current.get("address", "")
        if rid and state:
            neighbors.append({
                "neighbor_id": rid,
                "state": _normalize_ospf_state(state),
                "interface": intf,
                "address": addr,
                "area": "",
            })

    for line in raw.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0].isdigit():
            _flush()
            current = {}
        for p in parts:
            if "=" in p:
                k, _, v = p.partition("=")
                current[k] = v.strip('"')

    _flush()
    return neighbors


def _ospf_neighbors_vyos(raw: str) -> list[dict]:
    """Parse 'show ip ospf neighbor' (VyOS/FRR).

    Non-VRF: NeighborID Pri State DeadTime Address Interface (6 cols)
    VRF:     NeighborID Pri State UpTime DeadTime Address Interface RXmtL RqstL DBsmL (10 cols)

    Interface column includes ':localIP' suffix (e.g. eth1:10.0.0.41) — strip it.
    Scan for the interface rather than using a fixed index to handle both column layouts.
    """
    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 6 and _looks_like_ip(parts[0]):
            # Interface token has ':' with an alpha prefix; skip neighbor_id/pri/state
            intf = ""
            for p in parts[3:]:
                if ":" in p and p[0].isalpha():
                    intf = p.split(":")[0]
                    break
            neighbors.append({
                "neighbor_id": parts[0],
                "state": _normalize_ospf_state(parts[2]),
                "interface": intf,
                "area": "",
            })
    return neighbors


_OSPF_NEIGHBOR_PARSERS: dict = {
    "ios":      _ospf_neighbors_ios,
    "eos":      _ospf_neighbors_eos,
    "junos":    _ospf_neighbors_junos,
    "aos":      _ospf_neighbors_aos,
    "routeros": _ospf_neighbors_routeros,
    "vyos":     _ospf_neighbors_vyos,
}


# ─── OSPF details (router-id, area types, default-originate) ─────────────────

def normalize_ospf_details(result: dict, config_raw: str = "") -> dict:
    """Return {"router_id": str, "areas": {"0": "normal", "1": "stub"}, "default_originate": bool}.

    config_raw: raw text from the OSPF config command, used to detect
    default-information originate on vendors that don't show it in show ip ospf.
    """
    raw = result.get("raw", "")
    cli_style = result.get("cli_style", "ios")
    parser = _OSPF_DETAIL_PARSERS.get(cli_style, _ospf_details_ios)
    return parser(raw, config_raw) if isinstance(raw, str) else {}


def _ospf_details_ios(raw: str, config_raw: str) -> dict:
    """Parse 'show ip ospf' + 'show run | section ospf' (IOS/IOS-XE)."""
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    rid_match = re.search(r"(?:Router\s+ID|with\s+ID)\s+(\d+\.\d+\.\d+\.\d+)", raw)
    if rid_match:
        out["router_id"] = rid_match.group(1)

    for m in re.finditer(r"Area\s+(\S+).*?\((stub|nssa)", raw, re.IGNORECASE):
        area_id = _area_id_to_int(m.group(1).strip(","))
        out["areas"][area_id] = m.group(2).lower()

    # Multi-line format: "Area <id>" on one line, "It is a stub area" on a later line
    if not out["areas"]:
        current_area = None
        for line in raw.splitlines():
            m = re.match(r"\s*Area\s+(\S+)", line, re.IGNORECASE)
            if m:
                current_area = _area_id_to_int(m.group(1).strip(","))
            if current_area:
                m2 = re.search(r"it\s+is\s+a\s+(stub|nssa)", line, re.IGNORECASE)
                if m2:
                    out["areas"][current_area] = m2.group(1).lower()
                    current_area = None

    # Final fallback: parse area types from running config
    if not out["areas"] and config_raw:
        for m in re.finditer(r"^\s*area\s+(\S+)\s+(stub|nssa)", config_raw, re.IGNORECASE | re.MULTILINE):
            area_id = _area_id_to_int(m.group(1))
            out["areas"][area_id] = m.group(2).lower()

    supplement = config_raw or raw
    if "default-information originate" in supplement.lower():
        out["default_originate"] = True

    return out


def _ospf_details_eos(raw: str, config_raw: str) -> dict:
    """Parse 'show ip ospf' + 'show run section ospf' (Arista EOS).

    Router ID appears as 'with ID x.x.x.x' or 'Router-ID: x.x.x.x'.
    Area types: 'is STUB' / 'is NSSA' or '(Stub)' / '(NSSA)' in parens.
    """
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    rid_match = re.search(
        r"(?:with\s+ID|Router.?ID)[:\s]+(\d+\.\d+\.\d+\.\d+)", raw, re.IGNORECASE
    )
    if rid_match:
        out["router_id"] = rid_match.group(1)

    for m in re.finditer(r"Area\s+(\S+)[^\n]*?(stub|nssa)", raw, re.IGNORECASE):
        area_id = _area_id_to_int(m.group(1).strip(",()\n"))
        out["areas"][area_id] = m.group(2).lower()

    supplement = config_raw or raw
    if "default-information originate" in supplement.lower():
        out["default_originate"] = True

    return out


def _ospf_details_junos(raw: str, config_raw: str) -> dict:
    """Parse 'show ospf overview' + 'show configuration protocols ospf' (Juniper JunOS).

    Router ID: 'Router ID: x.x.x.x'
    Area blocks: 'Area: x.x.x.x' followed by 'Stub type: Stub|NSSA'
    Default originate: 'generate-default' or 'default-information' in config.
    """
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    rid_match = re.search(r"Router\s+ID:\s+(\d+\.\d+\.\d+\.\d+)", raw)
    if rid_match:
        out["router_id"] = rid_match.group(1)

    current_area: str | None = None
    for line in raw.splitlines():
        area_m = re.match(r"\s+Area:\s+(\S+)", line)
        if area_m:
            current_area = _area_id_to_int(area_m.group(1))
            out["areas"].setdefault(current_area, "normal")
        stub_m = re.match(r"\s+Stub\s+type:\s+(\S+)", line, re.IGNORECASE)
        if stub_m and current_area:
            t = stub_m.group(1).lower()
            if "nssa" in t:
                out["areas"][current_area] = "nssa"
            elif "stub" in t:
                out["areas"][current_area] = "stub"

    supplement = config_raw or ""
    if "generate-default" in supplement.lower() or "default-information" in supplement.lower():
        out["default_originate"] = True

    return out


def _ospf_details_aos(raw: str, config_raw: str) -> dict:
    """Parse 'show ip ospf' + 'show running-config' (Aruba AOS-CX).

    Router ID: 'Router ID: x.x.x.x' or 'router-id x.x.x.x'
    Area types: 'Area (0.0.0.1)' with 'Area type: Stub' or '(Stub)'/'(NSSA)' nearby.
    """
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    rid_match = re.search(r"Router.?ID[:\s]+(\d+\.\d+\.\d+\.\d+)", raw, re.IGNORECASE)
    if rid_match:
        out["router_id"] = rid_match.group(1)

    for m in re.finditer(r"Area\s+(?::\s*)?(\d[\d.]*)[^\n]*?(stub|nssa)", raw, re.IGNORECASE):
        area_id = _area_id_to_int(m.group(1).strip("(),\n"))
        out["areas"][area_id] = m.group(2).lower()

    # Multi-line format: "Area  : <id>" on one line, "Area Type : Stub" on a later line
    if not out["areas"]:
        current_area = None
        for line in raw.splitlines():
            m = re.match(r"\s*Area\s+(?::\s*)?(\d[\d.]+)", line, re.IGNORECASE)
            if m:
                current_area = _area_id_to_int(m.group(1).strip("(),\n"))
            if current_area:
                m2 = re.search(r"area\s+type\s*:\s*(stub|nssa)", line, re.IGNORECASE)
                if m2:
                    out["areas"][current_area] = m2.group(1).lower()
                    current_area = None

    # Final fallback: parse area types from running config
    if not out["areas"] and config_raw:
        for m in re.finditer(r"^\s*area\s+(\S+)\s+(stub|nssa)", config_raw, re.IGNORECASE | re.MULTILINE):
            area_id = _area_id_to_int(m.group(1).strip("(),"))
            out["areas"][area_id] = m.group(2).lower()

    supplement = config_raw or raw
    if "default-information originate" in supplement.lower():
        out["default_originate"] = True

    return out


def _ospf_details_routeros(raw: str, config_raw: str) -> dict:
    """Parse '/routing ospf instance print detail' + '/routing ospf area print detail' (MikroTik RouterOS).

    Key=value format:
      Instance: router-id=, distribute-default=never|always|if-installed-*
      Area:     area-id=0.0.0.1 type=stub|nssa|default (from config_raw)
    """
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    for line in raw.splitlines():
        for part in line.split():
            if "=" in part:
                k, _, v = part.partition("=")
                v = v.strip('"')
                if k == "router-id":
                    out["router_id"] = v
                elif k == "distribute-default" and v != "never":
                    out["default_originate"] = True

    # Parse area types from config_raw (/routing ospf area print detail)
    if config_raw:
        current_area_id: str | None = None
        for part in config_raw.split():
            if "=" in part:
                k, _, v = part.partition("=")
                v = v.strip('"')
                if k == "area-id":
                    current_area_id = _area_id_to_int(v)
                elif k == "type" and current_area_id is not None:
                    if v == "stub":
                        out["areas"][current_area_id] = "stub"
                    elif v == "nssa":
                        out["areas"][current_area_id] = "nssa"

    return out


def _ospf_details_vyos(raw: str, config_raw: str) -> dict:
    """Parse 'show ip ospf' + 'show configuration commands | match ospf' (VyOS/FRR).

    Router ID: 'Router ID: x.x.x.x' or 'OSPF Routing Process ... Router-ID: ...'
    Area types: 'Area ID: x.x.x.x [Stub]' / '[NSSA]' in brackets.
    Default originate: 'default-information originate' in config.
    """
    out: dict = {"router_id": "", "areas": {}, "default_originate": False}

    rid_match = re.search(r"Router.?ID[:\s]+(\d+\.\d+\.\d+\.\d+)", raw, re.IGNORECASE)
    if rid_match:
        out["router_id"] = rid_match.group(1)

    for m in re.finditer(r"Area.?ID[:\s]+(\S+)[^\n]*?[\[(](Stub|NSSA)", raw, re.IGNORECASE):
        area_id = _area_id_to_int(m.group(1).strip(","))
        out["areas"][area_id] = m.group(2).lower()

    supplement = config_raw or raw
    if "default-information originate" in supplement.lower():
        out["default_originate"] = True

    return out


_OSPF_DETAIL_PARSERS: dict = {
    "ios":      _ospf_details_ios,
    "eos":      _ospf_details_eos,
    "junos":    _ospf_details_junos,
    "aos":      _ospf_details_aos,
    "routeros": _ospf_details_routeros,
    "vyos":     _ospf_details_vyos,
}


# ─── BGP summary ─────────────────────────────────────────────────────────────

def normalize_bgp_summary(result: dict) -> list[dict]:
    """Return [{"neighbor_ip": str, "state": str, "as": int}]."""
    raw = result.get("raw", "")
    cli_style = result.get("cli_style", "ios")
    parser = _BGP_SUMMARY_PARSERS.get(cli_style, _bgp_summary_ios)
    return parser(raw) if isinstance(raw, str) else []


def _bgp_summary_ios(raw: str) -> list[dict]:
    """Parse 'show ip bgp summary' (IOS/IOS-XE).

    Columns: Neighbor V AS ... State/PfxRcd
    Numeric last column means Established (prefix count).
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
            neighbors.append({"neighbor_ip": parts[0], "state": state, "as": peer_as})
    return neighbors


def _bgp_summary_eos(raw: str) -> list[dict]:
    """Parse 'show ip bgp summary' (Arista EOS).

    May include a Description column before Neighbor. 'Estab' abbreviation.
    Find V=4 to locate AS. Last column: digit=PfxAcc (Established), else State.
    """
    neighbors = []
    in_table = False
    for line in raw.splitlines():
        stripped = line.strip()
        if "Neighbor" in stripped and "State" in stripped:
            in_table = True
            continue
        if not in_table:
            continue
        parts = stripped.split()
        # Find neighbor IP in first two parts
        nbr_ip = None
        for p in parts[:2]:
            if _looks_like_ip(p):
                nbr_ip = p
                break
        if not nbr_ip:
            continue
        # AS is the value after BGP version "4"
        peer_as = 0
        for i, p in enumerate(parts):
            if p == "4" and i + 1 < len(parts) and parts[i + 1].isdigit():
                peer_as = int(parts[i + 1])
                break
        last_col = parts[-1]
        if last_col.isdigit() or last_col.lower() in ("estab", "established"):
            state = "Established"
        else:
            state = _normalize_bgp_state(last_col)
        neighbors.append({"neighbor_ip": nbr_ip, "state": state, "as": peer_as})
    return neighbors


def _bgp_summary_junos(raw: str) -> list[dict]:
    """Parse 'show bgp summary' (Juniper JunOS).

    Columns: Peer AS InPkt OutPkt OutQ Flaps LastUp State
    'Establ' abbreviation. N/N/N/N counter format also means Established.
    """
    neighbors = []
    in_table = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("Peer") and "AS" in stripped:
            in_table = True
            continue
        if not in_table:
            continue
        parts = stripped.split()
        if len(parts) >= 7 and _looks_like_ip(parts[0]):
            peer_as = int(parts[1]) if parts[1].isdigit() else 0
            last_col = parts[-1]
            if re.match(r'^\d+/\d+/\d+/\d+$', last_col) or last_col.lower() in ("establ", "established"):
                state = "Established"
            else:
                state = _normalize_bgp_state(last_col)
            neighbors.append({"neighbor_ip": parts[0], "state": state, "as": peer_as})
    return neighbors


def _bgp_summary_aos(raw: str) -> list[dict]:
    """Parse 'show bgp ipv4 unicast summary' (Aruba AOS-CX).

    Columns: Neighbor RemoteAS State Up-Time ...
    State is fully spelled out.
    """
    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3 and _looks_like_ip(parts[0]) and parts[1].isdigit():
            neighbors.append({
                "neighbor_ip": parts[0],
                "state": _normalize_bgp_state(parts[2]),
                "as": int(parts[1]),
            })
    return neighbors


def _bgp_summary_routeros(raw: str) -> list[dict]:
    """Parse '/routing bgp session print without-paging' (MikroTik RouterOS).

    Lines start with numeric index. E flag = established.
    Columns after index [flags]: REMOTE-AS REMOTE-ADDRESS ...
    """
    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        # Detect optional flags column (uppercase letters only)
        if len(parts) > 1 and parts[1] and all(c.isupper() for c in parts[1]):
            flags_str = parts[1]
            data = parts[2:]
        else:
            flags_str = ""
            data = parts[1:]
        if len(data) < 2:
            continue
        peer_as_str, nbr_ip = data[0], data[1]
        if not _looks_like_ip(nbr_ip) or not peer_as_str.isdigit():
            continue
        if "E" in flags_str:
            state = "Established"
        else:
            state = _normalize_bgp_state(data[-1]) if data else "Unknown"
        neighbors.append({"neighbor_ip": nbr_ip, "state": state, "as": int(peer_as_str)})
    return neighbors


def _bgp_summary_vyos(raw: str) -> list[dict]:
    """Parse 'show ip bgp summary' (VyOS/FRR).

    Nearly identical to IOS. Extra PfxSnt column when established — last column
    is still a digit when established, so IOS parser logic applies directly.
    """
    return _bgp_summary_ios(raw)


_BGP_SUMMARY_PARSERS: dict = {
    "ios":      _bgp_summary_ios,
    "eos":      _bgp_summary_eos,
    "junos":    _bgp_summary_junos,
    "aos":      _bgp_summary_aos,
    "routeros": _bgp_summary_routeros,
    "vyos":     _bgp_summary_vyos,
}


# ─── EIGRP neighbors ─────────────────────────────────────────────────────────

def normalize_eigrp_neighbors(result: dict) -> list[dict]:
    """Return [{"neighbor_ip": str, "interface": str}]."""
    raw = result.get("raw", "")
    cli_style = result.get("cli_style", "ios")
    parser = _EIGRP_NEIGHBOR_PARSERS.get(cli_style, _eigrp_neighbors_ios)
    return parser(raw) if isinstance(raw, str) else []


def _eigrp_neighbors_ios(raw: str) -> list[dict]:
    """Parse 'show ip eigrp neighbors' (IOS/IOS-XE).

    Example:
    EIGRP-IPv4 Neighbors for AS(10)
    H   Address         Interface        Hold Uptime   SRTT   RTO  Q  Seq
                                         (sec)         (ms)       Cnt Num
    0   10.10.10.1      Et0/1              13 00:05:32    3   100  0  3

    Each data line starts with a numeric handle (H column).
    """
    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit() and _looks_like_ip(parts[1]):
            neighbors.append({
                "neighbor_ip": parts[1],
                "interface":   parts[2],
            })
    return neighbors


_EIGRP_NEIGHBOR_PARSERS: dict = {
    "ios": _eigrp_neighbors_ios,
}


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _normalize_ospf_state(raw_state: str) -> str:
    """Normalize OSPF neighbor state to a canonical uppercase string.

    Strips the DR role suffix (FULL/DR → FULL) and handles vendor variations.
    """
    s = raw_state.upper().split("/")[0].strip()
    if s in ("FULL", "2WAY", "INIT", "DOWN", "EXSTART", "EXCHANGE", "LOADING"):
        return s
    if "FULL" in s:
        return "FULL"
    if "2WAY" in s or "TWO" in s:
        return "2WAY"
    if "INIT" in s:
        return "INIT"
    if "DOWN" in s:
        return "DOWN"
    return s


def _normalize_bgp_state(raw_state: str) -> str:
    """Normalize BGP session state to a canonical string."""
    s = raw_state.strip()
    if s.isdigit():
        return "Established"
    sl = s.lower()
    if "established" in sl or sl == "estab" or sl == "establ":
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


def _area_id_to_int(area_id: str) -> str:
    """Convert dotted-decimal OSPF area ID to integer string.

    Intent uses integer strings (e.g. "1"); some vendors return dotted-decimal
    (e.g. "0.0.0.1"). Convert so lookups match.
    """
    if "." in str(area_id):
        try:
            packed = socket.inet_aton(str(area_id))
            return str(int.from_bytes(packed, "big"))
        except OSError:
            pass
    return str(area_id)


def _looks_like_ip(s: str) -> bool:
    """Quick check: does this string look like an IPv4 address?"""
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)
