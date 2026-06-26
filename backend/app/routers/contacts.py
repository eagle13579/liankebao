"""
链客宝 — 联系人管理 API 路由
==============================
迁移自旧版链客宝 backend/app/routers/contacts.py
适配 chainke-full 架构。

端点:
  GET    /api/contacts/             — 联系人列表（分页，支持搜索/标签筛选）
  POST   /api/contacts/             — 创建联系人
  GET    /api/contacts/search       — FTS 搜索联系人
  GET    /api/contacts/tags         — 获取标签列表
  GET    /api/contacts/{id}         — 查询联系人详情
  PUT    /api/contacts/{id}         — 更新联系人
  DELETE /api/contacts/{id}         — 删除联系人（软删除）
  POST   /api/contacts/batch        — 批量创建联系人
  POST   /api/contacts/seed         — 生成测试联系人数据
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["联系人管理"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CreateContactRequest(BaseModel):
    """创建联系人请求"""
    name: str = Field(..., min_length=1, max_length=100, description="联系人姓名")
    owner_id: int = Field(..., gt=0, description="所属用户 ID")
    phone: str | None = Field(default=None, max_length=50, description="手机号")
    wechat_id: str | None = Field(default=None, max_length=100, description="微信号")
    company: str | None = Field(default=None, max_length=200, description="公司")
    position: str | None = Field(default=None, max_length=100, description="职位")
    email: str | None = Field(default=None, max_length=200, description="邮箱")
    notes: str | None = Field(default=None, description="备注")
    tags: str | None = Field(default=None, max_length=500, description="标签（逗号分隔）")
    source: str | None = Field(default="manual", max_length=50, description="来源: manual/import/wechat")


class UpdateContactRequest(BaseModel):
    """更新联系人请求（所有字段可选）"""
    name: str | None = Field(default=None, min_length=1, max_length=100, description="联系人姓名")
    phone: str | None = Field(default=None, max_length=50, description="手机号")
    wechat_id: str | None = Field(default=None, max_length=100, description="微信号")
    company: str | None = Field(default=None, max_length=200, description="公司")
    position: str | None = Field(default=None, max_length=100, description="职位")
    email: str | None = Field(default=None, max_length=200, description="邮箱")
    notes: str | None = Field(default=None, description="备注")
    tags: str | None = Field(default=None, max_length=500, description="标签（逗号分隔）")
    source: str | None = Field(default=None, max_length=50, description="来源: manual/import/wechat")


class BatchCreateContactItem(BaseModel):
    """批量创建联系人单项"""
    name: str = Field(..., min_length=1, max_length=100, description="联系人姓名")
    phone: str | None = Field(default=None, max_length=50, description="手机号")
    wechat_id: str | None = Field(default=None, max_length=100, description="微信号")
    company: str | None = Field(default=None, max_length=200, description="公司")
    position: str | None = Field(default=None, max_length=100, description="职位")
    email: str | None = Field(default=None, max_length=200, description="邮箱")
    notes: str | None = Field(default=None, description="备注")
    tags: str | None = Field(default=None, max_length=500, description="标签（逗号分隔）")
    source: str | None = Field(default=None, max_length=50, description="来源")


class BatchCreateContactsRequest(BaseModel):
    """批量创建联系人请求"""
    owner_id: int = Field(..., gt=0, description="所属用户 ID")
    items: list[BatchCreateContactItem] = Field(..., min_length=1, max_length=500, description="联系人列表")


class SeedContactsRequest(BaseModel):
    """生成测试联系人请求"""
    owner_id: int = Field(..., gt=0, description="所属用户 ID")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 路由实现
# ===================================================================


@router.get("", response_model=ApiResponse)
async def list_contacts(
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
    search: str = Query(None, description="搜索关键词（匹配姓名/电话/公司）"),
    tags: str = Query(None, description="按标签筛选（逗号分隔）"),
    tag: str = Query(None, description="按标签筛选（向后兼容，单标签精确匹配）"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """获取联系人列表（分页，可选按搜索关键词或标签筛选）"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        filter_tag = tag or tags
        items, total = service.list_contacts(
            owner_id=owner_id,
            page=page,
            limit=limit,
            search=search,
            tags=filter_tag,
        )
        return ApiResponse(
            code=0,
            message="success",
            data={
                "total": total,
                "page": page,
                "page_size": limit,
                "items": [format_contact_response(c) for c in items],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.post("", response_model=ApiResponse, status_code=201)
async def create_contact(req: CreateContactRequest, db: Session = Depends(get_db)):
    """创建联系人"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        contact = service.create_contact(
            owner_id=req.owner_id,
            name=req.name,
            phone=req.phone,
            wechat_id=req.wechat_id,
            company=req.company,
            position=req.position,
            email=req.email,
            notes=req.notes,
            tags=req.tags,
            source=req.source or "manual",
        )
        return ApiResponse(code=0, message="创建成功", data=format_contact_response(contact))
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.get("/search", response_model=ApiResponse)
async def search_contacts(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """FTS 搜索联系人（姓名/电话/微信号/公司/职位/邮箱/备注）"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        items, total = service.search_contacts(
            owner_id=owner_id,
            q=q,
            page=page,
            limit=limit,
        )
        return ApiResponse(
            code=0,
            message="success",
            data={
                "total": total,
                "page": page,
                "page_size": limit,
                "items": [format_contact_response(c) for c in items],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.get("/tags", response_model=ApiResponse)
async def list_tags(
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
    db: Session = Depends(get_db),
):
    """获取当前用户所有标签列表（去重排序）"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        tags = service.list_tags(owner_id=owner_id)
        return ApiResponse(code=0, message="success", data={"tags": tags})
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.get("/{contact_id}", response_model=ApiResponse)
async def get_contact(
    contact_id: int,
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
    db: Session = Depends(get_db),
):
    """获取联系人详情"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        contact = service.get_contact(contact_id=contact_id, owner_id=owner_id)
        if contact is None:
            raise HTTPException(status_code=404, detail=f"联系人不存在: id={contact_id}")
        return ApiResponse(code=0, message="success", data=format_contact_response(contact))
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.put("/{contact_id}", response_model=ApiResponse)
async def update_contact(
    contact_id: int,
    req: UpdateContactRequest,
    db: Session = Depends(get_db),
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
):
    """更新联系人"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        update_fields = req.model_dump(exclude_unset=True)
        contact = service.update_contact(
            contact_id=contact_id,
            owner_id=owner_id,
            **update_fields,
        )
        return ApiResponse(code=0, message="更新成功", data=format_contact_response(contact))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.delete("/{contact_id}", response_model=ApiResponse)
async def delete_contact(
    contact_id: int,
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
    db: Session = Depends(get_db),
):
    """删除联系人（软删除）"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        service.delete_contact(contact_id=contact_id, owner_id=owner_id)
        return ApiResponse(code=0, message="删除成功", data={"id": contact_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.post("/batch", response_model=ApiResponse, status_code=201)
async def batch_create_contacts(req: BatchCreateContactsRequest, db: Session = Depends(get_db)):
    """批量创建联系人（用于导入确认接口调用）"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        contacts_data = [item.model_dump() for item in req.items]
        created = service.batch_create_contacts(
            owner_id=req.owner_id,
            contacts_data=contacts_data,
        )
        return ApiResponse(
            code=0,
            message=f"成功创建 {len(created)} 个联系人",
            data={
                "total": len(created),
                "items": [format_contact_response(c) for c in created],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


@router.post("/seed", response_model=ApiResponse)
async def seed_contacts(req: SeedContactsRequest, db: Session = Depends(get_db)):
    """为指定用户生成测试联系人数据"""
    try:
        from features.contacts.services import ContactService

        service = ContactService(db)
        count = service.seed_contacts(owner_id=req.owner_id)
        return ApiResponse(code=0, message=f"成功创建 {count} 个测试联系人", data={"created": count})
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")


# ===================================================================
# 辅助函数
# ===================================================================


def format_contact_response(contact) -> dict:
    """将 Contact ORM 实例转为前端友好格式（tags 字符串转数组）"""
    d = contact.to_dict()
    # 转换 tags 从字符串到数组（前端期望数组格式）
    if isinstance(d.get("tags"), str):
        d["tags"] = [t.strip() for t in d["tags"].split(",") if t.strip()] if d["tags"] else []
    elif d.get("tags") is None:
        d["tags"] = []
    return d
