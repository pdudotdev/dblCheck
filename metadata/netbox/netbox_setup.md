# NetBox Setup

dblCheck uses NetBox as the source of truth for device inventory and network intent (config contexts). NetBox is optional — the system falls back to `lab_configs/NETWORK.json` when not configured.

---

## Install NetBox (Docker)

```bash
git clone -b release https://github.com/netbox-community/netbox-docker.git
cd netbox-docker
```

### Configure port mapping

Rename the existing test override file and edit it to expose port 8000:

```bash
sudo mv docker-compose.test.override.yml docker-compose.override.yml
```

Edit `docker-compose.override.yml`:

```yaml
services:
  netbox:
    ports:
      - "127.0.0.1:8000:8080"
```

### Start containers

```bash
docker compose up -d
```

First start takes ~2 minutes to run database migrations. All containers show healthy when ready.

---

## Create Superuser

```bash
docker compose exec -e DJANGO_SUPERUSER_PASSWORD=<password> netbox \
  python /opt/netbox/netbox/manage.py createsuperuser \
  --username admin --email admin@dblcheck.local --noinput
```

Restart to apply the port mapping:

```bash
docker compose down && docker compose up -d
```

---

## Create API Token

1. Log in at `http://localhost:8000` with `admin` / `<your_password>`
2. Go to the user menu (top right) → Profile → API Tokens → Add Token
3. Under **Version**, select **v1** — v2 tokens are hashed and incompatible with pynetbox
4. Copy the generated token value (shown once at creation)

---

## Configure dblCheck

Add to `.env`:

```
NETBOX_URL=http://localhost:8000
```

Store the token in Vault:

```bash
vault kv put secret/dblcheck/netbox token=<your_api_token>
```

Or add to `.env` as a fallback (no Vault):

```
NETBOX_TOKEN=<your_api_token>
```

---

## Populate Devices

Run the population script — it creates all prerequisite objects (sites, manufacturers, device types, platforms, custom fields) and all 16 devices automatically. It also uploads per-device intent from `intent/INTENT.json` as NetBox config contexts.

```bash
python lab_configs/populate_netbox.py
```

The script is idempotent — safe to run multiple times. Verify the result:

```python
PYTHONPATH=/home/mcp/dblCheck python -c "
from core.netbox import load_devices
d = load_devices()
print(f'{len(d)} devices loaded from NetBox')
for name, info in sorted(d.items()):
    print(f'  {name}: {info[\"host\"]} ({info[\"cli_style\"]})')
"
```

---

## Device Reference

| Device | Platform | cli_style | Management IP | Location |
|--------|----------|-----------|---------------|----------|
| A1M | mikrotik_routeros | routeros | 172.20.20.201 | Access |
| A2V | vyos_vyos | vyos | 172.20.20.202 | Access |
| A3V | vyos_vyos | vyos | 172.20.20.203 | Access |
| A4M | mikrotik_routeros | routeros | 172.20.20.204 | Access |
| D1C | cisco_iosxe | ios | 172.20.20.205 | Distribution |
| D2B | aruba_aoscx | aos | 172.20.20.206 | Distribution |
| C1J | juniper_junos | junos | 172.20.20.207 | Core |
| C2A | arista_eos | eos | 172.20.20.208 | Core |
| E1C | cisco_iosxe | ios | 172.20.20.209 | Edge |
| E2C | cisco_iosxe | ios | 172.20.20.210 | Edge |
| B1C | cisco_iosxe | ios | 172.20.20.211 | Local Branch |
| B2C | cisco_iosxe | ios | 172.20.20.212 | Local Branch |
| DC1V | vyos_vyos | vyos | 172.20.20.219 | Data Center |
| IAN | cisco_iosxe | ios | 172.20.20.220 | ISP A |
| IBN | cisco_iosxe | ios | 172.20.20.230 | ISP B |
| X1C | cisco_iosxe | ios | 172.20.20.240 | Remote Branch |

---

## Production: Boot Persistence

### Enable Docker to start on boot

```bash
sudo systemctl enable docker
```

### Add restart policies

Edit `docker-compose.override.yml` to add `restart: unless-stopped` to each service:

```yaml
services:
  netbox:
    ports:
      - "127.0.0.1:8000:8080"
    restart: unless-stopped
  netbox-worker:
    restart: unless-stopped
  netbox-housekeeping:
    restart: unless-stopped
  postgres:
    restart: unless-stopped
  redis:
    restart: unless-stopped
  redis-cache:
    restart: unless-stopped
```

### Verify after reboot

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

---

## Troubleshooting

### Containers exited after reboot (NetBox unreachable)

Cause: Docker containers don't restart automatically without `restart: unless-stopped`.

Fix: Add restart policies as above, then `docker compose up -d`.

### dblCheck using NETWORK.json after NetBox is restored

Cause: `core/inventory.py` caches `inventory_source` from startup.

Fix: Restart the dblCheck process (or daemon: `systemctl restart dblcheck`).

### API token rejected (401)

Cause: v2 tokens are hashed and incompatible with pynetbox.

Fix: Delete the v2 token and create a new one with **Version: v1**.

### populate_netbox.py fails on first run

Cause: NetBox containers may still be initializing (migrations running).

Fix: Wait until all containers show `healthy` in `docker compose ps`, then re-run the script. It is idempotent.
