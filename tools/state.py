"""Network state tools: get_intent."""
import logging

log = logging.getLogger("dblcheck.tools.state")

from input_models.models import EmptyInput


async def get_intent(params: EmptyInput) -> dict:
    """Return the desired network intent from NetBox config contexts."""
    try:
        from core.netbox import load_intent as _netbox_intent
        intent = _netbox_intent()
        if intent:
            return intent
    except Exception:
        pass

    return {"error": "Intent not available — NetBox unreachable or no config contexts found"}
