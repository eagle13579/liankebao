"""
链客宝 — 订单管理 API 路由
============================
迁移自旧版链客宝 backend/modules/orders/routes/
适配 chainke-full 架构。

端点:
  POST   /api/orders/           — 创建订单
  GET    /api/orders/{id}       — 查询订单详情
  GET    /api/orders/           — 订单列表（分页）
  PUT    /api/orders/{id}/status — 更新订单状态
  DELETE /api/orders/{id}       — 删除订单
"""

from __future__ import annotations

import logging
import random
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["订单管理"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    product_id: int = Field(..., gt=0, description="产品 ID")
    buyer_id: int = Field(..., gt=0, description="买家 ID")
    supplier_id: int = Field(..., gt=0, description="供应商 ID")
    total_price: float = Field(..., gt=0, description="总价")
    quantity: int = Field(default=1, ge=1, description="数量")
    promoter_id: int | None = Field(default=None, description="推广员 ID")
    contact_name: str | None = Field(default=None, max_length=100, description="收货人姓名")
    contact_phone: str | None = Field(default=None, max_length=20, description="收货人电话")
    shipping_address: str | None = Field(default=None, max_length=500, description="收货地址")
    note: str | None = Field(default=None, max_length=2000, description="订单备注")


class UpdateStatusRequest(BaseModel):
    """更新订单状态请求"""
    status: str = Field(..., pattern=r"^(paid|shipped|received|cancelled|refunded)$", description="目标状态")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 工具函数
# ===================================================================


def _generate_order_no() -> str:
    """生成订单号: ORD{timestamp}{4位随机数}"""
    ts = time.strftime("%Y%m%d%H%M%S")
    rand = f"{random.randint(1000, 9999)}"
    return f"ORD{ts}{rand}"


# ===================================================================
# 路由实现
# ===================================================================


@router.post("", response_model=ApiResponse)
async def create_order(req: CreateOrderRequest, db: Session = Depends(get_db)):
    """创建新订单"""
    try:
        from features.orders.services import OrderService

        service = OrderService(db)
        order_no = _generate_order_no()
        order = service.create_order(
            order_no=order_no,
            product_id=req.product_id,
            buyer_id=req.buyer_id,
            supplier_id=req.supplier_id,
            total_price=req.total_price,
            quantity=req.quantity,
            promoter_id=req.promoter_id,
            contact_name=req.contact_name,
            contact_phone=req.contact_phone,
            shipping_address=req.shipping_address,
            note=req.note,
        )
        return ApiResponse(code=0, message="success", data=order.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="orders 模块未安装")


@router.get("/{order_id}", response_model=ApiResponse)
async def get_order(order_id: int, db: Session = Depends(get_db)):
    """查询订单详情"""
    try:
        from features.orders.services import OrderService

        service = OrderService(db)
        order = service.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail=f"订单不存在: id={order_id}")
        return ApiResponse(code=0, message="success", data=order.to_dict())
    except ImportError:
        raise HTTPException(status_code=500, detail="orders 模块未安装")


@router.get("", response_model=ApiResponse)
async def list_orders(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    buyer_id: int | None = Query(None, description="买家 ID 过滤"),
    supplier_id: int | None = Query(None, description="供应商 ID 过滤"),
    status: str | None = Query(
        None,
        pattern=r"^(pending|paid|shipped|received|cancelled|refunded)$",
        description="订单状态过滤",
    ),
    db: Session = Depends(get_db),
):
    """订单列表（分页）"""
    try:
        from features.orders.services import OrderService

        service = OrderService(db)
        items, total = service.list_orders(
            page=page,
            limit=limit,
            buyer_id=buyer_id,
            supplier_id=supplier_id,
            status=status,
        )
        return ApiResponse(
            code=0,
            message="success",
            data={
                "total": total,
                "page": page,
                "limit": limit,
                "items": [o.to_dict() for o in items],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="orders 模块未安装")


@router.put("/{order_id}/status", response_model=ApiResponse)
async def update_order_status(order_id: int, req: UpdateStatusRequest, db: Session = Depends(get_db)):
    """更新订单状态（含状态机校验）"""
    try:
        from features.orders.services import OrderService

        service = OrderService(db)
        order = service.update_status(order_id, req.status)
        return ApiResponse(code=0, message="success", data=order.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="orders 模块未安装")


@router.delete("/{order_id}", response_model=ApiResponse)
async def delete_order(order_id: int, db: Session = Depends(get_db)):
    """删除订单"""
    try:
        from features.orders.services import OrderService

        service = OrderService(db)
        service.delete_order(order_id)
        return ApiResponse(code=0, message="success", data={"id": order_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="orders 模块未安装")
