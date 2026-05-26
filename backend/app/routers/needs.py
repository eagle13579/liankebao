"""需求路由：供需匹配 CRUD / 大厅列表 / 我的需求"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import User, BusinessNeed
from app.schemas import (
    ApiResponse, BusinessNeedCreate, BusinessNeedUpdate, BusinessNeedResponse,
    UserBrief,
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/needs", tags=["供需匹配"])


@router.get("", response_model=ApiResponse)
def list_needs(
    category: str = Query(None, description="按品类筛选"),
    status: str = Query(None, description="按状态筛选（open/closed）"),
    search: str = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """需求大厅列表（公开，无需登录）"""
    query = db.query(BusinessNeed).filter(BusinessNeed.is_deleted == False)

    # 默认只显示 open 状态的需求
    if status:
        query = query.filter(BusinessNeed.status == status)
    else:
        query = query.filter(BusinessNeed.status == "open")

    # 按品类筛选
    if category:
        query = query.filter(BusinessNeed.category == category)

    # 搜索（标题和描述）
    if search:
        like_pattern = f"%{search}%"
        query = query.filter(
            (BusinessNeed.title.like(like_pattern)) |
            (BusinessNeed.description.like(like_pattern))
        )

    total = query.count()

    needs = query.order_by(desc(BusinessNeed.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = []
    for n in needs:
        item = BusinessNeedResponse.model_validate(n).model_dump()
        if n.user:
            item["user"] = UserBrief.model_validate(n.user).model_dump()
        items.append(item)

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        },
    )


@router.get("/my", response_model=ApiResponse)
def list_my_needs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户发布的需求（我的需求）"""
    query = db.query(BusinessNeed).filter(
        BusinessNeed.user_id == current_user.id,
        BusinessNeed.is_deleted == False,
    )
    total = query.count()

    needs = query.order_by(desc(BusinessNeed.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [BusinessNeedResponse.model_validate(n).model_dump() for n in needs],
        },
    )


@router.get("/{need_id}", response_model=ApiResponse)
def get_need(
    need_id: int,
    db: Session = Depends(get_db),
):
    """获取需求详情"""
    need = db.query(BusinessNeed).filter(
        BusinessNeed.id == need_id,
        BusinessNeed.is_deleted == False,
    ).first()
    if not need:
        raise HTTPException(status_code=404, detail="需求不存在")

    item = BusinessNeedResponse.model_validate(need).model_dump()
    if need.user:
        item["user"] = UserBrief.model_validate(need.user).model_dump()

    return ApiResponse(
        code=200,
        message="success",
        data=item,
    )


@router.post("", response_model=ApiResponse)
def create_need(
    req: BusinessNeedCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发布需求（需登录）"""
    need = BusinessNeed(
        user_id=current_user.id,
        title=req.title,
        description=req.description,
        category=req.category,
        budget=req.budget,
        region=req.region,
        contact_name=req.contact_name,
        contact_phone=req.contact_phone,
        status="open",
    )
    db.add(need)
    db.commit()
    db.refresh(need)

    return ApiResponse(
        code=200,
        message="需求发布成功",
        data=BusinessNeedResponse.model_validate(need).model_dump(),
    )


@router.put("/{need_id}", response_model=ApiResponse)
def update_need(
    need_id: int,
    req: BusinessNeedUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """修改需求（仅发布者或管理员）"""
    need = db.query(BusinessNeed).filter(
        BusinessNeed.id == need_id,
        BusinessNeed.is_deleted == False,
    ).first()
    if not need:
        raise HTTPException(status_code=404, detail="需求不存在")

    if need.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权修改此需求")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(need, field, value)

    db.commit()
    db.refresh(need)

    return ApiResponse(
        code=200,
        message="需求更新成功",
        data=BusinessNeedResponse.model_validate(need).model_dump(),
    )


@router.delete("/{need_id}", response_model=ApiResponse)
def delete_need(
    need_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除需求（仅发布者或管理员）"""
    need = db.query(BusinessNeed).filter(
        BusinessNeed.id == need_id,
        BusinessNeed.is_deleted == False,
    ).first()
    if not need:
        raise HTTPException(status_code=404, detail="需求不存在")

    if need.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除此需求")

    need.is_deleted = True
    need.deleted_at = datetime.utcnow()
    db.commit()

    return ApiResponse(
        code=200,
        message="需求删除成功",
        data=None,
    )
