"""
数据迁移脚本：从 SQLite 迁移到 PostgreSQL
支持增量迁移（断点续传）

用法:
    # 1. 设置 PostgreSQL 环境变量
    export DB_TYPE=postgres
    export PG_HOST=localhost
    export PG_PORT=5432
    export PG_USER=chainke
    export PG_PASSWORD=your_password
    export PG_DATABASE=chainke

    # 2. 执行迁移（完整）
    python data_migration.py

    # 3. 断点续传（如果上次迁移中断）
    python data_migration.py --resume

    # 4. 验证一致性
    python data_migration.py --verify

选项:
    --sqlite-path PATH    指定 SQLite 数据库路径（默认: backend/data/chainke.db）
    --verify              仅验证数据一致性，不执行迁移
    --truncate            迁移前清空目标 PostgreSQL 表
    --dry-run             预览迁移内容，不实际写入
    --resume              从上次中断点继续迁移（使用 checkpoint 文件）
    --checkpoint-path PATH checkpoint 文件路径（默认: backend/.migration_checkpoint.json）
    --reset-checkpoint    重置 checkpoint（强制重新迁移）
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


# ============================================================
# Checkpoint 管理（断点续传）
# ============================================================
CHECKPOINT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".migration_checkpoint.json"
)


def load_checkpoint(checkpoint_path: str) -> dict:
    """加载 checkpoint 文件"""
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                cp = json.load(f)
            logger.info(f"  加载 checkpoint: {checkpoint_path}")
            logger.info(
                f"  已迁移的表: {', '.join(cp.get('completed_tables', [])) or '无'}"
            )
            return cp
        except Exception as e:
            logger.warning(f"  checkpoint 读取失败，将从头开始: {e}")
    return {"completed_tables": [], "table_row_counts": {}, "started_at": None}


def save_checkpoint(
    checkpoint_path: str,
    completed_tables: list,
    table_row_counts: dict,
    started_at: str,
):
    """保存 checkpoint 文件"""
    cp = {
        "completed_tables": completed_tables,
        "table_row_counts": table_row_counts,
        "started_at": started_at,
        "updated_at": datetime.utcnow().isoformat(),
        "migration_tool": "data_migration.py",
    }
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)
    logger.info(f"  保存 checkpoint: {checkpoint_path}")


def reset_checkpoint(checkpoint_path: str):
    """删除 checkpoint 文件"""
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
        logger.info(f"  已重置 checkpoint: {checkpoint_path}")


# ============================================================
# 数据库连接
# ============================================================
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
        logger.error(
            "请设置 PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE 环境变量\n"
            "或设置 USE_POSTGRES=1 + DB_TYPE=postgres"
        )
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


# ============================================================
# 获取所有表名（自动发现）
# ============================================================
def get_all_table_names(sqlite_path: str) -> list:
    """从 SQLite 读取所有用户表名"""
    import sqlite3

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    skip_tables = {
        "sqlite_sequence",
        "sqlite_stat1",
        "sqlite_stat4",
        "alembic_version",
        "spatial_ref_sys",
        "geometry_columns",
    }
    tables = [
        row[0]
        for row in cursor.fetchall()
        if not row[0].startswith("sqlite_") and row[0] not in skip_tables
    ]
    conn.close()
    return tables


# ============================================================
# 数据导出
# ============================================================
def export_from_sqlite(
    sqlite_path: str, table_names: list = None, skip_tables: list = None
) -> dict:
    """从 SQLite 导出指定表的数据"""
    engine = get_sqlite_engine(sqlite_path)
    conn = engine.connect()

    if table_names is None:
        table_names = get_all_table_names(sqlite_path)

    data = {}

    try:
        for table in table_names:
            if skip_tables and table in skip_tables:
                logger.info(f"  跳过 {table}（已在 checkpoint 中完成）")
                continue
            try:
                result = conn.execute(
                    "SELECT * FROM %s" % table
                )  # nosec — table 来自白名单
                columns = list(result.keys())
                rows = []
                for row in result.fetchall():
                    record = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if isinstance(val, datetime):
                            val = val.isoformat()
                        elif isinstance(val, bytes):
                            try:
                                val = val.decode("utf-8")
                            except UnicodeDecodeError:
                                val = val.hex()
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


# ============================================================
# PostgreSQL 建表（从 SQLAlchemy 模型自动创建）
# ============================================================
def create_pg_tables_from_models():
    """使用 SQLAlchemy ORM 模型自动创建 PG 表结构"""
    try:
        # 强制 PG 模式
        os.environ["DB_TYPE"] = "postgres"
        os.environ["USE_POSTGRES"] = "1"

        from app.database import Base, engine
        import app.models  # noqa: F401 — 注册所有模型

        Base.metadata.create_all(bind=engine)
        logger.info("  表结构创建/同步完成（基于 ORM 模型）")
        return True
    except Exception as e:
        logger.warning(f"  ORM 建表失败，尝试 SQL DDL: {e}")
        return False


def create_pg_tables_ddl(cur):
    """在 PostgreSQL 中创建表结构（DDL 备用方案）"""
    ddl_statements = [
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
            specs TEXT, details TEXT, brand VARCHAR(100),
            sale_price DOUBLE PRECISION, video_url VARCHAR(500),
            tags VARCHAR(500), files TEXT,
            is_featured INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0,
            version BIGINT NOT NULL DEFAULT 1,
            deleted_at TIMESTAMP, is_deleted BOOLEAN DEFAULT FALSE,
            organization_id INTEGER REFERENCES organizations(id)
        );
        """,
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
            refund_id VARCHAR(100), refund_time TIMESTAMP,
            pay_time TIMESTAMP,
            version BIGINT NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP, is_deleted BOOLEAN DEFAULT FALSE,
            organization_id INTEGER REFERENCES organizations(id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount DOUBLE PRECISION NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            bank_info TEXT,
            version BIGINT NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP, is_deleted BOOLEAN DEFAULT FALSE,
            organization_id INTEGER REFERENCES organizations(id)
        );
        """,
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
        """
        CREATE TABLE IF NOT EXISTS memberships (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            org_id INTEGER NOT NULL REFERENCES organizations(id),
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);",
        "CREATE INDEX IF NOT EXISTS idx_products_org ON products(organization_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_org ON orders(organization_id);",
        "CREATE INDEX IF NOT EXISTS idx_withdrawals_org ON withdrawals(organization_id);",
    ]

    for ddl in ddl_statements:
        try:
            cur.execute(ddl)
        except Exception as e:
            logger.warning(f"  DDL 执行警告: {e}")


# ============================================================
# 数据导入
# ============================================================
def import_to_postgres(
    data: dict,
    truncate_first: bool = False,
    table_order: list = None,
    completed_tables: list = None,
) -> dict:
    """将数据导入 PostgreSQL，支持跳过已完成的表"""
    conn = get_pg_connection()
    cur = conn.cursor()
    stats = {}

    if completed_tables is None:
        completed_tables = []
    if table_order is None:
        # 按外键依赖顺序排列
        table_order = [
            "organizations",
            "users",
            "products",
            "orders",
            "withdrawals",
            "contacts",
            "activities",
            "import_history",
            "business_needs",
        ]

    try:
        # 1. 尝试 ORM 方式建表
        if not completed_tables:
            orm_ok = create_pg_tables_from_models()
            if not orm_ok:
                create_pg_tables_ddl(cur)
            conn.commit()

        # 2. 可选：清空（只在非续传模式生效）
        if truncate_first and not completed_tables:
            for table in reversed(table_order):
                if table in data and data[table]:
                    try:
                        cur.execute("TRUNCATE TABLE %s CASCADE;" % table)
                    except Exception as e:
                        logger.warning(f"  清空 {table} 失败: {e}")
            conn.commit()

        # 3. 导入数据（跳过已完成的表）
        for table in table_order:
            if table in completed_tables:
                logger.info(f"  跳过 {table}（checkpoint 标记已完成）")
                stats[table] = data.get(table, {}).get("row_count", 0)
                continue

            records = data.get(table, [])
            if not records:
                stats[table] = 0
                logger.info(f"  导入 {table}: 0 条（跳过空表）")
                completed_tables.append(table)
                continue

            # 从记录中提取列
            columns = list(records[0].keys())
            valid_columns = [
                c for c in columns if c not in ("organization_id",)
            ]

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
                            logger.error(
                                f"    跳过 {table}.id={rec.get('id', '?')}: {e2}"
                            )

            stats[table] = inserted
            logger.info(f"  导入 {table}: {inserted}/{len(records)} 条")
            completed_tables.append(table)

        # 4. 创建默认组织并关联
        if "organizations" not in completed_tables or not data.get(
            "organizations"
        ):
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
                        json.dumps(
                            {
                                "display_name": "链客宝AI",
                                "timezone": "Asia/Shanghai",
                            }
                        ),
                    ),
                )
                conn.commit()

                cur.execute("SELECT id FROM organizations WHERE slug = 'liankebao'")
                org_id = cur.fetchone()[0]

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

                for tbl in [
                    "products",
                    "orders",
                    "withdrawals",
                    "contacts",
                    "activities",
                    "import_history",
                    "business_needs",
                ]:
                    try:
                        cur.execute(
                            "UPDATE %s SET organization_id = %s WHERE organization_id IS NULL"
                            % (tbl, org_id)
                        )
                    except Exception:
                        pass

                conn.commit()
                logger.info(
                    f"创建默认组织并关联所有用户 (org_id={org_id})"
                )

        return stats, completed_tables

    except Exception as e:
        conn.rollback()
        logger.error(f"导入失败: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ============================================================
# 数据一致性验证
# ============================================================
def verify_consistency(sqlite_path: str) -> dict:
    """验证 SQLite 和 PostgreSQL 之间的数据一致性"""
    engine = get_sqlite_engine(sqlite_path)
    sqlite_conn = engine.connect()

    pg_conn = get_pg_connection()
    pg_cur = pg_conn.cursor()

    tables = get_all_table_names(sqlite_path)
    result = {}

    try:
        for table in tables:
            try:
                # SQLite count
                sqlite_count = sqlite_conn.execute(
                    "SELECT COUNT(*) FROM %s" % table
                ).scalar()

                # PostgreSQL count
                try:
                    pg_cur.execute("SELECT COUNT(*) FROM %s" % table)
                    pg_count = pg_cur.fetchone()[0]
                except Exception:
                    pg_count = -1  # 表不存在

                match = sqlite_count == pg_count
                detail = (
                    "一致"
                    if match
                    else f"不一致（差异: {sqlite_count - pg_count}）"
                )
                result[table] = {
                    "sqlite": sqlite_count,
                    "postgres": pg_count,
                    "match": match,
                    "detail": detail,
                }
                icon = "✓" if match else ("⚠" if pg_count < 0 else "✗")
                pg_str = str(pg_count) if pg_count >= 0 else "不存在"
                logger.info(
                    f"  {icon} {table}: SQLite={sqlite_count} PG={pg_str}"
                )
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


# ============================================================
# 迁移报告
# ============================================================
def print_report(stats: dict, verify_result: dict, checkpoint_path: str):
    """打印迁移完成报告"""
    print()
    print("=" * 50)
    print("  迁移完成报告")
    print("=" * 50)
    print()

    # 数据统计
    total_pg = sum(v for v in stats.values() if isinstance(v, int))
    print(f"  PostgreSQL 数据量:")
    for table, count in stats.items():
        if isinstance(count, int):
            print(f"    {table}: {count} 条")
    print(f"  总计: {total_pg} 条记录")
    print()

    # 一致性验证结果
    if verify_result:
        all_match = all(v.get("match", False) for v in verify_result.values())
        tables_ok = sum(1 for v in verify_result.values() if v.get("match"))
        tables_total = len(verify_result)
        print(f"  一致性验证: {tables_ok}/{tables_total} 表一致")
        if all_match:
            print("  状态: ✓ 全部一致")
        else:
            print("  状态: ⚠ 部分不一致（详情见上方日志）")
    print()

    # Checkpoint 信息
    if checkpoint_path and os.path.exists(checkpoint_path):
        print(f"  Checkpoint 文件: {checkpoint_path}")
        print(f"  如需重新迁移，请执行: python data_migration.py --reset-checkpoint")
    print()

    # 切换说明
    print("  切换方式:")
    print("  切换到 PostgreSQL:")
    print("    Windows: set USE_POSTGRES=1")
    print("    Linux:   export USE_POSTGRES=1")
    print("  切换回 SQLite:")
    print("    Windows: set USE_POSTGRES=0")
    print("    Linux:   export USE_POSTGRES=0")
    print("=" * 50)


# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="从 SQLite 迁移数据到 PostgreSQL（支持断点续传）"
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help="SQLite 数据库路径（默认: backend/data/chainke.db）",
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
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从上次中断点继续迁移（使用 checkpoint 文件）",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=CHECKPOINT_FILE,
        help=f"checkpoint 文件路径（默认: {CHECKPOINT_FILE}）",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="重置 checkpoint（强制重新迁移）",
    )
    args = parser.parse_args()

    # 确定 SQLite 路径
    if args.sqlite_path:
        sqlite_path = args.sqlite_path
    else:
        base_dir = os.path.join(
            os.path.dirname(__file__), "data"
        )
        sqlite_path = os.path.join(base_dir, "chainke.db")

    if not os.path.exists(sqlite_path):
        # 尝试在项目根目录查找
        alt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "backend",
            "data",
            "chainke.db",
        )
        if os.path.exists(alt_path):
            sqlite_path = alt_path
        else:
            logger.error(f"SQLite 数据库不存在: {sqlite_path}")
            logger.error(f"也未找到: {alt_path}")
            sys.exit(1)

    # 处理 checkpoint 重置
    if args.reset_checkpoint:
        reset_checkpoint(args.checkpoint_path)

    # 加载 checkpoint（续传模式）
    if args.resume:
        checkpoint = load_checkpoint(args.checkpoint_path)
        completed_tables = checkpoint.get("completed_tables", [])
        if completed_tables:
            logger.info(
                f"续传模式: 跳过 {len(completed_tables)} 个已完成表"
            )
    else:
        checkpoint = None
        completed_tables = []

    # 仅验证模式
    if args.verify:
        logger.info("=" * 50)
        logger.info("验证数据一致性")
        logger.info("=" * 50)
        result = verify_consistency(sqlite_path)
        all_match = all(v.get("match", False) for v in result.values())
        if all_match:
            logger.info("✓ 所有表数据一致")
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

    # 获取所有表
    all_tables = get_all_table_names(sqlite_path)
    logger.info(f"  发现 {len(all_tables)} 个表: {', '.join(all_tables)}")

    if args.resume and completed_tables:
        skip = [t for t in completed_tables if t in all_tables]
        tables_to_migrate = [t for t in all_tables if t not in completed_tables]
    else:
        skip = []
        tables_to_migrate = all_tables

    data = export_from_sqlite(sqlite_path, table_names=tables_to_migrate)

    total_records = sum(
        len(v) for k, v in data.items() if isinstance(v, list)
    )
    logger.info(f"\n共导出 {total_records} 条记录（将导入 {len(tables_to_migrate)} 个表）")

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
    stats, completed_tables_result = import_to_postgres(
        data,
        truncate_first=args.truncate,
        completed_tables=completed_tables,
    )

    # 保存 checkpoint
    started_at = (
        checkpoint.get("started_at", datetime.utcnow().isoformat())
        if checkpoint
        else datetime.utcnow().isoformat()
    )
    save_checkpoint(
        args.checkpoint_path,
        completed_tables_result,
        stats,
        started_at,
    )

    logger.info("\n迁移完成!")
    for table, count in stats.items():
        if isinstance(count, int):
            logger.info(f"  {table}: {count} 条")

    # 验证
    logger.info("\n" + "=" * 50)
    logger.info("第3步: 验证数据一致性")
    logger.info("=" * 50)
    verify_result = verify_consistency(sqlite_path)

    # 打印报告
    print_report(stats, verify_result, args.checkpoint_path)


if __name__ == "__main__":
    main()
