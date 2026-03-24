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
  │  3 · VALIDATE  (the core pipeline)          │
  ├─────────────────────────────────────────────┤
  │                                             │
  │  Four stages, executed in order:            │
  │                                             │
  │  ┌─────────────────────────────────────┐    │
  │  │  3a · DERIVE ASSERTIONS             │    │
  │  │  validation/derivation.py           │    │
  │  │                                     │    │
  │  │  Reads the intent dict and builds   │    │
  │  │  a checklist of Assertion objects   │    │
  │  │  — one per thing that must be true  │    │
  │  │  (e.g. "C1C GigabitEthernet2       │    │
  │  │  should be up/up").                 │    │
  │  │                                     │    │
  │  │  Pure logic — no devices contacted. │    │
  │  │  Covers: interfaces, OSPF, BGP,    │    │
  │  │  EIGRP adjacencies, router-id,     │    │
  │  │  area types, default-originate.     │    │
  │  └──────────────┬──────────────────────┘    │
  │                 │                            │
  │  ┌──────────────┴──────────────────────┐    │
  │  │  3b · COLLECT STATE                 │    │
  │  │  validation/collector.py            │    │
  │  │  transport/ssh.py · transport/      │    │
  │  │  platforms/platform_map.py          │    │
  │  │                                     │    │
  │  │  Looks at which assertions exist    │    │
  │  │  to decide what to query per        │    │
  │  │  device (only fetches what's        │    │
  │  │  needed). SSHs into all devices     │    │
  │  │  concurrently (max 5 parallel).     │    │
  │  │                                     │    │
  │  │  platform_map.py translates         │    │
  │  │  (vendor, protocol, query) into     │    │
  │  │  the correct CLI command for each   │    │
  │  │  of the 6 supported vendors:        │    │
  │  │  IOS, EOS, JunOS, AOS-CX,          │    │
  │  │  RouterOS, VyOS.                    │    │
  │  └──────────────┬──────────────────────┘    │
  │                 │                            │
  │  ┌──────────────┴──────────────────────┐    │
  │  │  3c · NORMALIZE                     │    │
  │  │  validation/normalizers.py          │    │
  │  │                                     │    │
  │  │  Each vendor's CLI output looks     │    │
  │  │  different. Normalizers parse the   │    │
  │  │  raw text into a common structure   │    │
  │  │  the evaluator can compare.         │    │
  │  │                                     │    │
  │  │  e.g. IOS "show ip ospf neighbor"   │    │
  │  │  and JunOS "show ospf neighbor"     │    │
  │  │  both become:                       │    │
  │  │  [{"neighbor_id", "state",          │    │
  │  │    "interface", "area"}]            │    │
  │  └──────────────┬──────────────────────┘    │
  │                 │                            │
  │  ┌──────────────┴──────────────────────┐    │
  │  │  3d · EVALUATE                      │    │
  │  │  validation/evaluator.py            │    │
  │  │                                     │    │
  │  │  Walks each Assertion, looks up     │    │
  │  │  the matching value in collected    │    │
  │  │  DeviceState, returns PASS / FAIL   │    │
  │  │  / ERROR per assertion.             │    │
  │  │                                     │    │
  │  │  Handles interface name matching    │    │
  │  │  across vendors (e.g. "Gi2" ==     │    │
  │  │  "GigabitEthernet2").              │    │
  │  └──────────────┬──────────────────────┘    │
  │                 │                            │
  │  Results formatted by validation/report.py  │
  └──────────┬──────────────────────┬───────────┘
             │                      │
     [ No drift ]          [ State drift ]
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

## MCP Tools — the AI diagnosis read path

When Claude diagnoses failures (step 5), it queries devices through a
separate read-only MCP server (`server/MCPServer.py`), not through
the validation pipeline.

```
  Claude CLI subprocess
       │
       │  MCP tool call (e.g. get_ospf device=C1C query=neighbors)
       ▼
  server/MCPServer.py         ← FastMCP, 8 registered tools
       │
  tools/protocol.py           ← get_ospf, get_bgp, get_eigrp
  tools/routing.py            ← get_routing, get_routing_policies
  tools/operational.py        ← get_interfaces, run_show
  tools/state.py              ← get_intent
       │
  input_models/models.py      ← Pydantic validation + injection prevention
       │
  platforms/platform_map.py   ← (vendor, protocol, query) → CLI command
       │
  transport/ → transport/ssh.py  ← Scrapli SSH, session cache, retry
       │
       ▼
  Raw CLI output returned to Claude
```

The tools share the same platform_map and transport layer as the
validation pipeline, but they do not use the normalizers or evaluator.
Claude gets raw device output and interprets it directly.

---

## Files at a Glance

| Step | Key Files |
|------|-----------|
| **Daemon** | `deploy/dblcheck_daemon.py` |
| **1 · Credentials** | `core/vault.py` · `core/settings.py` |
| **2 · Inventory & Intent** | `core/inventory.py` · `core/netbox.py` |
| **3a · Derive assertions** | `validation/derivation.py` · `validation/assertions.py` |
| **3b · Collect state** | `validation/collector.py` · `transport/ssh.py` · `platforms/platform_map.py` |
| **3c · Normalize** | `validation/normalizers.py` |
| **3d · Evaluate** | `validation/evaluator.py` · `validation/report.py` |
| **4 · Compare** | `cli/dblcheck.py` · `data/incident.json` |
| **5 · Diagnose** | `cli/dblcheck.py` · `server/MCPServer.py` · `tools/` |
| **6 · Jira Ticket** | `core/jira_client.py` · `data/incident.json` |
| **7 · Dashboard** | `data/dashboard_state.json` · `dashboard/ws_bridge.py` |
| **Input validation** | `input_models/models.py` |
