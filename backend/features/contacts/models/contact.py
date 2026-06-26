"""
联系人模型 (Contact Model)
==========================
迁移自旧版链客宝 backend/modules/contacts/models/contact.py
适配修改:
  - 使用 chainke-full 的 app.database.Base
  - datetime.utcnow -> func.now() (与 chainke-full 约定一致)
  - 添加 __table_args__ 和 to_dict() 方法
  - 添加 is_deleted / deleted_at 字段 (旧路由软删除必需)
  - 关系使用字符串懒加载 (与其他模型模式一致)
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Contact(Base):
    """人脉/联系人"""

    __tablename__ = "contacts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True, comment="联系人姓名")
    phone = Column(String(20), index=True, comment="手机号")
    wechat_id = Column(String(100), comment="微信号")
    company = Column(String(200), comment="公司")
    position = Column(String(100), comment="职位")
    email = Column(String(100), comment="邮箱")
    notes = Column(Text, comment="备注")
    tags = Column(String(500), comment="标签(逗号分隔)")
    source = Column(String(50), default="manual", comment="来源: manual/import/wechat/seed")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="所属用户ID")
    is_deleted = Column(Boolean, default=False, index=True, comment="软删除标记")
    deleted_at = Column(DateTime, nullable=True, comment="删除时间")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系 (字符串懒加载)
    owner = relationship("User", foreign_keys=[owner_id])
    activities = relationship("Activity", back_populates="contact", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Contact(id={self.id}, name='{self.name}')>"

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "wechat_id": self.wechat_id,
            "company": self.company,
            "position": self.position,
            "email": self.email,
            "notes": self.notes,
            "tags": self.tags,
            "source": self.source,
            "owner_id": self.owner_id,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
