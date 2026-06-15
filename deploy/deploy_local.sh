#!/usr/bin/env bash
# ============================================================
# 链客宝AI 本地一键部署脚本
# 用途: git push → SSH → Docker Compose 全自动部署
# 服务器: 阿里云 ECS (47.100.160.250)
# 分支: develop (测试) / main (生产)
# 认证: 支持 SSH 密钥 和 密码 两种方式
#
# 使用方式:
#   # 密钥认证（默认）
#   bash deploy/deploy_local.sh
#   bash deploy/deploy_local.sh --branch develop
#
#   # 密码认证
#   bash deploy/deploy_local.sh --password
#
#   # 指定 SSH 密钥文件
#   bash deploy/deploy_local.sh --key ~/.ssh/id_rsa_liankebao
#
#   # 生产部署
#   bash deploy/deploy_local.sh --branch main
#
#   # 仅 SSH 部署（跳过 git push）
#   bash deploy/deploy_local.sh --skip-push
# ============================================================
set -e

# ============================================================
# 配置区（可按需修改）
# ============================================================

# ECS 服务器配置
REMOTE_HOST="${ECS_HOST:-47.100.160.250}"
REMOTE_USER="${ECS_USER:-root}"
REMOTE_PORT="${ECS_PORT:-22}"
# SSH 密钥路径（留空则使用默认 ~/.ssh/id_*）
SSH_KEY="${ECS_SSH_KEY:-}"
# SSH 密码（仅 --password 模式使用，建议通过环境变量传入）
SSH_PASSWORD="${ECS_PASSWORD:-}"

# Git 配置
GIT_REMOTE="origin"
BRANCH="${BRANCH:-develop}"

# 项目配置
PROJECT_DIR="/opt/liankebao"
DOCKER_COMPOSE_FILE="docker-compose.yml"
HEALTH_CHECK_URL="http://127.0.0.1:8001/health"

# ============================================================
# 颜色 & 日志
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error(){ echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }

# ============================================================
# 帮助信息
# ============================================================
usage() {
    echo ""
    echo "链客宝AI 一键部署脚本"
    echo "===================="
    echo ""
    echo "用法: bash deploy/deploy_local.sh [选项]"
    echo ""
    echo "认证选项（二选一，默认密钥）:"
    echo "  -k, --key <path>         SSH 私钥路径 (默认: ~/.ssh/id_*)"
    echo "  -p, --password           使用密码认证（设置 ECS_PASSWORD 环境变量）"
    echo ""
    echo "分支选项:"
    echo "  -b, --branch <name>      Git 分支 (默认: develop)"
    echo ""
    echo "行为选项:"
    echo "  --skip-push              跳过 git push，只做 SSH 远程部署"
    echo "  --skip-build             跳过远程 Docker 构建（仅 pull 镜像）"
    echo "  -h, --help               显示此帮助"
    echo ""
    echo "示例:"
    echo "  bash deploy/deploy_local.sh                    # develop 密钥部署"
    echo "  bash deploy/deploy_local.sh -b main            # main 生产部署"
    echo "  bash deploy/deploy_local.sh -p                 # 密码认证"
    echo "  ECS_PASSWORD='xxx' bash deploy/deploy_local.sh -p"
    echo "  bash deploy/deploy_local.sh -k ~/.ssh/mykey -b main --skip-push"
    echo ""
    exit 0
}

# ============================================================
# 参数解析
# ============================================================
USE_PASSWORD=false
SKIP_PUSH=false
SKIP_BUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--key)
            SSH_KEY="$2"
            shift 2
            ;;
        -p|--password)
            USE_PASSWORD=true
            shift
            ;;
        -b|--branch)
            BRANCH="$2"
            shift 2
            ;;
        --skip-push)
            SKIP_PUSH=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            warn "未知参数: $1"
            usage
            ;;
    esac
done

# ============================================================
# 前置检查
# ============================================================
pre_check() {
    echo ""
    echo "=========================================="
    echo "  链客宝AI 一键部署"
    echo "  主机: ${REMOTE_HOST}"
    echo "  分支: ${BRANCH}"
    echo "  认证: $([ "$USE_PASSWORD" = true ] && echo '密码' || echo '密钥')"
    echo "=========================================="
    echo ""

    # 检查 git
    if ! command -v git &>/dev/null; then
        fail "git 未安装"
    fi

    # 检查本地 Git 仓库
    if [ ! -d ".git" ]; then
        fail "当前目录不是 Git 仓库，请到链客宝AI项目根目录执行"
    fi

    # 检查 SSH 命令
    if ! command -v ssh &>/dev/null; then
        fail "ssh 未安装"
    fi

    # 检查密钥文件
    if [ "$USE_PASSWORD" = false ]; then
        if [ -z "$SSH_KEY" ]; then
            # 自动查找默认密钥
            for key in ~/.ssh/id_rsa ~/.ssh/id_ed25519 ~/.ssh/id_ecdsa; do
                if [ -f "$key" ]; then
                    SSH_KEY="$key"
                    break
                fi
            done
        fi

        if [ -z "$SSH_KEY" ] || [ ! -f "$SSH_KEY" ]; then
            warn "未找到 SSH 密钥文件"
            warn "请指定: -k ~/.ssh/your_key，或使用 -p 密码认证"
            info "也可通过环境变量 ECS_SSH_KEY 设置密钥路径"
            USE_PASSWORD=true
        else
            ok "SSH 密钥: $SSH_KEY"
        fi
    fi

    # 密码认证检查
    if [ "$USE_PASSWORD" = true ] && [ -z "$SSH_PASSWORD" ]; then
        warn "密码认证已选择，但 ECS_PASSWORD 未设置"
        warn "请通过环境变量传入: ECS_PASSWORD='your_pass' bash $0 -p"
        # 尝试从 stdin 读取（不 echo）
        read -s -p "请输入 SSH 密码: " SSH_PASSWORD
        echo ""
        if [ -z "$SSH_PASSWORD" ]; then
            fail "密码不能为空"
        fi
    fi

    # 确认分支
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
        warn "当前本地分支: $CURRENT_BRANCH，目标分支: $BRANCH"
        read -p "是否继续? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    ok "前置检查通过"
}

# ============================================================
# Step 1: Git Push
# ============================================================
git_push() {
    if [ "$SKIP_PUSH" = true ]; then
        warn "跳过 git push"
        return 0
    fi

    log "=== Step 1/3: Git Push ==="

    # 检查是否有未提交的变更
    if [ -n "$(git status --porcelain)" ]; then
        warn "有未提交的变更，自动提交..."
        git add -A
        git commit -m "auto-deploy: $(date '+%Y-%m-%d %H:%M:%S')" || true
    fi

    log "推送到 $GIT_REMOTE/$BRANCH ..."
    git push "$GIT_REMOTE" "$BRANCH"

    LATEST_COMMIT=$(git rev-parse --short HEAD)
    ok "推送完成 (commit: $LATEST_COMMIT)"
}

# ============================================================
# Step 2: SSH 部署
# ============================================================
ssh_deploy() {
    log "=== Step 2/3: SSH 远程部署 ==="

    # 构建 SSH 连接参数
    SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

    if [ "$USE_PASSWORD" = false ] && [ -n "$SSH_KEY" ]; then
        SSH_CMD="ssh -i \"$SSH_KEY\" $SSH_OPTS -p $REMOTE_PORT"
    else
        # 使用 sshpass（需安装）
        if command -v sshpass &>/dev/null; then
            SSH_CMD="sshpass -p \"$SSH_PASSWORD\" ssh $SSH_OPTS -p $REMOTE_PORT"
        else
            warn "sshpass 未安装，尝试安装..."
            if command -v apt-get &>/dev/null; then
                sudo apt-get install -y sshpass
            elif command -v brew &>/dev/null; then
                brew install hudochenkov/sshpass/sshpass
            else
                fail "请安装 sshpass: apt-get install sshpass"
            fi
            SSH_CMD="sshpass -p \"$SSH_PASSWORD\" ssh $SSH_OPTS -p $REMOTE_PORT"
        fi
    fi

    # 构建远程执行脚本
    REMOTE_SCRIPT=$(cat << 'EOSCRIPT'
set -e

echo "[$(date '+%H:%M:%S')] ====== 链客宝AI 远程部署 ======"
echo "  分支: BRANCH_PLACEHOLDER"
echo "  目录: DIR_PLACEHOLDER"

# 1. 检查 Docker
echo ""
echo "[1/6] 检查 Docker 环境..."
if ! command -v docker &>/dev/null; then
    echo "  Docker 未安装，正在安装..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
    ok "  Docker 安装完成"
fi

if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    echo "  Docker Compose 未安装，正在安装..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    ok "  Docker Compose 安装完成"
fi

DOCKER_VERSION=$(docker --version 2>/dev/null)
echo "  $DOCKER_VERSION"

# 2. 拉取/更新代码
echo ""
echo "[2/6] 拉取最新代码..."
if [ ! -d "DIR_PLACEHOLDER/.git" ]; then
    echo "  首次部署: 克隆仓库..."
    rm -rf DIR_PLACEHOLDER 2>/dev/null || true
    git clone https://github.com/eagle13579/liankebao.git DIR_PLACEHOLDER
fi

cd DIR_PLACEHOLDER
git fetch origin BRANCH_PLACEHOLDER
git reset --hard origin/BRANCH_PLACEHOLDER
git clean -fd
echo "  commit: $(git rev-parse --short HEAD)"

# 3. 清理旧容器（保留数据卷）
echo ""
echo "[3/6] 清理旧容器..."
docker compose down --remove-orphans 2>/dev/null || true
docker system prune -f 2>/dev/null || true
ok "  清理完成"

# 4. 构建/拉取镜像
echo ""
echo "[4/6] 构建 Docker 镜像..."
if [ "SKIP_BUILD_PLACEHOLDER" = "true" ]; then
    echo "  跳过构建，直接拉取镜像..."
    if [ -n "$GITHUB_TOKEN_PLACEHOLDER" ]; then
        echo "$GITHUB_TOKEN_PLACEHOLDER" | docker login ghcr.io -u eagle13579 --password-stdin 2>/dev/null || true
        docker compose pull 2>/dev/null || true
    fi
else
    echo "  本地构建镜像..."
    docker compose build --no-cache
fi
ok "  镜像就绪"

# 5. 启动服务
echo ""
echo "[5/6] 启动 Docker Compose..."
docker compose up -d
ok "  服务已启动"

# 6. 健康检查
echo ""
echo "[6/6] 健康检查..."
sleep 3
MAX_RETRIES=12
for i in $(seq 1 $MAX_RETRIES); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/health 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  后端健康检查 ✅ (尝试 $i/$MAX_RETRIES, HTTP $HTTP_CODE)"
        break
    fi
    echo "  等待后端就绪... (尝试 $i/$MAX_RETRIES, HTTP $HTTP_CODE)"
    sleep 5
    if [ "$i" = "$MAX_RETRIES" ]; then
        echo "  ⚠ 后端未完全就绪，检查日志: docker compose logs backend"
    fi
done

# 检查前端
FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:80/ 2>/dev/null || echo "000")
echo "  前端状态: HTTP $FRONTEND_CODE"

echo ""
echo "========================================"
echo "  ✅ 部署完成！"
echo "  后端: http://127.0.0.1:8001/health"
echo "  前端: http://$(curl -s ifconfig.me 2>/dev/null || echo 'ECS_IP'):80"
echo "========================================"
EOSCRIPT
)

    # 替换占位符（注意这里需要实际替换，不能简化为 envsubst）
    ESCAPED_DIR=$(echo "$PROJECT_DIR" | sed 's/\//\\\//g')
    REMOTE_SCRIPT=$(echo "$REMOTE_SCRIPT" | \
        sed "s/BRANCH_PLACEHOLDER/$BRANCH/g" | \
        sed "s/DIR_PLACEHOLDER/$PROJECT_DIR/g" | \
        sed "s/SKIP_BUILD_PLACEHOLDER/$([ "$SKIP_BUILD" = true ] && echo 'true' || echo 'false')/g")

    # 执行远程命令
    echo "  连接 ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT} ..."
    # 将多行脚本通过 SSH 执行
    echo "$REMOTE_SCRIPT" | ${SSH_CMD} "${REMOTE_USER}@${REMOTE_HOST}" "bash -s"

    if [ $? -eq 0 ]; then
        ok "SSH 远程部署成功"
    else
        fail "SSH 远程部署失败"
    fi
}

# ============================================================
# Step 3: 部署验证
# ============================================================
verify_deploy() {
    log "=== Step 3/3: 部署验证 ==="

    echo ""
    info "========== 链客宝AI部署状态 =========="
    echo ""

    echo "  服务器:  ${CYAN}${REMOTE_HOST}${NC}"
    echo "  分支:     ${CYAN}${BRANCH}${NC}"
    echo "  时间:     ${CYAN}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""

    # 通过 SSH 获取服务状态
    SSH_TEST_CMD="${SSH_CMD} ${REMOTE_USER}@${REMOTE_HOST}"

    # 检查 Docker 进程
    local docker_status
    docker_status=$(${SSH_TEST_CMD} "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null" 2>/dev/null || echo "无法获取")
    if [ -n "$docker_status" ]; then
        echo "  Docker 容器状态:"
        echo "$docker_status" | while IFS= read -r line; do
            echo "    $line"
        done
    fi

    echo ""

    # 检查后端健康
    local health
    health=$(${SSH_TEST_CMD} "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/health 2>/dev/null || echo '失败'" 2>/dev/null)
    if [ "$health" = "200" ]; then
        echo -e "  后端健康:  ${GREEN}✅ HTTP 200${NC}"
    else
        echo -e "  后端健康:  ${RED}❌ HTTP ${health}${NC}"
    fi

    # 检查前端
    local frontend
    frontend=$(${SSH_TEST_CMD} "docker ps --format '{{.Names}}' | grep -q frontend && echo '运行中' || echo '未运行'" 2>/dev/null)
    if [ "$frontend" = "运行中" ]; then
        echo -e "  前端:      ${GREEN}✅ ${frontend}${NC}"
    else
        echo -e "  前端:      ${RED}❌ ${frontend}${NC}"
    fi

    echo ""
    info "====================================="
    echo ""

    # 最终判断
    if [ "$health" = "200" ]; then
        log "✅ 部署成功！链客宝AI已上线！"
        echo ""
        echo "  访问地址:"
        echo "    前端: http://${REMOTE_HOST}"
        echo "    API:  http://${REMOTE_HOST}/api/"
        echo "    文档: http://${REMOTE_HOST}/docs"
    else
        warn "⚠ 部署完成但健康检查异常，请手动排查:"
        echo "  ssh ${REMOTE_USER}@${REMOTE_HOST}"
        echo "  cd ${PROJECT_DIR} && docker compose logs"
    fi
}

# ============================================================
# Main
# ============================================================
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     链客宝AI 一键部署工具                       ║"
echo "║     LianKeBao One-Click Deploy Tool           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 计时
START_TIME=$(date +%s)

# 执行
pre_check
git_push
ssh_deploy
verify_deploy

# 耗时
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo ""
log "总耗时: ${DURATION} 秒"
echo ""
