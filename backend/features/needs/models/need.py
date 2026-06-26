"""
商业需求模型 (BusinessNeed Model)
==================================
迁移自旧版链客宝 backend/modules/needs/models/need.py
适配修改:
  - 使用 chainke-full 的 app.database.Base
  - datetime.utcnow -> func.now() (与 chainke-full 约定一致)
  - 添加 __table_args__ 和 to_dict() 方法
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class BusinessNeed(Base):
    """商机/商业需求"""

    __tablename__ = "business_needs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
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
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系 (字符串懒加载)
    owner = relationship("User", foreign_keys=[owner_id])

    def __repr__(self) -> str:
        return f"<BusinessNeed(id={self.id}, title='{self.title}', status='{self.status}')>"

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "budget": self.budget,
            "status": self.status,
            "owner_id": self.owner_id,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
