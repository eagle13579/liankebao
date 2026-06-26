"""
链客宝 — 信任评分 API 路由
===============================
信任评分 RESTful API 接口。

端点:
  GET  /api/trust/score/{user_id}                     — 获取用户信任评分详情
  GET  /api/trust/score/{user_id}/breakdown           — 获取评分细分维度详情
  GET  /api/trust/behavior/{user_id}                  — 获取用户行为积分历史
  GET  /api/trust/network/{user_id}                   — 获取用户的担保网络
  POST /api/trust/guarantee                           — 创建担保关系
  PUT  /api/trust/guarantee/{guarantee_id}/confirm    — 确认担保
  PUT  /api/trust/guarantee/{guarantee_id}/revoke     — 撤销担保
  POST /api/trust/score/{user_id}/recalculate         — 重新计算信任评分
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.trust_score_models import BehaviorPoint
from app.services.trust_score_service import TrustScoreService

logger = logging.getLogger(__name__)

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/trust", tags=["信任评分"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================

class BehaviorPointResponse(BaseModel):
    """行为积分流水响应"""
    id: int
    user_id: str
    source: str
    points: float
    description: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class GuaranteeResponse(BaseModel):
    """担保关系响应"""
    id: int
    guarantor_id: str
    guarantee_id: str
    status: str
    weight: float
    created_at: Optional[str] = None
    expired_at: Optional[str] = None

    class Config:
        from_attributes = True


class TrustScoreDetailResponse(BaseModel):
    """信任评分详情响应"""
    user_id: str
    total_score: float
    tier: str
    tier_label: str = ""
    tier_icon: str = ""
    verification_points: float
    behavior_points: float
    guarantee_points: float
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class TrustNetworkResponse(BaseModel):
    """担保网络响应"""
    user_id: str
    as_guarantor: list[GuaranteeResponse]
    as_guarantee: list[GuaranteeResponse]
    total_score: float
    tier: str


class CreateGuaranteeRequest(BaseModel):
    """创建担保请求体"""
    guarantor_id: str = Field(..., description="担保人用户 ID")
    guarantee_id: str = Field(..., description="被担保人用户 ID")
    weight: float = Field(1.0, ge=0.0, le=1.0, description="担保权重 (0.0~1.0)")
    expired_at: Optional[str] = Field(None, description="过期时间 (ISO 格式，可选)")


class CreateGuaranteeResponse(BaseModel):
    """创建担保响应"""
    id: int
    guarantor_id: str
    guarantee_id: str
    status: str
    weight: float
    created_at: Optional[str] = None
    expired_at: Optional[str] = None
    message: str = "担保创建成功"


# ===================================================================
# GET /api/trust/score/{user_id} — 获取信任评分详情
# ===================================================================

@router.get("/score/{user_id}", response_model=TrustScoreDetailResponse)
async def get_trust_score(user_id: str, db: Session = Depends(get_db)):
    """获取用户信任评分详情

    返回用户的综合信任评分、等级及各维度分项得分。
    如果用户尚无评分记录，会触发一次计算。
    """
    service = TrustScoreService(db)
    from app.models.trust_score_models import TrustScore

    trust_score = (
        db.query(TrustScore)
        .filter(TrustScore.user_id == user_id)
        .first()
    )
    if trust_score is None:
        trust_score = service.calculate_trust_score(user_id)

    # 获取等级详细信息
    from features.trust_engine.tier import TrustTier
    tier_detail = TrustTier(trust_score.total_score)

    return TrustScoreDetailResponse(
        user_id=trust_score.user_id,
        total_score=trust_score.total_score,
        tier=trust_score.tier,
        tier_label=tier_detail.label_cn,
        tier_icon=tier_detail.icon,
        verification_points=trust_score.verification_points,
        behavior_points=trust_score.behavior_points,
        guarantee_points=trust_score.guarantee_points,
        updated_at=trust_score.updated_at.isoformat() if trust_score.updated_at else None,
    )


# ===================================================================
# GET /api/trust/score/{user_id}/breakdown — 获取评分细分维度详情
# ===================================================================

@router.get("/score/{user_id}/breakdown")
async def get_trust_score_breakdown(user_id: str, db: Session = Depends(get_db)):
    """获取用户信任评分细分维度详情

    返回三个维度的详细子指标得分，包含:
      - qualification: 认证可信度子指标
      - transaction: 行为可信度子指标（含时间衰减）
      - compliance: 担保可信度子指标
      - tier_detail: 等级详细信息
    """
    service = TrustScoreService(db)
    try:
        result = service.calculate_trust_score_with_details(user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评分计算失败: {str(e)}")


# ===================================================================
# GET /api/trust/behavior/{user_id} — 获取行为积分历史
# ===================================================================

@router.get("/behavior/{user_id}")
async def get_behavior_history(
    user_id: str,
    limit: int = Query(50, ge=1, le=500, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    source: Optional[str] = Query(None, description="按来源筛选"),
    db: Session = Depends(get_db),
):
    """获取用户的行为积分流水历史

    返回按时间倒序排列的行为积分记录，支持分页和来源筛选。
    """
    query = db.query(BehaviorPoint).filter(BehaviorPoint.user_id == user_id)

    if source:
        query = query.filter(BehaviorPoint.source == source)

    total = query.count()

    records = (
        query
        .order_by(BehaviorPoint.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "source_filter": source,
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "source": r.source,
                "points": r.points,
                "description": r.description,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }


# ===================================================================
# GET /api/trust/network/{user_id} — 获取担保网络
# ===================================================================

@router.get("/network/{user_id}", response_model=TrustNetworkResponse)
async def get_trust_network(user_id: str, db: Session = Depends(get_db)):
    """获取用户的担保网络

    返回该用户作为担保人和被担保人的所有活跃关系。
    """
    service = TrustScoreService(db)
    network = service.get_trust_network(user_id)
    return TrustNetworkResponse(**network)


# ===================================================================
# POST /api/trust/guarantee — 创建担保关系
# ===================================================================

@router.post("/guarantee", response_model=CreateGuaranteeResponse, status_code=201)
async def create_guarantee(req: CreateGuaranteeRequest, db: Session = Depends(get_db)):
    """创建一条担保关系

    担保人 (guarantor_id) 为被担保人 (guarantee_id) 提供信用背书。
    创建后状态为 pending，需调用确认接口转为 active 后生效。
    """
    service = TrustScoreService(db)

    expired_at = None
    if req.expired_at:
        try:
            expired_at = datetime.fromisoformat(req.expired_at)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"expired_at 格式无效: '{req.expired_at}'，请使用 ISO 8601 格式 (如 2026-12-31T23:59:59)",
            )

    try:
        guarantee = service.create_guarantee(
            guarantor_id=req.guarantor_id,
            guarantee_id=req.guarantee_id,
            weight=req.weight,
            expired_at=expired_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return CreateGuaranteeResponse(
        id=guarantee.id,
        guarantor_id=guarantee.guarantor_id,
        guarantee_id=guarantee.guarantee_id,
        status=guarantee.status,
        weight=guarantee.weight,
        created_at=guarantee.created_at.isoformat() if guarantee.created_at else None,
        expired_at=guarantee.expired_at.isoformat() if guarantee.expired_at else None,
    )


# ===================================================================
# PUT /api/trust/guarantee/{guarantee_id}/confirm — 确认担保
# ===================================================================

@router.put("/guarantee/{guarantee_id}/confirm")
async def confirm_guarantee(guarantee_id: int, db: Session = Depends(get_db)):
    """确认担保关系，将状态从 pending 变为 active"""
    service = TrustScoreService(db)
    try:
        guarantee = service.confirm_guarantee(guarantee_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "id": guarantee.id,
        "status": guarantee.status,
        "message": "担保已确认",
    }


# ===================================================================
# PUT /api/trust/guarantee/{guarantee_id}/revoke — 撤销担保
# ===================================================================

@router.put("/guarantee/{guarantee_id}/revoke")
async def revoke_guarantee(guarantee_id: int, db: Session = Depends(get_db)):
    """撤销担保关系"""
    service = TrustScoreService(db)
    try:
        guarantee = service.revoke_guarantee(guarantee_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "id": guarantee.id,
        "status": guarantee.status,
        "message": "担保已撤销",
    }


# ===================================================================
# POST /api/trust/score/{user_id}/recalculate — 重新计算信任评分
# ===================================================================

@router.post("/score/{user_id}/recalculate")
async def recalculate_trust_score(user_id: str, db: Session = Depends(get_db)):
    """触发重新计算用户的信任评分

    从三个维度重新聚合计算用户的信任总分并更新等级。
    """
    service = TrustScoreService(db)
    trust_score = service.calculate_trust_score(user_id)

    from features.trust_engine.tier import TrustTier
    tier_detail = TrustTier(trust_score.total_score)

    return {
        "user_id": trust_score.user_id,
        "total_score": trust_score.total_score,
        "tier": trust_score.tier,
        "tier_label": tier_detail.label_cn,
        "tier_icon": tier_detail.icon,
        "verification_points": trust_score.verification_points,
        "behavior_points": trust_score.behavior_points,
        "guarantee_points": trust_score.guarantee_points,
        "message": "信任评分已重新计算",
    }
