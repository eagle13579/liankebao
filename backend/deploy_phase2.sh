#!/bin/bash
# ============================================================
# 链客宝AI匹配引擎 Phase 2 部署脚本
# 将企业知识图谱注入搜索/推荐/匹配逻辑
# 用法: bash deploy_phase2.sh
# ============================================================
set -e

BACKEND_DIR="/opt/chainke/backend"
TMP_DIR="/tmp/chainke_deploy_$(date +%Y%m%d_%H%M%S)"
SRC_DIR="D:/链客宝AI/backend"
REMOTE_USER="root"
REMOTE_HOST="47.100.160.250"

echo "=== 链客宝AI Phase 2 部署 ==="
echo "源目录: $SRC_DIR"
echo "目标: $REMOTE_USER@$REMOTE_HOST:$BACKEND_DIR"
echo ""

# 要部署的修改文件列表
FILES_TO_DEPLOY=(
    "app/business_card_ai.py"
    "app/routers/business_card.py"
    "app/routers/search.py"
    "app/routers/needs.py"
)

# Step 1: 打包修改的文件
echo "[1/4] 打包修改文件..."
cd "$SRC_DIR"
tar czf /tmp/chainke_phase2.tar.gz "${FILES_TO_DEPLOY[@]}"
echo "  -> 打包完成: /tmp/chainke_phase2.tar.gz"

# Step 2: SCP 到远程服务器
echo "[2/4] SCP 到远程服务器..."
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $TMP_DIR"
scp /tmp/chainke_phase2.tar.gz "$REMOTE_USER@$REMOTE_HOST:$TMP_DIR/"
echo "  -> SCP 完成"

# Step 3: 在远程服务器上解压并备份
echo "[3/4] 备份并更新文件..."
ssh "$REMOTE_USER@$REMOTE_HOST" bash -c "'
set -e
cd $TMP_DIR
tar xzf chainke_phase2.tar.gz

for f in ${FILES_TO_DEPLOY[@]}; do
    target=\"$BACKEND_DIR/\$f\"
    backup=\"\$target.bak.\$(date +%Y%m%d_%H%M%S)\"

    if [ -f \"\$target\" ]; then
        cp \"\$target\" \"\$backup\"
        echo \"  -> 已备份: \$backup\"
    fi

    cp \"\$f\" \"\$target\"
    echo \"  -> 已更新: \$target\"
done

# 验证 Python 语法
cd $BACKEND_DIR
source venv/bin/activate 2>/dev/null || true
python -m py_compile app/business_card_ai.py
python -m py_compile app/routers/business_card.py
python -m py_compile app/routers/search.py
python -m py_compile app/routers/needs.py
echo \"  -> Python 语法验证通过\"
'"

echo ""

# Step 4: 重启服务
echo "[4/4] 重启 chainke 服务..."
ssh "$REMOTE_USER@$REMOTE_HOST" "sudo systemctl restart chainke.service"
echo "  -> 服务重启命令已发送"

# 等待服务启动并验证健康检查
echo ""
echo "=== 等待服务启动 (5秒) ==="
sleep 5

# 健康检查
echo "=== 健康检查 ==="
HEALTH=$(ssh "$REMOTE_USER@$REMOTE_HOST" "curl -s http://localhost:8000/health" 2>/dev/null || echo "FAILED")
if echo "$HEALTH" | grep -q "ok\|true\|200"; then
    echo "✅ Health check: PASSED ($HEALTH)"
else
    echo "⚠️ Health check: $HEALTH"
    echo "   请手动检查: ssh $REMOTE_USER@$REMOTE_HOST 'sudo systemctl status chainke.service'"
fi

# 新路由验证
echo ""
echo "=== 新路由验证 ==="
echo "GET /api/search/enterprises?q=阿里"
RESULT=$(ssh "$REMOTE_USER@$REMOTE_HOST" "curl -s http://localhost:8000/api/search/enterprises?q=%E9%98%BF%E9%87%8C" 2>/dev/null || echo "FAILED")
if echo "$RESULT" | grep -q "items"; then
    echo "✅ /api/search/enterprises: OK"
else
    echo "⚠️ /api/search/enterprises: 响应异常 (可能无数据或路由未注册)"
    echo "   响应: $RESULT"
fi

echo ""
echo "=== 部署完成 ==="
echo "查看服务状态: ssh $REMOTE_USER@$REMOTE_HOST 'sudo systemctl status chainke.service'"
echo "查看服务日志: ssh $REMOTE_USER@$REMOTE_HOST 'journalctl -u chainke.service -n 50 --no-pager'"
