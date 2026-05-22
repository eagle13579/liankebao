"""充值模块 — SQLAlchemy ORM 数据模型"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric, BigInteger, ForeignKey,
    UniqueConstraint, Index, Text, DECIMAL
)
from sqlalchemy.orm import relationship

from app.database import Base


class UserBalance(Base):
    """用户余额模型（含乐观锁）"""
    __tablename__ = "user_balances"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    balance = Column(DECIMAL(12, 2), nullable=False, default=0.00, comment="当前余额")
    total_recharged = Column(DECIMAL(12, 2), nullable=False, default=0.00, comment="累计充值")
    total_consumed = Column(DECIMAL(12, 2), nullable=False, default=0.00, comment="累计消费")
    frozen_amount = Column(DECIMAL(12, 2), nullable=False, default=0.00, comment="冻结金额")
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    user = relationship("User", foreign_keys=[user_id])


class RechargeOrder(Base):
    """充值订单模型"""
    __tablename__ = "recharge_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True, comment="充值单号（RC前缀）")
    amount = Column(DECIMAL(12, 2), nullable=False, comment="充值金额（元）")
    platform = Column(String(10), nullable=False, default="wxpay", comment="支付平台: wxpay/alipay")
    prepay_id = Column(String(128), nullable=True, comment="微信预支付ID")
    status = Column(String(20), nullable=False, default="pending",
                    comment="订单状态: pending/paid/cancelled/refunded")
    paid_at = Column(DateTime, nullable=True, comment="支付完成时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    user = relationship("User", foreign_keys=[user_id])


class BalanceLog(Base):
    """余额流水模型"""
    __tablename__ = "balance_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(DECIMAL(12, 2), nullable=False, comment="变动金额（正数）")
    balance_before = Column(DECIMAL(12, 2), nullable=False, comment="变动前余额")
    balance_after = Column(DECIMAL(12, 2), nullable=False, comment="变动后余额")
    direction = Column(String(10), nullable=False, comment="方向: IN(收入)/OUT(支出)")
    biz_type = Column(String(20), nullable=False,
                      comment="业务类型: recharge/consume/refund/adjust/grant")
    biz_id = Column(String(128), nullable=True, comment="关联业务ID（如订单号、充值单号）")
    remark = Column(String(500), nullable=True, comment="备注说明")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_balance_logs_user_time", "user_id", "created_at"),
    )
