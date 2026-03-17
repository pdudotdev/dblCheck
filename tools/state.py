"""Network state tools: get_intent."""
import json
import logging
import os

log = logging.getLogger("dblcheck.tools.state")

from input_models.models import EmptyInput

_BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INTENT_FILE = os.path.join(_BASE_DIR, "intent", "INTENT.json")


async def get_intent(params: EmptyInput) -> dict:
    """Return the desired network intent."""
    if not os.path.exists(_INTENT_FILE):
        raise RuntimeError("INTENT.json not found")
    with open(_INTENT_FILE) as f:
        return json.load(f)
