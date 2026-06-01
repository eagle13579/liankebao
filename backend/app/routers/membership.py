"""
会员系统路由
GET    /api/membership/tiers        — 会员等级信息+价格
POST   /api/membership/upgrade      — 升级会员（生成订单）
GET    /api/membership/status       — 当前会员状态
POST   /api/membership/credits/use  — 使用对接券
GET    /api/membership/credits      — 剩余对接券
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import MatchCreditLog, MembershipOrder, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/membership", tags=["会员"])

# ============================================================
# 会员等级定价配置
# ============================================================
MEMBERSHIP_TIERS = {
    "free": {
        "name": "免费会员",
        "price": 0,
        "duration_days": None,
        "match_credits": 3,
        "features": [
            "浏览产品和企业信息",
            "发布供需需求",
            "基础搜索功能",
            "每月3次对接机会",
        ],
    },
    "gold": {
        "name": "黄金会员",
        "price": 199.00,
        "duration_days": 365,
        "match_credits": 20,
        "features": [
            "所有免费会员权益",
            "无限次对接机会",
            "AI智能匹配推荐",
            "企业背景查询",
            "专属客服支持",
            "数据分析看板",
        ],
    },
    "diamond": {
        "name": "钻石会员",
        "price": 599.00,
        "duration_days": 365,
        "match_credits": 60,
        "features": [
            "所有黄金会员权益",
            "优先对接推荐",
            "线下活动优先参与",
            "商业情报推送",
            "一对一商务顾问",
            "品牌曝光加权",
        ],
    },
    "board": {
        "name": "董事会会员",
        "price": 2999.00,
        "duration_days": 365,
        "match_credits": 200,
        "features": [
            "所有钻石会员权益",
            "高端闭门对接会参与",
            "链客宝官方背书",
            "投资机构对接通道",
            "定制化商业方案",
            "年度CEO闭门晚宴邀请",
        ],
    },
}

# ============================================================
# Pydantic 请求/响应模型
# ============================================================


class UpgradeRequest(BaseModel):
    """升级会员请求"""

    tier: str = Field(..., pattern=r"^(gold|diamond|board)$", description="目标会员等级")
    payment_platform: str = Field(default="wxpay", pattern=r"^(wxpay|alipay)$")


class UseCreditRequest(BaseModel):
    """使用对接券请求"""

    event_id: int = Field(..., description="对接会活动ID")
    notes: str | None = None


# ============================================================
# API 端点
# ============================================================


@router.get("/tiers")
def list_tiers():
    """获取三层会员信息+价格（含免费层）"""
    tiers = []
    for tier_key in ["free", "gold", "diamond", "board"]:
        t = MEMBERSHIP_TIERS[tier_key]
        tiers.append(
            {
                "tier": tier_key,
                "name": t["name"],
                "price": t["price"],
                "duration_days": t["duration_days"],
                "match_credits": t["match_credits"],
                "features": t["features"],
            }
        )
    return {"code": 200, "message": "success", "data": tiers}


@router.post("/upgrade")
def upgrade_membership(
    req: UpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """升级会员 — 生成会员升级订单"""
    # 校验会员等级
    tier_config = MEMBERSHIP_TIERS.get(req.tier)
    if not tier_config:
        raise HTTPException(status_code=400, detail="无效的会员等级")

    # 检查是否已经是目标等级且未过期
    if (
        current_user.membership_tier == req.tier
        and current_user.membership_expires_at
        and current_user.membership_expires_at > datetime.utcnow()
    ):
        raise HTTPException(status_code=400, detail="您已经是该等级会员且仍在有效期内")

    # 创建订单
    order = MembershipOrder(
        user_id=current_user.id,
        tier=req.tier,
        amount=tier_config["price"],
        status="pending",
        payment_platform=req.payment_platform,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "code": 200,
        "message": "订单创建成功",
        "data": {
            "order_id": order.id,
            "tier": order.tier,
            "amount": order.amount,
            "status": order.status,
            "payment_platform": order.payment_platform,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
    }


@router.get("/status")
def membership_status(
    current_user: User = Depends(get_current_user),
):
    """当前会员状态"""
    now = datetime.utcnow()
    is_expired = bool(
        current_user.membership_expires_at
        and current_user.membership_expires_at < now
    )

    # 如果已过期，自动降级为 free
    effective_tier = current_user.membership_tier
    if is_expired and effective_tier != "free":
        effective_tier = "free"

    expires_at = current_user.membership_expires_at.isoformat() if current_user.membership_expires_at else None

    return {
        "code": 200,
        "message": "success",
        "data": {
            "user_id": current_user.id,
            "username": current_user.username,
            "membership_tier": effective_tier,
            "membership_expires_at": expires_at,
            "is_expired": is_expired,
            "match_credits": current_user.match_credits,
            "tier_info": MEMBERSHIP_TIERS.get(effective_tier, MEMBERSHIP_TIERS["free"]),
        },
    }


@router.post("/credits/use")
def use_match_credit(
    req: UseCreditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """使用对接券"""
    if current_user.match_credits < 1:
        raise HTTPException(status_code=400, detail="对接券不足，请升级会员获取更多对接券")

    # 扣除对接券
    current_user.match_credits -= 1

    # 记录日志
    log = MatchCreditLog(
        user_id=current_user.id,
        amount=-1,
        balance_after=current_user.match_credits,
        reason="use",
        related_type="matching_event",
        related_id=req.event_id,
    )
    db.add(log)
    db.commit()

    return {
        "code": 200,
        "message": "对接券使用成功",
        "data": {
            "remaining_credits": current_user.match_credits,
            "used_for_event_id": req.event_id,
        },
    }


@router.get("/credits")
def get_match_credits(
    current_user: User = Depends(get_current_user),
):
    """剩余对接券"""
    return {
        "code": 200,
        "message": "success",
        "data": {
            "match_credits": current_user.match_credits,
            "membership_tier": current_user.membership_tier,
        },
    }
