"""订单路由：创建订单/查看订单/更新订单状态"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Product, Order
from app.schemas import (
    ApiResponse, OrderCreate, OrderStatusRequest, OrderResponse,
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/orders", tags=["订单"])


@router.post("", response_model=ApiResponse)
def create_order(req: OrderCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """创建订单"""
    # 验证产品
    product = db.query(Product).filter(Product.id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    if product.status != "approved":
        raise HTTPException(status_code=400, detail="产品未上架")
    if product.stock < req.quantity:
        raise HTTPException(status_code=400, detail="库存不足")

    # 计算价格
    total_price = product.price * req.quantity
    commission = 0.0

    # 如果有推广员，计算分润
    promoter = None
    if req.promoter_id:
        promoter = db.query(User).filter(
            User.id == req.promoter_id,
            User.role == "promoter",
        ).first()
        if not promoter:
            raise HTTPException(status_code=400, detail="推广员不存在")
        # 推广员分润 = earn_per_share * 数量 * 50%
        commission = product.earn_per_share * req.quantity * 0.5

    # 扣减库存
    product.stock -= req.quantity

    # 创建订单
    order = Order(
        user_id=current_user.id,
        product_id=req.product_id,
        quantity=req.quantity,
        total_price=total_price,
        status="paid",
        promoter_id=req.promoter_id,
        commission=commission,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return ApiResponse(
        code=200,
        message="下单成功",
        data=OrderResponse.model_validate(order).model_dump(),
    )


@router.get("", response_model=ApiResponse)
def get_orders(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """获取订单列表（按角色过滤）"""
    if current_user.role == "admin":
        # 管理员看所有订单
        orders = db.query(Order).order_by(Order.id.desc()).all()
    elif current_user.role == "supplier":
        # 产品方看自己产品的订单
        orders = db.query(Order).join(Product).filter(
            Product.owner_id == current_user.id
        ).order_by(Order.id.desc()).all()
    elif current_user.role == "promoter":
        # 推广员看自己推广的订单
        orders = db.query(Order).filter(
            Order.promoter_id == current_user.id
        ).order_by(Order.id.desc()).all()
    else:
        # 普通用户看自己的订单
        orders = db.query(Order).filter(
            Order.user_id == current_user.id
        ).order_by(Order.id.desc()).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(orders),
            "items": [OrderResponse.model_validate(o).model_dump() for o in orders],
        },
    )


# 允许的状态流转
ALLOWED_TRANSITIONS = {
    "paid": ["shipped", "refunded"],
    "shipped": ["received", "refunded"],
    "received": ["refunded"],
    "refunded": [],
}


@router.put("/{order_id}/status", response_model=ApiResponse)
def update_order_status(
    order_id: int,
    req: OrderStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新订单状态（按角色限制）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 检查权限
    is_admin = current_user.role == "admin"
    is_supplier = current_user.role == "supplier" and order.product.owner_id == current_user.id
    is_buyer = current_user.role in ("buyer",) and order.user_id == current_user.id

    if not (is_admin or is_supplier or is_buyer):
        raise HTTPException(status_code=403, detail="无权操作此订单")

    # 检查状态流转是否合法
    allowed = ALLOWED_TRANSITIONS.get(order.status, [])
    if req.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"状态不允许变更: {order.status} → {req.status}，可选: {allowed}",
        )

    # 普通用户只能确认收货或申请退款
    if is_buyer and req.status not in ["received", "refunded"]:
        raise HTTPException(status_code=403, detail="买家只能确认收货或申请退款")

    # 产品方只能发货
    if is_supplier and req.status not in ["shipped"]:
        raise HTTPException(status_code=403, detail="产品方只能发货")

    # 记录旧状态
    old_status = order.status
    order.status = req.status

    # 如果确认收货且有关联推广员，累加收益
    if req.status == "received" and order.promoter_id and order.commission > 0:
        promoter_user = db.query(User).filter(User.id == order.promoter_id).first()
        if promoter_user:
            # 推广收益累加逻辑由promoter earnings查询时实时计算
            pass

    db.commit()
    db.refresh(order)

    return ApiResponse(
        code=200,
        message=f"订单状态已变更: {old_status} → {req.status}",
        data=OrderResponse.model_validate(order).model_dump(),
    )
