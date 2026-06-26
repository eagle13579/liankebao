"""订阅计费 API 路由

端点:
  GET    /api/subscription/plans               — 获取所有订阅方案
  POST   /api/subscription/create              — 创建订阅 (月付/年付/用量计费)
  POST   /api/subscription/cancel              — 取消订阅
  GET    /api/subscription/invoices            — 获取用户发票列表
  GET    /api/subscription/invoices/{id}       — 获取发票详情
  POST   /api/subscription/payment-callback    — 支付回调更新 (由支付渠道回调)
  POST   /api/subscription/usage/record        — 记录用量 (用量计费模式)
"""

import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from features.subscription.models import (
    SubscriptionPlan, Subscription, Invoice, InvoiceStatus,
    PlanTier, SubscriptionStatus, BillingMode,
    generate_invoice_no,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/subscription", tags=["订阅计费"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================

class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[dict | list] = Field(default=None, description="响应数据")


class CreateSubscriptionRequest(BaseModel):
    """创建订阅请求"""
    user_id: int = Field(..., description="用户ID")
    plan_id: int = Field(..., description="订阅方案ID")
    billing_mode: str = Field(
        default="monthly", pattern="^(monthly|yearly|usage)$",
        description="计费模式: monthly(月付)/yearly(年付)/usage(用量计费)",
    )
    payment_provider: str = Field(
        default="alipay", pattern="^(alipay|wxpay)$",
        description="支付渠道",
    )
    auto_renew: bool = Field(default=True, description="自动续费")


class CancelSubscriptionRequest(BaseModel):
    """取消订阅请求"""
    user_id: int = Field(..., description="用户ID")
    immediate: bool = Field(
        default=False,
        description="是否立即取消(true)或周期结束后取消(false)",
    )


class PaymentCallbackRequest(BaseModel):
    """支付回调更新请求"""
    invoice_no: str = Field(..., description="发票号")
    payment_id: str = Field(..., description="支付流水号(渠道侧)")
    status: str = Field(
        ..., pattern="^(paid|refunded)$",
        description="支付结果: paid(支付成功)/refunded(已退款)",
    )
    channel: str = Field(default="alipay", description="支付渠道: alipay/wxpay")
    extra: Optional[dict] = Field(default=None, description="回调原始数据")


class UsageRecordRequest(BaseModel):
    """用量记录请求 (用量计费模式)"""
    subscription_id: int = Field(..., description="订阅ID")
    units: int = Field(default=1, ge=1, description="消耗单位数")


# ===================================================================
# 工具函数
# ===================================================================

def get_plan_or_404(db: Session, plan_id: int) -> SubscriptionPlan:
    """获取方案，不存在则抛 404"""
    plan = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.id == plan_id,
        SubscriptionPlan.is_active == True,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="订阅方案不存在")
    return plan


def get_subscription_or_404(
    db: Session, user_id: int, subscription_id: int = None,
) -> Subscription:
    """获取用户的活跃订阅"""
    query = db.query(Subscription).filter(
        Subscription.user_id == user_id,
    )
    if subscription_id:
        query = query.filter(Subscription.id == subscription_id)
    sub = query.order_by(Subscription.created_at.desc()).first()
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return sub


# ===================================================================
# GET /api/subscription/plans — 获取所有订阅方案
# ===================================================================

@router.get("/plans", response_model=ApiResponse)
async def list_plans(db: Session = Depends(get_db)):
    """查询所有启用的订阅方案"""
    plans = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.is_active == True,
    ).order_by(SubscriptionPlan.sort_order).all()
    return ApiResponse(
        code=0,
        data=[p.to_dict() for p in plans],
    )


# ===================================================================
# POST /api/subscription/create — 创建订阅
# ===================================================================

@router.post("/create", response_model=ApiResponse)
async def create_subscription(
    req: CreateSubscriptionRequest,
    db: Session = Depends(get_db),
):
    """创建订阅

    支持三种计费模式:
    - monthly : 月付，立即生成首月发票
    - yearly  : 年付，立即生成全年发票
    - usage   : 用量计费，仅创建订阅不生成发票 (按用量出账)
    """
    # 1. 获取方案
    plan = get_plan_or_404(db, req.plan_id)

    # 2. 取消用户现有的活跃订阅
    existing = db.query(Subscription).filter(
        Subscription.user_id == req.user_id,
        Subscription.status.in_([
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
        ]),
    ).first()
    if existing:
        existing.status = SubscriptionStatus.CANCELED
        existing.canceled_at = datetime.datetime.utcnow()
        existing.auto_renew = False
        logger.info("已取消用户 %s 原有订阅 %s", req.user_id, existing.id)

    # 3. 计算周期
    now = datetime.datetime.utcnow()
    if req.billing_mode == BillingMode.YEARLY.value:
        period_end = now + datetime.timedelta(days=365)
    elif req.billing_mode == BillingMode.USAGE.value:
        period_end = now + datetime.timedelta(days=30)  # 按月结算
    else:  # monthly
        period_end = now + datetime.timedelta(days=30)

    # 4. 创建订阅
    sub = Subscription(
        user_id=req.user_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_mode=BillingMode(req.billing_mode),
        current_period_start=now,
        current_period_end=period_end,
        payment_provider=req.payment_provider,
        auto_renew=req.auto_renew,
        usage_included=plan.usage_included,
    )
    db.add(sub)
    db.flush()  # 获取 sub.id

    # 5. 月付/年付立即生成发票
    invoice = None
    if req.billing_mode in (BillingMode.MONTHLY.value, BillingMode.YEARLY.value):
        price = plan.get_price(req.billing_mode)
        tax = round(price * 0.06, 2)
        total = round(price + tax, 2)

        invoice = Invoice(
            invoice_no=generate_invoice_no(req.user_id),
            user_id=req.user_id,
            subscription_id=sub.id,
            amount=price,
            tax=tax,
            total=total,
            status=InvoiceStatus.PENDING,
            billing_type="subscription",
            billing_cycle=req.billing_mode,
            payment_method=req.payment_provider,
            description=f"{plan.name} {req.billing_mode} 订阅",
            due_at=now + datetime.timedelta(days=1),  # 24小时内支付
        )
        db.add(invoice)

    db.commit()
    db.refresh(sub)

    result = sub.to_dict()
    if invoice:
        db.refresh(invoice)
        result["invoice"] = invoice.to_dict()

    logger.info(
        "用户 %s 创建订阅: plan=%s, mode=%s, sub_id=%s",
        req.user_id, plan.name, req.billing_mode, sub.id,
    )
    return ApiResponse(code=0, data=result)


# ===================================================================
# POST /api/subscription/cancel — 取消订阅
# ===================================================================

@router.post("/cancel", response_model=ApiResponse)
async def cancel_subscription(
    req: CancelSubscriptionRequest,
    db: Session = Depends(get_db),
):
    """取消订阅"""
    sub = get_subscription_or_404(db, req.user_id)

    if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        raise HTTPException(status_code=400, detail="订阅状态不允许取消")

    sub.status = SubscriptionStatus.CANCELED
    sub.canceled_at = datetime.datetime.utcnow()
    sub.auto_renew = False

    db.commit()
    logger.info("用户 %s 取消订阅 %s", req.user_id, sub.id)
    return ApiResponse(
        code=0,
        message="订阅已取消",
        data=sub.to_dict(),
    )


# ===================================================================
# GET /api/subscription/invoices — 获取用户发票列表
# ===================================================================

@router.get("/invoices", response_model=ApiResponse)
async def list_invoices(
    user_id: int = Query(..., description="用户ID"),
    status: Optional[str] = Query(None, description="筛选状态: pending/paid/refunded"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
):
    """查询用户的发票记录，支持分页和状态筛选"""
    query = db.query(Invoice).filter(Invoice.user_id == user_id)

    if status:
        try:
            invoice_status = InvoiceStatus(status)
            query = query.filter(Invoice.status == invoice_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态: {status}")

    total = query.count()
    invoices = (
        query.order_by(Invoice.issued_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        code=0,
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [inv.to_dict() for inv in invoices],
        },
    )


# ===================================================================
# GET /api/subscription/invoices/{id} — 获取发票详情
# ===================================================================

@router.get("/invoices/{invoice_id}", response_model=ApiResponse)
async def get_invoice_detail(
    invoice_id: int,
    user_id: int = Query(..., description="用户ID"),
    db: Session = Depends(get_db),
):
    """查询单张发票详情"""
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="发票不存在")

    return ApiResponse(code=0, data=invoice.to_dict())


# ===================================================================
# POST /api/subscription/payment-callback — 支付回调更新
# ===================================================================

@router.post("/payment-callback", response_model=ApiResponse)
async def payment_callback(
    req: PaymentCallbackRequest,
    db: Session = Depends(get_db),
):
    """支付回调 — 由支付渠道(支付宝/微信)回调时调用

    更新发票状态，并根据结果更新关联订阅状态。
    此 API 不应直接暴露给前端，仅限内部/支付渠道回调使用。
    """
    # 1. 查找发票
    invoice = db.query(Invoice).filter(
        Invoice.invoice_no == req.invoice_no,
    ).first()
    if not invoice:
        logger.warning("支付回调: 发票不存在 invoice_no=%s", req.invoice_no)
        raise HTTPException(status_code=404, detail="发票不存在")

    # 2. 更新发票状态
    if req.status == "paid":
        if invoice.status == InvoiceStatus.PAID:
            logger.info("支付回调: 发票 %s 已支付，忽略重复回调", req.invoice_no)
            return ApiResponse(code=0, message="already processed")

        invoice.mark_paid(payment_id=req.payment_id, paid_at=datetime.datetime.utcnow())
        invoice.payment_method = req.channel
        if req.extra:
            invoice.extra = {**(invoice.extra or {}), **req.extra}

        # 3. 更新关联订阅
        if invoice.subscription_id:
            sub = db.query(Subscription).filter(
                Subscription.id == invoice.subscription_id,
            ).first()
            if sub:
                sub.status = SubscriptionStatus.ACTIVE
                sub.payment_id = req.payment_id
                sub.payment_provider = req.channel
                logger.info("支付回调: 订阅 %s 已激活", sub.id)

        logger.info(
            "支付回调成功: invoice=%s, payment_id=%s, channel=%s",
            req.invoice_no, req.payment_id, req.channel,
        )

    elif req.status == "refunded":
        invoice.mark_refunded()
        logger.info("支付回调: 发票 %s 已退款", req.invoice_no)

    db.commit()
    db.refresh(invoice)
    return ApiResponse(code=0, data=invoice.to_dict())


# ===================================================================
# POST /api/subscription/usage/record — 记录用量 (用量计费)
# ===================================================================

@router.post("/usage/record", response_model=ApiResponse)
async def record_usage(
    req: UsageRecordRequest,
    db: Session = Depends(get_db),
):
    """记录用量消耗 (仅用量计费模式)

    用量超过免费额度后，超额部分将在下一个结算周期出账。
    """
    # 1. 查找订阅
    sub = db.query(Subscription).filter(
        Subscription.id == req.subscription_id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.billing_mode == BillingMode.USAGE,
    ).first()
    if not sub:
        raise HTTPException(
            status_code=404,
            detail="订阅不存在或非用量计费模式",
        )

    # 2. 记录用量
    sub.consume_usage(req.units)
    db.commit()
    db.refresh(sub)

    logger.info(
        "用量记录: sub_id=%s, consumed=%s, included=%s, overage=%s",
        sub.id, sub.usage_consumed, sub.usage_included, sub.usage_overage,
    )
    return ApiResponse(
        code=0,
        data={
            "subscription_id": sub.id,
            "usage_consumed": sub.usage_consumed,
            "usage_included": sub.usage_included,
            "usage_overage": sub.usage_overage,
        },
    )


# ===================================================================
# GET /api/subscription/status — 查询用户订阅状态
# ===================================================================

@router.get("/status", response_model=ApiResponse)
async def get_subscription_status(
    user_id: int = Query(..., description="用户ID"),
    db: Session = Depends(get_db),
):
    """查询用户当前订阅状态"""
    sub = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status.in_([
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
        ]),
    ).order_by(Subscription.created_at.desc()).first()

    return ApiResponse(
        code=0,
        data=sub.to_dict() if sub else None,
    )
