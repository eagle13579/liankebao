#!/bin/bash
# ============================================================
# 链客宝 — 全测试运行器
# LianKeBao — All Tests Runner
#
# Runs all test suites that don't require the circular import
# chain. Reports pass/fail for each suite with timing.
#
# Usage:
#   ./tests/run_all.sh                  # Run all test suites
#   ./tests/run_all.sh --verbose        # Verbose output (-v)
#   ./tests/run_all.sh --coverage       # With coverage report
#   ./tests/run_all.sh --list           # List available test suites
#   ./tests/run_all.sh --quick          # Quick mode (smoke only)
#   ./tests/run_all.sh --ci             # CI mode (JUnit XML output)
#
# Exit codes:
#   0   All tests passed
#   1   Some tests failed
#   2   No test files found
#   3   Prerequisites not met
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Timestamp ─────────────────────────────────────────────────────
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# ── Config ────────────────────────────────────────────────────────
VERBOSE=""
COVERAGE=false
CI_MODE=false
QUICK_MODE=false
LIST_ONLY=false
PYTHON="${PYTHON:-python}"
REPORT_DIR="${REPORT_DIR:-$PROJECT_DIR/test-reports}"
FAILURES=0
TOTAL=0
PASSED=0
START_TIME=""

# ── Parse args ───────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --verbose|-v)       VERBOSE="-v" ;;
        --coverage)         COVERAGE=true ;;
        --ci)               CI_MODE=true; REPORT_DIR="${REPORT_DIR}" ;;
        --quick)            QUICK_MODE=true ;;
        --list)             LIST_ONLY=true ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --verbose, -v   Verbose output"
            echo "  --coverage      With coverage report"
            echo "  --ci            CI mode (JUnit XML output)"
            echo "  --quick         Quick mode (smoke tests only)"
            echo "  --list          List available test suites"
            echo "  --help, -h      Show this help"
            exit 0
            ;;
    esac
done

# ── Ensure INFRA_PHASE is set ─────────────────────────────────────
export INFRA_PHASE="${INFRA_PHASE:-0}"

# ── Helper functions ──────────────────────────────────────────────
info()     { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()       { echo -e "${GREEN}[PASS]${NC} $*"; }
fail()     { echo -e "${RED}[FAIL]${NC} $*"; }
warn()     { echo -e "${YELLOW}[WARN]${NC} $*"; }
header()   { echo -e "\n${CYAN}════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"; }
subheader(){ echo -e "\n${BOLD}─── $* ───${NC}"; }

# ── Define test suites ────────────────────────────────────────────
declare -A TEST_SUITES
TEST_SUITES["smoke-test-new-arch"]="tests/smoke_test_new_arch.py"
TEST_SUITES["legion-employee"]="tests/test_legion_employee.py"
TEST_SUITES["phase1-adapters"]="tests/test_phase1_adapters.py"
TEST_SUITES["all-agents"]="tests/test_all_agents.py"
TEST_SUITES["agent-runtime"]="tests/test_agent_runtime.py"
TEST_SUITES["crm-module"]="tests/test_crm_module.py"
TEST_SUITES["gaia-7rules"]="tests/test_gaia_7rules.py"

# Quick mode test suites
declare -A QUICK_SUITES
QUICK_SUITES["smoke-test-new-arch"]="tests/smoke_test_new_arch.py"
QUICK_SUITES["legion-employee"]="tests/test_legion_employee.py"

# ── Pre-flight checks ────────────────────────────────────────────
preflight_checks() {
    header "🔎 前置检查"

    # Python
    if ! command -v "$PYTHON" &>/dev/null; then
        error "Python not found: $PYTHON"
        exit 3
    fi
    py_ver="$($PYTHON --version 2>&1)"
    ok "Python: $py_ver"

    # Pytest
    if ! $PYTHON -c "import pytest" &>/dev/null; then
        error "pytest not installed"
        exit 3
    fi
    ok "pytest: $($PYTHON -m pytest --version 2>&1)"

    # Check test directory
    if [ ! -d "$PROJECT_DIR/tests" ]; then
        error "tests/ directory not found"
        exit 3
    fi
    ok "tests/ directory exists"

    # Coverage
    if $COVERAGE; then
        if ! $PYTHON -c "import coverage" &>/dev/null 2>&1; then
            warn "coverage not installed — disabling coverage report"
            COVERAGE=false
        else
            ok "coverage available"
        fi
    fi

    # Create report directory for CI
    if $CI_MODE; then
        mkdir -p "$REPORT_DIR"
        ok "CI report directory: $REPORT_DIR"
    fi

    echo ""
}

# ── List test suites ──────────────────────────────────────────────
list_suites() {
    header "📋 可用测试套件"
    if $QUICK_MODE; then
        echo -e "${YELLOW}Quick mode — 仅运行快速测试:${NC}"
        for name in "${!QUICK_SUITES[@]}"; do
            echo "  • $name  → ${QUICK_SUITES[$name]}"
        done
    else
        for name in "${!TEST_SUITES[@]}"; do
            file="${TEST_SUITES[$name]}"
            if [ -f "$PROJECT_DIR/$file" ]; then
                echo -e "  ${GREEN}✓${NC} $name  → $file"
            else
                echo -e "  ${RED}✗${NC} $name  → $file ${RED}(not found)${NC}"
            fi
        done
    fi
    echo ""
}

# ── Run a single test suite ───────────────────────────────────────
run_suite() {
    local name="$1"
    local file="$2"
    local suite_start
    local suite_end
    local duration
    local exit_code=0

    suite_start="$(date +%s%N)"
    TOTAL=$((TOTAL + 1))

    subheader "Running: $name ($file)"

    if [ ! -f "$PROJECT_DIR/$file" ]; then
        fail "Test file not found: $file"
        FAILURES=$((FAILURES + 1))
        return 1
    fi

    # Build command
    local cmd="$PYTHON -m pytest"

    if $CI_MODE; then
        local junit_xml="$REPORT_DIR/${name}.xml"
        cmd="$cmd --junitxml=$junit_xml"
    fi

    if [ -n "$VERBOSE" ]; then
        cmd="$cmd $VERBOSE"
    fi

    # Color mode
    if [ -t 1 ]; then
        cmd="$cmd --color=yes"
    fi

    cmd="$cmd $file"

    # Run the test
    echo "  $cmd"
    echo ""

    if $COVERAGE; then
        # Run with coverage
        $PYTHON -m coverage run --source=app --omit="*/tests/*" -m pytest "$file" ${VERBOSE:-} --color=yes 2>&1 | sed 's/^/    /' || exit_code=$?
    else
        # Run normally
        $PYTHON -m pytest "$file" ${VERBOSE:-} --color=yes 2>&1 | sed 's/^/    /' || exit_code=$?
    fi

    suite_end="$(date +%s%N)"
    duration="$(( (suite_end - suite_start) / 1000000 ))"

    if [ "$exit_code" -eq 0 ]; then
        ok "$name passed (${duration}ms)"
        PASSED=$((PASSED + 1))
    else
        fail "$name failed (${duration}ms, exit=$exit_code)"
        FAILURES=$((FAILURES + 1))
    fi

    return $exit_code
}

# ── Coverage report ───────────────────────────────────────────────
generate_coverage() {
    if ! $COVERAGE; then
        return
    fi

    header "📊 覆盖率报告"

    $PYTHON -m coverage report --skip-covered --sort=-cover 2>&1 || {
        warn "Coverage report generation failed"
    }

    echo ""
    info "生成 HTML 覆盖率报告..."
    $PYTHON -m coverage html -d "$REPORT_DIR/coverage" 2>/dev/null && {
        ok "HTML 报告: $REPORT_DIR/coverage/index.html"
    }
}

# ── Summary ───────────────────────────────────────────────────────
print_summary() {
    local end_time
    local total_duration
    end_time="$(date +%s%N)"
    total_duration="$(( (end_time - START_TIME) / 1000000 ))"
    local score=0
    if [ "$TOTAL" -gt 0 ]; then
        score="$(( PASSED * 100 / TOTAL ))"
    fi

    header "📋 测试汇总"

    echo -e "  ${BOLD}Timestamp:${NC}      $TIMESTAMP"
    echo -e "  ${BOLD}Duration:${NC}       ${total_duration}ms"
    echo -e "  ${BOLD}INFRA_PHASE:${NC}    ${INFRA_PHASE:-0}"
    echo -e "  ${BOLD}Python:${NC}         $($PYTHON --version 2>&1)"
    echo ""
    echo -e "  ${BOLD}结果:${NC}"
    echo -e "    ${GREEN}通过:${NC}  $PASSED"
    echo -e "    ${RED}失败:${NC}  $FAILURES"
    echo -e "    总计: $TOTAL"
    echo -e "    得分: ${score}%"
    echo ""

    if [ "$FAILURES" -eq 0 ]; then
        echo -e "  ${GREEN}${BOLD}🎉 全部测试通过！${NC}"
        if $CI_MODE; then
            echo -e "  ${GREEN}JUnit XML: $REPORT_DIR/*.xml${NC}"
        fi
        echo ""
        return 0
    else
        echo -e "  ${RED}${BOLD}❌ ${FAILURES} 个测试套件未通过${NC}"
        echo ""
        return 1
    fi
}

# ==================================================================
# Main
# ==================================================================
main() {
    START_TIME="$(date +%s%N)"

    echo ""
    echo -e "${CYAN}${BOLD}  🧪 链客宝 — 全测试运行器"
    echo -e "  ${CYAN}${BOLD}  LianKeBao — All Tests Runner${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
    echo "  INFRA_PHASE=${INFRA_PHASE:-0} | ${TIMESTAMP}"
    echo ""

    preflight_checks

    if $LIST_ONLY; then
        list_suites
        exit 0
    fi

    if $QUICK_MODE; then
        header "⚡ 快速模式 — 仅运行关键测试"
        for name in "${!QUICK_SUITES[@]}"; do
            run_suite "$name" "${QUICK_SUITES[$name]}"
        done
    else
        header "🧪 全测试套件"

        # Phase 1 — Core infrastructure (must be independent)
        header "┌─ Phase 1: 核心基础设施"
        run_suite "smoke-test-new-arch" "tests/smoke_test_new_arch.py"

        # Phase 2 — Legacy employee + agent tests
        header "┌─ Phase 2: Legion Employee & Agents"

        # Run these with INFRA_PHASE=0 (in-memory) for isolation
        INFRA_PHASE=0 run_suite "legion-employee" "tests/test_legion_employee.py"
        INFRA_PHASE=0 run_suite "phase1-adapters" "tests/test_phase1_adapters.py"
        INFRA_PHASE=0 run_suite "all-agents" "tests/test_all_agents.py"
        INFRA_PHASE=0 run_suite "agent-runtime" "tests/test_agent_runtime.py"

        # Phase 3 — Domain logic
        header "┌─ Phase 3: 领域逻辑"
        run_suite "crm-module" "tests/test_crm_module.py"
        run_suite "gaia-7rules" "tests/test_gaia_7rules.py"

        # Re-run key tests with INFRA_PHASE=1 if available
        if [ "$INFRA_PHASE" = "1" ] || [ -n "${REDIS_HOST:-}" ]; then
            header "┌─ Phase 1 集成测试 (INFRA_PHASE=1)"
            INFRA_PHASE=1 run_suite "legion-employee-phase1" "tests/test_legion_employee.py"
        fi
    fi

    echo ""

    if $COVERAGE; then
        generate_coverage
    fi

    if print_summary; then
        exit 0
    else
        exit 1
    fi
}

main "$@"
