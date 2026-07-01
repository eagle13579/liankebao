#!/usr/bin/env python3
"""
PostgreSQL 连接测试脚本

用法:
    python scripts/check_pg_connection.py

环境变量:
    USE_POSTGRES=1     — 强制 PG 模式
    DB_TYPE=postgres   — 或设置 DB_TYPE
    PG_URL=...         — 完整连接 URL（可选）
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE — 逐项配置（可选）
"""

import os
import sys

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 强制 PG 模式
os.environ.setdefault("USE_POSTGRES", "1")
os.environ.setdefault("DB_TYPE", "postgres")


def main():
    print("=" * 50)
    print("  链客宝AI — PostgreSQL 连接测试")
    print("=" * 50)

    # 检查驱动
    try:
        import psycopg2

        pg_version = psycopg2.__version__
        print(f"  [+] psycopg2 驱动: v{pg_version}")
    except ImportError:
        print("  [✗] psycopg2 未安装。执行: pip install psycopg2-binary")
        return False

    # 读取配置
    pg_url = os.environ.get("PG_URL", "")
    pg_host = os.environ.get("PG_HOST", "localhost")
    pg_port = os.environ.get("PG_PORT", "5432")
    pg_user = os.environ.get("PG_USER", "")
    pg_password = os.environ.get("PG_PASSWORD", "")
    pg_db = os.environ.get("PG_DATABASE", "")

    print("\n  配置信息:")
    if pg_url:
        masked_url = pg_url
        if "@" in masked_url:
            user_part, host_part = masked_url.split("@", 1)
            if ":" in user_part:
                masked_url = user_part.split(":", 1)[0] + ":****@" + host_part
        print(f"    PG_URL: {masked_url}")
    else:
        print(f"    PG_HOST: {pg_host}")
        print(f"    PG_PORT: {pg_port}")
        print(f"    PG_USER: {pg_user}")
        print(f"    PG_DATABASE: {pg_db}")
        print(f"    PG_PASSWORD: {'****' if pg_password else '(空)'}")

    # 尝试连接
    print("\n  正在连接...")
    try:
        if pg_url:
            conn = psycopg2.connect(pg_url)
        else:
            conn = psycopg2.connect(
                host=pg_host,
                port=pg_port,
                user=pg_user,
                password=pg_password,
                dbname=pg_db,
            )

        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        cur.close()
        conn.close()

        print("  [✓] 连接成功!")
        print(f"  [i] PostgreSQL 版本: {version}")
        return True

    except Exception as e:
        print(f"  [✗] 连接失败: {e}")
        print()
        print("  可能的原因:")
        print("    1. PostgreSQL 服务未运行")
        print("    2. 连接信息（主机/端口/用户名/密码）不正确")
        print("    3. 数据库不存在")
        print("    4. 防火墙阻挡了连接")
        print()
        print("  检查命令:")
        print("    # 检查 PG 服务状态")
        print("    pg_isready")
        print()
        print("    # 尝试手动连接")
        print(f"    psql -h {pg_host} -p {pg_port} -U {pg_user} -d {pg_db}")
        return False


if __name__ == "__main__":
    success = main()
    print()
    sys.exit(0 if success else 1)
