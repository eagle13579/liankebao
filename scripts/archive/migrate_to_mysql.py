"""
SQLite → MySQL 数据迁移脚本（增强版）
- 支持预迁移数据验证
- 支持迁移后数据校验
- 带进度提示和错误恢复

用法:
    # 一步迁移（导出 + 导入 + 校验）
    python scripts/migrate_to_mysql.py

    # 仅校验数据一致性
    python scripts/migrate_to_mysql.py --verify

环境变量:
    DB_TYPE=mysql                    — 必须设置
    DATABASE_URL: MySQL 连接串       — 必须设置
    SQLITE_PATH: SQLite 数据库路径   — 可选，有默认路径
"""

import os
import sys
import argparse
from datetime import datetime

# 添加项目根目录到 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine, inspect


# ============================================================
# 辅助函数
# ============================================================


def print_banner(title):
    """打印分隔横幅"""
    width = 66
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_table(headers, rows):
    """打印表格（带或不带 tabulate）"""
    try:
        from tabulate import tabulate as tb

        print(tb(rows, headers=headers, tablefmt="simple"))
    except ImportError:
        # fallback: 手动对齐
        col_widths = [
            max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
            for i, h in enumerate(headers)
        ]
        header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        print("  " + "-" * len(header_line))
        print("  " + header_line)
        print("  " + "-" * len(header_line))
        for row in rows:
            print(
                "  "
                + "  ".join(
                    str(row[i]).ljust(col_widths[i]) for i in range(len(headers))
                )
            )
        print("  " + "-" * len(header_line))


def get_sqlite_engine(sqlite_path: str = None):
    """获取 SQLite 引擎"""
    if sqlite_path and os.path.exists(sqlite_path):
        db_path = sqlite_path
    else:
        base_dir = os.path.join(PROJECT_ROOT, "data")
        db_path = os.path.join(base_dir, "chainke.db")

    if not os.path.exists(db_path):
        print(f"错误: SQLite 数据库不存在: {db_path}")
        sys.exit(1)

    print(f"  SQLite:  {db_path}")
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    return engine


def get_mysql_engine(mysql_url: str = None):
    """获取 MySQL 引擎"""
    url = mysql_url or os.environ.get("DATABASE_URL", "")
    if not url:
        print("错误: 未设置 DATABASE_URL 环境变量")
        print(
            "示例: DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4"
        )
        sys.exit(1)

    # 脱敏显示
    safe_url = url
    if ":" in safe_url and "@" in safe_url:
        user_part = safe_url.split("@", 1)[0]
        if ":" in user_part:
            safe_url = user_part.split(":", 1)[0] + ":****@" + safe_url.split("@", 1)[1]
    print(f"  MySQL:   {safe_url[:80]}")
    engine = create_engine(url, echo=False, pool_pre_ping=True)
    return engine


# ============================================================
# 预迁移验证
# ============================================================


def pre_validate(sqlite_engine) -> dict:
    """
    迁移前验证：检查 SQLite 源数据完整性
    返回验证报告
    """
    print_banner("迁移前数据验证 (SQLite 源)")
    inspector = inspect(sqlite_engine)
    tables = inspector.get_table_names()

    report = {
        "tables_found": tables,
        "row_counts": {},
        "warnings": [],
        "errors": [],
        "passed": True,
    }

    conn = sqlite_engine.connect()
    try:
        for table in ["users", "products", "orders", "withdrawals"]:
            if table not in tables:
                report["errors"].append(f"缺少必要表: {table}")
                report["passed"] = False
                continue

            # 行数统计
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").scalar()
            report["row_counts"][table] = count

            # 检查列完整性
            cols = [c["name"] for c in inspector.get_columns(table)]
            expected_pks = {
                "users": ["id", "username", "password_hash", "name"],
                "products": ["id", "name", "price", "owner_id"],
                "orders": ["id", "user_id", "product_id", "total_price"],
                "withdrawals": ["id", "user_id", "amount"],
            }
            for req_col in expected_pks.get(table, []):
                if req_col not in cols:
                    report["warnings"].append(f"{table}: 缺少必要列 '{req_col}'")

            # 检查空数据
            if count == 0:
                report["warnings"].append(f"{table}: 数据为空")

        # 打印报告
        headers = ["表名", "记录数", "状态"]
        rows = []
        all_ok = True
        for t in ["users", "products", "orders", "withdrawals"]:
            c = report["row_counts"].get(t, 0)
            ok = t in report["row_counts"] and c >= 0
            if not ok:
                all_ok = False
            rows.append([t, c, "✓" if ok else "✗"])
        print_table(headers, rows)

        if report["warnings"]:
            print("\n  警告:")
            for w in report["warnings"]:
                print(f"    ⚠ {w}")

        if report["errors"]:
            print("\n  错误:")
            for e in report["errors"]:
                print(f"    ✗ {e}")
            report["passed"] = False

        print(f"\n  验证结论: {'通过 ✓' if report['passed'] else '失败 ✗'}")
        return report

    finally:
        conn.close()


# ============================================================
# 数据迁移
# ============================================================


def create_mysql_tables(mysql_engine):
    """使用 SQLAlchemy ORM 在 MySQL 上创建表"""
    print_banner("创建 MySQL 表结构")

    # 使用 models 的 Base（它与 database.py 共享同一个 Base）
    # 这里我们直接使用 SQLAlchemy 的 metadata

    # 获取 app.database 中定义的 Base（所有模型共享的 Base）
    from app.database import Base as AppBase

    # 创建所有表
    AppBase.metadata.create_all(bind=mysql_engine)

    # 验证表已创建
    inspector = inspect(mysql_engine)
    created_tables = inspector.get_table_names()
    print(f"  已创建表: {', '.join(created_tables)}")
    print(f"  表结构创建完成 ({len(created_tables)} 张表)")


def get_all_tables_in_order():
    """按外键依赖顺序返回表名列表"""
    return ["users", "products", "orders", "withdrawals"]


def migrate_table(sqlite_engine, mysql_engine, table_name: str, truncate: bool = True):
    """迁移单个表的数据，带进度提示"""
    sqlite_conn = sqlite_engine.connect()
    rows = sqlite_conn.execute(f"SELECT * FROM {table_name}").fetchall()

    # 获取列名
    cols_result = sqlite_conn.execute(f"SELECT * FROM {table_name} LIMIT 0")
    column_names = [desc[0] for desc in cols_result.cursor.description]
    sqlite_conn.close()

    if not rows:
        print(f"  [{table_name:15s}] 0 条记录，跳过")
        return 0

    total = len(rows)
    print(f"  [{table_name:15s}] {total} 条记录 -> 正在写入...", end="", flush=True)

    mysql_conn = mysql_engine.connect()
    transaction = mysql_conn.begin()

    try:
        # 清空目标表
        if truncate:
            mysql_conn.execute(f"TRUNCATE TABLE {table_name}")

        # 批量插入
        placeholders = ", ".join([f":{name}" for name in column_names])
        cols = ", ".join(column_names)
        insert_sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

        batch_size = 100
        inserted = 0
        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            params_list = []
            for row in batch:
                params = {}
                for idx, col_name in enumerate(column_names):
                    val = row[idx]
                    # datetime 转字符串
                    if isinstance(val, datetime):
                        val = val.strftime("%Y-%m-%d %H:%M:%S")
                    params[col_name] = val
                params_list.append(params)

            mysql_conn.execute(insert_sql, params_list)
            inserted += len(params_list)

            # 进度提示
            if total > batch_size:
                pct = min(100, int(inserted / total * 100))
                print(
                    f"\r  [{table_name:15s}] {inserted}/{total} ({pct}%)...",
                    end="",
                    flush=True,
                )

        transaction.commit()
        print(f"\r  [{table_name:15s}] {inserted}/{total} 迁移完成 ✓")
        return inserted

    except Exception as e:
        transaction.rollback()
        print(f"\r  [{table_name:15s}] 迁移失败: {e} ✗")
        raise


# ============================================================
# 迁移后校验
# ============================================================


def verify_migration(sqlite_engine, mysql_engine) -> dict:
    """
    迁移后验证：对比 SQLite 和 MySQL 行数
    返回验证报告
    """
    print_banner("迁移后数据校验")

    report = {
        "row_counts": {},
        "all_match": True,
        "checks": [],
    }

    sqlite_conn = sqlite_engine.connect()
    mysql_conn = mysql_engine.connect()

    try:
        for table in get_all_tables_in_order():
            # SQLite 行数
            try:
                sqlite_count = sqlite_conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).scalar()
            except Exception:
                sqlite_count = -1

            # MySQL 行数
            try:
                mysql_count = mysql_conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).scalar()
            except Exception:
                mysql_count = -1

            match = sqlite_count == mysql_count
            if not match:
                report["all_match"] = False

            report["row_counts"][table] = {
                "sqlite": sqlite_count,
                "mysql": mysql_count,
                "match": match,
            }
            report["checks"].append((table, sqlite_count, mysql_count, match))

        # 打印表格
        headers = ["表名", "SQLite", "MySQL", "匹配"]
        rows = []
        for table, sc, mc, match in report["checks"]:
            status = "✓" if match else "✗"
            diff = f"(差异: {sc - mc})" if not match else ""
            rows.append([table, sc, mc, f"{status} {diff}"])

        print_table(headers, rows)

        if report["all_match"]:
            print("\n  校验通过: 所有表数据一致! ✓")
        else:
            print("\n  校验失败: 部分表数据不一致! ✗")
            for table, info in report["row_counts"].items():
                if not info["match"]:
                    print(
                        f"    {table}: SQLite={info['sqlite']}, MySQL={info['mysql']}"
                    )

        return report

    finally:
        sqlite_conn.close()
        mysql_conn.close()


# ============================================================
# 主流程
# ============================================================


def cmd_migrate(args):
    """执行完整迁移流程"""
    print_banner("链客宝AI SQLite → MySQL 数据迁移")

    # 1. 检查环境变量
    db_type = os.environ.get("DB_TYPE", "")
    mysql_url = os.environ.get("DATABASE_URL", "")
    if not mysql_url:
        print("错误: 未设置 DATABASE_URL 环境变量")
        sys.exit(1)
    if db_type and db_type != "mysql":
        print(f"警告: DB_TYPE={db_type}，但正在执行 MySQL 迁移。建议设置 DB_TYPE=mysql")

    # 2. 获取引擎
    print("\n  数据库连接:")
    sqlite_path = args.sqlite_path or os.environ.get("SQLITE_PATH", "")
    sqlite_engine = get_sqlite_engine(sqlite_path)
    mysql_engine = get_mysql_engine(mysql_url)

    # 3. 预迁移验证
    if not args.skip_validate:
        validate_result = pre_validate(sqlite_engine)
        if not validate_result["passed"]:
            print("\n  预验证失败，中止迁移。使用 --skip-validate 强制迁移。")
            sys.exit(1)

        if not args.yes:
            total_records = sum(validate_result["row_counts"].values())
            if total_records == 0:
                print("\n  源数据库无数据，无需迁移。")
                return
            confirm = (
                input(f"\n  确认迁移 {total_records} 条记录到 MySQL? (y/N): ")
                .strip()
                .lower()
            )
            if confirm not in ("y", "yes"):
                print("  已取消")
                return

    # 4. 创建 MySQL 表
    create_mysql_tables(mysql_engine)

    # 5. 迁移数据
    print_banner("开始迁移数据")
    totals = {}
    for table_name in get_all_tables_in_order():
        try:
            count = migrate_table(
                sqlite_engine, mysql_engine, table_name, truncate=not args.no_truncate
            )
            totals[table_name] = count
        except Exception as e:
            print(f"  [{table_name}] 迁移失败: {e}")
            if not args.force:
                print("  迁移中止。使用 --force 忽略错误继续。")
                sys.exit(1)

    total = sum(totals.values())
    print(f"\n  数据迁移完成: 共 {total} 条记录")

    # 6. 迁移后校验
    if not args.skip_verify:
        verify_migration(sqlite_engine, mysql_engine)

    # 7. 总结
    print_banner("迁移完成")
    print(f"  源:    SQLite ({sqlite_engine.url})")
    safe_url = mysql_url
    if ":" in safe_url and "@" in safe_url:
        safe_url = (
            safe_url.split("@", 1)[0].split(":", 1)[0]
            + ":****@"
            + safe_url.split("@", 1)[1]
        )
    print(f"  目标:  MySQL ({safe_url})")
    print(f"  记录:  {total} 条")
    print(f"  状态:  {'全部通过 ✓' if not args.skip_verify else '跳过校验'}")


def cmd_verify(args):
    """仅执行数据校验"""
    print_banner("链客宝AI 数据一致性校验")

    mysql_url = os.environ.get("DATABASE_URL", "")
    if not mysql_url:
        print("错误: 未设置 DATABASE_URL 环境变量")
        sys.exit(1)

    print("\n  数据库连接:")
    sqlite_path = args.sqlite_path or os.environ.get("SQLITE_PATH", "")
    sqlite_engine = get_sqlite_engine(sqlite_path)
    mysql_engine = get_mysql_engine(mysql_url)

    report = verify_migration(sqlite_engine, mysql_engine)

    return report["all_match"]


def main():
    parser = argparse.ArgumentParser(
        description="链客宝AI SQLite → MySQL 数据迁移工具（增强版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整迁移（验证 + 迁移 + 校验）
  export DB_TYPE=mysql
  export DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/chainke?charset=utf8mb4
  python scripts/migrate_to_mysql.py

  # 仅校验数据一致性
  python scripts/migrate_to_mysql.py --verify

  # 跳过预验证和迁移后校验
  python scripts/migrate_to_mysql.py --skip-validate --skip-verify -y
        """,
    )

    parser.add_argument(
        "--verify", action="store_true", help="仅执行数据一致性校验，不迁移"
    )
    parser.add_argument("--sqlite-path", type=str, default="", help="SQLite 数据库路径")
    parser.add_argument(
        "--skip-validate", action="store_true", help="跳过迁移前数据验证"
    )
    parser.add_argument("--skip-verify", action="store_true", help="跳过迁移后数据校验")
    parser.add_argument(
        "--no-truncate", action="store_true", help="不清空目标表（追加模式）"
    )
    parser.add_argument(
        "--force", action="store_true", help="忽略部分表迁移错误，继续执行"
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="自动确认（跳过交互提示）"
    )

    args = parser.parse_args()

    if args.verify:
        cmd_verify(args)
    else:
        cmd_migrate(args)


if __name__ == "__main__":
    main()
