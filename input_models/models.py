# dblCheck - Network Intent Validation Tool
# Copyright (c) 2026 Mihai Catalin Teodosiu
# Licensed under the Business Source License 1.1

import ipaddress
import json
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# Compiled patterns for parameter validation
_VRF_RE    = re.compile(r'^[a-zA-Z0-9_-]{1,32}$')
_PREFIX_RE = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$')



class BaseParamsModel(BaseModel):
    """Base class for all MCP tool input models.

    Adds a pre-validator that handles the case where the model passes `params`
    as a JSON string instead of a dict (e.g. '{"device": "R1A"}}' with trailing
    garbage). Uses raw_decode() so any trailing characters after valid JSON are
    silently ignored.

    Also validates the optional `vrf` field (present on most subclasses) to
    prevent CLI injection via VRF name substitution in platform_map.py.
    """
    @model_validator(mode='before')
    @classmethod
    def parse_string_input(cls, v):
        if isinstance(v, str):
            try:
                obj, _ = json.JSONDecoder().raw_decode(v.strip())
                return obj
            except (json.JSONDecodeError, ValueError) as e:
                raise ValueError(f"Could not parse params as JSON: {v!r}") from e
        return v

    @field_validator('vrf', mode='before', check_fields=False)
    @classmethod
    def _validate_vrf(cls, v):
        if v is None:
            return v
        if not _VRF_RE.match(str(v)):
            raise ValueError(
                f"vrf must be alphanumeric with underscores/dashes, max 32 chars. Got: {v!r}"
            )
        return v


# OSPF query - input model
class OspfQuery(BaseParamsModel):
    device: str = Field(..., description="Device name from inventory")
    query: Literal["neighbors", "database", "borders", "config", "interfaces", "details"] = Field(
        ..., description="neighbors | database | borders | config | interfaces | details"
    )
    vrf: str | None = Field(None, description="Optional VRF name (default: global routing table)")

# BGP query - input model
class BgpQuery(BaseParamsModel):
    device: str
    query: Literal["summary", "table", "config", "neighbors"] = Field(
        ..., description="summary | table | config | neighbors"
    )
    neighbor: str | None = Field(None, description="Optional neighbor IP to filter output (neighbors query)")
    vrf: str | None = Field(None, description="Optional VRF name (default: global routing table)")

    @field_validator('neighbor')
    @classmethod
    def _validate_neighbor(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError(f"neighbor must be a valid IP address, got: {v!r}")
        return v

class EigrpQuery(BaseParamsModel):
    device: str = Field(..., description="Device name from inventory")
    query: Literal["neighbors", "interfaces", "config", "topology"] = Field(
        ..., description="EIGRP query type"
    )
    vrf: str | None = Field(None, description="Optional VRF name")

class RoutingQuery(BaseParamsModel):
    device: str
    prefix: str | None = Field(None, description="Optional prefix to look up")
    vrf: str | None = Field(None, description="Optional VRF name (default: global routing table)")

    @field_validator('prefix')
    @classmethod
    def _validate_prefix(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _PREFIX_RE.match(v):
            raise ValueError(
                f"prefix must be a valid IPv4 address or CIDR (e.g. 10.0.0.0/24), got: {v!r}"
            )
        return v

# Routing policies query - input model
class RoutingPolicyQuery(BaseParamsModel):
    device: str
    query: Literal[
        "redistribution", "route_maps", "prefix_lists",
        "policy_based_routing", "access_lists"
    ] = Field(..., description="redistribution | route_maps | prefix_lists | policy_based_routing | access_lists")
    vrf: str | None = Field(None, description="Optional VRF name (default: global routing table)")

# Interfaces query - input model
class InterfacesQuery(BaseParamsModel):
    device: str = Field(..., description="Device name from inventory")

# Show command - input model
class ShowCommand(BaseParamsModel):
    """Run a show command against a network device."""
    device: str = Field(..., description="Device name from inventory (e.g. A1C, E1C)")
    command: str = Field(..., description="Show command to execute on the device")

    @field_validator("command")
    @classmethod
    def must_be_read_only(cls, v: str) -> str:
        """Enforce safe, read-only show commands (all vendors).

        Rules:
          - Must start with 'show ' (case-insensitive) or '/' (RouterOS)
          - Must not contain control characters (\\r, \\n, \\x00)
          - 'show' commands: second token must not be a sensitive command category
          - RouterOS '/' commands: must contain a safe verb and no dangerous verbs
        """
        stripped = v.strip()

        # Reject control characters — prevent multi-command injection on device PTY
        if any(c in stripped for c in '\r\n\x00'):
            raise ValueError("run_show: command must not contain control characters")

        if stripped.lower().startswith("show "):
            # Blocklist sensitive show categories that expose credentials/keys/config.
            # Also catches IOS abbreviations (e.g. "show run" → "show running-config"):
            # if any blocked word starts with the user's token, treat it as blocked.
            # Minimum 3 chars for prefix matching to avoid false positives on short tokens.
            _BLOCKED = frozenset({"running-config", "startup-config", "tech-support",
                                  "aaa", "crypto", "snmp", "secret"})
            tokens = stripped.lower().split()
            if len(tokens) >= 2:
                cmd = tokens[1]
                if any(cmd == b or (len(cmd) >= 3 and b.startswith(cmd)) for b in _BLOCKED):
                    raise ValueError(
                        f"run_show: 'show {cmd}' is not permitted (sensitive data)"
                    )

        elif stripped.startswith("/"):
            # RouterOS commands: must contain a safe verb and no dangerous verbs
            _ROS_SAFE      = frozenset({"print", "monitor"})
            _ROS_DANGEROUS = frozenset({"set", "add", "remove", "disable", "enable",
                                        "reset", "move", "unset"})
            tokens = stripped.lower().split()
            if not any(t in _ROS_SAFE for t in tokens):
                raise ValueError(
                    f"run_show: RouterOS command must contain a read-only verb "
                    f"(print, monitor). Got: {stripped!r}"
                )
            if any(t in _ROS_DANGEROUS for t in tokens):
                raise ValueError(
                    f"run_show: RouterOS command contains a dangerous verb. Got: {stripped!r}"
                )

        else:
            raise ValueError(
                f"run_show only accepts read-only commands: 'show ...' (IOS/IOS-XE) "
                f"or '/...' (RouterOS). Got: {stripped!r}"
            )

        return v

# Empty placeholder - input model
class EmptyInput(BaseParamsModel):
    pass
