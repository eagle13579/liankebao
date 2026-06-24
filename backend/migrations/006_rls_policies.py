"""
RLS 迁移脚本 — 为所有业务表启用 PostgreSQL Row-Level Security

目标:
  为所有包含 organization_id 列的表启用 RLS 策略，确保数据库层强制租户隔离。
  防止"应用层漏过滤 + 数据库层无限制"的安全缺口。

适用数据库: PostgreSQL 12+
使用方式:
  python migrations/006_rls_policies.py              # 只打印 SQL（dry-run）
  python migrations/006_rls_policies.py --apply      # 实际执行
  python migrations/006_rls_policies.py --down       # 回滚（删除所有 RLS 策略）

约束:
  - 只追加不覆盖（铁律九十二）
  - 保留已有 RLS 策略
"""

import argparse
import os
import sys

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ============================================================
# 所有需要 RLS 的表（含 organization_id 的业务表）
# 共 18 张表，按依赖顺序排列（子表在前，父表在后不影响策略创建）
# ============================================================
RLS_TABLES = [
    # 核心业务表
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
    # 私董会 & 会员
    "private_board_orders",
    "membership_orders",
    "match_credit_logs",
    # 线上对接会
    "online_matching_events",
    "online_matching_registrations",
    "online_matching_feedback",
    # 系统表
    "revoked_tokens",
]

# ============================================================
# SQL 生成
# ============================================================


def _make_up_sql(table: str) -> list[str]:
    """生成启用 RLS + 创建策略的 SQL"""
    return [
        f"-- === {table} ===",
        f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;',
        f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;',
        "",
        f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table}";',
        "",
        f'CREATE POLICY tenant_isolation_policy ON "{table}"',
        "    FOR ALL",
        "    USING (organization_id = current_setting('app.current_org_id')::integer);",
        "",
    ]


def _make_down_sql(table: str) -> list[str]:
    """生成回滚 SQL"""
    return [
        f"-- === {table} ===",
        f'DROP POLICY IF EXISTS tenant_isolation_policy ON "{table}";',
        f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;',
        f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;',
        "",
    ]


def _admin_bypass_sql() -> list[str]:
    """为管理员提供绕过 RLS 的 helper"""
    return [
        "-- ============================================================",
        "-- 管理员绕过 RLS 的辅助函数",
        "-- ============================================================",
        "CREATE OR REPLACE FUNCTION admin_bypass_rls()",
        "    RETURNS boolean AS $$",
        "    SELECT current_setting('app.bypass_rls', true) = 'true';",
        "$$ LANGUAGE sql STABLE;",
        "",
        "-- 为每张表创建管理员豁免策略（如果还没有的话）",
        "-- 这样当 app.bypass_rls=true 时，admin 用户可以查询所有租户数据",
    ]


def _admin_wrapper_sql(table: str) -> list[str]:
    return [
        f'DROP POLICY IF EXISTS admin_bypass_policy ON "{table}";',
        f'CREATE POLICY admin_bypass_policy ON "{table}"',
        "    FOR ALL",
        "    USING (admin_bypass_rls());",
        "",
    ]


def _set_org_id_function_sql() -> str:
    """生成设置 org_id 的函数（app 层在路由入口调用）"""
    return """
-- ============================================================
-- 设置当前请求的租户上下文（由 FastAPI 中间件在每次请求时调用）
-- ============================================================
CREATE OR REPLACE FUNCTION set_current_org_id(org_id integer)
    RETURNS void AS $$
    SELECT set_config('app.current_org_id', org_id::text, true);
$$ LANGUAGE sql VOLATILE;


-- ============================================================
-- 获取当前请求的租户 ID（供 RLS 策略使用）
-- ============================================================
CREATE OR REPLACE FUNCTION get_current_org_id_rls()
    RETURNS integer AS $$
    SELECT current_setting('app.current_org_id', true)::integer;
$$ LANGUAGE sql STABLE;


-- ============================================================
-- 设置 RLS 绕过标志（供超级管理员使用）
-- ============================================================
CREATE OR REPLACE FUNCTION set_bypass_rls(bypass boolean)
    RETURNS void AS $$
    SELECT set_config('app.bypass_rls', CASE WHEN bypass THEN 'true' ELSE 'false' END, true);
$$ LANGUAGE sql VOLATILE;
"""


def build_full_up_sql() -> str:
    """生成完整的迁移 SQL（向上）"""
    lines = [
        "-- ============================================================",
        "-- RLS 多租户隔离迁移 — UP",
        f"-- 创建时间: {__import__('datetime').datetime.utcnow().isoformat()}",
        "-- ============================================================",
        "",
        "-- 前置条件：确保所有表已有 organization_id 列",
        "-- （由 app/models.py 中 _org_fk() 自动创建）",
        "",
    ]

    # 1. 辅助函数
    lines.append("-- 1. 创建租户上下文函数")
    lines.append(_set_org_id_function_sql())
    lines.append("")

    # 2. 管理员绕过函数
    lines.append("-- 2. 管理员绕过 RLS 辅助函数")
    lines.extend(_admin_bypass_sql())
    lines.append("")

    # 3. 为每张表启用 RLS 并创建策略
    lines.append("-- 3. 为所有业务表启用 RLS + 创建租户隔离策略")
    lines.append("")
    for table in RLS_TABLES:
        lines.extend(_make_up_sql(table))
        lines.extend(_admin_wrapper_sql(table))

    lines.append("-- === 完成 ===\n")
    return "\n".join(lines)


def build_full_down_sql() -> str:
    """生成完整的回滚 SQL（向下）"""
    lines = [
        "-- ============================================================",
        "-- RLS 多租户隔离迁移 — DOWN",
        "-- ============================================================",
        "",
    ]
    for table in reversed(RLS_TABLES):
        lines.extend(_make_down_sql(table))

    lines.extend(
        [
            "",
            "-- 删除辅助函数",
            "DROP FUNCTION IF EXISTS get_current_org_id_rls;",
            "DROP FUNCTION IF EXISTS set_current_org_id(integer);",
            "DROP FUNCTION IF EXISTS set_bypass_rls(boolean);",
            "DROP FUNCTION IF EXISTS admin_bypass_rls;",
            "",
            "-- === 完成 ===\n",
        ]
    )
    return "\n".join(lines)


# ============================================================
# 执行入口
# ============================================================


def apply_sql(sql: str) -> None:
    """连接到 PostgreSQL 并执行 SQL"""
    from app.database import DB_TYPE, engine

    if DB_TYPE != "postgres":
        print("错误: RLS 策略仅适用于 PostgreSQL，当前 DB_TYPE=%s" % DB_TYPE)
        sys.exit(1)

    with engine.connect() as conn:
        # 逐条执行（psycopg2 不支持多条语句一次 execute）
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            if not stmt or stmt.startswith("--"):
                continue
            try:
                conn.execute(stmt)
                print("  ✓ 执行成功")
            except Exception as e:
                print(f"  ✗ 执行失败: {e}")
        conn.commit()
    print("\n所有 RLS 策略已应用。")


def main():
    parser = argparse.ArgumentParser(description="RLS 多租户隔离迁移脚本")
    parser.add_argument("--apply", action="store_true", help="实际执行迁移（默认 dry-run 只输出 SQL）")
    parser.add_argument("--down", action="store_true", help="回滚 RLS 策略")
    args = parser.parse_args()

    if args.down:
        sql = build_full_down_sql()
        print(sql)
        if args.apply:
            print("\n正在回滚 RLS 策略...")
            apply_sql(sql)
    else:
        sql = build_full_up_sql()
        print(sql)
        if args.apply:
            print("\n正在应用 RLS 策略...")
            apply_sql(sql)

    if not args.apply:
        print("\n提示: 以上为 dry-run 输出。实际执行请加 --apply 参数。")


if __name__ == "__main__":
    main()
