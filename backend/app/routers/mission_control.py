"""链客宝AI首页「任务控制」路由 - 返回3个核心功能状态"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Order, Product, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/home", tags=["home"])


@router.get(
    "/mission-control",
    summary="首页任务控制面板",
    description="返回3个核心功能（发布任务、邀请伙伴、追踪分账）的状态摘要数据",
)
def mission_control(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """首页3按钮聚焦模式的状态数据

    返回三个核心入口的上下文感知状态：
    - publish_task: 发布任务
    - invite_partner: 邀请伙伴
    - track_split: 追踪分账
    """
    user_id = current_user.id
    now = datetime.utcnow()

    # 1. 发布任务状态：用户已发布的产品数 + 是否有草稿
    published_count = (
        db.query(func.count(Product.id))
        .filter(
            Product.owner_id == user_id,
            ~Product.is_deleted.is_(True),
        )
        .scalar()
        or 0
    )

    # 2. 邀请伙伴状态：该用户推荐的下级数量
    subordinate_count = (
        db.query(func.count(User.id))
        .filter(
            User.referred_by == user_id,
        )
        .scalar()
        or 0
    )

    # 3. 追踪分账状态：待结算订单数 + 累计收益
    pending_settlement = (
        db.query(func.count(Order.id))
        .filter(
            Order.promoter_id == user_id,
            Order.status.in_(["paid", "shipped", "delivered"]),
        )
        .scalar()
        or 0
    )

    total_earnings_result = (
        db.query(func.sum(Order.commission_amount))
        .filter(
            Order.promoter_id == user_id,
            Order.status == "completed",
        )
        .scalar()
    )
    total_earnings = float(total_earnings_result) if total_earnings_result else 0.0

    return {
        "code": 200,
        "message": "success",
        "data": {
            "publish_task": {
                "label": "发布任务",
                "icon": "flame",
                "description": "创建分销/合作任务",
                "status": "active",
                "badge": str(published_count) if published_count > 0 else None,
                "action_hint": "发布新产品" if published_count == 0 else "继续发布",
                "sort_order": 1,
            },
            "invite_partner": {
                "label": "邀请伙伴",
                "icon": "handshake",
                "description": "发送邀请链接/二维码",
                "status": "active",
                "badge": str(subordinate_count) if subordinate_count > 0 else None,
                "action_hint": "立即邀请" if subordinate_count == 0 else f"已有{subordinate_count}位伙伴",
                "sort_order": 2,
            },
            "track_split": {
                "label": "追踪分账",
                "icon": "chart",
                "description": "查看收益/佣金/结算",
                "status": "active" if pending_settlement > 0 else "idle",
                "badge": str(pending_settlement) if pending_settlement > 0 else None,
                "action_hint": f"累计收益 ¥{total_earnings:.2f}",
                "sort_order": 3,
            },
        },
    }
