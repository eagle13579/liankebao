#!/usr/bin/env python3
"""
链客宝 SQLite → PostgreSQL 数据迁移脚本

功能:
1. 连接 SQLite (data/chainke.db) 和 PostgreSQL (chainke 数据库)
2. 逐表同步数据（SQLite→PG）
3. 为缺少 organization_id 的表添加列
4. 创建缺失的表（visitor_logs, revoked_tokens 等）
5. 为每条没有 organization_id 的记录创建默认组织并分配

用法:
    python app/migrate_sqlite_to_pg.py

依赖:
    pip install psycopg2-binary sqlalchemy
"""

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
logger = logging.getLogger("migrate")

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
# Tables that need organization_id (from models.py _org_fk())
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

# ============================================================
# Tables that exist in SQLite but may not in PG (or vice versa)
# ============================================================
MISSING_TABLES_SQL = {
    "visitor_logs": """
        CREATE TABLE IF NOT EXISTS visitor_logs (
            id SERIAL PRIMARY KEY,
            brochure_id INTEGER NOT NULL,
            visitor_id INTEGER,
            page VARCHAR(50),
            duration INTEGER,
            interested BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            organization_id INTEGER
        )
    """,
    "revoked_tokens": """
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            id SERIAL PRIMARY KEY,
            jti VARCHAR(64) NOT NULL UNIQUE,
            revoked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            organization_id INTEGER
        )
    """,
}


def get_sqlite_tables(conn):
    """获取 SQLite 中所有业务表"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence') ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def get_pg_tables(insp):
    """获取 PostgreSQL 中所有表"""
    return insp.get_table_names()


def add_org_id_column_if_missing(pg_conn, table_name):
    """为 PG 表添加 organization_id 列（如果缺失）"""
    insp = inspect(pg_conn)
    columns = [col["name"] for col in insp.get_columns(table_name)]
    if "organization_id" not in columns and table_name in TABLES_WITH_ORG_ID:
        logger.info(f"  添加 organization_id 列到 {table_name}")
        pg_conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN organization_id INTEGER'))
        pg_conn.commit()


def create_missing_tables(pg_conn):
    """创建 PG 中缺失的表"""
    insp = inspect(pg_conn)
    existing = set(insp.get_table_names())
    for table_name, ddl in MISSING_TABLES_SQL.items():
        if table_name not in existing:
            logger.info(f"  创建缺失表 {table_name}")
            pg_conn.execute(text(ddl))
            pg_conn.commit()


def migrate_table(sqlite_conn, pg_conn, table_name):
    """从 SQLite 迁移一个表到 PG"""
    logger.info(f"迁移表: {table_name}")

    # 读取 SQLite 数据
    sqlite_rows = sqlite_conn.execute(text(f'SELECT * FROM "{table_name}"')).fetchall()
    if not sqlite_rows:
        logger.info(f"  {table_name}: 无数据，跳过")
        return 0

    # 获取列名
    sqlite_col_names = list(sqlite_rows[0]._mapping.keys())
    pg_insp = inspect(pg_conn)
    pg_columns = [col["name"] for col in pg_insp.get_columns(table_name)]

    # 只迁移 PG 中存在的列
    common_cols = [c for c in sqlite_col_names if c in pg_columns]
    if not common_cols:
        logger.warning(f"  {table_name}: 无共同列，跳过")
        return 0

    # 逐行插入（处理重复键）
    count = 0
    for row in sqlite_rows:
        row_dict = {k: v for k, v in row._mapping.items() if k in common_cols}
        # 类型转换
        for k, v in row_dict.items():
            if isinstance(v, bool):
                row_dict[k] = int(v)
            elif isinstance(v, datetime):
                row_dict[k] = v
            elif v is None:
                continue

        cols = list(row_dict.keys())
        placeholders = [f":{c}" for c in cols]
        values = {c: row_dict[c] for c in cols}

        # 如果是 users/products 等有业务唯一约束的表，使用 INSERT ... ON CONFLICT
        unique_col = None
        if table_name == "users":
            unique_col = "username"
        elif table_name == "business_cards":
            unique_col = "share_token"
        elif table_name == "enterprises":
            unique_col = "credit_code"
        elif table_name == "revoked_tokens":
            unique_col = "jti"

        if unique_col and unique_col in cols:
            # UPSERT
            update_parts = [f'"{c}" = EXCLUDED."{c}"' for c in cols if c != unique_col]
            if update_parts:
                upsert_sql = f"""
                    INSERT INTO "{table_name}" ({", ".join(f'"{c}"' for c in cols)})
                    VALUES ({", ".join(placeholders)})
                    ON CONFLICT ("{unique_col}") DO UPDATE SET
                    {", ".join(update_parts)}
                """
                try:
                    pg_conn.execute(text(upsert_sql), values)
                    count += 1
                except Exception as e:
                    logger.warning(f"    UPSERT 失败 ({table_name} id={values.get('id')}): {e}")
                    try:
                        # Fallback: simple INSERT IGNORE
                        insert_sql = f"""
                            INSERT INTO "{table_name}" ({", ".join(f'"{c}"' for c in cols)})
                            VALUES ({", ".join(placeholders)})
                            ON CONFLICT ("{unique_col}") DO NOTHING
                        """
                        pg_conn.execute(text(insert_sql), values)
                        count += 1
                    except Exception as e2:
                        logger.warning(f"    INSERT IGNORE 也失败: {e2}")
            else:
                insert_sql = f"""
                    INSERT INTO "{table_name}" ({", ".join(f'"{c}"' for c in cols)})
                    VALUES ({", ".join(placeholders)})
                    ON CONFLICT DO NOTHING
                """
                try:
                    pg_conn.execute(text(insert_sql), values)
                    count += 1
                except Exception:
                    pass
        else:
            # Simple INSERT
            insert_sql = f"""
                INSERT INTO "{table_name}" ({", ".join(f'"{c}"' for c in cols)})
                VALUES ({", ".join(placeholders)})
            """
            try:
                pg_conn.execute(text(insert_sql), values)
                count += 1
            except Exception as e:
                logger.warning(f"    插入失败 ({table_name} id={values.get('id')}): {e}")
                if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                    # Skip duplicates
                    pass
                else:
                    # Try to find the column issue
                    logger.warning(f"    值: {values}")

    pg_conn.commit()
    logger.info(f"  {table_name}: 迁移 {count}/{len(sqlite_rows)} 行")
    return count


def backfill_organizations(sqlite_conn, pg_conn):
    """为无组织的记录创建默认组织并填充 organization_id"""
    logger.info("=" * 60)
    logger.info("开始回填 organization_id...")
    logger.info("=" * 60)

    # 获取所有用户
    users = sqlite_conn.execute(text('SELECT id, username, name, company FROM "users"')).fetchall()
    logger.info(f"共 {len(users)} 个用户")

    # 为每个用户创建一个组织（如果不存在）
    org_map = {}
    for user in users:
        user_id = user[0]
        username = user[1] or f"user_{user_id}"
        name = user[3] or username
        company = user[4] or f"{name}的组织"

        # 检查用户是否已有组织（通过 PG 中的组织表）
        existing_org = pg_conn.execute(
            text("SELECT id FROM organizations WHERE owner_id = :uid"), {"uid": user_id}
        ).fetchone()

        if existing_org:
            org_map[user_id] = existing_org[0]
        else:
            slug = f"org_{username}_{uuid.uuid4().hex[:8]}"
            try:
                result = pg_conn.execute(
                    text("""
                        INSERT INTO organizations (name, slug, owner_id, created_at)
                        VALUES (:name, :slug, :owner_id, :created_at)
                        RETURNING id
                    """),
                    {
                        "name": company or f"{name}的默认组织",
                        "slug": slug,
                        "owner_id": user_id,
                        "created_at": datetime.utcnow(),
                    },
                )
                org_id = result.fetchone()[0]
                org_map[user_id] = org_id
                logger.info(f"  为用户 {username}(id={user_id}) 创建组织 id={org_id}")

                # 也创建成员关联
                pg_conn.execute(
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
            except Exception as e:
                logger.warning(f"  为用户 {user_id} 创建组织失败: {e}")

    pg_conn.commit()
    logger.info(f"组织创建完成，共 {len(org_map)} 个映射")

    # 回填所有表的 organization_id
    for table_name in TABLES_WITH_ORG_ID:
        try:
            # 检查表是否存在
            pg_insp = inspect(pg_conn)
            if table_name not in pg_insp.get_table_names():
                logger.warning(f"  表 {table_name} 不存在，跳过")
                continue

            columns = [col["name"] for col in pg_insp.get_columns(table_name)]
            if "organization_id" not in columns:
                logger.warning(f"  表 {table_name} 无 organization_id 列，跳过")
                continue

            # 检查是否有 user_id 或 owner_id 列
            user_ref_col = None
            if "user_id" in columns:
                user_ref_col = "user_id"
            elif "owner_id" in columns:
                user_ref_col = "owner_id"
            else:
                # 没有用户引用列，尝试使用默认组织
                logger.warning(f"  表 {table_name} 无 user_id/owner_id 列，跳过回填")
                continue

            null_rows = pg_conn.execute(
                text(f'SELECT id, "{user_ref_col}" FROM "{table_name}" WHERE organization_id IS NULL')
            ).fetchall()

            if not null_rows:
                logger.info(f"  {table_name}: 所有记录已有 organization_id")
                continue

            logger.info(f"  {table_name}: 回填 {len(null_rows)} 条记录")
            for row in null_rows:
                row_id = row[0]
                ref_user_id = row[1]
                if ref_user_id and ref_user_id in org_map:
                    pg_conn.execute(
                        text(f'UPDATE "{table_name}" SET organization_id = :org_id WHERE id = :id'),
                        {"org_id": org_map[ref_user_id], "id": row_id},
                    )
                elif ref_user_id:
                    # 用户没有组织，尝试用第一个组织
                    first_org = pg_conn.execute(text("SELECT id FROM organizations LIMIT 1")).fetchone()
                    if first_org:
                        pg_conn.execute(
                            text(f'UPDATE "{table_name}" SET organization_id = :org_id WHERE id = :id'),
                            {"org_id": first_org[0], "id": row_id},
                        )

            pg_conn.commit()
        except Exception as e:
            logger.warning(f"  回填 {table_name} 失败: {e}")

    logger.info("organization_id 回填完成！")


def main():
    logger.info("=" * 60)
    logger.info("链客宝 SQLite → PostgreSQL 迁移脚本")
    logger.info("=" * 60)
    logger.info(f"SQLite: {SQLITE_PATH}")
    logger.info(f"PostgreSQL: {PG_URL.replace(PG_PASSWORD, '****')}")

    # 连接 SQLite
    sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}")
    sqlite_conn = sqlite_engine.connect()
    sqlite_tables = get_sqlite_tables(sqlite_conn)
    logger.info(f"SQLite 表数: {len(sqlite_tables)}")

    # 连接 PostgreSQL
    pg_engine = create_engine(PG_URL)
    pg_conn = pg_engine.connect()
    pg_insp = inspect(pg_engine)
    pg_tables = get_pg_tables(pg_insp)
    logger.info(f"PostgreSQL 表数: {len(pg_tables)}")

    # Step 1: 创建 PG 中缺失的表
    logger.info("\n" + "=" * 60)
    logger.info("Step 1: 创建缺失的表")
    logger.info("=" * 60)
    create_missing_tables(pg_conn)

    # Step 2: 为 PG 表添加 organization_id 列
    logger.info("\n" + "=" * 60)
    logger.info("Step 2: 添加 organization_id 列")
    logger.info("=" * 60)
    for table_name in list(set(sqlite_tables + pg_tables)):
        try:
            add_org_id_column_if_missing(pg_conn, table_name)
        except Exception as e:
            logger.warning(f"  无法处理 {table_name}: {e}")

    # Step 3: 迁移数据（SQLite → PG）
    logger.info("\n" + "=" * 60)
    logger.info("Step 3: 迁移数据")
    logger.info("=" * 60)
    total_rows = 0
    for table_name in sqlite_tables:
        try:
            rows = migrate_table(sqlite_conn, pg_conn, table_name)
            total_rows += rows
        except Exception as e:
            logger.warning(f"  迁移 {table_name} 失败: {e}")
            import traceback

            traceback.print_exc()

    logger.info(f"\n共迁移 {total_rows} 行数据")

    # Step 4: 回填 organization_id
    logger.info("\n" + "=" * 60)
    logger.info("Step 4: 回填 organization_id")
    logger.info("=" * 60)
    backfill_organizations(sqlite_conn, pg_conn)

    # 清理
    sqlite_conn.close()
    pg_conn.close()
    sqlite_engine.dispose()
    pg_engine.dispose()

    logger.info("\n" + "=" * 60)
    logger.info("迁移完成！")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
