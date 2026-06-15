"""digital_brochure 初始建表

创建 7 张核心表:
  - auth_users     认证用户
  - auth_tokens    认证令牌
  - users          用户信息
  - brochures      翻页图册
  - trust_network  信任网络
  - match_records  匹配记录
  - visitor_logs   访客日志

Migration ID: 9a8b7c6d5e
Revises: None (初始迁移)
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a8b7c6d5e"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("digital_brochure",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 digital_brochure 数据库的 7 张表"""

    # --- 1. auth_users ---
    op.create_table(
        "auth_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- 2. auth_tokens ---
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False, unique=True),
        sa.Column("token_type", sa.String(length=20), nullable=False, server_default=sa.text("'access'")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    # --- 3. users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("auth_user_id", sa.Integer(), sa.ForeignKey("auth_users.id"), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("avatar", sa.String(length=500), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("wechat_id", sa.String(length=100), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True, server_default=sa.text("'[]'")),
        sa.Column("settings", sa.Text(), nullable=True, server_default=sa.text("'{}'")),
        sa.Column("is_public", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- 4. brochures ---
    op.create_table(
        "brochures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("cover", sa.String(length=500), nullable=True),
        sa.Column("pages_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("is_public", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("share_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- 5. trust_network ---
    op.create_table(
        "trust_network",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trust_level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("tags", sa.Text(), nullable=True, server_default=sa.text("'[]'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_mutual", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "target_user_id", name="uq_trust_network_pair"),
    )

    # --- 6. match_records ---
    op.create_table(
        "match_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("matched_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("match_type", sa.String(length=50), nullable=False, server_default=sa.text("'supply_demand'")),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("contact_made", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- 7. visitor_logs ---
    op.create_table(
        "visitor_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("brochure_id", sa.Integer(), sa.ForeignKey("brochures.id"), nullable=False),
        sa.Column("visitor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("visitor_ip", sa.String(length=45), nullable=True),
        sa.Column("visitor_agent", sa.String(length=500), nullable=True),
        sa.Column("visit_type", sa.String(length=20), nullable=False, server_default=sa.text("'view'")),
        sa.Column("duration_sec", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("extra_data", sa.Text(), nullable=True, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- 索引 ---
    op.create_index("idx_at_user_id", "auth_tokens", ["user_id"])
    op.create_index("idx_at_token", "auth_tokens", ["token"])
    op.create_index("idx_u_auth_user_id", "users", ["auth_user_id"])
    op.create_index("idx_b_user_id", "brochures", ["user_id"])
    op.create_index("idx_b_status", "brochures", ["status"])
    op.create_index("idx_tn_user_id", "trust_network", ["user_id"])
    op.create_index("idx_tn_target", "trust_network", ["target_user_id"])
    op.create_index("idx_mr_user_id", "match_records", ["user_id"])
    op.create_index("idx_mr_matched", "match_records", ["matched_user_id"])
    op.create_index("idx_vl_brochure", "visitor_logs", ["brochure_id"])
    op.create_index("idx_vl_visitor", "visitor_logs", ["visitor_id"])
    op.create_index("idx_vl_time", "visitor_logs", ["created_at"])

    # --- Schema 版本记录 ---
    op.create_table(
        "_schema_version",
        sa.Column("version", sa.String(length=20), primary_key=True),
        sa.Column("applied_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.execute(
        "INSERT INTO _schema_version (version, description) VALUES "
        "('v1.0.0', 'digital_brochure_db v1.0.0 - 7张初始表')"
    )


def downgrade() -> None:
    """删除所有 digital_brochure 表"""
    op.drop_table("_schema_version")
    op.drop_table("visitor_logs")
    op.drop_table("match_records")
    op.drop_table("trust_network")
    op.drop_table("brochures")
    op.drop_table("users")
    op.drop_table("auth_tokens")
    op.drop_table("auth_users")
