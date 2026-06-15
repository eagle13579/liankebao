#!/usr/bin/env python3
"""
链客宝 organization_id 回填脚本

功能:
1. 扫描所有表中 organization_id 为 NULL 的记录
2. 为每个用户创建一个默认组织（如果不存在）
3. 更新所有记录的 organization_id

用法:
    python app/backfill_org_id.py

选项:
    --dry-run    只扫描不更新
    --db sqlite  使用 SQLite 模式
    --db pg      使用 PostgreSQL 模式（默认）
"""

import argparse
import logging
import os
import uuid
from datetime import datetime

from sqlalchemy import create_engine, inspect, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backfill")

# ============================================================
# Configuration
# ============================================================
SQLITE_PATH = os.environ.get(
    "SQLITE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chainke.db"),
)

PG_HOST = os.environ.get("PG_HOST", "47.116.116.87")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_USER = os.environ.get("PG_USER", "chainke")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "Ch@1nKe_PG_2026")
PG_DATABASE = os.environ.get("PG_DATABASE", "chainke")
PG_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"

# ============================================================
# Tables that should have organization_id
# ============================================================
TABLES_WITH_ORG_ID = [
    "users",
    "products",
    "orders",
    "contacts",
    "activities",
    "import_history",
    "business_needs",
    "business_cards",
    "visitor_logs",
    "user_events",
    "withdrawals",
    "private_board_orders",
    "membership_orders",
    "match_credit_logs",
    "online_matching_events",
    "online_matching_registrations",
    "online_matching_feedback",
    "revoked_tokens",
]

# Tables with user reference columns (for mapping records to users)
TABLE_USER_COL_MAP = {
    "users": "id",  # self-referential
    "products": "owner_id",
    "orders": "user_id",
    "contacts": "owner_id",
    "activities": None,  # uses contact_id -> contacts -> owner_id
    "import_history": "user_id",
    "business_needs": "user_id",
    "business_cards": "user_id",
    "visitor_logs": "visitor_id",
    "user_events": "user_id",
    "withdrawals": "user_id",
    "private_board_orders": "user_id",
    "membership_orders": "user_id",
    "match_credit_logs": "user_id",
    "online_matching_events": None,  # no direct user col, use default org
    "online_matching_registrations": "user_id",
    "online_matching_feedback": "user_id",
    "revoked_tokens": None,  # no user col, use default org
}


def get_connection(db_type):
    """获取数据库连接"""
    if db_type == "sqlite":
        engine = create_engine(f"sqlite:///{SQLITE_PATH}")
        conn = engine.connect()
        logger.info(f"连接 SQLite: {SQLITE_PATH}")
        return engine, conn
    else:
        engine = create_engine(PG_URL)
        conn = engine.connect()
        logger.info(f"连接 PostgreSQL: {PG_HOST}:{PG_PORT}/{PG_DATABASE}")
        return engine, conn


def get_pg_tables(conn):
    """获取 PG 中的所有表"""
    insp = inspect(conn)
    return insp.get_table_names()


def get_sqlite_tables(conn):
    """获取 SQLite 中的所有表"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence') ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def create_default_organization(conn, user_id, username, company_name):
    """为指定用户创建默认组织"""
    slug = f"org_{username}_{uuid.uuid4().hex[:8]}"
    name = company_name or f"{username}的默认组织"
    try:
        result = conn.execute(
            text("""
                INSERT INTO organizations (name, slug, owner_id, created_at)
                VALUES (:name, :slug, :owner_id, :created_at)
                RETURNING id
            """),
            {
                "name": name,
                "slug": slug,
                "owner_id": user_id,
                "created_at": datetime.utcnow(),
            },
        )
        org_id = result.fetchone()[0]
        logger.info(f"  创建组织: {name} (id={org_id}, owner={username})")

        # 创建成员关联
        try:
            conn.execute(
                text("""
                    INSERT INTO organization_members (org_id, user_id, role, joined_at)
                    VALUES (:org_id, :user_id, :role, :joined_at)
                """),
                {
                    "org_id": org_id,
                    "user_id": user_id,
                    "role": "admin",
                    "joined_at": datetime.utcnow(),
                },
            )
        except Exception:
            pass  # 可能已存在

        conn.commit()
        return org_id
    except Exception as e:
        logger.warning(f"  创建组织失败: {e}")
        conn.rollback()
        return None


def scan_and_backfill(db_type="pg", dry_run=False):
    """扫描并回填 organization_id"""
    engine, conn = get_connection(db_type)
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}开始扫描 organization_id 为 NULL 的记录")

    # 获取表列表
    if db_type == "sqlite":
        tables = get_sqlite_tables(conn)
    else:
        tables = get_pg_tables(conn)

    # 统计
    total_null = 0
    total_fixed = 0

    # Step 1: 检查用户表
    logger.info("\n--- Step 1: 检查和创建用户组织 ---")
    users_without_org = conn.execute(
        text('SELECT id, username, name, company FROM "users" WHERE organization_id IS NULL')
    ).fetchall()
    logger.info(f"有 {len(users_without_org)} 个用户无组织")

    if not dry_run:
        for user in users_without_org:
            user_id = user[0]
            username = user[1] or f"user_{user_id}"
            name = user[2] or username
            company = user[3] or None

            org_id = create_default_organization(conn, user_id, username, company)
            if org_id:
                conn.execute(
                    text('UPDATE "users" SET organization_id = :org_id WHERE id = :id'),
                    {"org_id": org_id, "id": user_id},
                )
                conn.commit()
                total_fixed += 1
                logger.info(f"  更新用户 {username}(id={user_id}) organization_id={org_id}")

    # Step 2: 收集所有用户的 org_id 映射
    user_orgs = conn.execute(
        text('SELECT id, organization_id FROM "users" WHERE organization_id IS NOT NULL')
    ).fetchall()
    org_map = {row[0]: row[1] for row in user_orgs}
    logger.info(f"用户-组织映射: {len(org_map)} 条")

    # 获取默认组织（第一个）
    default_org = conn.execute(text("SELECT id FROM organizations LIMIT 1")).fetchone()
    default_org_id = default_org[0] if default_org else None

    # Step 3: 回填所有业务表的 organization_id
    logger.info("\n--- Step 2: 回填业务表 organization_id ---")
    for table_name in tables:
        if table_name not in TABLES_WITH_ORG_ID:
            continue
        if table_name == "users":
            continue  # 已经在 Step 1 处理

        try:
            # 检查列是否存在
            if db_type == "pg":
                insp = inspect(conn)
                columns = [col["name"] for col in insp.get_columns(table_name)]
            else:
                cursor = conn.execute(f'PRAGMA table_info("{table_name}")')
                columns = [row[1] for row in cursor.fetchall()]

            if "organization_id" not in columns:
                logger.warning(f"  {table_name}: 无 organization_id 列，跳过")
                continue

            user_col = TABLE_USER_COL_MAP.get(table_name)
            if not user_col:
                # 使用默认组织
                null_rows = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}" WHERE organization_id IS NULL')
                ).fetchone()[0]
                if null_rows > 0:
                    total_null += null_rows
                    logger.info(f"  {table_name}: {null_rows} 条无组织记录 (使用默认组织)")
                    if not dry_run and default_org_id:
                        conn.execute(
                            text(f'UPDATE "{table_name}" SET organization_id = :org_id WHERE organization_id IS NULL'),
                            {"org_id": default_org_id},
                        )
                        conn.commit()
                        total_fixed += null_rows
                continue

            # 通过用户列映射
            null_rows = conn.execute(
                text(f'SELECT id, "{user_col}" FROM "{table_name}" WHERE organization_id IS NULL')
            ).fetchall()

            if not null_rows:
                continue

            total_null += len(null_rows)
            logger.info(f"  {table_name}: {len(null_rows)} 条无组织记录")

            if not dry_run:
                fixed = 0
                for row in null_rows:
                    row_id = row[0]
                    ref_user_id = row[1]
                    user_id_for_org = ref_user_id if ref_user_id is not None else None

                    # 处理 activities 表（通过 contact_id 间接关联）
                    if table_name == "activities" and user_col is None:
                        continue  # handled above

                    org_id = org_map.get(user_id_for_org, default_org_id)
                    if org_id:
                        conn.execute(
                            text(f'UPDATE "{table_name}" SET organization_id = :org_id WHERE id = :id'),
                            {"org_id": org_id, "id": row_id},
                        )
                        fixed += 1

                if fixed > 0:
                    conn.commit()
                    total_fixed += fixed
                    logger.info(f"  {table_name}: 更新 {fixed} 条")

        except Exception as e:
            logger.warning(f"  处理 {table_name} 失败: {e}")
            conn.rollback()

    logger.info("\n" + "=" * 60)
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}回填完成!")
    logger.info(f"  无组织记录数: {total_null}")
    logger.info(f"  已更新记录数: {total_fixed}")
    logger.info("=" * 60)

    conn.close()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="链客宝 organization_id 回填工具")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不更新")
    parser.add_argument("--db", choices=["sqlite", "pg"], default="pg", help="数据库类型")
    args = parser.parse_args()

    logger.info("链客宝 organization_id 回填脚本")
    scan_and_backfill(db_type=args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
