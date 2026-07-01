"""盖娅进化大脑 — FastAPI 路由

提供知识摄取、进化控制、权重查询等 API 端点。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_db
from app.ai.gaia_evolution_brain import get_gaia_brain, GaiaEvolutionBrain
from app.ai.gaia_trainer import get_gaia_trainer, GaiaTrainer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gaia", tags=["盖娅进化大脑"])


# ======================================================================
# Pydantic Schemas
# ======================================================================


class KnowledgeIngestRequest(BaseModel):
    """知识摄取请求"""
    source: str = Field(
        ..., description="知识来源: retrospective | feedback | ab_test | manual | system",
    )
    source_id: str = Field("", description="来源标识")
    knowledge_type: str = Field(
        ..., description="知识类型: insight | pattern | rule | preference | behavior | optimization",
    )
    title: str = Field(..., description="知识标题")
    content: str = Field(..., description="知识详细内容")
    tags: list[str] | None = Field(None, description="标签列表")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="置信度 0.0 ~ 1.0")


class FeedbackIngestRequest(BaseModel):
    """反馈摄取请求"""
    user_id: int = Field(..., description="用户 ID")
    item_id: int = Field(..., description="评价对象 ID")
    rating: float = Field(..., ge=1.0, le=5.0, description="评分")
    source: str = Field("recommendation", description="来源")
    comment: str | None = Field(None, description="评语")


class EvolutionTriggerRequest(BaseModel):
    """进化触发请求"""
    trigger: str = Field("api", description="触发方式: manual | scheduled | automatic | api")


# ======================================================================
# 知识管理
# ======================================================================


@router.post("/knowledge")
async def ingest_knowledge(
    data: KnowledgeIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """摄取一条进化知识（来自复盘、反馈、A/B测试等来源）"""
    brain = get_gaia_brain()
    knowledge = await brain.ingest_knowledge(
        db=db,
        source=data.source,
        source_id=data.source_id,
        knowledge_type=data.knowledge_type,
        title=data.title,
        content=data.content,
        tags=data.tags,
        confidence=data.confidence,
    )
    return {
        "code": 200,
        "message": "知识已摄取",
        "data": {
            "id": knowledge.id,
            "source": knowledge.source,
            "knowledge_type": knowledge.knowledge_type,
            "title": knowledge.title,
            "confidence": knowledge.confidence,
        },
    }


@router.get("/knowledge")
async def query_knowledge(
    query: str = Query(..., description="检索查询文本"),
    limit: int = Query(10, ge=1, le=100, description="返回结果数量上限"),
    knowledge_type: str | None = Query(None, description="按知识类型过滤"),
    source: str | None = Query(None, description="按来源过滤"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="最低置信度"),
    db: AsyncSession = Depends(get_db),
):
    """语义检索知识库（向量搜索 + 关键词回退）"""
    brain = get_gaia_brain()
    results = await brain.get_knowledge_base(
        db=db,
        query=query,
        limit=limit,
        knowledge_type=knowledge_type,
        source=source,
        min_confidence=min_confidence,
    )
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "items": results,
            "total": len(results),
        },
    }


@router.post("/feedback")
async def ingest_feedback(
    data: FeedbackIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """摄取用户反馈（极端评分自动转化为进化知识）"""
    brain = get_gaia_brain()
    knowledge = await brain.ingest_feedback(
        db=db,
        user_id=data.user_id,
        item_id=data.item_id,
        rating=data.rating,
        source=data.source,
        comment=data.comment,
    )
    return {
        "code": 200,
        "message": "反馈已记录" + (" 并生成知识" if knowledge else ""),
        "data": {
            "knowledge_generated": knowledge is not None,
            "knowledge_id": knowledge.id if knowledge else None,
        },
    }


# ======================================================================
# 进化控制
# ======================================================================


@router.get("/evolution/status")
async def get_evolution_status(
    db: AsyncSession = Depends(get_db),
):
    """获取进化大脑状态概览"""
    brain = get_gaia_brain()
    status = await brain.get_status(db)
    return {
        "code": 200,
        "message": "ok",
        "data": status,
    }


@router.post("/evolution/trigger")
async def trigger_evolution(
    data: EvolutionTriggerRequest = EvolutionTriggerRequest(),
    db: AsyncSession = Depends(get_db),
):
    """手动触发一次进化循环

    执行知识聚合、向量化、权重更新全链路。
    """
    brain = get_gaia_brain()
    result = await brain.process_evolution_cycle(db, trigger=data.trigger)
    status_code = 200 if result.get("status") == "completed" else 500
    return {
        "code": status_code,
        "message": "进化循环" + ("完成" if result.get("status") == "completed" else "失败"),
        "data": result,
    }


@router.post("/training/trigger")
async def trigger_training(
    trigger: str = Query("api", description="触发方式: manual | scheduled | automatic"),
    db: AsyncSession = Depends(get_db),
):
    """手动触发一次完整训练管线

    执行: 数据收集 → 向量索引更新 → 权重计算 → 权重部署。
    比进化循环更深入，执行权重部署到数据库。
    """
    trainer = get_gaia_trainer()
    result = await trainer.run_training_cycle(db, trigger=trigger)
    status_code = 200 if result.get("status") == "completed" else 500
    return {
        "code": status_code,
        "message": "训练管线" + ("完成" if result.get("status") == "completed" else "失败"),
        "data": result,
    }


# ======================================================================
# 权重查询
# ======================================================================


@router.get("/weights/{module}")
async def get_evolved_weights(
    module: str,
    db: AsyncSession = Depends(get_db),
):
    """获取指定模块的当前进化权重

    可用模块: recommendation | search | extractor | writing | optimization | rag | knowledge_graph
    """
    valid_modules = {
        "recommendation", "search", "extractor",
        "writing", "optimization", "rag", "knowledge_graph",
    }
    if module not in valid_modules:
        raise HTTPException(
            status_code=400,
            detail=f"无效的模块名: {module}，可用: {', '.join(sorted(valid_modules))}",
        )

    brain = get_gaia_brain()
    weights = await brain.get_evolved_weights(db, module=module)
    if weights is None:
        return {
            "code": 404,
            "message": f"模块 {module} 暂无进化权重",
            "data": None,
        }
    return {
        "code": 200,
        "message": "ok",
        "data": weights,
    }


# ======================================================================
# 事件与训练记录
# ======================================================================


@router.get("/events")
async def list_events(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数"),
    event_type: str | None = Query(None, description="事件类型过滤"),
    db: AsyncSession = Depends(get_db),
):
    """列出进化事件日志（分页，按时间倒序）"""
    brain = get_gaia_brain()
    items, total = await brain.get_events(
        db=db,
        page=page,
        page_size=page_size,
        event_type=event_type,
    )
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/training-runs")
async def list_training_runs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数"),
    status: str | None = Query(None, description="训练状态过滤: pending | running | completed | failed"),
    db: AsyncSession = Depends(get_db),
):
    """列出训练运行记录（分页，按时间倒序）"""
    brain = get_gaia_brain()
    items, total = await brain.get_training_runs(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
    )
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
