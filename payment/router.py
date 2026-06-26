"""链客宝 — 支付路由
====================
支付模块 FastAPI 路由，提供订单创建、查询、关闭、回调处理。

端点:
  POST   /api/payment/create     — 创建支付订单
  GET    /api/payment/query/{order_no}  — 查询订单
  POST   /api/payment/close/{order_no}  — 关闭未支付订单
  POST   /api/payment/callback   — 支付渠道异步回调（Webhook）
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from payment.models import PaymentOrder, generate_order_no, get_db

logger = logging.getLogger(__name__)

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/payment", tags=["支付"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    user_id: str = Field(..., min_length=1, max_length=64, description="用户标识")
    amount: int = Field(..., ge=1, description="订单金额（单位：分）")
    currency: str = Field(default="CNY", max_length=8, description="币种")
    channel: str = Field(default="wechat", description="支付渠道: wechat/alipay/balance")
    subject: str = Field(..., min_length=1, max_length=128, description="订单标题")
    body: Optional[str] = Field(default=None, description="订单描述")
    notify_url: Optional[str] = Field(default=None, max_length=256, description="异步通知地址")
    return_url: Optional[str] = Field(default=None, max_length=256, description="同步跳转地址")
    extra: Optional[dict] = Field(default=None, description="附加数据（JSON）")


class CreateOrderResponse(BaseModel):
    """创建订单响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[dict] = Field(default=None, description="订单数据")


class QueryOrderResponse(BaseModel):
    """查询订单响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[dict] = Field(default=None, description="订单数据")


class CloseOrderResponse(BaseModel):
    """关闭订单响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[dict] = Field(default=None, description="关闭的订单数据")


class CallbackRequest(BaseModel):
    """支付渠道回调请求（通用格式，各渠道需自行适配）"""
    channel: str = Field(..., description="支付渠道: wechat/alipay")
    channel_order_no: str = Field(..., description="渠道订单号")
    order_no: str = Field(..., description="业务订单号")
    trade_status: str = Field(..., description="交易状态: SUCCESS/FAIL/REFUND")
    total_amount: int = Field(..., description="支付金额（分）")
    paid_at: Optional[str] = Field(default=None, description="支付完成时间 (ISO格式)")
    sign: Optional[str] = Field(default=None, description="签名（暂不做强制验证）")
    raw_data: Optional[dict] = Field(default=None, description="渠道原始回调数据")


class CallbackResponse(BaseModel):
    """回调处理响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")


# ===================================================================
# POST /api/payment/create — 创建支付订单
# ===================================================================


@router.post("/create", response_model=CreateOrderResponse)
async def create_order(
    req: CreateOrderRequest,
    db: Session = Depends(get_db),
):
    """
    创建一笔新的支付订单。

    - 自动生成唯一业务订单号
    - 金额以「分」为单位，避免浮点数精度问题
    - 返回 order_no 供后续查询/支付
    """
    order = PaymentOrder(
        order_no=generate_order_no(),
        user_id=req.user_id,
        amount=req.amount,
        currency=req.currency,
        status="pending",
        channel=req.channel,
        subject=req.subject,
        body=req.body,
        notify_url=req.notify_url,
        return_url=req.return_url,
        extra=req.extra or {},
    )

    try:
        db.add(order)
        db.commit()
        db.refresh(order)
        logger.info(f"[支付] 订单创建成功: {order.order_no}, 金额: {order.amount}分")
        return CreateOrderResponse(data=order.to_dict())
    except Exception as e:
        db.rollback()
        logger.error(f"[支付] 订单创建失败: {e}")
        raise HTTPException(status_code=500, detail=f"订单创建失败: {str(e)}")


# ===================================================================
# GET /api/payment/query/{order_no} — 查询订单
# ===================================================================


@router.get("/query/{order_no}", response_model=QueryOrderResponse)
async def query_order(
    order_no: str,
    db: Session = Depends(get_db),
):
    """
    根据业务订单号查询订单详情。

    返回订单完整信息，包括状态、金额、支付时间等。
    """
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == order_no,
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"订单不存在: {order_no}",
        )

    return QueryOrderResponse(data=order.to_dict())


# ===================================================================
# POST /api/payment/close/{order_no} — 关闭未支付订单
# ===================================================================


@router.post("/close/{order_no}", response_model=CloseOrderResponse)
async def close_order(
    order_no: str,
    db: Session = Depends(get_db),
):
    """
    关闭一笔未支付的订单。

    仅允许关闭 status=pending 的订单，已支付/已关闭/已退款的订单无法关闭。
    """
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == order_no,
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"订单不存在: {order_no}",
        )

    if order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"订单状态不允许关闭: 当前状态={order.status}",
        )

    try:
        order.status = "closed"
        order.closed_at = datetime.utcnow()
        db.commit()
        db.refresh(order)
        logger.info(f"[支付] 订单已关闭: {order_no}")
        return CloseOrderResponse(data=order.to_dict())
    except Exception as e:
        db.rollback()
        logger.error(f"[支付] 订单关闭失败: {e}")
        raise HTTPException(status_code=500, detail=f"订单关闭失败: {str(e)}")


# ===================================================================
# POST /api/payment/callback — 支付渠道异步回调
# ===================================================================


@router.post("/callback", response_model=CallbackResponse)
async def payment_callback(
    req: CallbackRequest,
    db: Session = Depends(get_db),
):
    """
    支付渠道异步回调 Webhook。

    处理渠道（微信/支付宝）的回调通知，更新订单状态。
    - trade_status=SUCCESS → 订单标记为 paid
    - trade_status=REFUND  → 订单标记为 refunded
    - 其他状态不做状态变更

    注意: 生产环境需验签（sign 字段），此处预留了 raw_data 用于透传原始数据。
    """
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == req.order_no,
    ).first()

    if not order:
        logger.warning(f"[支付] 回调订单不存在: {req.order_no}")
        raise HTTPException(
            status_code=404,
            detail=f"订单不存在: {req.order_no}",
        )

    # 幂等处理: 已支付的订单不再重复处理
    if order.status == "paid" and req.trade_status == "SUCCESS":
        logger.info(f"[支付] 回调幂等忽略: {req.order_no} 已是 paid")
        return CallbackResponse(message="already processed")

    try:
        if req.trade_status == "SUCCESS":
            order.status = "paid"
            order.channel_order_no = req.channel_order_no
            order.paid_at = (
                datetime.fromisoformat(req.paid_at) if req.paid_at else datetime.utcnow()
            )
            logger.info(f"[支付] 订单支付成功: {req.order_no}")

        elif req.trade_status == "REFUND":
            order.status = "refunded"
            logger.info(f"[支付] 订单已退款: {req.order_no}")

        else:
            logger.info(
                f"[支付] 回调收到未知状态: {req.trade_status}, 订单: {req.order_no}, 不做变更",
            )

        # 附带回传原始数据到 extra 中
        extra = order.extra or {}
        if req.raw_data:
            extra.setdefault("callback_raw", req.raw_data)
            order.extra = extra

        db.commit()
        db.refresh(order)
        return CallbackResponse()

    except Exception as e:
        db.rollback()
        logger.error(f"[支付] 回调处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"回调处理失败: {str(e)}")


# ===================================================================
# 健康检查（可选，便于支付模块独立部署时使用）
# ===================================================================


@router.get("/health", tags=["支付"])
async def payment_health():
    """支付模块健康检查"""
    return {"status": "ok", "module": "payment"}
