"""Data definitions for validation assertions and results."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssertionType(Enum):
    INTERFACE_UP       = "interface_up"
    OSPF_NEIGHBOR      = "ospf_neighbor"
    OSPF_ROUTER_ID     = "ospf_router_id"
    OSPF_AREA_TYPE     = "ospf_area_type"
    OSPF_DEFAULT_ORIG  = "ospf_default_originate"
    BGP_SESSION        = "bgp_session"
    EIGRP_NEIGHBOR     = "eigrp_neighbor"


class AssertionResult(Enum):
    PASS  = "pass"
    FAIL  = "fail"
    ERROR = "error"  # could not collect state (device unreachable, transport failure)


@dataclass
class Assertion:
    """A single thing that must be true if the network matches its design intent."""
    type:         AssertionType
    device:       str
    description:  str           # human-readable, e.g. "C1C GigabitEthernet2 should be up/up"
    expected:     Any           # the intended value derived from network intent
    protocol:     str = ""      # "interface", "ospf", "bgp"
    peer:         str = ""      # peer device name (for neighbor/session assertions)
    interface:    str = ""      # local interface name
    area:         str = ""      # OSPF area ID
    neighbor_ip:  str = ""      # peer IP (for BGP match)


@dataclass
class EvaluatedAssertion:
    """An assertion after comparing against live device state."""
    assertion: Assertion
    result:    AssertionResult
    actual:    Any = None       # actual value from device (None if ERROR)
    detail:    str = ""         # explanation of mismatch or error


@dataclass
class DeviceState:
    """Collected operational state from a single device."""
    interfaces:     dict | None = None   # {intf_name: "up/up"}
    ospf_neighbors: list | None = None   # [{"state": "FULL", "interface": "Gi2"}]
    ospf_details:   dict | None = None   # {"router_id": "...", "areas": {...}, "default_originate": bool}
    bgp_summary:    list | None = None   # [{"neighbor_ip": "...", "state": "Established", "as": N}]
    eigrp_neighbors: list | None = None  # [{"neighbor_ip": "...", "interface": "..."}]
    errors:         list = field(default_factory=list)
