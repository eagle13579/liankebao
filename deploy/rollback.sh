#!/usr/bin/env bash
# ==============================================================================
# 链客宝 — 自动回滚脚本 (Rollback)
# ==============================================================================
# 功能:
#   1. git revert 回退到上一个稳定版本
#   2. 使用 blue_green_deploy.sh 重新构建 + 部署到非活跃环境
#   3. 切换流量到回滚版本
# ==============================================================================
#
# 用法:
#   bash deploy/rollback.sh                           # 回滚到上一个版本
#   bash deploy/rollback.sh --commit=<HASH>           # 回滚到指定版本
#   bash deploy/rollback.sh --steps=<N>               # 回滚 N 个提交
#   bash deploy/rollback.sh --dry-run                 # 空跑 (只输出不执行)
#
# 依赖:
#   - git, docker, docker compose, curl
#   - deploy/blue_green_deploy.sh
#   - deploy/docker-compose.{blue,green}.yml
# ==============================================================================

set -euo pipefail

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
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
ROLLBACK_COMMIT=""           # 回滚到的指定 commit
ROLLBACK_STEPS=1             # 回滚步数
DRY_RUN=false
HEALTH_RETRIES="${HEALTH_RETRIES:-12}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-$PROJECT_DIR/deploy/.blue-green-state}"

# ── 解析参数 ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --commit=*)     ROLLBACK_COMMIT="${1#*=}" ; shift ;;
        --steps=*)      ROLLBACK_STEPS="${1#*=}" ; shift ;;
        --dry-run)      DRY_RUN=true ; shift ;;
        -h|--help)
            echo "用法: $0 [--commit=<HASH>] [--steps=<N>] [--dry-run]"
            echo ""
            echo "选项:"
            echo "  --commit=<HASH>   回滚到指定 commit"
            echo "  --steps=<N>       回滚 N 个提交 (默认: 1)"
            echo "  --dry-run         空跑模式"
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
        echo "none"
    fi
}

# ── 主流程 ────────────────────────────────────────────────────────────────────

main() {
    if ! command -v git &>/dev/null; then
        err "缺少必需命令: git"
        exit 1
    fi

    # 检查是否在 git 仓库中
    if ! git rev-parse --git-dir &>/dev/null; then
        err "当前目录不是 git 仓库: $PROJECT_DIR"
        exit 1
    fi

    echo ""
    info "=============================================="
    info "  链客宝 自动回滚"
    info "=============================================="
    info "  回滚方式:  ${ROLLBACK_COMMIT:+指定 commit $ROLLBACK_COMMIT}${ROLLBACK_COMMIT:-回滚 ${ROLLBACK_STEPS} 步}"
    info "  空跑模式:  ${DRY_RUN}"
    info "=============================================="
    echo ""

    if [ "$DRY_RUN" = true ]; then
        warn "空跑模式 — 仅输出，不执行实际操作"
        echo ""
    fi

    # ── Step 1: 显示当前状态 ────────────────────────────────────────────────
    info "[1/6] 当前状态"
    info "  当前分支: $(git branch --show-current)"
    info "  当前提交: $(git rev-parse --short HEAD)"
    echo "  最近提交:"
    git log --oneline -5 2>/dev/null | sed 's/^/    /'
    echo ""

    # ── Step 2: 确认回滚目标 ────────────────────────────────────────────────
    info "[2/6] 确定回滚目标..."

    local target_commit=""
    local target_message=""

    if [ -n "$ROLLBACK_COMMIT" ]; then
        # 验证指定 commit 存在
        if ! git cat-file -e "${ROLLBACK_COMMIT}^{commit}" 2>/dev/null; then
            err "指定的 commit 不存在: $ROLLBACK_COMMIT"
            exit 1
        fi
        target_commit="$ROLLBACK_COMMIT"
        target_message="指定 commit: $ROLLBACK_COMMIT"
    else
        # 获取回滚目标 commit
        target_commit="$(git rev-parse HEAD~"${ROLLBACK_STEPS}" 2>/dev/null || true)"
        if [ -z "$target_commit" ]; then
            err "无法回滚 ${ROLLBACK_STEPS} 步 — 历史记录不足"
            exit 1
        fi
        target_message="回滚 ${ROLLBACK_STEPS} 步到 $(git rev-parse --short "$target_commit" 2>/dev/null)"
    fi

    info "  回滚目标: ${target_message}"
    info "  目标提交: $(git rev-parse --short "$target_commit" 2>/dev/null)"
    echo "  目标提交信息:"
    git log --oneline -1 "$target_commit" 2>/dev/null | sed 's/^/    /'
    echo ""

    # ── Step 3: git revert ──────────────────────────────────────────────────
    info "[3/6] 执行 git revert..."

    if [ "$DRY_RUN" = false ]; then
        # 创建一个 revert commit (而不是 reset，保持历史可追溯)
        # 回滚从 target_commit 到 HEAD 之间的所有更改
        local revert_range
        if [ -n "$ROLLBACK_COMMIT" ]; then
            revert_range="${ROLLBACK_COMMIT}..HEAD"
        else
            revert_range="HEAD~${ROLLBACK_STEPS}..HEAD"
        fi

        # 检查是否有未提交的更改
        if ! git diff --quiet || ! git diff --cached --quiet; then
            warn "存在未提交的更改，尝试 stash 保存..."
            git stash push -m "rollback-auto-stash-$(date +%s)" 2>/dev/null || true
        fi

        # 执行 git revert (为每个 commit 生成 revert commit)
        if ! git revert --no-edit "$revert_range" 2>&1; then
            err "git revert 失败 — 可能存在冲突"
            err "请手动解决冲突后重新执行部署:"
            err "  git revert --continue"
            err "  bash deploy/blue_green_deploy.sh"
            exit 1
        fi

        local new_head
        new_head="$(git rev-parse --short HEAD)"
        ok "git revert 完成 — 当前提交: ${new_head}"
        echo ""
        info "  Revert 提交信息:"
        git log --oneline -3 2>/dev/null | sed 's/^/    /'
    else
        local revert_range_dry
        if [ -n "$ROLLBACK_COMMIT" ]; then
            revert_range_dry="${ROLLBACK_COMMIT}..HEAD"
        else
            revert_range_dry="HEAD~${ROLLBACK_STEPS}..HEAD"
        fi
        warn "[DRY-RUN] git revert --no-edit $revert_range_dry"
    fi
    echo ""

    # ── Step 4: 确定目标环境 ───────────────────────────────────────────────
    info "[4/6] 确定部署目标环境..."

    local active target
    active="$(detect_active)"
    case "$active" in
        blue)   target="green" ;;
        green)  target="blue"  ;;
        none)   target="blue"  ;;
    esac

    info "  当前活跃: ${active:-none}"
    info "  部署目标: ${target} (回滚版本)"
    echo ""

    # ── Step 5: 部署回滚版本 ───────────────────────────────────────────────
    info "[5/6] 部署回滚版本到 ${target} 环境..."

    if [ "$DRY_RUN" = false ]; then
        # 调用 blue_green_deploy.sh 部署到目标环境 (构建 + 部署 + 切换)
        # 使用 --force-<color> 确保部署到正确的非活跃环境
        local force_flag="--force-${target}"

        info "调用: bash deploy/blue_green_deploy.sh ${force_flag}"
        echo ""

        if bash "$SCRIPT_DIR/blue_green_deploy.sh" "$force_flag"; then
            ok "回滚版本部署成功"
        else
            err "回滚版本部署失败"
            err "请手动检查: docker compose logs --tail=50"
            exit 1
        fi
    else
        warn "[DRY-RUN] bash deploy/blue_green_deploy.sh --force-${target}"
    fi
    echo ""

    # ── Step 6: 验证 ────────────────────────────────────────────────────────
    info "[6/6] 回滚后验证..."

    if [ "$DRY_RUN" = false ]; then
        local health_url="http://127.0.0.1:8001/health"
        local verified=false

        for i in $(seq 1 "$HEALTH_RETRIES"); do
            local http_code
            http_code=$(curl -s -o /dev/null -w '%{http_code}' \
                --connect-timeout 5 --max-time 5 \
                "$health_url" 2>/dev/null || echo "000")

            if [ "$http_code" = "200" ]; then
                ok "回滚验证通过 (HTTP ${http_code})"
                verified=true
                break
            fi
            info "等待回滚版本就绪... (${i}/${HEALTH_RETRIES})"
            sleep "$HEALTH_INTERVAL"
        done

        if [ "$verified" != true ]; then
            err "回滚验证失败 — 服务未恢复"
            err "请手动检查服务状态"
            exit 1
        fi
    else
        warn "[DRY-RUN] curl http://127.0.0.1:8001/health (验证)"
    fi
    echo ""

    # ── 回滚总结 ─────────────────────────────────────────────────────────────
    echo ""
    ok "=============================================="
    ok "  自动回滚完成"
    ok "=============================================="
    echo "  回滚方式:  ${target_message}"
    echo "  当前提交:  $(git rev-parse --short HEAD)"
    echo "  当前活跃:  $(detect_active)"
    echo "  回滚时间:  $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    echo "验证服务:"
    echo "  curl -s http://127.0.0.1:8001/health"
    echo ""
    info "如需进一步回滚，再次执行: bash deploy/rollback.sh"
    echo "=============================================="
    echo ""
}

# ── 执行 ───────────────────────────────────────────────────────────────────────
main
