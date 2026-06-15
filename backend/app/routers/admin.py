"""管理后台路由：数据看板/用户管理/产品审核"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import Order, Product, User, Withdrawal
from app.rbac import require_roles
from app.schemas import (
    ApiResponse,
    DashboardResponse,
    ProductResponse,
    ProductReviewRequest,
    UpdateUserRoleRequest,
    UserResponse,
    WithdrawalResponse,
)

router = APIRouter(prefix="/api/admin", tags=["管理后台"])

# admin 全部接口都需要 admin 角色
_admin_only = require_roles(["admin"])


@router.get("/dashboard", response_model=ApiResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """获取管理后台数据看板"""
    total_users = db.query(User).filter(User.is_deleted == False).count()
    total_products = db.query(Product).filter(Product.is_deleted == False).count()
    total_orders = db.query(Order).filter(Order.is_deleted == False).count()
    total_revenue = (
        db.query(func.sum(Order.total_price))
        .filter(
            Order.status.in_(["paid", "shipped", "received"]),
            Order.is_deleted == False,
        )
        .scalar()
        or 0.0
    )

    # 今日订单
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = (
        db.query(Order)
        .filter(
            Order.created_at >= today,
            Order.is_deleted == False,
        )
        .count()
    )

    # 待审核产品
    pending_review = (
        db.query(Product)
        .filter(
            Product.status == "pending",
            Product.is_deleted == False,
        )
        .count()
    )

    # 待处理提现
    pending_withdrawals = (
        db.query(Withdrawal)
        .filter(
            Withdrawal.status == "pending",
            Withdrawal.is_deleted == False,
        )
        .count()
    )

    dashboard = DashboardResponse(
        total_users=total_users,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue,
        today_orders=today_orders,
        pending_review_products=pending_review,
        pending_withdrawals=pending_withdrawals,
    )

    return ApiResponse(code=200, message="success", data=dashboard.model_dump())


@router.get("/users", response_model=ApiResponse)
def list_users(
    search: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """获取用户列表（服务端分页 + 搜索）"""
    query = db.query(User).filter(User.is_deleted == False)

    if search:
        like = f"%{search}%"
        query = query.filter(User.name.ilike(like) | User.username.ilike(like) | User.phone.ilike(like))

    total = query.count()
    users = query.order_by(desc(User.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [UserResponse.model_validate(u).model_dump() for u in users],
        },
    )


@router.patch("/users/{user_id}/role", response_model=ApiResponse)
def update_user_role(
    user_id: int,
    req: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """管理员修改用户角色"""
    # 管理员不可修改自己的角色
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_deleted == False,
        )
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.role = req.role
    db.commit()
    db.refresh(user)

    return ApiResponse(
        code=200,
        message="角色更新成功",
        data=UserResponse.model_validate(user).model_dump(),
    )


@router.get("/products", response_model=ApiResponse)
def list_all_products(
    status: str = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """获取所有产品（管理后台）"""
    query = db.query(Product).filter(Product.is_deleted == False)
    if status:
        query = query.filter(Product.status == status)
    products = query.order_by(desc(Product.created_at)).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(products),
            "items": [ProductResponse.model_validate(p).model_dump() for p in products],
        },
    )


@router.put("/products/{product_id}/review", response_model=ApiResponse)
def review_product(
    product_id: int,
    req: ProductReviewRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """审核产品（通过/驳回）"""
    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.is_deleted == False,
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    if req.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="操作无效，请使用 approve 或 reject")

    product.status = "approved" if req.action == "approve" else "rejected"

    db.commit()
    db.refresh(product)

    message = "产品审核通过" if req.action == "approve" else "产品审核驳回"
    return ApiResponse(
        code=200,
        message=message,
        data=ProductResponse.model_validate(product).model_dump(),
    )


@router.get("/withdrawals", response_model=ApiResponse)
def list_withdrawals(
    status: str = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """获取提现申请列表"""
    query = db.query(Withdrawal).filter(Withdrawal.is_deleted == False)
    if status:
        query = query.filter(Withdrawal.status == status)
    withdrawals = query.order_by(desc(Withdrawal.created_at)).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(withdrawals),
            "items": [WithdrawalResponse.model_validate(w).model_dump() for w in withdrawals],
        },
    )


@router.put("/withdrawals/{withdrawal_id}/review", response_model=ApiResponse)
def review_withdrawal(
    withdrawal_id: int,
    req: ProductReviewRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """审核提现申请"""
    withdrawal = (
        db.query(Withdrawal)
        .filter(
            Withdrawal.id == withdrawal_id,
            Withdrawal.is_deleted == False,
        )
        .first()
    )
    if not withdrawal:
        raise HTTPException(status_code=404, detail="提现记录不存在")

    if req.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="操作无效，请使用 approve 或 reject")

    withdrawal.status = "approved" if req.action == "approve" else "rejected"

    db.commit()
    db.refresh(withdrawal)

    message = "提现审核通过" if req.action == "approve" else "提现审核驳回"
    return ApiResponse(
        code=200,
        message=message,
        data=WithdrawalResponse.model_validate(withdrawal).model_dump(),
    )
