"""
PostgreSQL 独立数据库引擎模块
可直接用于迁移脚本或需要直连 PostgreSQL 的场景

环境变量:
    PG_HOST: PostgreSQL 主机地址（默认 localhost）
    PG_PORT: PostgreSQL 端口（默认 5432）
    PG_USER: PostgreSQL 用户名
    PG_PASSWORD: PostgreSQL 密码
    PG_DATABASE: PostgreSQL 数据库名

若上述 PG_* 变量未设置，自动回退到 SQLite（兼容开发环境）
"""
import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ========================
# PostgreSQL 配置
# ========================
PG_HOST = os.environ.get("PG_HOST", "")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_USER = os.environ.get("PG_USER", "")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
PG_DATABASE = os.environ.get("PG_DATABASE", "")

# ========================
# 数据库引擎选择
# ========================
_USE_POSTGRES = all([PG_HOST, PG_USER, PG_PASSWORD, PG_DATABASE])

# 尝试导入 psycopg2（仅 PG 模式下需要）
_PG_DRIVER_AVAILABLE = False
if _USE_POSTGRES:
    try:
        import psycopg2  # noqa: F401
        _PG_DRIVER_AVAILABLE = True
    except ImportError:
        print(
            "警告: PostgreSQL 环境变量已设置，但未安装 psycopg2。\n"
            "请执行: pip install psycopg2-binary\n"
            "将回退到 SQLite 模式。"
        )
        _USE_POSTGRES = False

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

engine = None
SessionLocal = None

if _USE_POSTGRES and _PG_DRIVER_AVAILABLE:
    # PostgreSQL 模式
    PG_URL = (
        f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}"
        f"@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
    )
    engine = create_engine(
        PG_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info(f"PostgreSQL 模式: {PG_HOST}:{PG_PORT}/{PG_DATABASE}")
else:
    # SQLite 回退模式
    DB_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    DB_PATH = os.path.join(DB_DIR, "chainke.db")
    os.makedirs(DB_DIR, exist_ok=True)
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info(f"SQLite 回退模式: {DB_PATH}")


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    if SessionLocal is None:
        raise RuntimeError("数据库未配置")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_engine():
    """获取数据库引擎（供迁移脚本使用）"""
    return engine


# ========================
# DDL 语句（PostgreSQL 版）
# ========================
PG_DDL_STATEMENTS = [
    # users 表
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        wechat_openid VARCHAR(100) UNIQUE,
        name VARCHAR(100) NOT NULL,
        phone VARCHAR(20),
        company VARCHAR(200),
        position VARCHAR(100),
        role VARCHAR(20) NOT NULL DEFAULT 'buyer',
        avatar VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # products 表
    """
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        description TEXT,
        price DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        earn_per_share DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        category VARCHAR(100),
        stock INTEGER NOT NULL DEFAULT 0,
        images TEXT,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        owner_id INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        specs TEXT,
        details TEXT,
        brand VARCHAR(100),
        sale_price DOUBLE PRECISION,
        video_url VARCHAR(500),
        tags VARCHAR(500),
        files TEXT,
        is_featured INTEGER DEFAULT 0,
        sort_order INTEGER DEFAULT 0
    );
    """,
    # orders 表
    """
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        quantity INTEGER NOT NULL DEFAULT 1,
        total_price DOUBLE PRECISION NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'paid',
        promoter_id INTEGER REFERENCES users(id),
        commission DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        wx_transaction_id VARCHAR(100),
        pay_time TIMESTAMP,
        prepay_id VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # withdrawals 表
    """
    CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        amount DOUBLE PRECISION NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        bank_info TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # 索引
    """
    CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_users_wechat_openid ON users(wechat_openid);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_products_owner_id ON products(owner_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_orders_product_id ON orders(product_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_orders_promoter_id ON orders(promoter_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_withdrawals_user_id ON withdrawals(user_id);
    """,
]


def create_pg_tables(connection):
    """在 PostgreSQL 连接上创建所有表"""
    logger.info("正在 PostgreSQL 中创建表结构...")
    for ddl in PG_DDL_STATEMENTS:
        connection.execute(ddl)
    logger.info("PostgreSQL 表结构创建完成")


def drop_pg_tables(connection):
    """删除 PostgreSQL 中的所有表（回滚用）"""
    logger.info("正在删除 PostgreSQL 中的表...")
    connection.execute("DROP TABLE IF EXISTS withdrawals CASCADE;")
    connection.execute("DROP TABLE IF EXISTS orders CASCADE;")
    connection.execute("DROP TABLE IF EXISTS products CASCADE;")
    connection.execute("DROP TABLE IF EXISTS users CASCADE;")
    logger.info("PostgreSQL 表已删除")


# ========================
# 数据迁移函数
# ========================

def export_from_sqlite(sqlite_path: Optional[str] = None) -> dict:
    """
    从 SQLite 数据库导出所有数据为字典（JSON 可序列化）

    返回: {
        "users": [ {...}, ... ],
        "products": [ {...}, ... ],
        "orders": [ {...}, ... ],
        "withdrawals": [ {...}, ... ],
        "export_time": "2026-05-16T20:00:00"
    }
    """
    if sqlite_path is None:
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        sqlite_path = os.path.join(base_dir, "chainke.db")

    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite 数据库不存在: {sqlite_path}")

    sqlite_url = f"sqlite:///{sqlite_path}"
    sqlite_engine = create_engine(sqlite_url, echo=False)
    conn = sqlite_engine.connect()

    data = {}
    table_names = ["users", "products", "orders", "withdrawals"]

    try:
        for table in table_names:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                columns = [desc[0] for desc in conn.execute(
                    f"SELECT * FROM {table} LIMIT 0"
                ).cursor.description]
                records = []
                for row in rows:
                    record = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        # datetime → ISO 字符串
                        if isinstance(val, datetime):
                            val = val.isoformat()
                        record[col] = val
                    records.append(record)
                data[table] = records
                logger.info(f"  导出 {table}: {len(records)} 条记录")
            except Exception as e:
                logger.warning(f"  跳过 {table}: {e}")
                data[table] = []

        data["export_time"] = datetime.utcnow().isoformat()
        return data

    finally:
        conn.close()
        sqlite_engine.dispose()


def import_to_postgres(
    data: dict,
    pg_connection=None,
    truncate_first: bool = True,
) -> dict:
    """
    将导出的数据字典导入到 PostgreSQL

    参数:
        data: export_from_sqlite() 返回的数据字典
        pg_connection: 已连接的 psycopg2 connection，如果为 None 则自动创建
        truncate_first: 是否在导入前清空目标表

    返回: {
        "users": 4,
        "products": 6,
        "orders": 3,
        "withdrawals": 2
    }
    """
    import psycopg2
    from psycopg2.extras import execute_values

    own_connection = False
    if pg_connection is None:
        pg_connection = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DATABASE,
        )
        pg_connection.autocommit = False
        own_connection = True

    stats = {}
    table_order = ["users", "products", "orders", "withdrawals"]

    try:
        cur = pg_connection.cursor()

        # 1. 确保表存在
        create_pg_tables(cur)

        # 2. 可选：清空表
        if truncate_first:
            for table in reversed(table_order):
                try:
                    cur.execute(f"TRUNCATE TABLE {table} CASCADE;")
                except Exception as e:
                    logger.warning(f"  清空 {table} 失败（可能不存在）: {e}")

        # 3. 按依赖顺序插入数据
        for table in table_order:
            records = data.get(table, [])
            if not records:
                stats[table] = 0
                logger.info(f"  导入 {table}: 0 条（无数据）")
                continue

            # 获取列名（跳过自动生成的 id 和 created_at 列？不，我们保留所有列）
            columns = list(records[0].keys())

            # 过滤掉 PostgreSQL 自动列（SERIAL 类型的 id 我们手动插入以确保一致性）
            # 但 id 在记录中是存在的，所以保留

            # 准备 VALUES 占位符
            col_names = ", ".join(columns)
            placeholders = ", ".join([f"%({c})s" for c in columns])

            insert_sql = (
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
            )

            batch_size = 100
            inserted = 0
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                try:
                    cur.executemany(insert_sql, batch)
                    inserted += len(batch)
                except Exception as e:
                    # 尝试逐条插入以跳过问题记录
                    logger.warning(f"  批量插入失败，尝试逐条: {e}")
                    for rec in batch:
                        try:
                            cur.execute(insert_sql, rec)
                            inserted += 1
                        except Exception as e2:
                            logger.error(
                                f"    跳过记录 {table}.id={rec.get('id', '?')}: {e2}"
                            )

            stats[table] = inserted
            logger.info(f"  导入 {table}: {inserted}/{len(records)} 条记录")

        pg_connection.commit()
        return stats

    except Exception as e:
        if own_connection and pg_connection:
            pg_connection.rollback()
        raise e

    finally:
        if own_connection and pg_connection:
            pg_connection.close()


def verify_data_consistency(sqlite_path: Optional[str] = None) -> dict:
    """
    验证 SQLite 和 PostgreSQL 之间的数据一致性
    返回: { "表名": { "sqlite": N, "postgres": N, "match": True/False, "detail": "..." } }
    """
    import psycopg2

    # 读取 SQLite 行数
    if sqlite_path is None:
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        sqlite_path = os.path.join(base_dir, "chainke.db")

    sqlite_url = f"sqlite:///{sqlite_path}"
    sqlite_engine = create_engine(sqlite_url, echo=False)
    sqlite_conn = sqlite_engine.connect()

    # 连接 PostgreSQL
    pg_conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DATABASE,
    )
    pg_cur = pg_conn.cursor()

    result = {}
    tables = ["users", "products", "orders", "withdrawals"]

    try:
        for table in tables:
            try:
                # SQLite 计数
                sqlite_count = sqlite_conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).scalar()

                # PostgreSQL 计数
                pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
                pg_count = pg_cur.fetchone()[0]

                match = sqlite_count == pg_count
                detail = "一致" if match else f"不一致（差异: {sqlite_count - pg_count}）"
                result[table] = {
                    "sqlite": sqlite_count,
                    "postgres": pg_count,
                    "match": match,
                    "detail": detail,
                }
            except Exception as e:
                result[table] = {
                    "sqlite": -1,
                    "postgres": -1,
                    "match": False,
                    "detail": str(e),
                }

        return result

    finally:
        sqlite_conn.close()
        sqlite_engine.dispose()
        pg_cur.close()
        pg_conn.close()
