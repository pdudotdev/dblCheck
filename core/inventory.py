"""Device inventory — loads from NetBox.

Exposes the 'devices' dict: {name: {host, platform, transport, cli_style, location}}
All tools that need to look up a device by name import 'devices' from here.
"""
import logging

from core.netbox import load_devices

_log = logging.getLogger("dblcheck.inventory")


_netbox_result = load_devices()
if _netbox_result:
    devices: dict = _netbox_result
    inventory_source: str = "NetBox"
    _log.info("Inventory: loaded %d device(s) from NetBox", len(devices))
else:
    _log.error(
        "No inventory — check NETBOX_URL in .env and netbox token in Vault (dblcheck/netbox)"
    )
    devices: dict = {}
    inventory_source: str = "none"
