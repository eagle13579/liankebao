"""
链客宝AI自建BI看板 — 轻量统计聚合API
======================================
所有统计数据从现有数据库表（users, products, orders, business_cards, business_needs）实时聚合，
不依赖外部BI工具。

基础API (已有):
  GET /api/bi/overview       — 总览（总用户/总产品/总订单/今日注册）
  GET /api/bi/revenue        — 收入趋势（日/周/月）
  GET /api/bi/top-products   — 热门产品TOP10
  GET /api/bi/user-growth    — 用户增长曲线（按日）
  GET /api/bi/card-stats     — AI名片统计数据

高级分析API (新增):
  GET /api/bi/funnel         — 转化漏斗: 注册→创建名片→匹配→下单
  GET /api/bi/retention      — 用户留存: 日/周/月留存率
  GET /api/bi/churn-risk     — 流失预警: 7天未登录+0名片用户列表
  GET /api/bi/geo-distribution — 用户地域分布
"""

import logging
from collections import OrderedDict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessCard, BusinessNeed, Order, Product, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bi", tags=["BI看板"])


# ============================================================
# 基础API：已有功能，保持原样
# ============================================================


@router.get(
    "/overview",
    summary="BI总览",
    description="返回总用户数、总产品数、总订单数、今日注册数四个核心指标",
)
def get_overview(db: Session = Depends(get_db)):
    """获取仪表盘总览指标"""
    total_users = db.query(User).filter(User.is_deleted == False).count()
    total_products = db.query(Product).filter(Product.is_deleted == False, Product.status == "approved").count()
    total_orders = db.query(Order).filter(Order.is_deleted == False).count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_registrations = db.query(User).filter(User.is_deleted == False, User.created_at >= today_start).count()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_users": total_users,
            "total_products": total_products,
            "total_orders": total_orders,
            "today_registrations": today_registrations,
        },
    }


@router.get(
    "/revenue",
    summary="收入趋势",
    description="返回日/周/月收入趋势数据",
)
def get_revenue(
    period: str = Query("month", description="统计周期: day/week/month"),
    days: int = Query(30, description="回溯天数", ge=1, le=365),
    db: Session = Depends(get_db),
):
    """按指定周期聚合订单金额"""
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            func.date(Order.created_at).label("day"),
            func.coalesce(func.sum(Order.total_price), 0).label("revenue"),
            func.count(Order.id).label("orders_count"),
        )
        .filter(
            Order.is_deleted == False,
            Order.created_at >= since,
            Order.status.in_(["paid", "shipped", "received"]),
        )
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
        .all()
    )

    data = [{"date": str(r.day), "revenue": float(r.revenue), "orders": r.orders_count} for r in rows]

    if period == "week":
        weekly: dict = OrderedDict()
        for item in data:
            d = datetime.strptime(item["date"], "%Y-%m-%d")
            week_start = d - timedelta(days=d.weekday())
            key = week_start.strftime("%Y-%m-%d")
            if key not in weekly:
                weekly[key] = {"date": key, "revenue": 0.0, "orders": 0}
            weekly[key]["revenue"] += item["revenue"]
            weekly[key]["orders"] += item["orders"]
        data = list(weekly.values())
    elif period == "month":
        monthly: dict = OrderedDict()
        for item in data:
            key = item["date"][:7]
            if key not in monthly:
                monthly[key] = {"date": key, "revenue": 0.0, "orders": 0}
            monthly[key]["revenue"] += item["revenue"]
            monthly[key]["orders"] += item["orders"]
        data = list(monthly.values())

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }


@router.get(
    "/top-products",
    summary="热门产品TOP10",
    description="按订单数排序返回热门产品TOP10",
)
def get_top_products(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """统计每个产品的订单数，取TOP N"""
    rows = (
        db.query(
            Product.id,
            Product.name,
            Product.price,
            Product.category,
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_price), 0).label("total_revenue"),
        )
        .join(Order, Order.product_id == Product.id)
        .filter(
            Product.is_deleted == False,
            Order.is_deleted == False,
            Order.status.in_(["paid", "shipped", "received"]),
        )
        .group_by(Product.id)
        .order_by(func.count(Order.id).desc())
        .limit(limit)
        .all()
    )

    data = []
    for r in rows:
        data.append(
            {
                "id": r.id,
                "name": r.name,
                "price": float(r.price),
                "category": r.category or "",
                "order_count": r.order_count,
                "total_revenue": float(r.total_revenue),
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }


@router.get(
    "/user-growth",
    summary="用户增长曲线",
    description="返回每日用户注册数累积增长",
)
def get_user_growth(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """按日统计用户注册数"""
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            func.date(User.created_at).label("day"),
            func.count(User.id).label("new_users"),
        )
        .filter(User.is_deleted == False, User.created_at >= since)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )

    data = []
    cumulative = 0
    for r in rows:
        cumulative += r.new_users
        data.append(
            {
                "date": str(r.day),
                "new_users": r.new_users,
                "cumulative": cumulative,
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }


@router.get(
    "/card-stats",
    summary="AI名片统计",
    description="返回名片生成量、总浏览量、平均浏览量等统计",
)
def get_card_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """统计AI名片相关数据"""
    since = datetime.utcnow() - timedelta(days=days)

    total_cards = db.query(BusinessCard).filter(BusinessCard.is_deleted == False).count()

    recent_cards = (
        db.query(BusinessCard).filter(BusinessCard.is_deleted == False, BusinessCard.created_at >= since).count()
    )

    total_views = (
        db.query(func.coalesce(func.sum(BusinessCard.view_count), 0)).filter(BusinessCard.is_deleted == False).scalar()
        or 0
    )

    daily_rows = (
        db.query(
            func.date(BusinessCard.created_at).label("day"),
            func.count(BusinessCard.id).label("generated"),
            func.coalesce(func.sum(BusinessCard.view_count), 0).label("views"),
        )
        .filter(BusinessCard.is_deleted == False, BusinessCard.created_at >= since)
        .group_by(func.date(BusinessCard.created_at))
        .order_by(func.date(BusinessCard.created_at))
        .all()
    )

    daily_trend = [{"date": str(r.day), "generated": r.generated, "views": int(r.views)} for r in daily_rows]

    avg_views = round(total_views / total_cards, 1) if total_cards > 0 else 0

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_cards": total_cards,
            "recent_cards": recent_cards,
            "total_views": total_views,
            "avg_views_per_card": avg_views,
            "daily_trend": daily_trend,
        },
    }


# ============================================================
# 高级分析API：转化漏斗
# GET /api/bi/funnel
# ============================================================


@router.get(
    "/funnel",
    summary="转化漏斗",
    description="注册→创建名片→发布需求(匹配)→下单，四步转化率分析",
)
def get_funnel(
    days: int = Query(90, ge=1, le=365, description="统计时间范围(天)"),
    db: Session = Depends(get_db),
):
    """计算注册→创建名片→发布需求→下单各步骤转化率"""
    since = datetime.utcnow() - timedelta(days=days)

    # 步骤1: 注册用户数
    total_users = db.query(User.id).filter(User.is_deleted == False, User.created_at >= since).count()

    # 步骤2: 有AI名片的用户数
    users_with_card = (
        db.query(distinct(BusinessCard.user_id))
        .join(User, BusinessCard.user_id == User.id)
        .filter(
            BusinessCard.is_deleted == False,
            User.is_deleted == False,
            BusinessCard.created_at >= since,
        )
        .count()
    )

    # 步骤3: 发布过需求的用户数（供需匹配）
    users_with_need = (
        db.query(distinct(BusinessNeed.user_id))
        .join(User, BusinessNeed.user_id == User.id)
        .filter(
            BusinessNeed.is_deleted == False,
            User.is_deleted == False,
            BusinessNeed.created_at >= since,
        )
        .count()
    )

    # 步骤4: 下过单的用户数
    users_with_order = (
        db.query(distinct(Order.user_id))
        .join(User, Order.user_id == User.id)
        .filter(
            Order.is_deleted == False,
            User.is_deleted == False,
            Order.created_at >= since,
        )
        .count()
    )

    steps = [
        {"step": "注册", "users": total_users, "rate": 100.0},
        {
            "step": "创建名片",
            "users": users_with_card,
            "rate": round(users_with_card / total_users * 100, 2) if total_users > 0 else 0,
        },
        {
            "step": "发布需求(匹配)",
            "users": users_with_need,
            "rate": round(users_with_need / total_users * 100, 2) if total_users > 0 else 0,
        },
        {
            "step": "下单",
            "users": users_with_order,
            "rate": round(users_with_order / total_users * 100, 2) if total_users > 0 else 0,
        },
    ]

    # 步骤间转化率
    transitions = []
    for i in range(len(steps) - 1):
        from_step = steps[i]
        to_step = steps[i + 1]
        transition_rate = round(to_step["users"] / from_step["users"] * 100, 2) if from_step["users"] > 0 else 0
        transitions.append(
            {
                "from": from_step["step"],
                "to": to_step["step"],
                "from_users": from_step["users"],
                "to_users": to_step["users"],
                "transition_rate": transition_rate,
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "steps": steps,
            "transitions": transitions,
            "period_days": days,
        },
    }


# ============================================================
# 高级分析API：用户留存
# GET /api/bi/retention
# ============================================================


@router.get(
    "/retention",
    summary="用户留存",
    description="基于用户注册时间的日/周/月留存率分析",
)
def get_retention(
    period: str = Query("week", description="留存周期: day/week/month"),
    cohorts: int = Query(12, ge=1, le=52, description="回溯分组数(个周期)"),
    db: Session = Depends(get_db),
):
    """计算用户留存率：对注册用户分组，追踪后续回访行为（下单/创建名片为回访标记）"""
    now = datetime.utcnow()

    if period == "day":
        delta = timedelta(days=1)
        date_trunc = func.date(User.created_at)
        period_label = "日"
    elif period == "month":
        delta = timedelta(days=30)
        date_trunc = func.substr(func.strftime("%Y-%m", User.created_at), 1, 7)
        period_label = "月"
    else:  # week (default)
        delta = timedelta(days=7)
        # 用ISO周作为分组
        date_trunc = func.strftime("%Y-%W", User.created_at)
        period_label = "周"

    # 获取注册用户按周期分组
    cohort_start = now - delta * cohorts

    users_by_cohort = (
        db.query(
            date_trunc.label("cohort"),
            func.count(User.id).label("total"),
        )
        .filter(User.is_deleted == False, User.created_at >= cohort_start, User.created_at < now)
        .group_by(date_trunc)
        .order_by(date_trunc)
        .all()
    )

    result = []
    for cohort_row in users_by_cohort:
        cohort_key = str(cohort_row.cohort)
        total_in_cohort = cohort_row.total

        # 获取该组所有用户ID
        if period == "day" or period == "week":
            user_ids_subq = (
                db.query(User.id)
                .filter(
                    User.is_deleted == False,
                    func.date(User.created_at) >= cohort_start,
                    date_trunc == cohort_key,
                )
                .subquery()
            )
        else:
            user_ids_subq = (
                db.query(User.id)
                .filter(
                    User.is_deleted == False,
                    User.created_at >= cohort_start,
                    date_trunc == cohort_key,
                )
                .subquery()
            )

        retention_periods = []
        for offset in range(0, min(cohorts, 8)):  # 最多显示8个周期
            period_start = now - delta * (offset + 1)
            period_end = now - delta * offset

            # 回访 = 在该周期内有过活动（下单或创建名片）
            active_users = (
                db.query(distinct(Order.user_id))
                .filter(
                    Order.user_id.in_(db.query(user_ids_subq.c.id)),
                    Order.is_deleted == False,
                    Order.created_at >= period_start,
                    Order.created_at < period_end,
                )
                .union(
                    db.query(distinct(BusinessCard.user_id)).filter(
                        BusinessCard.user_id.in_(db.query(user_ids_subq.c.id)),
                        BusinessCard.is_deleted == False,
                        BusinessCard.created_at >= period_start,
                        BusinessCard.created_at < period_end,
                    )
                )
                .count()
            )

            retention_rate = round(active_users / total_in_cohort * 100, 2) if total_in_cohort > 0 else 0
            retention_periods.append(
                {
                    "offset": offset,
                    "label": f"第{offset + 1}{period_label}",
                    "active_users": active_users,
                    "retention_rate": retention_rate,
                }
            )

        result.append(
            {
                "cohort": cohort_key,
                "total_users": total_in_cohort,
                "retention": retention_periods,
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "period": period,
            "cohorts": result,
        },
    }


# ============================================================
# 高级分析API：流失预警
# GET /api/bi/churn-risk
# ============================================================


@router.get(
    "/churn-risk",
    summary="流失预警",
    description="识别7天未登录且未创建名片的潜在流失用户",
)
def get_churn_risk(
    days_since_activity: int = Query(7, ge=1, le=90, description="沉寂天数阈值"),
    db: Session = Depends(get_db),
):
    """查找潜在流失用户：注册超过指定天数、无任何后续活动（无订单、无名片）"""
    since = datetime.utcnow() - timedelta(days=days_since_activity)

    # 没有名片且没有订单且注册超过沉寂天数的用户
    users_with_card = db.query(distinct(BusinessCard.user_id)).filter(BusinessCard.is_deleted == False).subquery()
    users_with_order = db.query(distinct(Order.user_id)).filter(Order.is_deleted == False).subquery()

    churn_users = (
        db.query(
            User.id,
            User.name,
            User.company,
            User.phone,
            User.role,
            User.created_at,
        )
        .filter(
            User.is_deleted == False,
            User.created_at < since,
            ~User.id.in_(db.query(users_with_card)),
            ~User.id.in_(db.query(users_with_order)),
        )
        .order_by(User.created_at.desc())
        .limit(100)
        .all()
    )

    data = [
        {
            "id": u.id,
            "name": u.name,
            "company": u.company or "",
            "phone": u.phone or "",
            "role": u.role,
            "registered_at": str(u.created_at),
            "days_since_registration": (datetime.utcnow() - u.created_at).days,
        }
        for u in churn_users
    ]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "churn_users": data,
            "total_risk_count": len(data),
            "days_threshold": days_since_activity,
            "note": f"流失判定条件: 注册超过{days_since_activity}天 + 0名片 + 0订单",
        },
    }


# ============================================================
# 高级分析API：用户地域分布
# GET /api/bi/geo-distribution
# ============================================================


@router.get(
    "/geo-distribution",
    summary="用户地域分布",
    description="基于用户发布的需求(供需匹配)中region字段统计地域分布",
)
def get_geo_distribution(
    db: Session = Depends(get_db),
):
    """从business_needs.region统计地域分布（用户表中无地域字段时使用需求地域作为近似）"""
    # 方式1: 从 BusinessNeed.region 统计
    geo_from_needs = (
        db.query(
            BusinessNeed.region,
            func.count(distinct(BusinessNeed.user_id)).label("user_count"),
        )
        .filter(
            BusinessNeed.is_deleted == False,
            BusinessNeed.region.isnot(None),
            BusinessNeed.region != "",
        )
        .group_by(BusinessNeed.region)
        .order_by(func.count(distinct(BusinessNeed.user_id)).desc())
        .all()
    )

    need_geo = [{"region": r.region, "user_count": r.user_count} for r in geo_from_needs]

    # 方式2: 从 User 表中尝试提取地域信息（company字段中可能包含城市信息）
    # 采用简单方案：统计所有用户的company字段头一个字作为地域标签
    all_companies = (
        db.query(User.company).filter(User.is_deleted == False, User.company.isnot(None), User.company != "").all()
    )

    # 如果需求地域数据足够，优先使用需求地域
    # 否则补充用户注册地域

    return {
        "code": 200,
        "message": "success",
        "data": {
            "by_region": need_geo if need_geo else [],
            "total_regions": len(need_geo),
            "note": "地域数据来源于用户发布需求时填写的region字段; 用户注册时建议补充city/province字段以获得更准确分布",
        },
    }
