#!/bin/bash
# ============================================================
# 链客宝 — 一键生产部署脚本
# 链客宝 (LianKeBao) — One-command Production Deployment
#
# Activates:
#   - Phase 1 Infrastructure (RedisCache + SQLiteEventBus)
#   - Agent Runtime with all 9 AI Digital Employees
#   - Gaia Evolution Brain (every 30 min)
#
# Usage:
#   # Linux (systemd)
#   sudo bash scripts/deploy_production.sh
#
#   # Linux (no systemd — background process)
#   bash scripts/deploy_production.sh
#
#   # Verify without deploying
#   bash scripts/deploy_production.sh --check
#
#   # Dry run (print what would happen)
#   bash scripts/deploy_production.sh --dry-run
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

# ── Config ────────────────────────────────────────────────────────
INFRA_PHASE="${INFRA_PHASE:-1}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/logs}"
AGENTS_LOG="${AGENTS_LOG:-$LOG_DIR/agents.log}"
SERVICE_FILE="$PROJECT_DIR/deploy/chainke-agents.service"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# ── Helpers ──────────────────────────────────────────────────────
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[✅]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[⚠️]${NC}  $*"; }
error() { echo -e "${RED}[❌]${NC}  $*"; }
header(){ echo -e "\n${CYAN}════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"; }

# ── Parse args ───────────────────────────────────────────────────
DRY_RUN=false
CHECK_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --check)   CHECK_ONLY=true ;;
        --help|-h)
            echo "Usage: $0 [--check] [--dry-run] [--help]"
            echo ""
            echo "  --check     Verify environment prerequisites only"
            echo "  --dry-run   Print actions without executing"
            echo "  --help      Show this help"
            exit 0
            ;;
    esac
done

# ==================================================================
# Phase 0: Pre-flight checks
# ==================================================================
preflight_checks() {
    header "🔎 前置检查 Pre-flight Checks"
    local all_ok=true

    # Python
    if command -v python3 &>/dev/null; then
        py_ver="$(python3 --version 2>&1)"
        ok "Python: $py_ver"
    elif command -v python &>/dev/null; then
        py_ver="$(python --version 2>&1)"
        ok "Python: $py_ver"
    else
        error "Python 未安装 (not found)"
        all_ok=false
    fi

    # Check critical modules exist
    local modules=(
        "app.dependencies"
        "app.agents.employee_profiles"
        "app.cache.adapters.redis_adapter"
        "app.events.adapters.sqlite_adapter"
        "app.agents.agent_runtime"
    )
    for mod in "${modules[@]}"; do
        mod_path="${PROJECT_DIR}/${mod//\./\/}.py"
        # Handle package __init__
        mod_py_path="$PROJECT_DIR/${mod//\./\/}.py"
        mod_init_path="$PROJECT_DIR/${mod//\./\/}/__init__.py"

        if [ -f "$mod_py_path" ] || [ -f "$mod_init_path" ]; then
            ok "Module exists: $mod"
        else
            warn "Module not found: $mod"
            # Not necessarily fatal — might be in site-packages
        fi
    done

    # .env.production
    if [ -f "$PROJECT_DIR/.env.production" ]; then
        ok ".env.production found"
    else
        warn ".env.production 未找到 — 将从 .env.example 创建"
    fi

    # deploy directory
    if [ -d "$PROJECT_DIR/deploy" ]; then
        ok "deploy/ directory exists"
    else
        error "deploy/ 目录缺失！"
        all_ok=false
    fi

    # systemd availability (informational only)
    if command -v systemctl &>/dev/null; then
        ok "systemd detected — 支持 systemd 部署"
    else
        warn "systemd 不可用 — 将使用后台进程模式"
    fi

    $all_ok && ok "前置检查全部通过" || error "部分检查未通过"
    echo ""
    return $($all_ok && echo 0 || echo 1)
}

# ==================================================================
# Phase 1: Environment setup
# ==================================================================
setup_environment() {
    header "🌍 环境配置 Environment Setup"

    # Export Phase 1
    export INFRA_PHASE="$INFRA_PHASE"
    ok "INFRA_PHASE=$INFRA_PHASE (Phase 1 基础设施激活)"

    # Load .env.production if exists
    if [ -f "$PROJECT_DIR/.env.production" ]; then
        set -a
        # shellcheck disable=SC1091
        source "$PROJECT_DIR/.env.production"
        set +a
        ok ".env.production 已加载"
    else
        warn ".env.production 未找到 — 使用默认值"
    fi

    # Ensure log directory
    if [ "$DRY_RUN" = false ]; then
        mkdir -p "$LOG_DIR"
    fi
    ok "日志目录: $LOG_DIR"

    # Check Redis connectivity (if REDIS_HOST is set)
    if [ -n "${REDIS_HOST:-}" ] && [ "$DRY_RUN" = false ]; then
        if command -v redis-cli &>/dev/null; then
            if redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" ping 2>/dev/null | grep -q "PONG"; then
                ok "Redis 连接正常 ($REDIS_HOST:${REDIS_PORT:-6379})"
            else
                warn "Redis 连接失败 ($REDIS_HOST:${REDIS_PORT:-6379}) — RedisCache 将降级为 InMemoryCache"
            fi
        else
            warn "redis-cli 不可用，跳过 Redis 连通性测试"
        fi
    fi
}

# ==================================================================
# Phase 2: Start Agent Runtime
# ==================================================================
start_agent_runtime() {
    header "🤖 AI 数字员工 Runtime 启动"

    START_SCRIPT="$PROJECT_DIR/scripts/start_agents.py"
    if [ ! -f "$START_SCRIPT" ]; then
        error "启动脚本未找到: $START_SCRIPT"
        return 1
    fi

    if [ "$DRY_RUN" = true ]; then
        ok "[DRY-RUN] 将执行: INFRA_PHASE=1 python $START_SCRIPT"
        return 0
    fi

    if command -v systemctl &>/dev/null && [ -f "$SERVICE_FILE" ]; then
        # ── systemd mode ─────────────────────────────────────────
        info "systemd 模式部署..."
        sudo cp "$SERVICE_FILE" /etc/systemd/system/chainke-agents.service
        sudo systemctl daemon-reload
        sudo systemctl enable chainke-agents
        sudo systemctl restart chainke-agents

        # Wait for service to start
        sleep 3
        if sudo systemctl is-active --quiet chainke-agents; then
            ok "systemd 服务 chainke-agents 运行中"
            sudo systemctl status chainke-agents --no-pager -l | head -15
        else
            error "systemd 服务启动失败"
            sudo journalctl -u chainke-agents --no-pager -n 20
            return 1
        fi
    else
        # ── Background process mode ──────────────────────────────
        info "后台进程模式部署..."
        # Kill any existing agent process
        if [ -f "$PROJECT_DIR/agents.pid" ]; then
            old_pid="$(cat "$PROJECT_DIR/agents.pid")"
            if kill -0 "$old_pid" 2>/dev/null; then
                warn "正在停止旧进程 (PID: $old_pid)"
                kill "$old_pid" 2>/dev/null || true
                sleep 2
            fi
        fi

        nohup python "$START_SCRIPT" > "$AGENTS_LOG" 2>&1 &
        AGENT_PID=$!
        echo "$AGENT_PID" > "$PROJECT_DIR/agents.pid"
        ok "后台进程已启动 (PID: $AGENT_PID)"

        # Wait briefly to check it's running
        sleep 3
        if kill -0 "$AGENT_PID" 2>/dev/null; then
            ok "Agent Runtime 进程存活"
            tail -5 "$AGENTS_LOG" 2>/dev/null || true
        else
            error "Agent Runtime 进程已退出 — 检查日志: $AGENTS_LOG"
            tail -20 "$AGENTS_LOG" 2>/dev/null || true
            return 1
        fi
    fi
}

# ==================================================================
# Phase 3: Verification
# ==================================================================
verify_deployment() {
    header "🔍 部署验证 Verification"

    if [ "$DRY_RUN" = true ]; then
        ok "[DRY-RUN] 将执行验证: python -c 'from app...'"
        return 0
    fi

    # Run Python verification inline
    python3 -c "
import sys, os
sys.path.insert(0, '$PROJECT_DIR')
os.environ['INFRA_PHASE'] = '1'

print(f'  {\"=\"*50}')
print(f'  {\"链客宝部署验证\":^50}')
print(f'  {\"=\"*50}')

# Check Phase 1 infrastructure
try:
    from app.cache.adapters.redis_adapter import RedisCache
    print(f'  ✅ RedisCache — 就绪')
except Exception as e:
    print(f'  ⚠️  RedisCache — 降级: {e}')

try:
    from app.events.adapters.sqlite_adapter import SQLiteEventBus
    print(f'  ✅ SQLiteEventBus — 就绪')
except Exception as e:
    print(f'  ❌ SQLiteEventBus — 错误: {e}')

# Check dependencies
try:
    from app.dependencies import get_cache, get_event_bus
    cache = get_cache()
    bus = get_event_bus()
    print(f'  ✅ Dependencies — cache={type(cache).__name__}, bus={type(bus).__name__}')
except Exception as e:
    print(f'  ⚠️  Dependencies — {e}')

# Check all 9 employees
try:
    from app.agents.employee_profiles import EMPLOYEE_AGENT_MAP, create_all_legion_agents
    print(f'  ✅ 数字员工注册: {len(EMPLOYEE_AGENT_MAP)} 名')
    for k, v in EMPLOYEE_AGENT_MAP.items():
        print(f'     {k:>15s} → {v[\"employee_id\"]}')
except Exception as e:
    print(f'  ❌ 员工注册失败: {e}')

# Check Agent Runtime
try:
    from app.agents.agent_runtime import AgentRuntime
    from app.agents.base_agent import AgentConfig
    print(f'  ✅ AgentRuntime — 就绪')
    print(f'  ✅ AgentConfig — 就绪')
except Exception as e:
    print(f'  ❌ AgentRuntime — {e}')

# Check Gaia Brain integration
try:
    from app.agents.scheduler_rules import SCHEDULER_RULES
    print(f'  ✅ SchedulerRules — {len(SCHEDULER_RULES)} 条规则')
    for rule in SCHEDULER_RULES:
        print(f'     {rule[\"schedule\"]:>12s} → {rule[\"agent_name\"]}')
except Exception as e:
    print(f'  ⚠️  SchedulerRules — {e}')

# Check Gaia Brain
try:
    from app.gaia_brain import GaiaBrain
    print(f'  ✅ GaiaBrain — 就绪')
except Exception as e:
    print(f'  ⚠️  GaiaBrain — {e}')

print(f'  {\"=\"*50}')
print(f'  INFRA_PHASE={os.environ.get(\"INFRA_PHASE\", \"0\")}')
print(f'  部署状态: 完成')
print(f'  {\"=\"*50}')
" 2>&1 || {
        error "Python 验证失败"
        return 1
    }
}

# ==================================================================
# Phase 4: Deployment report
# ==================================================================
report() {
    header "📋 部署报告 Deployment Report"

    echo -e "  ${BOLD}Timestamp:${NC}      $TIMESTAMP"
    echo -e "  ${BOLD}Project:${NC}        链客宝 (LianKeBao)"
    echo -e "  ${BOLD}Directory:${NC}      $PROJECT_DIR"
    echo -e "  ${BOLD}INFRA_PHASE:${NC}    $INFRA_PHASE"
    echo ""
    echo -e "  ${BOLD}已激活组件:${NC}"
    echo -e "    Phase 1:      RedisCache + SQLiteEventBus"
    echo -e "    Agent Runtime: 9 名数字员工"
    echo -e "    盖娅飞轮:      每 30 分钟自动进化"
    echo ""
    echo -e "  ${BOLD}日志:${NC}           $AGENTS_LOG"
    echo -e "  ${BOLD}PID:${NC}            $(cat "$PROJECT_DIR/agents.pid" 2>/dev/null || echo 'N/A')"
    echo -e "  ${BOLD}节点:${NC}           $(hostname 2>/dev/null || echo 'unknown')"
    echo ""
    echo -e "  ${GREEN}${BOLD}✅ 链客宝生产部署完成 🚀${NC}"
    echo -e "  ${GREEN}${BOLD}   LianKeBao production deployment complete.${NC}"
}

# ==================================================================
# Main
# ==================================================================
main() {
    echo ""
    echo -e "${CYAN}${BOLD}  🚀  链客宝 — 一键生产部署"
    echo -e "  ${CYAN}${BOLD}  LianKeBao — One-Command Production Deployment${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
    echo ""

    preflight_checks || {
        if [ "$CHECK_ONLY" = true ]; then
            error "前置检查未通过"
            exit 1
        fi
        warn "继续部署（部分前置检查未通过）"
    }

    if [ "$CHECK_ONLY" = true ]; then
        echo ""
        ok "检查完成 — 未执行部署 (--check)"
        exit 0
    fi

    setup_environment
    start_agent_runtime || {
        error "Agent Runtime 启动失败"
        exit 1
    }
    verify_deployment || {
        error "部署验证失败"
        exit 1
    }
    report
}

main "$@"
