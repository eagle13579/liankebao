"""活动时间线路由：联系人的活动列表/添加"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Activity, Contact, User
from app.schemas import ActivityCreate, ActivityResponse, ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["联系人活动"])


def _get_contact_or_404(contact_id: int, user_id: int, db: Session) -> Contact:
    """获取联系人并校验所有权，不存在则抛 404"""
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.owner_id == user_id,
            Contact.is_deleted == False,
        )
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")
    return contact


@router.get("/{contact_id}/activities", response_model=ApiResponse)
def list_activities(
    contact_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取联系人的活动列表（按时间倒序）"""
    # 校验联系人和所有权
    _get_contact_or_404(contact_id, current_user.id, db)

    query = db.query(Activity).filter(
        Activity.contact_id == contact_id,
        Activity.is_deleted == False,
    )
    total = query.count()
    activities = query.order_by(desc(Activity.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    items = [ActivityResponse.model_validate(a) for a in activities]
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [item.model_dump() for item in items],
        },
    }


@router.post("/{contact_id}/activities", response_model=ApiResponse, status_code=201)
def create_activity(
    contact_id: int,
    activity_data: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为联系人添加活动"""
    # 校验联系人和所有权
    _get_contact_or_404(contact_id, current_user.id, db)

    # 校验 action_type 合法值
    valid_types = {"note", "call", "meeting", "email", "wechat", "order", "import"}
    if activity_data.action_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的活动类型，可选值: {', '.join(sorted(valid_types))}",
        )

    activity = Activity(
        contact_id=contact_id,
        action_type=activity_data.action_type,
        summary=activity_data.summary,
        detail=activity_data.detail,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    logger.info(
        "活动创建成功",
        extra={
            "contact_id": contact_id,
            "activity_id": activity.id,
            "action_type": activity.action_type,
            "user_id": current_user.id,
        },
    )
    return {
        "code": 201,
        "message": "添加成功",
        "data": ActivityResponse.model_validate(activity).model_dump(),
    }
