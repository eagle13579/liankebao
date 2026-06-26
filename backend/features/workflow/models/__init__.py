"""
工作流模块 - 数据模型

数据模型适配到 chainke-full 的 Base (SQLAlchemy ORM)
"""
from features.workflow.models.deal import Deal
from features.workflow.models.event import Event

__all__ = ["Deal", "Event"]
