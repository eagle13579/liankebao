"""
私董会（Private Board）路由
GET    /api/board/info       — 私董会产品介绍信息
POST   /api/board/apply      — 私董会申请（含企业信息、年营收、推荐人）
GET    /api/board/status     — 申请/会员状态
POST   /api/board/upgrade    — 付费升级（审核通过后支付）
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import PrivateBoardOrder, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/board", tags=["私董会"])

# ============================================================
# 私董会产品配置
# ============================================================
BOARD_PRODUCT_INFO = {
    "name": "私董会 Private Board",
    "subtitle": "链客宝AI最高端企业家社群 · 限量50席",
    "price": 19999.00,
    "quota": 50,
    "duration_days": 365,
    "access_requirements": "钻石会员升级 或 创始人邀请+审核",
    "exclusivity_policy": "同行业不超过2家，确保私密性与深度",
    "features": [
        {
            "icon": "users",
            "title": "线下闭门私董会",
            "description": "每季度1次高端闭门私董会，深度对话行业领袖",
        },
        {
            "icon": "briefcase",
            "title": "1v1商业诊断",
            "description": "每季度1次一对一商业诊断，由资深导师亲自把脉",
        },
        {
            "icon": "graduation-cap",
            "title": "专家导师库",
            "description": "对接各领域顶尖专家，为企业战略决策提供智囊支持",
        },
        {
            "icon": "handshake",
            "title": "优先投资对接",
            "description": "优秀项目优先推荐给合作投资机构，获得融资机会",
        },
    ],
    "mentors": [
        {
            "name": "张明远",
            "title": "前阿里副总裁",
            "expertise": "企业战略、数字化转型",
            "avatar": None,
        },
        {
            "name": "李思诚",
            "title": "红杉资本合伙人",
            "expertise": "投融资、商业模式设计",
            "avatar": None,
        },
        {
            "name": "王晓峰",
            "title": "连续创业者（已上市）",
            "expertise": "创业辅导、组织管理",
            "avatar": None,
        },
        {
            "name": "陈静宜",
            "title": "知名企业咨询顾问",
            "expertise": "品牌营销、增长策略",
            "avatar": None,
        },
    ],
    "annual_schedule": [
        {"quarter": "Q1", "theme": "战略破局 — 2026年度产业趋势与增长机会", "date": "2026-03"},
        {"quarter": "Q2", "theme": "资本对接 — 融资策略与投资人面对面", "date": "2026-06"},
        {"quarter": "Q3", "theme": "组织进化 — 从优秀到卓越的管理之道", "date": "2026-09"},
        {"quarter": "Q4", "theme": "年度盛典 — CEO闭门晚宴暨年度展望", "date": "2026-12"},
    ],
}

# ============================================================
# Pydantic 请求模型
# ============================================================


class BoardApplyRequest(BaseModel):
    """私董会申请请求"""

    company: str = Field(..., min_length=1, max_length=200, description="企业全称")
    revenue: str | None = Field(None, max_length=100, description="年营收")
    industry: str | None = Field(None, max_length=100, description="所属行业")
    position: str | None = Field(None, max_length=100, description="职位")
    referrer: str | None = Field(None, max_length=100, description="推荐人姓名/ID")
    referrer_notes: str | None = Field(None, max_length=500, description="推荐人备注")


class BoardUpgradeRequest(BaseModel):
    """私董会付费升级请求"""

    order_id: int = Field(..., description="私董会订单ID")
    payment_platform: str = Field(default="wxpay", pattern=r"^(wxpay|alipay)$")


# ============================================================
# API 端点
# ============================================================


@router.get("/info")
def get_board_info():
    """获取私董会产品介绍信息"""
    return {
        "code": 200,
        "message": "success",
        "data": BOARD_PRODUCT_INFO,
    }


@router.post("/apply")
def apply_private_board(
    req: BoardApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交私董会申请"""
    # 检查是否已有进行中的申请
    existing = (
        db.query(PrivateBoardOrder)
        .filter(
            PrivateBoardOrder.user_id == current_user.id,
            PrivateBoardOrder.status.in_(["pending", "approved"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"您已有{'待审核' if existing.status == 'pending' else '已通过'}的申请，无需重复提交",
        )

    # 检查是否为钻石会员（准入要求之一）
    if current_user.membership_tier not in ("diamond", "board"):
        raise HTTPException(
            status_code=400,
            detail="私董会仅限钻石会员及以上等级申请，请先升级会员",
        )

    # 创建申请订单
    order = PrivateBoardOrder(
        user_id=current_user.id,
        amount=BOARD_PRODUCT_INFO["price"],
        status="pending",
        company=req.company,
        revenue=req.revenue,
        industry=req.industry,
        position=req.position or current_user.position,
        referrer=req.referrer,
        referrer_notes=req.referrer_notes,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    logger.info(f"用户 {current_user.id} 提交私董会申请，订单ID={order.id}")

    return {
        "code": 200,
        "message": "申请提交成功，请等待审核",
        "data": {
            "order_id": order.id,
            "company": order.company,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
    }


@router.get("/status")
def get_board_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取私董会申请/会员状态"""
    # 查找最新的申请
    order = (
        db.query(PrivateBoardOrder)
        .filter(PrivateBoardOrder.user_id == current_user.id)
        .order_by(PrivateBoardOrder.created_at.desc())
        .first()
    )

    is_board_member = current_user.membership_tier == "board"
    is_expired = False
    if (
        is_board_member
        and current_user.membership_expires_at
        and current_user.membership_expires_at < datetime.utcnow()
    ):
        is_expired = True

    expires_at = current_user.membership_expires_at.isoformat() if current_user.membership_expires_at else None

    # 当前获批会员数量统计
    active_member_count = (
        db.query(PrivateBoardOrder)
        .filter(
            PrivateBoardOrder.status == "paid",
            PrivateBoardOrder.expires_at > datetime.utcnow(),
        )
        .count()
    )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "is_board_member": is_board_member and not is_expired,
            "is_expired": is_expired,
            "membership_expires_at": expires_at,
            "application": {
                "order_id": order.id if order else None,
                "status": order.status if order else None,
                "company": order.company if order else None,
                "created_at": order.created_at.isoformat() if order and order.created_at else None,
            }
            if order
            else None,
            "active_member_count": active_member_count,
            "total_quota": BOARD_PRODUCT_INFO["quota"],
            "remaining_seats": max(0, BOARD_PRODUCT_INFO["quota"] - active_member_count),
        },
    }


@router.post("/upgrade")
def upgrade_private_board(
    req: BoardUpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """私董会付费升级（审核通过后支付）"""
    # 查找订单
    order = (
        db.query(PrivateBoardOrder)
        .filter(
            PrivateBoardOrder.id == req.order_id,
            PrivateBoardOrder.user_id == current_user.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    if order.status != "approved":
        raise HTTPException(status_code=400, detail=f"订单状态为 {order.status}，请等待审核通过后支付")

    # 更新订单为支付状态
    order.status = "paid"
    order.pay_time = datetime.utcnow()
    order.transaction_id = f"BOARD_{order.id}_{int(datetime.utcnow().timestamp())}"

    # 更新用户的会员等级为 board
    current_user.membership_tier = "board"
    current_user.membership_expires_at = datetime.utcnow() + timedelta(days=BOARD_PRODUCT_INFO["duration_days"])
    order.expires_at = current_user.membership_expires_at

    db.commit()

    logger.info(f"用户 {current_user.id} 私董会升级成功，订单ID={order.id}")

    return {
        "code": 200,
        "message": "私董会升级成功",
        "data": {
            "order_id": order.id,
            "tier": "board",
            "amount": order.amount,
            "paid_at": order.pay_time.isoformat() if order.pay_time else None,
            "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        },
    }
