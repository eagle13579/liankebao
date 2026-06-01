"""
链客宝后端 - FastAPI 主入口

使用方式:
    uvicorn app:app --host 0.0.0.0 --port 8003

环境变量:
    DB_TYPE:      sqlite (默认) | mysql
    DATABASE_URL: 数据库连接字符串 (可选, 默认使用 SQLite)
    SQL_ECHO:     SQLAlchemy 日志输出 true/false (默认 false)
    CORS_ORIGINS: 允许的跨域源 (逗号分隔, 默认 *)
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app import __version__

# ── 日志配置 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("liankebao")

# ── CORS 配置 ─────────────────────────────────────────────────
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("链客宝后端启动中...")

    # 1. 初始化数据库表 (SQLAlchemy models)
    import app.models  # noqa: F401 — 确保所有模型已注册
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表已就绪")

    # 2. 初始化数字图册数据库 (原生 sqlite3)
    from digital_brochure_api import init_db as init_brochure_db
    init_brochure_db()
    logger.info("数字图册数据库已就绪")

    # 3. 初始化工作流引擎
    from modules.workflow.routes import init_workflow_engine
    init_workflow_engine(app)
    logger.info("工作流引擎已就绪")

    yield

    # 关闭资源
    logger.info("链客宝后端关闭中...")
    engine.dispose()


# ── FastAPI 应用实例 ──────────────────────────────────────────
app = FastAPI(
    title="链客宝 API",
    description="链客宝后端服务 - 客户关系管理与商机匹配平台",
    version=__version__,
    lifespan=lifespan,
)

# ── 中间件 ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(",") if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由 ──────────────────────────────────────────────────────

# 数字图册 API 路由 (如果 FastAPI 可用)
try:
    from digital_brochure_api import router as brochure_router
    if brochure_router is not None:
        app.include_router(brochure_router)
        logger.info("数字图册 API 路由已挂载")
except Exception as e:
    logger.warning("数字图册 API 路由挂载失败: %s", e)


# ── 健康检查 ──────────────────────────────────────────────────


@app.get("/health", tags=["系统"])
async def health_check():
    """系统健康检查"""
    return {
        "status": "ok",
        "service": "liankebao",
        "version": __version__,
        "db_type": os.getenv("DB_TYPE", "sqlite"),
    }


@app.get("/", tags=["系统"])
async def root():
    """根路径"""
    return {
        "service": "链客宝 API",
        "version": __version__,
        "docs": "/docs",
    }
