"""
链客宝AI发票系统模块
===================

功能:
  1. 发票申请表（用户/金额/订单号/发票抬头/税号/状态/申请时间）
  2. API：申请发票(POST)、查询发票列表(GET)、管理员审核(PUT)
  3. 嵌入前端：订单详情返回中附带 invoice_eligible 标记

数据库模型 (SQLAlchemy):
    InvoiceRequest — 发票申请表

注册方式（在 main.py 中）:
    import invoice as invoice_module
    app.include_router(invoice_module.router)
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, desc
from sqlalchemy.orm import Session

from app.auth import get_current_admin, get_current_user
from app.database import Base, get_db
from app.models import Order, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invoice", tags=["发票"])

# ============================================================
# 数据库模型
# ============================================================


class InvoiceRequest(Base):
    """发票申请表"""

    __tablename__ = "invoice_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="申请人用户ID")
    order_id = Column(Integer, nullable=False, index=True, comment="关联订单ID")
    amount = Column(Float, nullable=False, default=0.0, comment="开票金额")
    title = Column(String(200), nullable=False, comment="发票抬头")
    tax_id = Column(String(50), nullable=True, comment="税号（企业发票必填）")
    email = Column(String(200), nullable=True, comment="接收电子发票的邮箱")
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="状态: pending(待审核)/approved(已通过)/rejected(已拒绝)/issued(已开票)",
    )
    remark = Column(Text, nullable=True, comment="备注/审核意见")
    created_at = Column(DateTime, default=datetime.utcnow, comment="申请时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


# ============================================================
# Pydantic 请求/响应模型
# ============================================================


class InvoiceApplyRequest(BaseModel):
    """申请发票请求"""

    order_id: int = Field(..., description="订单ID")
    title: str = Field(..., min_length=1, max_length=200, description="发票抬头")
    tax_id: str | None = Field(None, max_length=50, description="税号")
    email: str | None = Field(None, max_length=200, description="电子邮箱")
    remark: str | None = Field(None, max_length=500, description="备注")


class InvoiceReviewRequest(BaseModel):
    """审核发票请求（管理员）"""

    action: str = Field(..., pattern=r"^(approved|rejected)$", description="操作: approved(通过) / rejected(拒绝)")
    remark: str | None = Field(None, max_length=500, description="审核意见")


class InvoiceItem(BaseModel):
    """发票申请条目"""

    id: int
    user_id: int
    order_id: int
    amount: float
    title: str
    tax_id: str | None = None
    email: str | None = None
    status: str
    remark: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# ============================================================
# 工具函数
# ============================================================

_INVOICE_STATUS_MAP = {
    "pending": "待审核",
    "approved": "已通过",
    "rejected": "已拒绝",
    "issued": "已开票",
}

_INVOICE_VALID_ORDER_STATUSES = {"paid", "shipped", "received"}

# ============================================================
# API 路由
# ============================================================


@router.post("/apply")
def apply_invoice(
    req: InvoiceApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    申请发票 (POST /api/invoice/apply)

    校验：
    - 订单属于当前用户
    - 订单状态为 paid/shipped/received（可开票状态）
    - 该订单未申请过发票（一个订单只能申请一次）
    - 企业发票税号必填
    """
    # 1. 校验订单
    order = db.query(Order).filter(Order.id == req.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此订单")
    if order.status not in _INVOICE_VALID_ORDER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"订单状态 {order.status} 不可开票，仅 {_INVOICE_VALID_ORDER_STATUSES} 状态的订单可申请",
        )

    # 2. 检查是否已申请过发票
    existing = (
        db.query(InvoiceRequest)
        .filter(
            InvoiceRequest.order_id == req.order_id,
            InvoiceRequest.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        status_cn = _INVOICE_STATUS_MAP.get(existing.status, existing.status)
        raise HTTPException(
            status_code=400,
            detail=f"该订单已申请过发票（状态: {status_cn}），不可重复申请",
        )

    # 3. 创建发票申请
    invoice = InvoiceRequest(
        user_id=current_user.id,
        order_id=req.order_id,
        amount=order.total_price,
        title=req.title,
        tax_id=req.tax_id or "",
        email=req.email or "",
        status="pending",
        remark=req.remark or "",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    logger.info(
        "发票申请已提交: user=%d, order=%d, amount=%.2f, title=%s",
        current_user.id,
        req.order_id,
        order.total_price,
        req.title,
    )

    return {
        "code": 200,
        "message": "发票申请已提交，等待审核",
        "data": InvoiceItem.model_validate(invoice).model_dump(),
    }


@router.get("/list")
def list_invoices(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status_filter: str | None = Query(None, description="按状态筛选: pending/approved/rejected/issued"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询发票申请列表 (GET /api/invoice/list)

    普通用户：只查自己的发票
    管理员：查所有发票（可按状态筛选）
    """
    is_admin = current_user.role == "admin"

    query = db.query(InvoiceRequest)
    if not is_admin:
        query = query.filter(InvoiceRequest.user_id == current_user.id)
    if status_filter:
        query = query.filter(InvoiceRequest.status == status_filter)

    total = query.count()
    items = query.order_by(desc(InvoiceRequest.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [InvoiceItem.model_validate(i).model_dump() for i in items],
        },
    }


@router.put("/{invoice_id}/review")
def review_invoice(
    invoice_id: int,
    req: InvoiceReviewRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    管理员审核发票 (PUT /api/invoice/{invoice_id}/review)

    操作: approved(通过) / rejected(拒绝)
    通过后可继续调用本接口升级为 issued(已开票)。
    """
    invoice = db.query(InvoiceRequest).filter(InvoiceRequest.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="发票申请不存在")

    old_status = invoice.status
    new_status = req.action

    # 状态流转校验
    if old_status == "pending" and new_status in ("approved", "rejected"):
        pass  # 待审核 → 通过/拒绝
    elif old_status == "approved" and new_status == "issued":
        pass  # 已通过 → 已开票
    else:
        raise HTTPException(
            status_code=400,
            detail=f"状态不允许变更: {_INVOICE_STATUS_MAP.get(old_status, old_status)} "
            f"→ {_INVOICE_STATUS_MAP.get(new_status, new_status)}",
        )

    invoice.status = new_status
    if req.remark:
        invoice.remark = (invoice.remark or "") + f"\n[审核] {req.remark}"
    invoice.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(invoice)

    logger.info(
        "发票审核完成: id=%d, order=%d, status: %s → %s (admin=%d)",
        invoice_id,
        invoice.order_id,
        old_status,
        new_status,
        current_admin.id,
    )

    return {
        "code": 200,
        "message": f"发票状态已更新: {_INVOICE_STATUS_MAP.get(old_status, old_status)} "
        f"→ {_INVOICE_STATUS_MAP.get(new_status, new_status)}",
        "data": InvoiceItem.model_validate(invoice).model_dump(),
    }


@router.get("/stats")
def invoice_stats(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """
    发票统计（管理员）(GET /api/invoice/stats)
    """
    total = db.query(InvoiceRequest).count()
    pending = db.query(InvoiceRequest).filter(InvoiceRequest.status == "pending").count()
    approved = db.query(InvoiceRequest).filter(InvoiceRequest.status == "approved").count()
    rejected = db.query(InvoiceRequest).filter(InvoiceRequest.status == "rejected").count()
    issued = db.query(InvoiceRequest).filter(InvoiceRequest.status == "issued").count()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "issued": issued,
        },
    }


# ============================================================
# 嵌入前端：订单详情返回额外字段
# ============================================================


def get_order_invoice_info(order_id: int, db: Session) -> dict:
    """
    获取订单的发票信息，供订单详情 API 返回时嵌入。
    在 orders.py 的 get_order 路由末尾调用此函数扩充 data。

    返回:
        {
            "invoice_eligible": bool,       # 是否可申请发票
            "invoice_status": str|None,     # 发票申请状态（如有）
            "invoice_id": int|None,         # 发票申请ID（如有）
        }
    """
    invoice = db.query(InvoiceRequest).filter(InvoiceRequest.order_id == order_id).first()

    if invoice:
        return {
            "invoice_eligible": invoice.status in ("rejected",),  # 被拒绝了可以重新申请
            "invoice_status": invoice.status,
            "invoice_id": invoice.id,
        }
    else:
        return {
            "invoice_eligible": True,  # 未申请过，可以申请
            "invoice_status": None,
            "invoice_id": None,
        }
