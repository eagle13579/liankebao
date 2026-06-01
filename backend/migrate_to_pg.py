#!/usr/bin/env python3
"""
链客宝 SQLite → PostgreSQL 完整迁移脚本 v3
- 处理 INTEGER DEFAULT '' (PG 不接受空字符串作整数默认值)
- 处理 is_deleted/is_featured 等 bool 字段 (SQLite 存 0/1, PG Boolean 不兼容)
- 幂等 DROP → CREATE
"""

import os
import sys
import sqlite3
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Any

warnings.filterwarnings("ignore", message=".*SAWarning.*")
warnings.filterwarnings("ignore", message=".*ForeignKey.*")
warnings.filterwarnings("ignore", message=".*deprecated.*")
warnings.filterwarnings("ignore", category=UserWarning)

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Text,
    Float, Boolean, DateTime, Date, Time, LargeBinary, Numeric,
    BigInteger, SmallInteger, text, JSON as SQLA_JSON,
    UniqueConstraint, Index, ForeignKeyConstraint, inspect
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

SQLITE_DBS: Dict[str, str] = {
    "main": os.path.join(DATA_DIR, "chainke.db"),
    "crm": os.path.join(DATA_DIR, "crm.db"),
    "growth": os.path.join(DATA_DIR, "growth.db"),
    "enrichment_cache": os.path.join(DATA_DIR, "enrichment_cache.db"),
}

PG_CONFIGS: Dict[str, Dict[str, str]] = {
    "main": {
        "url": os.environ.get("DATABASE_URL", "postgresql://chainke:chainke_pg_2026@localhost:5432/chainke"),
        "db_name": "chainke",
    },
    "crm": {
        "url": os.environ.get("CRM_DATABASE_URL", "postgresql://chainke:chainke_pg_2026@localhost:5432/chainke_crm"),
        "db_name": "chainke_crm",
    },
    "growth": {
        "url": os.environ.get("GROWTH_DATABASE_URL", "postgresql://chainke:chainke_pg_2026@localhost:5432/chainke_growth"),
        "db_name": "chainke_growth",
    },
    "enrichment_cache": {
        "url": os.environ.get("ENRICHMENT_CACHE_DATABASE_URL", "postgresql://chainke:chainke_pg_2026@localhost:5432/chainke"),
        "db_name": "chainke",
    },
}

SKIP_TABLES = {"sqlite_sequence", "sqlite_stat1", "sqlite_stat4", "alembic_version"}

# 列名含这些关键词 → 用 SmallInteger (兼容 SQLite 0/1)
BOOL_LIKE_COLUMNS = {"is_deleted", "is_featured", "is_active", "is_verified", "is_enabled", "accepted", "is_approved"}


def map_sqlite_type_to_pg(sqlite_type: str, col_name: str = "") -> Any:
    """将 SQLite 列类型映射到 SQLAlchemy PostgreSQL 兼容类型"""
    t = sqlite_type.upper().strip() if sqlite_type else ""

    # bool 类列 → SmallInteger (兼容 SQLite 的 0/1)
    if col_name.lower() in BOOL_LIKE_COLUMNS:
        return SmallInteger

    # JSON 智能检测
    if col_name and any(k in col_name.lower() for k in ["json", "payload", "meta", "config"]):
        return SQLA_JSON

    if "BIGINT" in t:
        return BigInteger
    if "SMALLINT" in t or "TINYINT" in t:
        return SmallInteger
    if "INT" in t or "INTEGER" in t:
        return Integer
    if "REAL" in t or "FLOAT" in t or "DOUBLE" in t:
        return Float
    if "NUMERIC" in t or "DECIMAL" in t:
        return Numeric(18, 6)
    if "BOOL" in t:
        return SmallInteger  # 不用 Boolean, 避免 0/1 转换问题
    if "BLOB" in t or "BINARY" in t:
        return LargeBinary
    if "CLOB" in t or "TEXT" in t or "CHAR" in t or "VARCHAR" in t or "STRING" in t:
        return Text
    if "DATE" in t and "TIME" in t:
        return DateTime
    if "DATE" in t:
        return Date
    if "TIME" in t:
        return Time
    if "TIMESTAMP" in t:
        return DateTime
    if "JSON" in t:
        return SQLA_JSON
    return Text


def get_sqlite_schema(db_path: str, db_name: str) -> Optional[Dict]:
    """从 SQLite 数据库读取完整 schema"""
    if not os.path.exists(db_path):
        print(f"  [!] {db_name}: {db_path} 不存在，跳过")
        return None
    size_kb = os.path.getsize(db_path) / 1024
    if size_kb < 1:
        print(f"  [!] {db_name}: {db_path} 为空，跳过")
        return None
    print(f"  [i] SQLite 文件大小: {size_kb:.1f} KB")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    tables_info: Dict[str, Dict] = {}
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    for row in cursor.fetchall():
        table_name = row["name"]
        if table_name.startswith("sqlite_") or table_name in SKIP_TABLES:
            continue
        try:
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = []
            for col in cursor.fetchall():
                columns.append({
                    "name": col["name"],
                    "type": col["type"],
                    "nullable": not col["notnull"],
                    "default": col["dflt_value"],
                    "primary_key": bool(col["pk"]),
                })
            cursor.execute(f'PRAGMA index_list("{table_name}")')
            indexes = []
            for idx in cursor.fetchall():
                idx_name = idx["name"]
                cursor.execute(f'PRAGMA index_info("{idx_name}")')
                idx_cols = [c["name"] for c in cursor.fetchall()]
                indexes.append({
                    "name": idx_name,
                    "unique": bool(idx["unique"]),
                    "columns": idx_cols,
                })
            cursor.execute(f'PRAGMA foreign_key_list("{table_name}")')
            foreign_keys = []
            for fk in cursor.fetchall():
                foreign_keys.append({
                    "column": fk["from"],
                    "ref_table": fk["table"],
                    "ref_column": fk["to"],
                })
            tables_info[table_name] = {
                "columns": columns,
                "indexes": indexes,
                "foreign_keys": foreign_keys,
            }
            print(f"  [+] {table_name}: {len(columns)} 列, {len(indexes)} 索引, {len(foreign_keys)} 外键")
        except Exception as e:
            print(f"  [✗] {table_name}: schema 读取失败 - {e}")
    conn.close()
    return tables_info


def create_pg_tables(engine, table_name: str, table_info: Dict) -> bool:
    """在 PostgreSQL 中创建表"""
    try:
        columns: List[Column] = []
        for col in table_info["columns"]:
            col_type = map_sqlite_type_to_pg(col["type"], col["name"])
            col_kwargs = {
                "name": col["name"],
                "type_": col_type,
                "nullable": col["nullable"],
                "primary_key": col["primary_key"],
            }
            # 处理默认值：空字符串默认值对数值类型无效
            if col["default"] is not None:
                default_str = str(col["default"])
                col_type_cls = map_sqlite_type_to_pg(col["type"], col["name"])
                is_numeric = col_type_cls in (Integer, BigInteger, SmallInteger, Float, Numeric)

                # 跳过空字符串默认值（对数值类型无效）
                if is_numeric and (default_str == "''" or default_str == '""' or default_str == ""):
                    pass  # 不设置 server_default
                elif default_str.upper() in ("CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"):
                    col_kwargs["server_default"] = text(default_str)
                elif default_str.startswith("'") and default_str.endswith("'"):
                    col_kwargs["server_default"] = text(f"'{default_str[1:-1]}'")
                else:
                    try:
                        int(default_str)
                        col_kwargs["server_default"] = text(default_str)
                    except ValueError:
                        try:
                            float(default_str)
                            col_kwargs["server_default"] = text(default_str)
                        except ValueError:
                            col_kwargs["server_default"] = text(f"'{default_str}'")

            columns.append(Column(**col_kwargs))

        metadata = MetaData()
        table = Table(table_name, metadata, *columns, extend_existing=True)
        insp = inspect(engine)
        if insp.has_table(table_name):
            table.drop(engine)
        table.create(engine)

        # 创建索引
        for idx in table_info["indexes"]:
            try:
                idx_name = idx["name"]
                if idx_name.startswith("sqlite_autoindex"):
                    continue
                valid_cols = [table.c[c] for c in idx["columns"] if c in table.c]
                if not valid_cols:
                    continue
                idx_obj = Index(idx_name, *valid_cols, unique=idx["unique"])
                try:
                    idx_obj.create(engine)
                except Exception:
                    try:
                        idx_obj.drop(engine, checkfirst=True)
                        idx_obj.create(engine)
                    except Exception:
                        pass
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"  [✗] {table_name}: 创建失败 - {e}")
        return False


def migrate_data(sqlite_path: str, pg_engine, tables_info: Dict) -> int:
    """将数据从 SQLite 批量迁移到 PostgreSQL"""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.text_factory = lambda x: str(x, "utf-8", errors="replace")

    total_rows = 0
    for table_name, info in tables_info.items():
        try:
            rows = conn.execute(f'SELECT * FROM "{table_name}"').fetchall()
            if not rows:
                print(f"  [ ] {table_name}: 0 行")
                continue

            columns = [col["name"] for col in info["columns"]]
            # 缓存列类型信息，用于数据转换
            col_types = {col["name"]: map_sqlite_type_to_pg(col["type"], col["name"]) for col in info["columns"]}

            batch_size = 500
            batches = [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]

            with pg_engine.begin() as pg_conn:
                for batch in batches:
                    records = []
                    for row in batch:
                        record = {}
                        for col_name in columns:
                            val = row[col_name]
                            if isinstance(val, bytes):
                                try:
                                    val = val.decode("utf-8")
                                except UnicodeDecodeError:
                                    val = val.hex()
                            record[col_name] = val
                        records.append(record)

                    col_names = ", ".join(f'"{c}"' for c in columns)
                    placeholders = ", ".join(f":{c}" for c in columns)
                    insert_sql = text(f"INSERT INTO \"{table_name}\" ({col_names}) VALUES ({placeholders})")
                    pg_conn.execute(insert_sql, records)

            print(f"  [>] {table_name}: {len(rows)} 行")
            total_rows += len(rows)
        except Exception as e:
            print(f"  [✗] {table_name}: 迁移失败 - {e}")

    conn.close()
    return total_rows


def verify_migration(pg_engine, tables_info: Dict) -> Dict[str, int]:
    """验证 PostgreSQL 中各表数据量"""
    result: Dict[str, int] = {}
    with pg_engine.connect() as conn:
        for table_name in tables_info:
            try:
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                result[table_name] = count
            except Exception as e:
                print(f"  [✗] {table_name}: 验证失败 - {e}")
                result[table_name] = -1
    return result


def main():
    print("=" * 60)
    print("  链客宝 SQLite → PostgreSQL 完整迁移 v3")
    print(f"  时间: {datetime.now().isoformat()}")
    print(f"  数据目录: {DATA_DIR}")
    print("=" * 60)

    results: Dict[str, Dict] = {}
    for db_key in ["main", "crm", "growth", "enrichment_cache"]:
        sqlite_path = SQLITE_DBS[db_key]
        pg_url = PG_CONFIGS[db_key]["url"]
        pg_db_name = PG_CONFIGS[db_key]["db_name"]

        print(f"\n{'='*60}")
        print(f"  数据库: [{db_key}]  SQLite→PG:{pg_db_name}")
        print(f"{'='*60}")

        # 1. Schema
        print(f"\n  步骤 1: 读取 SQLite schema...")
        tables_info = get_sqlite_schema(sqlite_path, db_key)
        if tables_info is None or len(tables_info) == 0:
            print(f"  → 跳过")
            results[db_key] = {"status": "skipped", "reason": "无有效表"}
            continue
        print(f"  发现 {len(tables_info)} 个表")

        # 2. Connect PG
        print(f"\n  步骤 2: 连接 PostgreSQL...")
        try:
            pg_engine = create_engine(pg_url, pool_pre_ping=True, pool_size=2)
            with pg_engine.connect() as c:
                c.execute(text("SELECT 1"))
            print(f"  ✓ 连接成功")
        except Exception as e:
            print(f"  ✗ 连接失败: {e}")
            results[db_key] = {"status": "failed", "error": str(e)}
            continue

        # 3. Create + Migrate
        print(f"\n  步骤 3: 建表+迁移数据...")
        created = 0
        for table_name in tables_info:
            if create_pg_tables(pg_engine, table_name, tables_info[table_name]):
                created += 1
        print(f"  ✓ 创建 {created}/{len(tables_info)} 个表")

        total_rows = migrate_data(sqlite_path, pg_engine, tables_info)
        print(f"  ✓ 迁移 {total_rows} 行")

        # 4. Verify
        print(f"\n  步骤 4: 验证...")
        counts = verify_migration(pg_engine, tables_info)
        pg_total = sum(v for v in counts.values() if v >= 0)
        mismatches = [t for t, c in counts.items() if c < 0]
        print(f"  ✓ PG 共 {pg_total} 行")
        if mismatches:
            print(f"  ⚠ {len(mismatches)} 个表异常")

        results[db_key] = {
            "status": "success" if not mismatches else "partial",
            "tables": len(tables_info),
            "tables_created": created,
            "rows_migrated": total_rows,
            "rows_verified": pg_total,
        }

    # Summary
    print(f"\n{'='*60}")
    print("  迁移总结")
    print(f"{'='*60}")
    grand_total = 0
    for db_key, res in results.items():
        status = res.get("status", "unknown")
        icon = "✓" if status == "success" else ("⚠" if "skip" in status else "✗")
        rows = res.get("rows_migrated", 0) or 0
        grand_total += rows
        print(f"  [{icon}] {db_key:20s} → {status:8s}  ({rows} 行)")

    print(f"\n  总计: {grand_total} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
