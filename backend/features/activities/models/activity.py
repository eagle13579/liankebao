"""
活动模型 (Activity Model)
=========================
迁移自旧版链客宝 backend/modules/activities/models/activity.py
适配修改:
  - 使用 chainke-full 的 app.database.Base
  - datetime.utcnow -> func.now() (与 chainke-full 约定一致)
  - 添加 __table_args__ 和 to_dict() 方法
  - 添加 is_deleted / deleted_at 字段 (软删除支持)
  - 添加 updated_at 字段 (与 chainke-full 其他模型一致)
  - 关系使用字符串懒加载
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Boolean, func
from sqlalchemy.orm import relationship

from app.database import Base


class Activity(Base):
    """联系人活动记录"""

    __tablename__ = "activities"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    contact_id = Column(
        Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True, comment="关联联系人ID"
    )
    action_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="活动类型: note/call/meeting/email/wechat/order/import",
    )
    summary = Column(String(200), comment="活动概要")
    detail = Column(Text, comment="活动详情")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="创建人ID")
    is_deleted = Column(Boolean, default=False, index=True, comment="软删除标记")
    deleted_at = Column(DateTime, nullable=True, comment="删除时间")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系 (字符串懒加载)
    contact = relationship("Contact", back_populates="activities")
    owner = relationship("User", foreign_keys=[owner_id])

    def __repr__(self) -> str:
        return f"<Activity(id={self.id}, contact_id={self.contact_id}, action_type='{self.action_type}')>"

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "action_type": self.action_type,
            "summary": self.summary,
            "detail": self.detail,
            "owner_id": self.owner_id,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
