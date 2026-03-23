"""Protocol diagnostic tools: get_ospf, get_bgp, get_eigrp."""
from core.inventory import devices
from input_models.models import BgpQuery, EigrpQuery, OspfQuery
from platforms.platform_map import get_action
from tools import _error_response
from transport import execute_command


async def get_ospf(params: OspfQuery) -> dict:
    """
    Retrieve OSPF operational data from a network device.

    Use this tool to investigate OSPF adjacency, database, and configuration
    issues during troubleshooting.

    Supported queries:
    - neighbors   → Check OSPF neighbor state and adjacency health
    - database    → Inspect LSDB contents and LSA propagation
    - borders     → Identify ABRs/ASBRs and inter-area routing
    - config      → Review OSPF configuration on the device
    - interfaces  → Verify OSPF-enabled interfaces and parameters
    - details     → Vendor-specific detailed OSPF information (if available)

    Notes:
    - Not all queries are supported on all platforms.

    Use this tool before falling back to run_show.
    """
    device = devices.get(params.device)
    if not device:
        return _error_response(params.device, f"Unknown device: {params.device}")

    try:
        action = get_action(device, "ospf", params.query, vrf=params.vrf)
    except KeyError:
        return _error_response(params.device, f"OSPF query '{params.query}' not supported on platform {device['cli_style'].upper()}")

    return await execute_command(params.device, action)


async def get_eigrp(params: EigrpQuery) -> dict:
    """
    Retrieve EIGRP operational data from a network device (IOS/IOS-XE only).

    Supported queries:
    - neighbors  → Check EIGRP neighbor adjacencies
    - interfaces → Verify EIGRP-enabled interfaces and parameters
    - config     → Review EIGRP configuration
    - topology   → Inspect EIGRP topology table

    Use this tool before falling back to run_show.
    """
    device = devices.get(params.device)
    if not device:
        return _error_response(params.device, f"Unknown device: {params.device}")

    try:
        action = get_action(device, "eigrp", params.query, vrf=params.vrf)
    except KeyError:
        return _error_response(params.device, f"EIGRP query '{params.query}' not supported on platform {device['cli_style'].upper()}")

    return await execute_command(params.device, action)


async def get_bgp(params: BgpQuery) -> dict:
    """
    Retrieve BGP operational data from a network device.

    Use this tool to investigate BGP session state, route exchange,
    and configuration during routing issues.

    Supported queries:
    - summary    → Check neighbor state, uptime, and prefixes exchanged
    - table      → Inspect detailed BGP table and path attributes
    - config     → Review BGP configuration
    - neighbors  → Per-neighbor detail: negotiated timers, capabilities, address families

    Notes:
    - Supported queries vary by platform.
    - For "neighbors", provide neighbor=<ip> to scope output to a single peer.

    Recommended usage:
    - Start with "summary" to verify session health.
    - Use "table" when routes are missing or path selection is unexpected.

    Use this tool before falling back to run_show.
    """
    device = devices.get(params.device)
    if not device:
        return _error_response(params.device, f"Unknown device: {params.device}")

    try:
        action = get_action(device, "bgp", params.query, vrf=params.vrf)
    except KeyError:
        return _error_response(params.device, f"BGP query '{params.query}' not supported on platform {device['cli_style'].upper()}")

    if params.query == "neighbors" and params.neighbor and isinstance(action, str):
        # Append neighbor IP to CLI command string for scoped output
        action = f"{action} {params.neighbor}"

    return await execute_command(params.device, action)
