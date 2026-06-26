"""链客宝 — 信任评分数据模型
=================================
信任评分系统核心模型，支持基于三塔 DNN 的信任评分方案。

模型:
  TrustScore        — ORM 模型，用户信任评分主表
  BehaviorPoint     — ORM 模型，行为积分流水
  TrustGuarantee    — ORM 模型，担保关系

信任等级:
  bronze    (0-300)
  silver    (301-500)
  gold      (501-700)
  platinum  (701-1000)

设计约束:
  - user_id 使用 String(64) 关联，不使用 ForeignKey
  - 所有表通过 extend_existing=True 支持热重载
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from app.database import Base

logger = logging.getLogger(__name__)


# ============================================================
# 信任等级常量
# ============================================================

TIER_BRONZE = "bronze"      # 0-300
TIER_SILVER = "silver"      # 301-500
TIER_GOLD = "gold"          # 501-700
TIER_PLATINUM = "platinum"  # 701-1000

VALID_TIERS = frozenset({TIER_BRONZE, TIER_SILVER, TIER_GOLD, TIER_PLATINUM})

# 担保状态
GUARANTEE_STATUS_PENDING = "pending"
GUARANTEE_STATUS_ACTIVE = "active"
GUARANTEE_STATUS_EXPIRED = "expired"
GUARANTEE_STATUS_REVOKED = "revoked"

VALID_GUARANTEE_STATUSES = frozenset(
    {GUARANTEE_STATUS_PENDING, GUARANTEE_STATUS_ACTIVE,
     GUARANTEE_STATUS_EXPIRED, GUARANTEE_STATUS_REVOKED}
)


def get_trust_tier(score: float) -> str:
    """根据分数返回信任等级"""
    if score <= 300:
        return TIER_BRONZE
    elif score <= 500:
        return TIER_SILVER
    elif score <= 700:
        return TIER_GOLD
    else:
        return TIER_PLATINUM


# ============================================================
# ORM 模型
# ============================================================


class TrustScore(Base):
    """用户信任评分主表

    存储用户从三个维度计算的总信任评分:
      - verification_points: 认证积分（实名/企业认证等）
      - behavior_points:     行为积分（交易/评价/活跃度）
      - guarantee_points:    担保积分（背书关系网络）
    """

    __tablename__ = "trust_scores"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, unique=True, comment="用户 ID")

    total_score = Column(Float, nullable=False, default=0.0, comment="信任总分")
    tier = Column(String(20), nullable=False, default=TIER_BRONZE, comment="信任等级")

    # 三个维度分值
    verification_points = Column(Float, nullable=False, default=0.0, comment="认证积分")
    behavior_points = Column(Float, nullable=False, default=0.0, comment="行为积分")
    guarantee_points = Column(Float, nullable=False, default=0.0, comment="担保积分")

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="最后更新时间")

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "total_score": self.total_score,
            "tier": self.tier,
            "verification_points": self.verification_points,
            "behavior_points": self.behavior_points,
            "guarantee_points": self.guarantee_points,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BehaviorPoint(Base):
    """行为积分流水

    记录用户每次行为积分变化，包含来源追踪和描述信息。
    每条记录代表一次加分或扣分操作。
    """

    __tablename__ = "behavior_points"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, comment="用户 ID")
    source = Column(String(64), nullable=False, comment="积分来源 (如 trade/review/referral)")
    points = Column(Float, nullable=False, default=0.0, comment="积分变动值（正为加分，负为扣分）")
    description = Column(Text, nullable=True, comment="变动描述/原因")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "source": self.source,
            "points": self.points,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TrustGuarantee(Base):
    """担保关系

    用户之间通过担保关系建立信任背书网络。
    担保人 (guarantor_id) 为被担保人 (guarantee_id) 提供信用背书。
    weight 表示担保权重，影响担保积分计算。
    """

    __tablename__ = "trust_guarantees"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    guarantor_id = Column(String(64), nullable=False, index=True, comment="担保人用户 ID")
    guarantee_id = Column(String(64), nullable=False, index=True, comment="被担保人用户 ID")
    status = Column(String(20), nullable=False, default=GUARANTEE_STATUS_PENDING, comment="担保状态")
    weight = Column(Float, nullable=False, default=1.0, comment="担保权重 (0.0~1.0)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    expired_at = Column(DateTime, nullable=True, comment="过期时间")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "guarantor_id": self.guarantor_id,
            "guarantee_id": self.guarantee_id,
            "status": self.status,
            "weight": self.weight,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expired_at": self.expired_at.isoformat() if self.expired_at else None,
        }
