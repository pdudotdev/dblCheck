#!/usr/bin/env bash
# dblCheck Test Runner
# Runs all test suites with stable IDs and tracks pass/fail per file.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Locate Python / pytest from project venv if available
if [[ -x "$PROJECT_ROOT/dbl/bin/python" ]]; then
    PYTHON="$PROJECT_ROOT/dbl/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

PYTEST="$PYTHON -m pytest"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
RESET='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
declare -a FAILED_SUITES=()

run_suite() {
    local suite_id="$1"
    local suite_file="$2"
    local suite_name="$3"

    printf "  %-8s  %-55s  " "$suite_id" "$suite_name"

    local output
    if output=$(cd "$PROJECT_ROOT" && $PYTEST "$suite_file" -v --tb=short -q 2>&1); then
        printf "${GREEN}PASS${RESET}\n"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        printf "${RED}FAIL${RESET}\n"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAILED_SUITES+=("$suite_id: $suite_name")
        # Print first failure detail
        echo "$output" | grep -A 5 "FAILED\|ERROR\|assert" | head -20 | sed 's/^/    /'
    fi
}

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  dblCheck Test Suite"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "  Suite     File / Name                                       Status"
echo "  ────────  ─────────────────────────────────────────────────  ──────"

# ── Unit Tests ────────────────────────────────────────────────────────────────
run_suite "UT-001" "testing/unit/test_normalizers_interfaces.py" "Interface normalizers (6 vendors)"
run_suite "UT-002" "testing/unit/test_normalizers_ospf.py"        "OSPF normalizers + helpers"
run_suite "UT-003" "testing/unit/test_normalizers_bgp.py"         "BGP summary normalizers"
run_suite "UT-004" "testing/unit/test_normalizers_eigrp.py"       "EIGRP neighbor normalizer"
run_suite "UT-005" "testing/unit/test_derivation.py"              "Assertion derivation"
run_suite "UT-006" "testing/unit/test_evaluator.py"               "Evaluator (all 7 types)"
run_suite "UT-007" "testing/unit/test_input_models.py"            "Pydantic input models"
run_suite "UT-008" "testing/unit/test_platform_map.py"            "PLATFORM_MAP structure"
run_suite "UT-009" "testing/unit/test_collector.py"               "Collector query planner"
run_suite "UT-010" "testing/unit/test_report.py"                  "Report formatting"
run_suite "UT-011" "testing/unit/test_tool_layer.py"              "Tool layer (known/unknown)"
run_suite "UT-012" "testing/unit/test_helpers.py"                 "Helper functions"

# ── Integration Tests ─────────────────────────────────────────────────────────
run_suite "IT-001" "testing/integration/test_platform_coverage.py" "Platform coverage report"
run_suite "IT-002" "testing/integration/test_end_to_end.py"         "End-to-end pipeline"

# ── Summary ───────────────────────────────────────────────────────────────────
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo "  ────────────────────────────────────────────────────────────"
printf "  Suites: %d total  |  ${GREEN}%d passed${RESET}  |  " "$TOTAL" "$PASS_COUNT"

if [[ $FAIL_COUNT -gt 0 ]]; then
    printf "${RED}%d failed${RESET}\n" "$FAIL_COUNT"
else
    printf "${GREEN}%d failed${RESET}\n" "$FAIL_COUNT"
fi
echo ""

if [[ ${#FAILED_SUITES[@]} -gt 0 ]]; then
    echo "  Failed suites:"
    for s in "${FAILED_SUITES[@]}"; do
        printf "    ${RED}✗${RESET}  %s\n" "$s"
    done
    echo ""
fi

if [[ $FAIL_COUNT -eq 0 ]]; then
    printf "  ${GREEN}All $TOTAL suites passed.${RESET}\n"
    echo ""
    # Show platform_coverage_results.md was generated
    if [[ -f "$PROJECT_ROOT/testing/integration/platform_coverage_results.md" ]]; then
        echo "  Coverage report: testing/integration/platform_coverage_results.md"
    fi
    echo ""
    exit 0
else
    exit 1
fi
