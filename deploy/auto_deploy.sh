#!/bin/bash
# ============================================================
# 链客宝 自动部署脚本（免手动构建）
# 服务器: 阿里云 ECS (47.100.160.250)
# 用途: 从 Git 拉取最新代码，自动构建部署
# ============================================================
set -e

# ---- 配置 ----
PROJECT_DIR="/opt/liankebao"
GIT_REPO="git@github.com:your-org/liankebao.git"   # TODO: 替换为实际仓库地址
BRANCH="main"
LOG_FILE="$PROJECT_DIR/logs/auto_deploy.log"

# ---- 日志 ----
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# ---- 主流程 ----
main() {
    log "=== 自动部署开始 ==="

    # 进入项目目录
    cd "$PROJECT_DIR"

    # 拉取最新代码
    log "拉取代码 ($BRANCH 分支)..."
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
    git clean -fd

    # 执行部署
    log "执行 deploy.sh..."
    bash "$PROJECT_DIR/deploy.sh" 2>&1 | tee -a "$LOG_FILE"

    log "=== 自动部署完成 ==="
}

main "$@"
