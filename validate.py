#!/usr/bin/env python3
"""dblCheck — validate live network state against INTENT.json.

Usage:
    python validate.py                          # full validation
    python validate.py --device C1C             # single device
    python validate.py --device C1C --device E1C  # multiple devices
    python validate.py --protocol ospf          # OSPF assertions only
    python validate.py --format json            # JSON output for CI/CD
    python validate.py --no-diagnose            # skip AI diagnosis on failures

Exit codes:
    0  All assertions passed
    1  Argument error (no assertions match filters)
    2  One or more assertions failed
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time

from core.logging_config import setup_logging
setup_logging()

from validation.assertions import AssertionResult
from validation.derivation import derive_assertions
from validation.collector  import collect_state
from validation.evaluator  import evaluate
from validation.report     import format_text, format_json


def load_intent() -> dict:
    """Load INTENT.json. Isolated so future versions can load from NetBox/Git."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "intent", "INTENT.json")
    with open(path) as f:
        return json.load(f)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="validate",
        description="dblCheck: validate live network state against INTENT.json",
    )
    p.add_argument(
        "--device", action="append", default=[],
        metavar="NAME",
        help="Limit to specific device (repeatable, e.g. --device C1C --device E1C)",
    )
    p.add_argument(
        "--protocol", choices=["ospf", "bgp", "interface"],
        help="Limit to a specific protocol category",
    )
    p.add_argument(
        "--format", choices=["text", "json"], default="text",
        dest="output_format",
        help="Output format (default: text)",
    )
    p.add_argument(
        "--no-diagnose", action="store_true",
        help="Skip AI-assisted diagnosis of failures",
    )
    return p


async def _run(args) -> int:
    intent = load_intent()

    device_filter = {d.upper() for d in args.device} if args.device else None

    assertions = derive_assertions(
        intent,
        device_filter=device_filter,
        protocol_filter=args.protocol,
    )

    if not assertions:
        print("No assertions match the given filters.", file=sys.stderr)
        return 1

    t0 = time.monotonic()
    state = await collect_state(assertions)
    duration = time.monotonic() - t0

    results = evaluate(assertions, state)

    if args.output_format == "json":
        print(format_json(results, duration))
    else:
        print(format_text(results, duration))

    failures = [r for r in results if r.result != AssertionResult.PASS]
    if failures and not args.no_diagnose:
        _diagnose(failures)

    return 0 if not failures else 2


def _diagnose(failures: list) -> None:
    """Invoke Claude to investigate failures and explain root causes."""
    failure_lines = "\n".join(
        f"- [{r.assertion.device}] {r.assertion.description}\n"
        f"  Expected: {r.assertion.expected}  Actual: {r.actual}"
        for r in failures
    )

    prompt = (
        "The following dblCheck assertions FAILED on the live network:\n\n"
        f"{failure_lines}\n\n"
        "Investigate each failure using the available tools. "
        "For each one, explain the root cause and the evidence that supports it. "
        "Do not suggest configuration changes.\n\n"
        "Output plain text for a terminal — no markdown, no asterisks, no tables. "
        "Use plain labels like 'Root cause:' and 'Evidence:'. "
        "Indent continuation lines by 2 spaces."
    )

    print("\n" + "─" * 60)
    print("  AI Diagnosis")
    print("─" * 60)
    print("  Investigating...\n")

    try:
        proc = subprocess.Popen(
            ["claude", "-p", prompt,
             "--verbose",
             "--output-format", "stream-json",
             "--include-partial-messages"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Parse stream-json events and print text deltas + tool call progress.
        # Events arrive as: {"type": "stream_event", "event": {"type": "...", ...}}
        timed_out = threading.Event()

        def _kill_after_timeout() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(300, _kill_after_timeout)
        timer.daemon = True
        timer.start()

        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "stream_event":
                    continue
                inner = event.get("event", {})
                inner_type = inner.get("type", "")
                if inner_type == "content_block_start":
                    block = inner.get("content_block", {})
                    if block.get("type") == "tool_use":
                        name = block.get("name", "").replace("mcp__dblcheck__", "")
                        print(f"  [querying: {name}]", flush=True)
                elif inner_type == "content_block_delta":
                    delta = inner.get("delta", {})
                    if delta.get("type") == "text_delta":
                        print(delta.get("text", ""), end="", flush=True)
        finally:
            timer.cancel()
            proc.wait()

        print()  # ensure final newline
        if timed_out.is_set():
            print("\nWarning: AI diagnosis timed out after 5 minutes.", file=sys.stderr)

    except FileNotFoundError:
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
