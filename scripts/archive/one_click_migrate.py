"""
链客宝 一键数据库迁移工具
支持: SQLite → MySQL / SQLite → PostgreSQL

用法:
    # MySQL 迁移
    export DB_TYPE=mysql
    export DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4
    python scripts/one_click_migrate.py --to mysql

    # PostgreSQL 迁移
    export DB_TYPE=postgres
    export PG_HOST=localhost
    export PG_PORT=5432
    export PG_USER=user
    export PG_PASSWORD=pass
    export PG_DATABASE=chainke
    python scripts/one_click_migrate.py --to postgres

    # 仅校验
    python scripts/one_click_migrate.py --to mysql --verify-only

    # 不交互确认（自动化 CI/CD）
    python scripts/one_click_migrate.py --to mysql --yes
"""

import os
import sys
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def print_banner(title):
    width = 66
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def check_environment(target: str) -> list:
    """
    检查目标数据库的环境变量是否完整
    返回缺失的环境变量列表
    """
    missing = []

    if target == "mysql":
        if not os.environ.get("DATABASE_URL", ""):
            if not os.environ.get("DB_TYPE", "") == "mysql":
                missing.append("DATABASE_URL (或设置 DB_TYPE=mysql)")
        # 检查 pymysql
        try:
            import pymysql  # noqa: F401
        except ImportError:
            print("错误: pymysql 未安装。请执行: pip install pymysql")
            sys.exit(1)

    elif target == "postgres":
        if not os.environ.get("PG_URL", ""):
            required = ["PG_HOST", "PG_USER", "PG_PASSWORD", "PG_DATABASE"]
            for v in required:
                if not os.environ.get(v, ""):
                    missing.append(v)
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            print("错误: psycopg2 未安装。请执行: pip install psycopg2-binary")
            sys.exit(1)

    return missing


def run_mysql_migration(args) -> bool:
    """执行 MySQL 迁移"""
    from scripts.migrate_to_mysql import (
        get_sqlite_engine,
        get_mysql_engine,
        pre_validate,
        create_mysql_tables,
        migrate_table,
        verify_migration,
        get_all_tables_in_order,
        print_banner,
    )

    sqlite_path = args.sqlite_path or os.environ.get("SQLITE_PATH", "")
    sqlite_engine = get_sqlite_engine(sqlite_path)
    mysql_engine = get_mysql_engine()

    # 第一步：预验证
    print_banner("Step 1/4 - 数据源验证")
    val_result = pre_validate(sqlite_engine)
    if not val_result["passed"]:
        print("  数据源验证失败，中止迁移。")
        return False

    total_records = sum(val_result["row_counts"].values())
    if total_records == 0:
        print("  源数据库无数据，无需迁移。")
        return True

    # 确认
    if not args.yes:
        confirm = input(f"\n  确认迁移 {total_records} 条记录? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("  已取消")
            return False

    # 第二步：创建表
    print_banner("Step 2/4 - 创建目标表结构")
    create_mysql_tables(mysql_engine)

    # 第三步：迁移数据
    print_banner("Step 3/4 - 迁移数据")
    totals = {}
    for table_name in get_all_tables_in_order():
        try:
            count = migrate_table(
                sqlite_engine, mysql_engine, table_name, truncate=True
            )
            totals[table_name] = count
        except Exception as e:
            print(f"  [{table_name}] 迁移失败: {e}")
            return False

    print(f"\n  数据迁移完成: 共 {sum(totals.values())} 条记录")

    # 第四步：校验
    print_banner("Step 4/4 - 数据一致性校验")
    report = verify_migration(sqlite_engine, mysql_engine)

    return report["all_match"]


def run_postgres_migration(args) -> bool:
    """执行 PostgreSQL 迁移"""
    # 检查 psycopg2
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("错误: psycopg2 未安装。请执行: pip install psycopg2-binary")
        return False

    from app.database_postgres import (
        export_from_sqlite,
        import_to_postgres,
        verify_data_consistency,
    )

    sqlite_path = args.sqlite_path or os.environ.get("SQLITE_PATH", "")

    # 第一步：导出
    print_banner("Step 1/4 - 从 SQLite 导出数据")
    if sqlite_path and os.path.exists(sqlite_path):
        pass  # 使用指定路径
    else:
        base_dir = os.path.join(PROJECT_ROOT, "data")
        sqlite_path = os.path.join(base_dir, "chainke.db")

    if not os.path.exists(sqlite_path):
        print(f"错误: SQLite 数据库不存在: {sqlite_path}")
        return False

    print(f"  SQLite 数据库: {sqlite_path}")
    data = export_from_sqlite(sqlite_path)

    total_records = sum(len(v) for k, v in data.items() if isinstance(v, list))
    print(f"  导出完成: {total_records} 条记录")
    print(f"  导出时间: {data.get('export_time', 'N/A')}")

    if total_records == 0:
        print("  源数据库无数据，无需迁移。")
        return True

    # 第二步：预验证（确认源数据完整性）
    print_banner("Step 2/4 - 数据源验证")
    for table in ["users", "products", "orders", "withdrawals"]:
        count = len(data.get(table, []))
        status = "✓" if count > 0 else "⚠ 空表"
        print(f"    {table:15s} {count} 条  {status}")

    # 确认
    if not args.yes:
        confirm = (
            input(f"\n  确认导入 {total_records} 条记录到 PostgreSQL? (y/N): ")
            .strip()
            .lower()
        )
        if confirm not in ("y", "yes"):
            print("  已取消")
            return False

    # 第三步：导入
    print_banner("Step 3/4 - 导入到 PostgreSQL")
    try:
        stats = import_to_postgres(data)
        print("  导入完成:")
        for table, count in stats.items():
            print(f"    {table}: {count} 条")
    except Exception as e:
        print(f"  导入失败: {e}")
        return False

    # 第四步：校验
    print_banner("Step 4/4 - 数据一致性校验")
    try:
        results = verify_data_consistency(sqlite_path)
        all_match = True
        for table, info in results.items():
            status = "✓" if info["match"] else "✗"
            if not info["match"]:
                all_match = False
            print(
                f"    {table:15s} SQLite: {info['sqlite']:>5d}  |  "
                f"PostgreSQL: {info['postgres']:>5d}  |  {status}  {info['detail']}"
            )
        print()
        if all_match:
            print("  校验通过: 所有表数据一致! ✓")
        else:
            print("  校验失败: 部分表数据不一致! ✗")
        return all_match
    except Exception as e:
        print(f"  校验失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="链客宝 一键数据库迁移工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
环境变量说明:
  MySQL 迁移:
    export DB_TYPE=mysql
    export DATABASE_URL=mysql+pymysql://user:pass@host:3306/db?charset=utf8mb4

  PostgreSQL 迁移:
    export DB_TYPE=postgres
    export PG_HOST=localhost  PG_PORT=5432
    export PG_USER=user  PG_PASSWORD=pass  PG_DATABASE=chainke

  通用:
    export SQLITE_PATH=/path/to/chainke.db  (可选)

示例:
  python scripts/one_click_migrate.py --to mysql -y
  python scripts/one_click_migrate.py --to postgres --verify-only
  python scripts/one_click_migrate.py --to mysql --sqlite-path /data/chainke.db
        """,
    )

    parser.add_argument(
        "--to",
        "-t",
        type=str,
        required=True,
        choices=["mysql", "postgres"],
        help="目标数据库类型: mysql / postgres",
    )
    parser.add_argument(
        "--sqlite-path",
        type=str,
        default="",
        help="SQLite 数据库路径（默认: backend/data/chainke.db）",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="自动确认所有提示（非交互模式）",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="仅执行数据一致性校验，不做迁移",
    )

    args = parser.parse_args()

    # 显示配置
    print_banner(f"链客宝 一键迁移工具 — SQLite → {args.to.upper()}")
    print(f"  目标数据库: {args.to}")
    if args.verify_only:
        print("  模式:       仅校验")
    print(f"  项目路径:   {PROJECT_ROOT}")

    # 检查环境变量
    missing = check_environment(args.to)
    if missing:
        print(f"错误: 缺少必要环境变量: {', '.join(missing)}")
        print("请设置后再试。使用 --help 查看说明。")
        sys.exit(1)

    # 执行
    print()
    if args.to == "mysql":
        if args.verify_only:
            # 仅校验
            from scripts.migrate_to_mysql import cmd_verify

            success = cmd_verify(args)
        else:
            success = run_mysql_migration(args)
    else:
        if args.verify_only:
            # 仅校验 — 调用 postgres 的 verify
            from app.database_postgres import verify_data_consistency

            sqlite_path = args.sqlite_path or os.environ.get("SQLITE_PATH", "")
            if not sqlite_path or not os.path.exists(sqlite_path):
                base_dir = os.path.join(PROJECT_ROOT, "data")
                sqlite_path = os.path.join(base_dir, "chainke.db")
            print_banner("数据一致性校验")
            results = verify_data_consistency(sqlite_path)
            all_match = True
            for table, info in results.items():
                status = "✓" if info["match"] else "✗"
                if not info["match"]:
                    all_match = False
                print(
                    f"  {table:15s} SQLite: {info['sqlite']:>5d}  |  "
                    f"PostgreSQL: {info['postgres']:>5d}  |  {status}"
                )
            success = all_match
        else:
            success = run_postgres_migration(args)

    # 最终结果
    print()
    if success:
        print_banner("迁移全部完成 ✓")
        print("  所有步骤已成功执行，数据一致性已确认。")
        print("  现在可以将 DB_TYPE 环境变量设置为对应值并重启服务。")
    else:
        print_banner("迁移未完成 ✗")
        print("  请检查上方错误信息并修复后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
