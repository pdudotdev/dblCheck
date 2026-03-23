"""Populate NetBox from lab_configs/NETWORK.json and legacy/INTENT.json.

Creates all required objects (sites, manufacturers, device types, platforms,
device role, custom fields, devices, IP addresses) and assigns primary IPs.
Also uploads per-device intent as config contexts so dblCheck can load
network intent directly from NetBox at runtime.

Idempotent: existing objects are reused or updated, not duplicated.

Usage:
    python lab_configs/populate_netbox.py

Requires NETBOX_URL in .env; NETBOX_TOKEN loaded from Vault (dblcheck/netbox) with fallback to NETBOX_TOKEN env var.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pynetbox
from dotenv import load_dotenv

from core.vault import get_secret

load_dotenv()

NETWORK_JSON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "legacy", "NETWORK.json")
INTENT_JSON  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "legacy", "INTENT.json")

MANUFACTURER_MAP = {
    "cisco_iosxe":      "Cisco",
    "mikrotik_routeros": "MikroTik",
    "vyos_vyos":        "VyOS",
    "aruba_aoscx":      "Aruba",
    "juniper_junos":    "Juniper",
    "arista_eos":       "Arista",
}


def get_or_create(endpoint, lookup: dict, create: dict | None = None):
    """Return an existing object matching lookup, or create one using create dict.

    If create is None, uses lookup as the creation payload.
    """
    obj = endpoint.get(**lookup)
    if obj:
        return obj, False
    payload = create if create is not None else lookup
    obj = endpoint.create(**payload)
    return obj, True


def log(msg: str):
    print(msg, flush=True)


def main():
    url = os.getenv("NETBOX_URL", "").strip()
    token = (get_secret("dblcheck/netbox", "token", fallback_env="NETBOX_TOKEN") or "").strip()
    if not url or not token:
        print("ERROR: NETBOX_URL must be set in .env; NETBOX_TOKEN must be in Vault (dblcheck/netbox) or .env")
        sys.exit(1)

    nb = pynetbox.api(url, token=token)
    nb.http_session.timeout = (5, 30)

    with open(NETWORK_JSON) as f:
        inventory: dict = json.load(f)

    # ── 1. Sites ──────────────────────────────────────────────────────────────
    log("Creating sites...")
    sites: dict = {}
    for dev in inventory.values():
        location = dev["location"]
        if location not in sites:
            slug = location.lower().replace(" ", "-")
            obj, created = get_or_create(
                nb.dcim.sites,
                {"slug": slug},
                {"name": location, "slug": slug, "status": "active"},
            )
            sites[location] = obj
            log(f"  {'Created' if created else 'Exists '} site: {location}")

    # ── 2. Manufacturers ──────────────────────────────────────────────────────
    log("Creating manufacturers...")
    manufacturers: dict = {}
    for platform_slug in set(d["platform"] for d in inventory.values()):
        name = MANUFACTURER_MAP.get(platform_slug, platform_slug)
        if name not in manufacturers:
            slug = name.lower().replace(" ", "-")
            obj, created = get_or_create(
                nb.dcim.manufacturers,
                {"slug": slug},
                {"name": name, "slug": slug},
            )
            manufacturers[name] = obj
            log(f"  {'Created' if created else 'Exists '} manufacturer: {name}")

    # ── 3. Device types (one per manufacturer) ────────────────────────────────
    log("Creating device types...")
    device_types: dict = {}
    for platform_slug, mfr_name in MANUFACTURER_MAP.items():
        if mfr_name not in manufacturers:
            continue
        model = mfr_name
        slug = f"{mfr_name.lower()}-router"
        obj, created = get_or_create(
            nb.dcim.device_types,
            {"slug": slug},
            {"manufacturer": manufacturers[mfr_name].id, "model": model, "slug": slug},
        )
        device_types[platform_slug] = obj
        log(f"  {'Created' if created else 'Exists '} device type: {model}")

    # ── 4. Platforms ──────────────────────────────────────────────────────────
    log("Creating platforms...")
    platforms: dict = {}
    for platform_slug, mfr_name in MANUFACTURER_MAP.items():
        if mfr_name not in manufacturers:
            continue
        obj, created = get_or_create(
            nb.dcim.platforms,
            {"slug": platform_slug},
            {
                "name": platform_slug,
                "slug": platform_slug,
                "manufacturer": manufacturers[mfr_name].id,
            },
        )
        platforms[platform_slug] = obj
        log(f"  {'Created' if created else 'Exists '} platform: {platform_slug}")

    # ── 5. Device role ────────────────────────────────────────────────────────
    log("Creating device role...")
    role, created = get_or_create(
        nb.dcim.device_roles,
        {"slug": "router"},
        {"name": "Router", "slug": "router", "color": "0000ff"},
    )
    log(f"  {'Created' if created else 'Exists '} device role: Router")

    # ── 6. Custom fields ──────────────────────────────────────────────────────
    log("Creating custom fields...")
    custom_fields = [
        {"name": "transport", "label": "Transport",  "type": "text",
         "description": "SSH transport identifier (vestigial; libscrapli uses bin)"},
        {"name": "cli_style", "label": "CLI Style",  "type": "text",
         "description": "Platform CLI style: ios, eos, junos, aos, routeros, vyos"},
        {"name": "vrf",       "label": "VRF",        "type": "text",
         "description": "Production VRF name (e.g. VRF1); blank = global/default VRF"},
    ]
    for cf in custom_fields:
        existing = nb.extras.custom_fields.get(name=cf["name"])
        if existing:
            log(f"  Exists  custom field: {cf['name']}")
        else:
            nb.extras.custom_fields.create(
                object_types=["dcim.device"],
                **cf,
            )
            log(f"  Created custom field: {cf['name']}")

    # ── 7. Devices ────────────────────────────────────────────────────────────
    log("Creating devices...")
    devices: dict = {}
    for name, info in inventory.items():
        platform_slug = info["platform"]
        location = info["location"]

        obj, created = get_or_create(
            nb.dcim.devices,
            {"name": name},
            {
                "name": name,
                "device_type": device_types[platform_slug].id,
                "role": role.id,
                "platform": platforms[platform_slug].id,
                "site": sites[location].id,
                "status": "active",
                "custom_fields": {
                    "transport": info.get("transport", "asyncssh"),
                    "cli_style": info["cli_style"],
                    "vrf":       info.get("vrf", ""),
                },
            },
        )
        if not created:
            # Backfill custom fields on existing devices (e.g. vrf added after initial run)
            obj.custom_fields = {
                "transport": info.get("transport", "asyncssh"),
                "cli_style": info["cli_style"],
                "vrf":       info.get("vrf", ""),
            }
            obj.save()
        devices[name] = obj
        log(f"  {'Created' if created else 'Updated'} device: {name}")

    # ── 7.5. Management interfaces ────────────────────────────────────────────
    log("Creating management interfaces...")
    interfaces: dict = {}
    for name in devices:
        intf = nb.dcim.interfaces.get(device=name, name="mgmt")
        if intf:
            interfaces[name] = intf
            log(f"  Exists  interface: {name}/mgmt")
        else:
            intf = nb.dcim.interfaces.create(
                device=devices[name].id,
                name="mgmt",
                type="virtual",
            )
            interfaces[name] = intf
            log(f"  Created interface: {name}/mgmt")

    # ── 8. IP addresses and primary IP assignment ─────────────────────────────
    log("Creating IP addresses and assigning primary IPs...")
    for name, info in inventory.items():
        host = info["host"]
        ip_address = f"{host}/32"

        ip_obj = nb.ipam.ip_addresses.get(address=ip_address)
        if not ip_obj:
            ip_obj = nb.ipam.ip_addresses.create(
                address=ip_address,
                status="active",
                assigned_object_type="dcim.interface",
                assigned_object_id=interfaces[name].id,
            )
            log(f"  Created IP {ip_address} → {name}/mgmt")
        else:
            intf_id = interfaces[name].id
            if not ip_obj.assigned_object or ip_obj.assigned_object_id != intf_id:
                # Can't PATCH assigned_object_type on an existing IP (NetBox 500) — delete and recreate
                ip_obj.delete()
                ip_obj = nb.ipam.ip_addresses.create(
                    address=ip_address,
                    status="active",
                    assigned_object_type="dcim.interface",
                    assigned_object_id=intf_id,
                )
                log(f"  Reassigned IP {ip_address} → {name}/mgmt")
            else:
                log(f"  Exists  IP {ip_address}")

        dev = devices[name]
        if not dev.primary_ip4 or str(dev.primary_ip4) != str(ip_obj):
            dev.primary_ip4 = ip_obj.id
            dev.save()
            log(f"  Assigned primary IP {host} → {name}")

    # ── 9. Intent config contexts ─────────────────────────────────────────────
    log("Uploading intent as NetBox config contexts...")
    with open(INTENT_JSON) as f:
        intent: dict = json.load(f)

    # 9a. Ensure the "dblcheck" tag exists
    tag = nb.extras.tags.get(slug="dblcheck")
    if not tag:
        tag = nb.extras.tags.create(name="dblcheck", slug="dblcheck",
                                    color="aa1409",
                                    description="Managed by dblCheck")
        log("  Created tag: dblcheck")
    else:
        log("  Exists  tag: dblcheck")

    def _upsert_config_context(name: str, data: dict, device_ids: list[int]) -> None:
        existing = nb.extras.config_contexts.get(name=name)
        if existing:
            existing.data = data
            existing.save()
            log(f"  Updated config context: {name}")
        else:
            nb.extras.config_contexts.create(
                name=name,
                data=data,
                is_active=True,
                devices=device_ids,
            )
            log(f"  Created config context: {name}")

    # 9b. Global config context: autonomous_systems (tagged, not device-specific)
    auto_sys = intent.get("autonomous_systems", {})
    if auto_sys:
        existing_global = nb.extras.config_contexts.get(name="dblcheck-global")
        if existing_global:
            existing_global.data = {"autonomous_systems": auto_sys}
            existing_global.save()
            log("  Updated config context: dblcheck-global")
        else:
            nb.extras.config_contexts.create(
                name="dblcheck-global",
                data={"autonomous_systems": auto_sys},
                is_active=True,
                tags=["dblcheck"],
            )
            log("  Created config context: dblcheck-global")

    # 9c. Per-device config contexts
    routers = intent.get("routers", {})
    for dev_name, router_data in routers.items():
        if dev_name not in devices:
            log(f"  Skipped config context for {dev_name} (not in inventory)")
            continue
        _upsert_config_context(
            name=f"dblcheck-{dev_name}",
            data=router_data,
            device_ids=[devices[dev_name].id],
        )

    log(f"\nDone. {len(inventory)} devices processed.")


if __name__ == "__main__":
    main()
