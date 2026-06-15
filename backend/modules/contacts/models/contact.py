"""
联系人模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Contact(Base):
    """人脉/联系人"""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True, comment="联系人姓名")
    phone = Column(String(20), index=True, comment="手机号")
    wechat_id = Column(String(100), comment="微信号")
    company = Column(String(200), comment="公司")
    position = Column(String(100), comment="职位")
    email = Column(String(100), comment="邮箱")
    notes = Column(Text, comment="备注")
    tags = Column(String(500), comment="标签(逗号分隔)")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="所属用户ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    owner = relationship("User", back_populates="contacts")
    activities = relationship("Activity", back_populates="contact", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Contact(id={self.id}, name='{self.name}')>"
