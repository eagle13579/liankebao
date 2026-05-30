#!/usr/bin/env python3
"""
链客宝数据库自动备份脚本

用法:
    python scripts/backup_db.py --type sqlite                  # SQLite 备份
    python scripts/backup_db.py --type postgres                # PostgreSQL 备份
    python scripts/backup_db.py --type sqlite --dry-run        # 试运行(不实际执行)
    python scripts/backup_db.py --type sqlite --retention 14   # 保留14天

Cron 配置 (每天凌晨3点执行 SQLite 备份):
    # crontab -e
    0 3 * * * cd /path/to/链客宝 && /usr/bin/python3 scripts/backup_db.py --type sqlite >> logs/backup_db.log 2>&1

Windows 任务计划程序 (每天凌晨3点执行):
    schtasks /create /tn "链客宝SQLite备份" /tr "python D:\\链客宝\\scripts\\backup_db.py --type sqlite" /sc daily /st 03:00

依赖:
    - Python 标准库 (无第三方依赖)
    - PostgreSQL 模式需要 pg_dump 命令可用

环境变量 (PostgreSQL 模式):
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE
    从项目根 .env 文件自动读取 (如存在)
"""

import argparse
import gzip
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径常量 ────────────────────────────────────────────────────────────────
# 项目根目录 = 脚本所在目录的上一级 (scripts/ -> 链客宝/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# 默认路径
DEFAULT_SQLITE_DB = PROJECT_ROOT / "backend" / "app" / "chainke.db"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backend" / "backups"
DEFAULT_ENV_BACKUP_DIR = DEFAULT_BACKUP_DIR / "env_backup"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="链客宝数据库自动备份工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --type sqlite
  %(prog)s --type sqlite --dry-run
  %(prog)s --type postgres --retention 14
        """,
    )
    parser.add_argument(
        "--type",
        choices=["sqlite", "postgres"],
        required=True,
        help="备份类型: sqlite (复制+gzip) 或 postgres (pg_dump)",
    )
    parser.add_argument(
        "--retention",
        type=int,
        default=7,
        help="备份保留天数 (默认: 7, 超出此天数的将被删除)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式: 仅显示将要执行的操作，不实际备份",
    )
    parser.add_argument(
        "--sqlite-db",
        default=str(DEFAULT_SQLITE_DB),
        help=f"SQLite 数据库路径 (默认: {DEFAULT_SQLITE_DB})",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help=f"备份存放目录 (默认: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help=f".env 文件路径 (默认: {DEFAULT_ENV_FILE})",
    )
    return parser.parse_args()


def load_env_file(env_path: Path) -> dict[str, str]:
    """简易 .env 文件解析，返回 {KEY: VALUE} 字典"""
    env_vars: dict[str, str] = {}
    if not env_path.is_file():
        return env_vars
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    env_vars[key] = value
    except OSError as e:
        print(f"[WARN] 读取 .env 文件失败: {e}", file=sys.stderr)
    return env_vars


def ensure_dir(path: Path, dry_run: bool = False) -> None:
    """确保目录存在"""
    if dry_run:
        if not path.exists():
            print(f"[DRY-RUN] 创建目录: {path}")
        return
    path.mkdir(parents=True, exist_ok=True)
    print(f"[OK] 备份目录就绪: {path}")


def timestamp_str() -> str:
    """返回备份用时间戳: YYYYMMDD_HHMMSS"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def rotate_old_backups(
    backup_dir: Path, pattern: str, retention_days: int, dry_run: bool = False
) -> int:
    """
    删除超过 retention_days 的旧备份文件。
    返回删除的文件数。
    """
    if not backup_dir.is_dir():
        return 0

    cutoff = time.time() - retention_days * 86400
    deleted = 0

    for fpath in sorted(backup_dir.glob(pattern)):
        # 也匹配压缩文件 .db.gz
        if fpath.name.endswith(".db.gz"):
            continue
        if fpath.stat().st_mtime < cutoff:
            if dry_run:
                print(f"[DRY-RUN] 删除过期备份: {fpath.name}")
            else:
                fpath.unlink(missing_ok=True)
                print(f"[DELETE] 删除过期备份: {fpath.name}")
            deleted += 1

    # 同时清理 .db.gz 文件
    for fpath in sorted(backup_dir.glob("*.db.gz")):
        if fpath.stat().st_mtime < cutoff:
            if dry_run:
                print(f"[DRY-RUN] 删除过期备份: {fpath.name}")
            else:
                fpath.unlink(missing_ok=True)
                print(f"[DELETE] 删除过期备份: {fpath.name}")
            deleted += 1

    return deleted


def backup_sqlite(
    db_path: Path,
    backup_dir: Path,
    retention_days: int,
    dry_run: bool = False,
) -> bool:
    """
    SQLite 备份模式:
    1. 直接复制 .db 文件
    2. gzip 压缩
    3. 保留 retention_days 天
    """
    if not db_path.is_file():
        print(f"[ERROR] SQLite 数据库不存在: {db_path}", file=sys.stderr)
        return False

    ts = timestamp_str()
    backup_name = f"chainke_{ts}.db"
    backup_path = backup_dir / backup_name
    gz_path = backup_dir / f"{backup_name}.gz"

    if dry_run:
        print(f"[DRY-RUN] 备份 SQLite: {db_path}")
        print(f"           -> 复制到: {backup_path}")
        print(f"           -> 压缩到: {gz_path}")
        print(f"[DRY-RUN] 保留天数: {retention_days}")
        # 仍然检查旧文件
        rotate_old_backups(backup_dir, "chainke_*.db", retention_days, dry_run=True)
        rotate_old_backups(backup_dir, "chainke_*.db.gz", retention_days, dry_run=True)
        return True

    # 1. 复制数据库文件
    try:
        shutil.copy2(str(db_path), str(backup_path))
        print(f"[OK] 复制数据库: {db_path.name} -> {backup_name}")
    except OSError as e:
        print(f"[ERROR] 复制数据库失败: {e}", file=sys.stderr)
        return False

    # 2. gzip 压缩 (使用最高压缩率)
    try:
        with open(backup_path, "rb") as f_in:
            with gzip.open(gz_path, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        # 删除未压缩的副本
        backup_path.unlink()
        gz_size = gz_path.stat().st_size
        db_size = db_path.stat().st_size
        ratio = (1 - gz_size / db_size) * 100 if db_size > 0 else 0
        print(f"[OK] GZip 压缩完成: {gz_path.name} ({gz_size:,} bytes, 压缩率 {ratio:.1f}%)")
    except OSError as e:
        print(f"[ERROR] GZip 压缩失败: {e}", file=sys.stderr)
        # 保留未压缩版本
        print(f"[WARN] 保留未压缩备份: {backup_path}")
        return False

    # 3. 清理旧备份
    n_deleted = rotate_old_backups(backup_dir, "chainke_*.db", retention_days)
    n_deleted += rotate_old_backups(backup_dir, "chainke_*.db.gz", retention_days)
    if n_deleted > 0:
        print(f"[OK] 清理完成: 删除 {n_deleted} 个过期备份")
    else:
        print(f"[OK] 无过期备份需要清理 (保留期: {retention_days} 天)")

    return True


def backup_postgres(
    backup_dir: Path,
    retention_days: int,
    env_vars: dict[str, str],
    dry_run: bool = False,
) -> bool:
    """
    PostgreSQL 备份模式:
    1. 使用 pg_dump 导出
    2. 输出到 .sql 文件
    3. 保留 retention_days 天
    """
    # 从环境变量或 .env 中读取 PG 配置
    pg_host = os.environ.get("PG_HOST") or env_vars.get("PG_HOST", "")
    pg_port = os.environ.get("PG_PORT") or env_vars.get("PG_PORT", "5432")
    pg_user = os.environ.get("PG_USER") or env_vars.get("PG_USER", "")
    pg_password = os.environ.get("PG_PASSWORD") or env_vars.get("PG_PASSWORD", "")
    pg_database = os.environ.get("PG_DATABASE") or env_vars.get("PG_DATABASE", "chainke")

    if not pg_host:
        print("[ERROR] PostgreSQL 备份需要设置 PG_HOST (环境变量或 .env)", file=sys.stderr)
        return False
    if not pg_user:
        print("[ERROR] PostgreSQL 备份需要设置 PG_USER (环境变量或 .env)", file=sys.stderr)
        return False

    ts = timestamp_str()
    backup_name = f"chainke_pg_{ts}.sql"
    backup_path = backup_dir / backup_name
    gz_path = backup_dir / f"{backup_name}.gz"

    if dry_run:
        print(f"[DRY-RUN] 备份 PostgreSQL 数据库: {pg_database}")
        print(f"           Host: {pg_host}:{pg_port}")
        print(f"           User: {pg_user}")
        print(f"           -> 导出到: {backup_name}")
        print(f"           -> 压缩到: {gz_path.name}")
        print(f"[DRY-RUN] 保留天数: {retention_days}")
        rotate_old_backups(backup_dir, "chainke_pg_*.sql", retention_days, dry_run=True)
        rotate_old_backups(backup_dir, "chainke_pg_*.sql.gz", retention_days, dry_run=True)
        return True

    # 1. pg_dump
    env = os.environ.copy()
    if pg_password:
        env["PGPASSWORD"] = pg_password

    pg_dump_cmd = [
        "pg_dump",
        "-h", pg_host,
        "-p", str(pg_port),
        "-U", pg_user,
        "-d", pg_database,
        "--no-owner",          # 避免跨环境 owner 问题
        "--no-acl",            # 避免权限问题
        "--format=custom",     # 自定义格式，支持 pg_restore
        "-f", str(backup_path),
    ]

    try:
        print(f"[INFO] 执行 pg_dump...")
        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,  # 最长 10 分钟
        )
        if result.returncode != 0:
            print(f"[ERROR] pg_dump 失败 (exit code={result.returncode})", file=sys.stderr)
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  stderr: {line}", file=sys.stderr)
            return False
        dump_size = backup_path.stat().st_size
        print(f"[OK] pg_dump 完成: {backup_name} ({dump_size:,} bytes)")
    except FileNotFoundError:
        print("[ERROR] pg_dump 命令未找到，请安装 PostgreSQL 客户端", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("[ERROR] pg_dump 超时 (10分钟)", file=sys.stderr)
        return False
    except OSError as e:
        print(f"[ERROR] pg_dump 执行失败: {e}", file=sys.stderr)
        return False

    # 2. gzip 压缩
    try:
        with open(backup_path, "rb") as f_in:
            with gzip.open(gz_path, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        backup_path.unlink()
        gz_size = gz_path.stat().st_size
        ratio = (1 - gz_size / dump_size) * 100 if dump_size > 0 else 0
        print(f"[OK] GZip 压缩完成: {gz_path.name} ({gz_size:,} bytes, 压缩率 {ratio:.1f}%)")
    except OSError as e:
        print(f"[ERROR] GZip 压缩失败: {e}", file=sys.stderr)
        return False

    # 3. 清理旧备份
    n_deleted = rotate_old_backups(backup_dir, "chainke_pg_*.sql", retention_days)
    n_deleted += rotate_old_backups(backup_dir, "chainke_pg_*.sql.gz", retention_days)
    if n_deleted > 0:
        print(f"[OK] 清理完成: 删除 {n_deleted} 个过期备份")
    else:
        print(f"[OK] 无过期备份需要清理 (保留期: {retention_days} 天)")

    return True


def backup_env_file(
    env_path: Path,
    env_backup_dir: Path,
    dry_run: bool = False,
) -> bool:
    """
    备份 .env 文件到 backups/env_backup/ 目录
    附带时间戳以保留历史版本
    """
    if not env_path.is_file():
        if dry_run:
            print(f"[DRY-RUN] .env 文件不存在，跳过: {env_path}")
        return True  # 不是错误

    ts = timestamp_str()
    backup_name = f".env.backup_{ts}"
    backup_path = env_backup_dir / backup_name

    if dry_run:
        print(f"[DRY-RUN] 备份 .env 文件: {env_path}")
        print(f"           -> 复制到: {backup_path}")
        return True

    try:
        shutil.copy2(str(env_path), str(backup_path))
        size = backup_path.stat().st_size
        print(f"[OK] .env 备份完成: {backup_name} ({size:,} bytes)")
        return True
    except OSError as e:
        print(f"[ERROR] .env 备份失败: {e}", file=sys.stderr)
        return False


def cleanup_env_backups(
    env_backup_dir: Path,
    retention_days: int,
    dry_run: bool = False,
) -> int:
    """
    清理过期的 .env 备份
    """
    if not env_backup_dir.is_dir():
        return 0

    cutoff = time.time() - retention_days * 86400
    deleted = 0

    for fpath in sorted(env_backup_dir.glob(".env.backup_*")):
        if fpath.stat().st_mtime < cutoff:
            if dry_run:
                print(f"[DRY-RUN] 删除过期 .env 备份: {fpath.name}")
            else:
                fpath.unlink(missing_ok=True)
                print(f"[DELETE] 删除过期 .env 备份: {fpath.name}")
            deleted += 1

    return deleted


def print_summary(
    backup_type: str,
    retention_days: int,
    success: bool,
    dry_run: bool,
) -> None:
    """打印执行摘要"""
    prefix = "[DRY-RUN] " if dry_run else ""
    status = "成功" if success else "失败"
    sep = "=" * 50
    print(f"\n{sep}")
    print(f"{prefix}链客宝数据库备份报告 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"{prefix}类型: {backup_type.upper()} | 状态: {status} | 保留: {retention_days} 天")
    print(f"{sep}")


def main() -> int:
    """主入口"""
    args = parse_args()
    dry_run = args.dry_run
    prefix = "[DRY-RUN] " if dry_run else ""

    backup_dir = Path(args.backup_dir)
    env_backup_dir = backup_dir / "env_backup"

    # ── 确保目录 ──────────────────────────────────────────────────────
    ensure_dir(backup_dir, dry_run=dry_run)
    ensure_dir(env_backup_dir, dry_run=dry_run)

    # ── 加载 .env 文件 ────────────────────────────────────────────────
    env_path = Path(args.env_file)
    env_vars = {}
    if env_path.is_file():
        env_vars = load_env_file(env_path)
        print(f"{prefix}已加载 .env 文件: {env_path} ({len(env_vars)} 个变量)")

    # ── 执行备份 ──────────────────────────────────────────────────────
    success = False
    if args.type == "sqlite":
        db_path = Path(args.sqlite_db)
        success = backup_sqlite(db_path, backup_dir, args.retention, dry_run=dry_run)
    elif args.type == "postgres":
        success = backup_postgres(backup_dir, args.retention, env_vars, dry_run=dry_run)

    if not success and not dry_run:
        print_summary(args.type, args.retention, False, dry_run)
        return 1

    # ── 备份 .env 文件 ────────────────────────────────────────────────
    backup_env_file(env_path, env_backup_dir, dry_run=dry_run)
    cleanup_env_backups(env_backup_dir, args.retention, dry_run=dry_run)

    # ── 打印摘要 ──────────────────────────────────────────────────────
    print_summary(args.type, args.retention, success, dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
