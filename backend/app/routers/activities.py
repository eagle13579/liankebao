"""
链客宝 — 联系人活动时间线 API 路由
====================================
迁移自旧版链客宝 backend/app/routers/activities.py
适配 chainke-full 架构。

端点:
  GET    /api/contacts/{contact_id}/activities — 获取联系人的活动列表（分页）
  POST   /api/contacts/{contact_id}/activities — 为联系人添加活动
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["联系人活动"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CreateActivityRequest(BaseModel):
    """创建活动请求"""
    action_type: str = Field(
        ...,
        pattern=r"^(note|call|meeting|email|wechat|order|import)$",
        description="活动类型: note/call/meeting/email/wechat/order/import",
    )
    summary: str | None = Field(default=None, max_length=200, description="活动概要")
    detail: str | None = Field(default=None, description="活动详情")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 常量
# ===================================================================

VALID_ACTION_TYPES = {"note", "call", "meeting", "email", "wechat", "order", "import"}


# ===================================================================
# 辅助函数
# ===================================================================


def _get_contact_or_404(contact_id: int, owner_id: int, db: Session):
    """获取联系人并校验所有权，不存在则抛 404"""
    try:
        from features.contacts.models.contact import Contact
    except ImportError:
        raise HTTPException(status_code=500, detail="contacts 模块未安装")

    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.owner_id == owner_id,
            Contact.is_deleted == False,
        )
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")
    return contact


def format_activity_response(activity) -> dict:
    """将 Activity ORM 实例转为前端友好格式"""
    return activity.to_dict()


# ===================================================================
# 路由实现
# ===================================================================


@router.get("/{contact_id}/activities", response_model=ApiResponse)
async def list_activities(
    contact_id: int,
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """获取联系人的活动列表（按时间倒序）"""
    try:
        # 校验联系人和所有权
        _get_contact_or_404(contact_id, owner_id, db)

        from features.activities.services.activity_service import ActivityService

        service = ActivityService(db)
        items, total = service.list_activities(
            contact_id=contact_id,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(
            code=0,
            message="success",
            data={
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [format_activity_response(a) for a in items],
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="activities 模块未安装")


@router.post("/{contact_id}/activities", response_model=ApiResponse, status_code=201)
async def create_activity(
    contact_id: int,
    req: CreateActivityRequest,
    owner_id: int = Query(..., gt=0, description="所属用户 ID"),
    db: Session = Depends(get_db),
):
    """为联系人添加活动"""
    try:
        # 校验联系人和所有权
        _get_contact_or_404(contact_id, owner_id, db)

        # 校验 action_type 合法值
        if req.action_type not in VALID_ACTION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"无效的活动类型，可选值: {', '.join(sorted(VALID_ACTION_TYPES))}",
            )

        from features.activities.services.activity_service import ActivityService

        service = ActivityService(db)
        activity = service.create_activity(
            contact_id=contact_id,
            action_type=req.action_type,
            summary=req.summary,
            detail=req.detail,
            owner_id=owner_id,
        )
        return ApiResponse(
            code=0,
            message="添加成功",
            data=format_activity_response(activity),
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="activities 模块未安装")
