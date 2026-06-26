"""
产品服务层 (Product Service)
============================
迁移自旧版链客宝 backend/modules/products/services/
提供产品 CRUD 与状态管理。

用法:
    from features.products.services import ProductService
    service = ProductService(db)
    product = service.create_product(...)
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from features.products.models.product import Product

logger = logging.getLogger(__name__)


class ProductService:
    """产品业务服务"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # create_product — 创建产品
    # ------------------------------------------------------------------

    def create_product(
        self,
        name: str,
        price: float,
        owner_id: int,
        description: Optional[str] = None,
        category: Optional[str] = None,
        images: Optional[str] = None,
        review_note: Optional[str] = None,
    ) -> Product:
        """创建新产品

        Args:
            name:        产品名称
            price:       单价
            owner_id:    供应商 ID
            description: 产品描述（可选）
            category:    产品分类（可选）
            images:      图片URL列表 JSON（可选）
            review_note: 审核备注（可选）

        Returns:
            Product ORM 实例
        """
        product = Product(
            name=name,
            price=price,
            owner_id=owner_id,
            description=description,
            category=category,
            images=images,
            status="pending",
            review_note=review_note,
        )
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        logger.info("产品创建成功: id=%d, name='%s', price=%.2f", product.id, name, price)
        return product

    # ------------------------------------------------------------------
    # get_product — 查询单个产品
    # ------------------------------------------------------------------

    def get_product(self, product_id: int) -> Optional[Product]:
        """根据 ID 查询产品"""
        return self.db.query(Product).filter(Product.id == product_id).first()

    # ------------------------------------------------------------------
    # list_products — 产品列表（分页）
    # ------------------------------------------------------------------

    def list_products(
        self,
        page: int = 1,
        limit: int = 20,
        owner_id: Optional[int] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> tuple[list[Product], int]:
        """分页查询产品列表

        Args:
            page:      页码，从 1 开始
            limit:     每页条数
            owner_id:  按供应商过滤（可选）
            category:  按分类过滤（可选）
            status:    按状态过滤（可选）

        Returns:
            (items, total) 元组
        """
        query = self.db.query(Product)

        if owner_id is not None:
            query = query.filter(Product.owner_id == owner_id)
        if category is not None:
            query = query.filter(Product.category == category)
        if status is not None:
            query = query.filter(Product.status == status)

        total = query.count()
        items = (
            query.order_by(Product.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # update_product — 更新产品
    # ------------------------------------------------------------------

    def update_product(
        self,
        product_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        price: Optional[float] = None,
        category: Optional[str] = None,
        images: Optional[str] = None,
        review_note: Optional[str] = None,
    ) -> Product:
        """更新产品信息

        Args:
            product_id:  产品 ID
            name:        产品名称（可选）
            description: 产品描述（可选）
            price:       单价（可选）
            category:    产品分类（可选）
            images:      图片URL列表 JSON（可选）
            review_note: 审核备注（可选）

        Returns:
            Product ORM 实例

        Raises:
            ValueError: 产品不存在
        """
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            raise ValueError(f"产品不存在: id={product_id}")

        if name is not None:
            product.name = name
        if description is not None:
            product.description = description
        if price is not None:
            product.price = price
        if category is not None:
            product.category = category
        if images is not None:
            product.images = images
        if review_note is not None:
            product.review_note = review_note

        self.db.commit()
        self.db.refresh(product)
        logger.info("产品更新成功: id=%d", product_id)
        return product

    # ------------------------------------------------------------------
    # update_status — 更新产品状态
    # ------------------------------------------------------------------

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"approved", "rejected"},
        "approved": {"archived", "rejected"},
        "rejected": {"pending"},
        "archived": set(),
    }

    def update_status(self, product_id: int, new_status: str) -> Product:
        """更新产品状态（含状态机校验）

        Args:
            product_id:  产品 ID
            new_status:  目标状态

        Returns:
            Product ORM 实例

        Raises:
            ValueError: 产品不存在或状态转换非法
        """
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            raise ValueError(f"产品不存在: id={product_id}")

        allowed = self.VALID_TRANSITIONS.get(product.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"非法状态转换: {product.status} → {new_status} "
                f"(允许: {', '.join(sorted(allowed)) or '无'})"
            )

        product.status = new_status
        self.db.commit()
        self.db.refresh(product)
        logger.info("产品状态更新: id=%d, %s → %s", product_id, product.status, new_status)
        return product

    # ------------------------------------------------------------------
    # delete_product — 删除产品
    # ------------------------------------------------------------------

    def delete_product(self, product_id: int) -> None:
        """删除产品（物理删除）

        Args:
            product_id: 产品 ID

        Raises:
            ValueError: 产品不存在
        """
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            raise ValueError(f"产品不存在: id={product_id}")

        self.db.delete(product)
        self.db.commit()
        logger.info("产品已删除: id=%d, name='%s'", product_id, product.name)
