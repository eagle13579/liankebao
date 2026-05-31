"""PostgreSQL 多租户迁移: 创建组织/成员关系表 + 所有业务表加 organization_id

Revision ID: add_tenant_models
Revises: 02c9e16c4b58
Create Date: 2026-05-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_tenant_models"
down_revision: str | Sequence[str] | None = "c0398919c9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建多租户表结构"""

    # ================================================================
    # 1. 创建 organizations 表
    # ================================================================
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False, server_default="free"),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_id"), "organizations", ["id"], unique=False)
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    # ================================================================
    # 2. 创建 memberships 表
    # ================================================================
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memberships_id"), "memberships", ["id"], unique=False)
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_index(op.f("ix_memberships_org_id"), "memberships", ["org_id"], unique=False)

    # ================================================================
    # 3. 所有业务表加 organization_id 列
    # ================================================================

    # 3a. users
    op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_organization",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"], unique=False)

    # 3b. products
    op.add_column("products", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_products_organization",
        "products",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_products_organization_id"), "products", ["organization_id"], unique=False)

    # 3c. orders
    op.add_column("orders", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_orders_organization",
        "orders",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_orders_organization_id"), "orders", ["organization_id"], unique=False)

    # 3d. withdrawals
    op.add_column("withdrawals", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_withdrawals_organization",
        "withdrawals",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_withdrawals_organization_id"), "withdrawals", ["organization_id"], unique=False)

    # 3e. contacts
    op.add_column("contacts", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_contacts_organization",
        "contacts",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_contacts_organization_id"), "contacts", ["organization_id"], unique=False)

    # 3f. activities
    op.add_column("activities", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_activities_organization",
        "activities",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_activities_organization_id"), "activities", ["organization_id"], unique=False)

    # 3g. import_history
    op.add_column("import_history", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_import_history_organization",
        "import_history",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_import_history_organization_id"), "import_history", ["organization_id"], unique=False)

    # 3h. business_needs
    op.add_column("business_needs", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_business_needs_organization",
        "business_needs",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(op.f("ix_business_needs_organization_id"), "business_needs", ["organization_id"], unique=False)


def downgrade() -> None:
    """回滚多租户结构"""

    # ================================================================
    # 1. 删除业务表的 organization_id 列和索引
    # ================================================================

    # 按依赖顺序反向操作
    tables_with_org = [
        "business_needs",
        "import_history",
        "activities",
        "contacts",
        "withdrawals",
        "orders",
        "products",
        "users",
    ]

    for table in tables_with_org:
        op.drop_constraint(
            f"fk_{table}_organization",
            table,
            type_="foreignkey",
        )
        op.drop_index(op.f(f"ix_{table}_organization_id"), table_name=table)
        op.drop_column(table, "organization_id")

    # ================================================================
    # 2. 删除 memberships 表
    # ================================================================
    op.drop_index(op.f("ix_memberships_org_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_id"), table_name="memberships")
    op.drop_table("memberships")

    # ================================================================
    # 3. 删除 organizations 表
    # ================================================================
    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_index(op.f("ix_organizations_id"), table_name="organizations")
    op.drop_table("organizations")
