"""Runtime configuration — credentials, TLS flags, and transport timeout constants.

Loaded once at import time. All transport modules import from here.
"""
import os

from core.vault import get_secret

USERNAME = get_secret("dblcheck/router", "username", fallback_env="ROUTER_USERNAME")
PASSWORD = get_secret("dblcheck/router", "password", fallback_env="ROUTER_PASSWORD")

# Credentials validated at entry points (cli/dblcheck.py, server/MCPServer.py) — not at import time.

# SSH security settings — defaults are lab-safe; set to 'true' in .env for production.
SSH_STRICT_KEY = os.getenv("SSH_STRICT_HOST_KEY", "false").lower() == "true"

# RESTCONF settings — defaults are lab-safe; set RESTCONF_VERIFY_TLS=true for production.
try:
    RESTCONF_PORT = int(os.getenv("RESTCONF_PORT", "443"))
except ValueError:
    raise ValueError(
        f"RESTCONF_PORT must be an integer, got: {os.getenv('RESTCONF_PORT')!r}"
    )
RESTCONF_VERIFY_TLS = os.getenv("RESTCONF_VERIFY_TLS", "false").lower() == "true"

# Scrapli SSH timeout (seconds) applied to all SSH connections.
SSH_TIMEOUT_TRANSPORT = 15   # SSH handshake; devices respond in <5s or are unreachable
SSH_TIMEOUT_OPS       = 30   # Command execution — kept high for slow commands

# SSH retry settings — applied to transient connection failures only.
SSH_RETRIES     = 1   # One retry after initial failure (2 total); reduces worst-case per-call from 94s → 32s
SSH_RETRY_DELAY = 2   # Seconds between retries
