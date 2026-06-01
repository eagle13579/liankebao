"""
用户模型
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """用户账号"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    name = Column(String(100), comment="姓名/昵称")
    role = Column(String(20), default="buyer", comment="角色: buyer/supplier/promoter/admin")
    phone = Column(String(20), comment="手机号")
    email = Column(String(100), comment="邮箱")
    avatar = Column(String(255), comment="头像URL")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    products = relationship("Product", back_populates="owner", lazy="dynamic")
    orders_as_buyer = relationship(
        "Order", back_populates="buyer", foreign_keys="Order.buyer_id", lazy="dynamic"
    )
    orders_as_supplier = relationship(
        "Order", back_populates="supplier", foreign_keys="Order.supplier_id", lazy="dynamic"
    )
    contacts = relationship("Contact", back_populates="owner", lazy="dynamic")
    activities = relationship("Activity", back_populates="owner", lazy="dynamic")
    needs = relationship("BusinessNeed", back_populates="owner", lazy="dynamic")
    withdrawals = relationship("Withdrawal", back_populates="user", lazy="dynamic")
    import_histories = relationship("ImportHistory", back_populates="user", lazy="dynamic")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
