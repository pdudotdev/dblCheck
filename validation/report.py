"""Format validation results as human-readable text or machine-parseable JSON."""
import json
from datetime import datetime, timezone

from validation.assertions import AssertionResult, EvaluatedAssertion

# Terminal width for formatting
_WIDTH = 60
_SEP = "─" * _WIDTH
_DOUBLE_SEP = "═" * _WIDTH


def _colorize(text: str, code: str, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


def format_text(results: list[EvaluatedAssertion], duration_sec: float,
                color: bool = False) -> str:
    """Human-readable terminal report."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = len(results)
    passed = sum(1 for r in results if r.result == AssertionResult.PASS)
    failed = sum(1 for r in results if r.result == AssertionResult.FAIL)
    errors = sum(1 for r in results if r.result == AssertionResult.ERROR)

    sep        = _colorize(_SEP,        "2",   color)
    double_sep = _colorize(_DOUBLE_SEP, "1",   color)

    failed_str = _colorize(str(failed), "1;31", color) if failed else str(failed)
    errors_str = _colorize(str(errors), "1;33", color) if errors else str(errors)

    lines = [
        "",
        double_sep,
        "  dblCheck Validation Report",
        f"  {now}",
        double_sep,
        "",
        f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed_str}  |  Errors: {errors_str}",
        f"  Duration: {duration_sec:.1f}s",
        "",
    ]

    failures = [r for r in results if r.result != AssertionResult.PASS]
    if failures:
        lines += [sep, "  FAILURES AND ERRORS", sep, ""]
        for r in failures:
            if r.result == AssertionResult.FAIL:
                tag = _colorize("[FAIL]", "1;31", color)
            else:
                tag = _colorize("[ERR ]", "1;33", color)
            lines.append(f"  {tag} {r.assertion.description}")
            lines.append(f"         Expected : {r.assertion.expected}")
            if r.actual is not None:
                lines.append(f"         Actual   : {r.actual}")
            if r.detail:
                lines.append(f"         Detail   : {r.detail}")
            lines.append("")
    else:
        lines += [_colorize("  All assertions passed.", "32", color), ""]

    # Per-device summary table
    per_device: dict[str, dict] = {}
    for r in results:
        d = per_device.setdefault(r.assertion.device, {"pass": 0, "fail": 0, "error": 0})
        d[r.result.value] += 1

    lines.append("")
    if per_device:
        nd = max(max(len(d) for d in per_device), 6)  # min 6 = len("Device")
        cd, cn, ce = nd + 2, 8, 9
        cs = max(5, 27 - nd)  # fills total row to 62 chars

        def _tr(dv, ps, fl, er, sf):
            return f"  │ {dv:<{nd}} │  {ps}  │  {fl}  │  {er}  │{sf}│"

        lines.append(f"  ┌{'─'*cd}┬{'─'*cn}┬{'─'*cn}┬{'─'*ce}┬{'─'*cs}┐")
        lines.append(_tr("Device", f"{'Pass':>{cn-4}}", f"{'Fail':>{cn-4}}", f"{'Error':>{ce-4}}", " "*cs))
        lines.append(f"  ├{'─'*cd}┼{'─'*cn}┼{'─'*cn}┼{'─'*ce}┼{'─'*cs}┤")
        for device in sorted(per_device):
            counts = per_device[device]
            bad = counts["fail"] or counts["error"]
            p_s = f"{counts['pass']:>{cn-4}}"
            f_raw = f"{counts['fail']:>{cn-4}}"
            f_s = _colorize(f_raw, "1;31", color) if counts["fail"] else f_raw
            e_raw = f"{counts['error']:>{ce-4}}"
            e_s = _colorize(e_raw, "1;33", color) if counts["error"] else e_raw
            s_cell = ("  " + _colorize("<<<", "31", color) + " " * (cs - 5)) if bad else " " * cs
            lines.append(_tr(device, p_s, f_s, e_s, s_cell))
        lines.append(f"  └{'─'*cd}┴{'─'*cn}┴{'─'*cn}┴{'─'*ce}┴{'─'*cs}┘")

    lines += ["", double_sep, ""]
    return "\n".join(lines)


def format_run_dict(results: list[EvaluatedAssertion], duration_sec: float) -> dict:
    """Build the run result dict for file persistence and JSON output."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = len(results)
    passed = sum(1 for r in results if r.result == AssertionResult.PASS)
    failed = sum(1 for r in results if r.result == AssertionResult.FAIL)
    errors = sum(1 for r in results if r.result == AssertionResult.ERROR)

    per_device: dict[str, dict] = {}
    for r in results:
        d = per_device.setdefault(r.assertion.device, {"pass": 0, "fail": 0, "error": 0})
        d[r.result.value] += 1

    return {
        "timestamp": now,
        "duration_sec": round(duration_sec, 2),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
        },
        "per_device": per_device,
        "assertions": [
            {
                "type": r.assertion.type.value,
                "device": r.assertion.device,
                "description": r.assertion.description,
                "result": r.result.value,
                "expected": r.assertion.expected,
                "actual": r.actual,
                "detail": r.detail or None,
                "protocol": r.assertion.protocol or None,
                "peer": r.assertion.peer or None,
                "interface": r.assertion.interface or None,
                "area": r.assertion.area or None,
            }
            for r in results
        ],
    }


