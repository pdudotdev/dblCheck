"""SSH into devices and collect actual operational state.

Queries all devices concurrently. Within a single device, queries run
sequentially to avoid SSH session conflicts.
"""
import asyncio
import logging

from input_models.models import OspfQuery, BgpQuery, EigrpQuery, InterfacesQuery
from tools.protocol    import get_ospf, get_bgp, get_eigrp
from tools.operational import get_interfaces
from validation.assertions import AssertionType, Assertion, DeviceState
from validation.normalizers import (
    normalize_interfaces,
    normalize_ospf_neighbors,
    normalize_ospf_details,
    normalize_bgp_summary,
    normalize_eigrp_neighbors,
)

log = logging.getLogger("dblcheck.validation.collector")


async def collect_state(assertions: list[Assertion]) -> dict[str, DeviceState]:
    """Query all devices referenced in assertions and return their operational state.

    Returns a dict mapping device name -> DeviceState.
    """
    plan = _plan_queries(assertions)
    if not plan:
        return {}

    tasks = [_collect_device(device, queries) for device, queries in plan.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    state: dict[str, DeviceState] = {}
    for device, result in zip(plan.keys(), results):
        if isinstance(result, Exception):
            log.error("device collection failed: %s — %s", device, result)
            state[device] = DeviceState(errors=[str(result)])
        else:
            state[device] = result

    return state


def _plan_queries(assertions: list[Assertion]) -> dict[str, set[str]]:
    """Determine which queries each device needs based on the assertion list."""
    plan: dict[str, set[str]] = {}
    for a in assertions:
        needed = plan.setdefault(a.device, set())
        if a.type == AssertionType.INTERFACE_UP:
            needed.add("interfaces")
        elif a.type == AssertionType.OSPF_NEIGHBOR:
            needed.add("ospf_neighbors")
        elif a.type in (AssertionType.OSPF_ROUTER_ID,
                        AssertionType.OSPF_AREA_TYPE,
                        AssertionType.OSPF_DEFAULT_ORIG):
            needed.add("ospf_details")
        elif a.type == AssertionType.BGP_SESSION:
            needed.add("bgp_summary")
        elif a.type == AssertionType.EIGRP_NEIGHBOR:
            needed.add("eigrp_neighbors")
    return plan


async def _collect_device(device: str, queries: set[str]) -> DeviceState:
    """Run all needed queries for one device sequentially."""
    state = DeviceState()

    if "interfaces" in queries:
        result = await get_interfaces(InterfacesQuery(device=device))
        if "error" in result:
            log.warning("%s interfaces: %s", device, result["error"])
            state.errors.append(f"interfaces: {result['error']}")
        else:
            state.interfaces = normalize_interfaces(result)
            log.debug("%s interfaces: %d entries", device, len(state.interfaces))

    if "ospf_neighbors" in queries:
        result = await get_ospf(OspfQuery(device=device, query="neighbors"))
        if "error" in result:
            log.warning("%s ospf neighbors: %s", device, result["error"])
            state.errors.append(f"ospf_neighbors: {result['error']}")
        else:
            state.ospf_neighbors = normalize_ospf_neighbors(result)
            log.debug("%s ospf neighbors: %d entries", device, len(state.ospf_neighbors))

    if "ospf_details" in queries:
        result = await get_ospf(OspfQuery(device=device, query="details"))
        if "error" in result:
            log.warning("%s ospf details: %s", device, result["error"])
            state.errors.append(f"ospf_details: {result['error']}")
        else:
            # Also fetch running config to detect default-information originate,
            # which is not present in 'show ip ospf' output.
            config_result = await get_ospf(OspfQuery(device=device, query="config"))
            config_raw = config_result.get("raw", "") if "error" not in config_result else ""
            state.ospf_details = normalize_ospf_details(result, config_raw=config_raw)
            log.debug("%s ospf details: router_id=%s default_orig=%s", device,
                      state.ospf_details.get("router_id"),
                      state.ospf_details.get("default_originate"))

    if "bgp_summary" in queries:
        result = await get_bgp(BgpQuery(device=device, query="summary"))
        if "error" in result:
            log.warning("%s bgp summary: %s", device, result["error"])
            state.errors.append(f"bgp_summary: {result['error']}")
        else:
            state.bgp_summary = normalize_bgp_summary(result)
            log.debug("%s bgp summary: %d neighbors", device, len(state.bgp_summary))

    if "eigrp_neighbors" in queries:
        result = await get_eigrp(EigrpQuery(device=device, query="neighbors"))
        if "error" in result:
            log.warning("%s eigrp neighbors: %s", device, result["error"])
            state.errors.append(f"eigrp_neighbors: {result['error']}")
        else:
            state.eigrp_neighbors = normalize_eigrp_neighbors(result)
            log.debug("%s eigrp neighbors: %d entries", device, len(state.eigrp_neighbors))

    return state
