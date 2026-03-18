"""Scrapli SSH executor — multi-vendor, libscrapli backend."""
import asyncio
import logging
import os

from scrapli import Cli, AuthOptions, SessionOptions
from scrapli.exceptions import OpenException
from core.settings import (
    USERNAME, PASSWORD,
    SSH_TIMEOUT_OPS, SSH_RETRIES, SSH_RETRY_DELAY,
)
from core.vault import get_secret

log = logging.getLogger("dblcheck.transport.ssh")

# Custom YAML definitions for platforms whose bundled scrapli2 definition
# needs overrides (prompt patterns, mode definitions, failure indicators).
_DEFINITIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platforms", "definitions")
_CUSTOM_DEFINITIONS: dict[str, str] = {
    "mikrotik_routeros": os.path.join(_DEFINITIONS_DIR, "mikrotik_routeros.yaml"),
    "vyos_vyos":         os.path.join(_DEFINITIONS_DIR, "vyos_vyos.yaml"),
}


def _build_cli(device: dict, timeout_ops: int | None = None) -> Cli:
    platform = device["platform"]
    definition = _CUSTOM_DEFINITIONS.get(platform, platform)
    op_timeout = timeout_ops or SSH_TIMEOUT_OPS

    # Per-platform credential override: check dblcheck/router<cli_style> first.
    # Falls back to the default dblcheck/router credentials if not found.
    cli_style = device.get("cli_style", "")
    username = get_secret(f"dblcheck/router{cli_style}", "username", quiet=True) or USERNAME
    password = get_secret(f"dblcheck/router{cli_style}", "password", quiet=True) or PASSWORD

    if platform == "mikrotik_routeros":
        # +ct disables colors and autocompletion for clean output
        auth = AuthOptions(username=f"{username}+ct", password=password)
        session = SessionOptions(operation_timeout_s=op_timeout, return_char="\r\n")
    else:
        auth = AuthOptions(username=username, password=password)
        session = SessionOptions(operation_timeout_s=op_timeout)

    return Cli(
        host=device["host"],
        definition_file_or_name=definition,
        auth_options=auth,
        session_options=session,
    )


async def execute_ssh(device: dict, command: str, timeout_ops: int | None = None) -> str:
    """Execute a show command via Scrapli SSH.

    Returns the raw CLI output string.
    Retries up to SSH_RETRIES times on transient failures.
    """
    last_exc = None
    for attempt in range(1 + SSH_RETRIES):
        try:
            async with _build_cli(device, timeout_ops) as conn:
                log.debug("SSH → %s: %s", device["host"], command)
                result = await conn.send_input_async(input_=command)
            return result.result
        except OpenException:
            raise  # Connection/auth failures — don't retry
        except Exception as e:
            last_exc = e
            if attempt < SSH_RETRIES:
                log.warning(
                    "SSH attempt %d/%d failed for %s: %s — retrying in %ds",
                    attempt + 1, 1 + SSH_RETRIES, device["host"], e, SSH_RETRY_DELAY,
                )
                await asyncio.sleep(SSH_RETRY_DELAY)
    raise last_exc
