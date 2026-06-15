
"""
Member tier routes with full field mapping
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
router = APIRouter(prefix="/api/membership", tags=["membership"])

MEMBERSHIP_TIERS = {
    "free": {"name": "\u514d\u8d39\u4f1a\u5458", "price": 0, "duration_days": None, "match_credits": 3, "features": ["\u6d4f\u89c8\u4ea7\u54c1\u548c\u4f01\u4e1a\u4fe1\u606f", "\u53d1\u5e03\u4f9b\u9700\u9700\u6c42", "\u6bcf\u67083\u6b21\u5bf9\u63a5\u673a\u4f1a", "\u67e5\u770b\u5e73\u53f0\u6210\u4ea4\u6848\u4f8b"]},
    "gold": {"name": "\u91d1\u5361\u4f1a\u5458", "price": 999.00, "duration_days": 365, "match_credits": 20, "features": ["\u6240\u6709\u514d\u8d39\u4f1a\u5458\u6743\u76ca", "\u65e0\u9650\u53d1\u5e03\u4f9b\u9700\u9700\u6c42", "\u67e5\u770b\u5bf9\u65b9\u8054\u7cfb\u65b9\u5f0f", "AI\u5339\u914d\u4f18\u5148\u63a8\u8350", "\u6bcf\u67085\u6b21\u5b9a\u5411\u5bf9\u63a5\u673a\u4f1a", "\u4f01\u4e1a\u8eab\u4efd\u8ba4\u8bc1\u6807\u8bc6", "\u9996\u6708\u4e0d\u6ee1\u610f\u5168\u989d\u9000\u6b3e"]},
    "diamond": {"name": "\u94bb\u77f3\u4f1a\u5458", "price": 4999.00, "duration_days": 365, "match_credits": 60, "features": ["\u6240\u6709\u91d1\u5361\u4f1a\u5458\u6743\u76ca", "\u7ebf\u4e0a\u95ed\u95e8\u5bf9\u63a5\u4f1a\uff08\u6bcf\u5b631\u6b21\uff09", "\u4e13\u5c5e\u64ae\u5408\u7ecf\u7406\u670d\u52a1", "\u4f01\u4e1a\u6df1\u5ea6\u8ba4\u8bc1+\u4fe1\u7528\u62a5\u544a", "\u4ea4\u6613\u5b89\u5168\u4fdd\u969c\u91d1", "CRM\u5bf9\u63a5\u5de5\u5177+\u5408\u4f5c\u8ffd\u8e2a", "\u7eed\u8d39\u63a8\u8350\u8fd4\u73b015%"]},
    "board": {"name": "\u79c1\u8463\u4f1a", "price": 19999.00, "duration_days": 365, "match_credits": 200, "features": ["\u6240\u6709\u94bb\u77f3\u4f1a\u5458\u6743\u76ca", "\u7ebf\u4e0b\u95ed\u95e8\u79c1\u8463\u4f1a\uff08\u6bcf\u5b631\u6b21\uff09", "\u4e00\u5bf9\u4e00\u5546\u4e1a\u8bca\u65ad\uff08\u5b63\u5ea6\uff09", "\u4e13\u5bb6\u5bfc\u5e08\u5e93\uff08TOP100\u4f01\u4e1a\u5bb6\uff09", "\u4f18\u5148\u6295\u8d44\u5bf9\u63a5", "\u72ec\u5bb6\u9879\u76ee\u8def\u6f14", "\u540c\u884c\u4e1a\u4e0d\u8d85\u8fc72\u5bb6", "\u9650\u989d50\u5e2d\u00b7\u521b\u59cb\u4eba\u9080\u8bf7\u5236"]},
}

TIER_ORDER = ["free", "gold", "diamond", "board"]

class UpgradeRequest(BaseModel):
    tier: str = Field(..., description="target tier: gold/diamond/board")

class MembershipStatusResponse(BaseModel):
    level: str
    level_name: str
    expired_at: datetime | None = None
    remaining_coupons: int
    total_coupons_this_month: int
    trial_used: bool = False
    coupon_used_count: int = 0

class CreditsResponse(BaseModel):
    credits: int
    tier: str

@router.get("/tiers")
def get_membership_tiers():
    order_map = {"free": 1, "gold": 2, "diamond": 3, "board": 4}
    badge_map = {"free": "", "gold": "\u63a8\u8350", "diamond": "\u9ad8\u6027\u4ef7\u6bd4", "board": "\u5c0a\u4eab"}
    commission_map = {"free": 0.05, "gold": 0.08, "diamond": 0.12, "board": 0.15}
    result = []
    for idx, key in enumerate(TIER_ORDER):
        if key in MEMBERSHIP_TIERS:
            t = MEMBERSHIP_TIERS[key]
            result.append({
                "id": idx + 1,
                "name": t["name"],
                "level": key,
                "price": t["price"],
                "trial_price": t["price"] // 10 if t["price"] > 0 else 0,
                "对接券_per_month": t.get("match_credits", 0),
                "commission_rate": commission_map.get(key, 0.05),
                "features": t.get("features", []),
                "badge": badge_map.get(key, ""),
                "sort_order": order_map.get(key, 99),
            })
    return {"code": 200, "message": "success", "data": result}

@router.get("/status", response_model=MembershipStatusResponse)
def get_membership_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    is_active = False
    tier = current_user.membership_tier or "free"
    if tier != "free" and current_user.membership_expires_at:
        is_active = current_user.membership_expires_at > now
    tier_config = MEMBERSHIP_TIERS.get(tier, {})
    return MembershipStatusResponse(
        level=tier,
        level_name=tier_config.get("name", "免费会员"),
        expired_at=current_user.membership_expires_at,
        remaining_coupons=current_user.match_credits or 0,
        total_coupons_this_month=tier_config.get("match_credits", 3),
        trial_used=False,
        coupon_used_count=0,
    )

@router.post("/upgrade")
def upgrade_membership(req: UpgradeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.tier not in MEMBERSHIP_TIERS:
        raise HTTPException(status_code=400, detail=f"Unsupported tier: {req.tier}")
    if req.tier == "free":
        raise HTTPException(status_code=400, detail="Cannot upgrade to free")
    tier_config = MEMBERSHIP_TIERS[req.tier]
    price = tier_config["price"]
    from app.models import Order
    order = Order(user_id=current_user.id, product_id=None, quantity=1, total_price=price, status="pending", promoter_id=None, commission=0)
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "tier": req.tier, "price": price, "status": "pending", "message": f"Order created, pay to activate {tier_config['name']}"}

@router.post("/credits/use")
def use_match_credit(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.match_credits <= 0:
        raise HTTPException(status_code=400, detail="No credits left")
    current_user.match_credits -= 1
    log = MatchCreditLog(user_id=current_user.id, action="use", credits_before=current_user.match_credits + 1, credits_after=current_user.match_credits)
    db.add(log)
    db.commit()
    return {"code": 200, "credits": current_user.match_credits}

@router.get("/credits", response_model=CreditsResponse)
def get_match_credits(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return CreditsResponse(credits=current_user.match_credits or 0, tier=current_user.membership_tier or "free")
