"""
SQLite → MySQL 数据迁移脚本
从 SQLite 数据库读取所有数据，写入 MySQL 数据库

用法:
    python scripts/migrate_to_mysql.py

环境变量:
    SQLITE_PATH: SQLite 数据库路径（默认 backend/data/chainke.db）
    DATABASE_URL: MySQL 连接串（默认从环境变量读取）
"""
import os
import sys
import json

# 添加项目根目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import sessionmaker
from datetime import datetime


def get_sqlite_engine(sqlite_path: str = None):
    """获取 SQLite 引擎"""
    if sqlite_path and os.path.exists(sqlite_path):
        db_path = sqlite_path
    else:
        # 默认路径
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        db_path = os.path.join(base_dir, "chainke.db")

    if not os.path.exists(db_path):
        print(f"错误: SQLite 数据库不存在: {db_path}")
        sys.exit(1)

    print(f"SQLite 数据库: {db_path}")
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    return engine


def get_mysql_engine(mysql_url: str = None):
    """获取 MySQL 引擎"""
    url = mysql_url or os.environ.get("DATABASE_URL", "")
    if not url:
        print("错误: 未设置 DATABASE_URL 环境变量")
        sys.exit(1)

    print(f"MySQL 连接: {url[:50]}...")
    engine = create_engine(url, echo=False)
    return engine


def migrate_table(sqlite_engine, mysql_engine, table_name: str, columns: list):
    """迁移单个表的数据"""
    # 从 SQLite 读取
    sqlite_conn = sqlite_engine.connect()
    rows = sqlite_conn.execute(f"SELECT * FROM {table_name}").fetchall()
    column_names = [c.name for c in columns]
    sqlite_conn.close()

    if not rows:
        print(f"  表 {table_name}: 无数据，跳过")
        return

    print(f"  表 {table_name}: {len(rows)} 条记录")

    # 写入 MySQL
    mysql_conn = mysql_engine.connect()
    transaction = mysql_conn.begin()

    try:
        # 清空目标表
        mysql_conn.execute(f"TRUNCATE TABLE {table_name}")

        # 批量插入
        placeholders = ", ".join([f":{name}" for name in column_names])
        cols = ", ".join(column_names)
        insert_sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

        batch_size = 100
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            params_list = []
            for row in batch:
                params = {}
                for idx, col_name in enumerate(column_names):
                    val = row[idx]
                    # 处理特殊类型
                    if isinstance(val, datetime):
                        val = val.strftime("%Y-%m-%d %H:%M:%S")
                    params[col_name] = val
                params_list.append(params)
            mysql_conn.execute(insert_sql, params_list)

        transaction.commit()
        print(f"  表 {table_name}: 迁移完成 ({len(rows)} 条)")
    except Exception as e:
        transaction.rollback()
        print(f"  表 {table_name}: 迁移失败: {e}")
        raise


def main():
    print("=" * 60)
    print("SQLite → MySQL 数据迁移")
    print("=" * 60)

    # 获取引擎
    sqlite_path = os.environ.get("SQLITE_PATH", "")
    sqlite_engine = get_sqlite_engine(sqlite_path)

    mysql_url = os.environ.get("DATABASE_URL", "")
    mysql_engine = get_mysql_engine(mysql_url)

    # 在 MySQL 中创建表（使用 models 中的 Base）
    print("\n创建 MySQL 表结构...")
    from app.database import Base as SQLiteBase
    from app.models import User, Product, Order, Withdrawal  # noqa

    # 使用 models 中的 Base（其实应该用 database_mysql 的 Base）
    # 由于 Base 相同（declarative_base()），直接 create_all
    SQLiteBase.metadata.create_all(bind=mysql_engine)
    print("MySQL 表结构创建完成")

    # 迁移数据
    print("\n开始迁移数据...")

    # 定义表结构（按外键依赖顺序）
    tables_info = [
        ("users", User.__table__.columns),
        ("products", Product.__table__.columns),
        ("orders", Order.__table__.columns),
        ("withdrawals", Withdrawal.__table__.columns),
    ]

    for table_name, columns in tables_info:
        migrate_table(sqlite_engine, mysql_engine, table_name, list(columns))

    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
