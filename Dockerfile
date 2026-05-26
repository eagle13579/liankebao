# ============================================================
# 链客宝 (LianKeBao) — Docker 多阶段构建
# ============================================================
# 构建方式:
#   docker compose build
#   docker compose up -d
#
# 单阶段构建（可选）:
#   docker build --target backend -t liankebao-backend .
#   docker build --target frontend -t liankebao-frontend .
# ============================================================

# ============================================================
# Stage 1: 前端构建 (Node.js + Vite + React)
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# 单独复制 package.json 和 lockfile 以利用 Docker 缓存层
COPY package.json package-lock.json ./
RUN npm ci --frozen-lockfile

# 复制前端源码并构建
COPY index.html vite.config.ts tsconfig.json ./
COPY public/ ./public/
COPY src/ ./src/

RUN npm run build

# ============================================================
# Stage 2: 后端 (FastAPI + Uvicorn)
# ============================================================
FROM python:3.12-slim AS backend

LABEL maintainer="链客宝团队 <eagle13579/liankebao>"
LABEL description="链客宝后端服务 — FastAPI + Uvicorn"
LABEL version="1.0.0"

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    TZ=Asia/Shanghai

# 安装系统依赖（仅必要的最小集合）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制后端代码
COPY backend/ ./backend/

# 安装 Python 依赖
RUN pip install --no-cache-dir -r /app/backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8001/health || exit 1

# 使用 tini 作为 init 进程（处理僵尸进程和信号转发）
ENTRYPOINT ["/usr/bin/tini", "--"]

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2", "--log-level", "info"]

EXPOSE 8001

# ============================================================
# Stage 3: 前端 Nginx 服务 (静态文件 + 反向代理)
# ============================================================
FROM nginx:1.27-alpine AS frontend

LABEL maintainer="链客宝团队 <eagle13579/liankebao>"
LABEL description="链客宝前端 — Nginx 静态文件服务 + API 反向代理"
LABEL version="1.0.0"

# 环境变量
ENV TZ=Asia/Shanghai

# 从 frontend-builder 阶段复制构建产物
COPY --from=frontend-builder /app/dist/ /usr/share/nginx/html/

# 复制 Docker 专用 Nginx 配置
COPY deploy/nginx.docker.conf /etc/nginx/nginx.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:80/ || exit 1

EXPOSE 80
