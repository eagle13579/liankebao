"""
活动服务层 (Activity Service)
=============================
迁移自旧版链客宝 backend/modules/activities/services/
提供活动 CRUD 管理。

用法:
    from features.activities.services.activity_service import ActivityService
    service = ActivityService(db)
    activities = service.list_activities(...)
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from features.activities.models.activity import Activity

logger = logging.getLogger(__name__)


class ActivityService:
    """活动业务服务"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    def _base_query(self):
        """未删除活动查询"""
        return self.db.query(Activity).filter(
            Activity.is_deleted == False,
        )

    # ------------------------------------------------------------------
    # list_activities — 获取联系人的活动列表
    # ------------------------------------------------------------------

    def list_activities(
        self,
        contact_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Activity], int]:
        """获取指定联系人的活动列表（按时间倒序）"""
        query = (
            self._base_query()
            .filter(Activity.contact_id == contact_id)
        )
        total = query.count()
        items = (
            query.order_by(desc(Activity.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # create_activity — 创建活动
    # ------------------------------------------------------------------

    def create_activity(
        self,
        contact_id: int,
        action_type: str,
        summary: Optional[str] = None,
        detail: Optional[str] = None,
        owner_id: int = 0,
    ) -> Activity:
        """为联系人创建活动记录"""
        activity = Activity(
            contact_id=contact_id,
            action_type=action_type,
            summary=summary,
            detail=detail,
            owner_id=owner_id,
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)

        logger.info(
            "活动创建成功",
            extra={
                "contact_id": contact_id,
                "activity_id": activity.id,
                "action_type": action_type,
            },
        )
        return activity
