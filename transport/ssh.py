"""Scrapli SSH executor — multi-vendor, libscrapli backend."""
import asyncio
import logging
import os

from scrapli import AuthOptions, Cli, SessionOptions
from scrapli.exceptions import OpenException
from scrapli.transport import BinOptions
from scrapli.transport import Ssh2Options as TransportSsh2Options

from core.settings import (
    PASSWORD,
    SSH_RETRIES,
    SSH_RETRY_DELAY,
    SSH_STRICT_HOST_KEY,
    SSH_TIMEOUT_OPS,
    USERNAME,
)
from core.vault import get_secret

log = logging.getLogger("dblcheck.transport.ssh")

# ── Session cache (connection reuse within a device collection) ────────────────
_sessions: dict[str, Cli] = {}


async def open_session(device: dict, timeout_ops: int | None = None) -> None:
    """Open and cache a persistent SSH session for a device (keyed by host)."""
    key = device["host"]
    if key in _sessions:
        return
    cli = _build_cli(device, timeout_ops)
    try:
        await cli.open_async()
    except Exception:
        try:
            cli._free()
        except Exception:
            pass
        raise
    _sessions[key] = cli


async def close_session(host: str) -> None:
    """Close and remove a cached SSH session by host."""
    cli = _sessions.pop(host, None)
    if cli:
        try:
            await cli.close_async()
        except Exception:
            pass

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

    # VyOS per-command SSH connections time out via bin.Transport (system SSH binary + PTY)
    # in daemon mode. Using libssh2 directly bypasses the PTY-based auth path that hangs.
    _known_hosts = os.path.expanduser("~/.ssh/known_hosts") if SSH_STRICT_HOST_KEY else None
    if platform == "vyos_vyos":
        transport = TransportSsh2Options(known_hosts_path=_known_hosts)
    elif SSH_STRICT_HOST_KEY:
        transport = BinOptions(enable_strict_key=True, known_hosts_path=_known_hosts)
    else:
        transport = None

    return Cli(
        host=device["host"],
        definition_file_or_name=definition,
        auth_options=auth,
        session_options=session,
        transport_options=transport,
    )


async def execute_ssh(device: dict, command: str, timeout_ops: int | None = None) -> str:
    """Execute a show command via Scrapli SSH.

    If a cached session exists for this device (opened by open_session), reuse it.
    Otherwise falls back to a new connection per command with retry.
    Returns the raw CLI output string.
    """
    key = device["host"]
    cached = _sessions.get(key)

    if cached:
        try:
            log.debug("SSH (cached) → %s: %s", device["host"], command)
            result = await cached.send_input_async(input_=command)
            return result.result
        except Exception:
            # Session went bad — evict and fall through to per-command connection
            _sessions.pop(key, None)
            try:
                await cached.close_async()
            except Exception:
                pass

    # Per-command connection flow with retry
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
