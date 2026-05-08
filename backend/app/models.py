"""SQLAlchemy ORM 数据模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    company = Column(String(200), nullable=True)
    position = Column(String(100), nullable=True)
    role = Column(String(20), nullable=False, default="buyer")  # buyer/promoter/supplier/admin
    avatar = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    products = relationship("Product", back_populates="owner", foreign_keys="Product.owner_id")
    orders = relationship("Order", back_populates="user", foreign_keys="Order.user_id")
    promoter_orders = relationship("Order", back_populates="promoter", foreign_keys="Order.promoter_id")
    withdrawals = relationship("Withdrawal", back_populates="user")


class Product(Base):
    """产品模型"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False, default=0.0)
    earn_per_share = Column(Float, nullable=False, default=0.0)  # 推广分润/每单
    category = Column(String(100), nullable=True)
    stock = Column(Integer, nullable=False, default=0)
    images = Column(Text, nullable=True)  # JSON数组字符串
    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    owner = relationship("User", back_populates="products", foreign_keys=[owner_id])
    orders = relationship("Order", back_populates="product")


class Order(Base):
    """订单模型"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    total_price = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="paid")  # paid/shipped/received/refunded
    promoter_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    commission = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="orders", foreign_keys=[user_id])
    product = relationship("Product", back_populates="orders")
    promoter = relationship("User", back_populates="promoter_orders", foreign_keys=[promoter_id])


class Withdrawal(Base):
    """提现模型"""
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    bank_info = Column(Text, nullable=True)  # JSON字符串: 银行信息
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="withdrawals")
