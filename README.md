# ✨ dblCheck

[![Version](https://img.shields.io/badge/version-1.0.0-1a1a2e)](https://github.com/pdudotdev/dblCheck/releases/tag/1.0.0)
![License](https://img.shields.io/badge/license-BSL%201.1-1a1a2e)
[![Last Commit](https://img.shields.io/github/last-commit/pdudotdev/dblCheck?color=1a1a2e)](https://github.com/pdudotdev/dblCheck/commits/main/)

| | |
|---|---|
| **Platforms** | ![Cisco IOS](https://img.shields.io/badge/Cisco_IOS-0d47a1) ![Cisco IOS-XE](https://img.shields.io/badge/Cisco_IOS--XE-0d47a1) |
| **Transport** | ![SSH](https://img.shields.io/badge/SSH-1565c0) |
| **Integrations** | ![NetBox](https://img.shields.io/badge/NetBox-1976d2) ![HashiCorp Vault](https://img.shields.io/badge/HashiCorp_Vault-1976d2) |

## 📖 **Table of Contents**
- 📜 **dblCheck**
  - [🔭 Overview](#-overview)
  - [⚒️ Core Tech Stack](#️-core-tech-stack)
  - [📋 Validation Scope](#-validation-scope)
  - [🛠️ Installation & Usage](#️-installation--usage)
  - [🔄 Test Network Topology](#-test-network-topology)
  - [📞 Daemon Mode](#-daemon-mode)
  - [📄 Disclaimer](#-disclaimer)
  - [📜 License](#-license)
  - [📧 Collaborations](#-collaborations)

## 🔭 Overview
AI-assisted **network intent validation framework** for Cisco environments. Continuously checks live network state against design intent and invokes a Claude agent to diagnose failures.

▫️ **Key characteristics:**
- [x] **Intent-driven validation** — define expected state in `intent/INTENT.json`, dblCheck does the rest
- [x] **AI root-cause diagnosis** — Claude agent investigates failures using 9 read-only MCP tools
- [x] **Read-only** — agent queries devices, never configures
- [x] **Real-time dashboard** — live validation results and streamed AI diagnosis
- [x] **Daemon mode** — scheduled validation runs, always-on monitoring
- [x] **HashiCorp Vault** — all secrets (device creds, NetBox token, API key) stored in Vault
- [x] **NetBox** — device inventory loaded automatically
- [x] **CI/CD ready** — JSON output mode + exit codes

▫️ **Supported models:**
- [x] Haiku 4.5
- [x] Sonnet 4.6
- [x] Opus 4.6 (default, best reasoning)

## ⚒️ Core Tech Stack

| Tool | |
|------|---|
| Claude Code | ✓ |
| MCP (FastMCP) | ✓ |
| Python | ✓ |
| Scrapli | ✓ |
| Genie | ✓ |
| HashiCorp Vault | ✓ |
| NetBox | ✓ |

## 📋 Validation Scope

| Protocol | What's Checked |
|----------|---------------|
| **OSPF** | Neighbor state (FULL), area config, process config |
| **BGP** | Peer state (Established), prefix counts |
| **Interfaces** | Up/down state, expected operational status |

## 🛠️ Installation & Usage

▫️ **Prerequisites:**
- Python 3.11+
- HashiCorp Vault (KV v2)
- NetBox
- Git

▫️ **Step 1 — Install:**
```
git clone https://github.com/pdudotdev/dblCheck /opt/dblcheck
cd /opt/dblcheck
python3 -m venv dbl
dbl/bin/pip install -r requirements.txt
```

▫️ **Step 2 — Vault secrets:**
```
vault kv put secret/dblcheck/router username=<user> password=<pass>
vault kv put secret/dblcheck/netbox token=<token>
# vault kv put secret/dblcheck/anthropic api_key=<key>
```

▫️ **Step 3 — Configure `.env`:**
```
cp .env.example .env
```
Edit `.env` and set `VAULT_ADDR`, `VAULT_TOKEN`, and `NETBOX_URL`.

▫️ **Step 4 — Claude auth**:

Option A — Anthropic account:
```
claude login
```
Option B — API key via Vault.

▫️ **Step 5 — Register the MCP server:**
```
claude mcp add dblcheck -s user -- ./dbl/bin/python server/MCPServer.py
```

▫️ **Step 6 — Run:**
```
dbl/bin/python cli/dblcheck.py                   # full validation
dbl/bin/python cli/dblcheck.py --device C1C      # single device
dbl/bin/python cli/dblcheck.py --no-diagnose     # skip AI diagnosis
dbl/bin/python cli/dblcheck.py --format json     # JSON output for CI/CD
```

## 📞 Daemon Mode

dblCheck runs as a **systemd daemon** that validates the network on a schedule and serves a live dashboard.

▫️ **Install the service:**
```
sudo deploy/install.sh
```
Detects your install path and user automatically — no manual editing required.

▫️ **Manage with:**
`systemctl start | stop | restart | status dblcheck`

▫️ **Dashboard:**
```
http://localhost:5556
```
Shows live validation results and streams AI diagnosis output when failures are found. Port is configurable via `DASHBOARD_PORT` in `.env`.

⚠️ **NOTE:** The daemon validates every 300 seconds by default. Change with `INTERVAL=<seconds>` in `.env`.

## 🔄 Test Network Topology

▫️ **Lab environment:**
- [x] 9 devices defined in [**TOPOLOGY.yml**](TOPOLOGY.yml) for [**Containerlab**](https://containerlab.dev/)
- [x] 4 × Cisco IOL nodes (IOS)
- [x] 5 × Cisco c8000v nodes (IOS-XE)
- [x] Default credentials: see [**.env.example**](.env.example)

## 📄 Disclaimer
You are responsible for defining your own network intent (`intent/INTENT.json`), building your test environment, and meeting the necessary conditions (Python 3.11+, Claude CLI, HashiCorp Vault, etc.).

## 📜 License
Licensed under the [**Business Source License 1.1**](LICENSE).
Source code is available for research, educational, and non-commercial use. Commercial use, SaaS deployment, enterprise integration, or paid services require a commercial license.

## 📧 Collaborations
Interested in collaborating?
- **Email:**
  - Reach out at [**hello@ainoc.dev**](mailto:hello@ainoc.dev)
- **LinkedIn:**
  - Let's discuss via [**LinkedIn**](https://www.linkedin.com/in/tmihaicatalin/)
