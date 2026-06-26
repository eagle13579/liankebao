"""
订单模型 (Order Model)
======================
迁移自旧版链客宝 backend/modules/orders/models/order.py
适配修改:
  - 移除 Product 关系引用 (chainke-full 中无 Product ORM 模型)
  - 保留 User 关系引用 (与其他模型一致)
  - 添加 __table_args__ 和 to_dict() 方法
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Order(Base):
    """交易订单"""

    __tablename__ = "orders"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_no = Column(String(50), unique=True, index=True, nullable=False, comment="订单号")
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True, comment="产品ID")
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="买家ID")
    supplier_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="供应商ID")
    promoter_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="推广员ID")
    quantity = Column(Integer, default=1, comment="数量")
    total_price = Column(Float, nullable=False, comment="总价")
    status = Column(
        String(20),
        default="pending",
        index=True,
        comment="状态: pending/paid/shipped/received/cancelled/refunded",
    )
    contact_name = Column(String(100), comment="收货人姓名")
    contact_phone = Column(String(20), comment="收货人电话")
    shipping_address = Column(String(500), comment="收货地址")
    note = Column(Text, comment="订单备注")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    buyer = relationship("User", foreign_keys=[buyer_id])
    supplier = relationship("User", foreign_keys=[supplier_id])

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, order_no='{self.order_no}', status='{self.status}')>"

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "order_no": self.order_no,
            "product_id": self.product_id,
            "buyer_id": self.buyer_id,
            "supplier_id": self.supplier_id,
            "promoter_id": self.promoter_id,
            "quantity": self.quantity,
            "total_price": self.total_price,
            "status": self.status,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "shipping_address": self.shipping_address,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
