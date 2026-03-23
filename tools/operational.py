"""Operational tools: get_interfaces, run_show."""
from core.inventory import devices
from input_models.models import InterfacesQuery, ShowCommand
from platforms.platform_map import get_action
from tools import _error_response
from transport import execute_command


async def get_interfaces(params: InterfacesQuery) -> dict:
    """
    Retrieve interface status and IP information from a device.

    Use this tool to verify interface state, IP assignments, and operational
    status during connectivity and routing investigations.

    Notes:
    - Command syntax is vendor-specific and resolved via PLATFORM_MAP.
    - Returns a summary view of interfaces.

    Recommended usage:
    - Use when troubleshooting down links or missing adjacencies.
    - Use to confirm IP addressing and interface operational state.

    Use this tool before falling back to run_show.
    """
    device = devices.get(params.device)
    if not device:
        return _error_response(params.device, f"Unknown device: {params.device}")

    try:
        action = get_action(device, "interfaces", "interface_status")
    except KeyError:
        return _error_response(params.device, f"Interface status not supported on {device['cli_style'].upper()}")

    return await execute_command(params.device, action)


async def run_show(params: ShowCommand) -> dict:
    """Run a show command against a network device (SSH CLI only)."""
    device = devices.get(params.device)
    if not device:
        return _error_response(params.device, f"Unknown device: {params.device}")
    return await execute_command(params.device, params.command.strip())
