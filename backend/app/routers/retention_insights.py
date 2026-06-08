"""
M7 心智模型注入 — 留存为王
=============================
链客宝留存分析引擎：在用户系统中加入深度留存分析指标。
将一堂 M7「留存为王」模型产品化为留存分析看板。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, User
from app.rbac import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/retention", tags=["M7心智模型-留存分析"])

_admin_only = require_roles(["admin"])


# ============================================================
# 留存分析 API
# ============================================================

@router.get("/cohort", summary="留存群组分析", description="按注册日期分群，计算各群组在后续周期的留存率")
def cohort_retention_analysis(
    cohort_period: str = Query("week", description="分群周期: day/week/month"),
    lookback_weeks: int = Query(12, description="回溯周数", ge=4, le=52),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """群组留存分析 — 核心留存看板"""
    now = datetime.utcnow()
    since = now - timedelta(weeks=lookback_weeks)

    # 获取所有用户及其注册时间
    users = db.query(User.id, User.created_at).filter(
        User.is_deleted == False,
        User.created_at >= since,
    ).all()

    # 获取所有订单（用户ID + 下单时间）
    orders = db.query(Order.user_id, Order.created_at).filter(
        Order.is_deleted == False,
        Order.created_at >= since,
    ).all()

    # 构建用户订单集合
    user_orders = {}
    for o in orders:
        uid = o.user_id
        if uid not in user_orders:
            user_orders[uid] = set()
        user_orders[uid].add(o.created_at.date())

    # 按周分群
    cohorts = {}
    for u in users:
        reg_date = u.created_at.date()
        # 计算从起始日期开始的周数偏移
        week_offset = (reg_date - since.date()).days // 7
        if week_offset not in cohorts:
            cohorts[week_offset] = {"users": [], "cohort_label": f"第{week_offset+1}周"}
        cohorts[week_offset]["users"].append((u.id, reg_date))

    # 计算各群组各周的留存
    cohort_matrix = []
    for week_num in sorted(cohorts.keys()):
        cohort = cohorts[week_num]
        total_users = len(cohort["users"])

        weekly_retention = []
        for offset in range(12):  # 跟踪12周
            start_of_week = since.date() + timedelta(weeks=week_num + offset)
            end_of_week = start_of_week + timedelta(days=7)

            active = 0
            for uid, reg_date in cohort["users"]:
                if uid in user_orders:
                    for order_date in user_orders[uid]:
                        if start_of_week <= order_date < end_of_week:
                            active += 1
                            break

            retention_rate = round(active / total_users * 100, 1) if total_users > 0 else 0.0
            weekly_retention.append({
                "week_offset": offset,
                "label": f"第{offset}周",
                "active_users": active,
                "retention_rate": retention_rate,
            })

        cohort_matrix.append({
            "cohort_label": cohort["cohort_label"],
            "total_users": total_users,
            "retention": weekly_retention,
        })

    return {
        "code": 200,
        "message": "success",
        "data": {
            "cohorts": cohort_matrix,
            "period": cohort_period,
            "lookback_weeks": lookback_weeks,
        },
    }


@router.get("/overview", summary="留存概览", description="核心留存指标：次日/7日/30日留存率")
def retention_overview(
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """计算次日/7日/30日留存率"""
    now = datetime.utcnow()

    def calc_retention(days_offset: int, label: str):
        """计算N日留存"""
        target_date = now - timedelta(days=days_offset)
        target_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        target_end = target_start + timedelta(days=1)

        # 目标日注册用户
        cohort_users = db.query(User.id).filter(
            User.is_deleted == False,
            User.created_at >= target_start,
            User.created_at < target_end,
        ).all()
        total = len(cohort_users)
        if total == 0:
            return {"label": label, "total_users": 0, "retained": 0, "retention_rate": 0.0}

        # 这些用户在后续 days_offset 天内有订单的
        retained = 0
        for (uid,) in cohort_users:
            has_order = db.query(Order.id).filter(
                Order.user_id == uid,
                Order.is_deleted == False,
                Order.created_at >= target_end,
                Order.created_at < target_end + timedelta(days=days_offset),
            ).first()
            if has_order:
                retained += 1

        rate = round(retained / total * 100, 1)
        return {"label": label, "total_users": total, "retained": retained, "retention_rate": rate}

    return {
        "code": 200,
        "message": "success",
        "data": {
            "d1": calc_retention(1, "次日留存"),
            "d7": calc_retention(7, "7日留存"),
            "d30": calc_retention(30, "30日留存"),
            "calculated_at": now.isoformat(),
        },
    }


@router.get("/churn-risk", summary="流失预警", description="识别高流失风险用户（7天未登录+0互动的用户）")
def churn_risk_analysis(
    days_since_last_active: int = Query(7, ge=3, le=90),
    min_orders: int = Query(1, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """流失风险用户识别"""
    cutoff = datetime.utcnow() - timedelta(days=days_since_last_active)

    # 找到在cutoff之后有订单的用户
    active_user_ids = set()
    active_orders = db.query(Order.user_id).filter(
        Order.created_at >= cutoff,
        Order.is_deleted == False,
    ).all()
    for (uid,) in active_orders:
        active_user_ids.add(uid)

    # 所有非删除用户
    all_users = db.query(User.id, User.name, User.company, User.created_at).filter(
        User.is_deleted == False,
    ).all()

    at_risk = []
    for uid, name, company, created_at in all_users:
        if uid not in active_user_ids:
            # 检查总订单数
            total_orders = db.query(func.count(Order.id)).filter(
                Order.user_id == uid,
                Order.is_deleted == False,
            ).scalar() or 0

            if total_orders <= min_orders:
                days_since_reg = (datetime.utcnow() - created_at).days
                at_risk.append({
                    "user_id": uid,
                    "name": name,
                    "company": company or "",
                    "registered_days": days_since_reg,
                    "total_orders": total_orders,
                    "risk_level": "高" if days_since_reg > 30 else "中",
                })

    # 按风险排序
    at_risk.sort(key=lambda x: x["registered_days"], reverse=True)

    logger.info(f"[M7留存] 流失预警: {len(at_risk)}个用户处于风险中")
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_at_risk": len(at_risk),
            "risk_users": at_risk[:50],  # 最多返回50条
            "days_since_last_active": days_since_last_active,
        },
    }


@router.get("/engagement", summary="用户活跃度分布", description="按活跃度分层展示用户分布")
def engagement_distribution(
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """按订单数分层展示用户活跃度"""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    # 30天内活跃用户
    active_30d = db.query(Order.user_id).filter(
        Order.created_at >= thirty_days_ago,
        Order.is_deleted == False,
    ).distinct().count()

    # 所有用户
    total_users = db.query(User).filter(User.is_deleted == False).count()

    # 按订单数量分层
    high_value = db.query(Order.user_id).filter(
        Order.is_deleted == False,
    ).group_by(Order.user_id).having(func.count(Order.id) >= 5).count()

    medium = db.query(Order.user_id).filter(
        Order.is_deleted == False,
    ).group_by(Order.user_id).having(
        func.count(Order.id) >= 2,
        func.count(Order.id) < 5,
    ).count()

    low = db.query(Order.user_id).filter(
        Order.is_deleted == False,
    ).group_by(Order.user_id).having(func.count(Order.id) == 1).count()

    dormant = total_users - high_value - medium - low

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_users": total_users,
            "active_30d": active_30d,
            "active_30d_rate": round(active_30d / max(total_users, 1) * 100, 1),
            "engagement_tiers": {
                "high_value": max(0, high_value),
                "medium": max(0, medium),
                "low": max(0, low),
                "dormant": max(0, dormant),
            },
        },
    }
