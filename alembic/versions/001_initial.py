"""001_initial - 链客宝初始数据库 Schema (SQLite → PostgreSQL)

从链客宝现有 SQLite 数据库 schema 生成的等价格 PostgreSQL 迁移脚本。
包含后端核心表 + 交易保障 + 多租户组织 + 六度人脉 + 支付模块。

创建的表:
  - audit_logs          审计日志
  - business_cards      企业数字名片
  - feedbacks           用户反馈
  - notification_records 通知发送记录
  - payment_orders      支付订单 (支付模块)
  - escrow_deals        交易保障主表
  - escrow_milestones   交易里程碑
  - escrow_disputes     交易争议
  - organizations       多租户组织
  - organization_members 组织成员
  - organization_invites 组织邀请
  - user_relations      用户关系边
  - relation_events     关系事件日志
  - six_degree_path_cache 六度路径缓存
  - referral_links      邀请链接
  - users               用户 (被其他表 FK 引用, 无单独 ORM 模型)

Revision ID: 001
Revises: None
Create Date: 2025-06-25 00:57:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===================================================================
    # users — 用户表（被多个模块 FK 引用）
    # ===================================================================
    # 该表无独立 ORM 模型，仅根据 ForeignKey 引用推断的 minimal schema
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True, comment="用户名"),
        sa.Column("email", sa.String(length=128), nullable=True, comment="邮箱"),
        sa.Column("phone", sa.String(length=20), nullable=True, comment="手机号"),
        sa.Column("nickname", sa.String(length=64), nullable=True, comment="昵称"),
        sa.Column("avatar_url", sa.String(length=512), nullable=True, comment="头像 URL"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active", comment="状态: active/inactive/disabled"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="用户表",
    )
    op.create_index("ix_users_id", "users", ["id"])

    # ===================================================================
    # audit_logs — 审计日志（app/models/audit_log.py）
    # ===================================================================
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False, comment="操作用户ID"),
        sa.Column("action", sa.String(length=64), nullable=False, comment="操作类型"),
        sa.Column("resource_type", sa.String(length=64), nullable=True, comment="资源类型"),
        sa.Column("resource_id", sa.String(length=128), nullable=True, comment="资源ID"),
        sa.Column("detail", postgresql.JSON(), nullable=True, comment="详情JSON"),
        sa.Column("ip_address", sa.String(length=45), nullable=True, comment="客户端IP地址"),
        sa.Column("user_agent", sa.Text(), nullable=True, comment="客户端User-Agent"),
        sa.Column("result", sa.String(length=16), nullable=False, server_default="success", comment="操作结果: success/failure"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="审计日志记录",
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ===================================================================
    # business_cards — 企业数字名片（app/models/_legacy.py）
    # ===================================================================
    op.create_table(
        "business_cards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False, comment="所属用户ID"),
        sa.Column("fields", postgresql.JSON(), nullable=False, comment="名片字段 JSON"),
        sa.Column("share_token", sa.String(length=128), nullable=True, comment="分享令牌"),
        sa.Column("cover_image", sa.String(length=512), nullable=True, comment="封面图 URL"),
        sa.Column("album_meta", postgresql.JSON(), nullable=True, comment="电子画册配置"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="web_upload", comment="来源: web_upload/web_manual/miniapp_wechat"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_token", name="uq_business_cards_share_token"),
        comment="企业数字名片",
    )
    op.create_index("ix_business_cards_id", "business_cards", ["id"])
    op.create_index("ix_business_cards_user_id", "business_cards", ["user_id"])

    # ===================================================================
    # feedbacks — 用户反馈（app/models/feedback.py）
    # ===================================================================
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False, comment="反馈用户ID"),
        sa.Column("target_type", sa.String(length=32), nullable=False, comment="目标类型: enterprise/card/match"),
        sa.Column("target_id", sa.String(length=128), nullable=False, comment="目标ID"),
        sa.Column("feedback_type", sa.String(length=16), nullable=False, comment="反馈类型: like/dislike/rating/report"),
        sa.Column("score", sa.Integer(), nullable=True, comment="评分 (1-5)，仅 rating 类型使用"),
        sa.Column("comment", sa.Text(), nullable=True, comment="文本评论"),
        sa.Column("context", postgresql.JSON(), nullable=True, comment="上下文 JSON (页面/场景/候选列表等)"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="用户反馈记录",
    )
    op.create_index("ix_feedbacks_id", "feedbacks", ["id"])
    op.create_index("ix_feedbacks_user_id", "feedbacks", ["user_id"])
    op.create_index("ix_feedbacks_target_type", "feedbacks", ["target_type"])
    op.create_index("ix_feedbacks_target_id", "feedbacks", ["target_id"])

    # ===================================================================
    # notification_records — 通知发送记录（app/notification_service.py）
    # ===================================================================
    op.create_table(
        "notification_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False, comment="目标用户 ID"),
        sa.Column("channel", sa.String(length=16), nullable=False, comment="渠道: email / sms"),
        sa.Column("title", sa.String(length=256), nullable=True, comment="通知标题"),
        sa.Column("body", sa.Text(), nullable=False, comment="通知正文"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending", comment="状态: pending/success/failed"),
        sa.Column("error", sa.Text(), nullable=True, comment="失败原因"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("sent_at", sa.DateTime(), nullable=True, comment="发送时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="通知发送记录",
    )
    op.create_index("ix_notification_records_id", "notification_records", ["id"])
    op.create_index("ix_notification_records_user_id", "notification_records", ["user_id"])

    # ===================================================================
    # payment_orders — 支付订单（payment/models.py）
    # ===================================================================
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=False, comment="业务订单号"),
        sa.Column("user_id", sa.String(length=64), nullable=False, comment="用户标识"),
        sa.Column("amount", sa.Integer(), nullable=False, comment="订单金额(分)"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY", comment="币种"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending", comment="订单状态: pending/paid/closed/refunded"),
        sa.Column("channel", sa.String(length=16), nullable=True, server_default="wechat", comment="支付渠道: wechat/alipay/balance"),
        sa.Column("channel_order_no", sa.String(length=128), nullable=True, comment="渠道订单号"),
        sa.Column("subject", sa.String(length=128), nullable=False, comment="订单标题"),
        sa.Column("body", sa.Text(), nullable=True, comment="订单描述"),
        sa.Column("notify_url", sa.String(length=256), nullable=True, comment="异步通知地址"),
        sa.Column("return_url", sa.String(length=256), nullable=True, comment="同步跳转地址"),
        sa.Column("extra", postgresql.JSON(), nullable=True, comment="附加数据"),
        sa.Column("paid_at", sa.DateTime(), nullable=True, comment="支付完成时间"),
        sa.Column("closed_at", sa.DateTime(), nullable=True, comment="订单关闭时间"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="最后更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no", name="uq_payment_orders_order_no"),
        comment="支付订单记录",
    )
    op.create_index("ix_payment_orders_id", "payment_orders", ["id"])
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_index("ix_payment_orders_order_no", "payment_orders", ["order_no"])
    op.create_index("ix_payment_orders_status", "payment_orders", ["status"])

    # ===================================================================
    # escrow_deals — 交易保障主表（app/models/escrow.py）
    # ===================================================================
    op.create_table(
        "escrow_deals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False, comment="买方用户ID"),
        sa.Column("seller_id", sa.Integer(), nullable=False, comment="卖方用户ID"),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0.0", comment="交易金额"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", comment="交易状态"),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="", comment="交易标题/商品名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="交易描述"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="交易保障主表",
    )
    op.create_index("ix_escrow_deals_id", "escrow_deals", ["id"])
    op.create_index("ix_escrow_deals_buyer_id", "escrow_deals", ["buyer_id"])
    op.create_index("ix_escrow_deals_seller_id", "escrow_deals", ["seller_id"])
    op.create_index("ix_escrow_deals_status", "escrow_deals", ["status"])

    # ===================================================================
    # escrow_milestones — 交易里程碑（app/models/escrow.py）
    # ===================================================================
    op.create_table(
        "escrow_milestones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False, comment="关联交易ID"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="里程碑名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="里程碑描述"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", comment="状态"),
        sa.Column("due_date", sa.DateTime(), nullable=True, comment="截止日期"),
        sa.Column("completed_at", sa.DateTime(), nullable=True, comment="完成时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="交易里程碑",
    )
    op.create_index("ix_escrow_milestones_id", "escrow_milestones", ["id"])
    op.create_index("ix_escrow_milestones_deal_id", "escrow_milestones", ["deal_id"])

    # ===================================================================
    # escrow_disputes — 交易争议（app/models/escrow.py）
    # ===================================================================
    op.create_table(
        "escrow_disputes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False, comment="关联交易ID"),
        sa.Column("initiator_id", sa.Integer(), nullable=False, comment="发起人用户ID"),
        sa.Column("reason", sa.String(length=500), nullable=False, comment="争议原因"),
        sa.Column("description", sa.Text(), nullable=True, comment="详细描述"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open", comment="争议状态"),
        sa.Column("evidence", sa.Text(), nullable=True, comment="证据（JSON字符串，存文件链接/描述）"),
        sa.Column("resolution", sa.Text(), nullable=True, comment="解决结果"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True, comment="解决时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="争议处理",
    )
    op.create_index("ix_escrow_disputes_id", "escrow_disputes", ["id"])
    op.create_index("ix_escrow_disputes_deal_id", "escrow_disputes", ["deal_id"])

    # ===================================================================
    # organizations — 多租户组织（app/models/organization.py）
    # ===================================================================
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="组织名称"),
        sa.Column("slug", sa.String(length=100), nullable=False, comment="唯一标识符（用于 URL）"),
        sa.Column("owner_id", sa.Integer(), nullable=False, comment="创建者/所有者"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        comment="组织模型",
    )
    op.create_index("ix_organizations_id", "organizations", ["id"])
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # ===================================================================
    # organization_members — 组织成员（app/models/organization.py）
    # ===================================================================
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False, comment="组织 ID"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="用户 ID"),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member", comment="角色: admin/member"),
        sa.Column("joined_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="加入时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="组织成员关联模型",
    )
    op.create_index("ix_organization_members_id", "organization_members", ["id"])

    # ===================================================================
    # organization_invites — 组织邀请（app/models/organization.py）
    # ===================================================================
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False, comment="组织 ID"),
        sa.Column("email", sa.String(length=255), nullable=False, comment="受邀邮箱"),
        sa.Column("token", sa.String(length=64), nullable=False, comment="邀请令牌"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", comment="状态: pending/accepted/expired"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_organization_invites_token"),
        comment="组织邀请模型",
    )
    op.create_index("ix_organization_invites_id", "organization_invites", ["id"])
    op.create_index("ix_organization_invites_token", "organization_invites", ["token"])

    # ===================================================================
    # user_relations — 用户关系边（app/models/six_degrees.py）
    # ===================================================================
    op.create_table(
        "user_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False, comment="关系发起方"),
        sa.Column("to_user_id", sa.Integer(), nullable=False, comment="关系接收方"),
        sa.Column("relation_type", sa.String(length=20), nullable=False, server_default="invite", comment="关系类型: invite/contact/brochure/coop/refer"),
        sa.Column("label", sa.String(length=100), nullable=True, comment="关系标签/备注"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.5", comment="信任度 0.0~1.0"),
        sa.Column("interaction_count", sa.Integer(), nullable=False, server_default="1", comment="交互次数"),
        sa.Column("last_interaction_at", sa.DateTime(), nullable=True, comment="最近一次交互时间"),
        sa.Column("bidirectional", sa.Boolean(), nullable=False, server_default=sa.text("false"), comment="是否为双向关系"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"), comment="关系是否有效"),
        sa.Column("source", sa.String(length=30), nullable=True, server_default="invite", comment="来源: invite/import/wechat/manual"),
        sa.Column("source_detail", sa.String(length=200), nullable=True, comment="来源详情，如导入批次ID"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("organization_id", sa.Integer(), nullable=True, default=None),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_user_id", "to_user_id", name="uq_user_relation_pair"),
        comment="用户关系边（信任连接）",
    )
    op.create_index("ix_user_relations_id", "user_relations", ["id"])
    op.create_index("ix_user_relations_from_user_id", "user_relations", ["from_user_id"])
    op.create_index("ix_user_relations_to_user_id", "user_relations", ["to_user_id"])
    op.create_index("idx_user_relation_active", "user_relations", ["from_user_id", "is_active", "trust_score"])
    op.create_index("idx_user_relation_to", "user_relations", ["to_user_id", "is_active"])

    # ===================================================================
    # relation_events — 关系事件日志（app/models/six_degrees.py）
    # ===================================================================
    op.create_table(
        "relation_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("relation_id", sa.Integer(), nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False, comment="事件类型: created/trust_updated/deactivated/reactivated/score_decayed"),
        sa.Column("old_trust_score", sa.Float(), nullable=True, comment="变更前信任度"),
        sa.Column("new_trust_score", sa.Float(), nullable=True, comment="变更后信任度"),
        sa.Column("reason", sa.String(length=200), nullable=True, comment="变更原因描述"),
        sa.Column("metadata_json", sa.Text(), nullable=True, comment="附加元数据 JSON"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        comment="关系事件日志",
    )
    op.create_index("ix_relation_events_id", "relation_events", ["id"])
    op.create_index("ix_relation_events_relation_id", "relation_events", ["relation_id"])
    op.create_index("ix_relation_events_from_user_id", "relation_events", ["from_user_id"])
    op.create_index("ix_relation_events_to_user_id", "relation_events", ["to_user_id"])
    op.create_index("ix_relation_events_created_at", "relation_events", ["created_at"])

    # ===================================================================
    # six_degree_path_cache — 六度路径缓存（app/models/six_degrees.py）
    # ===================================================================
    op.create_table(
        "six_degree_path_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("path_json", sa.Text(), nullable=False, comment="路径 JSON"),
        sa.Column("path_length", sa.Integer(), nullable=False, comment="路径长度(跳数)"),
        sa.Column("total_trust_score", sa.Float(), nullable=False, server_default="0.0", comment="路径总信任度"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1", comment="被命中次数"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="缓存过期时间"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_user_id", "to_user_id", name="uq_path_cache_pair"),
        comment="六度路径缓存表",
    )
    op.create_index("ix_six_degree_path_cache_id", "six_degree_path_cache", ["id"])
    op.create_index("ix_six_degree_path_cache_from_user_id", "six_degree_path_cache", ["from_user_id"])
    op.create_index("ix_six_degree_path_cache_to_user_id", "six_degree_path_cache", ["to_user_id"])
    op.create_index("idx_path_cache_expires", "six_degree_path_cache", ["expires_at"])

    # ===================================================================
    # referral_links — 邀请链接（app/models/six_degrees.py）
    # ===================================================================
    op.create_table(
        "referral_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False, comment="邀请码"),
        sa.Column("title", sa.String(length=100), nullable=True, comment="链接标题"),
        sa.Column("description", sa.String(length=500), nullable=True, comment="链接描述"),
        sa.Column("invite_type", sa.String(length=20), nullable=False, server_default="direct", comment="邀请类型: direct/brochure/product"),
        sa.Column("redirect_url", sa.String(length=500), nullable=True, comment="跳转目标URL"),
        sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0", comment="扫码次数"),
        sa.Column("register_count", sa.Integer(), nullable=False, server_default="0", comment="通过此链接注册数"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(), nullable=True, comment="过期时间"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_referral_links_code"),
        comment="邀请链接/二维码",
    )
    op.create_index("ix_referral_links_id", "referral_links", ["id"])
    op.create_index("ix_referral_links_code", "referral_links", ["code"])
    op.create_index("ix_referral_links_owner_user_id", "referral_links", ["owner_user_id"])
    op.create_index("idx_referral_owner", "referral_links", ["owner_user_id", "is_active"])


def downgrade() -> None:
    """回滚迁移（删除所有表，逆序以避免 FK 冲突）"""
    tables = [
        "referral_links",
        "six_degree_path_cache",
        "relation_events",
        "user_relations",
        "organization_invites",
        "organization_members",
        "organizations",
        "escrow_disputes",
        "escrow_milestones",
        "escrow_deals",
        "payment_orders",
        "notification_records",
        "feedbacks",
        "business_cards",
        "audit_logs",
        "users",
    ]
    for table in tables:
        op.drop_table(table, if_exists=True)
