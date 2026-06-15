"""
推广员提现模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Withdrawal(Base):
    """提现申请"""

    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="推广员ID")
    amount = Column(Float, nullable=False, comment="提现金额")
    bank_info = Column(String(500), comment="收款信息(JSON)")
    status = Column(
        String(20), default="pending", index=True, comment="状态: pending/approved/rejected"
    )
    review_note = Column(String(500), comment="审核备注")
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="审核人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    user = relationship("User", back_populates="withdrawals")

    def __repr__(self):
        return f"<Withdrawal(id={self.id}, user_id={self.user_id}, amount={self.amount}, status='{self.status}')>"
