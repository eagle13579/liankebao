"""
数据迁移脚本：从 SQLite 迁移到 PostgreSQL

用法:
    # 1. 设置 PostgreSQL 环境变量
    export DB_TYPE=postgres
    export PG_HOST=localhost
    export PG_PORT=5432
    export PG_USER=liankebao
    export PG_PASSWORD=your_password
    export PG_DATABASE=liankebao

    # 2. 执行迁移
    python data_migration.py

    # 3. 验证一致性
    python data_migration.py --verify

选项:
    --sqlite-path PATH    指定 SQLite 数据库路径（默认: ../data/chainke.db）
    --verify              仅验证数据一致性，不执行迁移
    --truncate            迁移前清空目标 PostgreSQL 表
    --dry-run             预览迁移内容，不实际写入
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("data_migration")

# ============================================================
# 检查 PostgreSQL 驱动
# ============================================================
try:
    import psycopg2
    from psycopg2.extras import execute_values

    PG_DRIVER_AVAILABLE = True
except ImportError:
    PG_DRIVER_AVAILABLE = False
    logger.error("未安装 psycopg2 驱动。请执行: pip install psycopg2-binary")
    sys.exit(1)


def get_sqlite_engine(sqlite_path: str):
    """创建 SQLite 引擎"""
    from sqlalchemy import create_engine

    url = f"sqlite:///{sqlite_path}"
    engine = create_engine(url, echo=False)
    return engine


def get_pg_connection():
    """创建 PostgreSQL 连接"""
    pg_host = os.environ.get("PG_HOST", "localhost")
    pg_port = os.environ.get("PG_PORT", "5432")
    pg_user = os.environ.get("PG_USER", "")
    pg_password = os.environ.get("PG_PASSWORD", "")
    pg_db = os.environ.get("PG_DATABASE", "")

    if not all([pg_user, pg_password, pg_db]):
        logger.error("请设置 PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE 环境变量")
        sys.exit(1)

    conn = psycopg2.connect(
        host=pg_host,
        port=pg_port,
        user=pg_user,
        password=pg_password,
        dbname=pg_db,
    )
    conn.autocommit = False
    return conn


def export_from_sqlite(sqlite_path: str) -> dict:
    """从 SQLite 导出所有数据"""
    engine = get_sqlite_engine(sqlite_path)
    conn = engine.connect()

    tables = ["users", "products", "orders", "withdrawals"]
    data = {}

    try:
        for table in tables:
            try:
                result = conn.execute(f"SELECT * FROM {table}")  # nosec — table 来自硬编码白名单
                columns = list(result.keys())
                rows = []
                for row in result.fetchall():
                    record = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if isinstance(val, datetime):
                            val = val.isoformat()
                        record[col] = val
                    rows.append(record)
                data[table] = rows
                logger.info(f"  导出 {table}: {len(rows)} 条记录")
            except Exception as e:
                logger.warning(f"  跳过 {table}: {e}")
                data[table] = []

        data["export_time"] = datetime.utcnow().isoformat()
        return data
    finally:
        conn.close()
        engine.dispose()


def create_pg_tables(cur):
    """在 PostgreSQL 中创建表结构"""
    ddl_statements = [
        # 用户表
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
            version BIGINT NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            organization_id INTEGER REFERENCES organizations(id)
        );
        """,
        # 产品表
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
            sort_order INTEGER DEFAULT 0,
            version BIGINT NOT NULL DEFAULT 1,
            deleted_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            organization_id INTEGER REFERENCES organizations(id)
        );
        """,
        # 订单表
        """
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL DEFAULT 1,
            total_price DOUBLE PRECISION NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            promoter_id INTEGER REFERENCES users(id),
            commission DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            payment_platform VARCHAR(10),
            wx_transaction_id VARCHAR(100),
            transaction_id VARCHAR(100),
            prepay_id VARCHAR(100),
            payment_time TIMESTAMP,
            refund_id VARCHAR(100),
            refund_time TIMESTAMP,
            pay_time TIMESTAMP,
            version BIGINT NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            organization_id INTEGER REFERENCES organizations(id)
        );
        """,
        # 提现表
        """
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount DOUBLE PRECISION NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            bank_info TEXT,
            version BIGINT NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            organization_id INTEGER REFERENCES organizations(id)
        );
        """,
        # 组织表
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            slug VARCHAR(100) NOT NULL UNIQUE,
            plan VARCHAR(50) NOT NULL DEFAULT 'free',
            settings JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # 成员关系表
        """
        CREATE TABLE IF NOT EXISTS memberships (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            org_id INTEGER NOT NULL REFERENCES organizations(id),
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # 索引
        "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);",
        "CREATE INDEX IF NOT EXISTS idx_products_org ON products(organization_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_org ON orders(organization_id);",
        "CREATE INDEX IF NOT EXISTS idx_withdrawals_org ON withdrawals(organization_id);",
    ]

    for ddl in ddl_statements:
        try:
            cur.execute(ddl)
        except Exception as e:
            logger.warning(f"DDL 执行警告: {e}")


def import_to_postgres(data: dict, truncate_first: bool = False) -> dict:
    """将数据导入 PostgreSQL"""
    conn = get_pg_connection()
    cur = conn.cursor()
    stats = {}

    table_order = ["users", "products", "orders", "withdrawals"]

    try:
        # 1. 创建表
        create_pg_tables(cur)
        conn.commit()

        # 2. 可选：清空
        if truncate_first:
            for table in reversed(table_order):
                try:
                    cur.execute(f"TRUNCATE TABLE {table} CASCADE;")  # nosec — table 来自硬编码白名单
                except Exception as e:
                    logger.warning(f"  清空 {table} 失败: {e}")
            conn.commit()

        # 3. 导入数据
        for table in table_order:
            records = data.get(table, [])
            if not records:
                stats[table] = 0
                logger.info(f"  导入 {table}: 0 条")
                continue

            # 从记录中提取列（排除可能不存在的 column）
            columns = list(records[0].keys())
            # 确保 organization_id 不在导入列中（因为我们还没有创建默认组织）
            # 实际上我们将在导入后设置 organization_id
            valid_columns = [c for c in columns if c not in ("organization_id",) and c in records[0]]

            col_names = ", ".join(valid_columns)
            placeholders = ", ".join([f"%({c})s" for c in valid_columns])
            insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

            batch_size = 100
            inserted = 0
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                try:
                    cur.executemany(insert_sql, batch)
                    inserted += len(batch)
                except Exception as e:
                    logger.warning(f"  批量插入失败，尝试逐条: {e}")
                    for rec in batch:
                        try:
                            cur.execute(insert_sql, rec)
                            inserted += 1
                        except Exception as e2:
                            logger.error(f"    跳过 {table}.id={rec.get('id', '?')}: {e2}")

            stats[table] = inserted
            logger.info(f"  导入 {table}: {inserted}/{len(records)} 条")

        # 4. 创建默认组织并关联
        cur.execute("SELECT COUNT(*) FROM organizations")
        org_count = cur.fetchone()[0]
        if org_count == 0:
            cur.execute(
                """
                INSERT INTO organizations (name, slug, plan, settings)
                VALUES (%s, %s, %s, %s)
            """,
                (
                    "链客宝AI科技有限公司",
                    "liankebao",
                    "enterprise",
                    json.dumps({"display_name": "链客宝AI", "timezone": "Asia/Shanghai"}),
                ),
            )
            conn.commit()

            # 获取新创建的 org_id
            cur.execute("SELECT id FROM organizations WHERE slug = 'liankebao'")
            org_id = cur.fetchone()[0]

            # 关联所有用户到默认组织
            cur.execute("SELECT id, role FROM users")
            for user_row in cur.fetchall():
                uid, role = user_row
                membership_role = "admin" if role == "admin" else "member"
                cur.execute(
                    "INSERT INTO memberships (user_id, org_id, role) VALUES (%s, %s, %s)",
                    (uid, org_id, membership_role),
                )
                cur.execute(
                    "UPDATE users SET organization_id = %s WHERE id = %s",
                    (org_id, uid),
                )

            # 更新所有业务表
            for table in [
                "products",
                "orders",
                "withdrawals",
                "contacts",
                "activities",
                "import_history",
                "business_needs",
            ]:
                try:
                    cur.execute(f"UPDATE {table} SET organization_id = %s WHERE organization_id IS NULL", (org_id,))
                except Exception:
                    pass

            conn.commit()
            logger.info(f"创建默认组织并关联所有用户 (org_id={org_id})")

        return stats

    except Exception as e:
        conn.rollback()
        logger.error(f"导入失败: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def verify_consistency(sqlite_path: str) -> dict:
    """验证 SQLite 和 PostgreSQL 之间的数据一致性"""
    engine = get_sqlite_engine(sqlite_path)
    sqlite_conn = engine.connect()

    pg_conn = get_pg_connection()
    pg_cur = pg_conn.cursor()

    tables = ["users", "products", "orders", "withdrawals"]
    result = {}

    try:
        for table in tables:
            try:
                # SQLite count
                sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").scalar()

                # PostgreSQL count
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
                logger.info(f"  {table}: SQLite={sqlite_count} PG={pg_count} {'✓' if match else '✗'}")
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
        engine.dispose()
        pg_cur.close()
        pg_conn.close()


def main():
    parser = argparse.ArgumentParser(description="从 SQLite 迁移数据到 PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help="SQLite 数据库路径（默认: ../data/chainke.db）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="仅验证数据一致性，不执行迁移",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="迁移前清空目标 PostgreSQL 表",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览迁移内容，不实际写入",
    )
    args = parser.parse_args()

    # 确定 SQLite 路径
    if args.sqlite_path:
        sqlite_path = args.sqlite_path
    else:
        base_dir = os.path.join(os.path.dirname(__file__), "data")
        sqlite_path = os.path.join(base_dir, "chainke.db")

    if not os.path.exists(sqlite_path):
        logger.error(f"SQLite 数据库不存在: {sqlite_path}")
        sys.exit(1)

    if args.verify:
        logger.info("=" * 50)
        logger.info("验证数据一致性")
        logger.info("=" * 50)
        result = verify_consistency(sqlite_path)
        all_match = all(v.get("match", False) for v in result.values())
        if all_match:
            logger.info("所有表数据一致 ✓")
        else:
            logger.warning("部分表数据不一致:")
            for table, info in result.items():
                if not info.get("match", False):
                    logger.warning(f"  {table}: {info['detail']}")
        return

    # 导出
    logger.info("=" * 50)
    logger.info("第1步: 从 SQLite 导出数据")
    logger.info("=" * 50)
    data = export_from_sqlite(sqlite_path)

    total_records = sum(len(v) for k, v in data.items() if isinstance(v, list))
    logger.info(f"\n共导出 {total_records} 条记录")

    if args.dry_run:
        logger.info("\n预览完成（--dry-run 模式，未写入 PostgreSQL）")
        for table, records in data.items():
            if isinstance(records, list):
                logger.info(f"  {table}: {len(records)} 条")
        return

    # 导入
    logger.info("\n" + "=" * 50)
    logger.info("第2步: 导入到 PostgreSQL")
    logger.info("=" * 50)
    stats = import_to_postgres(data, truncate_first=args.truncate)

    logger.info("\n迁移完成!")
    logger.info(f"  用户: {stats.get('users', 0)}")
    logger.info(f"  产品: {stats.get('products', 0)}")
    logger.info(f"  订单: {stats.get('orders', 0)}")
    logger.info(f"  提现: {stats.get('withdrawals', 0)}")

    # 验证
    logger.info("\n" + "=" * 50)
    logger.info("第3步: 验证数据一致性")
    logger.info("=" * 50)
    verify_result = verify_consistency(sqlite_path)
    all_match = all(v.get("match", False) for v in verify_result.values())
    if all_match:
        logger.info("✓ 所有表数据一致，迁移成功!")
    else:
        logger.warning("⚠ 部分表数据不一致，请检查:")
        for table, info in verify_result.items():
            if not info.get("match", False):
                logger.warning(f"  {table}: {info['detail']}")


if __name__ == "__main__":
    main()
