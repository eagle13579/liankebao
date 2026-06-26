"""链客宝 — 用户反馈数据模型（自进化闭环 P0）
==============================================
反馈采集管道核心模型，用于收集用户对系统的反馈，形成自进化闭环。

模型:
  Feedback         — ORM 模型，存储单条反馈记录
  FeedbackStats    — 聚合统计值对象
  FeedbackCategory — 反馈分类枚举
  FeedbackStatus   — 反馈状态枚举

表: feedbacks

字段:
  id         - 主键自增 ID
  user_id    - 反馈用户 ID
  category   - 分类: bug / feature / improvement / other
  message    - 反馈文本内容（必填）
  rating     - 评分 1-5（可选）
  page_url   - 页面 URL（可选，记录来源页面）
  status     - 处理状态: pending / acknowledged / resolved / closed
  created_at - 创建时间
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, func, Enum as SAEnum
from app.database import Base

import enum


class FeedbackCategory(str, enum.Enum):
    """反馈分类枚举"""
    BUG = "bug"
    FEATURE = "feature"
    IMPROVEMENT = "improvement"
    OTHER = "other"


class FeedbackStatus(str, enum.Enum):
    """反馈处理状态枚举"""
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Feedback(Base):
    """用户反馈记录"""
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, comment="反馈用户ID")
    category = Column(
        SAEnum(FeedbackCategory, name="feedback_category_enum", create_constraint=True),
        nullable=False,
        default=FeedbackCategory.OTHER,
        comment="反馈分类: bug/feature/improvement/other",
    )
    message = Column(Text, nullable=False, comment="反馈文本内容")
    rating = Column(Integer, nullable=True, comment="评分 (1-5)")
    page_url = Column(String(1024), nullable=True, comment="来源页面 URL")
    status = Column(
        SAEnum(FeedbackStatus, name="feedback_status_enum", create_constraint=True),
        nullable=False,
        default=FeedbackStatus.PENDING,
        comment="处理状态: pending/acknowledged/resolved/closed",
    )
    created_at = Column(DateTime, default=func.now(), comment="创建时间")

    def __repr__(self):
        return (
            f"<Feedback(id={self.id}, user={self.user_id}, "
            f"category={self.category}, status={self.status})>"
        )

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category.value if isinstance(self.category, enum.Enum) else self.category,
            "message": self.message,
            "rating": self.rating,
            "page_url": self.page_url,
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FeedbackStats:
    """反馈聚合统计结果（值对象，非 ORM 映射）

    由统计查询构造，包含:
      total_count         - 反馈总数
      category_distribution - 按分类分布 { "bug": N, "feature": N, ... }
      avg_rating          - 平均评分（仅含评分记录）
      rating_distribution - 评分分布 { 1: N, 2: N, ..., 5: N }
      status_distribution - 按状态分布 { "pending": N, ... }
      trend               - 按日期趋势 { "2025-01-01": N, ... }
    """

    def __init__(
        self,
        total_count: int = 0,
        category_distribution: dict[str, int] = None,
        avg_rating: float = 0.0,
        rating_distribution: dict[int, int] = None,
        status_distribution: dict[str, int] = None,
        trend: dict[str, int] = None,
    ):
        self.total_count = total_count
        self.category_distribution = category_distribution or {}
        self.avg_rating = round(avg_rating, 2)
        self.rating_distribution = rating_distribution or {}
        self.status_distribution = status_distribution or {}
        self.trend = trend or {}

    def to_dict(self) -> dict:
        return {
            "total_count": self.total_count,
            "category_distribution": self.category_distribution,
            "avg_rating": self.avg_rating,
            "rating_distribution": self.rating_distribution,
            "status_distribution": self.status_distribution,
            "trend": self.trend,
        }
