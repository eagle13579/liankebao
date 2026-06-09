"""
链客宝AI对账系统模块
==================

功能:
  1. 每日对账报表生成（订单数/金额/退款/净收入）
  2. 对账差异标记（Mock — 不依赖真实微信支付账单）
  3. 历史对账列表查询
  4. 对账详情查看

API:
  GET  /api/reconciliation/daily          — 生成/查询日报
  GET  /api/reconciliation/list           — 历史对账列表
  GET  /api/reconciliation/{report_id}    — 对账详情

注册方式（在 main.py 中）:
    import reconciliation as reconciliation_module
    app.include_router(reconciliation_module.router)
"""

import json
import logging
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, desc, func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import Base, get_db
from app.models import Order, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reconciliation", tags=["对账"])

# ============================================================
# 数据库模型
# ============================================================


class ReconciliationReport(Base):
    """对账报表"""

    __tablename__ = "reconciliation_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    report_date = Column(String(10), nullable=False, index=True, unique=True, comment="报表日期，格式 YYYY-MM-DD")
    total_orders = Column(Integer, nullable=False, default=0, comment="订单总数")
    total_amount = Column(Float, nullable=False, default=0.0, comment="订单总金额")
    total_refunds = Column(Integer, nullable=False, default=0, comment="退款单数")
    refund_amount = Column(Float, nullable=False, default=0.0, comment="退款总金额")
    net_income = Column(Float, nullable=False, default=0.0, comment="净收入（订单金额 - 退款）")
    platform_fee = Column(Float, nullable=False, default=0.0, comment="平台手续费估算")
    promoter_commission = Column(Float, nullable=False, default=0.0, comment="推广员分润")
    diff_count = Column(Integer, nullable=False, default=0, comment="差异笔数")
    diff_details = Column(Text, nullable=True, comment="差异详情（JSON）")
    status = Column(
        String(20),
        nullable=False,
        default="generated",
        comment="状态: generated(已生成)/verified(已核对)/mismatch(有差异)",
    )
    created_at = Column(DateTime, default=datetime.utcnow, comment="生成时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


# ============================================================
# Pydantic 模型
# ============================================================


class ReportItem(BaseModel):
    """对账报表条目"""

    id: int
    report_date: str
    total_orders: int
    total_amount: float
    total_refunds: int
    refund_amount: float
    net_income: float
    platform_fee: float
    promoter_commission: float
    diff_count: int
    diff_details: str | None = None
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ReportDetail(BaseModel):
    """对账详情"""

    report: ReportItem
    order_items: list[dict] = Field(default_factory=list, description="当日订单明细")
    diff_items: list[dict] = Field(default_factory=list, description="差异明细")


# ============================================================
# Mock 生成随机差异
# ============================================================


def _maybe_generate_mock_diff(order_total: float) -> dict | None:
    """
    随机模拟对账差异（Mock — 不依赖真实微信支付账单）。
    约 5% 概率生成一个差异项。
    """
    if random.random() > 0.05:
        return None

    diff_types = [
        ("订单金额不一致", lambda: {"order_amount": order_total, "platform_amount": round(order_total * 0.98, 2)}),
        ("订单状态不一致", lambda: {"order_status": "paid", "platform_status": "pending"}),
        ("退款金额不一致", lambda: {"order_refund": order_total, "platform_refund": round(order_total * 0.95, 2)}),
    ]
    diff_type, diff_gen = random.choice(diff_types)
    diff_data = diff_gen()
    return {
        "diff_type": diff_type,
        "diff_data": diff_data,
    }


# ============================================================
# 工具函数
# ============================================================


def _generate_daily_report(target_date: str, db: Session) -> dict:
    """
    生成指定日期的对账日报。

    数据来源:
      - 订单表（当日创建 + 当日支付/退款）
      - Mock 差异注入（模拟微信支付对账差异）

    返回: 报表数据字典
    """
    # 解析日期
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"日期格式错误: {target_date}，应为 YYYY-MM-DD")

    day_start = dt
    day_end = dt + timedelta(days=1)

    # 1. 统计当日订单
    orders_query = db.query(Order).filter(
        Order.created_at >= day_start,
        Order.created_at < day_end,
    )

    total_orders = orders_query.count()
    total_amount = orders_query.with_entities(func.coalesce(func.sum(Order.total_price), 0.0)).scalar()
    total_amount = round(float(total_amount), 2)

    # 2. 统计退款（状态为 refunded 的订单）
    refunds_query = db.query(Order).filter(
        Order.status == "refunded",
        Order.created_at >= day_start,
        Order.created_at < day_end,
    )
    total_refunds = refunds_query.count()
    refund_amount = refunds_query.with_entities(func.coalesce(func.sum(Order.total_price), 0.0)).scalar()
    refund_amount = round(float(refund_amount), 2)

    # 3. 计算净收入
    net_income = round(total_amount - refund_amount, 2)

    # 4. 平台手续费（Mock: 按 0.6% 估算）
    platform_fee = round(total_amount * 0.006, 2)

    # 5. 推广员分润
    commission_query = db.query(func.coalesce(func.sum(Order.commission), 0.0)).filter(
        Order.promoter_id.isnot(None),
        Order.created_at >= day_start,
        Order.created_at < day_end,
    )
    promoter_commission = round(float(commission_query.scalar()), 2)

    # 6. Mock 差异
    diff_details = []
    all_orders = orders_query.all()
    for order in all_orders:
        diff = _maybe_generate_mock_diff(float(order.total_price))
        if diff:
            diff["order_id"] = order.id
            diff["order_no"] = f"LK{order.id:08d}"
            diff_details.append(diff)

    diff_count = len(diff_details)
    status_val = "mismatch" if diff_count > 0 else "generated"

    return {
        "report_date": target_date,
        "total_orders": total_orders,
        "total_amount": total_amount,
        "total_refunds": total_refunds,
        "refund_amount": refund_amount,
        "net_income": net_income,
        "platform_fee": platform_fee,
        "promoter_commission": promoter_commission,
        "diff_count": diff_count,
        "diff_details": json.dumps(diff_details, ensure_ascii=False) if diff_details else None,
        "status": status_val,
    }


# ============================================================
# API 路由
# ============================================================


@router.get("/daily")
def get_or_generate_daily_report(
    report_date: str = Query(..., description="对账日期 YYYY-MM-DD"),
    force_regenerate: bool = Query(False, description="是否强制重新生成"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    生成/查询日报 (GET /api/reconciliation/daily)

    参数:
      - report_date: 对账日期 (YYYY-MM-DD)
      - force_regenerate: 为 true 时强制重新生成（覆盖已有报表）

    返回: 对账报表详情
    """
    # 先查询是否已有
    existing = db.query(ReconciliationReport).filter(ReconciliationReport.report_date == report_date).first()

    if existing and not force_regenerate:
        # 返回已有报表
        return {
            "code": 200,
            "message": "success",
            "data": ReportItem.model_validate(existing).model_dump(),
        }

    # 生成新报表
    report_data = _generate_daily_report(report_date, db)

    if existing and force_regenerate:
        # 更新已有报表
        for key, val in report_data.items():
            setattr(existing, key, val)
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        report = existing
    else:
        # 创建新报表
        report = ReconciliationReport(**report_data)
        db.add(report)
        db.commit()
        db.refresh(report)

    logger.info(
        "对账日报生成: date=%s, orders=%d, amount=%.2f, refunds=%d, diff=%d",
        report_date,
        report.total_orders,
        report.total_amount,
        report.total_refunds,
        report.diff_count,
    )

    return {
        "code": 200,
        "message": "success",
        "data": ReportItem.model_validate(report).model_dump(),
    }


@router.get("/list")
def list_reconciliation_reports(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status_filter: str | None = Query(None, description="按状态筛选: generated/verified/mismatch"),
    date_from: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    历史对账列表 (GET /api/reconciliation/list)
    """
    query = db.query(ReconciliationReport)

    if status_filter:
        query = query.filter(ReconciliationReport.status == status_filter)
    if date_from:
        query = query.filter(ReconciliationReport.report_date >= date_from)
    if date_to:
        query = query.filter(ReconciliationReport.report_date <= date_to)

    total = query.count()
    items = query.order_by(desc(ReconciliationReport.report_date)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [ReportItem.model_validate(i).model_dump() for i in items],
        },
    }


@router.get("/{report_id}")
def get_reconciliation_detail(
    report_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    对账详情 (GET /api/reconciliation/{report_id})

    返回:
      - report: 报表摘要
      - order_items: 当日订单明细（分页）
      - diff_items: 差异明细
    """
    report = db.query(ReconciliationReport).filter(ReconciliationReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="对账报表不存在")

    # 解析当日订单
    try:
        dt = datetime.strptime(report.report_date, "%Y-%m-%d")
    except ValueError:
        dt = datetime.utcnow()

    day_end = dt + timedelta(days=1)

    orders_query = (
        db.query(Order)
        .filter(
            Order.created_at >= dt,
            Order.created_at < day_end,
        )
        .order_by(Order.id.desc())
    )

    total_orders = orders_query.count()
    order_items = orders_query.offset((page - 1) * page_size).limit(page_size).all()

    # 解析差异详情
    diff_items = []
    if report.diff_details:
        try:
            diff_items = json.loads(report.diff_details)
        except (json.JSONDecodeError, TypeError):
            diff_items = []

    return {
        "code": 200,
        "message": "success",
        "data": {
            "report": ReportItem.model_validate(report).model_dump(),
            "order_items": [
                {
                    "id": o.id,
                    "user_id": o.user_id,
                    "product_id": o.product_id,
                    "total_price": o.total_price,
                    "status": o.status,
                    "commission": o.commission,
                    "promoter_id": o.promoter_id,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in order_items
            ],
            "order_pagination": {
                "total": total_orders,
                "page": page,
                "page_size": page_size,
            },
            "diff_items": diff_items,
        },
    }


@router.put("/{report_id}/verify")
def verify_reconciliation_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    标记对账报表为已核对 (PUT /api/reconciliation/{report_id}/verify)

    仅当 diff_count == 0 时可标记为 verified。
    有差异的报表需要先处理差异。
    """
    report = db.query(ReconciliationReport).filter(ReconciliationReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="对账报表不存在")

    if report.diff_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该报表有 {report.diff_count} 项差异未处理，请先处理差异后再核对",
        )

    report.status = "verified"
    report.updated_at = datetime.utcnow()
    db.commit()

    return {
        "code": 200,
        "message": "对账报表已标记为已核对",
        "data": ReportItem.model_validate(report).model_dump(),
    }


@router.get("/stats/summary")
def reconciliation_summary(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    对账汇总统计 (GET /api/reconciliation/stats/summary)

    返回所有对账报表的汇总数据。
    """
    reports = db.query(ReconciliationReport).all()

    total_reports = len(reports)
    total_orders = sum(r.total_orders for r in reports)
    total_amount = sum(r.total_amount for r in reports)
    total_refunds = sum(r.total_refunds for r in reports)
    total_refund_amount = sum(r.refund_amount for r in reports)
    total_net_income = sum(r.net_income for r in reports)
    total_diff = sum(r.diff_count for r in reports)
    mismatch_count = sum(1 for r in reports if r.status == "mismatch")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_reports": total_reports,
            "total_orders": round(total_orders, 2),
            "total_amount": round(total_amount, 2),
            "total_refunds": total_refunds,
            "total_refund_amount": round(total_refund_amount, 2),
            "total_net_income": round(total_net_income, 2),
            "total_diff_count": total_diff,
            "mismatch_report_count": mismatch_count,
        },
    }
