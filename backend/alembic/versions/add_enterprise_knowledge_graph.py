"""创建企业知识图谱表 (enterprises + enterprise_relations)

Revision ID: add_enterprise_knowledge_graph
Revises: add_tenant_models
Create Date: 2026-05-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_enterprise_knowledge_graph"
down_revision: str | Sequence[str] | None = "add_tenant_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建企业知识图谱表"""

    # ================================================================
    # 1. 创建 enterprises 表
    # ================================================================
    op.create_table(
        "enterprises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="企业全称"),
        sa.Column("short_name", sa.String(length=100), nullable=True, comment="企业简称"),
        sa.Column(
            "credit_code",
            sa.String(length=18),
            nullable=True,
            unique=True,
            comment="统一社会信用代码",
        ),
        sa.Column("legal_person", sa.String(length=100), nullable=True, comment="法定代表人"),
        sa.Column("registered_capital", sa.String(length=50), nullable=True, comment="注册资本"),
        sa.Column("established_date", sa.String(length=20), nullable=True, comment="成立日期"),
        sa.Column("industry", sa.String(length=100), nullable=True, comment="行业分类"),
        sa.Column("region", sa.String(length=100), nullable=True, comment="地区"),
        sa.Column("business_scope", sa.Text(), nullable=True, comment="经营范围"),
        sa.Column("tags", sa.String(length=500), nullable=True, comment="标签(逗号分隔)"),
        sa.Column("website", sa.String(length=500), nullable=True, comment="企业官网"),
        sa.Column(
            "data_source",
            sa.String(length=20),
            nullable=True,
            server_default="manual",
            comment="数据来源: manual/crawl/api",
        ),
        sa.Column(
            "confidence", sa.Integer(), nullable=True, server_default="50", comment="数据置信度 0-100"
        ),
        sa.Column("extra", sa.Text(), nullable=True, comment="扩展JSON"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_enterprises_id"), "enterprises", ["id"], unique=False)
    op.create_index(op.f("ix_enterprises_name"), "enterprises", ["name"], unique=False)
    op.create_index(op.f("ix_enterprises_credit_code"), "enterprises", ["credit_code"], unique=True)

    # ================================================================
    # 2. 创建 enterprise_relations 表
    # ================================================================
    op.create_table(
        "enterprise_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "relation_type",
            sa.String(length=30),
            nullable=False,
            comment="关系类型: invest/compete/supply/subsidiary/partner/customer",
        ),
        sa.Column("relation_label", sa.String(length=100), nullable=True, comment="关系描述"),
        sa.Column(
            "confidence", sa.Integer(), nullable=True, server_default="50", comment="置信度 0-100"
        ),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=True,
            server_default="manual",
            comment="来源: manual/crawl/ai_infer",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_enterprise_relations_id"), "enterprise_relations", ["id"], unique=False)
    op.create_index(
        op.f("ix_enterprise_relations_source_id"), "enterprise_relations", ["source_id"], unique=False
    )
    op.create_index(
        op.f("ix_enterprise_relations_target_id"), "enterprise_relations", ["target_id"], unique=False
    )


def downgrade() -> None:
    """回滚：删除企业知识图谱表"""
    op.drop_table("enterprise_relations")
    op.drop_table("enterprises")
