#!/bin/bash
# =============================================================================
# 链客宝 基础设施修复脚本
# =============================================================================
# 用途: 修复 Docker 镜像拉取 + 启动 PostgreSQL/Redis + 重建后端容器
# 适用: 服务器 47.116.116.87 (Ubuntu 24.04, 3.4GB RAM)
# 用法: ssh root@47.116.116.87 'bash -s' < infra-fix.sh
# =============================================================================
set -e

echo "=== Step 1: 配置 Docker 镜像加速 ==="
cat > /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ],
  "max-concurrent-downloads": 3,
  "storage-driver": "overlay2"
}
EOF

systemctl restart docker
sleep 3
echo "Docker 已重启"

echo "=== Step 2: 拉取基础镜像 (从 daocloud 镜像站) ==="
# 先检查本地是否有缓存
for img in \
  "docker.m.daocloud.io/library/postgres:16-alpine" \
  "docker.m.daocloud.io/library/redis:7-alpine" \
  "docker.m.daocloud.io/library/node:20-alpine" \
  "docker.m.daocloud.io/library/python:3.12-slim"; do
  echo "拉取 $img ..."
  docker pull "$img" 2>&1 | tail -1
done

echo "=== Step 3: 标记为标准镜像名 ==="
docker tag docker.m.daocloud.io/library/postgres:16-alpine postgres:16-alpine 2>/dev/null || true
docker tag docker.m.daocloud.io/library/redis:7-alpine redis:7-alpine 2>/dev/null || true
docker tag docker.m.daocloud.io/library/node:20-alpine node:20-alpine 2>/dev/null || true
docker tag docker.m.daocloud.io/library/python:3.12-slim python:3.12-slim 2>/dev/null || true

echo "=== Step 4: 创建网络 ==="
docker network create liankebao-net 2>/dev/null || true

echo "=== Step 5: 启动 PostgreSQL ==="
docker run -d --name chainke-postgres \
  --network liankebao-net \
  -p 5432:5432 \
  -e POSTGRES_USER=chainke \
  -e POSTGRES_PASSWORD=chainke_secret \
  -e POSTGRES_DB=chainke \
  -v pg-data:/var/lib/postgresql/data \
  postgres:16-alpine 2>/dev/null || docker start chainke-postgres

echo "=== Step 6: 启动 Redis ==="
docker run -d --name chainke-redis \
  --network liankebao-net \
  -p 6379:6379 \
  redis:7-alpine 2>/dev/null || docker start chainke-redis

echo "=== Step 7: 构建并启动链客宝后端 ==="
cd /var/www/liankebao
docker compose -f docker-compose.yml build backend 2>&1 | tail -5
docker compose -f docker-compose.yml up -d backend 2>&1

echo "=== Step 8: 验证 ==="
sleep 5
curl -s --max-time 5 http://127.0.0.1:8001/health
echo ""
curl -s --max-time 5 http://127.0.0.1:5432 2>/dev/null && echo "PostgreSQL OK" || echo "PostgreSQL 启动中..."
curl -s --max-time 5 http://127.0.0.1:6379 2>/dev/null && echo "Redis OK" || echo "Redis 启动中..."

echo ""
echo "=== 完成 ==="
echo "前端: https://liankebao.top/"
echo "后端: http://127.0.0.1:8001/health"
echo "微信: POST https://liankebao.top/api/wechat/qr-session"
