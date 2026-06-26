"""
链客宝 - 数据库配置与模型基类
=================================
提供 SQLAlchemy 引擎、SessionLocal、Base 模型基类，
供 FastAPI 路由和测试使用。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# SQLite 数据库 (默认本地文件)
# ---------------------------------------------------------------------------
SQLALCHEMY_DATABASE_URL = "sqlite:///./chainke.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 多线程支持
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ---------------------------------------------------------------------------
# FastAPI 依赖注入 —— 获取数据库会话
# ---------------------------------------------------------------------------


def get_db():
    """FastAPI 中间件/路由的数据库会话依赖"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
