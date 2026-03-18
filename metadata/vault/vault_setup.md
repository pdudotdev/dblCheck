# HashiCorp Vault Setup

dblCheck uses Vault to store all secrets (device credentials, NetBox token, Anthropic API key, Jira token, dashboard token). Vault is optional — the system falls back to `.env` values when not configured.

---

## Install Vault

```bash
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install vault
```

---

## Start Vault (dev mode — lab only)

Dev mode keeps everything in memory. Secrets are lost on restart. Use this for local development only.

```bash
vault server -dev -dev-root-token-id="dev-root-token" &
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='dev-root-token'
```

> For production: use a persistent storage backend + AppRole auth + audit logging. See the [Production Initialization](#production-initialization) section below.

---

## Store Secrets

```bash
# Required: device SSH credentials
vault kv put secret/dblcheck/router username=<router_username> password=<router_password>

# Required: NetBox API token
vault kv put secret/dblcheck/netbox token=<netbox_api_token>

# Required: Anthropic API key (if not using `claude login`)
vault kv put secret/dblcheck/anthropic api_key=<anthropic_api_key>

# Optional: Jira integration
vault kv put secret/dblcheck/jira token=<jira_api_token>

# Optional: dashboard token authentication
vault kv put secret/dblcheck/dashboard token=<dashboard_token>
```

---

## Verify

```bash
vault kv get secret/dblcheck/router
vault kv get secret/dblcheck/netbox
vault kv get secret/dblcheck/anthropic
```

---

## Configure dblCheck

Add to `.env`:

```
VAULT_ADDR=http://127.0.0.1:8200
VAULT_TOKEN=dev-root-token
```

When these are set, `core/vault.py` reads secrets from Vault instead of `.env`. If Vault is unreachable, the system falls back to the corresponding env vars in `.env` (see `.env.example`).

---

## Vault Paths Reference

| Path | Keys | Used by |
|------|------|---------|
| `secret/dblcheck/router` | `username`, `password` | `core/settings.py` — SSH credentials for all devices |
| `secret/dblcheck/netbox` | `token` | `core/netbox.py` — NetBox API access |
| `secret/dblcheck/anthropic` | `api_key` | `cli/dblcheck.py` — Anthropic API key for Claude |
| `secret/dblcheck/jira` | `token` | `core/jira_client.py` — Jira API token |
| `secret/dblcheck/dashboard` | `token` | `deploy/dblcheck_daemon.py` — dashboard auth token |

Per-platform credential overrides are also supported: `secret/dblcheck/router<cli_style>` (e.g., `secret/dblcheck/routerios`, `secret/dblcheck/routerjunos`). If a platform-specific path exists, it takes precedence over the global `router` path for that vendor.

---

## Production: Boot Persistence

```bash
sudo systemctl enable vault
sudo systemctl start vault
```

Verify after a reboot:

```bash
systemctl status vault
vault status
```

---

## Production: Initialization

Use this for a persistent Vault instance (not dev mode).

### Step 1 — Configure HTTP listener

Edit `/etc/vault.d/vault.hcl`:

```hcl
ui = true

storage "file" {
  path = "/opt/vault/data"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = 1
}
```

```bash
sudo mkdir -p /opt/vault/data
sudo chown vault:vault /opt/vault/data
sudo systemctl restart vault
```

### Step 2 — Initialize Vault (run once, ever)

```bash
export VAULT_ADDR='http://127.0.0.1:8200'
vault operator init -key-shares=1 -key-threshold=1
```

> Save the output — the unseal key and root token are shown only once. Store them somewhere safe.

### Step 3 — Unseal Vault

```bash
vault operator unseal <unseal-key>
```

Vault must be unsealed after every restart.

### Step 4 — Enable KV engine and store secrets

```bash
export VAULT_TOKEN='<root-token-from-init>'
vault secrets enable -path=secret kv-v2
vault kv put secret/dblcheck/router username=<user> password=<pass>
vault kv put secret/dblcheck/netbox token=<token>
# ... (remaining paths as above)
```

### Step 5 — Update .env

```
VAULT_ADDR=http://127.0.0.1:8200
VAULT_TOKEN=<root-token-from-init>
```

---

## Troubleshooting

### Vault sealed after reboot

Cause: by design — production Vault seals on every restart.

Fix:
```bash
export VAULT_ADDR='http://127.0.0.1:8200'
vault operator unseal <unseal-key>
```

### Vault running but `vault status` returns connection error

Cause: HTTPS listener with self-signed cert while `VAULT_ADDR` uses `http://`.

Fix: Switch to the HTTP listener config above, or set `VAULT_SKIP_VERIFY=true` if using TLS.

### dblCheck using .env after Vault is restored

Cause: `core/vault.py` caches a `_VAULT_FAILED` sentinel after the first failed connection.

Fix: Restart the dblCheck process (or daemon: `systemctl restart dblcheck`).

### Dev mode secrets not available after restart

Cause: Dev mode stores everything in RAM — all secrets are lost on process exit.

Fix: Re-run `vault kv put ...` after restarting dev mode. For persistence, switch to production mode.
