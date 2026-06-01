"""链客宝会员体系 API
会员等级、价格与权益配置
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/membership", tags=["会员体系"])

# ============================================================
# 会员等级配置
# ============================================================
# 价格定义（单位：人民币元/年）
MEMBERSHIP_TIERS = {
    "free": {
        "level": "free",
        "name": "免费会员",
        "name_en": "Free",
        "icon": "🆓",
        "price": 0,
        "currency": "CNY",
        "interval": "year",
        "features": [
            "浏览",
            "3次对接券",
            "基础搜索",
        ],
        "highlight": False,
        "sort_order": 0,
    },
    "gold": {
        "level": "gold",
        "name": "金卡会员",
        "name_en": "Gold",
        "icon": "🥇",
        "price": 999,
        "currency": "CNY",
        "interval": "year",
        "features": [
            "无限发布",
            "5次定向对接",
            "企业认证标识",
            "首月全额退",
        ],
        "highlight": True,
        "sort_order": 1,
    },
    "diamond": {
        "level": "diamond",
        "name": "钻石会员",
        "name_en": "Diamond",
        "icon": "💎",
        "price": 4999,
        "currency": "CNY",
        "interval": "year",
        "features": [
            "专属撮合经理",
            "线上闭门对接会",
            "交易安全金",
            "CRM工具",
            "续费返15%",
        ],
        "highlight": False,
        "sort_order": 2,
    },
    "board": {
        "level": "board",
        "name": "私董会",
        "name_en": "Board",
        "icon": "👑",
        "price": 19999,
        "currency": "CNY",
        "interval": "year",
        "features": [
            "线下闭门私董会",
            "1v1商业诊断",
            "导师库",
            "投资对接",
            "限额50席",
        ],
        "highlight": False,
        "sort_order": 3,
    },
}


@router.get("/tiers", summary="获取会员等级列表")
async def get_membership_tiers():
    """返回所有会员等级的价格和权益描述"""
    tiers = list(MEMBERSHIP_TIERS.values())
    tiers.sort(key=lambda t: t["sort_order"])
    return {
        "code": 200,
        "data": tiers,
    }


@router.get("/tiers/{level}", summary="获取指定会员等级信息")
async def get_membership_tier(level: str):
    """返回指定会员等级的详情"""
    tier = MEMBERSHIP_TIERS.get(level)
    if not tier:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"会员等级 '{level}' 不存在")
    return {
        "code": 200,
        "data": tier,
    }
