"""
链客宝 — 推广分润管理 API 路由
=================================
迁移自旧版链客宝 backend/modules/promoter/routes/
适配 chainke-full 架构。

端点:
  POST   /api/promoter/withdrawals          — 创建提现申请
  GET    /api/promoter/withdrawals/{id}     — 查询提现详情
  GET    /api/promoter/withdrawals/         — 提现列表（分页）
  PUT    /api/promoter/withdrawals/{id}     — 更新提现申请信息
  PUT    /api/promoter/withdrawals/{id}/review — 审核提现申请
  DELETE /api/promoter/withdrawals/{id}     — 删除提现申请
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/promoter", tags=["推广分润管理"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CreateWithdrawalRequest(BaseModel):
    """创建提现申请请求"""
    user_id: int = Field(..., gt=0, description="推广员 ID")
    amount: float = Field(..., gt=0, description="提现金额")
    bank_info: str | None = Field(default=None, description="收款信息(JSON)")


class UpdateWithdrawalRequest(BaseModel):
    """更新提现申请请求"""
    bank_info: str | None = Field(default=None, description="收款信息(JSON)")


class ReviewWithdrawalRequest(BaseModel):
    """审核提现申请请求"""
    status: str = Field(
        ...,
        pattern=r"^(approved|rejected)$",
        description="审核结果: approved/rejected",
    )
    reviewed_by: int = Field(..., gt=0, description="审核人 ID")
    review_note: str | None = Field(default=None, max_length=500, description="审核备注")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 路由实现
# ===================================================================


@router.post("/withdrawals", response_model=ApiResponse)
async def create_withdrawal(req: CreateWithdrawalRequest, db: Session = Depends(get_db)):
    """创建提现申请"""
    try:
        from features.promoter.services import WithdrawalService

        service = WithdrawalService(db)
        withdrawal = service.create_withdrawal(
            user_id=req.user_id,
            amount=req.amount,
            bank_info=req.bank_info,
        )
        return ApiResponse(code=0, message="success", data=withdrawal.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="promoter 模块未安装")


@router.get("/withdrawals/{withdrawal_id}", response_model=ApiResponse)
async def get_withdrawal(withdrawal_id: int, db: Session = Depends(get_db)):
    """查询提现详情"""
    try:
        from features.promoter.services import WithdrawalService

        service = WithdrawalService(db)
        withdrawal = service.get_withdrawal(withdrawal_id)
        if withdrawal is None:
            raise HTTPException(status_code=404, detail=f"提现申请不存在: id={withdrawal_id}")
        return ApiResponse(code=0, message="success", data=withdrawal.to_dict())
    except ImportError:
        raise HTTPException(status_code=500, detail="promoter 模块未安装")


@router.get("/withdrawals", response_model=ApiResponse)
async def list_withdrawals(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    user_id: int | None = Query(None, description="推广员 ID 过滤"),
    status: str | None = Query(
        None,
        pattern=r"^(pending|approved|rejected)$",
        description="提现状态过滤",
    ),
    db: Session = Depends(get_db),
):
    """提现列表（分页）"""
    try:
        from features.promoter.services import WithdrawalService

        service = WithdrawalService(db)
        items, total = service.list_withdrawals(
            page=page,
            limit=limit,
            user_id=user_id,
            status=status,
        )
        return ApiResponse(
            code=0,
            message="success",
            data={
                "total": total,
                "page": page,
                "limit": limit,
                "items": [w.to_dict() for w in items],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="promoter 模块未安装")


@router.put("/withdrawals/{withdrawal_id}", response_model=ApiResponse)
async def update_withdrawal(
    withdrawal_id: int, req: UpdateWithdrawalRequest, db: Session = Depends(get_db)
):
    """更新提现申请信息"""
    try:
        from features.promoter.services import WithdrawalService

        service = WithdrawalService(db)
        withdrawal = service.update_withdrawal(
            withdrawal_id=withdrawal_id,
            bank_info=req.bank_info,
        )
        return ApiResponse(code=0, message="success", data=withdrawal.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="promoter 模块未安装")


@router.put("/withdrawals/{withdrawal_id}/review", response_model=ApiResponse)
async def review_withdrawal(
    withdrawal_id: int, req: ReviewWithdrawalRequest, db: Session = Depends(get_db)
):
    """审核提现申请"""
    try:
        from features.promoter.services import WithdrawalService

        service = WithdrawalService(db)
        withdrawal = service.review_withdrawal(
            withdrawal_id=withdrawal_id,
            new_status=req.status,
            reviewed_by=req.reviewed_by,
            review_note=req.review_note,
        )
        return ApiResponse(code=0, message="success", data=withdrawal.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="promoter 模块未安装")


@router.delete("/withdrawals/{withdrawal_id}", response_model=ApiResponse)
async def delete_withdrawal(withdrawal_id: int, db: Session = Depends(get_db)):
    """删除提现申请"""
    try:
        from features.promoter.services import WithdrawalService

        service = WithdrawalService(db)
        service.delete_withdrawal(withdrawal_id)
        return ApiResponse(code=0, message="success", data={"id": withdrawal_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="promoter 模块未安装")
