# Agent Invocation

Documents how `cli/dblcheck.py` assembles the diagnosis prompt and invokes the Claude agent when validation failures are found. Source of truth: `_diagnose()` in `cli/dblcheck.py`.

---

## Overview

When dblCheck finds assertion failures and `--no-diagnose` is not set, it invokes the `claude` CLI non-interactively with a formatted failure report. The agent investigates each failure using the 8 MCP tools against live devices and produces a root-cause analysis.

Behavioral instructions come from `CLAUDE.md`, which Claude Code auto-loads from the project root. The diagnosis prompt only carries failure context — no behavioral instructions are repeated in the prompt itself.

---

## CLI Invocation

```
claude -p "<assembled-prompt>" \
  --verbose \
  --output-format stream-json \
  --include-partial-messages
```

Launched as a subprocess via `subprocess.Popen` with `preexec_fn=os.setsid` (new process group) so `os.killpg()` terminates Claude plus all MCP child processes when the timeout fires.

| Flag | Purpose |
|------|---------|
| `-p` | Print mode — non-interactive, exits autonomously after completing the task |
| `--verbose` | Emits tool call events in addition to text output |
| `--output-format stream-json` | Produces NDJSON event stream; each line is a JSON object |
| `--include-partial-messages` | Emits streaming content deltas as they arrive (enables real-time display) |

The `ANTHROPIC_API_KEY` is loaded from Vault (`dblcheck/anthropic`) and injected into the subprocess environment. If Vault is unavailable the key falls back to the environment variable of the same name.

---

## Prompt Structure

The prompt is assembled in `_diagnose()` from three parts:

### Part 1 — Failure list (always present)

```
The following dblCheck assertions FAILED on the live network:

- [DEVICE] <assertion description>
  Expected: <expected value>  Actual: <actual value>
- [DEVICE] <assertion description>
  Expected: <expected value>  Actual: <actual value>
...
```

Each failure comes from an `EvaluatedAssertion` object. Expected and actual values are sanitized before embedding:
- Control characters stripped (preserves tabs and newlines, removes everything below ASCII 0x20)
- Truncated to 500 characters per value

### Part 2 — Investigation instruction (always present)

```
Investigate each failure using the available tools.
For each one, explain the root cause and the evidence that supports it.
Do not suggest configuration changes.
```

### Part 3 — Output format instruction (mode-dependent)

**Interactive mode** (default): plain text for terminal — no markdown, no asterisks, no tables. Labels like `Root cause:` and `Evidence:`. Continuation lines indented 2 spaces.

**Headless mode** (`--headless`): Markdown format with `##` headings per failure, `**bold**` labels, inline code for interface names and IPs, code blocks for raw device output excerpts.

### Part 4 — Anti-preamble instruction (always present)

```
Do not output any text before your findings — no planning, no narration, no preamble.
Your first text output must be a finding, not a description of what you are about to do.
```

---

## Agent Timeout

A `threading.Timer` fires after **300 seconds** (5 minutes). On expiry:
1. `timed_out` event is set
2. `os.killpg(proc.pid, SIGKILL)` kills the entire process group (Claude + all MCP child processes)

If the timer fires, the partial output collected so far is still written to the session file and displayed. The run is marked as timed out in the dashboard state.

---

## Output Handling

The subprocess stdout is an NDJSON stream. Each line is a JSON event object. dblCheck handles two modes:

**Interactive mode**: Events are parsed in real-time. `content_block_delta` events with text deltas are printed to the terminal as they arrive. Tool call events (`content_block_start` with `tool_use` type) print a summary line showing the tool name and target device. The full stream is simultaneously written to the session file (`data/.session-<ts>.ndjson`) for the dashboard.

**Headless mode**: All events are written to the session file only. No terminal output. The dashboard reads the file via its WebSocket bridge.

After the subprocess exits, `_extract_diagnosis_text()` re-reads the session file and extracts all text content into a plain string for Jira comments and the stored run dict.

---

## Fingerprinting

Before invoking the agent, `_failure_fingerprint()` computes a SHA-256 hash of the current failure set:

```python
items = sorted(
    f"{r.assertion.device}:{r.assertion.type.value}:{r.assertion.description}"
    for r in failures
)
digest = hashlib.sha256("\n".join(items).encode()).hexdigest()
```

If the fingerprint matches the previous run's fingerprint (stored in `data/incident.json`), diagnosis is skipped — the failures haven't changed since the last investigation. This prevents re-running the agent on every validation cycle when the network is in a persistent failure state.

---

## Jira Integration

If Jira is configured (`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_PROJECT_KEY` in `.env`), `_handle_incident()` is called after diagnosis:

- **New failure set** (no existing ticket or fingerprint changed): Creates a new Jira issue with the failure list and diagnosis text as the description.
- **Existing ticket, Jira pending** (ticket key exists but comment not yet added): Adds a comment with the diagnosis text.
- **All-pass**: Resolves the open ticket.

The current ticket key and fingerprint are persisted in `data/incident.json` between runs.
