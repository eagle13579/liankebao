"""
M6 心智模型注入 — 单位经济门禁
=================================
链客宝单位经济模型仪表盘：在定价/运营面板中加入 LTV/CAC 计算模型。
将一堂 M6「单位经济门禁」模型产品化为可量化的单位经济仪表盘。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import Order, User, Product
from app.rbac import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/unit-economics", tags=["M6心智模型-单位经济门禁"])

_admin_only = require_roles(["admin"])


# ============================================================
# LTV/CAC 计算模型
# ============================================================

class UnitEconomicsSnapshot(Base):
    """单位经济快照 — 按周期保存 LTV/CAC 等关键指标"""
    __tablename__ = "unit_economics_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    period = Column(String(20), nullable=False, comment="统计周期: daily/weekly/monthly")
    period_start = Column(DateTime, nullable=False, comment="周期起始")
    period_end = Column(DateTime, nullable=False, comment="周期结束")

    # CAC (Customer Acquisition Cost)
    total_acquisition_cost = Column(Float, default=0.0, comment="总获客成本(元)")
    new_customers = Column(Integer, default=0, comment="新增客户数")
    cac = Column(Float, default=0.0, comment="CAC = 总获客成本 / 新增客户数")

    # LTV (Life Time Value)
    avg_order_value = Column(Float, default=0.0, comment="平均客单价")
    purchase_frequency = Column(Float, default=0.0, comment="人均购买频次")
    avg_customer_lifetime_months = Column(Float, default=0.0, comment="平均客户生命周期(月)")
    ltv = Column(Float, default=0.0, comment="LTV = 客单价 × 频次 × 生命周期")

    # 核心比率
    ltv_cac_ratio = Column(Float, default=0.0, comment="LTV/CAC 比值（>3为健康）")
    payback_months = Column(Float, default=0.0, comment="回本周期(月)")

    # 辅助指标
    total_revenue = Column(Float, default=0.0, comment="周期总收入")
    gross_margin = Column(Float, default=0.0, comment="毛利率(%)")
    churn_rate = Column(Float, default=0.0, comment="客户流失率(%)")

    created_at = Column(DateTime, default=datetime.utcnow)

    class Config:
        from_attributes = True


# ============================================================
# API 路由
# ============================================================

@router.get("/compute", summary="计算单位经济指标", description="根据订单/用户数据实时计算 LTV/CAC 等核心指标")
def compute_unit_economics(
    period: str = Query("monthly", description="统计周期: daily/weekly/monthly"),
    days: int = Query(90, description="回溯天数", ge=7, le=730),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """实时计算 LTV/CAC 等核心单位经济指标"""
    now = datetime.utcnow()
    since = now - timedelta(days=days)

    # --- CAC 计算 ---
    # 获客成本 = 营销费用 + 推广佣金（这里用订单折扣/推广费近似）
    new_customers = db.query(User).filter(
        User.is_deleted == False,
        User.created_at >= since,
    ).count()

    # 推广总支出（从 promoter 订单佣金估算）
    total_acquisition_cost = db.query(func.coalesce(func.sum(Order.total_price * 0.1), 0)).filter(
        Order.created_at >= since,
        Order.is_deleted == False,
        Order.promoter_id.isnot(None),
        Order.status.in_(["paid", "shipped", "received"]),
    ).scalar() or 0.0

    # 加营销费用估算（按总收入的20%估算）
    total_revenue = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(
        Order.created_at >= since,
        Order.is_deleted == False,
        Order.status.in_(["paid", "shipped", "received"]),
    ).scalar() or 0.0
    marketing_cost = total_revenue * 0.2

    total_acq_cost = float(total_acquisition_cost) + marketing_cost
    cac = round(total_acq_cost / new_customers, 2) if new_customers > 0 else 0.0

    # --- LTV 计算 ---
    # 平均客单价
    total_orders_count = db.query(func.count(Order.id)).filter(
        Order.created_at >= since,
        Order.is_deleted == False,
        Order.status.in_(["paid", "shipped", "received"]),
    ).scalar() or 0

    avg_order_value = round(float(total_revenue) / total_orders_count, 2) if total_orders_count > 0 else 0.0

    # 人均购买频次
    active_users = db.query(Order.user_id).filter(
        Order.created_at >= since,
        Order.is_deleted == False,
    ).distinct().count()
    purchase_frequency = round(total_orders_count / active_users, 2) if active_users > 0 else 0.0

    # 客户生命周期（月）— 从最早订单到最近订单的平均月数
    lifetime_data = db.query(
        func.min(Order.created_at).label("first_order"),
        func.max(Order.created_at).label("last_order"),
        Order.user_id,
    ).filter(
        Order.is_deleted == False,
    ).group_by(Order.user_id).having(func.count(Order.id) > 1).all()

    if lifetime_data:
        total_lifetime_days = sum(
            (max(r.last_order, r.first_order) - min(r.last_order, r.first_order)).days
            for r in lifetime_data
        )
        avg_lifetime_months = round(total_lifetime_days / len(lifetime_data) / 30.0, 1)
    else:
        avg_lifetime_months = 1.0  # 默认1个月

    ltv = round(avg_order_value * purchase_frequency * avg_lifetime_months, 2)

    # --- 核心比率 ---
    ltv_cac_ratio = round(ltv / cac, 2) if cac > 0 else 0.0
    payback_months = round(cac / (avg_order_value * purchase_frequency), 1) if (avg_order_value * purchase_frequency) > 0 else 0.0

    # 流失率(月) = 1 - (留存用户/总用户)^(1/月数)
    # 简化：上月不活跃用户占比
    last_month_start = now - timedelta(days=30)
    users_before = db.query(User).filter(User.created_at < last_month_start, User.is_deleted == False).count()
    active_last_month = db.query(Order.user_id).filter(
        Order.created_at >= last_month_start,
        Order.is_deleted == False,
    ).distinct().count()
    churn_rate = round(max(0, 1 - (active_last_month / max(users_before, 1))) * 100, 1)

    # 毛利率（简化：按50%估算）
    gross_margin = 50.0

    result = {
        "period": period,
        "days": days,
        "calculated_at": now.isoformat(),
        "cac_metrics": {
            "total_acquisition_cost": round(total_acq_cost, 2),
            "new_customers": new_customers,
            "cac": cac,
        },
        "ltv_metrics": {
            "avg_order_value": avg_order_value,
            "purchase_frequency": purchase_frequency,
            "avg_customer_lifetime_months": avg_lifetime_months,
            "ltv": ltv,
        },
        "core_ratios": {
            "ltv_cac_ratio": ltv_cac_ratio,
            "payback_months": payback_months,
            "health_status": "健康" if ltv_cac_ratio >= 3 else ("临界" if ltv_cac_ratio >= 1 else "危险"),
        },
        "auxiliary": {
            "total_revenue": round(float(total_revenue), 2),
            "gross_margin": gross_margin,
            "churn_rate": churn_rate,
        },
    }

    # 保存快照
    snapshot = UnitEconomicsSnapshot(
        period=period,
        period_start=since,
        period_end=now,
        total_acquisition_cost=total_acq_cost,
        new_customers=new_customers,
        cac=cac,
        avg_order_value=avg_order_value,
        purchase_frequency=purchase_frequency,
        avg_customer_lifetime_months=avg_lifetime_months,
        ltv=ltv,
        ltv_cac_ratio=ltv_cac_ratio,
        payback_months=payback_months,
        total_revenue=float(total_revenue),
        gross_margin=gross_margin,
        churn_rate=churn_rate,
    )
    db.add(snapshot)
    db.commit()

    logger.info(f"[M6单位经济] LTV={ltv} CAC={cac} 比值={ltv_cac_ratio} 状态={result['core_ratios']['health_status']}")
    return {"code": 200, "message": "success", "data": result}


@router.get("/snapshots", summary="历史快照", description="查看历史单位经济指标快照")
def list_snapshots(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """列出最近的历史快照"""
    snapshots = db.query(UnitEconomicsSnapshot).order_by(UnitEconomicsSnapshot.created_at.desc()).limit(limit).all()
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": s.id,
                "period": s.period,
                "period_start": s.period_start.isoformat(),
                "period_end": s.period_end.isoformat(),
                "cac": s.cac,
                "ltv": s.ltv,
                "ltv_cac_ratio": s.ltv_cac_ratio,
                "payback_months": s.payback_months,
                "churn_rate": s.churn_rate,
                "created_at": s.created_at.isoformat(),
            }
            for s in snapshots
        ],
    }


@router.get("/health-check", summary="单位经济健康检查", description="快速检查LTV/CAC比值是否达标，给出建议")
def unit_economics_health_check(
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """一键健康检查"""
    latest = db.query(UnitEconomicsSnapshot).order_by(UnitEconomicsSnapshot.created_at.desc()).first()
    if not latest:
        return {"code": 200, "message": "尚无快照数据，请先计算", "data": {"status": "unknown"}}

    ratio = latest.ltv_cac_ratio
    if ratio >= 3:
        status = "pass"
        advice = "单位经济模型健康，LTV/CAC > 3，可以加大获客投入"
    elif ratio >= 1:
        status = "warning"
        advice = f"LTV/CAC = {ratio}，处于临界区间，需优化获客效率或提升客单价"
    else:
        status = "danger"
        advice = f"LTV/CAC = {ratio}，单位经济不健康，必须立即优化：降低获客成本或提升客户价值"

    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": status,
            "ltv_cac_ratio": ratio,
            "ltv": latest.ltv,
            "cac": latest.cac,
            "payback_months": latest.payback_months,
            "churn_rate": latest.churn_rate,
            "advice": advice,
        },
    }
