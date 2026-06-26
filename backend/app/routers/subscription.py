"""订阅计费API路由"""
from fastapi import APIRouter, Depends, HTTPException
from features.subscription.services.subscription_service import SubscriptionService
from app.database import get_db

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


def get_service():
    return SubscriptionService()


@router.get("/plans")
async def list_plans(service: SubscriptionService = Depends(get_service)):
    """查询所有定价方案"""
    return {"code": 0, "data": service.list_active_plans()}


@router.get("/status")
async def get_subscription(user_id: int, service: SubscriptionService = Depends(get_service)):
    """查询用户订阅状态"""
    sub = service.get_user_subscription(user_id)
    return {"code": 0, "data": sub.to_dict() if sub else None}


@router.post("/create")
async def create_subscription(
    user_id: int, plan_id: int, billing_cycle: str = "monthly",
    payment_provider: str = "alipay",
    service: SubscriptionService = Depends(get_service)
):
    """创建订阅"""
    sub = service.create_subscription(user_id, plan_id, billing_cycle, payment_provider)
    return {"code": 0, "data": sub.to_dict()}


@router.post("/cancel")
async def cancel_subscription(user_id: int, service: SubscriptionService = Depends(get_service)):
    """取消订阅"""
    service.cancel_subscription(user_id)
    return {"code": 0, "message": "订阅已取消"}


@router.post("/upgrade")
async def upgrade_subscription(
    user_id: int, new_plan_id: int,
    service: SubscriptionService = Depends(get_service)
):
    """升级订阅方案"""
    sub = service.upgrade_subscription(user_id, new_plan_id)
    return {"code": 0, "data": sub.to_dict()}


@router.get("/invoices")
async def list_invoices(user_id: int, service: SubscriptionService = Depends(get_service)):
    """查询发票记录"""
    invoices = service.get_user_invoices(user_id)
    return {"code": 0, "data": [inv.to_dict() for inv in invoices]}
