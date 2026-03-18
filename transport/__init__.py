"""Transport dispatcher — routes execute_command calls to the SSH transport."""
import logging

from core.inventory import devices
from transport.ssh     import execute_ssh

log = logging.getLogger("dblcheck.transport")


async def execute_command(device_name: str, cmd_or_action,
                          timeout_ops: int | None = None) -> dict:
    """Execute a read command on a device and return a structured result dict."""
    device = devices.get(device_name)
    if not device:
        return {"error": "Unknown device"}

    cli_style = device["cli_style"]

    log.info("dispatch: %s", device_name)

    command_used = None

    try:
        raw_output = await execute_ssh(device, cmd_or_action, timeout_ops=timeout_ops)
        command_used = cmd_or_action

    except Exception as e:
        log.error("command failed: %s — %s", device_name, e)
        return {"device": device_name, "cli_style": cli_style, "error": str(e)}

    log.debug("audit: device=%s command=%s", device_name,
              command_used if command_used else "(unknown)")

    result = {
        "device":    device_name,
    }
    if command_used:
        result["_command"] = command_used
    result["cli_style"] = cli_style

    result["raw"] = raw_output

    return result
