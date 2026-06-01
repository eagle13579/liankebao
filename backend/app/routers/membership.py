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

MEMBERSHIP_TIERS = {
    "free": {
        "name": "免费会员",
        "price": 0,
        "duration_days": None,
        "match_credits": 3,
        "features": [
            "浏览产品和企业信息",
            "发布供需需求",
            "每月3次对接机会",
            "接收智能推荐",
            "查看平台成交案例",
        ],
    },
    "gold": {
        "name": "金卡会员",
        "price": 999.00,
        "duration_days": 365,
        "match_credits": 20,
        "features": [
            "所有免费会员权益",
            "无限发布供需需求",
            "查看对方联系方式",
            "AI匹配优先推荐",
            "每月5次定向对接机会",
            "企业身份认证标识",
            "首月不满意全额退款",
        ],
    },
    "diamond": {
        "name": "钻石会员",
        "price": 4999.00,
        "duration_days": 365,
        "match_credits": 60,
        "features": [
            "所有金卡会员权益",
            "线上闭门对接会（每季1次）",
            "专属撮合经理服务",
            "需求优先推荐TOP3",
            "企业深度认证+信用报告",
            "交易安全保障金",
            "CRM对接工具+合作追踪",
            "续费推荐返现15%",
        ],
    },
    "board": {
        "name": "私董会",
        "price": 19999.00,
        "duration_days": 365,
        "match_credits": 200,
        "features": [
            "所有钻石会员权益",
            "线下闭门私董会（每季1次）",
            "一对一商业诊断（季度）",
            "专家导师库（TOP100企业家）",
            "优先投资对接",
            "独家项目路演",
            "同行业不超过2家",
            "限额50席·创始人邀请制",
        ],
    },
}

TIER_ORDER = ["free", "gold", "diamond", "board"]


class UpgradeRequest(BaseModel):
    tier: str = Field(..., description="目标会员等级: gold/diamond/board")


class MembershipStatusResponse(BaseModel):
    tier: str
    expires_at: datetime | None = None
    is_active: bool
    match_credits: int


class CreditsResponse(BaseModel):
    credits: int
    tier: str


@router.get("/tiers")
def get_membership_tiers():
    """返回所有会员等级配置"""
    result = []
    for key in TIER_ORDER:
        if key in MEMBERSHIP_TIERS:
            tier = dict(MEMBERSHIP_TIERS[key])
            tier["tier"] = key
            result.append(tier)
    return {"code": 200, "message": "success", "data": result}


@router.get("/status", response_model=MembershipStatusResponse)
def get_membership_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的会员状态"""
    now = datetime.utcnow()
    is_active = False
    tier = current_user.membership_tier or "free"
    if tier != "free" and current_user.membership_expires_at:
        is_active = current_user.membership_expires_at > now
    return MembershipStatusResponse(
        tier=tier,
        expires_at=current_user.membership_expires_at,
        is_active=is_active,
        match_credits=current_user.match_credits or 0,
    )


@router.post("/upgrade")
def upgrade_membership(
    req: UpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """升级会员（生成订单，需支付后生效）"""
    if req.tier not in MEMBERSHIP_TIERS:
        raise HTTPException(status_code=400, detail=f"不支持的会员等级: {req.tier}")
    if req.tier == "free":
        raise HTTPException(status_code=400, detail="无法升级到免费会员")

    tier_config = MEMBERSHIP_TIERS[req.tier]
    price = tier_config["price"]

    from app.models import Order

    order = Order(
        user_id=current_user.id,
        product_id=None,
        quantity=1,
        total_price=price,
        status="pending",
        promoter_id=None,
        commission=0,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "tier": req.tier,
        "price": price,
        "status": "pending",
        "message": f"订单已创建，请完成支付以激活{tier_config['name']}",
    }


@router.post("/credits/use")
def use_match_credit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """使用1张对接券"""
    if current_user.match_credits <= 0:
        raise HTTPException(status_code=400, detail="对接券不足")
    current_user.match_credits -= 1
    log = MatchCreditLog(user_id=current_user.id, action="use", credits_before=current_user.match_credits + 1, credits_after=current_user.match_credits)
    db.add(log)
    db.commit()
    return {"code": 200, "credits": current_user.match_credits}


@router.get("/credits", response_model=CreditsResponse)
def get_match_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户剩余对接券数量"""
    return CreditsResponse(
        credits=current_user.match_credits or 0,
        tier=current_user.membership_tier or "free",
    )
