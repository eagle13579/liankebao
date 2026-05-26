"""用户数据洞察路由：我的产品数、我的订单数、本月成交额、推广收益"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import User, Product, Order, Withdrawal
from app.schemas import ApiResponse
from app.auth import get_current_user

router = APIRouter(prefix="/api/insights", tags=["数据洞察"])


@router.get("/dashboard", response_model=ApiResponse)
def get_insights_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的数据洞察看板"""
    # 1. 我的产品数
    my_products = db.query(Product).filter(
        Product.owner_id == current_user.id,
    ).count()

    # 2. 我的订单数（作为买家）
    my_orders = db.query(Order).filter(
        Order.user_id == current_user.id,
    ).count()

    # 3. 本月成交额（作为买家的已支付订单）
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_sales = db.query(sa_func.coalesce(sa_func.sum(Order.total_price), 0.0)).filter(
        Order.user_id == current_user.id,
        Order.status.in_(["paid", "shipped", "received"]),
        Order.created_at >= month_start,
    ).scalar()

    # 4. 推广收益（作为推广员的已结算佣金）
    promotion_earnings = db.query(sa_func.coalesce(sa_func.sum(Order.commission), 0.0)).filter(
        Order.promoter_id == current_user.id,
        Order.status == "received",
        Order.commission > 0,
    ).scalar()

    # 5. 本月新增订单数（用于环比）
    monthly_orders = db.query(Order).filter(
        Order.user_id == current_user.id,
        Order.created_at >= month_start,
    ).count()

    # 6. 上月成交额（用于环比计算）
    if month_start.month == 1:
        prev_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_month_start = month_start.replace(month=month_start.month - 1)
    prev_monthly_sales = db.query(sa_func.coalesce(sa_func.sum(Order.total_price), 0.0)).filter(
        Order.user_id == current_user.id,
        Order.status.in_(["paid", "shipped", "received"]),
        Order.created_at >= prev_month_start,
        Order.created_at < month_start,
    ).scalar()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "my_products": my_products,
            "my_orders": my_orders,
            "monthly_sales": round(monthly_sales, 2),
            "promotion_earnings": round(promotion_earnings, 2),
            "monthly_orders": monthly_orders,
            "prev_monthly_sales": round(prev_monthly_sales, 2),
        },
    )
