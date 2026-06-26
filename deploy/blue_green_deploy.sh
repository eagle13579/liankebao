#!/usr/bin/env bash
# ==============================================================================
# 链客宝 — 蓝绿部署脚本 (Blue-Green Deployment)
# ==============================================================================
# 功能:
#   1. 检测当前活跃环境 (blue / green)
#   2. 构建新版本到非活跃环境
#   3. 对新环境执行健康检查
#   4. 切换 Nginx upstream 到新环境
#   5. 停止旧环境容器
#   6. 保存部署状态
# ==============================================================================
#
# 用法:
#   bash deploy/blue_green_deploy.sh                    # 自动蓝绿切换
#   bash deploy/blue_green_deploy.sh --force-blue       # 强制部署到蓝色
#   bash deploy/blue_green_deploy.sh --force-green      # 强制部署到绿色
#   bash deploy/blue_green_deploy.sh --skip-build       # 跳过构建 (只切换)
#   bash deploy/blue_green_deploy.sh --dry-run          # 空跑 (只输出不执行)
#
# 依赖:
#   - docker, docker compose, curl
#   - 项目根目录的 docker-compose.yml (基础服务: postgres, redis, nginx)
#   - deploy/docker-compose.blue.yml
#   - deploy/docker-compose.green.yml
#   - deploy/nginx/upstream-blue.conf / upstream-green.conf
# ==============================================================================

set -euo pipefail

# ── 颜色输出 (同项目现有风格) ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── 项目路径 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ── 默认配置 ──────────────────────────────────────────────────────────────────
HEALTH_CHECK_URL="${HEALTH_CHECK_URL:-http://127.0.0.1:8001/health}"
HEALTH_RETRIES="${HEALTH_RETRIES:-12}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-$PROJECT_DIR/deploy/.blue-green-state}"
NGINX_CONTAINER="${NGINX_CONTAINER:-chainke-nginx}"

# 解析参数
FORCE_TARGET=""
SKIP_BUILD=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force-blue)   FORCE_TARGET="blue" ; shift ;;
        --force-green)  FORCE_TARGET="green" ; shift ;;
        --skip-build)   SKIP_BUILD=true ; shift ;;
        --dry-run)      DRY_RUN=true ; shift ;;
        -h|--help)
            echo "用法: $0 [--force-blue|--force-green] [--skip-build] [--dry-run]"
            exit 0
            ;;
        *)  err "未知参数: $1"; exit 1 ;;
    esac
done

# ── 工具函数 ───────────────────────────────────────────────────────────────────

# 检测当前活跃环境
detect_active() {
    if [ -f "$DEPLOY_STATE_FILE" ]; then
        cat "$DEPLOY_STATE_FILE"
    else
        # 默认蓝色为首次部署目标
        echo "none"
    fi
}

# 保存当前活跃环境
save_active() {
    local color="$1"
    echo "$color" > "$DEPLOY_STATE_FILE"
    ok "部署状态已保存: $color → $DEPLOY_STATE_FILE"
}

# 确定下一步部署的目标环境
determine_target() {
    if [ -n "$FORCE_TARGET" ]; then
        echo "$FORCE_TARGET"
        return
    fi

    local active
    active="$(detect_active)"
    case "$active" in
        blue)   echo "green" ;;
        green)  echo "blue"  ;;
        none)   echo "blue"  ;;  # 首次部署默认蓝色
        *)      err "未知状态: $active，重置为 blue"; echo "blue" ;;
    esac
}

# ── 主流程 ────────────────────────────────────────────────────────────────────

main() {
    local active target
    active="$(detect_active)"
    target="$(determine_target)"

    echo ""
    info "=============================================="
    info "  链客宝 蓝绿部署"
    info "=============================================="
    info "  当前活跃:  ${active:-none}"
    info "  部署目标:  ${target}"
    info "  跳过构建:  ${SKIP_BUILD}"
    info "  空跑模式:  ${DRY_RUN}"
    info "=============================================="
    echo ""

    if [ "$DRY_RUN" = true ]; then
        warn "空跑模式 — 仅输出，不执行实际操作"
        echo ""
    fi

    # ── Step 1: 前置检查 ─────────────────────────────────────────────────────
    info "[1/6] 前置检查..."

    for cmd in docker curl; do
        if ! command -v "$cmd" &>/dev/null; then
            err "缺少必需命令: $cmd"
            exit 1
        fi
    done

    # 检查 compose 文件存在
    local compose_base="docker-compose.yml"
    local compose_target="deploy/docker-compose.${target}.yml"
    if [ ! -f "$compose_base" ]; then
        err "基础 compose 文件不存在: $compose_base"
        exit 1
    fi
    if [ ! -f "$compose_target" ]; then
        err "目标 compose 文件不存在: $compose_target"
        exit 1
    fi

    # 检查 nginx upstream 配置存在
    local upstream_file="deploy/nginx/upstream-${target}.conf"
    if [ ! -f "$upstream_file" ]; then
        err "Nginx upstream 配置不存在: $upstream_file"
        exit 1
    fi

    ok "前置检查通过"
    echo ""

    # ── Step 2: 构建新版本 ───────────────────────────────────────────────────
    if [ "$SKIP_BUILD" = true ]; then
        info "[2/6] 跳过构建 (--skip-build)"
    else
        info "[2/6] 构建 ${target} 版本..."
        if [ "$DRY_RUN" = false ]; then
            # 使用目标 compose 文件构建 (只构建 target 对应的服务)
            docker compose -f "$compose_base" -f "$compose_target" build \
                "backend-${target}" "frontend-builder-${target}"
            ok "${target} 版本构建完成"
        else
            warn "[DRY-RUN] docker compose -f $compose_base -f $compose_target build backend-${target} frontend-builder-${target}"
        fi
    fi
    echo ""

    # ── Step 3: 启动新环境容器 ───────────────────────────────────────────────
    info "[3/6] 启动 ${target} 环境容器..."
    if [ "$DRY_RUN" = false ]; then
        # 只启动 target 新增的服务 (不启动 base 中已有的，也不影响 active 的服务)
        docker compose -f "$compose_base" -f "$compose_target" up -d \
            "backend-${target}" "frontend-builder-${target}"
        ok "${target} 环境容器已启动"
    else
        warn "[DRY-RUN] docker compose -f $compose_base -f $compose_target up -d backend-${target} frontend-builder-${target}"
    fi
    echo ""

    # ── Step 4: 健康检查 ─────────────────────────────────────────────────────
    info "[4/6] 等待 ${target} 环境健康检查..."

    # 根据目标环境确定健康检查端口
    local health_port
    case "$target" in
        blue)  health_port="8002" ;;  # blue 映射的宿主机端口
        green) health_port="8003" ;;  # green 映射的宿主机端口
    esac
    local target_health_url="http://127.0.0.1:${health_port}/health"

    if [ "$DRY_RUN" = false ]; then
        local health_ok=false
        for i in $(seq 1 "$HEALTH_RETRIES"); do
            local http_code
            http_code=$(curl -s -o /dev/null -w '%{http_code}' \
                --connect-timeout 5 --max-time 5 \
                "$target_health_url" 2>/dev/null || echo "000")

            if [ "$http_code" = "200" ]; then
                ok "健康检查通过 (HTTP ${http_code}) — 第 ${i}/${HEALTH_RETRIES} 次"
                health_ok=true
                break
            fi
            info "等待服务就绪... (${i}/${HEALTH_RETRIES}, HTTP ${http_code}, 间隔 ${HEALTH_INTERVAL}s)"
            sleep "$HEALTH_INTERVAL"
        done

        if [ "$health_ok" != true ]; then
            err "健康检查失败 — ${target} 环境未就绪"
            err "检查日志: docker compose -f $compose_base -f $compose_target logs backend-${target} --tail=50"
            err ""
            err "是否回滚? 执行: bash deploy/rollback.sh"
            exit 1
        fi
    else
        warn "[DRY-RUN] curl $target_health_url (预期 HTTP 200)"
    fi
    echo ""

    # ── Step 5: 切换 Nginx ──────────────────────────────────────────────────
    info "[5/6] 切换 Nginx upstream → ${target}..."

    if [ "$DRY_RUN" = false ]; then
        # 复制对应 upstream 配置到 active 文件 (nginx 容器内挂载了此路径)
        local active_upstream_file="$PROJECT_DIR/deploy/nginx/upstream-active.conf"
        cp "$upstream_file" "$active_upstream_file"
        ok "upstream 配置已更新: ${target}"

        # 重载 nginx 使配置生效
        if docker ps --format '{{.Names}}' | grep -q "^${NGINX_CONTAINER}$"; then
            docker exec "$NGINX_CONTAINER" nginx -s reload
            ok "Nginx 已重载，流量切换到 ${target}"
        else
            warn "Nginx 容器未运行 (${NGINX_CONTAINER})，无法重载"
            warn "请手动重启 Nginx 后继续"
        fi

        # 记录切换时间
        echo "$(date '+%Y-%m-%d %H:%M:%S') | 切换 | ${active:-none} → ${target}" >> "$PROJECT_DIR/deploy/.blue-green-history"
    else
        warn "[DRY-RUN] cp $upstream_file → deploy/nginx/upstream-active.conf"
        warn "[DRY-RUN] docker exec $NGINX_CONTAINER nginx -s reload"
    fi
    echo ""

    # ── Step 6: 清理旧环境 ──────────────────────────────────────────────────
    local old_env="$active"
    if [ "$old_env" != "none" ] && [ "$old_env" != "$target" ]; then
        info "[6/6] 清理旧环境 (${old_env})..."

        if [ "$DRY_RUN" = false ]; then
            local old_compose="deploy/docker-compose.${old_env}.yml"
            if [ -f "$old_compose" ]; then
                # 停止并移除旧环境的容器
                docker compose -f "$compose_base" -f "$old_compose" rm -fsv \
                    "backend-${old_env}" "frontend-builder-${old_env}" 2>/dev/null || {
                    # 如果 rm 失败，尝试 stop
                    docker compose -f "$compose_base" -f "$old_compose" stop \
                        "backend-${old_env}" "frontend-builder-${old_env}" 2>/dev/null || true
                }
                ok "旧环境 (${old_env}) 已清理"
            else
                warn "旧环境 compose 文件不存在: $old_compose，跳过清理"
            fi
        else
            warn "[DRY-RUN] 清理旧环境 ${old_env}"
        fi
    else
        info "[6/6] 无旧环境需要清理 (首次部署或同环境)"
    fi
    echo ""

    # ── 保存状态 ─────────────────────────────────────────────────────────────
    if [ "$DRY_RUN" = false ]; then
        save_active "$target"
    else
        warn "[DRY-RUN] save_active $target"
    fi

    # ── 部署总结 ─────────────────────────────────────────────────────────────
    echo ""
    ok "=============================================="
    ok "  蓝绿部署完成"
    ok "=============================================="
    echo "  当前活跃:  ${target}"
    echo "  健康端点:  ${target_health_url}"
    echo "  部署时间:  $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    echo "验证状态:"
    echo "  curl -s http://127.0.0.1:8001/health    # 通过 nginx"
    echo "  curl -s http://127.0.0.1:${health_port}/health  # 直连 ${target}"
    echo ""
    echo "查看日志:"
    echo "  docker compose -f $compose_base -f $compose_target logs -f backend-${target}"
    echo ""
    echo "如需回滚:"
    echo "  bash deploy/rollback.sh"
    echo "=============================================="
    echo ""
}

# ── 执行 ───────────────────────────────────────────────────────────────────────
main
