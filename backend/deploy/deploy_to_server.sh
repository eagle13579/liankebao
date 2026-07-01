#!/bin/bash
# ==============================================================================
# 链客宝 — 生产服务器部署脚本
# Deploy Gaia Evolution Brain + AI数字员工 + 6层架构 + Phase 1/2 基础设施
#
# 用法:
#   chmod +x deploy_to_server.sh
#   ./deploy_to_server.sh
#
# 前提:
#   - SSH 密钥已配置到 root@47.116.116.87
#   - git 仓库已 clone 到 /root/liankebao
#   - 系统服务 chainke-backend 已配置
# ==============================================================================

set -euo pipefail

SERVER="root@47.116.116.87"
APP_DIR="/root/liankebao"
BRANCH="feat/gaia-evolution"
BACKEND_DIR="${APP_DIR}/backend"

echo "============================================"
echo "  链客宝 — 生产部署"
echo "  分支: ${BRANCH}"
echo "  服务器: ${SERVER}"
echo "============================================"

# Step 1: SSH into server and deploy
ssh -T "${SERVER}" << 'EOF'
set -euo pipefail

APP_DIR="/root/liankebao"
BACKEND_DIR="${APP_DIR}/backend"
BRANCH="feat/gaia-evolution"

echo ""
echo "[1/7] 切换到应用目录..."
cd "${APP_DIR}"

echo ""
echo "[2/7] 拉取最新代码 (${BRANCH})..."
git fetch origin "${BRANCH}"
git checkout "${BRANCH}" 2>/dev/null || git checkout -b "${BRANCH}" "origin/${BRANCH}"
git pull origin "${BRANCH}"
echo "  HEAD: $(git rev-parse --short HEAD)"

echo ""
echo "[3/7] 安装/更新 Python 依赖..."
cd "${BACKEND_DIR}"
if [ -f requirements.txt ]; then
    pip install -r requirements.txt 2>&1 | tail -5
fi

echo ""
echo "[4/7] 检查关键文件..."
for f in \
    app/agents/base_agent.py \
    app/agents/agent_runtime.py \
    app/agents/legion_employee.py \
    app/agents/employee_profiles.py \
    app/agents/scheduler_rules.py \
    app/cache/interfaces.py \
    app/cache/adapters/redis_adapter.py \
    app/events/interfaces.py \
    app/events/adapters/sqlite_adapter.py \
    app/broker/interfaces.py \
    app/repositories/interfaces.py \
    app/identity/interfaces.py \
    app/health.py \
    app/lifespan.py \
    app/ai/gaia_evolution_brain.py \
    app/ai/gaia_trainer.py \
    app/ai/gaia_flywheel.py \
    app/ai/gateway/interfaces.py \
    app/models/gaia.py \
    app/routers/gaia_router.py \
    app/dependencies.py \
    .env.production
do
    if [ -f "${BACKEND_DIR}/${f}" ]; then
        echo "  ✅ ${f}"
    else
        echo "  ❌ ${f} — MISSING!"
    fi
done

echo ""
echo "[5/7] 创建必要的数据目录..."
mkdir -p "${BACKEND_DIR}/data"
mkdir -p "${BACKEND_DIR}/data/uploads"
mkdir -p "${BACKEND_DIR}/logs"

echo ""
echo "[6/7] 重启 systemd 服务..."
if systemctl list-units --type=service --state=running 2>/dev/null | grep -q chainke; then
    echo "  检测到 chainke 服务，重启中..."
    systemctl daemon-reload 2>/dev/null || true
    
    # Try the new agent service first
    if systemctl list-units --type=service --all 2>/dev/null | grep -q chainke-agents; then
        systemctl restart chainke-agents 2>&1
        echo "  chainke-agents restarted"
    fi
    
    # Restore original service if it exists
    if systemctl list-units --type=service --all 2>/dev/null | grep -q chainke-backend; then
        systemctl restart chainke-backend 2>&1
        echo "  chainke-backend restarted"
    fi
    
    # Try generic chainke
    if systemctl list-units --type=service --all 2>/dev/null | grep -q '^chainke\.'; then
        systemctl restart chainke 2>&1
        echo "  chainke restarted"
    fi
else
    echo "  未检测到 systemd 服务，尝试直接启动..."
    echo "  请手动配置 systemd 服务或使用 docker-compose"
fi

echo ""
echo "[7/7] 检查服务状态..."
sleep 3

# Check health endpoint
HEALTH_URL="http://localhost:8200/health"
if command -v curl &>/dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_URL}" 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" = "200" ]; then
        echo "  ✅ 服务健康检查通过 (HTTP ${HTTP_CODE})"
        echo "  📊 健康状态摘要:"
        curl -s "${HEALTH_URL}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'    应用: {d.get(\"app\",\"?\")} | 版本: {d.get(\"version\",\"?\")} | DB: {\"✅\" if d.get(\"database\",\"\")==\"ok\" else \"❌\"}')" 2>/dev/null || true
    else
        echo "  ⚠️  健康检查返回 HTTP ${HTTP_CODE}"
    fi
elif command -v wget &>/dev/null; then
    wget -q -O- "${HEALTH_URL}" 2>/dev/null && echo "  ✅ 健康检查通过" || echo "  ⚠️  健康检查失败"
fi

# Check logs
echo ""
echo "  最近日志 (journalctl):"
journalctl -u chainke* --since "5 minutes ago" --no-pager -n 20 2>/dev/null || echo "  无法读取 systemd 日志"

echo ""
echo "============================================"
echo "  部署完成！"
echo "  分支: ${BRANCH}"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"
EOF

echo ""
echo "本地部署脚本执行完毕。"
echo "如果 SSH 部署失败，请手动在服务器上执行上述步骤。"
