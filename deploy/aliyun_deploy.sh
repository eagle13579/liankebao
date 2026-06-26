#!/usr/bin/env bash
# ==============================================================================
# 链客宝 — 阿里云生产部署脚本
# ==============================================================================
# 功能:
#   1. SSH 连接到阿里云服务器
#   2. git pull 拉取最新 main 分支代码
#   3. 安装 Python 依赖
#   4. 构建前端（可选）
#   5. 应用数据库迁移（可选）
#   6. 重启链客宝服务（systemd / supervisor / docker-compose）
#   7. 健康检查验证
# ==============================================================================
#
# 用法:
#   export ALIYUN_PASSWORD="your_password"
#   bash deploy/aliyun_deploy.sh
#
#   或使用 SSH 密钥:
#   ssh -i ~/.ssh/id_rsa root@47.116.116.87
#   bash /var/www/chainke-full/deploy/aliyun_deploy.sh
#
# ==============================================================================

set -euo pipefail

# ── 颜色输出 ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── 配置（可通过环境变量覆盖）─────────────────────────────────────────────────
SERVER_HOST="${SERVER_HOST:-47.116.116.87}"
SERVER_USER="${SERVER_USER:-root}"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/chainke-full}"
BRANCH="${BRANCH:-main}"
HEALTH_CHECK_URL="${HEALTH_CHECK_URL:-http://127.0.0.1:8001/health}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-}"
SSH_PASSWORD="${ALIYUN_PASSWORD:-}"

# 是否构建前端
BUILD_FRONTEND="${BUILD_FRONTEND:-false}"

# 构建前端目录（相对于项目根目录）
FRONTEND_DIRS=("liankebao-weapp" "liankebao-miniapp")

# ── 项目根目录（脚本所在目录的上级）───────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 前置检查 ─────────────────────────────────────────────────────────────────
info "===== 链客宝 阿里云部署脚本 ====="
info "服务器:     ${SERVER_USER}@${SERVER_HOST}:${SSH_PORT}"
info "部署路径:   ${DEPLOY_PATH}"
info "分支:       ${BRANCH}"
echo ""

# 检查必需工具
for cmd in ssh; do
    if ! command -v "$cmd" &>/dev/null; then
        err "缺少必需命令: $cmd"
        exit 1
    fi
done

# ── 构建 SSH 命令 ─────────────────────────────────────────────────────────────
build_ssh_cmd() {
    local common_opts="-o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=5 -o TCPKeepAlive=yes -o LogLevel=ERROR"

    if [ -n "$SSH_KEY" ]; then
        # 使用 SSH 密钥文件
        if [ ! -f "$SSH_KEY" ]; then
            # 尝试从 PROJECT_DIR/.ssh/ 查找
            local local_key="$PROJECT_DIR/.ssh/id_rsa"
            if [ -f "$local_key" ]; then
                SSH_KEY="$local_key"
            else
                SSH_KEY="$HOME/.ssh/id_rsa"
            fi
        fi
        if [ -f "$SSH_KEY" ]; then
            echo "ssh -i $SSH_KEY $common_opts -p $SSH_PORT ${SERVER_USER}@${SERVER_HOST}"
        else
            err "SSH 密钥文件不存在: $SSH_KEY"
            err "请设置 SSH_KEY 环境变量指向有效的密钥文件"
            exit 1
        fi
    elif command -v sshpass &>/dev/null && [ -n "$SSH_PASSWORD" ]; then
        echo "sshpass -e ssh $common_opts -p $SSH_PORT ${SERVER_USER}@${SERVER_HOST}"
    else
        echo "ssh $common_opts -p $SSH_PORT ${SERVER_USER}@${SERVER_HOST}"
    fi
}

SSH_CMD="$(build_ssh_cmd)"
info "SSH 命令: $SSH_CMD ${SERVER_USER}@${SERVER_HOST}"

# ── 本地构建前端（可选，如果 BUILD_FRONTEND=true）─────────────────────────────
if [ "$BUILD_FRONTEND" = "true" ]; then
    info "──────────────────────────────────────────"
    info "构建前端..."
    info "──────────────────────────────────────────"

    cd "$PROJECT_DIR"

    # 检查是否有根目录 package.json
    if [ -f "package.json" ]; then
        info "📦 构建主前端..."
        npm install --silent && npm run build -- --logLevel error
        ok "主前端构建完成"
    fi

    # 构建子目录前端
    for dir in "${FRONTEND_DIRS[@]}"; do
        if [ -d "$dir" ] && [ -f "$dir/package.json" ]; then
            info "📦 构建 $dir 前端..."
            cd "$dir"
            npm install --silent && npm run build -- --logLevel error
            cd "$PROJECT_DIR"
            ok "$dir 构建完成"
        fi
    done
fi

# ── 远程部署（通过 SSH 执行远端命令）─────────────────────────────────────────
info "──────────────────────────────────────────"
info "远程部署到 ${SERVER_HOST}"
info "──────────────────────────────────────────"

# 构建远程命令
REMOTE_SCRIPT=$(cat <<'SCRIPT'
# 远端执行脚本
set -euo pipefail

DEPLOY_PATH="{DEPLOY_PATH}"
BRANCH="{BRANCH}"
HEALTH_URL="{HEALTH_CHECK_URL}"

echo "[1/6] 进入部署目录..."
cd "$DEPLOY_PATH"
echo "  当前目录: $(pwd)"

echo "[2/6] 拉取最新代码..."
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
git clean -fd
echo "  当前提交: $(git rev-parse --short HEAD)"

echo "[3/6] 安装 Python 依赖..."
# 查找虚拟环境
VENV_DIR=""
for venv in "backend/.venv" "backend/venv" ".venv" "venv"; do
    if [ -f "$venv/bin/activate" ]; then
        VENV_DIR="$venv"
        break
    fi
done

if [ -n "$VENV_DIR" ]; then
    echo "  使用虚拟环境: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
else
    echo "  ⚠️  未找到虚拟环境，使用系统 Python"
fi

cd backend
pip install -r requirements.txt -q --no-cache-dir
cd ..

# 如果激活了虚拟环境，退出
if [ -n "$VENV_DIR" ]; then
    deactivate 2>/dev/null || true
fi

echo "[4/6] 配置环境变量..."
if [ ! -f "backend/.env" ]; then
    if [ -f "deploy/production.env.example" ]; then
        echo "  ⚠️  .env 不存在，复制模板..."
        cp deploy/production.env.example backend/.env
        echo "  ⚠️  请手动填充 backend/.env 中的敏感值！"
    else
        echo "  ⚠️  未找到 production.env.example，跳过"
    fi
fi

echo "[5/6] 重启服务..."
RESTARTED=false

# 尝试 systemd
if command -v systemctl >/dev/null 2>&1 && systemctl is-active chainke &>/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl restart chainke
    echo "  ✅ systemctl restart chainke"
    RESTARTED=true
fi

# 尝试 supervisor
if [ "$RESTARTED" = false ] && command -v supervisorctl >/dev/null 2>&1; then
    if supervisorctl status chainke &>/dev/null 2>&1; then
        supervisorctl restart chainke
        echo "  ✅ supervisorctl restart chainke"
        RESTARTED=true
    fi
fi

# 尝试 docker-compose
if [ "$RESTARTED" = false ] && [ -f "docker-compose.prod.yml" ]; then
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose -f docker-compose.prod.yml up -d --build
        echo "  ✅ docker-compose up -d"
        RESTARTED=true
    fi
fi

# 回退：直接启动 uvicorn
if [ "$RESTARTED" = false ]; then
    echo "  ⚠️  未检测到 systemctl/supervisorctl/docker-compose"
    echo "  尝试直接启动 uvicorn（后台进程）..."

    # 杀掉旧的 uvicorn 进程
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 2

    cd backend
    nohup python -m uvicorn app.main:app \
        --host 0.0.0.0 --port 8001 --workers 2 \
        --log-level info > ../app.log 2>&1 &
    UVICORN_PID=$!
    cd ..
    echo "  ✅ uvicorn 已启动 (PID: $UVICORN_PID)"
    echo "  📝 日志: $DEPLOY_PATH/app.log"
    RESTARTED=true
fi

echo "[6/6] 健康检查..."
sleep 10
for i in $(seq 1 6); do
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo '000')
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  ✅ Health check passed (HTTP 200) on attempt $i"
        echo "DEPLOY_OK"
        exit 0
    fi
    echo "  ⏳ Health check attempt $i/6 - HTTP $HTTP_CODE, waiting 5s..."
    sleep 5
done

echo "❌ Health check failed after 6 attempts"
echo "  检查日志: tail -50 $DEPLOY_PATH/app.log"
exit 1
SCRIPT
)

# 替换模板变量
REMOTE_SCRIPT="${REMOTE_SCRIPT//\{DEPLOY_PATH\}/$DEPLOY_PATH}"
REMOTE_SCRIPT="${REMOTE_SCRIPT//\{BRANCH\}/$BRANCH}"
REMOTE_SCRIPT="${REMOTE_SCRIPT//\{HEALTH_CHECK_URL\}/$HEALTH_CHECK_URL}"

# 执行远程部署
info "执行远程部署命令..."
echo ""

if [ -n "$SSH_PASSWORD" ]; then
    # sshpass 模式
    export SSHPASS="$SSH_PASSWORD"
    echo "$REMOTE_SCRIPT" | $SSH_CMD "bash -s" 2>&1
    RESULT=$?
    unset SSHPASS
else
    # 密钥或交互模式
    echo "$REMOTE_SCRIPT" | $SSH_CMD "bash -s" 2>&1
    RESULT=$?
fi

# ── 结果输出 ─────────────────────────────────────────────────────────────────
echo ""
if [ $RESULT -eq 0 ]; then
    ok "===== 部署成功 ====="
    echo ""
    echo "  服务器:    ${SERVER_USER}@${SERVER_HOST}"
    echo "  部署路径:  ${DEPLOY_PATH}"
    echo "  分支:      ${BRANCH}"
    echo "  健康端点:  ${HEALTH_CHECK_URL}"
    echo ""
    info "查看服务状态:"
    echo "  ssh ${SERVER_USER}@${SERVER_HOST} 'systemctl status chainke'"
    info "查看实时日志:"
    echo "  ssh ${SERVER_USER}@${SERVER_HOST} 'journalctl -u chainke -f'"
else
    err "===== 部署失败 (exit code: $RESULT) ====="
    err "请检查服务器状态后重试"
    exit $RESULT
fi
