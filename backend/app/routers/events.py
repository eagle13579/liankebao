"""用户行为事件埋点路由"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", summary="记录用户行为事件", description="记录用户的浏览、点击、搜索等行为事件")
def create_event(
    user_id: int = None,
    event_type: str = None,
    target_type: str = None,
    target_id: int = None,
    search_keyword: str = None,
    session_id: str = None,
    page_url: str = None,
    db: Session = Depends(get_db),
):
    """记录一条用户行为事件（支持 JSON body 和 query params）"""
    # 兼容POST JSON body

    # 如果通过 query params 传入则直接使用
    if event_type is None:
        return {"code": 400, "message": "event_type 是必填字段"}

    event = UserEvent(
        user_id=user_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        search_keyword=search_keyword,
        session_id=session_id,
        page_url=page_url,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(
        "user_event",
        extra={
            "event_id": event.id,
            "user_id": user_id,
            "event_type": event_type,
            "target_type": target_type,
            "target_id": target_id,
            "search_keyword": search_keyword,
        },
    )

    return {"code": 200, "message": "success", "data": {"id": event.id}}


# 同时支持 POST JSON body
@router.post("/track", summary="记录用户行为事件（JSON body）", include_in_schema=False)
async def create_event_json(request: Request, db: Session = Depends(get_db)):
    """记录一条用户行为事件（接受完整的 JSON body）"""
    body = await request.json()
    user_id = body.get("user_id")
    event_type = body.get("event_type")
    target_type = body.get("target_type")
    target_id = body.get("target_id")
    search_keyword = body.get("search_keyword")
    session_id = body.get("session_id")
    page_url = body.get("page_url")

    if not event_type:
        return {"code": 400, "message": "event_type 是必填字段"}

    event = UserEvent(
        user_id=user_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        search_keyword=search_keyword,
        session_id=session_id,
        page_url=page_url,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(
        "user_event",
        extra={
            "event_id": event.id,
            "user_id": user_id,
            "event_type": event_type,
            "target_type": target_type,
            "target_id": target_id,
            "search_keyword": search_keyword,
        },
    )

    return {"code": 200, "message": "success", "data": {"id": event.id}}


@router.get("/user/{user_id}/recent", summary="获取用户最近行为事件", description="获取指定用户的最近行为事件")
def get_user_recent_events(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    event_type: str = Query(None, description="按事件类型筛选"),
    db: Session = Depends(get_db),
):
    """获取用户最近的N条行为事件"""
    query = db.query(UserEvent).filter(UserEvent.user_id == user_id)

    if event_type:
        query = query.filter(UserEvent.event_type == event_type)

    events = query.order_by(UserEvent.created_at.desc()).limit(limit).all()

    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "event_type": e.event_type,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "search_keyword": e.search_keyword,
                "session_id": e.session_id,
                "page_url": e.page_url,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


@router.get("/stats/hot-products", summary="热门产品统计", description="按浏览量统计热门产品TOP N")
def get_hot_products(
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """统计一段时间内浏览量最高的产品"""
    since = datetime.utcnow() - timedelta(days=days)

    # 统计 product_view 和 product_click 事件的 target_id 出现次数
    stats = (
        db.query(
            UserEvent.target_id,
            func.count(UserEvent.id).label("view_count"),
        )
        .filter(
            UserEvent.event_type.in_(["product_view", "product_click"]),
            UserEvent.target_id.isnot(None),
            UserEvent.created_at >= since,
        )
        .group_by(UserEvent.target_id)
        .order_by(func.count(UserEvent.id).desc())
        .limit(limit)
        .all()
    )

    return {
        "code": 200,
        "message": "success",
        "data": [{"target_id": row.target_id, "view_count": row.view_count} for row in stats],
    }
