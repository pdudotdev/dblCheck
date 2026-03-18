"""NetBox device inventory loader.

Fetches device inventory from a NetBox instance and maps it to the schema
expected by core/inventory.py. Returns None if NetBox is not configured
(NETBOX_URL absent), unreachable, or returns no usable devices.

NetBox custom fields required on the Device model:
  transport  — 'asyncssh' (vestigial; actual transport is libscrapli's bin backend)
  cli_style  — 'ios', 'eos', 'junos', 'aos', 'routeros', 'vyos'
  vrf        — optional; production VRF name (e.g. 'VRF1'); omit for devices using the default/global VRF

The 'location' field is read from device.site.name.
"""
import logging
import os

from core.vault import get_secret

log = logging.getLogger("dblcheck.netbox")


def load_devices() -> dict | None:
    """Load device inventory from NetBox.

    Returns a dict: {device_name: {host, platform, transport, cli_style, location}}

    Returns None if NetBox is not configured, unreachable, or returns no devices.
    """
    url = os.getenv("NETBOX_URL", "").strip()
    token = (get_secret("dblcheck/netbox", "token", fallback_env="NETBOX_TOKEN") or "").strip()

    if not url or not token:
        return None

    try:
        import pynetbox
        nb = pynetbox.api(url, token=token)
        nb.http_session.timeout = (5, 15)  # (connect_timeout, read_timeout) in seconds
        raw_devices = list(nb.dcim.devices.all())
    except Exception as exc:
        log.warning("NetBox unavailable: %s", exc)
        return None

    if not raw_devices:
        log.warning("NetBox returned no devices")
        return None

    devices: dict = {}
    for dev in raw_devices:
        try:
            name = dev.name
            if not name:
                continue

            # primary_ip comes back as an IPAddress object with .address = "x.x.x.x/mask"
            if not dev.primary_ip:
                log.warning("NetBox device %s has no primary IP — skipping", name)
                continue
            ip_addr = dev.primary_ip.address
            if not ip_addr:
                log.warning("NetBox device %s primary_ip.address is None — skipping", name)
                continue
            host = ip_addr.split("/")[0]

            platform = dev.platform.slug if dev.platform else ""
            transport = (dev.custom_fields or {}).get("transport", "")
            cli_style = (dev.custom_fields or {}).get("cli_style", "")
            vrf       = (dev.custom_fields or {}).get("vrf", "") or ""
            location  = dev.site.name if dev.site else ""

            if not platform or not transport or not cli_style:
                log.warning(
                    "NetBox device %s missing required fields "
                    "(platform=%r, transport=%r, cli_style=%r) — skipping",
                    name, platform, transport, cli_style,
                )
                continue

            entry: dict = {
                "host":      host,
                "platform":  platform,
                "transport": transport,
                "cli_style": cli_style,
                "location":  location,
            }
            if vrf:
                entry["vrf"] = vrf
            devices[name] = entry
        except Exception as exc:
            log.warning("NetBox device mapping error (skipping): %s", exc)

    if not devices:
        log.warning("NetBox: no valid devices after mapping")
        return None

    log.info("Loaded %d device(s) from NetBox", len(devices))
    return devices


def load_intent() -> dict | None:
    """Load network intent from NetBox config contexts.

    Expects config contexts named ``dblcheck-<device>`` (one per router) and
    optionally ``dblcheck-global`` (containing ``autonomous_systems`` data).

    Returns a dict matching the INTENT.json schema:
        {"autonomous_systems": {...}, "routers": {name: {...}, ...}}

    Returns None if NetBox is not configured, unreachable, or no dblcheck
    config contexts are found.
    """
    url = os.getenv("NETBOX_URL", "").strip()
    token = (get_secret("dblcheck/netbox", "token", fallback_env="NETBOX_TOKEN") or "").strip()

    if not url or not token:
        return None

    try:
        import pynetbox
        nb = pynetbox.api(url, token=token)
        nb.http_session.timeout = (5, 15)
        contexts = list(nb.extras.config_contexts.filter(name__isw="dblcheck-"))
    except Exception as exc:
        log.warning("NetBox config contexts unavailable: %s", exc)
        return None

    if not contexts:
        log.warning("NetBox: no dblcheck config contexts found")
        return None

    autonomous_systems: dict = {}
    routers: dict = {}

    for ctx in contexts:
        name: str = ctx.name
        data: dict = ctx.data or {}

        if name == "dblcheck-global":
            autonomous_systems = data.get("autonomous_systems", data)
        elif name.startswith("dblcheck-"):
            device_name = name[len("dblcheck-"):]
            routers[device_name] = data

    if not routers:
        log.warning("NetBox: no per-device config contexts found")
        return None

    intent: dict = {"routers": routers}
    if autonomous_systems:
        intent["autonomous_systems"] = autonomous_systems

    log.info("Loaded intent for %d router(s) from NetBox config contexts", len(routers))
    return intent
