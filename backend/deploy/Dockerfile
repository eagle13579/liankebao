# =============================================================================
# 链客宝 Backend — 生产多阶段构建 (Python 3.12 + FastAPI)
# =============================================================================
# 构建:
#   docker build -t chainke-backend:latest -f deploy/Dockerfile ..
# 运行:
#   docker run -d -p 8201:8201 --env-file .env.production chainke-backend:latest
# =============================================================================

# ═════════════════════════════════════════════════════════════════════════════
# Stage 1: Python Dependencies
# ═════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS builder

LABEL stage="builder"
LABEL description="链客宝后端依赖构建阶段"

# 安装构建工具（psycopg2, bcrypt 等需要 gcc）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 复制 requirements.txt 以利用 Docker 缓存层
COPY requirements.txt .

# 创建虚拟环境并安装依赖
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt

# ═════════════════════════════════════════════════════════════════════════════
# Stage 2: Runtime (最小化运行镜像)
# ═════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS runtime

LABEL maintainer="链客宝技术团队"
LABEL description="链客宝 Backend API — 生产运行镜像"
LABEL version="1.0.0"

# 安装运行时工具（curl 用于健康检查，ca-certificates 用于 SSL）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安全：创建非 root 用户
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 --no-create-home app

# 从 builder 阶段复制已安装的依赖
COPY --from=builder /venv /venv

# 复制应用代码
WORKDIR /app
COPY . .

# 创建必要的数据和日志目录
RUN mkdir -p /app/data /app/logs /app/uploads && \
    chown -R app:app /app

# 清理缓存文件
RUN find /app -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# 设置环境变量
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8201 \
    APP_ENV=production \
    LOG_LEVEL=INFO \
    LOG_JSON=1 \
    LOG_DIR=/app/logs \
    DATABASE_POOL_SIZE=10 \
    DATABASE_MAX_OVERFLOW=20 \
    DATABASE_POOL_RECYCLE=1800

# 暴露应用端口
EXPOSE 8201

# 健康检查（Docker 原生）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; exit(0 if urllib.request.urlopen('http://127.0.0.1:8201/health').status == 200 else 1)"

# 切换到非 root 用户
USER app

# 启动命令（使用 gunicorn + uvicorn workers 用于生产）
# 使用 uvicorn 直接运行 — 如需更高并发，可替换为 gunicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8201", "--log-level", "info", "--workers", "4"]
