"""线上闭门对接会路由
POST   /api/events/online              — 创建线上对接会（管理员）
GET    /api/events/online              — 获取对接会列表
POST   /api/events/online/{id}/register  — 报名（仅钻石会员）
POST   /api/events/online/{id}/feedback  — 提交会后反馈
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import OnlineMatchingEvent, OnlineMatchingFeedback, OnlineMatchingRegistration, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events/online", tags=["线上对接会"])

# ============================================================
# Pydantic 请求模型
# ============================================================


class CreateEventRequest(BaseModel):
    """创建线上对接会请求"""

    title: str = Field(..., min_length=1, max_length=200, description="活动标题")
    description: str | None = Field(None, description="活动描述")
    cover_image: str | None = Field(None, description="活动封面图URL")
    event_date: str = Field(..., description="活动日期/时间(ISO格式)")
    end_date: str | None = Field(None, description="活动结束日期/时间(ISO格式)")
    location: str | None = Field(None, description="活动地点/线上会议链接")
    max_participants: int = Field(100, ge=1, le=10000, description="最大参与人数")
    price: float = Field(0.0, ge=0, description="参与价格(0=免费)")
    tags: str | None = Field(None, description="标签(逗号分隔)")


class RegisterRequest(BaseModel):
    """报名请求"""

    company: str | None = Field(None, max_length=200, description="公司名称")
    position: str | None = Field(None, max_length=100, description="职位")
    phone: str | None = Field(None, max_length=20, description="电话")
    notes: str | None = Field(None, description="需求说明")


class FeedbackRequest(BaseModel):
    """反馈请求"""

    rating: int = Field(5, ge=1, le=5, description="评分 1-5")
    comment: str | None = Field(None, description="反馈内容")


# ============================================================
# API 端点
# ============================================================


@router.post("")
def create_event(
    req: CreateEventRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """【管理员】创建线上对接会"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可创建对接会")

    try:
        event_date = datetime.fromisoformat(req.event_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="event_date 格式无效，请使用 ISO 格式 (如 2025-06-15T14:00:00)")

    end_date = None
    if req.end_date:
        try:
            end_date = datetime.fromisoformat(req.end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式无效，请使用 ISO 格式")

    event = OnlineMatchingEvent(
        title=req.title,
        description=req.description,
        cover_image=req.cover_image,
        event_date=event_date,
        end_date=end_date,
        location=req.location,
        max_participants=req.max_participants,
        current_participants=0,
        price=req.price,
        status="published",
        tags=req.tags,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"线上对接会已创建: id={event.id}, title={event.title}")

    return {
        "code": 200,
        "message": "创建成功",
        "data": _format_event(event),
    }


@router.get("")
def list_events(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: str | None = Query(None, description="按状态筛选: draft/published/ongoing/completed/cancelled"),
    db: Session = Depends(get_db),
):
    """获取线上对接会列表"""
    query = db.query(OnlineMatchingEvent).filter(OnlineMatchingEvent.is_deleted == False)

    if status:
        query = query.filter(OnlineMatchingEvent.status == status)

    total = query.count()
    events = (
        query.order_by(OnlineMatchingEvent.event_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "code": 200,
        "message": "success",
        "data": [_format_event(e) for e in events],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{event_id}")
def get_event_detail(
    event_id: int,
    current_user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取对接会详情"""
    event = db.query(OnlineMatchingEvent).filter(
        OnlineMatchingEvent.id == event_id,
        OnlineMatchingEvent.is_deleted == False,
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="对接会不存在")

    # 检查当前用户是否已报名
    is_registered = False
    if current_user:
        reg = db.query(OnlineMatchingRegistration).filter(
            OnlineMatchingRegistration.event_id == event_id,
            OnlineMatchingRegistration.user_id == current_user.id,
        ).first()
        is_registered = reg is not None

    data = _format_event(event)
    data["is_registered"] = is_registered

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }


@router.post("/{event_id}/register")
def register_event(
    event_id: int,
    req: RegisterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """报名线上对接会（仅钻石会员可报名）"""
    # 1. 校验会员等级：仅 diamond 及以上可参与线上闭门对接会
    valid_tiers = ["diamond", "board"]
    if current_user.membership_tier not in valid_tiers:
        raise HTTPException(
            status_code=403,
            detail="仅钻石会员及董事会会员可报名线上闭门对接会，请升级会员后重试",
        )

    # 检查会员是否过期
    if (
        current_user.membership_expires_at
        and current_user.membership_expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=403,
            detail="您的会员已过期，请续费后重试",
        )

    # 2. 校验活动
    event = db.query(OnlineMatchingEvent).filter(
        OnlineMatchingEvent.id == event_id,
        OnlineMatchingEvent.is_deleted == False,
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="对接会不存在")

    if event.status == "cancelled":
        raise HTTPException(status_code=400, detail="对接会已取消")

    if event.status == "completed":
        raise HTTPException(status_code=400, detail="对接会已结束")

    # 3. 检查是否已报名
    existing = db.query(OnlineMatchingRegistration).filter(
        OnlineMatchingRegistration.event_id == event_id,
        OnlineMatchingRegistration.user_id == current_user.id,
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="您已报名该对接会")

    # 4. 检查名额
    if event.current_participants >= event.max_participants:
        raise HTTPException(status_code=400, detail="报名人数已满")

    # 5. 创建报名记录
    registration = OnlineMatchingRegistration(
        event_id=event_id,
        user_id=current_user.id,
        status="confirmed",
        company=req.company or current_user.company,
        position=req.position or current_user.position,
        phone=req.phone or current_user.phone,
        notes=req.notes,
    )
    db.add(registration)

    # 6. 更新参与人数
    event.current_participants += 1
    db.commit()
    db.refresh(registration)

    logger.info(f"用户 {current_user.id} 报名对接会 {event_id} 成功")

    return {
        "code": 200,
        "message": "报名成功",
        "data": {
            "registration_id": registration.id,
            "event_id": event_id,
            "status": registration.status,
            "event_title": event.title,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "location": event.location,
        },
    }


@router.post("/{event_id}/feedback")
def submit_feedback(
    event_id: int,
    req: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交线上对接会会后反馈"""
    # 1. 校验活动
    event = db.query(OnlineMatchingEvent).filter(
        OnlineMatchingEvent.id == event_id,
        OnlineMatchingEvent.is_deleted == False,
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="对接会不存在")

    # 2. 校验是否已报名该活动
    registration = db.query(OnlineMatchingRegistration).filter(
        OnlineMatchingRegistration.event_id == event_id,
        OnlineMatchingRegistration.user_id == current_user.id,
    ).first()

    if not registration:
        raise HTTPException(status_code=403, detail="仅已报名的用户可提交反馈")

    # 3. 检查是否已提交过反馈
    existing_feedback = db.query(OnlineMatchingFeedback).filter(
        OnlineMatchingFeedback.event_id == event_id,
        OnlineMatchingFeedback.user_id == current_user.id,
    ).first()

    if existing_feedback:
        raise HTTPException(status_code=400, detail="您已提交过反馈，不可重复提交")

    # 4. 创建反馈
    feedback = OnlineMatchingFeedback(
        event_id=event_id,
        user_id=current_user.id,
        rating=req.rating,
        comment=req.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    logger.info(f"用户 {current_user.id} 提交对接会 {event_id} 反馈: rating={req.rating}")

    return {
        "code": 200,
        "message": "反馈提交成功",
        "data": {
            "feedback_id": feedback.id,
            "rating": feedback.rating,
        },
    }


# ============================================================
# 辅助函数
# ============================================================


def _format_event(event: OnlineMatchingEvent) -> dict:
    """格式化活动数据"""
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "cover_image": event.cover_image,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "end_date": event.end_date.isoformat() if event.end_date else None,
        "location": event.location,
        "max_participants": event.max_participants,
        "current_participants": event.current_participants,
        "price": event.price,
        "status": event.status,
        "tags": event.tags.split(",") if event.tags else [],
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
