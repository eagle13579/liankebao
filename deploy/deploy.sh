#!/bin/bash
# ============================================================
# 链客宝 部署脚本
# 服务器: 阿里云 ECS (47.100.160.250)
# 用途: 前端构建 + 后端部署 + 服务重启
# ============================================================
set -e

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---- 路径配置 ----
PROJECT_DIR="/opt/liankebao"
BACKEND_DIR="$PROJECT_DIR/backend"
DIST_DIR="$PROJECT_DIR/dist"
VENV_DIR="$BACKEND_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
NGINX_CONF="$PROJECT_DIR/nginx.conf"

# ---- 服务配置 ----
UVICORN_PORT=8000
BACKEND_HOST="127.0.0.1"

# ---- 日志函数 ----
log()  { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error(){ echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

# ---- 帮助信息 ----
usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  --skip-frontend    跳过前端构建"
    echo "  --skip-backend     跳过后端部署"
    echo "  --skip-nginx       跳过nginx配置"
    echo "  --restart-only     只重启服务（不更新代码）"
    echo "  --help             显示帮助信息"
    exit 0
}

# ---- 参数解析 ----
SKIP_FRONTEND=false
SKIP_BACKEND=false
SKIP_NGINX=false
RESTART_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-frontend) SKIP_FRONTEND=true ;;
        --skip-backend)  SKIP_BACKEND=true ;;
        --skip-nginx)    SKIP_NGINX=true ;;
        --restart-only)  RESTART_ONLY=true ;;
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

# ---- 前端构建 ----
build_frontend() {
    if [[ "$SKIP_FRONTEND" = true ]]; then
        warn "跳过前端构建"
        return 0
    fi

    log "=== 前端构建 ==="

    cd "$PROJECT_DIR"

    if [[ ! -f "package.json" ]]; then
        error "package.json 不存在，无法构建前端"
        return 1
    fi

    log "安装前端依赖..."
    npm ci 2>&1 | tail -5

    log "构建前端..."
    npm run build 2>&1 | tail -10

    # 检查构建产物
    if [[ -f "$DIST_DIR/index.html" ]]; then
        log "前端构建成功: $DIST_DIR"
    else
        error "前端构建产物缺失 index.html"
        return 1
    fi
}

# ---- 后端部署 ----
deploy_backend() {
    if [[ "$SKIP_BACKEND" = true ]]; then
        warn "跳过后端部署"
        return 0
    fi

    log "=== 后端部署 ==="

    cd "$BACKEND_DIR"

    # 创建虚拟环境
    if [[ ! -d "$VENV_DIR" ]]; then
        log "创建 Python 虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi

    # 激活虚拟环境并安装依赖
    source "$VENV_DIR/bin/activate"

    log "安装 Python 依赖..."
    pip install --upgrade pip -q
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt -q
    fi

    deactivate
    log "后端依赖安装完成"
}

# ---- Nginx 配置 ----
configure_nginx() {
    if [[ "$SKIP_NGINX" = true ]]; then
        warn "跳过 nginx 配置"
        return 0
    fi

    log "=== Nginx 配置 ==="

    # 检查 SSL 证书是否存在
    if [[ -f "/etc/letsencrypt/live/liankebao.top/fullchain.pem" ]]; then
        log "SSL 证书已存在"
    else
        warn "SSL 证书不存在，需执行: sudo certbot --nginx -d liankebao.top -d www.liankebao.top"
    fi

    # 复制 nginx 配置
    if [[ -f "$NGINX_CONF" ]]; then
        sudo cp "$NGINX_CONF" /etc/nginx/nginx.conf
        log "nginx.conf 已部署到 /etc/nginx/nginx.conf"
    else
        warn "nginx.conf 不存在于 $NGINX_CONF"
    fi

    # 检查并重载 nginx
    if sudo nginx -t; then
        sudo systemctl reload nginx || sudo systemctl restart nginx
        log "Nginx 重载成功"
    else
        error "Nginx 配置检查失败"
        return 1
    fi
}

# ---- Systemd 服务配置 ----
setup_systemd_service() {
    log "=== Systemd 服务配置 ==="

    SERVICE_FILE="$PROJECT_DIR/chainke.service"

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

    # 重启后端
    if systemctl is-active --quiet chainke; then
        log "重启 chainke.service..."
        sudo systemctl restart chainke
    else
        log "启动 chainke.service..."
        sudo systemctl start chainke
    fi

    # 检查后端状态
    sleep 2
    if systemctl is-active --quiet chainke; then
        log "后端服务运行中"
    else
        error "后端服务启动失败，检查日志: sudo journalctl -u chainke -n 50"
        return 1
    fi

    # 检查后端健康端点
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$UVICORN_PORT/health | grep -q 200; then
        log "后端健康检查通过 (HTTP 200)"
    else
        warn "后端健康检查失败，请手动排查"
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
    else
        echo -e "  前端:      ${RED}缺失${NC}"
    fi

    # 检查 SSL
    if [[ -f "/etc/letsencrypt/live/liankebao.top/fullchain.pem" ]]; then
        local expiry=$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/liankebao.top/fullchain.pem 2>/dev/null | cut -d= -f2)
        echo -e "  SSL证书:   ${GREEN}$expiry${NC}"
    else
        echo -e "  SSL证书:   ${YELLOW}未配置${NC}"
    fi

    echo ""
    info "===================================="
    echo ""
    log "部署完成！"
}

# ---- 主流程 ----
main() {
    echo ""
    echo "======================================"
    echo "   链客宝 一键部署脚本"
    echo "   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "======================================"
    echo ""

    if [[ "$RESTART_ONLY" = true ]]; then
        log "仅重启服务模式"
        setup_systemd_service
        restart_services
        verify_deployment
        exit 0
    fi

    pre_check
    build_frontend
    deploy_backend
    setup_systemd_service
    restart_services
    configure_nginx
    verify_deployment
}

main "$@"
