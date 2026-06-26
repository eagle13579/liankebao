# =============================================================================
# 链客宝 — Docker 多阶段构建 (生产优化)
# Stage 1: frontend-build   — React 前端编译
# Stage 2: frontend-output  — 前端产物导出（供 docker-compose volume 使用）
# Stage 3: backend-build    — Python 依赖安装
# Stage 4: runtime          — 最小化后端运行镜像
# =============================================================================

# ═════════════════════════════════════════════════════════════════════════════
# Stage 1: Frontend Build
# ═════════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-build

LABEL stage="frontend-build"
LABEL description="链客宝前端构建阶段"

WORKDIR /build

# 复制前端构建配置
COPY deploy/docker/package.json deploy/docker/package-lock.json* ./
COPY deploy/docker/vite.config.ts deploy/docker/tsconfig.json ./

# 复制前端源代码
COPY src/ ./src/
COPY public/ ./public/
COPY index.html ./

# 安装依赖并构建生产包
RUN npm ci && npm run build

# 构建产物在 /build/dist/

# ═════════════════════════════════════════════════════════════════════════════
# Stage 2: Frontend Output Export
# ═════════════════════════════════════════════════════════════════════════════
# docker-compose 使用此 stage 将前端产物写入 named volume，供 nginx 容器读取
FROM alpine:3.20 AS frontend-output

LABEL stage="frontend-output"
LABEL description="链客宝前端产物导出阶段"

COPY --from=frontend-build /build/dist /app/frontend

# 容器启动时将产物复制到挂载的 volume (/output)
CMD ["cp", "-r", "/app/frontend/.", "/output/"]

# ═════════════════════════════════════════════════════════════════════════════
# Stage 3: Backend Build
# ═════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS backend-build

LABEL stage="backend-build"
LABEL description="链客宝后端依赖构建阶段"

# 安装编译工具（如有 C 扩展需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 先复制 requirements.txt 以利用 Docker 缓存层
COPY backend/requirements.txt .

# 安装 Python 依赖到 /venv
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt

# ═════════════════════════════════════════════════════════════════════════════
# Stage 4: Runtime (Backend API)
# ═════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS runtime

LABEL maintainer="链客宝技术团队"
LABEL description="链客宝 Backend API — 生产运行镜像"
LABEL version="1.0.0"

# 安装运行时工具（curl, ca-certificates）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安全：创建非 root 用户
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 --no-create-home app

# 从 backend-build 阶段复制已安装的依赖
COPY --from=backend-build /venv /venv

# 复制应用代码
WORKDIR /app
COPY backend/ ./backend/

# 创建必要的数据和日志目录
RUN mkdir -p /app/data /app/logs /app/storage && \
    chown -R app:app /app

# 设置环境变量
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001 \
    APP_ENV=production

# 暴露应用端口
EXPOSE 8001

# 健康检查（Docker 原生）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health').status == 200 else 1)"

# 切换到非 root 用户
USER app

# 启动命令
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
