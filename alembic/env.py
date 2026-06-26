"""链客宝 — Alembic 迁移环境配置

为 PostgreSQL 迁移提供自动生成支持。
基于链客宝后端所有 SQLAlchemy 模型 + 支付模块 payment_orders 表。
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from sqlalchemy import MetaData

from alembic import context

# ── 将 backend 目录和项目根目录加入 sys.path ───────────────────────
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
BACKEND_DIR = str(Path(__file__).resolve().parent.parent / "backend")
for p in [BACKEND_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Alembic Config ──────────────────────────────────────────────────
config = context.config

# ── 日志配置 ────────────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── 导入所有 ORM 模型以注册到 Base.metadata ─────────────────────────
# 后端核心模型
from app.database import Base as BackendBase
from app.models._legacy import BusinessCard
from app.models.feedback import Feedback
from app.models.audit_log import AuditLog
from app.notification_service import NotificationRecord
from app.models.escrow import Deal, Milestone, Dispute
from app.models.organization import Organization, OrganizationMember, Invite
from app.models.six_degrees import (
    UserRelation,
    RelationEvent,
    SixDegreePathCache,
    ReferralLink,
)

# 支付模块模型（独立的 Base）
from payment.models import Base as PaymentBase
from payment.models import PaymentOrder

# ── 合并两个 Base 的 metadata ─────────────────────────────────────
# 后端 + 支付模块的所有表合并到一个 target_metadata 中
target_metadata = MetaData()
for table in BackendBase.metadata.tables.values():
    table.tometadata(target_metadata)
for table in PaymentBase.metadata.tables.values():
    table.tometadata(target_metadata)


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接连接到数据库执行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
