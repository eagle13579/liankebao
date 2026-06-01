# ============================================================
# 链客宝后端 - Docker 镜像
# ============================================================
FROM python:3.12-slim

LABEL maintainer="liankebao"
LABEL description="链客宝后端服务 - FastAPI + SQLAlchemy"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# 安装系统依赖 (仅最小依赖)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ .

# 创建数据目录 (用于 SQLite 持久化)
RUN mkdir -p /app/data && chmod 755 /app/data

# 暴露端口
EXPOSE 8003

# 启动服务
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
