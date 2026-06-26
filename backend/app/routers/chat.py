"""
链客宝 — AI对话统一聊天API路由
=================================
连接前端AIChatWidget组件到ywhy-ai-backend的DeepSeek对话服务。

端点:
  POST /api/v1/chat  — 发送消息，获取AI回复

调用链:
  前端 → POST /api/v1/chat → ywhy-ai-backend (port 8100) → DeepSeek
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/v1/chat", tags=["AI对话"])

# ── ywhy-ai-backend 地址，可通过环境变量覆盖 ──────────────────────
_YWHY_AI_BASE_URL = os.getenv("YWHY_AI_BASE_URL", "http://localhost:8100")


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================

class ChatRequest(BaseModel):
    """聊天请求体"""
    message: str = Field(..., description="用户消息内容")
    session_id: Optional[str] = Field(None, description="会话ID（为空时自动生成）")


class ChatResponse(BaseModel):
    """聊天响应体"""
    reply: str = Field(..., description="AI回复内容")
    session_id: str = Field(..., description="会话ID")


# ===================================================================
# POST /api/v1/chat — 发送消息，获取AI回复
# ===================================================================

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """发送消息给AI助手，返回回复内容

    将请求转发到 ywhy-ai-backend 的 /api/chat/completion 端点，
    使用非流式模式获取完整回复。若未提供 session_id 则自动生成。
    """
    session_id = req.session_id or _generate_session_id()

    # 构造 ywhy-ai-backend 请求体
    payload = {
        "messages": [
            {"role": "user", "content": req.message}
        ],
        "model": "deepseek-chat",
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_YWHY_AI_BASE_URL}/api/chat/completion",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI服务响应超时")
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI服务不可用: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI服务调用失败: {str(e)}",
        )

    # 从 ywhy-ai-backend 响应中提取回复内容
    try:
        reply = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="AI服务返回格式异常",
        )

    return ChatResponse(reply=reply, session_id=session_id)


# ===================================================================
# 工具函数
# ===================================================================

def _generate_session_id() -> str:
    """生成唯一会话ID"""
    return f"chat_{uuid.uuid4().hex[:12]}"
