"""联系人CRUD路由：列表/创建/详情/更新/删除/搜索/标签/批量"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Contact, User
from app.schemas import (
    ApiResponse,
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["联系人"])


@router.get("", response_model=ApiResponse)
def list_contacts(
    search: str = Query(None, description="搜索关键词（匹配姓名/电话/公司）"),
    tags: str = Query(None, description="按标签筛选（逗号分隔，支持多标签）"),
    tag: str = Query(None, description="按标签筛选（向后兼容，单标签精确匹配）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的联系人列表（分页，可选按搜索关键词或标签筛选）"""
    query = db.query(Contact).filter(
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
    )

    # 搜索关键词
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            Contact.name.ilike(keyword) | Contact.phone.ilike(keyword) | Contact.company.ilike(keyword)
        )

    # 标签筛选（tags字段存逗号分隔字符串）
    filter_tag = tag or tags
    if filter_tag:
        for t in filter_tag.split(","):
            t = t.strip()
            if t:
                query = query.filter(Contact.tags.contains(t))

    total = query.count()
    contacts = query.order_by(desc(Contact.updated_at)).offset((page - 1) * page_size).limit(page_size).all()

    items = [ContactResponse.model_validate(c) for c in contacts]
    # 转换tags从字符串到数组（前端期望数组格式）
    data = ContactListResponse(total=total, page=page, page_size=page_size, items=items).model_dump()
    for item in data.get("items", []):
        if isinstance(item.get("tags"), str):
            item["tags"] = [t.strip() for t in item["tags"].split(",") if t.strip()] if item["tags"] else []
        elif item.get("tags") is None:
            item["tags"] = []
    return {
        "code": 200,
        "message": "success",
        "data": data,
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
    contacts = query.order_by(desc(Contact.updated_at)).offset((page - 1) * page_size).limit(page_size).all()
    items = [ContactResponse.model_validate(c) for c in contacts]
    # 转换tags从字符串到数组
    data = ContactListResponse(total=total, page=page, page_size=page_size, items=items).model_dump()
    for item in data.get("items", []):
        if isinstance(item.get("tags"), str):
            item["tags"] = [t.strip() for t in item["tags"].split(",") if t.strip()] if item["tags"] else []
        elif item.get("tags") is None:
            item["tags"] = []
    return {
        "code": 200,
        "message": "success",
        "data": data,
    }


@router.get("/tags", response_model=ApiResponse)
def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户所有标签列表（去重）"""
    contacts = (
        db.query(Contact)
        .filter(
            Contact.owner_id == current_user.id,
            Contact.is_deleted == False,
        )
        .all()
    )
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
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.owner_id == current_user.id,
            Contact.is_deleted == False,
        )
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")
    resp = ContactResponse.model_validate(contact).model_dump()
    # 转换tags从字符串到数组
    if isinstance(resp.get("tags"), str):
        resp["tags"] = [t.strip() for t in resp["tags"].split(",") if t.strip()] if resp["tags"] else []
    elif resp.get("tags") is None:
        resp["tags"] = []
    return {
        "code": 200,
        "message": "success",
        "data": resp,
    }


@router.put("/{contact_id}", response_model=ApiResponse)
def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新联系人"""
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.owner_id == current_user.id,
            Contact.is_deleted == False,
        )
        .first()
    )
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
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.owner_id == current_user.id,
            Contact.is_deleted == False,
        )
        .first()
    )
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
    contacts_data: list[ContactCreate],
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


@router.post("/seed", response_model=ApiResponse)
def seed_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为当前用户生成测试联系人数据"""
    sample_contacts = [
        {
            "name": "张伟",
            "phone": "13800138001",
            "company": "阿里巴巴",
            "position": "技术总监",
            "tags": "VIP,技术,合作伙伴",
        },
        {"name": "李娜", "phone": "13900139002", "company": "腾讯科技", "position": "产品经理", "tags": "客户,产品"},
        {"name": "王强", "phone": "13700137003", "company": "百度", "position": "销售总监", "tags": "潜在客户,销售"},
        {"name": "赵敏", "phone": "13600136004", "company": "京东集团", "position": "运营总监", "tags": "VIP,合作伙伴"},
        {
            "name": "刘洋",
            "phone": "13500135005",
            "company": "字节跳动",
            "position": "HRBP",
            "tags": "人力资源,潜在客户",
        },
        {
            "name": "陈静",
            "phone": "13400134006",
            "company": "华为技术",
            "position": "研发经理",
            "tags": "技术,合作伙伴",
        },
        {
            "name": "杨磊",
            "phone": "13300133007",
            "company": "小米科技",
            "position": "市场总监",
            "tags": "市场,潜在客户",
        },
        {"name": "黄丽", "phone": "13200132008", "company": "美团", "position": "商务拓展", "tags": "商务,客户"},
        {
            "name": "周杰",
            "phone": "13100131009",
            "company": "拼多多",
            "position": "供应链总监",
            "tags": "供应链,合作伙伴",
        },
        {"name": "吴芳", "phone": "13000130010", "company": "网易", "position": "产品运营", "tags": "运营,潜在客户"},
        {"name": "孙鹏", "phone": "15900159011", "company": "比亚迪", "position": "采购经理", "tags": "采购,客户"},
        {
            "name": "马小红",
            "phone": "15800158012",
            "company": "顺丰速运",
            "position": "区域总监",
            "tags": "物流,合作伙伴",
        },
    ]
    count = 0
    for data in sample_contacts:
        existing = (
            db.query(Contact)
            .filter(
                Contact.owner_id == current_user.id,
                Contact.phone == data["phone"],
                Contact.is_deleted == False,
            )
            .first()
        )
        if existing:
            continue
        contact = Contact(
            owner_id=current_user.id,
            name=data["name"],
            phone=data["phone"],
            company=data["company"],
            position=data["position"],
            tags=data["tags"],
            source="seed",
        )
        db.add(contact)
        count += 1
    db.commit()
    return {
        "code": 200,
        "message": f"成功创建 {count} 个测试联系人",
        "data": {"created": count},
    }
