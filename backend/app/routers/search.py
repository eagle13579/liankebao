"""搜索路由：产品搜索及热词推荐"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import Product
from app.schemas import ApiResponse, ProductResponse

router = APIRouter(prefix="/api/search", tags=["搜索"])


@router.get("", response_model=ApiResponse)
def search_products(
    q: str = Query("", description="搜索关键词（产品名称/描述）"),
    category: str = Query(None, description="分类筛选"),
    region: str = Query(None, description="地区筛选（匹配规格中的产地）"),
    min_price: float = Query(None, ge=0, description="最低价格"),
    max_price: float = Query(None, ge=0, description="最高价格"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """产品搜索

    支持多维度筛选和模糊匹配，已上架(approved)产品可见。

    参数说明：
    - q：搜索关键词，匹配产品名称和描述（支持部分匹配）
    - category：按分类精确筛选
    - region：按产地/地区筛选（模糊匹配规格JSON中的"产地"字段）
    - min_price / max_price：价格区间筛选
    - page / page_size：分页
    """
    # 基础查询：只查询已上架产品
    query = db.query(Product).filter(Product.status == "approved")

    # === 模糊搜索：名称 + 描述 ===
    if q and q.strip():
        like_pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Product.name.like(like_pattern),
                Product.description.like(like_pattern),
                Product.tags.like(like_pattern),
                Product.brand.like(like_pattern),
            )
        )

    # === 分类筛选 ===
    if category and category.strip():
        query = query.filter(Product.category == category.strip())

    # === 地区筛选（从 specs JSON 中匹配 "产地" 字段） ===
    if region and region.strip():
        region_pattern = f"%{region.strip()}%"
        query = query.filter(Product.specs.like(region_pattern))

    # === 价格区间筛选 ===
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    # === 统计总数 ===
    total = query.count()

    # === 分页（按 sort_order 降序，创建时间降序） ===
    products = (
        query.order_by(desc(Product.sort_order), desc(Product.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [ProductResponse.model_validate(p).model_dump() for p in products],
        },
    )


@router.get("/categories", response_model=ApiResponse)
def list_search_categories(db: Session = Depends(get_db)):
    """获取所有产品分类列表（去重）"""
    categories = (
        db.query(Product.category)
        .filter(
            Product.status == "approved",
            Product.category.isnot(None),
            Product.category != "",
        )
        .distinct()
        .order_by(Product.category)
        .all()
    )

    return ApiResponse(
        code=200,
        message="success",
        data={
            "categories": [c[0] for c in categories],
        },
    )


@router.get("/suggestions", response_model=ApiResponse)
def search_suggestions(
    q: str = Query("", description="输入前缀"),
    limit: int = Query(10, ge=1, le=50, description="最大返回数"),
    db: Session = Depends(get_db),
):
    """搜索建议（前缀补全），用于搜索框下拉提示"""
    if not q or not q.strip():
        return ApiResponse(code=200, message="success", data={"suggestions": []})

    # 从数据库中模糊查询产品名称作为建议
    like_pattern = f"%{q.strip()}%"
    products = (
        db.query(Product.name)
        .filter(
            Product.status == "approved",
            Product.name.like(like_pattern),
        )
        .distinct()
        .limit(limit)
        .all()
    )

    suggestions = [p[0] for p in products]

    return ApiResponse(
        code=200,
        message="success",
        data={"suggestions": suggestions},
    )
