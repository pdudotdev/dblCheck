"""Format validation results as human-readable text or machine-parseable JSON."""
import json
from datetime import datetime, timezone

from validation.assertions import AssertionResult, EvaluatedAssertion

# Terminal width for formatting
_WIDTH = 60
_SEP = "─" * _WIDTH
_DOUBLE_SEP = "═" * _WIDTH


def format_text(results: list[EvaluatedAssertion], duration_sec: float) -> str:
    """Human-readable terminal report."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = len(results)
    passed = sum(1 for r in results if r.result == AssertionResult.PASS)
    failed = sum(1 for r in results if r.result == AssertionResult.FAIL)
    errors = sum(1 for r in results if r.result == AssertionResult.ERROR)

    lines = [
        "",
        _DOUBLE_SEP,
        "  dblCheck Validation Report",
        f"  {now}",
        _DOUBLE_SEP,
        "",
        f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}  |  Errors: {errors}",
        f"  Duration: {duration_sec:.1f}s",
        "",
    ]

    failures = [r for r in results if r.result != AssertionResult.PASS]
    if failures:
        lines += [_SEP, "  FAILURES AND ERRORS", _SEP, ""]
        for r in failures:
            tag = "FAIL" if r.result == AssertionResult.FAIL else "ERR "
            lines.append(f"  [{tag}] {r.assertion.description}")
            lines.append(f"         Expected : {r.assertion.expected}")
            if r.actual is not None:
                lines.append(f"         Actual   : {r.actual}")
            if r.detail:
                lines.append(f"         Detail   : {r.detail}")
            lines.append("")
    else:
        lines += ["  All assertions passed.", ""]

    # Per-device summary
    lines += [_SEP, "  PER-DEVICE SUMMARY", _SEP, ""]
    per_device: dict[str, dict] = {}
    for r in results:
        d = per_device.setdefault(r.assertion.device, {"pass": 0, "fail": 0, "error": 0})
        d[r.result.value] += 1

    for device in sorted(per_device):
        counts = per_device[device]
        flag = "  <<<" if counts["fail"] or counts["error"] else ""
        lines.append(
            f"  {device:<8}  {counts['pass']} pass  "
            f"{counts['fail']} fail  {counts['error']} error{flag}"
        )

    lines += ["", _DOUBLE_SEP, ""]
    return "\n".join(lines)


def format_json(results: list[EvaluatedAssertion], duration_sec: float) -> str:
    """Machine-parseable JSON report for CI/CD integration."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = len(results)
    passed = sum(1 for r in results if r.result == AssertionResult.PASS)
    failed = sum(1 for r in results if r.result == AssertionResult.FAIL)
    errors = sum(1 for r in results if r.result == AssertionResult.ERROR)

    report = {
        "timestamp": now,
        "duration_sec": round(duration_sec, 2),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
        },
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
    return json.dumps(report, indent=2)
