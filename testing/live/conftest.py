"""
Live-device test conftest — no mocking.

Sets up sys.path only. Tests in testing/live/ connect to real lab devices
via the actual transport layer (SSH). Set NO_LAB=0 to enable.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
