"""
SQLite → PostgreSQL 数据迁移 CLI 脚本

用法:
    python scripts/migrate_to_postgres.py --export          # 从 SQLite 导出数据为 JSON
    python scripts/migrate_to_postgres.py --import          # 从 JSON 导入到 PostgreSQL
    python scripts/migrate_to_postgres.py --export --import # 导出并直接导入
    python scripts/migrate_to_postgres.py --verify          # 验证数据一致性

环境变量:
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE  — PostgreSQL 连接
    SQLITE_PATH                                           — SQLite 数据库路径（可选，有默认值）
"""
import os
import sys
import json
import argparse
from datetime import datetime

# 添加项目根目录到 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def check_psycopg2():
    """检查 psycopg2 是否已安装"""
    try:
        import psycopg2  # noqa: F401
        return True
    except ImportError:
        return False


def get_sqlite_path():
    """获取 SQLite 数据库路径"""
    custom_path = os.environ.get("SQLITE_PATH", "")
    if custom_path and os.path.exists(custom_path):
        return custom_path

    default_path = os.path.join(PROJECT_ROOT, "data", "chainke.db")
    if os.path.exists(default_path):
        return default_path

    return default_path  # 即使不存在也返回路径，让调用方处理


def cmd_export(args):
    """--export: 从 SQLite 导出数据为 JSON 文件"""
    from app.database_postgres import export_from_sqlite

    sqlite_path = args.sqlite_path or get_sqlite_path()

    if not os.path.exists(sqlite_path):
        print(f"错误: SQLite 数据库不存在: {sqlite_path}")
        sys.exit(1)

    print("=" * 60)
    print("SQLite → JSON 数据导出")
    print("=" * 60)
    print(f"SQLite 数据库: {sqlite_path}")
    print()

    try:
        data = export_from_sqlite(sqlite_path)

        # 写入 JSON 文件
        output_path = args.output or os.path.join(
            os.path.dirname(sqlite_path), "postgres_migrate_export.json"
        )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        total = sum(len(v) for k, v in data.items() if isinstance(v, list))

        print()
        print(f"导出完成!")
        print(f"  输出文件: {output_path}")
        print(f"  总记录数: {total}")
        print(f"  导出时间: {data.get('export_time', 'N/A')}")
        print("=" * 60)

        return output_path

    except Exception as e:
        print(f"导出失败: {e}")
        sys.exit(1)


def cmd_import(args):
    """--import: 从 JSON 导入到 PostgreSQL"""
    if not check_psycopg2():
        print(
            "错误: psycopg2 未安装。\n"
            "请执行: pip install psycopg2-binary"
        )
        sys.exit(1)

    from app.database_postgres import import_to_postgres

    # 验证 PostgreSQL 环境变量
    required_vars = ["PG_HOST", "PG_USER", "PG_PASSWORD", "PG_DATABASE"]
    missing = [v for v in required_vars if not os.environ.get(v, "")]
    if missing:
        print(
            f"错误: 缺少 PostgreSQL 环境变量: {', '.join(missing)}\n"
            f"请设置后再试。"
        )
        sys.exit(1)

    # 获取 JSON 数据
    if args.input and os.path.exists(args.input):
        json_path = args.input
    else:
        sqlite_path = args.sqlite_path or get_sqlite_path()
        json_path = os.path.join(
            os.path.dirname(sqlite_path), "postgres_migrate_export.json"
        )

    if not os.path.exists(json_path):
        print(
            f"错误: 导入文件不存在: {json_path}\n"
            f"请先执行 --export 导出数据。"
        )
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 60)
    print("JSON → PostgreSQL 数据导入")
    print("=" * 60)
    print(f"数据文件: {json_path}")
    pg_host = os.environ.get("PG_HOST", "")
    pg_port = os.environ.get("PG_PORT", "5432")
    pg_db = os.environ.get("PG_DATABASE", "")
    print(f"PostgreSQL: {pg_host}:{pg_port}/{pg_db}")
    print()

    total_records = sum(len(v) for k, v in data.items() if isinstance(v, list))
    print(f"待导入数据: {total_records} 条记录")
    print()

    # 确认
    if not args.yes:
        confirm = input("确认导入? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("已取消")
            return

    try:
        stats = import_to_postgres(data)

        print()
        print("导入完成!")
        for table, count in stats.items():
            print(f"  {table}: {count} 条")
        print("=" * 60)

    except Exception as e:
        print(f"导入失败: {e}")
        sys.exit(1)


def cmd_verify(args):
    """--verify: 验证 SQLite 和 PostgreSQL 数据一致性"""
    if not check_psycopg2():
        print(
            "错误: psycopg2 未安装。\n"
            "请执行: pip install psycopg2-binary"
        )
        sys.exit(1)

    from app.database_postgres import verify_data_consistency

    required_vars = ["PG_HOST", "PG_USER", "PG_PASSWORD", "PG_DATABASE"]
    missing = [v for v in required_vars if not os.environ.get(v, "")]
    if missing:
        print(
            f"错误: 缺少 PostgreSQL 环境变量: {', '.join(missing)}\n"
            f"请设置后再试。"
        )
        sys.exit(1)

    sqlite_path = args.sqlite_path or get_sqlite_path()
    if not os.path.exists(sqlite_path):
        print(f"错误: SQLite 数据库不存在: {sqlite_path}")
        sys.exit(1)

    print("=" * 60)
    print("数据一致性验证")
    print("=" * 60)
    print(f"SQLite 数据库: {sqlite_path}")
    pg_host = os.environ.get("PG_HOST", "")
    pg_port = os.environ.get("PG_PORT", "5432")
    pg_db = os.environ.get("PG_DATABASE", "")
    print(f"PostgreSQL:    {pg_host}:{pg_port}/{pg_db}")
    print()

    try:
        results = verify_data_consistency(sqlite_path)

        all_match = True
        for table, info in results.items():
            status = "✓ 一致" if info["match"] else "✗ 不一致"
            if not info["match"]:
                all_match = False
            print(
                f"  {table:15s}  SQLite: {info['sqlite']:>5d}  |  "
                f"PostgreSQL: {info['postgres']:>5d}  |  {status}"
            )

        print()
        if all_match:
            print("验证通过: 所有表数据一致! ✓")
        else:
            print("验证失败: 部分表数据不一致! ✗")
        print("=" * 60)

        return all_match

    except Exception as e:
        print(f"验证失败: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="链客宝 SQLite → PostgreSQL 数据迁移工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导出 SQLite 数据
  python scripts/migrate_to_postgres.py --export

  # 导入到 PostgreSQL
  python scripts/migrate_to_postgres.py --import

  # 导出并导入（一步完成）
  python scripts/migrate_to_postgres.py --export --import --yes

  # 验证数据一致性
  python scripts/migrate_to_postgres.py --verify

  # 指定 SQLite 路径和输出文件
  python scripts/migrate_to_postgres.py --export \\
      --sqlite-path /path/to/chainke.db \\
      --output /path/to/export.json
        """,
    )

    parser.add_argument(
        "--export", action="store_true", help="从 SQLite 导出数据为 JSON"
    )
    parser.add_argument(
        "--import", action="store_true", dest="import_",
        help="从 JSON 导入到 PostgreSQL",
    )
    parser.add_argument(
        "--verify", action="store_true", help="验证 SQLite 和 PostgreSQL 数据一致性"
    )
    parser.add_argument(
        "--sqlite-path", type=str, default="",
        help="SQLite 数据库路径（默认: backend/data/chainke.db）",
    )
    parser.add_argument(
        "--output", type=str, default="",
        help="导出 JSON 文件路径（默认: data/postgres_migrate_export.json）",
    )
    parser.add_argument(
        "--input", type=str, default="",
        help="导入 JSON 文件路径（默认: data/postgres_migrate_export.json）",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="自动确认导入（跳过确认提示）",
    )

    args = parser.parse_args()

    # 如果没有指定任何操作，显示帮助
    if not (args.export or args.import_ or args.verify):
        parser.print_help()
        sys.exit(0)

    # 建立统一的 sqlite_path
    if not args.sqlite_path:
        args.sqlite_path = get_sqlite_path()

    # 执行操作
    if args.export:
        json_path = cmd_export(args)
        if args.import_:
            print("\n" + "=" * 60)
            print("继续导入到 PostgreSQL...")
            print("=" * 60 + "\n")
            args.input = json_path
            cmd_import(args)

    elif args.import_:
        cmd_import(args)

    elif args.verify:
        cmd_verify(args)


if __name__ == "__main__":
    main()
