"""
链客宝 — 商机/需求管理 API 路由
=================================
迁移自旧版链客宝 backend/modules/needs/routes/
适配 chainke-full 架构。

端点:
  GET    /api/needs/             — 需求列表（分页，支持搜索/分类/状态筛选）
  POST   /api/needs/             — 创建需求
  GET    /api/needs/{need_id}    — 查询需求详情
  PUT    /api/needs/{need_id}    — 更新需求
  DELETE /api/needs/{need_id}    — 删除需求
  POST   /api/needs/{need_id}/respond  — 响应需求
  POST   /api/needs/{need_id}/fulfill  — 完成需求
  POST   /api/needs/{need_id}/close    — 关闭需求
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/needs", tags=["商机/需求管理"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CreateNeedRequest(BaseModel):
    """创建需求请求"""
    title: str = Field(..., min_length=1, max_length=200, description="需求标题")
    owner_id: int = Field(..., gt=0, description="发布人用户 ID")
    description: str | None = Field(default=None, description="需求描述")
    category: str | None = Field(default=None, max_length=100, description="需求分类")
    budget: float | None = Field(default=None, ge=0, description="预算金额")
    contact_name: str | None = Field(default=None, max_length=100, description="联系人姓名")
    contact_phone: str | None = Field(default=None, max_length=20, description="联系人电话")


class UpdateNeedRequest(BaseModel):
    """更新需求请求（所有字段可选）"""
    title: str | None = Field(default=None, min_length=1, max_length=200, description="需求标题")
    description: str | None = Field(default=None, description="需求描述")
    category: str | None = Field(default=None, max_length=100, description="需求分类")
    budget: float | None = Field(default=None, ge=0, description="预算金额")
    status: str | None = Field(default=None, max_length=20, description="状态")
    contact_name: str | None = Field(default=None, max_length=100, description="联系人姓名")
    contact_phone: str | None = Field(default=None, max_length=20, description="联系人电话")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 路由实现
# ===================================================================


@router.get("", response_model=ApiResponse)
async def list_needs(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    owner_id: int | None = Query(None, gt=0, description="按发布人筛选"),
    category: str | None = Query(None, description="按分类筛选"),
    status: str | None = Query(None, description="按状态筛选 (open/responding/closed/fulfilled)"),
    search: str | None = Query(None, description="搜索关键词（匹配标题/描述）"),
    db: Session = Depends(get_db),
):
    """获取需求列表（分页，可选按搜索关键词/分类/状态筛选）"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        items, total = service.list_needs(
            page=page,
            limit=limit,
            owner_id=owner_id,
            category=category,
            status=status,
            search=search,
        )
        return ApiResponse(
            code=0,
            message="success",
            data={
                "total": total,
                "page": page,
                "page_size": limit,
                "items": [format_need_response(n) for n in items],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


@router.post("", response_model=ApiResponse, status_code=201)
async def create_need(req: CreateNeedRequest, db: Session = Depends(get_db)):
    """创建需求"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        need = service.create_need(
            title=req.title,
            owner_id=req.owner_id,
            description=req.description,
            category=req.category,
            budget=req.budget,
            contact_name=req.contact_name,
            contact_phone=req.contact_phone,
        )
        return ApiResponse(code=0, message="创建成功", data=format_need_response(need))
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


@router.get("/{need_id}", response_model=ApiResponse)
async def get_need(
    need_id: int,
    db: Session = Depends(get_db),
):
    """获取需求详情"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        need = service.get_need(need_id=need_id)
        if need is None:
            raise HTTPException(status_code=404, detail=f"需求不存在: id={need_id}")
        return ApiResponse(code=0, message="success", data=format_need_response(need))
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


@router.put("/{need_id}", response_model=ApiResponse)
async def update_need(
    need_id: int,
    req: UpdateNeedRequest,
    db: Session = Depends(get_db),
):
    """更新需求"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        update_fields = req.model_dump(exclude_unset=True)
        need = service.update_need(
            need_id=need_id,
            **update_fields,
        )
        return ApiResponse(code=0, message="更新成功", data=format_need_response(need))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


@router.delete("/{need_id}", response_model=ApiResponse)
async def delete_need(
    need_id: int,
    db: Session = Depends(get_db),
):
    """删除需求"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        service.delete_need(need_id=need_id)
        return ApiResponse(code=0, message="删除成功", data={"id": need_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


@router.post("/{need_id}/respond", response_model=ApiResponse)
async def respond_need(
    need_id: int,
    db: Session = Depends(get_db),
):
    """响应需求（将状态改为 responding）"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        need = service.respond_need(need_id=need_id)
        return ApiResponse(code=0, message="响应成功", data=format_need_response(need))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


@router.post("/{need_id}/fulfill", response_model=ApiResponse)
async def fulfill_need(
    need_id: int,
    db: Session = Depends(get_db),
):
    """完成需求（将状态改为 fulfilled）"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        need = service.fulfill_need(need_id=need_id)
        return ApiResponse(code=0, message="已完成", data=format_need_response(need))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


@router.post("/{need_id}/close", response_model=ApiResponse)
async def close_need(
    need_id: int,
    db: Session = Depends(get_db),
):
    """关闭需求（将状态改为 closed）"""
    try:
        from features.needs.services import NeedService

        service = NeedService(db)
        need = service.close_need(need_id=need_id)
        return ApiResponse(code=0, message="已关闭", data=format_need_response(need))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="needs 模块未安装")


# ===================================================================
# 辅助函数
# ===================================================================


def format_need_response(need) -> dict:
    """将 BusinessNeed ORM 实例转为前端友好格式"""
    return need.to_dict()
