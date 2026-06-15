"""
MySQL 独立数据库引擎模块
可直接用于迁移脚本或需要直连 MySQL 的场景

环境变量:
    DB_TYPE=mysql              — 显式指定（推荐）
    DATABASE_URL: MySQL 连接串 — 兼容旧配置
    示例: mysql+pymysql://user:***@host:port/dbname?charset=utf8mb4
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL", "")

Base = declarative_base()

engine = None
SessionLocal = None

# 仅在 DB_TYPE=mysql 或 DATABASE_URL 以 mysql 开头时激活
_db_type = os.environ.get("DB_TYPE", "").strip().lower()
_use_mysql = _db_type == "mysql" or (not _db_type and DATABASE_URL.startswith("mysql"))

if _use_mysql and DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI 依赖注入：获取数据库会话（MySQL版）"""
    if SessionLocal is None:
        raise RuntimeError("MySQL 未配置，请设置 DB_TYPE=mysql 和 DATABASE_URL 环境变量")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化 MySQL 数据库：创建表"""
    if engine is None:
        raise RuntimeError("MySQL 未配置，请设置 DB_TYPE=mysql 和 DATABASE_URL 环境变量")
    from app.models import User, Product, Order, Withdrawal  # noqa
    Base.metadata.create_all(bind=engine)
    print("MySQL 数据库表创建完成")


def get_engine():
    """获取 MySQL 引擎（供迁移脚本使用）"""
    return engine
