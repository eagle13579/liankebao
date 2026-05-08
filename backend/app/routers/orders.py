"""订单路由：创建/列表/状态更新"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import User, Product, Order
from app.schemas import ApiResponse, OrderCreate, OrderResponse
from app.auth import get_current_user

router = APIRouter(prefix="/api/orders", tags=["订单"])


@router.post("", response_model=ApiResponse)
def create_order(
    req: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建订单"""
    # 检查产品
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
        # 推广员分润 = earn_per_share * 50%
        commission = product.earn_per_share * req.quantity * 0.5

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

    # 扣减库存
    product.stock -= req.quantity

    db.commit()
    db.refresh(order)

    return ApiResponse(
        code=200,
        message="订单创建成功",
        data=OrderResponse.model_validate(order).model_dump(),
    )


@router.get("", response_model=ApiResponse)
def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取订单列表"""
    query = db.query(Order)

    # 非管理员只看自己的订单
    if current_user.role != "admin":
        query = query.filter(Order.user_id == current_user.id)

    orders = query.order_by(desc(Order.created_at)).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(orders),
            "items": [OrderResponse.model_validate(o).model_dump() for o in orders],
        },
    )


@router.put("/{order_id}/status", response_model=ApiResponse)
def update_order_status(
    order_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新订单状态（发货/确认收货/退款）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    new_status = body.get("status")
    valid_statuses = ["shipped", "received", "refunded"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效状态，可选: {valid_statuses}")

    # 状态流转校验
    if new_status == "shipped" and order.status != "paid":
        raise HTTPException(status_code=400, detail="只能对已支付订单进行发货")
    if new_status == "received" and order.status not in ("paid", "shipped"):
        raise HTTPException(status_code=400, detail="订单状态不允许确认收货")
    if new_status == "refunded" and order.status not in ("paid", "shipped"):
        raise HTTPException(status_code=400, detail="订单状态不允许退款")

    order.status = new_status

    # 确认收货时，如果有关联推广员，确认分润
    if new_status == "received" and order.promoter_id and order.commission > 0:
        # 收益已锁定，无需额外操作
        pass

    # 退款时恢复库存
    if new_status == "refunded":
        product = db.query(Product).filter(Product.id == order.product_id).first()
        if product:
            product.stock += order.quantity
        # 退款时撤销推广佣金
        order.commission = 0.0

    db.commit()
    db.refresh(order)

    return ApiResponse(
        code=200,
        message=f"订单状态已更新为: {new_status}",
        data=OrderResponse.model_validate(order).model_dump(),
    )
