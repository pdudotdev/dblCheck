# ✨ dblCheck

[![Version](https://img.shields.io/badge/ver.-1.2.0-1a1a2e)](https://github.com/pdudotdev/dblCheck/releases/tag/1.2.0)
![License](https://img.shields.io/badge/license-BSL1.1-1a1a2e)
[![Last Commit](https://img.shields.io/github/last-commit/pdudotdev/dblCheck?color=1a1a2e)](https://github.com/pdudotdev/dblCheck/commits/main/)

| | |
|---|---|
| **Platforms** | ![Cisco IOS](https://img.shields.io/badge/Cisco_IOS-0d47a1) ![Cisco IOS-XE](https://img.shields.io/badge/Cisco_IOS--XE-0d47a1) ![Arista EOS](https://img.shields.io/badge/Arista_EOS-0d47a1) ![Juniper JunOS](https://img.shields.io/badge/Juniper_JunOS-0d47a1) ![Aruba AOS](https://img.shields.io/badge/Aruba_AOS-0d47a1) ![Vyatta VyOS](https://img.shields.io/badge/Vyatta_VyOS-0d47a1) ![MikroTik RouterOS](https://img.shields.io/badge/MikroTik_RouterOS-0d47a1) ![FRR](https://img.shields.io/badge/FRR-0d47a1) |
| **Transport** | ![SSH](https://img.shields.io/badge/SSH%20CLI-1565c0) ![Scrapli](https://img.shields.io/badge/Scrapli-1565c0) |
| **Integrations** | ![NetBox](https://img.shields.io/badge/NetBox-1976d2) ![HashiCorp Vault](https://img.shields.io/badge/HashiCorp_Vault-1976d2) ![Jira](https://img.shields.io/badge/Jira-1976d2) ![MCP](https://img.shields.io/badge/MCP-1976d2) |
| **Avg. Cost per Agent Session** | ![Cost](https://img.shields.io/badge/%240.19-1e88e5) |

## 📖 **Table of Contents**
- 📜 **dblCheck**
  - [🔭 Overview](#-overview)
  - [🍀 Here's a Quick Demo](#-heres-a-quick-demo)
  - [⭐ What's New in v1.2](#-whats-new-in-v12)
  - [⚒️ Core Tech Stack](#️-core-tech-stack)
  - [📋 Validation Scope](#-validation-scope)
  - [🛠️ Installation & Usage](#️-installation--usage)
  - [🦾 Operating Mode](#-operating-mode)
  - [🔄 Test Network Topology](#-test-network-topology)
  - [⬆️ Planned Upgrades](#️-planned-upgrades)
  - [♻️ Repository Lifecycle](#️-repository-lifecycle)
  - [📄 Disclaimer](#-disclaimer)
  - [📜 License](#-license)
  - [📧 Collaborations](#-collaborations)

## 🔭 Overview
AI-assisted **network intent validation framework** for multi-vendor environments. 

Continuously checks **live network state against design intent** and invokes a Claude agent to diagnose, explain, and document failures and inconsistencies between expected vs. actual state. 

🔑 Therefore, **the key** is having and maintaining an up-to-date network intent schema - and **dblCheck** does the rest.

▫️ **Key characteristics:**
- [x] **Intent-driven validation** - Define expected state in NetBox config contexts
- [x] **AI root-cause diagnosis** - Claude agent investigates failures using 8 read-only MCP tools
- [x] **Read-only** - Agent queries and investigates devices, never configures
- [x] **Real-time dashboard** - Live validation results and streamed AI diagnosis
- [x] **Daemon mode** - Scheduled validation runs, always-on monitoring
- [x] **HashiCorp Vault** - All secrets (device creds, NetBox token, Jira key etc.) stored in Vault
- [x] **NetBox** - Network inventory and expected state loaded automatically
- [x] **Jira** - Network state drift and deviations logged to Jira
- [x] **711 tests** - 21 suites (17 unit + 3 integration + 1 live)

▫️ **Supported models:**
- [x] Haiku 4.5
- [x] Sonnet 4.6
- [x] Opus 4.6 (default, best reasoning)

▫️ **Operational Costs:**
- [x] Periodic network state validation: programmatic, no cost
- [x] Agent diagnosis: **~$0.19 per run** (only on detected drift)

▫️ **Operational Flow:**
- [x] See [**operations.md**](metadata/about/operations.md)

▫️ **Operational Guardrails:**
- [x] See [**guardrails.md**](metadata/about/guardrails.md)

## 🍀 Here's a Quick Demo
- [x] *Demo video coming soon...*

## ⭐ What's New in v1.2
- [x] See [**CHANGELOG.md**](CHANGELOG.md)
 
## ⚒️ Core Tech Stack

| Tool | |
|------|---|
| Claude Agent | ✓ |
| FastMCP | ✓ |
| Python | ✓ |
| Scrapli | ✓ |
| HashiCorp Vault | ✓ |
| NetBox | ✓ |
| Jira | ✓ |

## 📋 Validation Scope

| Protocol | What's Checked |
|----------|---------------|
| **OSPF** | Neighbor state (FULL), area config, process config |
| **EIGRP** | Neighbor state, interfaces, topology |
| **BGP** | Peer state (Established), prefix counts |
| **Interfaces** | Up/down state, expected operational status |

## 🛠️ Installation & Usage

▫️ **Prerequisites:**
- Python 3.11+
- HashiCorp Vault
- NetBox
- Jira (optional)

▫️ **Step 1 - Install:**
```
git clone https://github.com/pdudotdev/dblCheck /opt/dblcheck
cd /opt/dblcheck
python3 -m venv dbl
dbl/bin/pip install -r requirements.txt
```

▫️ **Step 2 - Vault:**

Start Vault (dev mode, lab use):
```
vault server -dev -dev-root-token-id=<your-root-token>
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=<your-root-token>
```

Or initialize and unseal an existing Vault:
```
vault operator init -key-shares=1 -key-threshold=1   # first-time setup
vault operator unseal                                  # after every restart
```

> 🔑 Save the unseal key output from `vault operator init` somewhere safe - you'll need it every time Vault restarts or seals. Without it, a sealed Vault cannot be recovered.

> ⚠️ dblCheck requires Vault to be **running and unsealed** before any run. If Vault is unavailable, credential lookups fall back to env vars (see `.env.example`).

Store secrets:
```
vault kv put secret/dblcheck/router username=<user> password=<pass>
vault kv put secret/dblcheck/netbox token=<token>
vault kv put secret/dblcheck/jira token=<token>
vault kv put secret/dblcheck/dashboard token=<token>
# vault kv put secret/dblcheck/anthropic api_key=<key>
```

▫️ **Step 3 - Configure `.env`:**
- [x] See [**example**](.env.example)
```
cp .env.example .env
```

▫️ **Step 4 - Claude auth**:

Option A - Anthropic account:
```
claude auth login
```
Option B - API key via Vault.

▫️ **Step 5 - Register the MCP server:**
```
claude mcp add dblcheck -s user -- /home/<user>/dbl/bin/python server/MCPServer.py
```

## 🦾 Operating Mode

### Daemon (systemd service)

**dblCheck** runs as a **systemd daemon** that validates the network on a schedule and serves a live dashboard.

▫️ **Install the service:**
```
sudo deploy/install.sh
```
Detects your install path and user automatically - no manual editing required.

▫️ **Manage with:**
`systemctl start | stop | restart | status dblcheck`

▫️ **Dashboard:**
```
http://<IP|localhost>:5556
```
Shows live validation results and streams AI diagnosis output when failures are found. Port is configurable via `DASHBOARD_PORT` in `.env`.

⚠️ **NOTE:** The daemon validates every 300 seconds by default. Change with `INTERVAL=<seconds>` in `.env`.

> **Recommendation:** Runs are sequential — a new validation never starts while the previous one is still running. However, setting `INTERVAL` too low increases SSH load on network devices. Validation itself (polling devices and checking assertions) has **no API cost**. The AI diagnosis agent is only invoked when unexpected failures are detected — that is the only time API costs occur. For most environments, 120–300 seconds is a good range. Each run has a hard timeout of 600 seconds (10 minutes).

## 🔄 Test Network Topology

▫️ **Network diagram:**

![topology](metadata/topology/DBL-TOPOLOGY.png)

▫️ **Lab environment:**
- [x] 16 devices defined in [**TOPOLOGY.yml**](TOPOLOGY.yml)
- [x] 5 × Cisco IOS nodes
- [x] 3 × Cisco IOS-XE nodes
- [x] 4 × Arista cEOS nodes
- [x] 2 × MikroTik CHR nodes
- [x] 1 × Juniper JunOS node
- [x] 1 x Aruba AOS-CX node
- [x] OSPF multi-area, EIGRP, BGP
- [x] Device credentials stored in **Vault**
- [x] Network inventory and state in **NetBox**

## ⬆️ Planned Upgrades
- [ ] New protocols supported

## ♻️ Repository Lifecycle
**New features** are being added periodically (protocols, integrations, optimizations).

**Stay up-to-date**:
- [x] **Watch** and **Star** this repository

## 📄 Disclaimer
You are responsible for defining your own network intent (NetBox config contexts), building your test environment, and meeting the necessary conditions (Python 3.11+, Claude CLI, HashiCorp Vault, etc.).

## 📜 License
Licensed under the [**Business Source License 1.1**](LICENSE).
Source code is available for research, educational, and non-commercial use. Commercial use, SaaS deployment, enterprise integration, or paid services require a commercial license.

## 📧 Collaborations
Interested in collaborating?
- **Email:**
  - Reach out at [**hello@ainoc.dev**](mailto:hello@ainoc.dev)
- **LinkedIn:**
  - Let's discuss via [**LinkedIn**](https://www.linkedin.com/in/tmihaicatalin/)
