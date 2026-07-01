"""盖娅进化大脑 — 数据模型

Four tables:
- gaia_knowledge: 进化知识库（复盘提炼、反馈学习、A/B测试产出的知识）
- gaia_evolution_events: 进化事件日志（全链路追踪）
- gaia_training_runs: 模型训练记录
- gaia_model_weights: 当前进化后的模型参数
"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, DateTime, JSON, Boolean, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GaiaKnowledge(Base):
    """进化知识库 — 存储复盘提炼、反馈学习、A/B测试产出的知识条目"""

    __tablename__ = "gaia_knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="知识来源: retrospective | feedback | ab_test | manual | system",
    )
    source_id: Mapped[str] = mapped_column(
        String(64), nullable=True, default="",
        comment="来源标识（如复盘ID、反馈ID、实验ID）",
    )
    knowledge_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="知识类型: insight | pattern | rule | preference | behavior | optimization",
    )
    title: Mapped[str] = mapped_column(
        String(256), nullable=False, default="",
        comment="知识标题",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
        comment="知识详细内容",
    )
    tags: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="标签（JSON数组: [\"标签1\", \"标签2\"]）",
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0,
        comment="置信度 0.0 ~ 1.0",
    )
    impact_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="影响评分，用于知识权重排序",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="是否激活（软删除标记）",
    )
    vector_embedded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="是否已向量化",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_gaia_knowledge_source", "source", "source_id"),
        Index("idx_gaia_knowledge_type", "knowledge_type", "confidence"),
        Index("idx_gaia_knowledge_active", "is_active", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<GaiaKnowledge id={self.id} source={self.source!r} "
            f"type={self.knowledge_type!r} confidence={self.confidence}>"
        )


class GaiaEvolutionEvent(Base):
    """进化事件日志 — 全链路追踪系统进化过程中的所有事件"""

    __tablename__ = "gaia_evolution_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="事件类型: knowledge_ingested | feedback_recorded | cycle_started | cycle_completed | "
                "weights_updated | training_started | training_completed | training_failed",
    )
    event_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="system",
        comment="事件来源: api | scheduler | manual | internal",
    )
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="",
        comment="事件描述",
    )
    event_meta: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True, default=None,
        comment="事件元数据（JSON，存储上下文信息）",
    )
    reference_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None,
        comment="关联对象类型: knowledge | feedback | training_run | weights",
    )
    reference_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
        comment="关联对象ID",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True,
        comment="事件发生时间",
    )

    __table_args__ = (
        Index("idx_gaia_event_type_time", "event_type", "created_at"),
        Index("idx_gaia_event_ref", "reference_type", "reference_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<GaiaEvolutionEvent id={self.id} type={self.event_type!r} "
            f"source={self.event_source!r}>"
        )


class GaiaTrainingRun(Base):
    """模型训练记录 — 记录每次进化训练的全过程"""

    __tablename__ = "gaia_training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True,
        comment="状态: pending | running | completed | failed",
    )
    trigger: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual",
        comment="触发方式: manual | scheduled | automatic | api",
    )
    knowledge_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="本次训练使用的知识条目数",
    )
    feedback_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="本次训练使用的反馈条目数",
    )
    weights_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="本次训练更新的权重数",
    )
    vector_index_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="向量索引条目数",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="训练耗时（毫秒）",
    )
    metrics: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="训练指标（JSON: {\"accuracy\": 0.95, \"coverage\": 0.8, ...}）",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None,
        comment="错误信息（失败时记录）",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None,
        comment="训练开始时间",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None,
        comment="训练完成时间",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_gaia_training_status", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<GaiaTrainingRun id={self.id} status={self.status!r} "
            f"trigger={self.trigger!r}>"
        )


class GaiaModelWeights(Base):
    """当前进化后的模型参数 — 供其他服务查询进化后的权重"""

    __tablename__ = "gaia_model_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="模块标识: recommendation | search | extractor | writing | optimization | rag | knowledge_graph",
    )
    weights: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
        comment="权重字典（JSON, 结构因模块而异）",
    )
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1.0.0",
        comment="权重版本号",
    )
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="",
        comment="版本变更说明",
    )
    training_run_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
        comment="关联的训练记录ID",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="是否为当前活跃版本",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_gaia_weights_module_active", "module", "is_active", "version"),
    )

    def __repr__(self) -> str:
        return (
            f"<GaiaModelWeights id={self.id} module={self.module!r} "
            f"version={self.version!r} active={self.is_active}>"
        )
