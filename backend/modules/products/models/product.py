"""
产品模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    """产品/商品"""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True, comment="产品名称")
    description = Column(Text, comment="产品描述")
    price = Column(Float, nullable=False, comment="单价")
    category = Column(String(100), index=True, comment="产品分类")
    images = Column(Text, comment="图片URL列表(JSON数组)")
    status = Column(
        String(20), default="pending", index=True, comment="状态: pending/approved/rejected/archived"
    )
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="供应商ID")
    review_note = Column(String(500), comment="审核备注")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    owner = relationship("User", back_populates="products")
    orders = relationship("Order", back_populates="product", lazy="dynamic")

    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.name}', price={self.price}, status='{self.status}')>"
