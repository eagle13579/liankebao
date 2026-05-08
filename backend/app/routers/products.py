"""产品路由：CRUD/审核/搜索"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import User, Product
from app.schemas import (
    ApiResponse, ProductCreate, ProductUpdate, ProductResponse,
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/products", tags=["产品"])


@router.get("", response_model=ApiResponse)
def list_products(
    category: str = Query(None, description="按分类筛选"),
    status: str = Query("approved", description="产品状态"),
    search: str = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取产品列表"""
    query = db.query(Product)

    # 按状态筛选
    if status:
        query = query.filter(Product.status == status)

    # 按分类筛选
    if category:
        query = query.filter(Product.category == category)

    # 搜索（名称和描述）
    if search:
        like_pattern = f"%{search}%"
        query = query.filter(
            (Product.name.like(like_pattern)) | (Product.description.like(like_pattern))
        )

    # 总数
    total = query.count()

    # 分页
    products = query.order_by(desc(Product.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

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


@router.get("/{product_id}", response_model=ApiResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """获取产品详情"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    return ApiResponse(
        code=200,
        message="success",
        data=ProductResponse.model_validate(product).model_dump(),
    )


@router.post("", response_model=ApiResponse)
def create_product(
    req: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建产品"""
    product = Product(
        name=req.name,
        description=req.description,
        price=req.price,
        earn_per_share=req.earn_per_share,
        category=req.category,
        stock=req.stock,
        images=req.images or "[]",
        specs=req.specs,
        details=req.details,
        brand=req.brand,
        sale_price=req.sale_price,
        video_url=req.video_url,
        tags=req.tags,
        files=req.files,
        is_featured=req.is_featured or 0,
        sort_order=req.sort_order or 0,
        status="pending",  # 新建产品待审核
        owner_id=current_user.id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    return ApiResponse(
        code=200,
        message="产品创建成功，等待审核",
        data=ProductResponse.model_validate(product).model_dump(),
    )


@router.put("/{product_id}", response_model=ApiResponse)
def update_product(
    product_id: int,
    req: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新产品（仅自己创建的产品）"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 权限检查：仅创建者或管理员可修改
    if product.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权修改此产品")

    # 更新字段
    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    # 重新提交审核
    if current_user.role != "admin":
        product.status = "pending"

    db.commit()
    db.refresh(product)

    return ApiResponse(
        code=200,
        message="产品更新成功",
        data=ProductResponse.model_validate(product).model_dump(),
    )
