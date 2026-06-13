"""
交易保障数据模型 (Escrow System)
=================================
对标 Alibaba Trade Assurance 的交易保障体系:
  - Deal        — 交易主表, 含完整状态机
  - Milestone   — 里程碑追踪
  - Dispute     — 争议处理

状态机流转:
  pending → paid → fulfilled → completed (正常完成)
                  ↓
              disputed → resolved → completed
                  ↓
              disputed → refunded
      ↓
  cancelled
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, relationship

from app.database import Base

logger = logging.getLogger(__name__)

# ============================================================
# 交易状态常量
# ============================================================

DEAL_STATUS_PENDING = "pending"  # 待付款
DEAL_STATUS_PAID = "paid"  # 已付款（资金冻结，模拟）
DEAL_STATUS_FULFILLED = "fulfilled"  # 已履约（卖家完成交付）
DEAL_STATUS_DISPUTED = "disputed"  # 争议中
DEAL_STATUS_RESOLVED = "resolved"  # 争议已解决
DEAL_STATUS_COMPLETED = "completed"  # 已完成
DEAL_STATUS_REFUNDED = "refunded"  # 已退款
DEAL_STATUS_CANCELLED = "cancelled"  # 已取消

VALID_DEAL_STATUSES = frozenset({
    DEAL_STATUS_PENDING,
    DEAL_STATUS_PAID,
    DEAL_STATUS_FULFILLED,
    DEAL_STATUS_DISPUTED,
    DEAL_STATUS_RESOLVED,
    DEAL_STATUS_COMPLETED,
    DEAL_STATUS_REFUNDED,
    DEAL_STATUS_CANCELLED,
})

# 合法的状态转换映射
DEAL_STATUS_TRANSITIONS: dict[str, set[str]] = {
    DEAL_STATUS_PENDING: {DEAL_STATUS_PAID, DEAL_STATUS_CANCELLED},
    DEAL_STATUS_PAID: {DEAL_STATUS_FULFILLED, DEAL_STATUS_DISPUTED, DEAL_STATUS_CANCELLED},
    DEAL_STATUS_FULFILLED: {DEAL_STATUS_COMPLETED, DEAL_STATUS_DISPUTED},
    DEAL_STATUS_DISPUTED: {DEAL_STATUS_RESOLVED, DEAL_STATUS_REFUNDED},
    DEAL_STATUS_RESOLVED: {DEAL_STATUS_COMPLETED},
    DEAL_STATUS_COMPLETED: set(),
    DEAL_STATUS_REFUNDED: set(),
    DEAL_STATUS_CANCELLED: set(),
}

MILESTONE_STATUS_PENDING = "pending"
MILESTONE_STATUS_IN_PROGRESS = "in_progress"
MILESTONE_STATUS_COMPLETED = "completed"
MILESTONE_STATUS_FAILED = "failed"

VALID_MILESTONE_STATUSES = frozenset({
    MILESTONE_STATUS_PENDING,
    MILESTONE_STATUS_IN_PROGRESS,
    MILESTONE_STATUS_COMPLETED,
    MILESTONE_STATUS_FAILED,
})

DISPUTE_STATUS_OPEN = "open"
DISPUTE_STATUS_INVESTIGATING = "investigating"
DISPUTE_STATUS_RESOLVED = "resolved"
DISPUTE_STATUS_REJECTED = "rejected"

VALID_DISPUTE_STATUSES = frozenset({
    DISPUTE_STATUS_OPEN,
    DISPUTE_STATUS_INVESTIGATING,
    DISPUTE_STATUS_RESOLVED,
    DISPUTE_STATUS_REJECTED,
})


def validate_deal_transition(current: str, next_status: str) -> None:
    """校验交易状态转换是否合法"""
    allowed = DEAL_STATUS_TRANSITIONS.get(current, set())
    if next_status not in allowed:
        raise ValueError(
            f"非法状态转换: {current} → {next_status} "
            f"(允许: {', '.join(sorted(allowed)) or '无'})"
        )


# ============================================================
# ORM 模型
# ============================================================


class Deal(Base):
    """交易保障主表"""

    __tablename__ = "escrow_deals"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="买方用户ID")
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="卖方用户ID")
    amount = Column(Float, nullable=False, default=0.0, comment="交易金额")
    status = Column(String(20), nullable=False, default=DEAL_STATUS_PENDING, index=True, comment="交易状态")
    title = Column(String(255), nullable=False, default="", comment="交易标题/商品名称")
    description = Column(Text, nullable=True, comment="交易描述")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])
    milestones: Mapped[List["Milestone"]] = relationship(
        "Milestone", back_populates="deal", cascade="all, delete-orphan"
    )
    disputes: Mapped[List["Dispute"]] = relationship(
        "Dispute", back_populates="deal", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "amount": self.amount,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "milestones": [m.to_dict() for m in (self.milestones or [])],
            "disputes": [d.to_dict() for d in (self.disputes or [])],
        }


class Milestone(Base):
    """里程碑追踪"""

    __tablename__ = "escrow_milestones"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    deal_id = Column(Integer, ForeignKey("escrow_deals.id"), nullable=False, index=True, comment="关联交易ID")
    name = Column(String(200), nullable=False, comment="里程碑名称")
    description = Column(Text, nullable=True, comment="里程碑描述")
    status = Column(String(20), nullable=False, default=MILESTONE_STATUS_PENDING, comment="状态")
    due_date = Column(DateTime, nullable=True, comment="截止日期")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    # 关系
    deal: Mapped["Deal"] = relationship("Deal", back_populates="milestones")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "deal_id": self.deal_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class Dispute(Base):
    """争议处理"""

    __tablename__ = "escrow_disputes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    deal_id = Column(Integer, ForeignKey("escrow_deals.id"), nullable=False, index=True, comment="关联交易ID")
    initiator_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="发起人用户ID")
    reason = Column(String(500), nullable=False, comment="争议原因")
    description = Column(Text, nullable=True, comment="详细描述")
    status = Column(String(20), nullable=False, default=DISPUTE_STATUS_OPEN, comment="争议状态")
    evidence = Column(Text, nullable=True, comment="证据（JSON字符串，存文件链接/描述）")
    resolution = Column(Text, nullable=True, comment="解决结果")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    resolved_at = Column(DateTime, nullable=True, comment="解决时间")

    # 关系
    deal: Mapped["Deal"] = relationship("Deal", back_populates="disputes")
    initiator = relationship("User", foreign_keys=[initiator_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "deal_id": self.deal_id,
            "initiator_id": self.initiator_id,
            "reason": self.reason,
            "description": self.description,
            "status": self.status,
            "evidence": self.evidence,
            "resolution": self.resolution,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
