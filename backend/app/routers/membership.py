"""
链客宝 - 会员与额度路由（轻量版）
================================
提供与 /d/链客宝/backend/app/routers/membership.py 相同的 API 接口。

API:
  GET  /api/membership/credits     — 获取当前用户剩余额度
  GET  /api/membership/status      — 获取会员状态（含额度信息）
  POST /api/membership/credits/use — 消耗一次匹配额度（402检查）
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessCard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/membership", tags=["会员与额度（轻量版）"])

# ── 会员等级配置 ──

MEMBERSHIP_TIERS = {
    "free": {"name": "免费会员", "match_credits": 3},
    "gold": {"name": "金卡会员", "match_credits": 20},
    "diamond": {"name": "钻石会员", "match_credits": 60},
    "board": {"name": "私董会", "match_credits": 200},
}

# ── 额度存储（TODO: 迁移至数据库 User.match_credits） ──

_CREDITS_STORE: dict[int, int] = {}  # {user_id: remaining_credits}
_CREDIT_LOGS: list[dict] = []  # 额度消耗日志


class CreditsResponse(BaseModel):
    credits: int
    tier: str


class MembershipStatusResponse(BaseModel):
    level: str
    level_name: str
    expired_at: Optional[str] = None
    remaining_coupons: int
    total_coupons_this_month: int
    trial_used: bool = False
    coupon_used_count: int = 0


class CreditsUseResponse(BaseModel):
    code: int = 200
    credits: int
    message: str = "success"


# ── 辅助函数 ──


def _get_credits(user_id: int) -> int:
    """获取用户剩余额度"""
    if user_id not in _CREDITS_STORE:
        _CREDITS_STORE[user_id] = MEMBERSHIP_TIERS["free"]["match_credits"]
    return _CREDITS_STORE[user_id]


def _get_tier(user_id: int) -> str:
    """获取用户会员等级（简化版总是 free）"""
    return "free"


# ── API 端点 ──


@router.get("/credits", response_model=CreditsResponse)
def get_match_credits(
    user_id: int = Query(0, description="用户ID（0=默认用户）"),
    db: Session = Depends(get_db),
):
    """获取当前用户剩余匹配额度"""
    uid = user_id or 1
    credits = _get_credits(uid)
    tier = _get_tier(uid)
    return CreditsResponse(credits=credits, tier=tier)


@router.get("/status", response_model=MembershipStatusResponse)
def get_membership_status(
    user_id: int = Query(0, description="用户ID（0=默认用户）"),
    db: Session = Depends(get_db),
):
    """获取会员状态信息"""
    uid = user_id or 1
    tier = _get_tier(uid)
    tier_config = MEMBERSHIP_TIERS.get(tier, MEMBERSHIP_TIERS["free"])
    credits = _get_credits(uid)
    total_monthly = tier_config["match_credits"]
    used = max(0, total_monthly - credits)

    return MembershipStatusResponse(
        level=tier,
        level_name=tier_config["name"],
        expired_at=None,
        remaining_coupons=credits,
        total_coupons_this_month=total_monthly,
        trial_used=False,
        coupon_used_count=used,
    )


@router.post("/credits/use", response_model=CreditsUseResponse)
def use_match_credit(
    user_id: int = Query(0, description="用户ID（0=默认用户）"),
    db: Session = Depends(get_db),
):
    """消耗一次匹配额度（402检查）"""
    uid = user_id or 1
    current = _get_credits(uid)

    if current <= 0:
        raise HTTPException(
            status_code=402,
            detail="匹配额度不足，请充值后继续",
        )

    # 扣减
    _CREDITS_STORE[uid] = current - 1
    after = _CREDITS_STORE[uid]

    # 记录日志
    _CREDIT_LOGS.append({
        "user_id": uid,
        "amount": -1,
        "balance_after": after,
        "reason": "use",
        "created_at": datetime.utcnow().isoformat() + "Z",
    })

    logger.info(f"额度消耗: user_id={uid}, before={current}, after={after}")
    return CreditsUseResponse(credits=after, message="success")


@router.get("/credits/logs")
def get_credit_logs(
    user_id: int = Query(0, description="用户ID（0=默认用户）"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取额度消耗日志"""
    uid = user_id or 1
    logs = [log for log in _CREDIT_LOGS if log["user_id"] == uid]
    return {
        "code": 200,
        "data": logs[-limit:][::-1],  # 最新的在前
        "total": len(logs),
    }


# ── 启动提示 ──

print("[Membership] 会员与额度路由已加载 ✓")
print("[Membership] 端点: GET  /api/membership/credits")
print("[Membership] 端点: GET  /api/membership/status")
print("[Membership] 端点: POST /api/membership/credits/use")
print("[Membership] 端点: GET  /api/membership/credits/logs")
print("[Membership] TODO: 迁移额度存储至数据库 User.match_credits 字段")
