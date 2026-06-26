"""
链客宝 — 产品管理 API 路由
============================
迁移自旧版链客宝 backend/modules/products/routes/
适配 chainke-full 架构。

端点:
  POST   /api/products/          — 创建产品
  GET    /api/products/{id}      — 查询产品详情
  GET    /api/products/          — 产品列表（分页）
  PUT    /api/products/{id}      — 更新产品信息
  PUT    /api/products/{id}/status — 更新产品状态
  DELETE /api/products/{id}      — 删除产品
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/products", tags=["产品管理"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CreateProductRequest(BaseModel):
    """创建产品请求"""
    name: str = Field(..., max_length=200, description="产品名称")
    price: float = Field(..., gt=0, description="单价")
    owner_id: int = Field(..., gt=0, description="供应商 ID")
    description: str | None = Field(default=None, description="产品描述")
    category: str | None = Field(default=None, max_length=100, description="产品分类")
    images: str | None = Field(default=None, description="图片URL列表(JSON数组)")
    review_note: str | None = Field(default=None, max_length=500, description="审核备注")


class UpdateProductRequest(BaseModel):
    """更新产品请求"""
    name: str | None = Field(default=None, max_length=200, description="产品名称")
    description: str | None = Field(default=None, description="产品描述")
    price: float | None = Field(default=None, gt=0, description="单价")
    category: str | None = Field(default=None, max_length=100, description="产品分类")
    images: str | None = Field(default=None, description="图片URL列表(JSON数组)")
    review_note: str | None = Field(default=None, max_length=500, description="审核备注")


class UpdateStatusRequest(BaseModel):
    """更新产品状态请求"""
    status: str = Field(
        ...,
        pattern=r"^(approved|rejected|archived|pending)$",
        description="目标状态: approved/rejected/archived/pending",
    )


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 路由实现
# ===================================================================


@router.post("", response_model=ApiResponse)
async def create_product(req: CreateProductRequest, db: Session = Depends(get_db)):
    """创建新产品"""
    try:
        from features.products.services import ProductService

        service = ProductService(db)
        product = service.create_product(
            name=req.name,
            price=req.price,
            owner_id=req.owner_id,
            description=req.description,
            category=req.category,
            images=req.images,
            review_note=req.review_note,
        )
        return ApiResponse(code=0, message="success", data=product.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="products 模块未安装")


@router.get("/{product_id}", response_model=ApiResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    """查询产品详情"""
    try:
        from features.products.services import ProductService

        service = ProductService(db)
        product = service.get_product(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"产品不存在: id={product_id}")
        return ApiResponse(code=0, message="success", data=product.to_dict())
    except ImportError:
        raise HTTPException(status_code=500, detail="products 模块未安装")


@router.get("", response_model=ApiResponse)
async def list_products(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    owner_id: int | None = Query(None, description="供应商 ID 过滤"),
    category: str | None = Query(None, description="产品分类过滤"),
    status: str | None = Query(
        None,
        pattern=r"^(pending|approved|rejected|archived)$",
        description="产品状态过滤",
    ),
    db: Session = Depends(get_db),
):
    """产品列表（分页）"""
    try:
        from features.products.services import ProductService

        service = ProductService(db)
        items, total = service.list_products(
            page=page,
            limit=limit,
            owner_id=owner_id,
            category=category,
            status=status,
        )
        return ApiResponse(
            code=0,
            message="success",
            data={
                "total": total,
                "page": page,
                "limit": limit,
                "items": [p.to_dict() for p in items],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="products 模块未安装")


@router.put("/{product_id}", response_model=ApiResponse)
async def update_product(product_id: int, req: UpdateProductRequest, db: Session = Depends(get_db)):
    """更新产品信息"""
    try:
        from features.products.services import ProductService

        service = ProductService(db)
        product = service.update_product(
            product_id=product_id,
            name=req.name,
            description=req.description,
            price=req.price,
            category=req.category,
            images=req.images,
            review_note=req.review_note,
        )
        return ApiResponse(code=0, message="success", data=product.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="products 模块未安装")


@router.put("/{product_id}/status", response_model=ApiResponse)
async def update_product_status(product_id: int, req: UpdateStatusRequest, db: Session = Depends(get_db)):
    """更新产品状态（含状态机校验）"""
    try:
        from features.products.services import ProductService

        service = ProductService(db)
        product = service.update_status(product_id, req.status)
        return ApiResponse(code=0, message="success", data=product.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="products 模块未安装")


@router.delete("/{product_id}", response_model=ApiResponse)
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    """删除产品"""
    try:
        from features.products.services import ProductService

        service = ProductService(db)
        service.delete_product(product_id)
        return ApiResponse(code=0, message="success", data={"id": product_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="products 模块未安装")
