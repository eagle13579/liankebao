"""工作流引擎的SQLAlchemy ORM模型"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from app.database import Base
from .core import NodeType, WorkflowStatus


class WorkflowDefinitionModel(Base):
    """工作流定义持久化模型"""
    __tablename__ = "workflow_definitions"
    
    id = Column(String(36), primary_key=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, default="")
    nodes_json = Column(JSON, nullable=False, default=list)  # WorkflowNode列表
    edges_json = Column(JSON, nullable=False, default=list)  # WorkflowEdge列表
    tags = Column(JSON, default=list)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    instances = relationship("WorkflowInstanceModel", back_populates="definition", cascade="all, delete-orphan")


class WorkflowNodeModel(Base):
    """工作流节点定义（可选持久化，也可内嵌在WorkflowDefinitionModel中）"""
    __tablename__ = "workflow_nodes"
    
    id = Column(String(36), primary_key=True)
    workflow_id = Column(String(36), ForeignKey("workflow_definitions.id"), nullable=False)
    type = Column(String(20), nullable=False)  # NodeType
    label = Column(String(200), nullable=False)
    config = Column(JSON, default=dict)
    position_x = Column(Float, default=0)
    position_y = Column(Float, default=0)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkflowInstanceModel(Base):
    """工作流实例持久化模型"""
    __tablename__ = "workflow_instances"
    
    id = Column(String(36), primary_key=True)
    workflow_id = Column(String(36), ForeignKey("workflow_definitions.id"), nullable=False, index=True)
    status = Column(String(20), default=WorkflowStatus.PENDING.value, index=True)
    current_node_id = Column(String(36), nullable=True)
    context = Column(JSON, default=dict)
    node_statuses = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    definition = relationship("WorkflowDefinitionModel", back_populates="instances")
