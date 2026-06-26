"""链客宝 — 通知服务层
=====================
NotificationManager: 统一通知管理器，支持多通道。

当前支持的通道:
    - email:    邮件 (预留接口)
    - sms:      短信 (预留接口)
    - feishu:   飞书群机器人
    - dingtalk: 钉钉群机器人
"""

import logging
from typing import Optional

from app.im_bot import FeishuBot, DingTalkBot

logger = logging.getLogger(__name__)

# 全局 bot 实例（懒加载）
_feishu_bot: Optional[FeishuBot] = None
_dingtalk_bot: Optional[DingTalkBot] = None


def _get_feishu_bot() -> FeishuBot:
    global _feishu_bot
    if _feishu_bot is None:
        _feishu_bot = FeishuBot()
    return _feishu_bot


def _get_dingtalk_bot() -> DingTalkBot:
    global _dingtalk_bot
    if _dingtalk_bot is None:
        _dingtalk_bot = DingTalkBot()
    return _dingtalk_bot


class NotificationManager:
    """统一通知管理器

    用法:
        mgr = NotificationManager()
        mgr.send("feishu", title="告警", content="服务异常", webhook_url="...")
        mgr.send("dingtalk", title="通知", content="任务完成", webhook_url="...")
    """

    # 支持的通道列表
    SUPPORTED_CHANNELS = {"email", "sms", "feishu", "dingtalk"}

    def send(
        self,
        channel: str,
        title: str = "",
        content: str = "",
        webhook_url: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """发送通知

        Args:
            channel:     通道名称 ("email", "sms", "feishu", "dingtalk")
            title:       消息标题
            content:     消息正文
            webhook_url: 仅 feishu/dingtalk 通道有效，自定义 Webhook URL
            **kwargs:    各通道扩展参数
                - feishu:   msg_type="interactive" | "text"
                - dingtalk: msg_type="markdown" | "text"

        Returns:
            dict: {"channel": str, "success": bool, "detail": ...}

        Raises:
            ValueError: 不支持的通道名称
        """
        channel = channel.lower()
        if channel not in self.SUPPORTED_CHANNELS:
            raise ValueError(
                f"不支持的通道 '{channel}'，可选: {', '.join(sorted(self.SUPPORTED_CHANNELS))}"
            )

        if channel == "feishu":
            bot = _get_feishu_bot()
            msg_type = kwargs.get("msg_type", "interactive")
            result = bot.send_webhook(
                url=webhook_url,
                title=title,
                content=content,
                msg_type=msg_type,
            )
            return {
                "channel": "feishu",
                "success": result.get("success", False),
                "detail": result,
            }

        elif channel == "dingtalk":
            bot = _get_dingtalk_bot()
            msg_type = kwargs.get("msg_type", "markdown")
            result = bot.send_webhook(
                url=webhook_url,
                title=title,
                content=content,
                msg_type=msg_type,
            )
            return {
                "channel": "dingtalk",
                "success": result.get("success", False),
                "detail": result,
            }

        elif channel == "email":
            # ── 预留：邮件通知 ──
            logger.warning("[NotificationManager] email 通道尚未实现")
            return {
                "channel": "email",
                "success": False,
                "detail": {"error": "email 通道尚未实现"},
            }

        elif channel == "sms":
            # ── 预留：短信通知 ──
            logger.warning("[NotificationManager] sms 通道尚未实现")
            return {
                "channel": "sms",
                "success": False,
                "detail": {"error": "sms 通道尚未实现"},
            }

        # 不会执行到这里（前面已做校验），但保持完备性
        return {"channel": channel, "success": False, "detail": {"error": "未知通道"}}
