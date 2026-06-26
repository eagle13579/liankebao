"""链客宝 — IM Bot 通知 API
===========================
通知相关的 HTTP 接口层。

端点:
    POST /api/notifications/bot/test     — 测试 Webhook 连接
    POST /api/notifications/bot/register — 注册新的 Webhook URL
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.im_bot import FeishuBot, DingTalkBot
from app.services.notification_service import NotificationManager

logger = logging.getLogger(__name__)

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/notifications", tags=["通知"])

# ===================================================================
# Pydantic 模型
# ===================================================================


class BotTestRequest(BaseModel):
    """测试 Webhook 请求体"""

    platform: str = Field(
        ..., description="平台: feishu | dingtalk"
    )
    webhook_url: str = Field(
        ..., description="Webhook URL"
    )
    title: str = Field(
        "链客宝测试通知", description="消息标题"
    )
    content: str = Field(
        "这是一条来自链客宝后端的测试消息，收到此消息表示 Webhook 配置正确。",
        description="消息正文",
    )
    msg_type: Optional[str] = Field(
        None, description="消息类型 (feishu: text/interactive, dingtalk: text/markdown)"
    )


class BotTestResponse(BaseModel):
    """测试 Webhook 响应体"""

    success: bool
    platform: str
    message: str
    detail: dict


class BotRegisterRequest(BaseModel):
    """注册 Webhook 请求体"""

    platform: str = Field(
        ..., description="平台: feishu | dingtalk"
    )
    webhook_url: str = Field(
        ..., description="Webhook URL"
    )
    name: Optional[str] = Field(
        None, description="自定义名称（仅用于备注，不持久化存储）"
    )


class BotRegisterResponse(BaseModel):
    """注册 Webhook 响应体"""

    success: bool
    platform: str
    message: str
    note: str


# ===================================================================
# POST /api/notifications/bot/test — 测试 Webhook
# ===================================================================


@router.post("/bot/test", response_model=BotTestResponse)
async def test_bot_webhook(req: BotTestRequest):
    """测试飞书或钉钉群机器人 Webhook 连接是否正常

    发送一条测试消息到指定的 Webhook URL，验证配置是否正确。
    """
    platform = req.platform.lower()

    if platform == "feishu":
        bot = FeishuBot()
        msg_type = req.msg_type or "interactive"
        if msg_type not in ("text", "interactive"):
            raise HTTPException(
                status_code=422,
                detail=f"飞书消息类型必须为 'text' 或 'interactive'，收到: {msg_type}",
            )
        result = bot.send_webhook(
            url=req.webhook_url,
            title=req.title,
            content=req.content,
            msg_type=msg_type,
        )
    elif platform == "dingtalk":
        bot = DingTalkBot()
        msg_type = req.msg_type or "markdown"
        if msg_type not in ("text", "markdown"):
            raise HTTPException(
                status_code=422,
                detail=f"钉钉消息类型必须为 'text' 或 'markdown'，收到: {msg_type}",
            )
        result = bot.send_webhook(
            url=req.webhook_url,
            title=req.title,
            content=req.content,
            msg_type=msg_type,
        )
    else:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的平台 '{platform}'，可选: feishu, dingtalk",
        )

    success = result.get("success", False)
    return BotTestResponse(
        success=success,
        platform=platform,
        message="Webhook 测试消息发送成功" if success else "Webhook 测试消息发送失败",
        detail=result,
    )


# ===================================================================
# POST /api/notifications/bot/register — 注册 Webhook
# ===================================================================


@router.post("/bot/register", response_model=BotRegisterResponse)
async def register_bot_webhook(req: BotRegisterRequest):
    """注册一个新的 Webhook URL

    将 Webhook URL 写入环境变量（注意：重启后失效，生产环境请使用持久化存储）。

    后端暂不持久化存储 Webhook 注册信息。
    如需持久化，请将 Webhook URL 写入 .env 文件或数据库。
    """
    platform = req.platform.lower()

    if platform not in ("feishu", "dingtalk"):
        raise HTTPException(
            status_code=422,
            detail=f"不支持的平台 '{platform}'，可选: feishu, dingtalk",
        )

    # 简单校验 Webhook URL 格式
    if not req.webhook_url.startswith("https://"):
        raise HTTPException(
            status_code=422,
            detail="Webhook URL 必须以 https:// 开头",
        )

    # 测试一下 Webhook 连通性
    test_content = f"链客宝 Bot 注册确认 — {req.name or platform} Webhook 配置成功"

    if platform == "feishu":
        bot = FeishuBot()
        test_result = bot.send_webhook(
            url=req.webhook_url,
            title="Webhook 注册确认",
            content=test_content,
            msg_type="text",
        )
    else:
        bot = DingTalkBot()
        test_result = bot.send_webhook(
            url=req.webhook_url,
            title="Webhook 注册确认",
            content=test_content,
            msg_type="text",
        )

    if not test_result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=f"Webhook 连接测试失败: {test_result.get('response', '未知错误')}",
        )

    # 设置环境变量（仅当前进程有效，生产环境应写 .env 或数据库）
    env_key = "FEISHU_WEBHOOK_URL" if platform == "feishu" else "DINGTALK_WEBHOOK_URL"
    os.environ[env_key] = req.webhook_url

    # 也更新 bot 实例的默认 URL
    if platform == "feishu":
        FeishuBot.DEFAULT_WEBHOOK = req.webhook_url
    else:
        DingTalkBot.DEFAULT_WEBHOOK = req.webhook_url

    logger.info(
        f"[BotRegister] {platform} Webhook 注册成功: "
        f"{'name=' + req.name if req.name else ''} {req.webhook_url}"
    )

    return BotRegisterResponse(
        success=True,
        platform=platform,
        message=f"{platform} Webhook 注册成功",
        note=(
            f"Webhook URL 已设置为当前进程环境变量 {env_key}。"
            f"重启服务后需重新注册，或将 URL 写入 .env 文件以持久化。"
        ),
    )
