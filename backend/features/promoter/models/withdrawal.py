"""
推广员提现模型 (Withdrawal Model)
===================================
迁移自旧版链客宝 backend/modules/promoter/models/withdrawal.py
适配修改:
  - 使用 chainke-full 的 app.database.Base
  - datetime.utcnow -> func.now() (与 chainke-full 约定一致)
  - 添加 __table_args__ 和 to_dict() 方法
  - 保留 user 关系引用 (字符串懒加载，与 Product 模型模式一致)
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class Withdrawal(Base):
    """提现申请"""

    __tablename__ = "withdrawals"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="推广员ID")
    amount = Column(Float, nullable=False, comment="提现金额")
    bank_info = Column(String(500), comment="收款信息(JSON)")
    status = Column(
        String(20), default="pending", index=True, comment="状态: pending/approved/rejected"
    )
    review_note = Column(String(500), comment="审核备注")
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="审核人ID")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系 (字符串懒加载)
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<Withdrawal(id={self.id}, user_id={self.user_id}, amount={self.amount}, status='{self.status}')>"

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "bank_info": self.bank_info,
            "status": self.status,
            "review_note": self.review_note,
            "reviewed_by": self.reviewed_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
