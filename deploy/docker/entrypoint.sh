#!/bin/sh
# =============================================================================
# 链客宝 — Docker 入口脚本
# 启动 Nginx + uvicorn (FastAPI 后端)
# =============================================================================
set -e

# 等待 PostgreSQL（如果配置了）
if [ -n "$DATABASE_URL" ]; then
    echo "[Entrypoint] 等待 PostgreSQL 就绪..."
    # 从 DATABASE_URL 提取主机名
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:/]*\).*/\1/p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
    DB_PORT=${DB_PORT:-5432}
    DB_HOST=${DB_HOST:-postgres}

    for i in $(seq 1 30); do
        if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
            echo "[Entrypoint] PostgreSQL 已就绪"
            break
        fi
        echo "[Entrypoint] 等待 PostgreSQL... ($i/30)"
        sleep 1
    done
fi

echo "[Entrypoint] 启动 uvicorn (FastAPI)..."
# 后台启动 uvicorn
uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8001 \
    --workers 2 \
    --log-level info \
    --no-access-log &

UVICORN_PID=$!

echo "[Entrypoint] 启动 Nginx..."
nginx -g "daemon off;" &

NGINX_PID=$!

# 注册退出清理
trap "kill $UVICORN_PID $NGINX_PID 2>/dev/null; exit 0" SIGTERM SIGINT

# 等待任一进程退出
wait $UVICORN_PID $NGINX_PID
