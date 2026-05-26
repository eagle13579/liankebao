#!/bin/bash
# ============================================================
# 链客宝 自动部署脚本（增强版）
# 服务器: 阿里云 ECS (47.100.160.250)
# 用途: 从 Git 拉取最新代码 → 构建 → 部署 → 健康检查 → 回滚保障
# 支持: crontab 定时 / GitHub Actions 远程执行 / 手动
# ============================================================
set -e

# ---- 配置 ----
PROJECT_DIR="/opt/liankebao"
GIT_REPO="git@github.com:eagle13579/liankebao.git"
GIT_BRANCH="master"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/auto_deploy.log"
LOCK_FILE="/tmp/liankebao-auto-deploy.lock"
BACKEND_PORT=8001
DEPLOY_SCRIPT="$PROJECT_DIR/deploy/deploy.sh"
HEALTH_RETRIES=15
HEALTH_INTERVAL=2
ROLLBACK_ENABLED=true
MAX_BACKUPS=5

# ---- 颜色（仅在终端支持时）----
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    NC=''
fi

# ---- 日志 ----
log()  { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }
error(){ echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"; }
info() { echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"; }

# ---- 帮助信息 ----
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --skip-git-pull    跳过 git 拉取（CI/CD tarball 推送时使用）"
    echo "  --skip-health      跳过健康检查"
    echo "  --skip-notify      跳过通知发送"
    echo "  --branch=<name>    指定 Git 分支（默认: master）"
    echo "  --rollback         回滚到上一个备份版本"
    echo "  --help             显示帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                          # 完整自动部署"
    echo "  $0 --skip-git-pull          # 跳过 git pull（用于 CI tarball）"
    echo "  $0 --branch=develop         # 部署 develop 分支"
    echo "  $0 --rollback               # 回滚到上一个版本"
    exit 0
}

# ---- 参数解析 ----
SKIP_GIT_PULL=false
SKIP_HEALTH=false
SKIP_NOTIFY=false
ROLLBACK_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-git-pull) SKIP_GIT_PULL=true ;;
        --skip-health)   SKIP_HEALTH=true ;;
        --skip-notify)   SKIP_NOTIFY=true ;;
        --branch=*)      GIT_BRANCH="${1#*=}" ;;
        --rollback)      ROLLBACK_MODE=true ;;
        --help)          usage ;;
        *)               warn "Unknown option: $1"; usage ;;
    esac
    shift
done

# ---- 锁机制：防止并发执行 ----
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid=$(cat "$LOCK_FILE" 2>/dev/null)
        if kill -0 "$pid" 2>/dev/null; then
            warn "另一个部署进程正在运行 (PID: $pid)，跳过此次执行"
            exit 0
        else
            warn "发现过期锁文件，清理中..."
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
}

# ---- 创建必要目录 ----
ensure_dirs() {
    mkdir -p "$LOG_DIR"
}

# ---- 检查必要配置 ----
check_config() {
    local missing=false

    if [[ "$GIT_REPO" == "git@github.com:your-org/liankebao.git" ]]; then
        error "请先修改 auto_deploy.sh 中的 GIT_REPO 为实际仓库地址"
        missing=true
    fi

    # 检查必要命令
    for cmd in git curl; do
        if ! command -v $cmd &>/dev/null; then
            error "缺少必要命令: $cmd"
            missing=true
        fi
    done

    if [[ "$missing" = true ]]; then
        exit 1
    fi
}

# ---- Git 操作：克隆或拉取最新代码 ----
git_pull() {
    if [[ "$SKIP_GIT_PULL" = true ]]; then
        log "跳过 Git 拉取（--skip-git-pull）"
        return 0
    fi

    log "=== Git 操作（分支: $GIT_BRANCH）==="

    if [[ ! -d "$PROJECT_DIR" ]]; then
        log "项目目录不存在，首次部署中..."
        sudo mkdir -p "$PROJECT_DIR"
        sudo chown $(whoami):$(whoami) "$PROJECT_DIR"
        git clone --branch "$GIT_BRANCH" "$GIT_REPO" "$PROJECT_DIR"
        log "✓ Git 克隆完成（分支: $GIT_BRANCH）"
    else
        cd "$PROJECT_DIR"

        if [[ ! -d ".git" ]]; then
            error "$PROJECT_DIR 不是 Git 仓库"
            exit 1
        fi

        # 保存当前 commit hash 用于回滚
        OLD_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

        log "拉取代码（$GIT_BRANCH 分支）..."
        git fetch origin "$GIT_BRANCH"
        git reset --hard "origin/$GIT_BRANCH"
        git clean -fd

        NEW_COMMIT=$(git rev-parse --short HEAD)
        log "✓ 代码已更新: $OLD_COMMIT → $NEW_COMMIT"
    fi
}

# ---- 创建版本备份 ----
create_backup() {
    local BACKUP_DIR="${PROJECT_DIR}.bak.$(date +%Y%m%d_%H%M%S)"
    log "创建备份到 $BACKUP_DIR ..."
    sudo cp -r "$PROJECT_DIR" "$BACKUP_DIR" || {
        warn "备份失败，继续部署..."
        return 0
    }
    # 清理旧备份
    ls -dt ${PROJECT_DIR}.bak.* 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r sudo rm -rf
    log "✓ 备份完成（保留最近 $MAX_BACKUPS 个备份）"
    echo "$BACKUP_DIR"
}

# ---- 执行构建和部署 ----
run_deploy() {
    log "=== 执行构建和部署 ==="

    if [[ ! -f "$DEPLOY_SCRIPT" ]]; then
        error "部署脚本不存在: $DEPLOY_SCRIPT"
        return 1
    fi

    chmod +x "$DEPLOY_SCRIPT"

    # 构建 deploy.sh 参数
    local DEPLOY_ARGS=""

    if [[ "$SKIP_GIT_PULL" = true ]]; then
        DEPLOY_ARGS="$DEPLOY_ARGS --skip-git-pull"
    fi

    log "执行: bash deploy.sh $DEPLOY_ARGS"
    bash "$DEPLOY_SCRIPT" $DEPLOY_ARGS 2>&1 | tee -a "$LOG_FILE"

    local exit_code=${PIPESTATUS[0]}
    if [[ "$exit_code" -eq 0 ]]; then
        log "✓ 构建和部署完成"
        return 0
    else
        error "✗ 构建和部署失败 (exit code: $exit_code)"
        return "$exit_code"
    fi
}

# ---- 增强健康检查 ----
health_check() {
    if [[ "$SKIP_HEALTH" = true ]]; then
        warn "跳过健康检查（--skip-health）"
        return 0
    fi

    log "=== 健康检查 ==="
    local failures=0

    echo ""
    info "━━━ 1. Systemd 服务状态 ━━━"
    if sudo systemctl is-active --quiet chainke; then
        echo "  ✓ chainke.service 运行中"
    else
        echo "  ✗ chainke.service 未运行"
        sudo journalctl -u chainke -n 20 --no-pager
        failures=$((failures + 1))
    fi

    echo ""
    info "━━━ 2. TCP 端口监听 ━━━"
    if ss -tlnp 2>/dev/null | grep -q ":$BACKEND_PORT " || netstat -tlnp 2>/dev/null | grep -q ":$BACKEND_PORT "; then
        echo "  ✓ 后端端口 $BACKEND_PORT 正在监听"
    else
        echo "  ✗ 后端端口 $BACKEND_PORT 未监听"
        failures=$((failures + 1))
    fi

    echo ""
    info "━━━ 3. HTTP Health Endpoint（重试 $HEALTH_RETRIES 次，间隔 ${HEALTH_INTERVAL}s）━━━"
    local health_ok=false
    local response_body=""

    for i in $(seq 1 $HEALTH_RETRIES); do
        response_body=$(curl -s http://127.0.0.1:$BACKEND_PORT/health 2>/dev/null || true)
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$BACKEND_PORT/health 2>/dev/null || echo "000")

        if [[ "$http_code" == "200" ]]; then
            health_ok=true
            echo "  ✓ 健康检查通过 (HTTP $http_code, 尝试 $i/$HEALTH_RETRIES)"
            echo "    响应: $response_body"
            
            # 验证响应内容
            if echo "$response_body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
                echo "  ✓ 响应内容验证通过"
            fi
            break
        fi
        echo "  ⏳ 等待后端就绪... (HTTP $http_code, 尝试 $i/$HEALTH_RETRIES)"
        sleep $HEALTH_INTERVAL
    done

    if [[ "$health_ok" = false ]]; then
        echo "  ✗ 后端健康检查失败，最后响应: $response_body"
        echo "    检查日志: sudo journalctl -u chainke -n 50 --no-pager"
        echo "    检查日志: sudo tail -50 $LOG_DIR/backend-error.log"
        failures=$((failures + 1))
    fi

    echo ""
    info "━━━ 4. Nginx 配置检查 ━━━"
    if sudo nginx -t 2>&1; then
        echo "  ✓ Nginx 配置正确"
    else
        echo "  ✗ Nginx 配置有误"
        failures=$((failures + 1))
    fi

    echo ""
    info "━━━ 5. Nginx 服务状态 ━━━"
    if sudo systemctl is-active --quiet nginx; then
        echo "  ✓ Nginx 运行中"
    else
        echo "  ✗ Nginx 未运行"
        failures=$((failures + 1))
    fi

    echo ""
    info "━━━ 6. 系统资源 ━━━"
    local disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    local mem_usage=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
    local load=$(uptime | awk -F'load average:' '{print $2}' | xargs)
    
    if [[ "$disk_usage" -gt 85 ]]; then
        echo "  ⚠ 磁盘使用率 ${disk_usage}% — 超过 85%"
    else
        echo "  ✓ 磁盘使用率 ${disk_usage}%"
    fi
    echo "  ✓ 内存使用率 ${mem_usage}%"
    echo "  ✓ 系统负载: $load"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ "$failures" -gt 0 ]]; then
        error "健康检查发现 $failures 个问题"
        return 1
    else
        log "✓ 所有健康检查通过！"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ---- 回滚到上一个版本 ----
rollback() {
    log "=== 执行回滚 ==="

    # 查找最近的备份
    local latest_backup=$(ls -dt ${PROJECT_DIR}.bak.* 2>/dev/null | head -1)

    if [[ -z "$latest_backup" ]]; then
        error "没有找到可用的备份，无法回滚"
        return 1
    fi

    log "找到备份: $latest_backup"

    # 保存当前版本（以防需要再次回滚）
    local current_backup="${PROJECT_DIR}.bak.rollback-$(date +%Y%m%d_%H%M%S)"
    if [[ -d "$PROJECT_DIR" ]]; then
        sudo cp -r "$PROJECT_DIR" "$current_backup"
        log "当前版本已备份到 $current_backup"
    fi

    # 执行回滚
    sudo rm -rf "$PROJECT_DIR"
    sudo cp -r "$latest_backup" "$PROJECT_DIR"
    sudo chown -R $(whoami):$(whoami) "$PROJECT_DIR"

    log "✓ 已回滚到备份版本: $latest_backup"

    # 重启服务
    log "重启服务..."
    if [[ -f "$DEPLOY_SCRIPT" ]]; then
        bash "$DEPLOY_SCRIPT" --skip-git-pull --skip-frontend 2>&1 | tee -a "$LOG_FILE"
    fi

    # 回滚后健康检查
    health_check || warn "回滚后健康检查有警告"
    
    log "✓ 回滚完成"
}

# ---- 发送通知 ----
send_notification() {
    local status="$1"
    local message="$2"

    if [[ "$SKIP_NOTIFY" = true ]]; then
        return 0
    fi

    log "发送部署通知: $status"

    # 钉钉 Webhook（如果配置了）
    local DINGTALK_WEBHOOK="${DINGTALK_WEBHOOK:-}"
    if [[ -n "$DINGTALK_WEBHOOK" ]]; then
        curl -s -X POST "$DINGTALK_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{
                \"msgtype\": \"text\",
                \"text\": {
                    \"content\": \"【链客宝部署】$status\n$message\n时间: $(date '+%Y-%m-%d %H:%M:%S')\n服务器: 47.100.160.250\"
                }
            }" > /dev/null 2>&1 || true
        log "  钉钉通知已发送"
    fi
}

# ---- 主流程 ----
main() {
    echo ""
    echo "======================================="
    echo "   链客宝 自动部署 (Auto Deploy)"
    echo "   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "   分支: $GIT_BRANCH"
    echo "   端口: $BACKEND_PORT"
    echo "======================================="
    echo ""

    ensure_dirs
    acquire_lock

    # ---- 回滚模式 ----
    if [[ "$ROLLBACK_MODE" = true ]]; then
        rollback
        send_notification "回滚完成" "已回滚到上一个备份版本"
        exit 0
    fi

    check_config

    log "=== 自动部署开始 ==="
    local start_time=$(date +%s)

    # 1. Git 操作（拉取最新代码）
    git_pull

    # 2. 创建备份（部署前）
    local backup_dir=""
    if [[ "$ROLLBACK_ENABLED" = true ]] && [[ -d "$PROJECT_DIR" ]]; then
        backup_dir=$(create_backup)
    fi

    # 3. 执行构建和部署
    if ! run_deploy; then
        error "部署失败"
        send_notification "部署失败" "构建或部署步骤返回错误"
        
        # 自动回滚
        if [[ "$ROLLBACK_ENABLED" = true ]] && [[ -n "$backup_dir" ]]; then
            warn "触发自动回滚..."
            ROLLBACK_MODE=true
            rollback
            send_notification "自动回滚完成" "部署失败后自动回滚到上一个版本"
        fi
        exit 1
    fi

    # 4. 健康检查
    if ! health_check; then
        error "健康检查失败"
        send_notification "健康检查失败" "服务已部署但健康检查未通过"
        
        if [[ "$ROLLBACK_ENABLED" = true ]] && [[ -n "$backup_dir" ]]; then
            warn "触发自动回滚（健康检查失败）..."
            ROLLBACK_MODE=true
            rollback
            send_notification "自动回滚完成" "健康检查失败后自动回滚到上一个版本"
        fi
        exit 1
    fi

    # 5. 计算耗时
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    echo "======================================="
    log "✓ 自动部署成功完成！"
    log "   耗时: ${duration}s"
    log "   分支: $GIT_BRANCH"
    log "   提交: $(cd "$PROJECT_DIR" 2>/dev/null && git rev-parse --short HEAD || echo 'N/A')"
    log "   日志: $LOG_FILE"
    echo "======================================="
    echo ""

    send_notification "部署成功" "耗时 ${duration}s，分支 $GIT_BRANCH"
}

main "$@"
