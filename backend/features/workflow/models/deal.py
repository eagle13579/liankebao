"""
Deal/商机模型 - 工作流引擎专用

链客宝现有的 BusinessNeed 模型偏向"需求发布"场景，
Deal 模型更贴近 CRM 销售漏斗管道的概念，包含阶段(stage)流转。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base


class Deal(Base):
    """销售商机/Deal - CRM 管道核心"""

    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True, comment="商机标题")
    description = Column(Text, comment="商机描述")
    stage = Column(
        String(30),
        default="qualification",
        index=True,
        comment="阶段: qualification/meeting/proposal/negotiation/closed_won/closed_lost",
    )
    amount = Column(Float, default=0.0, comment="预计金额")
    probability = Column(Integer, default=10, comment="成交概率 0-100")
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True, comment="关联联系人ID")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="负责人ID")
    tags = Column(String(500), comment="标签(逗号分隔)")
    stage_entered_at = Column(DateTime, default=datetime.utcnow, comment="进入当前阶段的时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __repr__(self):
        return f"<Deal(id={self.id}, title='{self.title}', stage='{self.stage}')>"
