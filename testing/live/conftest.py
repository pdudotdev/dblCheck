"""
Live-device test conftest — no mocking.

Sets up sys.path only. Tests in testing/live/ connect to real lab devices
via the actual transport layer (SSH). Set NO_LAB=0 to enable.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True, scope="session")
def refresh_host_keys():
    """Remove stale and scan fresh SSH host keys for all lab devices.

    Containerlab regenerates device host keys on every restart. This fixture
    runs once before any live test to keep ~/.ssh/known_hosts in sync, so
    SSH_STRICT_HOST_KEY=True remains effective without manual intervention.
    """
    from core.inventory import devices

    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(mode=0o700, exist_ok=True)
    known_hosts.touch(exist_ok=True)

    hosts = [d["host"] for d in devices.values()]

    # Remove all stale entries for lab IPs
    for host in hosts:
        subprocess.run(
            ["ssh-keygen", "-R", host],
            capture_output=True,
        )

    # Scan and append fresh keys for all devices in one pass
    result = subprocess.run(
        ["ssh-keyscan", "-T", "5"] + hosts,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        with known_hosts.open("a") as f:
            f.write(result.stdout)
