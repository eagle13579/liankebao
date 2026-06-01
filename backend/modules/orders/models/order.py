"""
订单模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Order(Base):
    """交易订单"""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    product = relationship("Product", back_populates="orders")
    buyer = relationship("User", back_populates="orders_as_buyer", foreign_keys=[buyer_id])
    supplier = relationship("User", back_populates="orders_as_supplier", foreign_keys=[supplier_id])

    def __repr__(self):
        return f"<Order(id={self.id}, order_no='{self.order_no}', status='{self.status}')>"
