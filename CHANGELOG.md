# Changelog

## [1.2.0] — 2026-03-19

### Jira Incident Lifecycle

- Auto-resolve tickets when all failures clear (transitions API with "done"/"resolve"/"close" matching, `JIRA_RESOLVE_TRANSITION` env var override, comment-only fallback)
- Markdown-to-ADF formatting for Jira tickets and comments (headings, bold, inline code, code blocks)
- Human-readable timestamps in resolution messages (`Mar 19, 2026 18:26 UTC` instead of ISO 8601)

### Dashboard

- Markdown-rendered diagnosis output (headings, bold labels, inline code highlighting via `marked.js` + `highlight.js`)
- Diagnosis panel persistence across page refresh (session NDJSON replay for late joiners)

### Lab Topology

- Replaced 3 VyOS routers (A2V, A3V, DC1V) with Arista cEOS (A2A, A3A, DC1A)

### Test Suite

- Fixed 5 half-tests with missing return value assertions in tool layer tests
- Removed 1 tautological test and 3 redundant tests
- Strengthened 2 weak EIGRP unsupported-platform assertions
- 582 tests across 21 suites (19 unit + 2 integration): +99 tests covering vault client, WebSocket bridge, Jira ADF converter, NetBox loader, transport dispatcher, CLI orchestration gates, command validator evasion vectors, and `_safe()` injection sanitizer boundaries

---

## [1.1.0] — 2026-03-18

### Test Suite

- 489 tests across 14 suites (12 unit, 2 integration) with zero silent passes
- Unit tests: normalizers (6 vendors × 4 protocols), derivation, evaluator, input models, platform map, collector, report formatting, tool layer, helpers
- Integration tests: platform coverage matrix (generates coverage report), end-to-end pipeline (derive → evaluate → report)
- Test runner (`testing/run_tests.sh`) with stable suite IDs and per-suite pass/fail tracking
- `testing/conftest.py` injects mock modules to prevent NetBox/Vault calls during testing

### Documentation

- `metadata/about/guardrails.md` — three-tier safety documentation (code-enforced, config-enforced, behavioral)
- `metadata/vault/vault_setup.md` — complete Vault setup guide with production initialization and troubleshooting
- `metadata/netbox/netbox_setup.md` — complete NetBox setup guide with populate script reference and device table
- `metadata/about/agent_prompt.md` — agent invocation architecture (prompt assembly, CLI flags, timeout, output handling)

---

## [1.0.0] — 2026-03-18

### Intent-Driven Validation

- Assertions derived automatically from NetBox config contexts — no manual test definitions
- Seven assertion types: interface up/up, OSPF neighbor adjacency, OSPF router-id, OSPF area type, OSPF default-originate, BGP session state, EIGRP neighbor adjacency
- Pass/fail/error evaluation with fuzzy interface name matching across vendor abbreviation styles
- CLI output: color-coded terminal report with per-device summary
- Flags: `--no-diagnose`, `--headless`

### Multi-Vendor Support

- Six platforms: Cisco IOS/IOS-XE, Arista EOS, Juniper JunOS, Aruba AOS-CX, MikroTik RouterOS 7, VyOS
- Per-vendor CLI output normalizers for interfaces, OSPF neighbors, OSPF details, and BGP summary
- VRF-aware command generation with vendor-specific syntax (routing-instance, vrf keyword, routing-table filter)
- Platform command map covering OSPF, BGP, routing table, routing policies, and interface categories

### SSH Transport (libscrapli)

- Scrapli 2 with libscrapli backend for async multi-vendor SSH
- Custom YAML platform definitions for MikroTik RouterOS and VyOS (prompt patterns, mode transitions, failure indicators)
- Configurable timeouts and retry logic with automatic retry on transient failures
- Per-platform credential override via Vault (`dblcheck/router<cli_style>`)

### MCP Server (8 tools)

- FastMCP-based server exposing read-only network query tools
- `get_ospf` — neighbors, database, borders, config, interfaces, details
- `get_bgp` — summary, table, config, neighbors
- `get_eigrp` — neighbors, interfaces, config, topology (IOS/IOS-XE only)
- `get_routing` — full table or prefix-filtered lookup
- `get_routing_policies` — redistribution, route-maps, prefix-lists, PBR, ACLs
- `get_interfaces` — interface status and IP addressing
- `run_show` — arbitrary show commands with Pydantic input validation
- `get_intent` — network intent from NetBox config contexts

### AI-Assisted Diagnosis

- Claude CLI subprocess with streaming output and 5-minute timeout
- Investigates failures using MCP tools against live devices
- Produces root-cause analysis grounded in collected evidence
- Failure fingerprinting skips re-diagnosis when failures haven't changed
- Jira integration: auto-creates tickets on new failures, comments on changes, resolves on all-pass

### Live Dashboard

- Single-page web UI served over WebSocket with real-time state updates
- Validation results table with pass/fail badges
- Split-view diagnosis panel: agent reasoning (rendered Markdown) and tool calls (collapsible, with input/output)
- Run history dropdown for reviewing past results
- Token authentication when exposed beyond localhost

### Security

- Read-only by design — no configuration commands can reach devices
- HashiCorp Vault KV v2 for all secrets (router credentials, NetBox token, Anthropic API key, Jira token, dashboard token) with .env fallback
- `run_show` input validation: blocks sensitive commands (running-config, tech-support, aaa, crypto), rejects control characters to prevent multi-command injection, RouterOS verb allowlist (print, monitor only)
- Agent guardrails via `settings.local.json`: denies .env reads, direct SSH, destructive shell commands (rm -rf, git push --force, git reset --hard)
- Prompt sanitization: assertion values embedded in the diagnosis prompt are stripped of control characters and truncated
- Data boundary directive in agent system prompt: device output treated as opaque data, not instructions

### NetBox Integration

- Device inventory from NetBox DCIM (primary IP, platform, transport, cli_style, VRF from custom fields)
- Network intent from config contexts (`dblcheck-<device>`, optional `dblcheck-global`)

### Daemon Mode

- Periodic validation loop with configurable interval
- Headless operation with filesystem-based IPC (JSON/NDJSON in `data/`)
- systemd service template with install script
- Concurrent dashboard serving alongside validation

### Lab Topology

- 16-node Containerlab topology exercising all 6 vendors
- Multi-tier design: access, distribution, core, edge layers
- OSPF multi-area (backbone + stub), EIGRP, BGP, VRF segmentation
- 125 assertions across 28 inter-router links
