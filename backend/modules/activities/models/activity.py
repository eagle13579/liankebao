"""
联系人活动模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Activity(Base):
    """联系人活动记录"""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关系
    contact = relationship("Contact", back_populates="activities")
    owner = relationship("User", back_populates="activities")

    def __repr__(self):
        return f"<Activity(id={self.id}, contact_id={self.contact_id}, action_type='{self.action_type}')>"
