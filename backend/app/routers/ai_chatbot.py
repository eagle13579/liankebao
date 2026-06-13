"""链客宝AI客服机器人 API 路由

提供AI客服机器人的 REST API 端点：
  - POST /api/chatbot/message    — 发送消息，获取回复
  - GET  /api/chatbot/history    — 获取聊天历史
  - POST /api/chatbot/escalate   — 转人工客服
  - GET  /api/chatbot/faq        — 获取FAQ列表

设计对标：Intercom / Drift 在线客服API
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.models import User
from app.schemas import ApiResponse
from app.services.ai_chatbot import (
    get_chatbot_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chatbot", tags=["AI客服机器人"])

# ============================================================
# Pydantic 请求/响应模型
# ============================================================


class MessageRequest(BaseModel):
    """发送消息请求"""

    text: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="用户消息内容",
    )
    session_id: str | None = Field(
        None,
        description="会话ID（首次发送可不传，系统自动创建）",
    )


class MessageResponse(BaseModel):
    """消息回复响应"""

    session_id: str
    reply: str
    intent: str
    intent_confidence: float
    matched_faq: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    escalated: bool = False
    ticket: dict[str, Any] | None = None


class EscalateRequest(BaseModel):
    """转人工请求"""

    reason: str = Field(
        "",
        max_length=500,
        description="转人工原因",
    )
    session_id: str = Field(
        ...,
        description="会话ID",
    )


class FAQItemResponse(BaseModel):
    """FAQ条目响应"""

    question: str
    answer: str
    category: str
    keywords: list[str]


# ============================================================
# API 端点
# ============================================================


@router.post(
    "/message",
    summary="发送聊天消息",
    description="向AI客服发送消息并获取智能回复。支持意图识别、FAQ匹配、上下文管理和转人工。",
    response_model=ApiResponse,
)
def send_message(
    req: MessageRequest,
    current_user: User = Depends(get_current_user),
):
    """发送消息给AI客服机器人

    自动识别用户意图，匹配FAQ知识库，保持上下文记忆。
    如用户要求转人工，自动创建转人工工单。

    Args:
        req: 消息请求
        current_user: 当前认证用户

    Returns:
        ApiResponse 包含机器人回复
    """
    try:
        engine = get_chatbot_engine()
        result = engine.process_message(
            text=req.text,
            session_id=req.session_id,
            user_id=current_user.id,
        )

        return {
            "code": 200,
            "message": "success",
            "data": MessageResponse(
                session_id=result["session_id"],
                reply=result["reply"],
                intent=result["intent"],
                intent_confidence=result["intent_confidence"],
                matched_faq=result.get("matched_faq"),
                suggestions=result.get("suggestions", []),
                escalated=result.get("escalated", False),
                ticket=result.get("ticket"),
            ).model_dump(),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.error(
            "发送消息异常",
            extra={
                "user_id": current_user.id,
                "session_id": req.session_id,
                "error": str(exc),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="消息处理异常，请稍后再试",
        )


@router.get(
    "/history",
    summary="获取聊天历史",
    description="获取指定会话的聊天历史记录，支持分页。",
    response_model=ApiResponse,
)
def get_chat_history(
    session_id: str = Query(..., description="会话ID"),
    limit: int = Query(50, ge=1, le=200, description="返回消息数量上限"),
    current_user: User = Depends(get_current_user),
):
    """获取聊天历史

    Args:
        session_id: 会话ID
        limit: 返回消息数量上限
        current_user: 当前认证用户

    Returns:
        ApiResponse 包含消息历史列表
    """
    try:
        engine = get_chatbot_engine()
        history = engine.get_session_history(
            session_id=session_id,
            limit=limit,
        )

        return {
            "code": 200,
            "message": "success",
            "data": {
                "session_id": session_id,
                "total": len(history),
                "messages": history,
            },
        }

    except Exception as exc:
        logger.error(
            "获取聊天历史异常",
            extra={
                "user_id": current_user.id,
                "session_id": session_id,
                "error": str(exc),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="获取聊天历史异常",
        )


@router.post(
    "/escalate",
    summary="转人工客服",
    description="创建转人工工单，客服人员将尽快联系用户。",
    response_model=ApiResponse,
)
def escalate_to_human(
    req: EscalateRequest,
    current_user: User = Depends(get_current_user),
):
    """转人工客服

    创建转人工工单，包含会话上下文摘要。

    Args:
        req: 转人工请求
        current_user: 当前认证用户

    Returns:
        ApiResponse 包含工单信息
    """
    try:
        engine = get_chatbot_engine()
        result = engine.create_escalation_ticket(
            session_id=req.session_id,
            reason=req.reason or "用户主动申请转人工",
            user_id=current_user.id,
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="会话不存在，请先发送消息",
            )

        return {
            "code": 200,
            "message": "success",
            "data": {
                "session_id": result["session_id"],
                "reply": result["reply"],
                "escalated": True,
                "ticket": result.get("ticket"),
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "转人工异常",
            extra={
                "user_id": current_user.id,
                "session_id": req.session_id,
                "error": str(exc),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="转人工处理异常",
        )


@router.get(
    "/faq",
    summary="获取FAQ列表",
    description="获取AI客服知识库中的所有常见问题及回答。",
    response_model=ApiResponse,
)
def list_faqs(
    category: str | None = Query(
        None,
        description="按分类筛选：franchise / onboarding / contract / event / general / technology / enterprise / payment / account",
    ),
    current_user: User = Depends(get_current_user),
):
    """获取FAQ列表

    Args:
        category: 分类筛选（可选）
        current_user: 当前认证用户

    Returns:
        ApiResponse 包含FAQ条目列表
    """
    try:
        engine = get_chatbot_engine()
        faqs = engine.get_faqs_dict()

        if category:
            faqs = [f for f in faqs if f["category"] == category]

        return {
            "code": 200,
            "message": "success",
            "data": {
                "total": len(faqs),
                "items": [FAQItemResponse(**f).model_dump() for f in faqs],
            },
        }

    except Exception as exc:
        logger.error(
            "获取FAQ列表异常",
            extra={
                "user_id": current_user.id,
                "category": category,
                "error": str(exc),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="获取FAQ列表异常",
        )
