"""
订单服务层 (Order Service)
==========================
迁移自旧版链客宝订单模块，提供订单 CRUD 与状态管理。

用法:
    from features.orders.services import OrderService
    service = OrderService(db)
    order = service.create_order(...)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from features.orders.models.order import Order

logger = logging.getLogger(__name__)


class OrderService:
    """订单业务服务"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # create_order — 创建订单
    # ------------------------------------------------------------------

    def create_order(
        self,
        order_no: str,
        product_id: int,
        buyer_id: int,
        supplier_id: int,
        total_price: float,
        quantity: int = 1,
        promoter_id: Optional[int] = None,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
        shipping_address: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Order:
        """创建新订单

        Args:
            order_no:        订单号（需唯一）
            product_id:      产品 ID
            buyer_id:        买家 ID
            supplier_id:     供应商 ID
            total_price:     总价
            quantity:        数量，默认 1
            promoter_id:     推广员 ID（可选）
            contact_name:    收货人姓名（可选）
            contact_phone:   收货人电话（可选）
            shipping_address: 收货地址（可选）
            note:            订单备注（可选）

        Returns:
            Order ORM 实例

        Raises:
            ValueError: 订单号已存在
        """
        existing = self.db.query(Order).filter(Order.order_no == order_no).first()
        if existing is not None:
            raise ValueError(f"订单号已存在: {order_no}")

        order = Order(
            order_no=order_no,
            product_id=product_id,
            buyer_id=buyer_id,
            supplier_id=supplier_id,
            promoter_id=promoter_id,
            quantity=quantity,
            total_price=total_price,
            status="pending",
            contact_name=contact_name,
            contact_phone=contact_phone,
            shipping_address=shipping_address,
            note=note,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        logger.info("订单创建成功: order_no=%s, buyer=%s, amount=%.2f", order_no, buyer_id, total_price)
        return order

    # ------------------------------------------------------------------
    # get_order — 查询单个订单
    # ------------------------------------------------------------------

    def get_order(self, order_id: int) -> Optional[Order]:
        """根据 ID 查询订单"""
        return self.db.query(Order).filter(Order.id == order_id).first()

    def get_order_by_no(self, order_no: str) -> Optional[Order]:
        """根据订单号查询订单"""
        return self.db.query(Order).filter(Order.order_no == order_no).first()

    # ------------------------------------------------------------------
    # list_orders — 订单列表（分页）
    # ------------------------------------------------------------------

    def list_orders(
        self,
        page: int = 1,
        limit: int = 20,
        buyer_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> tuple[list[Order], int]:
        """分页查询订单列表

        Args:
            page:        页码，从 1 开始
            limit:       每页条数
            buyer_id:    按买家过滤（可选）
            supplier_id: 按供应商过滤（可选）
            status:      按状态过滤（可选）

        Returns:
            (items, total) 元组
        """
        query = self.db.query(Order)

        if buyer_id is not None:
            query = query.filter(Order.buyer_id == buyer_id)
        if supplier_id is not None:
            query = query.filter(Order.supplier_id == supplier_id)
        if status is not None:
            query = query.filter(Order.status == status)

        total = query.count()
        items = (
            query.order_by(Order.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # update_status — 更新订单状态
    # ------------------------------------------------------------------

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"paid", "cancelled"},
        "paid": {"shipped", "cancelled"},
        "shipped": {"received", "cancelled"},
        "received": {"refunded"},
        "cancelled": set(),
        "refunded": set(),
    }

    def update_status(self, order_id: int, new_status: str) -> Order:
        """更新订单状态（含状态机校验）

        Args:
            order_id:   订单 ID
            new_status: 目标状态

        Returns:
            Order ORM 实例

        Raises:
            ValueError: 订单不存在或状态转换非法
        """
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order is None:
            raise ValueError(f"订单不存在: id={order_id}")

        allowed = self.VALID_TRANSITIONS.get(order.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"非法状态转换: {order.status} → {new_status} "
                f"(允许: {', '.join(sorted(allowed)) or '无'})"
            )

        order.status = new_status
        self.db.commit()
        self.db.refresh(order)
        logger.info("订单状态更新: id=%d, %s → %s", order_id, order.status, new_status)
        return order

    # ------------------------------------------------------------------
    # delete_order — 删除订单
    # ------------------------------------------------------------------

    def delete_order(self, order_id: int) -> None:
        """删除订单（物理删除）

        Args:
            order_id: 订单 ID

        Raises:
            ValueError: 订单不存在
        """
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order is None:
            raise ValueError(f"订单不存在: id={order_id}")

        self.db.delete(order)
        self.db.commit()
        logger.info("订单已删除: id=%d, order_no=%s", order_id, order.order_no)
