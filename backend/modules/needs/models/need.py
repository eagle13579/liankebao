"""
商业需求模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class BusinessNeed(Base):
    """商机/商业需求"""

    __tablename__ = "business_needs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True, comment="需求标题")
    description = Column(Text, comment="需求描述")
    category = Column(String(100), index=True, comment="需求分类")
    budget = Column(Float, comment="预算金额")
    status = Column(
        String(20),
        default="open",
        index=True,
        comment="状态: open/responding/closed/fulfilled",
    )
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="发布人ID")
    contact_name = Column(String(100), comment="联系人姓名")
    contact_phone = Column(String(20), comment="联系人电话")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    owner = relationship("User", back_populates="needs")

    def __repr__(self):
        return f"<BusinessNeed(id={self.id}, title='{self.title}', status='{self.status}')>"
