"""
交易保障 API 路由 (Escrow Router)
==================================
对标 Alibaba Trade Assurance 的交易保障体系:
  - POST   /api/escrow/deals                   — 创建交易
  - GET    /api/escrow/deals                   — 交易列表
  - GET    /api/escrow/deals/{id}              — 交易详情
  - POST   /api/escrow/deals/{id}/milestones   — 更新里程碑
  - POST   /api/escrow/deals/{id}/release      — 释放付款
  - POST   /api/escrow/deals/{id}/dispute      — 发起争议
  - POST   /api/escrow/deals/{id}/cancel       — 取消交易
  - GET    /api/escrow/trust-score/{user_id}   — 用户信任分
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.models.escrow import (
    DEAL_STATUS_CANCELLED,
    DEAL_STATUS_COMPLETED,
    DEAL_STATUS_DISPUTED,
    DEAL_STATUS_FULFILLED,
    DEAL_STATUS_PAID,
    DEAL_STATUS_PENDING,
    DEAL_STATUS_REFUNDED,
    DEAL_STATUS_RESOLVED,
    VALID_DEAL_STATUSES,
    Deal,
    Dispute,
    Milestone,
)
from app.services.escrow_service import (
    calculate_trust_score,
    cancel_deal,
    create_deal,
    create_dispute,
    get_deal,
    get_trust_score,
    list_deals,
    release_payment,
    resolve_dispute,
    update_milestone,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/escrow", tags=["交易保障"])


# ──────────────────────────────────────────────
# Pydantic 请求 / 响应模型
# ──────────────────────────────────────────────


class MilestoneInput(BaseModel):
    """里程碑输入"""

    name: str = Field(..., min_length=1, max_length=200, description="里程碑名称")
    description: Optional[str] = Field(None, description="描述")
    due_date: Optional[str] = Field(None, description="截止日期 (ISO 8601)")


class CreateDealRequest(BaseModel):
    """创建交易请求"""

    seller_id: int = Field(..., description="卖方用户ID")
    amount: float = Field(..., gt=0, description="交易金额")
    title: str = Field("", max_length=255, description="交易标题")
    description: str = Field("", description="交易描述")
    milestones: Optional[List[MilestoneInput]] = Field(None, description="里程碑列表")


class MilestoneUpdateRequest(BaseModel):
    """更新里程碑请求"""

    milestone_id: int = Field(..., description="里程碑ID")
    status: str = Field(..., description="新状态 (pending / in_progress / completed / failed)")


class DisputeRequest(BaseModel):
    """发起争议请求"""

    reason: str = Field(..., min_length=1, max_length=500, description="争议原因")
    description: str = Field("", description="详细描述")
    evidence: Optional[List[str]] = Field(None, description="证据列表（文件URL）")


class ResolveDisputeRequest(BaseModel):
    """解决争议请求"""

    dispute_id: int = Field(..., description="争议ID")
    resolution: str = Field(..., min_length=1, description="解决结果说明")
    status: str = Field("resolved", description="解决状态 (resolved / rejected)")


# ============================================================
# API 端点
# ============================================================


@router.post("/deals", summary="创建交易", response_model=Dict[str, Any])
async def api_create_deal(
    req: CreateDealRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建一笔交易保障订单，可附带里程碑"""
    try:
        milestones_dict = None
        if req.milestones:
            milestones_dict = [ms.model_dump() for ms in req.milestones]

        deal = create_deal(
            db=db,
            buyer_id=current_user.id,
            seller_id=req.seller_id,
            amount=req.amount,
            title=req.title,
            description=req.description,
            milestones=milestones_dict,
        )
        return {"code": 0, "message": "交易创建成功", "data": deal.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"创建交易失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建交易失败")


@router.get("/deals", summary="交易列表", response_model=Dict[str, Any])
async def api_list_deals(
    status_filter: Optional[str] = Query(None, alias="status", description="按状态过滤"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的所有交易（作为买方或卖方）"""
    try:
        if status_filter and status_filter not in VALID_DEAL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的状态: {status_filter}",
            )

        deals = list_deals(db, current_user.id, status=status_filter)
        return {
            "code": 0,
            "message": "ok",
            "data": [d.to_dict() for d in deals],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"查询交易列表失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查询交易列表失败")


@router.get("/deals/{deal_id}", summary="交易详情", response_model=Dict[str, Any])
async def api_get_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单笔交易详情（含里程碑和争议信息）"""
    try:
        deal = get_deal(db, deal_id)
        if not deal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交易不存在")
        if deal.buyer_id != current_user.id and deal.seller_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看此交易")
        return {"code": 0, "message": "ok", "data": deal.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"查询交易详情失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查询交易详情失败")


@router.post("/deals/{deal_id}/milestones", summary="更新里程碑", response_model=Dict[str, Any])
async def api_update_milestone(
    deal_id: int,
    req: MilestoneUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新指定交易的里程碑状态"""
    try:
        deal = get_deal(db, deal_id)
        if not deal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交易不存在")

        milestone = update_milestone(db, deal_id, req.milestone_id, req.status)
        return {"code": 0, "message": "里程碑已更新", "data": milestone.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"更新里程碑失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新里程碑失败")


@router.post("/deals/{deal_id}/release", summary="释放付款", response_model=Dict[str, Any])
async def api_release_payment(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """买方确认释放付款给卖家（模拟）"""
    try:
        deal = release_payment(db, deal_id, current_user.id)
        return {"code": 0, "message": "付款已释放", "data": deal.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"释放付款失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="释放付款失败")


@router.post("/deals/{deal_id}/dispute", summary="发起争议", response_model=Dict[str, Any])
async def api_create_dispute(
    deal_id: int,
    req: DisputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对交易发起争议"""
    try:
        dispute = create_dispute(
            db=db,
            deal_id=deal_id,
            initiator_id=current_user.id,
            reason=req.reason,
            description=req.description,
            evidence=req.evidence,
        )
        return {"code": 0, "message": "争议已发起", "data": dispute.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"发起争议失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="发起争议失败")


@router.post("/deals/{deal_id}/cancel", summary="取消交易", response_model=Dict[str, Any])
async def api_cancel_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消交易（仅 pending / paid 状态可取消）"""
    try:
        deal = cancel_deal(db, deal_id, current_user.id)
        return {"code": 0, "message": "交易已取消", "data": deal.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"取消交易失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取消交易失败")


@router.get("/trust-score/{user_id}", summary="用户信任分", response_model=Dict[str, Any])
async def api_trust_score(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定用户的信任评分与等级"""
    try:
        # 验证用户存在
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        score = get_trust_score(db, user_id)
        return {"code": 0, "message": "ok", "data": score}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"查询信任分失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查询信任分失败")


# ============================================================
# 管理端/争议解决端点（管理员权限）
# ============================================================


@router.post("/disputes/resolve", summary="解决争议（管理员）", response_model=Dict[str, Any])
async def api_resolve_dispute(
    req: ResolveDisputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员解决争议"""
    try:
        # 简单权限校验：仅 admin 可操作
        if current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可解决争议")

        dispute = resolve_dispute(
            db=db,
            dispute_id=req.dispute_id,
            resolution=req.resolution,
            status=req.status,
        )
        return {"code": 0, "message": "争议已解决", "data": dispute.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"解决争议失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="解决争议失败")
