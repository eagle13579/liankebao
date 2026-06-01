"""
数据库连接与会话管理
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 数据库类型: sqlite | mysql
DB_TYPE = os.getenv("DB_TYPE", "sqlite")

if DB_TYPE == "mysql":
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://liankebao:CHANGE_ME_PLEASE@127.0.0.1:3306/liankebao?charset=utf8mb4",
    )
else:
    # SQLite 默认
    db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(db_dir, exist_ok=True)
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{db_dir}/chainke.db")

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    connect_args={"check_same_thread": False} if DB_TYPE == "sqlite" else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖: 获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
