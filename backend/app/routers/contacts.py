"""联系人CRUD路由：列表/创建/详情/更新/删除/搜索/标签/批量"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import User, Contact
from app.schemas import (
    ApiResponse,
    ContactCreate,
    ContactUpdate,
    ContactResponse,
    ContactListResponse,
)
from app.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["联系人"])


@router.get("", response_model=ApiResponse)
def list_contacts(
    tag: str = Query(None, description="按标签筛选（精确匹配）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的联系人列表（分页，可选按标签筛选）"""
    query = db.query(Contact).filter(
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
    )

    # 标签筛选（tags字段存逗号分隔字符串）
    if tag:
        query = query.filter(Contact.tags.contains(tag))

    total = query.count()
    contacts = (
        query.order_by(desc(Contact.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [ContactResponse.model_validate(c) for c in contacts]
    return {
        "code": 200,
        "message": "success",
        "data": ContactListResponse(total=total, page=page, page_size=page_size, items=items).model_dump(),
    }


@router.post("", response_model=ApiResponse, status_code=201)
def create_contact(
    contact_data: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建联系人"""
    contact = Contact(
        owner_id=current_user.id,
        name=contact_data.name,
        phone=contact_data.phone,
        wechat_id=contact_data.wechat_id,
        company=contact_data.company,
        position=contact_data.position,
        email=contact_data.email,
        notes=contact_data.notes,
        tags=contact_data.tags,
        source=contact_data.source or "manual",
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    logger.info("联系人创建成功", extra={"contact_id": contact.id, "user_id": current_user.id})
    return {
        "code": 201,
        "message": "创建成功",
        "data": ContactResponse.model_validate(contact).model_dump(),
    }


@router.get("/search", response_model=ApiResponse)
def search_contacts(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """FTS搜索联系人（姓名/电话/微信号/公司/职位/邮箱/备注）"""
    keyword = f"%{q}%"
    query = db.query(Contact).filter(
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
        (
            Contact.name.ilike(keyword)
            | Contact.phone.ilike(keyword)
            | Contact.wechat_id.ilike(keyword)
            | Contact.company.ilike(keyword)
            | Contact.position.ilike(keyword)
            | Contact.email.ilike(keyword)
            | Contact.notes.ilike(keyword)
        ),
    )
    total = query.count()
    contacts = (
        query.order_by(desc(Contact.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [ContactResponse.model_validate(c) for c in contacts]
    return {
        "code": 200,
        "message": "success",
        "data": ContactListResponse(total=total, page=page, page_size=page_size, items=items).model_dump(),
    }


@router.get("/tags", response_model=ApiResponse)
def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户所有标签列表（去重）"""
    contacts = db.query(Contact).filter(
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
    ).all()
    tag_set: set = set()
    for c in contacts:
        if c.tags:
            for t in c.tags.split(","):
                t = t.strip()
                if t:
                    tag_set.add(t)
    tags = sorted(tag_set)
    return {
        "code": 200,
        "message": "success",
        "data": {"tags": tags},
    }


@router.get("/{contact_id}", response_model=ApiResponse)
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取联系人详情"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")
    return {
        "code": 200,
        "message": "success",
        "data": ContactResponse.model_validate(contact).model_dump(),
    }


@router.put("/{contact_id}", response_model=ApiResponse)
def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新联系人"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")

    # 仅更新传入的非 None 字段
    update_fields = contact_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(contact, field, value)

    db.commit()
    db.refresh(contact)
    return {
        "code": 200,
        "message": "更新成功",
        "data": ContactResponse.model_validate(contact).model_dump(),
    }


@router.delete("/{contact_id}", response_model=ApiResponse, status_code=200)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除联系人"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")

    contact.is_deleted = True
    contact.deleted_at = datetime.utcnow()
    db.commit()
    return {
        "code": 200,
        "message": "删除成功",
        "data": None,
    }


@router.post("/batch", response_model=ApiResponse, status_code=201)
def batch_create_contacts(
    contacts_data: List[ContactCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量创建联系人（用于导入确认接口调用）"""
    created: list = []
    for data in contacts_data:
        contact = Contact(
            owner_id=current_user.id,
            name=data.name,
            phone=data.phone,
            wechat_id=data.wechat_id,
            company=data.company,
            position=data.position,
            email=data.email,
            notes=data.notes,
            tags=data.tags,
            source=data.source or "import",
        )
        db.add(contact)
        created.append(contact)

    db.commit()
    # 刷新以获取ID
    for c in created:
        db.refresh(c)

    logger.info(
        "批量创建联系人成功",
        extra={"user_id": current_user.id, "count": len(created)},
    )
    return {
        "code": 201,
        "message": f"成功创建 {len(created)} 个联系人",
        "data": {
            "total": len(created),
            "items": [ContactResponse.model_validate(c).model_dump() for c in created],
        },
    }
