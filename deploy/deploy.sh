#!/bin/bash
# ============================================================
# 链客宝 部署脚本
# 服务器: 阿里云 ECS (47.100.160.250)
# 用途: 从Git拉取最新代码 + 构建前端 + 部署后端 + 服务重启
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
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/liankebao-weapp"
DIST_DIR="$PROJECT_DIR/dist"
VENV_DIR="$BACKEND_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
NGINX_CONF="$PROJECT_DIR/deploy/nginx.conf"
NGINX_SECURITY_CONF="$PROJECT_DIR/deploy/nginx_security.conf"
NGINX_SSL_RENEW_SCRIPT="$PROJECT_DIR/deploy/ssl_auto_renew.sh"
SERVICE_FILE="$PROJECT_DIR/deploy/chainke.service"

# ---- Git 配置（auto_deploy.sh 使用）----
GIT_REMOTE="origin"
GIT_BRANCH="master"

# ---- 服务配置 ----
UVICORN_PORT=8001
BACKEND_HOST="127.0.0.1"
HEALTH_RETRIES=10
HEALTH_INTERVAL=2

# ---- .env 加载 ----
ENV_FILE="$PROJECT_DIR/.env"

load_env() {
    if [[ -f "$ENV_FILE" ]]; then
        log "加载环境变量: $ENV_FILE"
        set -a  # 自动 export 所有 source 的变量
        source "$ENV_FILE"
        set +a
        ok ".env 已加载 ($(wc -l < "$ENV_FILE") 行)"
    else
        warn ".env 文件不存在: $ENV_FILE"
        warn "请先运行: sudo bash $PROJECT_DIR/deploy/setup_env.sh"
        warn "或手动创建 $ENV_FILE (可参考 $PROJECT_DIR/deploy/.env.example)"
    fi
}

# ---- 日志函数 ----
log()  { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error(){ echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

# ---- 帮助信息 ----
usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  --skip-frontend    跳过前端构建（CI中已构建时使用）"
    echo "  --skip-backend     跳过后端部署"
    echo "  --skip-nginx       跳过nginx配置"
    echo "  --skip-git-pull    跳过git拉取（本地已是最新时使用）"
    echo "  --restart-only     只重启服务（不更新代码）"
    echo "  --branch=<name>    指定git分支（默认: master）"
    echo "  --help             显示帮助信息"
    exit 0
}

# ---- 参数解析 ----
SKIP_FRONTEND=false
SKIP_BACKEND=false
SKIP_NGINX=false
SKIP_GIT_PULL=false
RESTART_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-frontend) SKIP_FRONTEND=true ;;
        --skip-backend)  SKIP_BACKEND=true ;;
        --skip-nginx)    SKIP_NGINX=true ;;
        --skip-git-pull) SKIP_GIT_PULL=true ;;
        --restart-only)  RESTART_ONLY=true ;;
        --branch=*)      GIT_BRANCH="${1#*=}" ;;
        --help)          usage ;;
        *)               warn "Unknown option: $1"; usage ;;
    esac
    shift
done

# ---- 前置检查 ----
pre_check() {
    log "=== 前置检查 ==="

    if [[ $EUID -eq 0 ]]; then
        warn "正在以 root 用户执行，建议使用普通用户 + sudo"
    fi

    # 检查必要命令
    for cmd in git node npm python3 nginx systemctl; do
        if ! command -v $cmd &>/dev/null; then
            error "缺少必要命令: $cmd"
            exit 1
        fi
    done

    # 创建目录
    mkdir -p "$DIST_DIR" "$LOG_DIR"

    log "前置检查通过"
}

# ---- 从 Git 拉取最新代码 ----
git_pull_code() {
    if [[ "$SKIP_GIT_PULL" = true ]] || [[ "$RESTART_ONLY" = true ]]; then
        warn "跳过 Git 拉取"
        return 0
    fi

    log "=== 从 Git 拉取最新代码 ==="

    if [[ ! -d "$PROJECT_DIR/.git" ]]; then
        # 首次部署：需要手动 git clone
        warn "项目目录 $PROJECT_DIR 不是 Git 仓库"
        warn "请先执行: sudo git clone <repo-url> $PROJECT_DIR"
        warn "然后重新运行此脚本"
        return 1
    fi

    cd "$PROJECT_DIR"

    log "拉取 $GIT_BRANCH 分支..."
    git fetch "$GIT_REMOTE" "$GIT_BRANCH"
    git reset --hard "$GIT_REMOTE/$GIT_BRANCH"
    git clean -fd

    log "代码已更新到最新 (commit: $(git rev-parse --short HEAD))"
}

# ---- 前端构建 ----
build_frontend() {
    if [[ "$SKIP_FRONTEND" = true ]]; then
        warn "跳过前端构建"
        return 0
    fi

    log "=== 前端构建 ==="

    cd "$PROJECT_DIR"

    # 优先检查根目录 package.json，然后 liankebao-weapp
    if [[ -f "package.json" ]]; then
        log "使用根目录 package.json 构建"
        FRONTEND_PKG_DIR="$PROJECT_DIR"
    elif [[ -d "$FRONTEND_DIR" ]] && [[ -f "$FRONTEND_DIR/package.json" ]]; then
        log "使用前端目录 $FRONTEND_DIR 构建"
        FRONTEND_PKG_DIR="$FRONTEND_DIR"
    else
        warn "package.json 不存在，跳过前端构建"
        return 0
    fi

    cd "$FRONTEND_PKG_DIR"

    log "安装前端依赖..."
    npm ci 2>&1 | tail -5

    # 检查并执行构建命令
    log "构建前端..."
    if grep -q '"build:weapp"' package.json 2>/dev/null; then
        npm run build:weapp 2>&1 | tail -10
    elif grep -q '"build"' package.json 2>/dev/null; then
        npm run build 2>&1 | tail -10
    else
        warn "package.json 中未找到 build 命令"
        return 0
    fi

    # 检查构建产物（支持 dist/ 或 build/ 目录）
    if [[ -f "dist/index.html" ]]; then
        # 复制到统一 dist 目录
        if [[ "$FRONTEND_PKG_DIR" != "$PROJECT_DIR" ]]; then
            cp -r dist/* "$DIST_DIR/" 2>/dev/null || true
        fi
        log "前端构建成功: dist/index.html"
    elif [[ -f "build/index.html" ]]; then
        log "前端构建成功: build/index.html"
    else
        # Taro 小程序构建可能不生成 index.html
        if [[ -d "dist" ]]; then
            log "前端构建完成 (dist 目录存在，非标准 web 构建)"
        else
            warn "未检测到构建产物，请确认构建命令正确"
        fi
    fi
}

# ---- 后端部署 ----
deploy_backend() {
    if [[ "$SKIP_BACKEND" = true ]]; then
        warn "跳过后端部署"
        return 0
    fi

    log "=== 后端部署 ==="

    if [[ ! -d "$BACKEND_DIR" ]]; then
        error "后端目录 $BACKEND_DIR 不存在"
        return 1
    fi

    cd "$BACKEND_DIR"

    # 创建虚拟环境
    if [[ ! -d "$VENV_DIR" ]]; then
        log "创建 Python 虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi

    # 激活虚拟环境并安装依赖
    source "$VENV_DIR/bin/activate"

    log "升级 pip..."
    pip install --upgrade pip -q

    if [[ -f "requirements.txt" ]]; then
        log "安装 Python 依赖..."
        pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q
    fi

    deactivate
    log "后端依赖安装完成 (venv: $VENV_DIR)"
}

# ---- Nginx 配置 ----
configure_nginx() {
    if [[ "$SKIP_NGINX" = true ]]; then
        warn "跳过 nginx 配置"
        return 0
    fi

    log "=== Nginx 配置 ==="

    # ---- SSL 证书检查 ----
    SSL_CERT="/etc/letsencrypt/live/liankebao.top/fullchain.pem"
    SSL_KEY="/etc/letsencrypt/live/liankebao.top/privkey.pem"

    if [[ -f "$SSL_CERT" ]]; then
        local expiry=$(openssl x509 -enddate -noout -in "$SSL_CERT" 2>/dev/null | cut -d= -f2)
        local expiry_epoch=$(date -d "$expiry" +%s 2>/dev/null)
        local now_epoch=$(date +%s)
        local days_left=$(( (expiry_epoch - now_epoch) / 86400 ))
        log "SSL 证书存在，到期: $expiry（剩余 ${days_left} 天）"

        if [[ "$days_left" -lt 7 ]]; then
            warn "⚠ SSL 证书将在 ${days_left} 天后到期！请尽快续签！"
            warn "  运行: sudo bash $NGINX_SSL_RENEW_SCRIPT --force"
        elif [[ "$days_left" -lt 30 ]]; then
            warn "SSL 证书剩余 ${days_left} 天，建议安排续签"
        fi
    else
        warn "SSL 证书不存在 ($SSL_CERT)"
        warn "需执行: sudo certbot --nginx -d liankebao.top -d www.liankebao.top"
    fi

    # 检查密钥文件权限（最低权限 600）
    if [[ -f "$SSL_KEY" ]]; then
        local key_perm=$(stat -c "%a" "$SSL_KEY" 2>/dev/null || stat -f "%Lp" "$SSL_KEY" 2>/dev/null)
        if [[ "$key_perm" != "600" ]] && [[ "$key_perm" != "400" ]]; then
            warn "SSL 密钥文件权限为 $key_perm，建议设为 600"
            info "执行: sudo chmod 600 $SSL_KEY"
        fi
    fi

    # ---- 部署 nginx 主配置（注入安全配置 include）----
    if [[ -f "$NGINX_CONF" ]]; then
        # 先复制一份临时配置，注入 security.conf 的 include
        local tmp_conf=$(mktemp)
        cp "$NGINX_CONF" "$tmp_conf"

        # 检查是否已经包含了 security.conf
        if ! grep -q "nginx_security.conf" "$tmp_conf"; then
            # 在 http 块末尾的最后一个 } 之前插入 include
            # 找到 http 块中最后一个 }（即 http 块的结束符）
            awk '
            /^http \{/ { http_open=1; print; next }
            http_open && /^\}$/ {
                http_open=0
                print "    # 安全加固配置（自动注入）"
                print "    include /etc/nginx/nginx_security.conf;"
                print "}"
                next
            }
            { print }
            ' "$tmp_conf" > "${tmp_conf}.new" && mv "${tmp_conf}.new" "$tmp_conf"
            log "已注入 include nginx_security.conf 到 http 块"
        fi

        sudo cp "$tmp_conf" /etc/nginx/nginx.conf
        rm -f "$tmp_conf"
        log "nginx.conf 已部署到 /etc/nginx/nginx.conf"
    else
        warn "nginx.conf 不存在于 $NGINX_CONF"
    fi

    # ---- 部署安全配置 ----
    if [[ -f "$NGINX_SECURITY_CONF" ]]; then
        sudo cp "$NGINX_SECURITY_CONF" /etc/nginx/nginx_security.conf
        sudo chmod 644 /etc/nginx/nginx_security.conf
        log "nginx_security.conf 已部署到 /etc/nginx/nginx_security.conf"
    else
        warn "nginx_security.conf 不存在，跳过安全配置部署"
    fi

    # ---- 部署 SSL 自动续签脚本 ----
    if [[ -f "$NGINX_SSL_RENEW_SCRIPT" ]]; then
        sudo cp "$NGINX_SSL_RENEW_SCRIPT" /etc/nginx/ssl_auto_renew.sh
        sudo chmod +x /etc/nginx/ssl_auto_renew.sh
        log "ssl_auto_renew.sh 已部署到 /etc/nginx/ssl_auto_renew.sh"
    fi

    # ---- 验证并重载 nginx ----
    if sudo nginx -t; then
        sudo systemctl reload nginx || sudo systemctl restart nginx
        log "✓ Nginx 重载成功"
    else
        error "✗ Nginx 配置检查失败: sudo nginx -t"
        error "请手动检查: sudo nginx -t && sudo nginx -s reload"
        return 1
    fi
}

# ---- Systemd 服务配置 ----
setup_systemd_service() {
    log "=== Systemd 服务配置 ==="

    if [[ -f "$SERVICE_FILE" ]]; then
        sudo cp "$SERVICE_FILE" /etc/systemd/system/chainke.service
        sudo systemctl daemon-reload
        log "chainke.service 已更新"
    else
        error "chainke.service 不存在于 $SERVICE_FILE"
        return 1
    fi
}

# ---- 重启服务 ----
restart_services() {
    log "=== 重启服务 ==="

    # 杀掉旧进程（防止端口冲突）
    if lsof -i :$UVICORN_PORT &>/dev/null 2>&1; then
        warn "端口 $UVICORN_PORT 被占用，清理旧进程..."
        sudo fuser -k "${UVICORN_PORT}/tcp" 2>/dev/null || true
        sleep 1
    fi

    # 重启后端
    if systemctl is-active --quiet chainke; then
        log "重启 chainke.service..."
        sudo systemctl restart chainke
    else
        log "启动 chainke.service..."
        sudo systemctl start chainke
    fi

    # 等待后端就绪（带重试）
    log "等待后端就绪..."
    local ready=false
    for i in $(seq 1 $HEALTH_RETRIES); do
        sleep $HEALTH_INTERVAL
        if systemctl is-active --quiet chainke; then
            if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$UVICORN_PORT/health | grep -q 200; then
                ready=true
                log "后端服务已就绪 (尝试 $i/$HEALTH_RETRIES)"
                break
            fi
        fi
        info "  等待中... (尝试 $i/$HEALTH_RETRIES)"
    done

    if [[ "$ready" = true ]]; then
        log "✓ 后端健康检查通过 (HTTP 200)"
    else
        error "后端服务启动失败，检查日志:"
        error "  sudo journalctl -u chainke -n 50 --no-pager"
        error "  sudo tail -100 $LOG_DIR/backend-error.log"
        return 1
    fi

    # 重启 nginx
    if sudo nginx -t; then
        sudo systemctl reload nginx || sudo systemctl restart nginx
        log "Nginx 重载成功"
    fi
}

# ---- 部署后验证 ----
verify_deployment() {
    log "=== 部署验证 ==="

    echo ""
    info "========== 链客宝部署状态 =========="
    echo ""

    # 检查 nginx
    if systemctl is-active --quiet nginx; then
        echo -e "  Nginx:     ${GREEN}运行中${NC}"
    else
        echo -e "  Nginx:     ${RED}未运行${NC}"
    fi

    # 检查后端
    if systemctl is-active --quiet chainke; then
        echo -e "  后端:      ${GREEN}运行中${NC}"
    else
        echo -e "  后端:      ${RED}未运行${NC}"
    fi

    # 检查前端
    if [[ -f "$DIST_DIR/index.html" ]]; then
        echo -e "  前端:      ${GREEN}构建产物就绪${NC}"
    elif [[ -f "$PROJECT_DIR/dist/index.html" ]]; then
        echo -e "  前端:      ${GREEN}构建产物就绪 (PROJECT_DIR/dist)${NC}"
    elif [[ -d "$FRONTEND_DIR/dist" ]]; then
        echo -e "  前端:      ${GREEN}构建产物就绪 (FRONTEND_DIR/dist)${NC}"
    else
        echo -e "  前端:      ${YELLOW}未检测到标准构建产物${NC}"
    fi

    # 检查 SSL 证书
    SSL_CERT="/etc/letsencrypt/live/liankebao.top/fullchain.pem"
    if [[ -f "$SSL_CERT" ]]; then
        local expiry=$(openssl x509 -enddate -noout -in "$SSL_CERT" 2>/dev/null | cut -d= -f2)
        local expiry_epoch=$(date -d "$expiry" +%s 2>/dev/null)
        local now_epoch=$(date +%s)
        local days_left=$(( (expiry_epoch - now_epoch) / 86400 ))
        if [[ "$days_left" -lt 7 ]]; then
            echo -e "  SSL证书:   ${RED}$expiry（仅剩${days_left}天！）${NC}"
        else
            echo -e "  SSL证书:   ${GREEN}$expiry${NC}"
        fi
    else
        echo -e "  SSL证书:   ${YELLOW}未配置${NC}"
    fi

    # 检查安全配置是否已注入
    if grep -q "nginx_security.conf" /etc/nginx/nginx.conf 2>/dev/null; then
        echo -e "  安全加固:  ${GREEN}已启用${NC}"
    else
        echo -e "  安全加固:  ${YELLOW}未注入${NC}（需运行 sudo nginx -s reload）"
    fi

    # 检查续签脚本
    if [[ -f "/etc/nginx/ssl_auto_renew.sh" ]]; then
        echo -e "  续签脚本:  ${GREEN}已部署${NC}"
    else
        echo -e "  续签脚本:  ${YELLOW}未部署${NC}"
    fi

    # 检查 .env 是否就绪
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        echo -e "  .env:      ${GREEN}已配置${NC}"
    else
        echo -e "  .env:      ${YELLOW}未配置${NC}"
    fi

    # 磁盘使用率
    local disk_usage=$(df -h / | awk 'NR==2 {print $5}')
    echo -e "  磁盘使用:  ${CYAN}${disk_usage}${NC}"

    echo ""
    info "===================================="
    echo ""

    # 最终摘要
    if systemctl is-active --quiet nginx && systemctl is-active --quiet chainke; then
        log "✓ 部署完成！所有核心服务运行正常"
    else
        warn "⚠ 部署完成，但部分服务异常，请手动排查"
    fi
}

# ---- Hermes 特有：检查 logout 残留 ----
check_logout_residue() {
    log "=== 检查 logout 残留 (Hermes 特有) ==="
    if grep -rn "logout" --include="*.py" "$PROJECT_DIR" 2>/dev/null; then
        error "发现 logout 残留文本！"
        # 自动清理
        python3 -c "
import os
for root, dirs, files in os.walk('$PROJECT_DIR'):
    dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', 'node_modules', '.git')]
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                c = fp.read()
            if 'logout' in c:
                open(path, 'w', encoding='utf-8').write(c.replace('logout\n', '').replace('logout', ''))
                print(f'  cleaned: {path}')
"
        log "已自动清理 logout 残留"
    else
        log "✓ 未发现 logout 残留"
    fi
}

# ---- 主流程 ----
main() {
    echo ""
    echo "======================================="
    echo "   链客宝 一键部署脚本"
    echo "   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "======================================="
    echo ""

    # 加载环境变量（必须在任何子命令之前）
    load_env

    if [[ "$RESTART_ONLY" = true ]]; then
        log "仅重启服务模式"
        setup_systemd_service
        restart_services
        verify_deployment
        exit 0
    fi

    check_logout_residue
    pre_check
    git_pull_code
    build_frontend
    deploy_backend
    setup_systemd_service
    restart_services
    configure_nginx
    verify_deployment
}

main "$@"
