"""推广员路由：收益查询/提现/提现记录"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from app.models import User, Order, Withdrawal
from app.schemas import (
    ApiResponse, EarningsResponse, WithdrawRequest, WithdrawalResponse,
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/promoter", tags=["推广员"])


@router.get("/earnings", response_model=ApiResponse)
def get_earnings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取推广收益概览"""
    # 推广员专属，如果不是推广员则查不到收益
    earnings = EarningsResponse()

    # 如果当前用户是推广员，查他自己的
    user_id = current_user.id

    # 已完成订单的佣金（确认收货后才是实际收益）
    completed_orders = db.query(Order).filter(
        Order.promoter_id == user_id,
        Order.status == "received",
    ).all()
    completed_commission = sum(o.commission for o in completed_orders) if completed_orders else 0.0

    # 所有推广订单
    all_promoter_orders = db.query(Order).filter(
        Order.promoter_id == user_id,
    ).all()
    total_commission = sum(o.commission for o in all_promoter_orders) if all_promoter_orders else 0.0

    # 已提现和提现中
    approved_withdrawals = db.query(Withdrawal).filter(
        Withdrawal.user_id == user_id,
        Withdrawal.status == "approved",
    ).all()
    withdrawn_amount = sum(w.amount for w in approved_withdrawals) if approved_withdrawals else 0.0

    pending_withdrawals = db.query(Withdrawal).filter(
        Withdrawal.user_id == user_id,
        Withdrawal.status == "pending",
    ).all()
    pending_amount = sum(w.amount for w in pending_withdrawals) if pending_withdrawals else 0.0

    earnings = EarningsResponse(
        total_earnings=completed_commission,
        withdrawable=completed_commission - withdrawn_amount - pending_amount,
        withdrawn=withdrawn_amount,
        pending_withdrawal=pending_amount,
        order_count=len(all_promoter_orders),
    )

    return ApiResponse(
        code=200,
        message="success",
        data=earnings.model_dump(),
    )


@router.post("/withdraw", response_model=ApiResponse)
def withdraw(
    req: WithdrawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发起提现申请"""
    # 计算可提现金额
    user_id = current_user.id

    completed_orders = db.query(Order).filter(
        Order.promoter_id == user_id,
        Order.status == "received",
    ).all()
    completed_commission = sum(o.commission for o in completed_orders) if completed_orders else 0.0

    approved_withdrawals = db.query(Withdrawal).filter(
        Withdrawal.user_id == user_id,
        Withdrawal.status == "approved",
    ).all()
    withdrawn_amount = sum(w.amount for w in approved_withdrawals) if approved_withdrawals else 0.0

    pending_withdrawals = db.query(Withdrawal).filter(
        Withdrawal.user_id == user_id,
        Withdrawal.status == "pending",
    ).all()
    pending_amount = sum(w.amount for w in pending_withdrawals) if pending_withdrawals else 0.0

    withdrawable = completed_commission - withdrawn_amount - pending_amount

    if req.amount > withdrawable:
        raise HTTPException(
            status_code=400,
            detail=f"可提现金额不足，当前可提现: {withdrawable:.2f} 元",
        )

    withdrawal = Withdrawal(
        user_id=user_id,
        amount=req.amount,
        status="pending",
        bank_info=req.bank_info or '{"bank_name":"","card_number":"","holder_name":""}',
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
def list_withdrawals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取提现记录列表"""
    withdrawals = db.query(Withdrawal).filter(
        Withdrawal.user_id == current_user.id,
    ).order_by(desc(Withdrawal.created_at)).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(withdrawals),
            "items": [WithdrawalResponse.model_validate(w).model_dump() for w in withdrawals],
        },
    )
