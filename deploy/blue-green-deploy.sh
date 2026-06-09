#!/bin/bash
# ============================================================
# 链客宝AI 蓝绿部署脚本 (Blue-Green Deployment)
# 服务器: 阿里云 ECS (47.100.160.250)
# 用途: 实现零停机蓝绿部署，支持自动切换和回滚
#
# 目录结构:
#   /opt/liankebao-blue/   — Blue 环境（端口 18001）
#   /opt/liankebao-green/  — Green 环境（端口 18002）
#   /opt/liankebao/         — 原项目目录（代码源）
#
# 工作原理:
#   1. 构建新版本到非活跃目录
#   2. 启动新版本后端并进行健康检查
#   3. 健康通过 → 切换 Nginx upstream 指向新目录 → nginx reload
#   4. 健康不通过 → 保留旧版本，输出告警
#   5. 零停机: nginx reload 不会中断现有连接
# ============================================================
set -e

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---- 路径配置 ----
PROJECT_DIR="/opt/liankebao"
DEPLOY_DIR="$PROJECT_DIR/deploy"
BLUE_DIR="/opt/liankebao-blue"
GREEN_DIR="/opt/liankebao-green"
BLUE_PORT=18001
GREEN_PORT=18002
HEALTH_RETRIES=15
HEALTH_INTERVAL=2
NGINX_CONF="/etc/nginx/nginx.conf"
NGINX_ACTIVE_BACKEND_CONF="/etc/nginx/conf.d/chainke-active-backend.conf"
NGINX_DEFAULT_CONF="$DEPLOY_DIR/nginx.conf"
NGINX_BLUEGREEN_CONF="$DEPLOY_DIR/nginx-bluegreen.conf"
STATE_FILE="$DEPLOY_DIR/.bluegreen-state"
DIST_SYMLINK="/opt/liankebao/dist.active"
LOCK_FILE="/tmp/liankebao-bluegreen.lock"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/bluegreen-deploy.log"

# ---- 服务名称（用于 systemd）----
SERVICE_BLUE="chainke-blue"
SERVICE_GREEN="chainke-green"

# ---- Git 配置 ----
GIT_REMOTE="origin"
GIT_BRANCH="master"

# ---- 日志函数 ----
log()  { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }
error(){ echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"; }
info() { echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"; }

# ---- 帮助信息 ----
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "蓝绿部署选项:"
    echo "  --switch-to [blue|green|auto]  切换到指定环境（auto=自动选择非活跃环境）"
    echo "  --rollback                      回滚到上一个版本（切换回之前活跃的环境）"
    echo "  --status                        查看当前蓝绿部署状态"
    echo "  --help                          显示帮助信息"
    echo ""
    echo "部署控制:"
    echo "  --skip-git-pull                 跳过 Git 拉取"
    echo "  --skip-frontend                 跳过前端构建"
    echo "  --skip-backend                  跳过后端部署"
    echo "  --skip-health                   跳过健康检查"
    echo "  --branch=<name>                 指定 Git 分支（默认: master）"
    echo ""
    echo "示例:"
    echo "  $0 --switch-to auto              # 自动部署到非活跃环境并切换"
    echo "  $0 --switch-to blue              # 强制部署并切换到 blue"
    echo "  $0 --rollback                    # 回滚到上一个活跃环境"
    echo "  $0 --status                      # 查看状态"
    exit 0
}

# ---- 参数解析 ----
SWITCH_TARGET=""
ROLLBACK_MODE=false
STATUS_MODE=false
SKIP_GIT_PULL=false
SKIP_FRONTEND=false
SKIP_BACKEND=false
SKIP_HEALTH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --switch-to=*)    SWITCH_TARGET="${1#*=}" ;;
        --switch-to)      SWITCH_TARGET="$2"; shift ;;
        --rollback)       ROLLBACK_MODE=true ;;
        --status)         STATUS_MODE=true ;;
        --skip-git-pull)  SKIP_GIT_PULL=true ;;
        --skip-frontend)  SKIP_FRONTEND=true ;;
        --skip-backend)   SKIP_BACKEND=true ;;
        --skip-health)    SKIP_HEALTH=true ;;
        --branch=*)       GIT_BRANCH="${1#*=}" ;;
        --help)           usage ;;
        *)                warn "Unknown option: $1"; usage ;;
    esac
    shift
done

# ---- 锁机制 ----
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid=$(cat "$LOCK_FILE" 2>/dev/null)
        if kill -0 "$pid" 2>/dev/null; then
            error "另一个蓝绿部署进程正在运行 (PID: $pid)"
            exit 1
        else
            warn "发现过期锁文件，清理中..."
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
}

# ---- 确保目录存在 ----
ensure_dirs() {
    mkdir -p "$BLUE_DIR" "$GREEN_DIR" "$LOG_DIR" "$DEPLOY_DIR"
    # 创建 dist.active 符号链接（如果不存在）
    if [[ ! -L "$DIST_SYMLINK" ]]; then
        if [[ -d "$PROJECT_DIR/dist" ]]; then
            ln -sf "$PROJECT_DIR/dist" "$DIST_SYMLINK"
            log "创建 dist.active 符号链接 -> $PROJECT_DIR/dist"
        elif [[ -d "$BLUE_DIR/dist" ]]; then
            ln -sf "$BLUE_DIR/dist" "$DIST_SYMLINK"
            log "创建 dist.active 符号链接 -> $BLUE_DIR/dist"
        fi
    fi
}

# ---- 加载状态文件 ----
load_state() {
    if [[ -f "$STATE_FILE" ]]; then
        source "$STATE_FILE"
        log "加载状态: ACTIVE=$ACTIVE, PREVIOUS=$PREVIOUS"
    else
        # 初始状态：默认 blue 活跃，green 备用
        ACTIVE="blue"
        PREVIOUS="green"
        save_state
        log "初始化状态: ACTIVE=blue, PREVIOUS=green"
    fi
}

# ---- 保存状态文件 ----
save_state() {
    cat > "$STATE_FILE" << EOF
# 链客宝AI蓝绿部署状态文件
# 由 blue-green-deploy.sh 自动管理
ACTIVE=$ACTIVE
PREVIOUS=$PREVIOUS
LAST_UPDATED=$(date '+%Y-%m-%d %H:%M:%S')
EOF
    log "状态已保存: ACTIVE=$ACTIVE, PREVIOUS=$PREVIOUS"
}

# ---- 获取当前活跃/非活跃环境信息 ----
get_active_env() {
    echo "$ACTIVE"
}

get_inactive_env() {
    if [[ "$ACTIVE" == "blue" ]]; then
        echo "green"
    else
        echo "blue"
    fi
}

get_env_dir() {
    local env="$1"
    if [[ "$env" == "blue" ]]; then
        echo "$BLUE_DIR"
    else
        echo "$GREEN_DIR"
    fi
}

get_env_port() {
    local env="$1"
    if [[ "$env" == "blue" ]]; then
        echo "$BLUE_PORT"
    else
        echo "$GREEN_PORT"
    fi
}

get_env_service() {
    local env="$1"
    if [[ "$env" == "blue" ]]; then
        echo "$SERVICE_BLUE"
    else
        echo "$SERVICE_GREEN"
    fi
}

# ---- 显示状态 ----
show_status() {
    load_state
    local inactive_env=$(get_inactive_env)
    local active_dir=$(get_env_dir "$ACTIVE")
    local inactive_dir=$(get_env_dir "$inactive_env")
    local active_port=$(get_env_port "$ACTIVE")
    local inactive_port=$(get_env_port "$inactive_env")

    echo ""
    echo "========================================"
    echo "  链客宝AI 蓝绿部署状态"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    echo ""
    echo "  当前活跃: $(echo -e "${GREEN}${ACTIVE^^}${NC}") (端口 $active_port)"
    echo "  备  用:   $(echo -e "${BLUE}${inactive_env^^}${NC}") (端口 $inactive_port)"
    echo "  上次更新: ${LAST_UPDATED:-未知}"
    echo ""
    echo "  目录:"
    echo "    Blue:  $BLUE_DIR"
    echo "    Green: $GREEN_DIR"
    echo ""
    echo "  活跃目录: $active_dir"
    echo "  备用目录: $inactive_dir"
    echo ""

    # 检查各目录是否存在
    if [[ -d "$active_dir" ]]; then
        echo -e "  ${GREEN}✓${NC} 活跃目录存在"
    else
        echo -e "  ${RED}✗${NC} 活跃目录不存在"
    fi
    if [[ -d "$inactive_dir" ]]; then
        echo -e "  ${GREEN}✓${NC} 备用目录存在"
    else
        echo -e "  ${YELLOW}⚠${NC} 备用目录不存在"
    fi

    # 检查后端端口
    echo ""
    echo "  后端服务:"
    local active_svc=$(get_env_service "$ACTIVE")
    if systemctl is-active --quiet "$active_svc" 2>/dev/null; then
        echo -e "    ${GREEN}✓${NC} $active_svc (活跃) 运行中"
    else
        echo -e "    ${RED}✗${NC} $active_svc (活跃) 未运行"
    fi
    local inactive_svc=$(get_env_service "$inactive_env")
    if systemctl is-active --quiet "$inactive_svc" 2>/dev/null; then
        echo -e "    ${YELLOW}⚠${NC} $inactive_svc (备用) 仍在运行"
    else
        echo -e "    ${BLUE}○${NC} $inactive_svc (备用) 已停止"
    fi

    # 健康检查
    echo ""
    echo -n "  健康检查: "
    local http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$active_port/health" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
        echo -e "${GREEN}通过 (HTTP $http_code)${NC}"
    else
        echo -e "${RED}失败 (HTTP $http_code)${NC}"
    fi

    # Nginx active backend 文件
    echo ""
    echo "  Nginx 后端指向:"
    if [[ -f "$NGINX_ACTIVE_BACKEND_CONF" ]]; then
        local backend_line=$(cat "$NGINX_ACTIVE_BACKEND_CONF" | grep "server " | head -1 || echo "(空)")
        echo "    $backend_line"
    else
        echo -e "    ${YELLOW}配置文件不存在${NC}"
    fi

    echo ""
    echo "========================================"
    echo ""
}

# ---- 从 Git 拉取代码到指定目录 ----
git_pull_to_dir() {
    local target_dir="$1"

    if [[ "$SKIP_GIT_PULL" = true ]]; then
        log "跳过 Git 拉取（--skip-git-pull）"
        return 0
    fi

    log "=== 拉取最新代码到 $target_dir ==="

    if [[ ! -d "$target_dir/.git" ]]; then
        # 从项目目录复制 .git 信息或全新部署
        if [[ -d "$PROJECT_DIR/.git" ]]; then
            log "从 $PROJECT_DIR 复制代码..."
            rsync -a --delete --exclude='node_modules' --exclude='venv' \
                --exclude='__pycache__' --exclude='.git' \
                "$PROJECT_DIR/" "$target_dir/"
            # 复制 .git 以便 git 操作
            cp -r "$PROJECT_DIR/.git" "$target_dir/.git"
        else
            error "项目目录 $PROJECT_DIR 不是 Git 仓库，无法拉取代码"
            return 1
        fi
    fi

    cd "$target_dir"
    log "拉取 $GIT_BRANCH 分支..."
    git fetch "$GIT_REMOTE" "$GIT_BRANCH"
    git reset --hard "$GIT_REMOTE/$GIT_BRANCH"
    git clean -fd

    local commit_hash=$(git rev-parse --short HEAD)
    log "代码已更新到 $target_dir (commit: $commit_hash)"
}

# ---- 构建前端 ----
build_frontend() {
    local target_dir="$1"

    if [[ "$SKIP_FRONTEND" = true ]]; then
        warn "跳过前端构建（--skip-frontend）"
        return 0
    fi

    log "=== 前端构建 ($target_dir) ==="

    cd "$target_dir"

    local pkg_dir=""
    if [[ -f "package.json" ]]; then
        pkg_dir="$target_dir"
    elif [[ -d "liankebao-weapp" ]] && [[ -f "liankebao-weapp/package.json" ]]; then
        pkg_dir="$target_dir/liankebao-weapp"
    else
        warn "package.json 不存在，跳过前端构建"
        return 0
    fi

    cd "$pkg_dir"

    log "安装前端依赖..."
    npm ci 2>&1 | tail -5

    log "构建前端..."
    if grep -q '"build:weapp"' package.json 2>/dev/null; then
        npm run build:weapp 2>&1 | tail -10
    elif grep -q '"build"' package.json 2>/dev/null; then
        npm run build 2>&1 | tail -10
    else
        warn "package.json 中未找到 build 命令"
        return 0
    fi

    # 确保 dist 目录在目标环境根目录下
    if [[ -f "dist/index.html" ]] && [[ "$pkg_dir" != "$target_dir" ]]; then
        mkdir -p "$target_dir/dist"
        cp -r dist/* "$target_dir/dist/" 2>/dev/null || true
        log "前端构建产物已复制到 $target_dir/dist"
    fi

    log "前端构建完成"
}

# ---- 后端部署 ----
deploy_backend() {
    local target_dir="$1"
    local target_port="$2"

    if [[ "$SKIP_BACKEND" = true ]]; then
        warn "跳过后端部署（--skip-backend）"
        return 0
    fi

    log "=== 后端部署 ($target_dir, 端口: $target_port) ==="

    local backend_dir="$target_dir/backend"
    local venv_dir="$backend_dir/venv"

    if [[ ! -d "$backend_dir" ]]; then
        error "后端目录 $backend_dir 不存在"
        return 1
    fi

    cd "$backend_dir"

    # 创建虚拟环境
    if [[ ! -d "$venv_dir" ]]; then
        log "创建 Python 虚拟环境..."
        python3 -m venv "$venv_dir"
    fi

    # 激活虚拟环境并安装依赖
    source "$venv_dir/bin/activate"

    log "升级 pip..."
    pip install --upgrade pip -q

    if [[ -f "requirements.txt" ]]; then
        log "安装 Python 依赖..."
        pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q
    fi

    deactivate
    log "后端依赖安装完成 ($venv_dir)"
}

# ---- 创建/更新 systemd 服务 ----
setup_systemd_service() {
    local env_name="$1"       # "blue" 或 "green"
    local target_dir="$2"
    local target_port="$3"
    local service_name=$(get_env_service "$env_name")

    log "=== 配置 systemd 服务: $service_name ==="

    local service_content="[Unit]
Description=链客宝AI Backend - ${env_name^} Environment
Documentation=https://github.com/your-org/liankebao
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=${target_dir}/backend
Environment=\"PATH=${target_dir}/backend/venv/bin\"
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${target_dir}/backend/venv/bin/uvicorn app.main:app \\
    --host 127.0.0.1 \\
    --port ${target_port} \\
    --workers 4 \\
    --log-level info \\
    --access-log \\
    --proxy-headers \\
    --forwarded-allow-ips=\"*\"
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=append:${target_dir}/logs/backend.log
StandardError=append:${target_dir}/logs/backend-error.log

[Install]
WantedBy=multi-user.target
"

    local service_file="/etc/systemd/system/${service_name}.service"
    echo "$service_content" | sudo tee "$service_file" > /dev/null
    sudo systemctl daemon-reload
    log "服务文件已创建: $service_file"
}

# ---- 启动指定环境的后端服务 ----
start_backend() {
    local env_name="$1"
    local service_name=$(get_env_service "$env_name")

    log "=== 启动后端服务: $service_name ==="

    local target_dir=$(get_env_dir "$env_name")
    mkdir -p "$target_dir/logs"

    # 先确保旧进程已停止
    if systemctl is-active --quiet "$service_name" 2>/dev/null; then
        log "服务 $service_name 已在运行，重启中..."
        sudo systemctl restart "$service_name"
    else
        log "启动服务 $service_name..."
        sudo systemctl enable "$service_name" 2>/dev/null || true
        sudo systemctl start "$service_name"
    fi

    log "后端服务 $service_name 已启动"
}

# ---- 停止指定环境的后端服务 ----
stop_backend() {
    local env_name="$1"
    local service_name=$(get_env_service "$env_name")

    if systemctl is-active --quiet "$service_name" 2>/dev/null; then
        log "停止服务: $service_name"
        sudo systemctl stop "$service_name"
        log "服务 $service_name 已停止"
    else
        log "服务 $service_name 未在运行，跳过"
    fi
}

# ---- 健康检查 ----
health_check() {
    local env_name="$1"
    local target_port=$(get_env_port "$env_name")
    local target_dir=$(get_env_dir "$env_name")

    if [[ "$SKIP_HEALTH" = true ]]; then
        warn "跳过健康检查（--skip-health）"
        return 0
    fi

    log "=== 健康检查 ($env_name, 端口: $target_port) ==="
    log "重试 ${HEALTH_RETRIES} 次，间隔 ${HEALTH_INTERVAL}s"

    local ok=false
    local response=""

    for i in $(seq 1 $HEALTH_RETRIES); do
        # 1) 检查 systemd 服务状态
        if ! systemctl is-active --quiet "$(get_env_service "$env_name")" 2>/dev/null; then
            if [[ $((i % 3)) -eq 0 ]]; then
                info "  等待 systemd 服务就绪... (尝试 $i/$HEALTH_RETRIES)"
            fi
            sleep $HEALTH_INTERVAL
            continue
        fi

        # 2) HTTP 健康检查
        response=$(curl -s "http://127.0.0.1:$target_port/health" 2>/dev/null || true)
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$target_port/health" 2>/dev/null || echo "000")

        if [[ "$http_code" == "200" ]]; then
            ok=true
            echo ""
            log "✓ 健康检查通过 (HTTP $http_code, 尝试 $i/$HEALTH_RETRIES)"
            echo -e "  ${CYAN}响应: $response${NC}"
            echo ""
            break
        fi

        info "  HTTP $http_code, 等待就绪... (尝试 $i/$HEALTH_RETRIES)"
        sleep $HEALTH_INTERVAL
    done

    if [[ "$ok" = false ]]; then
        echo ""
        error "✗ 健康检查失败 ($env_name, 端口: $target_port)"
        error "  最后响应: ${response:-无响应}"
        error "  检查日志: sudo journalctl -u $(get_env_service "$env_name") -n 50 --no-pager"
        error "  检查日志: sudo tail -50 $target_dir/logs/backend-error.log"
        echo ""
        return 1
    fi

    return 0
}

# ---- 切换 Nginx 到目标环境 ----
switch_nginx() {
    local env_name="$1"
    local target_port=$(get_env_port "$env_name")
    local target_dir=$(get_env_dir "$env_name")

    log "=== 切换 Nginx 到 $env_name (端口 $target_port) ==="

    # 1) 生成 Nginx active backend 配置文件
    local nginx_conf_dir=$(dirname "$NGINX_ACTIVE_BACKEND_CONF")
    sudo mkdir -p "$nginx_conf_dir"

    echo "# 链客宝AI蓝绿部署 - 活跃后端配置" | sudo tee "$NGINX_ACTIVE_BACKEND_CONF" > /dev/null
    echo "# 由 blue-green-deploy.sh 自动管理" | sudo tee -a "$NGINX_ACTIVE_BACKEND_CONF" > /dev/null
    echo "# 活跃环境: $env_name" | sudo tee -a "$NGINX_ACTIVE_BACKEND_CONF" > /dev/null
    echo "server 127.0.0.1:$target_port;" | sudo tee -a "$NGINX_ACTIVE_BACKEND_CONF" > /dev/null

    log "已生成 Nginx 配置: $NGINX_ACTIVE_BACKEND_CONF -> server 127.0.0.1:$target_port;"

    # 2) 更新 dist.active 符号链接
    if [[ -d "$target_dir/dist" ]]; then
        ln -sfn "$target_dir/dist" "$DIST_SYMLINK"
        log "更新 dist.active 符号链接 -> $target_dir/dist"
    fi

    # 3) 检查 Nginx 是否使用蓝绿配置
    local using_bluegreen=false
    if [[ -f "$NGINX_CONF" ]]; then
        if grep -q "nginx-bluegreen.conf\|chainke-active-backend\|blue-green" "$NGINX_CONF" 2>/dev/null; then
            using_bluegreen=true
        fi
    fi

    if ! $using_bluegreen; then
        log "当前 Nginx 未使用蓝绿配置，部署蓝绿配置..."
        if [[ -f "$NGINX_BLUEGREEN_CONF" ]]; then
            sudo cp "$NGINX_BLUEGREEN_CONF" "$NGINX_CONF"
            log "已部署蓝绿 Nginx 配置到 $NGINX_CONF"
        else
            warn "蓝绿 Nginx 配置不存在: $NGINX_BLUEGREEN_CONF"
        fi
    fi

    # 4) 验证并重载 Nginx
    if sudo nginx -t 2>&1; then
        sudo systemctl reload nginx || sudo nginx -s reload
        log "✓ Nginx 重载成功，流量已切换到 $env_name 环境"
        return 0
    else
        error "✗ Nginx 配置检查失败"
        error "  请手动检查: sudo nginx -t && sudo nginx -s reload"
        return 1
    fi
}

# ---- 发送告警 ----
send_alert() {
    local level="$1"    # WARNING / ERROR
    local message="$2"

    warn "=== 告警 [$level] $message ==="

    # 如果配置了钉钉 Webhook，发送通知
    local webhook="${DINGTALK_WEBHOOK:-}"
    if [[ -n "$webhook" ]]; then
        curl -s -X POST "$webhook" \
            -H "Content-Type: application/json" \
            -d "{
                \"msgtype\": \"text\",
                \"text\": {
                    \"content\": \"【链客宝AI蓝绿部署】[$level] $message\n时间: $(date '+%Y-%m-%d %H:%M:%S')\n服务器: 链客宝AI ECS\n环境: $ACTIVE -> $SWITCH_TARGET\"
                }
            }" > /dev/null 2>&1 || true
        log "  钉钉告警已发送"
    fi
}

# ---- 执行蓝绿切换 ----
perform_switch() {
    local target_env="$1"
    local current_active=$(get_active_env)

    if [[ "$target_env" == "$current_active" ]]; then
        log "目标环境 $target_env 已经是当前活跃环境，无需切换"
        return 0
    fi

    local target_dir=$(get_env_dir "$target_env")
    local target_port=$(get_env_port "$target_env")
    local target_svc=$(get_env_service "$target_env")

    echo ""
    echo "========================================"
    echo "  执行蓝绿切换"
    echo "  从: ${CYAN}${current_active^^}${NC} (端口 $(get_env_port "$current_active"))"
    echo "  到: ${GREEN}${target_env^^}${NC} (端口 $target_port)"
    echo "========================================"
    echo ""

    # 步骤 1: 确保目标环境已部署
    if [[ ! -d "$target_dir/backend" ]]; then
        error "目标目录 $target_dir 尚未部署，请先运行构建"
        return 1
    fi

    # 步骤 2: 启动目标环境后端
    start_backend "$target_env"

    # 步骤 3: 健康检查
    log "执行健康检查..."
    if ! health_check "$target_env"; then
        echo ""
        error "╔═══════════════════════════════════════════╗"
        error "║  健康检查失败！保留当前版本                ║"
        error "║  目标: $target_env (端口 $target_port)           ║"
        error "║  活跃: $current_active (端口 $(get_env_port "$current_active"))            ║"
        error "╚═══════════════════════════════════════════╝"
        echo ""
        send_alert "ERROR" "蓝绿部署健康检查失败: $target_env (端口 $target_port)"
        return 1
    fi

    # 步骤 4: 切换 Nginx
    log "健康检查通过，切换 Nginx..."
    if ! switch_nginx "$target_env"; then
        error "Nginx 切换失败！"
        send_alert "ERROR" "Nginx 切换失败，请手动排查"
        return 1
    fi

    # 步骤 5: 更新状态
    local old_active="$current_active"
    ACTIVE="$target_env"
    PREVIOUS="$old_active"
    save_state

    # 步骤 6: 停止旧环境后端（节省资源）
    log "等待 ${HEALTH_INTERVAL}s 确认新环境稳定后，停止旧环境..."
    sleep $HEALTH_INTERVAL

    # 二次健康检查：确认新环境仍然健康
    if health_check "$target_env"; then
        log "新环境稳定，停止旧环境 $old_active..."
        stop_backend "$old_active"
    else
        warn "新环境不稳定，保留旧环境 $old_active 作为备用"
    fi

    echo ""
    echo "========================================"
    echo -e "  ${GREEN}✓ 蓝绿切换完成!${NC}"
    echo "  当前活跃: ${target_env^^}"
    echo "  备  用:   ${old_active^^}"
    echo "  前端:     $DIST_SYMLINK -> $(readlink "$DIST_SYMLINK" 2>/dev/null || echo 'N/A')"
    echo "========================================"
    echo ""

    return 0
}

# ---- 构建到非活跃环境 ----
build_to_inactive() {
    local inactive=$(get_inactive_env)
    local inactive_dir=$(get_env_dir "$inactive")
    local inactive_port=$(get_env_port "$inactive")

    echo ""
    echo "========================================"
    echo "  部署构建到: ${CYAN}${inactive^^}${NC}"
    echo "  目录: $inactive_dir"
    echo "  端口: $inactive_port"
    echo "========================================"
    echo ""

    # 1. 拉取代码
    git_pull_to_dir "$inactive_dir"

    # 2. 构建前端
    build_frontend "$inactive_dir"

    # 3. 部署后端
    deploy_backend "$inactive_dir" "$inactive_port"

    # 4. 配置 systemd 服务
    setup_systemd_service "$inactive" "$inactive_dir" "$inactive_port"

    log "部署构建完成 — 所有代码已就绪在 $inactive 环境"
}

# ---- 回滚操作 ----
do_rollback() {
    load_state

    local previous_env="$PREVIOUS"
    local current_active="$ACTIVE"

    if [[ "$previous_env" == "$current_active" ]]; then
        error "无法回滚：PREVIOUS 和 ACTIVE 相同（没有切换记录）"
        return 1
    fi

    local previous_dir=$(get_env_dir "$previous_env")
    if [[ ! -d "$previous_dir/backend" ]]; then
        error "无法回滚：目标目录 $previous_dir 不存在或未部署"
        error "请先手动部署到 $previous_env 环境再尝试回滚"
        return 1
    fi

    echo ""
    echo "========================================"
    echo "  执行回滚"
    echo "  从: ${CYAN}${current_active^^}${NC}"
    echo "  到: ${GREEN}${previous_env^^}${NC}"
    echo "========================================"
    echo ""

    log "=== 执行回滚: $current_active -> $previous_env ==="

    # 1. 启动目标环境
    start_backend "$previous_env"

    # 2. 健康检查
    if ! health_check "$previous_env"; then
        error "回滚目标 $previous_env 健康检查失败"
        send_alert "ERROR" "蓝绿回滚失败: $previous_env 健康检查未通过"
        return 1
    fi

    # 3. 切换 Nginx
    if ! switch_nginx "$previous_env"; then
        error "回滚时 Nginx 切换失败"
        return 1
    fi

    # 4. 更新状态
    ACTIVE="$previous_env"
    PREVIOUS="$current_active"
    save_state

    # 5. 停止旧环境
    sleep $HEALTH_INTERVAL
    stop_backend "$current_active"

    echo ""
    echo "========================================"
    echo -e "  ${GREEN}✓ 回滚完成!${NC}"
    echo "  当前活跃: ${previous_env^^}"
    echo "  备  用:   ${current_active^^}"
    echo "========================================"
    echo ""

    log "回滚成功: $current_active -> $previous_env"
    send_alert "INFO" "蓝绿部署回滚完成: $current_active -> $previous_env"
}

# ---- 前置检查 ----
pre_check() {
    log "=== 前置检查 ==="

    if [[ $EUID -ne 0 ]]; then
        warn "建议使用 sudo 运行此脚本以获得完整功能"
    fi

    for cmd in git npm python3 nginx systemctl curl rsync; do
        if ! command -v $cmd &>/dev/null; then
            warn "命令 $cmd 不可用（某些功能可能受限）"
        fi
    done

    log "前置检查完成"
}

# ---- 主流程 ----
main() {
    echo ""
    echo "======================================="
    echo "   链客宝AI 蓝绿部署系统"
    echo "   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "======================================="
    echo ""

    ensure_dirs
    load_state

    # ---- 仅查看状态 ----
    if [[ "$STATUS_MODE" = true ]]; then
        show_status
        exit 0
    fi

    # ---- 回滚模式 ----
    if [[ "$ROLLBACK_MODE" = true ]]; then
        acquire_lock
        pre_check
        do_rollback
        exit $?
    fi

    # ---- 空参数 ----
    if [[ -z "$SWITCH_TARGET" ]]; then
        warn "请指定 --switch-to 或 --rollback 或 --status"
        echo ""
        usage
        exit 1
    fi

    # ---- 解析 target ----
    case "$SWITCH_TARGET" in
        blue|green)
            TARGET_ENV="$SWITCH_TARGET"
            ;;
        auto)
            TARGET_ENV=$(get_inactive_env)
            log "自动选择非活跃环境: $TARGET_ENV"
            ;;
        *)
            error "无效的目标环境: $SWITCH_TARGET (可选: blue, green, auto)"
            exit 1
            ;;
    esac

    # ---- 验证参数一致 ----
    if [[ "$TARGET_ENV" == "$(get_active_env)" ]] && [[ "$SWITCH_TARGET" != "auto" ]]; then
        warn "目标环境 $TARGET_ENV 已经是活跃环境"
        log "如需强制重新部署，先用 --switch-to 切换到另一个环境"
        exit 0
    fi

    acquire_lock
    pre_check

    # ---- 执行蓝绿部署 ----
    local start_time=$(date +%s)

    # 步骤 1: 构建到非活跃环境
    build_to_inactive

    # 步骤 2: 执行切换
    if ! perform_switch "$TARGET_ENV"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        error "蓝绿部署失败 (耗时: ${duration}s)"
        send_alert "ERROR" "蓝绿部署失败，已保留原环境 $(get_active_env)"

        echo ""
        echo "======================================="
        echo "  部署失败摘要"
        echo "======================================="
        echo "  状态:   ${RED}失败${NC}"
        echo "  当前:   $(get_active_env) (保留)"
        echo "  目标:   $TARGET_ENV (失败)"
        echo "  耗时:   ${duration}s"
        echo "  日志:   $LOG_FILE"
        echo "======================================="
        echo ""

        exit 1
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    echo "======================================="
    echo "  部署成功摘要"
    echo "======================================="
    echo "  状态:   ${GREEN}成功${NC}"
    echo "  活跃:   ${GREEN}$(get_active_env)${NC}"
    echo "  备用:   $(get_inactive_env)"
    echo "  耗时:   ${duration}s"
    echo "  日志:   $LOG_FILE"
    echo "======================================="
    echo ""

    send_alert "INFO" "蓝绿部署成功: $(get_active_env) (耗时 ${duration}s)"
    log "✓ 蓝绿部署完成"
}

main "$@"
