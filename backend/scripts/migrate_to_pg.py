#!/usr/bin/env python3
"""
migrate_to_pg.py — 将 SQLite 数据迁移到 PostgreSQL

使用方法:
    python migrate_to_pg.py [--sqlite path/to/data.db] [--pg-url postgresql://user:pass@host/db]
"""

import argparse

from sqlalchemy import create_engine, inspect, text

# ── 配置 ─────────────────────────────────────────────

# 18 张表的顺序（按外键依赖排序，先迁移父表）
TABLES = [
    "organization",
    "user",
    "role",
    "permission",
    "role_permission",
    "user_role",
    "customer",
    "supplier",
    "product",
    "product_category",
    "inventory",
    "purchase_order",
    "purchase_order_item",
    "sales_order",
    "sales_order_item",
    "payment",
    "receipt",
    "system_log",
]

# 需要特殊处理 organization_id 为 NULL 的表
ORGANIZATION_ID_NULLABLE_TABLES = [
    "user",
    "role",
    "customer",
    "supplier",
    "product",
    "product_category",
    "inventory",
    "purchase_order",
    "purchase_order_item",
    "sales_order",
    "sales_order_item",
    "payment",
    "receipt",
    "system_log",
]


def get_column_names(engine, table_name):
    """获取表的列名列表"""
    insp = inspect(engine)
    columns = insp.get_columns(table_name)
    return [col["name"] for col in columns]


def migrate_table(
    sqlite_engine,
    pg_engine,
    table_name,
    org_nullable_tables,
    batch_size=500,
):
    """
    将单张表从 SQLite 迁移到 PostgreSQL。
    """
    # 获取源表列名
    columns = get_column_names(sqlite_engine, table_name)
    has_org_col = "organization_id" in columns

    # 检查目标表结构
    pg_columns = get_column_names(pg_engine, table_name)
    if not pg_columns:
        print(f"  ⚠ 目标表 '{table_name}' 不存在，跳过")
        return 0, 0

    # 读 SQLite
    with sqlite_engine.connect() as conn:
        result = conn.execute(text(f"SELECT * FROM {table_name}"))
        rows = result.mappings().all()

    total = len(rows)
    inserted = 0

    if total == 0:
        print(f"  ✓ {table_name}: 0 行（空表）")
        return 0, 0

    # 写 PostgreSQL（逐批插入）
    with pg_engine.connect() as pg_conn:
        # 清空目标表
        pg_conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
        pg_conn.commit()

        placeholders = ", ".join(f":{col}" for col in columns)
        col_names = ", ".join(columns)
        stmt = text(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})")

        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            batch_data = []
            for row in batch:
                row_dict = dict(row)
                # organization_id 为 NULL → 自动分配到 1
                if has_org_col and table_name in org_nullable_tables and row_dict.get("organization_id") is None:
                    row_dict["organization_id"] = 1
                batch_data.append(row_dict)

            for row_dict in batch_data:
                pg_conn.execute(stmt, row_dict)
            pg_conn.commit()
            inserted += len(batch_data)
            print(f"  · {table_name}: 已插入 {inserted}/{total} 行", end="\r")

        print()
        print(f"  ✓ {table_name}: 迁移完成 ({inserted} 行)")

    return total, inserted


def verify_counts(sqlite_engine, pg_engine):
    """逐表验证记录数是否一致"""
    print("\n═══ 验证记录数 ═══")
    all_match = True
    for table_name in TABLES:
        with sqlite_engine.connect() as conn:
            src_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        with pg_engine.connect() as conn:
            dst_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        match = "✓" if src_count == dst_count else "✗"
        if src_count != dst_count:
            all_match = False
        print(f"  {match} {table_name}: SQLite={src_count}  →  PG={dst_count}")
    if all_match:
        print("\n✅ 所有表记录数一致，迁移验证通过！")
    else:
        print("\n❌ 部分表记录数不一致，请检查！")
    return all_match


def main():
    parser = argparse.ArgumentParser(description="将 SQLite 数据迁移到 PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default="data.db",
        help="SQLite 数据库路径（默认: data.db）",
    )
    parser.add_argument(
        "--pg-url",
        dest="pg_url",
        default="postgresql://postgres:postgres@localhost:5432/lkb",
        help="PostgreSQL 连接 URL（默认: postgresql://postgres:postgres@localhost:5432/lkb）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="每批插入行数（默认: 500）",
    )
    args = parser.parse_args()

    print("═══ SQLite → PostgreSQL 数据迁移 ═══")
    print(f"  SQLite: {args.sqlite}")
    print(f"  PG:     {args.pg_url}")
    print()

    # 创建 engine
    sqlite_engine = create_engine(f"sqlite:///{args.sqlite}", echo=False)
    pg_engine = create_engine(args.pg_url, echo=False)

    total_src = 0
    total_dst = 0

    for table_name in TABLES:
        print(f"─── {table_name} ───")
        src_count, dst_count = migrate_table(
            sqlite_engine,
            pg_engine,
            table_name,
            ORGANIZATION_ID_NULLABLE_TABLES,
            args.batch_size,
        )
        total_src += src_count
        total_dst += dst_count

    print("\n═══ 汇总 ═══")
    print(f"  总计源表行数: {total_src}")
    print(f"  总计目标行数: {total_dst}")

    # 验证
    verify_counts(sqlite_engine, pg_engine)

    print("\n✅ 迁移脚本执行完毕！")


if __name__ == "__main__":
    main()
