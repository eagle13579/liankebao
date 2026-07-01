#!/bin/bash
# ==============================================================================
# 链客宝 — 服务重启脚本
# LianKeBao — Server Restart Script
#
# 功能:
#   - 重启 chainke-backend 服务
#   - 重启 chainke-agents 服务
#   - 等待两个服务健康就绪
#   - 报告最终状态
#
# 用法:
#   ./scripts/restart_all.sh                     # 重启所有服务
#   ./scripts/restart_all.sh --check              # 仅检查状态，不重启
#   ./scripts/restart_all.sh --backend-only       # 仅重启后端
#   ./scripts/restart_all.sh --agents-only        # 仅重启 Agent
#   ./scripts/restart_all.sh --docker             # 使用 docker-compose 重启
#   ./scripts/restart_all.sh --status             # 显示服务状态
#   ./scripts/restart_all.sh --force              # 强制重启 (kill -9)
#
# 依赖:
#   - systemctl (systemd) 或 docker-compose
#   - curl 用于健康检查
# ==============================================================================

set -euo pipefail

# ── 基础路径 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 配置 ─────────────────────────────────────────────────────────────────────
BACKEND_PORT="${BACKEND_PORT:-8201}"
AGENTS_PORT="${AGENTS_PORT:-8202}"
BACKEND_HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/health"
AGENTS_HEALTH_URL="http://127.0.0.1:${AGENTS_PORT}/health"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/logs}"
RESTART_LOG="${RESTART_LOG:-$LOG_DIR/restart.log}"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# systemd 服务名
SYSTEMD_BACKEND="${SYSTEMD_BACKEND:-chainke-backend}"
SYSTEMD_AGENTS="${SYSTEMD_AGENTS:-chainke-agents}"

# Docker Compose 路径
DOCKER_COMPOSE_DIR="${DOCKER_COMPOSE_DIR:-$PROJECT_DIR/deploy}"
DOCKER_COMPOSE_FILE="${DOCKER_COMPOSE_FILE:-docker-compose.yml}"

# ── 颜色 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── 日志 ─────────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

log()     { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$RESTART_LOG"; }
ok()      { echo -e "${GREEN}[✅]${NC} $*"; echo "[OK] $*" >> "$RESTART_LOG"; }
warn()    { echo -e "${YELLOW}[⚠️]${NC} $*"; echo "[WARN] $*" >> "$RESTART_LOG"; }
error()   { echo -e "${RED}[❌]${NC} $*"; echo "[ERROR] $*" >> "$RESTART_LOG"; }
header()  { echo -e "\n${CYAN}════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}════════════════════════════════════════════${NC}"; }

# ── 检测运行环境 ──────────────────────────────────────────────────────────────
detect_mode() {
    if command -v systemctl &>/dev/null; then
        if systemctl list-units --type=service --all 2>/dev/null | grep -q "${SYSTEMD_BACKEND}"; then
            echo "systemd"
            return
        fi
    fi

    if command -v docker &>/dev/null; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "chainke"; then
            echo "docker"
            return
        fi
    fi

    echo "unknown"
}

# ── 检查 systemd 服务是否存在 ───────────────────────────────────────────────
service_exists() {
    local svc="$1"
    systemctl list-units --type=service --all 2>/dev/null | grep -q "${svc}"
}

# ── 等待健康 ──────────────────────────────────────────────────────────────────
wait_healthy() {
    local name="$1"
    local url="$2"
    local retries="$3"
    local interval="$4"

    log "等待 ${name} 健康就绪 (最多 ${retries} 次, 间隔 ${interval}s)..."

    for i in $(seq 1 "$retries"); do
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${url}" 2>/dev/null || echo "000")

        if [ "${HTTP_CODE}" = "200" ]; then
            # 额外验证: 检查 JSON 响应中的 status
            local status
            status=$(curl -s "${url}" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
            if [ "${status}" = "ok" ]; then
                ok "${name} 健康就绪 (HTTP ${HTTP_CODE}, status=${status})"
                return 0
            fi
            ok "${name} 响应 (HTTP ${HTTP_CODE})"
            return 0
        fi

        if [ $((i % 5)) -eq 0 ]; then
            warn "  等待 ${name}... (尝试 ${i}/${retries}, HTTP ${HTTP_CODE})"
        fi
        sleep "${interval}"
    done

    error "${name} 健康检查超时 (${retries} 次尝试后)"
    return 1
}

# ── 查看服务状态 ──────────────────────────────────────────────────────────────
show_status() {
    header "📊 链客宝服务状态"

    local mode
    mode=$(detect_mode)
    log "运行模式: ${mode}"

    case "$mode" in
        systemd)
            for svc in "${SYSTEMD_BACKEND}" "${SYSTEMD_AGENTS}"; do
                if service_exists "${svc}"; then
                    local active_state
                    active_state=$(systemctl is-active "${svc}" 2>/dev/null || echo "unknown")
                    local sub_state
                    sub_state=$(systemctl show -p SubState "${svc}" 2>/dev/null | cut -d= -f2 || echo "unknown")

                    if [ "${active_state}" = "active" ]; then
                        ok "${svc}: ${active_state} (${sub_state})"
                    else
                        error "${svc}: ${active_state} (${sub_state})"
                    fi

                    # 显示最近日志
                    systemctl status "${svc}" --no-pager -l -n 3 2>/dev/null || true
                else
                    warn "${svc}: 未安装"
                fi
            done
            ;;
        docker)
            docker ps --filter "name=chainke" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
            ;;
        *)
            warn "无法检测服务模式"
            ;;
    esac

    echo ""
    # 检查健康端点
    log "检查健康端点..."
    for ep in "${BACKEND_HEALTH_URL}" "${AGENTS_HEALTH_URL}"; do
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${ep}" 2>/dev/null || echo "000")
        if [ "${HTTP_CODE}" = "200" ]; then
            ok "${ep} → HTTP ${HTTP_CODE}"
            curl -s "${ep}" 2>/dev/null | python3 -m json.tool 2>/dev/null || true
        else
            warn "${ep} → HTTP ${HTTP_CODE}"
        fi
    done
}

# ── systemd 重启 ──────────────────────────────────────────────────────────────
restart_systemd_service() {
    local svc="$1"
    local name="$2"

    if ! service_exists "${svc}"; then
        warn "${name} (${svc}) — systemd 服务不存在，跳过"
        return 1
    fi

    log "正在重启 ${name} (${svc})..."

    if [ "${FORCE_MODE}" = true ]; then
        # 强制重启
        systemctl kill --signal=SIGKILL "${svc}" 2>/dev/null || true
        sleep 1
    fi

    systemctl restart "${svc}" 2>&1 || {
        error "${name} 重启失败"
        journalctl -u "${svc}" --no-pager -n 10 2>/dev/null || true
        return 1
    }

    ok "${name} 已重启"

    # 等待服务启动
    systemctl is-active --quiet "${svc}" 2>/dev/null && ok "${name} 运行中" || warn "${name} 可能未完全启动"
}

# ── Docker restart ─────────────────────────────────────────────────────────
restart_docker_service() {
    local container_name="$1"
    local name="$2"
    local compose_service="$3"

    if ! command -v docker &>/dev/null; then
        warn "Docker 未安装，无法重启 ${name}"
        return 1
    fi

    log "正在重启 ${name} (docker: ${container_name})..."

    # 检查容器是否存在
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "${container_name}"; then
        docker restart "${container_name}" 2>&1 || {
            error "${name} Docker 重启失败"
            docker logs "${container_name}" --tail 10 2>/dev/null || true
            return 1
        }
        ok "${name} Docker 容器已重启"
    else
        warn "${name} Docker 容器 (${container_name}) 不存在"

        # 尝试 docker-compose
        if [ -f "${DOCKER_COMPOSE_DIR}/${DOCKER_COMPOSE_FILE}" ]; then
            log "使用 docker-compose 启动 ${compose_service}..."
            cd "${DOCKER_COMPOSE_DIR}"
            docker compose up -d "${compose_service}" 2>&1 || {
                error "${name} docker-compose 启动失败"
                return 1
            }
            ok "${name} docker-compose 已启动"
        else
            error "${name}: 无可用启动方式"
            return 1
        fi
    fi
}

# ── systemd 重启主流程 ──────────────────────────────────────────────────────
restart_systemd() {
    header "🚀 systemd 重启模式"

    if [ "${RESTART_BACKEND}" = true ]; then
        restart_systemd_service "${SYSTEMD_BACKEND}" "chainke-backend"
    fi

    if [ "${RESTART_AGENTS}" = true ]; then
        restart_systemd_service "${SYSTEMD_AGENTS}" "chainke-agents"
    fi

    # systemd daemon-reload
    if [ "${RESTART_BACKEND}" = true ] || [ "${RESTART_AGENTS}" = true ]; then
        log "重新加载 systemd 配置..."
        systemctl daemon-reload 2>/dev/null || true
    fi
}

# ── Docker 重启主流程 ────────────────────────────────────────────────────────
restart_docker() {
    header "🐳 Docker 重启模式"

    log "使用 docker-compose 文件: ${DOCKER_COMPOSE_DIR}/${DOCKER_COMPOSE_FILE}"

    if [ ! -f "${DOCKER_COMPOSE_DIR}/${DOCKER_COMPOSE_FILE}" ]; then
        error "docker-compose 文件未找到: ${DOCKER_COMPOSE_DIR}/${DOCKER_COMPOSE_FILE}"
        return 1
    fi

    cd "${DOCKER_COMPOSE_DIR}"

    if [ "${RESTART_BACKEND}" = true ] && [ "${RESTART_AGENTS}" = true ]; then
        # 重启所有
        log "重启所有服务..."
        docker compose up -d --remove-orphans 2>&1 || {
            error "docker-compose up -d 失败"
            return 1
        }
        ok "所有服务已重启"
    else
        # 选择性重启
        if [ "${RESTART_BACKEND}" = true ]; then
            log "重建并重启 backend..."
            docker compose up -d --no-deps --force-recreate backend 2>&1 || {
                error "backend 重启失败"
            }
        fi
        if [ "${RESTART_AGENTS}" = true ]; then
            log "重建并重启 agent-runtime..."
            docker compose up -d --no-deps --force-recreate agent-runtime 2>&1 || {
                error "agent-runtime 重启失败"
            }
        fi
    fi

    # 清理旧镜像
    docker image prune -f 2>/dev/null || true
}

# ── 健康验证 ──────────────────────────────────────────────────────────────────
verify_health() {
    header "🔍 健康验证"

    local all_healthy=true

    if [ "${RESTART_BACKEND}" = true ]; then
        wait_healthy "chainke-backend" "${BACKEND_HEALTH_URL}" "${HEALTH_RETRIES}" "${HEALTH_INTERVAL}" || all_healthy=false
    fi

    if [ "${RESTART_AGENTS}" = true ]; then
        wait_healthy "chainke-agents" "${AGENTS_HEALTH_URL}" "${HEALTH_RETRIES}" "${HEALTH_INTERVAL}" || all_healthy=false
    fi

    echo ""
    if [ "$all_healthy" = true ]; then
        ok "所有服务健康就绪"
    else
        error "部分服务未通过健康检查"
    fi

    # 显示最终状态摘要
    show_status

    return $($all_healthy && echo 0 || echo 1)
}

# ── 主函数 ────────────────────────────────────────────────────────────────────
main() {
    local CHECK_ONLY=false
    local STATUS_ONLY=false
    FORCE_MODE=false
    RESTART_BACKEND=true
    RESTART_AGENTS=true
    local MODE="auto"

    for arg in "$@"; do
        case "$arg" in
            --check)        CHECK_ONLY=true ;;
            --status)       STATUS_ONLY=true ;;
            --force)        FORCE_MODE=true ;;
            --backend-only) RESTART_AGENTS=false ;;
            --agents-only)  RESTART_BACKEND=false ;;
            --docker)       MODE="docker" ;;
            --systemd)      MODE="systemd" ;;
            --help|-h)
                echo "用法: $0 [选项]"
                echo ""
                echo "选项:"
                echo "  --check         预检模式 (检查环境，不重启)"
                echo "  --status        显示服务状态"
                echo "  --backend-only  仅重启后端"
                echo "  --agents-only   仅重启 Agent"
                echo "  --docker        强制使用 docker-compose"
                echo "  --systemd       强制使用 systemd"
                echo "  --force         强制重启 (kill -9)"
                echo "  --help          显示此帮助"
                echo ""
                echo "默认: 自动检测 systemd 或 docker 并重启所有服务"
                exit 0
                ;;
        esac
    done

    echo ""
    echo -e "${CYAN}${BOLD}  🚀  链客宝服务重启"
    echo -e "  ${CYAN}${BOLD}  LianKeBao Service Restart${NC}"
    echo -e "${CYAN}════════════════════════════════════════════${NC}"
    echo ""

    if [ "$STATUS_ONLY" = true ]; then
        show_status
        exit 0
    fi

    # 检测模式
    if [ "${MODE}" = "auto" ]; then
        MODE=$(detect_mode)
        log "自动检测模式: ${MODE}"
    else
        log "指定模式: ${MODE}"
    fi

    if [ "$CHECK_ONLY" = true ]; then
        show_status
        log "预检完成 (--check 模式，未执行重启)"
        exit 0
    fi

    # 执行重启
    case "${MODE}" in
        systemd)
            restart_systemd
            ;;
        docker)
            restart_docker
            ;;
        *)
            warn "无法检测运行模式，尝试 systemd..."
            restart_systemd || warn "systemd 重启失败"
            warn "尝试 docker-compose..."
            restart_docker || error "docker-compose 也失败"
            ;;
    esac

    # 等待健康
    verify_health

    # 最终报告
    echo ""
    log "════════════════════════════════════════════"
    log "  链客宝服务重启完成"
    log "  时间: ${TIMESTAMP}"
    log "  模式: ${MODE}"
    log "  Backend: ${BACKEND_HEALTH_URL}"
    log "  Agents:  ${AGENTS_HEALTH_URL}"
    log "  日志:    ${RESTART_LOG}"
    log "════════════════════════════════════════════"
}

main "$@"
