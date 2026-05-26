"""充值模块 — API 路由"""
import logging
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import User
from app.auth import get_current_user, get_current_admin
from recharge.models import UserBalance, RechargeOrder, BalanceLog

# ===== 支付模块 =====
from payment import (
    WxPayApi,
    WxPayConfig,
    get_config,
    PLATFORM_WXPAY,
    has_config,
    is_real_mode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recharge", tags=["充值"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================

class PrecreateRequest(BaseModel):
    amount: float = Field(..., gt=0, description="充值金额（元），最小1元")
    platform: str = Field(default="wxpay", pattern="^(wxpay|alipay)$")


class AdjustRequest(BaseModel):
    user_id: int
    amount: float = Field(..., description="调额金额（正数增加，负数减少）")
    remark: str = Field(default="", max_length=500)


# ============================================================
# 工具函数
# ============================================================

def generate_order_no(user_id: int) -> str:
    """生成充值单号：RC{user_id}{YYYYMMDD}{4位随机数}"""
    import time
    ts = time.strftime("%Y%m%d")
    rand = f"{random.randint(1000, 9999)}"
    return f"RC{user_id}{ts}{rand}"


def get_or_create_balance(db: Session, user_id: int) -> UserBalance:
    """获取用户余额记录，不存在则创建"""
    bal = db.query(UserBalance).filter(UserBalance.user_id == user_id).first()
    if not bal:
        bal = UserBalance(
            user_id=user_id,
            balance=0.00,
            total_recharged=0.00,
            total_consumed=0.00,
            frozen_amount=0.00,
            version=1,
        )
        db.add(bal)
        db.flush()
    return bal


# ============================================================
# API 路由
# ============================================================

@router.post("/precreate")
async def precreate_recharge(
    req: PrecreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    预创建充值单
    - 生成充值订单写入数据库
    - 调用微信 JSAPI 统一下单
    - 返回 prepay_id + 前端调起支付参数
    """
    # 校验支付平台
    if req.platform != "wxpay":
        raise HTTPException(status_code=400, detail="暂仅支持微信支付")

    # 生成订单号
    order_no = generate_order_no(current_user.id)
    amount_fen = int(round(req.amount * 100))  # 元 → 分

    # 创建充值订单（状态 pending）
    order = RechargeOrder(
        user_id=current_user.id,
        order_no=order_no,
        amount=req.amount,
        platform=req.platform,
        prepay_id=None,
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # 尝试真实微信支付（仅当 PAYMENT_MODE=real 且配置完整）
    result = None
    if is_real_mode() and has_config(PLATFORM_WXPAY):
        config = get_config(PLATFORM_WXPAY)
        openid = current_user.wechat_openid
        if openid and config.is_configured:
            try:
                wxpay = WxPayApi()
                result = await wxpay.create_jsapi_order(
                    openid=openid,
                    out_trade_no=order_no,
                    total_fee=amount_fen,
                    description=f"链客宝充值-{req.amount:.2f}元",
                    attach=f"recharge:{order.id}",
                )
            except Exception as e:
                logger.warning(f"微信统一下单失败，降级 mock: {e}")

    if not result or not result.get("prepay_id"):
        # Mock 模式
        import hashlib
        import time as time_mod
        mock_app_id = "wxb4f6d89904200fd2"
        mock_ts = str(int(time_mod.time()))
        mock_nonce = hashlib.md5(f"{mock_ts}{order.id}".encode()).hexdigest()[:16]
        mock_prepay_id = f"wx{mock_ts}{order.id}"
        order.prepay_id = mock_prepay_id
        order.status = "pending"
        db.commit()

        raw = f"{mock_app_id}\n{mock_ts}\n{mock_nonce}\nprepay_id={mock_prepay_id}\n"
        mock_pay_sign = hashlib.sha256(raw.encode()).hexdigest()[:32]
        payment_params = {
            "appId": mock_app_id,
            "timeStamp": mock_ts,
            "nonceStr": mock_nonce,
            "package": f"prepay_id={mock_prepay_id}",
            "signType": "RSA",
            "paySign": mock_pay_sign,
            "_mode": "mock",
        }
        logger.info(f"Mock 充值预创建: order_no={order_no}, amount={req.amount}")
        return {
            "code": 200,
            "message": "success (mock)",
            "data": {
                "order_id": order.id,
                "order_no": order_no,
                "amount": req.amount,
                "prepay_id": mock_prepay_id,
                "payment_params": payment_params,
            },
        }

    # 真实支付成功
    prepay_id = result["prepay_id"]
    order.prepay_id = prepay_id
    db.commit()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "order_id": order.id,
            "order_no": order_no,
            "amount": req.amount,
            "prepay_id": prepay_id,
            "payment_params": result.get("payment_params"),
        },
    }


@router.get("/query/{order_no}")
def query_recharge_order(
    order_no: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询充值单状态"""
    order = db.query(RechargeOrder).filter(
        RechargeOrder.order_no == order_no,
        RechargeOrder.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="充值订单不存在")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": order.id,
            "order_no": order.order_no,
            "amount": float(order.amount),
            "platform": order.platform,
            "status": order.status,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
    }


@router.get("/list")
def list_recharge_orders(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户充值记录列表（分页）"""
    query = db.query(RechargeOrder).filter(
        RechargeOrder.user_id == current_user.id
    )

    total = query.count()
    orders = (
        query.order_by(desc(RechargeOrder.created_at))
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": o.id,
                    "order_no": o.order_no,
                    "amount": float(o.amount),
                    "platform": o.platform,
                    "status": o.status,
                    "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in orders
            ],
        },
    }


@router.get("/balance")
def query_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询用户余额 + 最近10条流水"""
    bal = get_or_create_balance(db, current_user.id)

    recent_logs = (
        db.query(BalanceLog)
        .filter(BalanceLog.user_id == current_user.id)
        .order_by(desc(BalanceLog.created_at))
        .limit(10)
        .all()
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "balance": float(bal.balance),
            "total_recharged": float(bal.total_recharged),
            "total_consumed": float(bal.total_consumed),
            "recent_logs": [
                {
                    "id": log.id,
                    "amount": float(log.amount),
                    "balance_before": float(log.balance_before),
                    "balance_after": float(log.balance_after),
                    "direction": log.direction,
                    "biz_type": log.biz_type,
                    "biz_id": log.biz_id,
                    "remark": log.remark,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in recent_logs
            ],
        },
    }


@router.post("/adjust")
def adjust_balance(
    req: AdjustRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """管理员手动调额（正数增加余额，负数扣减余额）"""
    bal = get_or_create_balance(db, req.user_id)
    from decimal import Decimal
    amount = Decimal(str(req.amount))

    old_balance = Decimal(str(bal.balance))
    new_balance = old_balance + amount
    if new_balance < 0:
        raise HTTPException(status_code=400, detail="余额不足，调额后余额为负")

    direction = "IN" if req.amount >= 0 else "OUT"
    bal.balance = new_balance
    bal.version += 1

    # 写入流水
    log = BalanceLog(
        user_id=req.user_id,
        amount=abs(req.amount),
        balance_before=old_balance,
        balance_after=new_balance,
        direction=direction,
        biz_type="adjust",
        biz_id=None,
        remark=req.remark or f"管理员调额（操作人: {current_admin.username}）",
    )
    db.add(log)
    db.commit()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "user_id": req.user_id,
            "before": float(old_balance),
            "after": float(new_balance),
            "amount": req.amount,
        },
    }


@router.get("/balance-logs")
def list_balance_logs(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页查询余额流水记录"""
    query = db.query(BalanceLog).filter(
        BalanceLog.user_id == current_user.id
    )

    total = query.count()
    logs = (
        query.order_by(desc(BalanceLog.created_at))
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    def _map_type(direction: str, biz_type: str) -> str:
        if direction == "IN" and biz_type == "recharge":
            return "recharge"
        elif direction == "OUT":
            return "consume"
        elif direction == "IN":
            return "recharge"
        return "other"

    def _map_description(log) -> str:
        parts = []
        if log.biz_type == "recharge":
            parts.append(f"充值 {log.biz_id or ''}")
        elif log.biz_type == "consume":
            parts.append(f"消费 {log.biz_id or ''}")
        elif log.biz_type == "adjust":
            parts.append(f"管理员调额")
        elif log.biz_type == "refund":
            parts.append(f"退款 {log.biz_id or ''}")
        else:
            parts.append(log.biz_type or "")
        if log.remark:
            parts.append(f"({log.remark})")
        return " ".join(parts)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": log.id,
                    "amount": float(log.amount),
                    "type": _map_type(log.direction, log.biz_type),
                    "description": _map_description(log),
                    "biz_type": log.biz_type,
                    "direction": log.direction,
                    "balance_before": float(log.balance_before),
                    "balance_after": float(log.balance_after),
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
        },
    }
