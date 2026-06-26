"""
产品模型 (Product Model)
========================
迁移自旧版链客宝 backend/modules/products/models/product.py
适配修改:
  - 使用 chainke-full 的 app.database.Base
  - datetime.utcnow -> func.now() (与 chainke-full 约定一致)
  - 添加 __table_args__ 和 to_dict() 方法
  - 保留 owner 关系引用 (字符串懒加载，与 Order 模型模式一致)
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    """产品/商品"""

    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
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
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系 (字符串懒加载)
    owner = relationship("User", foreign_keys=[owner_id])

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', price={self.price}, status='{self.status}')>"

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        import json
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "category": self.category,
            "images": self.images,
            "status": self.status,
            "owner_id": self.owner_id,
            "review_note": self.review_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
