"""Runtime configuration — credentials and transport timeout constants.

Loaded once at import time. All transport modules import from here.
"""
import os

from core.vault import get_secret

USERNAME = get_secret("dblcheck/router", "username", fallback_env="ROUTER_USERNAME")
PASSWORD = get_secret("dblcheck/router", "password", fallback_env="ROUTER_PASSWORD")

# Credentials validated at entry points (cli/dblcheck.py, server/MCPServer.py) — not at import time.

# Operation timeout (seconds) — mapped to SessionOptions(operation_timeout_s=SSH_TIMEOUT_OPS).
# Transport-level timeout is handled internally by libscrapli.
SSH_TIMEOUT_OPS = 30   # Command execution — kept high for slow commands

# SSH retry settings — applied to transient connection failures only.
SSH_RETRIES     = 1   # One retry after initial failure (2 total); reduces worst-case per-call from 94s → 32s
SSH_RETRY_DELAY = 2   # Seconds between retries

# Max parallel device connections — prevents asyncio event loop starvation in daemon mode,
# where the bridge polling loops share the event loop with SSH collection tasks.
SSH_MAX_CONCURRENT = 5
