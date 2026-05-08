"""推广员路由：收益查询/提现"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from datetime import datetime

from app.database import get_db
from app.models import User, Order, Withdrawal
from app.schemas import (
    ApiResponse, WithdrawRequest, WithdrawalResponse,
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/promoter", tags=["推广员"])


@router.get("/earnings", response_model=ApiResponse)
def get_earnings(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """获取推广员收益"""
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可查看收益")

    # 计算总收益：已收货订单的commission总和
    total_earnings = db.query(sa_func.coalesce(sa_func.sum(Order.commission), 0.0)).filter(
        Order.promoter_id == current_user.id,
        Order.status == "received",
        Order.commission > 0,
    ).scalar()

    # 已提现总额
    withdrawn = db.query(sa_func.coalesce(sa_func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "approved",
    ).scalar()

    # 待审核提现
    pending = db.query(sa_func.coalesce(sa_func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "pending",
    ).scalar()

    available = total_earnings - withdrawn - pending

    order_count = db.query(Order).filter(
        Order.promoter_id == current_user.id,
    ).count()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total_earnings": round(total_earnings, 2),
            "withdrawn": round(withdrawn, 2),
            "pending": round(pending, 2),
            "available": round(available, 2),
            "order_count": order_count,
        },
    )


@router.post("/withdraw", response_model=ApiResponse)
def withdraw(req: WithdrawRequest, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    """发起提现"""
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可提现")

    # 计算可提现金额
    total_earnings = db.query(db.func.coalesce(db.func.sum(Order.commission), 0.0)).filter(
        Order.promoter_id == current_user.id,
        Order.status == "received",
    ).scalar()

    withdrawn = db.query(db.func.coalesce(db.func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "approved",
    ).scalar()

    pending = db.query(db.func.coalesce(db.func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "pending",
    ).scalar()

    available = total_earnings - withdrawn - pending

    if req.amount > available:
        raise HTTPException(
            status_code=400,
            detail=f"可提现金额不足。可提现: ¥{available:.2f}，申请: ¥{req.amount:.2f}",
        )

    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="提现金额必须大于0")

    withdrawal = Withdrawal(
        user_id=current_user.id,
        amount=req.amount,
        status="pending",
        bank_info=req.bank_info or "",
    )
    db.add(withdrawal)
    db.commit()
    db.refresh(withdrawal)

    return ApiResponse(
        code=200,
        message="提现申请已提交，等待审核",
        data=WithdrawalResponse.model_validate(withdrawal).model_dump(),
    )


@router.get("/withdrawals", response_model=ApiResponse)
def get_withdrawals(db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """获取提现记录"""
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可查看提现记录")

    withdrawals = db.query(Withdrawal).filter(
        Withdrawal.user_id == current_user.id,
    ).order_by(Withdrawal.id.desc()).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(withdrawals),
            "items": [WithdrawalResponse.model_validate(w).model_dump() for w in withdrawals],
        },
    )
