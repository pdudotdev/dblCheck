# dblCheck — Operational Flow

> **Each validation cycle runs as a fresh subprocess.**
> Credentials, inventory, and intent are fetched from scratch on every run — nothing is cached between cycles.

---

```
  ╔═════════════════════════════════════════════╗
  ║  DAEMON  ·  deploy/dblcheck_daemon.py       ║
  ╠═════════════════════════════════════════════╣
  ║  Starts two tasks in parallel:              ║
  ║  ▸ Validation loop — fires every INTERVAL   ║
  ║  ▸ WebSocket bridge — streams live state    ║
  ║    to the browser dashboard                 ║
  ╚══════════════════════╦══════════════════════╝
                         ║
                 (every INTERVAL sec)
                         ║
  ┌──────────────────────╨──────────────────────┐
  │  1 · CREDENTIALS                            │
  ├─────────────────────────────────────────────┤
  │  core/vault.py  ·  core/settings.py         │
  │                                             │
  │  HashiCorp Vault → .env fallback            │
  │  Loads SSH creds, API keys, tokens          │
  └──────────────────────┬──────────────────────┘
                         │
  ┌──────────────────────┴──────────────────────┐
  │  2 · INVENTORY & INTENT                     │
  ├─────────────────────────────────────────────┤
  │  core/inventory.py  ·  core/netbox.py       │
  │                                             │
  │  Fetch device list + design intent from     │
  │  NetBox — what the network should look      │
  │  like at all times                          │
  └──────────────────────┬──────────────────────┘
                         │
  ┌──────────────────────┴──────────────────────┐
  │  3 · VALIDATE                               │
  ├─────────────────────────────────────────────┤
  │  core/checker.py  ·  transport/ssh.py       │
  │                                             │
  │  SSH into every device → run show commands  │
  │  → compare live state to design intent      │
  └──────────┬──────────────────────┬───────────┘
             │                      │
     [ ✓  No drift ]       [ ⚠  State drift ]
             │                      │
  ┌──────────┴──────────┐           │
  │  All assertions OK. │           │
  ├─────────────────────┤           │
  │  If a Jira ticket   │  ┌────────┴────────────────────────────┐
  │  was open from a    │  │  4 · COMPARE TO LAST RUN            │
  │  previous incident, │  ├─────────────────────────────────────┤
  │  close it — the     │  │  cli/dblcheck.py                    │
  │  network is back    │  │  data/incident.json                 │
  │  to intended state. │  │                                     │
  └──────────┬──────────┘  │  · No record yet  →  diagnose now   │
             │             │  · Same drift      →  skip this run │
             │             │  · Drift decreased →  Jira comment  │
             │             │  · New/changed     →  diagnose ↓    │
             │             └────────────┬────────────────────────┘
             │                          │
             │             ┌────────────┴────────────────────────┐
             │             │  5 · DIAGNOSE                       │
             │             ├─────────────────────────────────────┤
             │             │  cli/dblcheck.py  ·  core/vault.py  │
             │             │                                     │
             │             │  Spawn Claude CLI subprocess        │
             │             │  (Anthropic API key from Vault).    │
             │             │  Agent queries devices live via     │
             │             │  MCP tools → identifies root cause  │
             │             │  → streams full findings to the     │
             │             │  dashboard in real time             │
             │             └────────────┬────────────────────────┘
             │                          │
             │             ┌────────────┴────────────────────────┐
             │             │  6 · OPEN JIRA TICKET               │
             │             ├─────────────────────────────────────┤
             │             │  core/jira_client.py                │
             │             │                                     │
             │             │  New ticket per diagnosis run,      │
             │             │  full findings attached.            │
             │             │  Previous ticket (if any):          │
             │             │  · Drift still active  →  comment,  │
             │             │    keep ticket open                 │
             │             │  · Drift resolved  →  close ticket  │
             │             │                                     │
             │             │  Writes data/incident.json          │
             │             │  (drift fingerprint + ticket key,   │
             │             │   used for comparison on next run)  │
             │             └────────────┬────────────────────────┘
             │                          │
             └────────────┬─────────────┘
                          │
  ┌───────────────────────┴───────────────────────┐
  │  7 · UPDATE DASHBOARD                         │
  ├───────────────────────────────────────────────┤
  │  data/dashboard_state.json                    │
  │  dashboard/ws_bridge.py                       │
  │                                               │
  │  State file updated → WS bridge detects       │
  │  change → pushes run outcome + full           │
  │  diagnosis stream to all connected browsers   │
  └───────────────────────┬───────────────────────┘
                          │
                  ┌───────┴────────┐
                  │  sleep INTERVAL│
                  │  then repeat   │
                  └───────┬────────┘
                          │
                          ▲  (back to top)
```

---

## Files at a Glance

| Step | Key Files |
|------|-----------|
| **Daemon** | `deploy/dblcheck_daemon.py` |
| **1 · Credentials** | `core/vault.py` · `core/settings.py` |
| **2 · Inventory & Intent** | `core/inventory.py` · `core/netbox.py` |
| **3 · Validate** | `core/checker.py` · `transport/ssh.py` |
| **4 · Compare** | `cli/dblcheck.py` · `data/incident.json` |
| **5 · Diagnose** | `cli/dblcheck.py` · `core/vault.py` |
| **6 · Jira Ticket** | `core/jira_client.py` · `data/incident.json` |
| **7 · Dashboard** | `data/dashboard_state.json` · `dashboard/ws_bridge.py` |
