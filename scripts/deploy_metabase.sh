#!/bin/bash
# ============================================================
# 链客宝 Metabase 自动部署脚本
# ============================================================
# 用途: 使用 Docker 部署 Metabase 数据分析平台
#       自动连接链客宝 PostgreSQL 数据库
#       预置 5 个常用分析问题
#
# 前置条件:
#   - Docker & Docker Compose 已安装
#   - .env 文件存在并包含 PG_URL 或 PG_* 变量
#
# 使用方法:
#   bash deploy_metabase.sh            # 部署 Metabase
#   bash deploy_metabase.sh --stop     # 停止 Metabase
#   bash deploy_metabase.sh --restart  # 重启 Metabase
#   bash deploy_metabase.sh --logs     # 查看日志
#   bash deploy_metabase.sh --status   # 查看运行状态
# ============================================================

set -e

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

# ---- 路径配置 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
METABASE_CONTAINER="chainke-metabase"
METABASE_PORT=3001
METABASE_IMAGE="metabase/metabase:latest"
METABASE_DATA_DIR="$PROJECT_DIR/data/metabase"

# ---- 加载 .env ----
load_env() {
    if [[ -f "$ENV_FILE" ]]; then
        log "加载环境变量: $ENV_FILE"
        set -a
        source "$ENV_FILE"
        set +a
    else
        warn ".env 文件不存在: $ENV_FILE"
        warn "将使用默认环境变量（可能无法连接数据库）"
    fi
}

# ---- 前置检查 ----
pre_check() {
    log "=== 前置检查 ==="

    # 检查 Docker
    if ! command -v docker &>/dev/null; then
        error "Docker 未安装！请先安装 Docker:"
        error "  curl -fsSL https://get.docker.com | bash"
        exit 1
    fi

    # 检查 Docker 是否运行
    if ! docker info &>/dev/null 2>&1; then
        error "Docker 守护进程未运行！"
        error "  sudo systemctl start docker"
        exit 1
    fi

    log "Docker 版本: $(docker --version)"
    log "前置检查通过"
}

# ---- 准备数据目录 ----
prepare_dirs() {
    mkdir -p "$METABASE_DATA_DIR"
    log "Metabase 数据目录: $METABASE_DATA_DIR"
}

# ---- 构建数据库连接参数 ----
get_db_url() {
    local pg_url="${PG_URL:-$DATABASE_URL}"

    if [[ -n "$pg_url" ]]; then
        echo "$pg_url"
        return 0
    fi

    # 从 PG_* 变量拼装
    local host="${PG_HOST:-localhost}"
    local port="${PG_PORT:-5432}"
    local user="${PG_USER:-postgres}"
    local password="${PG_PASSWORD:-}"
    local database="${PG_DATABASE:-chainke}"

    if [[ -n "$password" ]]; then
        echo "postgres://${user}:${password}@${host}:${port}/${database}"
    else
        echo "postgres://${user}@${host}:${port}/${database}"
    fi
}

# ---- 拉取 Metabase 镜像 ----
pull_image() {
    log "拉取 Metabase Docker 镜像..."
    docker pull "$METABASE_IMAGE" 2>&1 | tail -3
    log "镜像拉取完成"
}

# ---- 启动 Metabase ----
start_metabase() {
    log "=== 启动 Metabase ==="

    # 检查是否已运行
    if docker ps --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        warn "Metabase 容器已在运行中！"
        info "  访问地址: http://localhost:${METABASE_PORT}"
        info "  如需重启: bash $0 --restart"
        return 0
    fi

    # 如果容器存在但已停止，删除重新创建
    if docker ps -a --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        log "删除已停止的 Metabase 容器..."
        docker rm "$METABASE_CONTAINER" > /dev/null
    fi

    # 获取数据库连接
    local db_url
    db_url=$(get_db_url)
    log "数据库连接: ${db_url//:*@/:****@}"  # 脱敏打印

    # 启动 Metabase
    log "启动 Metabase 容器..."
    docker run -d \
        --name "$METABASE_CONTAINER" \
        -p "${METABASE_PORT}:3000" \
        -v "${METABASE_DATA_DIR}:/metabase.db" \
        -e "MB_DB_TYPE=postgres" \
        -e "MB_DB_DBNAME=chainke_metabase" \
        -e "MB_DB_HOST=${PG_HOST:-localhost}" \
        -e "MB_DB_PORT=${PG_PORT:-5432}" \
        -e "MB_DB_USER=${PG_USER:-postgres}" \
        -e "MB_DB_PASS=${PG_PASSWORD:-}" \
        -e "MB_JETTY_PORT=3000" \
        -e "MB_SITE_LOCALE=zh" \
        --restart unless-stopped \
        "$METABASE_IMAGE"

    log "Metabase 容器启动中..."

    # 等待就绪
    local retries=30
    local ready=false
    for i in $(seq 1 $retries); do
        sleep 2
        if curl -s -o /dev/null -w "%{http_code}" "http://localhost:${METABASE_PORT}/api/health" 2>/dev/null | grep -q 200; then
            ready=true
            break
        fi
        if [[ $((i % 5)) -eq 0 ]]; then
            info "  等待中... (${i}s)"
        fi
    done

    if [[ "$ready" = true ]]; then
        log "✓ Metabase 启动成功！"
    else
        warn "Metabase 启动中，请稍后检查状态"
        warn "  查看日志: bash $0 --logs"
    fi

    # 保存数据库连接信息到提示文件
    cat > "$METABASE_DATA_DIR/README.txt" << EOF
链客宝 Metabase 部署信息
=========================
访问地址: http://localhost:${METABASE_PORT}
首次使用: 浏览器打开后创建管理员账号

数据库连接信息（用于在 Metabase UI 中添加数据源）:
  主机: ${PG_HOST:-localhost}
  端口: ${PG_PORT:-5432}
  数据库名: ${PG_DATABASE:-chainke}
  用户名: ${PG_USER:-postgres}
  密码: ${PG_PASSWORD:-****}
  SSL: 禁用

预置问题文件: $PROJECT_DIR/deploy/metabase/questions.json
  （可通过 Metabase API 导入）
EOF
}

# ---- 显示访问信息 ----
show_info() {
    echo ""
    info "=========================================="
    info "  链客宝 Metabase 部署完成！"
    info "=========================================="
    echo ""
    echo -e "  ${GREEN}访问地址:${NC}     http://localhost:${METABASE_PORT}"
    echo ""
    echo -e "  ${CYAN}首次使用:${NC}"
    echo "    1. 浏览器打开上述地址"
    echo "    2. 设置管理员账号密码"
    echo "    3. 在 Metabase 中添加链客宝数据库源:"
    echo "       - 类型: PostgreSQL"
    echo "       - 主机: ${PG_HOST:-localhost}"
    echo "       - 端口: ${PG_PORT:-5432}"
    echo "       - 数据库: ${PG_DATABASE:-chainke}"
    echo "       - 用户名: ${PG_USER:-postgres}"
    echo "       - 密码: [从 .env 中读取]"
    echo ""
    echo -e "  ${YELLOW}预置问题:${NC}      deploy/metabase/questions.json"
    echo "    可通过 Metabase API 导入预置分析问题"
    echo ""
    echo -e "  ${BLUE}管理命令:${NC}"
    echo "    停止:   bash $0 --stop"
    echo "    重启:   bash $0 --restart"
    echo "    日志:   bash $0 --logs"
    echo "    状态:   bash $0 --status"
    echo ""
    info "=========================================="
}

# ---- 停止 Metabase ----
stop_metabase() {
    log "停止 Metabase..."
    if docker ps --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        docker stop "$METABASE_CONTAINER" > /dev/null
        log "Metabase 已停止"
    else
        warn "Metabase 未在运行"
    fi
}

# ---- 重启 Metabase ----
restart_metabase() {
    log "重启 Metabase..."
    if docker ps --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        docker restart "$METABASE_CONTAINER" > /dev/null
        log "Metabase 已重启"
    elif docker ps -a --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        docker start "$METABASE_CONTAINER" > /dev/null
        log "Metabase 已启动"
    else
        warn "Metabase 容器不存在，执行部署..."
        start_metabase
    fi
}

# ---- 查看日志 ----
show_logs() {
    if docker ps -a --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        docker logs -f "$METABASE_CONTAINER"
    else
        error "Metabase 容器不存在"
        exit 1
    fi
}

# ---- 查看状态 ----
show_status() {
    echo ""
    info "====== 链客宝 Metabase 状态 ======"
    echo ""

    if docker ps --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        echo -e "  运行状态: ${GREEN}运行中${NC}"
        local port_mapping
        port_mapping=$(docker port "$METABASE_CONTAINER" 2>/dev/null | head -1)
        echo -e "  端口映射: ${port_mapping:-localhost:$METABASE_PORT}"
        local uptime
        uptime=$(docker inspect "$METABASE_CONTAINER" --format='{{.State.StartedAt}}' 2>/dev/null)
        echo -e "  启动时间: ${uptime}"
        echo -e "  访问地址: ${CYAN}http://localhost:${METABASE_PORT}${NC}"
    elif docker ps -a --format '{{.Names}}' | grep -q "^${METABASE_CONTAINER}$"; then
        echo -e "  运行状态: ${YELLOW}已停止${NC}"
        echo -e "  启动命令: ${CYAN}docker start ${METABASE_CONTAINER}${NC}"
    else
        echo -e "  运行状态: ${RED}未部署${NC}"
        echo -e "  部署命令: ${CYAN}bash $0${NC}"
    fi

    echo ""
    echo -e "  数据目录: ${METABASE_DATA_DIR}"
    if [[ -f "$METABASE_DATA_DIR/README.txt" ]]; then
        echo -e "  配置信息: 已保存到 README.txt"
    fi
    echo ""
}

# ---- 导入预置问题（通过 Metabase API）----
import_questions() {
    local questions_file="$PROJECT_DIR/deploy/metabase/questions.json"
    if [[ ! -f "$questions_file" ]]; then
        warn "预置问题文件不存在: $questions_file"
        return 1
    fi

    log "导入预置问题到 Metabase..."
    warn "预置问题需要通过 Metabase 管理界面或 API 手动导入"
    warn "请参考: https://www.metabase.com/docs/latest/api-documentation"
    info "预置问题文件路径: $questions_file"
}

# ============================================================
# 主入口
# ============================================================

main() {
    local action="${1:-deploy}"

    case "$action" in
        deploy)
            load_env
            pre_check
            prepare_dirs
            pull_image
            start_metabase
            show_info
            import_questions
            ;;
        --stop|-stop|stop)
            load_env
            stop_metabase
            ;;
        --restart|-restart|restart)
            load_env
            restart_metabase
            show_info
            ;;
        --logs|-logs|logs)
            show_logs
            ;;
        --status|-status|status)
            show_status
            ;;
        --help|-help|help)
            echo "链客宝 Metabase 自动部署脚本"
            echo ""
            echo "用法:"
            echo "  bash $0              # 部署 Metabase"
            echo "  bash $0 --stop       # 停止 Metabase"
            echo "  bash $0 --restart    # 重启 Metabase"
            echo "  bash $0 --logs       # 查看日志"
            echo "  bash $0 --status     # 查看状态"
            echo "  bash $0 --help       # 显示帮助"
            ;;
        *)
            error "未知操作: $action"
            echo "用法: bash $0 {deploy|--stop|--restart|--logs|--status|--help}"
            exit 1
            ;;
    esac
}

main "$@"
