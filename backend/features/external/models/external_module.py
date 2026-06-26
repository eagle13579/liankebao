"""
外部模块注册模型 (ExternalModule)

记录所有注册到链客宝的外部模块信息，包括:
  - 模块元信息（名称、版本、描述）
  - 接入凭证（API Key / Secret）
  - 状态控制（启用/停用）
  - Webhook 签名配置

此模型对应数据库表 external_modules。
迁移自旧版链客宝 backend/modules/external/models/external_module.py
适配 chainke-full: 使用 app.database.Base 作为声明基类。
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped

from app.database import Base


class ExternalModule(Base):
    """外部模块注册记录

    每个外部模块在链客宝中注册后，对应一条记录。
    记录携带运行所需的配置和凭证信息。
    """

    __tablename__ = "external_modules"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = Column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="外部模块唯一名称，如 payment_gateway",
    )
    version: Mapped[str] = Column(
        String(20),
        default="1.0.0",
        nullable=False,
        comment="模块版本号",
    )
    description: Mapped[str | None] = Column(
        Text,
        comment="模块描述",
    )

    # ── 接入凭证 ─────────────────────────────────────────────
    api_key: Mapped[str | None] = Column(
        String(255),
        comment="API Key（用于外部回调时识别身份）",
    )
    api_secret: Mapped[str | None] = Column(
        String(255),
        comment="API Secret（用于签名验证）",
    )

    # ── Webhook 配置 ─────────────────────────────────────────
    webhook_url: Mapped[str | None] = Column(
        String(500),
        comment="外部模块注册的回调地址（由外部系统提供）",
    )
    webhook_secret: Mapped[str | None] = Column(
        String(255),
        comment="Webhook 签名密钥（用于验证回调来源）",
    )
    webhook_algo: Mapped[str] = Column(
        String(20),
        default="hmac-sha256",
        comment="Webhook 签名算法",
    )

    # ── 模块状态 ─────────────────────────────────────────────
    is_active: Mapped[bool] = Column(
        Boolean,
        default=True,
        comment="是否启用",
    )
    is_installed: Mapped[bool] = Column(
        Boolean,
        default=False,
        comment="是否已完成 install() 安装步骤",
    )

    # ── 时间戳 ──────────────────────────────────────────────
    created_at: Mapped[datetime] = Column(
        DateTime,
        default=datetime.utcnow,
        comment="注册时间",
    )
    updated_at: Mapped[datetime] = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
    installed_at: Mapped[datetime | None] = Column(
        DateTime,
        comment="安装完成时间",
    )

    def __repr__(self) -> str:
        return (
            f"<ExternalModule(id={self.id}, name='{self.name}', "
            f"active={self.is_active}, installed={self.is_installed})>"
        )
