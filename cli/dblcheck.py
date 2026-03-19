#!/usr/bin/env python3
"""dblCheck — validate live network state against network intent.

Usage:
    python cli/dblcheck.py                          # full validation
    python cli/dblcheck.py --no-diagnose            # skip AI diagnosis on failures

Exit codes:
    0  All assertions passed
    1  Argument error (no assertions match filters)
    2  One or more assertions failed
"""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Project root (two levels up from cli/dblcheck.py) ─────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import logging

from core.logging_config import setup_logging
setup_logging()
log = logging.getLogger("dblcheck.cli")

from validation.assertions import AssertionResult
from validation.derivation import derive_assertions
from validation.evaluator  import evaluate
from validation.report     import format_text, format_run_dict
# collector transitively imports core.inventory/netbox/vault/settings at module
# scope; suppress the resulting INFO logs (startup banner shows the same info).
logging.getLogger("dblcheck").setLevel(logging.WARNING)
from validation.collector  import collect_state
logging.getLogger("dblcheck").setLevel(logging.INFO)

# ── Data directory paths ──────────────────────────────────────────────────────
PROJECT_DIR  = _PROJECT_ROOT
DATA_DIR     = PROJECT_DIR / "data"
RUNS_DIR     = DATA_DIR / "runs"
SESSIONS_DIR = DATA_DIR / "sessions"
STATE_FILE   = DATA_DIR / "dashboard_state.json"
LOCK_FILE    = DATA_DIR / ".lock"

# Keep at most this many run/session files; delete oldest on each run.
MAX_RETAINED = 100

# ── Color + box-drawing helpers ───────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    """Wrap text in ANSI escape code, only when stdout is a TTY."""
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

_SEP = "─" * 60

# Box-drawing — total line width 62 (2-space indent + 60-char box)
_BW = 60  # box width: ┌ to ┐


def _box_top(label: str = "") -> str:
    inner = _BW - 2  # 58 chars between corners
    if label:
        fill = inner - len(label) - 3  # '─ ' + label + ' '
        return f"  ┌─ {label} {'─' * fill}┐"
    return f"  ┌{'─' * inner}┐"


def _box_row(text: str) -> str:
    inner = _BW - 2  # 58 chars between borders
    return f"  │  {text:<{inner - 2}}│"


def _box_bot() -> str:
    return f"  └{'─' * (_BW - 2)}┘"


def load_intent() -> dict:
    """Load network intent from NetBox config contexts."""
    try:
        from core.netbox import load_intent as _netbox_intent
        intent = _netbox_intent()
        if intent:
            return intent
    except Exception as exc:
        log.warning("Intent loading failed: %s", exc)
    print(
        "Error: Intent not available — NetBox unreachable or no config contexts found.",
        file=sys.stderr,
    )
    sys.exit(1)


def _ensure_data_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _write_state(state: dict) -> None:
    """Atomically write dashboard_state.json."""
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state))
    tmp.rename(STATE_FILE)


def _cleanup_old_files() -> None:
    """Delete oldest run and session files beyond MAX_RETAINED."""
    for directory in (RUNS_DIR, SESSIONS_DIR):
        if not directory.exists():
            continue
        files = sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime)
        for old in files[:-MAX_RETAINED]:
            old.unlink(missing_ok=True)


INCIDENT_FILE = DATA_DIR / "incident.json"


def _failure_fingerprint(failures: list) -> str:
    """Stable hash of a failure set — used to detect when failures change between runs.

    Hashes failure identity (device, type, expected) only — not actual values.
    Actual values can fluctuate for stuck protocol states (e.g. EXSTART ↔ EXCHANGE)
    without the root cause changing, which would otherwise cause redundant re-diagnosis.
    """
    items = sorted(
        (r.assertion.device, r.assertion.type.value, str(r.assertion.expected))
        for r in failures
    )
    return hashlib.sha256(str(items).encode()).hexdigest()


def _safe(value) -> str:
    """Sanitize a value before embedding in the agent prompt.

    Strips non-printable control characters (except spaces/tabs/newlines)
    and truncates to a reasonable length to limit prompt injection surface.
    """
    s = str(value) if value is not None else ""
    s = "".join(c for c in s if c >= " " or c in "\t\n")
    return s[:500]


def _extract_diagnosis_text(session_path: Path) -> str:
    """Extract the agent's diagnosis text from a completed session NDJSON file."""
    parts = []
    try:
        for line in session_path.read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "stream_event":
                continue
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    parts.append(delta.get("text", ""))
    except OSError:
        pass
    text = "".join(parts).strip()
    # Strip agent narration before the first finding heading (but not if already clean)
    if not text.startswith("## "):
        heading_pos = text.find("\n## ")
        if heading_pos != -1:
            text = text[heading_pos + 1:]
    return text


async def _handle_incident(failures: list, fingerprint: str,
                            diagnosis_text: str) -> None:
    """Create or update the Jira incident ticket for the current failure set."""
    from core import jira_client

    prev = {}
    if INCIDENT_FILE.exists():
        try:
            prev = json.loads(INCIDENT_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            pass

    device_list = ", ".join(sorted({r.assertion.device for r in failures}))
    summary = f"dblCheck: {len(failures)} assertion failure{'s' if len(failures) != 1 else ''} — {device_list}"

    existing_key = prev.get("jira_issue_key")

    if not existing_key:
        issue_key = await jira_client.create_issue(summary=summary, description=diagnosis_text)
        if not issue_key and jira_client._is_configured():
            log.error("Jira ticket creation failed — will retry on next run")
            return
    else:
        comment = f"Failure set changed ({len(failures)} failure{'s' if len(failures) != 1 else ''}). Updated diagnosis:\n\n{diagnosis_text}"
        await jira_client.add_comment(existing_key, comment)
        issue_key = existing_key

    incident = {
        "fingerprint":    fingerprint,
        "jira_issue_key": issue_key,
        "diagnosed_at":   datetime.now(timezone.utc).isoformat(),
    }
    tmp = INCIDENT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(incident, indent=2))
    tmp.rename(INCIDENT_FILE)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="validate",
        description="dblCheck: validate live network state against network intent",
    )
    p.add_argument(
        "--no-diagnose", action="store_true",
        help="Skip AI-assisted diagnosis of failures",
    )
    p.add_argument(
        "--headless", action="store_true",
        help="Suppress terminal output; write results to data/ only (daemon mode)",
    )
    return p


async def _run(args) -> int:
    from core.settings import USERNAME, PASSWORD
    from core.inventory import devices, inventory_source
    from core.vault import credential_source

    if not USERNAME or not PASSWORD:
        if not args.headless:
            print(
                "Error: Router credentials not configured.\n"
                "Store them in Vault (dblcheck/router) or set ROUTER_USERNAME "
                "and ROUTER_PASSWORD in .env.",
                file=sys.stderr,
            )
        return 1

    if not devices:
        if not args.headless:
            print(
                "Error: No device inventory available.\n"
                "Set NETBOX_URL in .env and store the NetBox token in Vault (dblcheck/netbox).",
                file=sys.stderr,
            )
        return 1

    # ── Startup banner ────────────────────────────────────────────────────────
    if not args.headless:
        cred_src = credential_source()
        print(_c("2", _box_top("dblCheck")))
        print(_c("2", _box_row(f"Inventory    {len(devices)} devices ({inventory_source})")))
        print(_c("2", _box_row(f"Credentials  {cred_src}")))
        print(_c("2", _box_bot()))
        print()

    _ensure_data_dirs()
    _cleanup_old_files()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_name = f"run-{ts}"
    run_file = RUNS_DIR / f"{run_name}.json"

    # Acquire exclusive lock — prevent concurrent runs (daemon + manual overlap)
    lock_fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as e:
        lock_fh.close()
        if isinstance(e, BlockingIOError):
            if not args.headless:
                print("Another validate.py run is in progress — skipping.", file=sys.stderr)
        else:
            if not args.headless:
                print(f"Failed to acquire run lock: {e}", file=sys.stderr)
        return 1

    try:
        try:
            existing = json.loads(STATE_FILE.read_text())
        except Exception:
            existing = {}
        _write_state({
            "state": "validating",
            "run_name": run_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in existing.items()
               if k in ("last_run", "last_run_file")},
        })

        logging.getLogger("dblcheck").setLevel(logging.WARNING)
        intent = load_intent()
        logging.getLogger("dblcheck").setLevel(logging.INFO)
        assertions = derive_assertions(intent)

        if not assertions:
            if not args.headless:
                print("No assertions derived from intent.", file=sys.stderr)
            # Preserve last_run metadata so dashboard late-joiners still see previous results
            try:
                existing = json.loads(STATE_FILE.read_text())
            except Exception:
                existing = {}
            _write_state({
                "state": "idle",
                **{k: v for k, v in existing.items()
                   if k in ("last_run", "last_run_file")},
            })
            return 1

        t0 = time.monotonic()
        state = await collect_state(assertions)
        duration = time.monotonic() - t0

        results = evaluate(assertions, state)

        # Persist run result file
        run_dict = format_run_dict(results, duration)
        run_file.write_text(json.dumps(run_dict, indent=2))

        # Terminal output (unless headless)
        if not args.headless:
            print(format_text(results, duration, color=_USE_COLOR))

        failures = [r for r in results if r.result == AssertionResult.FAIL]

        # ── Fingerprint — skip diagnosis when failure set is unchanged ─────────
        prev_incident: dict = {}
        if INCIDENT_FILE.exists():
            try:
                prev_incident = json.loads(INCIDENT_FILE.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        last_session_file = None
        diagnosis_skipped = False
        if failures and not args.no_diagnose:
            fingerprint = _failure_fingerprint(failures)
            from core import jira_client as _jc
            fingerprint_match = fingerprint == prev_incident.get("fingerprint")
            jira_pending = (not prev_incident.get("jira_issue_key")
                            and _jc._is_configured())

            if fingerprint_match and not jira_pending:
                diagnosis_skipped = True
                log.info("Failures unchanged (fingerprint match) — skipping diagnosis")
                if not args.headless:
                    print(_c("2", "  Failures unchanged since last run — diagnosis skipped."))
            else:
                session_name = f"session-{ts}"
                session_file = SESSIONS_DIR / f"{session_name}.ndjson"
                last_session_file = session_file
                _write_state({
                    "state": "diagnosing",
                    "run_name": run_name,
                    "run_file": str(run_file),
                    "session_file": str(session_file),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "summary": run_dict["summary"],
                })
                await asyncio.to_thread(_diagnose, failures, session_file,
                                         headless=args.headless)
                diagnosis_text = _extract_diagnosis_text(session_file)
                if diagnosis_text:
                    await _handle_incident(failures, fingerprint, diagnosis_text)
                else:
                    log.warning("Diagnosis produced no text — skipping incident handling")

        elif not failures and prev_incident.get("jira_issue_key"):
            # All assertions pass — resolve the ticket and clear incident state
            from core import jira_client
            ts_now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
            await jira_client.resolve_issue(
                prev_incident["jira_issue_key"],
                f"✅ All dblCheck assertions now pass. Failures resolved at {ts_now}.",
            )
            INCIDENT_FILE.unlink(missing_ok=True)

        idle_state = {
            "state": "idle",
            "last_run": run_name,
            "last_run_file": str(run_file),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if last_session_file:
            idle_state["session_file"] = str(last_session_file)
        if diagnosis_skipped:
            idle_state["diagnosis_skipped"] = True
            jira_key = prev_incident.get("jira_issue_key")
            if jira_key:
                idle_state["jira_issue_key"] = jira_key
            jira_base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
            if jira_base_url:
                idle_state["jira_base_url"] = jira_base_url
        _write_state(idle_state)

        return 0 if not failures else 2

    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


def _format_tool_call(name: str, input_obj: dict) -> str:
    """Format a tool call line: [tool → DEVICE] detail"""
    # FastMCP wraps tool params under a "params" key
    params = input_obj.get("params", input_obj)
    device = params.get("device", "")

    # Extract the most meaningful secondary parameter per tool
    secondary_keys = {
        "get_ospf":             "query",
        "get_bgp":              "query",
        "get_eigrp":            "query",
        "get_routing_policies": "query",
        "get_routing":          "prefix",
        "run_show":             "command",
    }
    detail = ""
    if name in secondary_keys:
        val = params.get(secondary_keys[name], "")
        if val:
            val = str(val)
            detail = f"  {val[:60]}{'…' if len(val) > 60 else ''}"

    if device:
        label = f"[{name} → {device}]"
    else:
        label = f"[{name}]"

    return f"  {_c('36', label)}{_c('2', detail)}"


def _diagnose(failures: list, session_path: Path, headless: bool = False) -> None:
    """Invoke Claude to investigate failures and explain root causes.

    Dual-output: raw stream-json lines written to session_path (for dashboard),
    and parsed text/tool events printed to CLI (unless headless).
    """
    failure_lines = "\n".join(
        f"- [{r.assertion.device}] {r.assertion.description}\n"
        f"  Expected: {_safe(r.assertion.expected)}  Actual: {_safe(r.actual)}"
        for r in failures
    )

    output_instructions = (
        "Format your output using Markdown. "
        "Use a `##` heading for each failure that includes the number and a short description of the device and what failed "
        "(e.g. `## Failure 1 — C1C OSPF neighbor missing on GigabitEthernet2`). "
        "Use **bold** for labels like **Root cause:** and **Evidence:**. "
        "Use `inline code` for interface names, IP addresses, and timer values. "
        "Use code blocks for raw device output excerpts."
    )

    prompt = (
        "The following dblCheck assertions FAILED on the live network:\n\n"
        f"{failure_lines}\n\n"
        "Investigate each failure using the available tools. "
        "For each one, explain the root cause and the evidence that supports it. "
        "Do not suggest configuration changes.\n\n"
        f"{output_instructions}\n\n"
        "Do not output any text before your findings — no planning, no narration, no preamble. "
        "Your first text output must be a finding, not a description of what you are about to do."
    )

    if not headless:
        print()
        print(_c("1", _box_top("AI Diagnosis")))
        print(_c("1", _box_row("Investigating failures...")))
        print(_c("1", _box_bot()))
        print()

    try:
        from core.vault import get_secret
        env = os.environ.copy()
        api_key = get_secret("dblcheck/anthropic", "api_key", quiet=True)
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key

        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise FileNotFoundError("claude")

        proc = subprocess.Popen(
            [claude_bin, "-p", prompt,
             "--verbose",
             "--output-format", "stream-json",
             "--include-partial-messages"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            # New process group so killpg() kills claude + all MCP child processes.
            # Without this, grandchildren keep the stdout pipe open after proc.kill(),
            # causing the stdout read loop to hang indefinitely.
            preexec_fn=os.setsid,
        )

        timed_out = threading.Event()

        def _kill_after_timeout() -> None:
            timed_out.set()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                try:
                    proc.kill()
                except OSError:
                    pass

        timer = threading.Timer(300, _kill_after_timeout)
        timer.daemon = True
        timer.start()

        # Buffer for assembling tool input JSON across content_block_delta chunks
        _tool_bufs: dict[int, dict] = {}  # {index: {name, json_buf}}
        _findings_started = False
        _text_buf = ""

        def _print_line(ln: str) -> None:
            stripped = ln.strip()
            if stripped and all(c == "`" for c in stripped):
                return  # skip bare backtick fence lines
            # Strip Markdown syntax for clean terminal display
            ln = re.sub(r"^#{1,3}\s+", "", ln)      # ## heading → heading text
            ln = ln.replace("**", "")                # **bold** → bold
            ln = re.sub(r"`([^`]+)`", r"\1", ln)     # `code` → code
            if stripped.startswith("---") and stripped.endswith("---") and len(stripped) > 6:
                print(_c("1", ln), flush=True)
            else:
                print(ln, flush=True)

        try:
            with open(session_path, "w", buffering=1) as session_fh:
                for line in proc.stdout:
                    session_fh.write(line)

                    if headless:
                        continue

                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        event = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "stream_event":
                        continue

                    inner = event.get("event", {})
                    inner_type = inner.get("type", "")
                    idx = inner.get("index", -1)

                    if inner_type == "content_block_start":
                        block = inner.get("content_block", {})
                        if block.get("type") == "tool_use":
                            raw_name = block.get("name", "")
                            if raw_name.startswith("mcp__dblcheck__"):
                                name = raw_name.replace("mcp__dblcheck__", "")
                                _tool_bufs[idx] = {"name": name, "json_buf": ""}

                    elif inner_type == "content_block_delta":
                        delta = inner.get("delta", {})
                        if delta.get("type") == "input_json_delta":
                            if idx in _tool_bufs:
                                _tool_bufs[idx]["json_buf"] += delta.get("partial_json", "")
                        elif delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                if not _findings_started:
                                    _findings_started = True
                                    print()
                                    print(_c("1", _box_top("Findings")))
                                    print(_c("1", _box_bot()))
                                    print()
                                _text_buf += text
                                while "\n" in _text_buf:
                                    ln, _text_buf = _text_buf.split("\n", 1)
                                    _print_line(ln)

                    elif inner_type == "content_block_stop":
                        if idx in _tool_bufs:
                            entry = _tool_bufs.pop(idx)
                            try:
                                input_obj = json.loads(entry["json_buf"]) if entry["json_buf"] else {}
                            except json.JSONDecodeError:
                                input_obj = {}
                            if not _findings_started:
                                print(_format_tool_call(entry["name"], input_obj), flush=True)

                if not headless and _text_buf:
                    _print_line(_text_buf)

        finally:
            timer.cancel()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    log.warning("subprocess did not exit after SIGKILL — possible kernel hang")

        if not headless:
            print()
            print(_c("2", "  " + "─" * (_BW - 2)))
            if timed_out.is_set():
                print("\nWarning: AI diagnosis timed out after 5 minutes.", file=sys.stderr)

    except FileNotFoundError:
        log.warning("'claude' CLI not found — skipping AI diagnosis.")
        if not headless:
            print(
                "Warning: 'claude' CLI not found. "
                "Install Claude Code to enable AI diagnosis.",
                file=sys.stderr,
            )


def main() -> None:
    args = _build_parser().parse_args()
    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
