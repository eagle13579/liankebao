"""
事件日志模型 - 记录所有系统内事件，供工作流引擎订阅
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class Event(Base):
    """系统事件日志 - 工作流引擎触发器的事件源"""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="事件类型: deal.created / deal.stage_changed / contact.added / order.paid / activity.logged",
    )
    entity_type = Column(String(30), index=True, comment="关联实体类型: deal / contact / order / product / activity")
    entity_id = Column(Integer, index=True, comment="关联实体ID")
    data = Column(Text, comment="事件载荷(JSON)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="事件发生时间")

    def __repr__(self):
        return f"<Event(id={self.id}, type='{self.event_type}', entity={self.entity_type}:{self.entity_id})>"
