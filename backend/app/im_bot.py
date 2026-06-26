"""链客宝 — IM Bot 通知模块 (飞书/钉钉群机器人)
=============================================
纯 requests 实现，无第三方 SDK 依赖。

用法:
    from app.im_bot import FeishuBot, DingTalkBot

    # 飞书
    bot = FeishuBot()
    bot.send_webhook(url, "标题", "内容")

    # 钉钉
    bot = DingTalkBot()
    bot.send_webhook(url, "标题", "内容")
"""

import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ===================================================================
# FeishuBot — 飞书群机器人
# ===================================================================

class FeishuBot:
    """飞书群机器人通知

    支持两种消息类型:
        - text:        纯文本消息
        - interactive: 富文本卡片消息

    环境变量:
        FEISHU_WEBHOOK_URL — 默认飞书群机器人 Webhook URL
    """

    DEFAULT_WEBHOOK = os.getenv("FEISHU_WEBHOOK_URL", "")

    @staticmethod
    def _build_text_payload(title: str, content: str) -> dict:
        """构建飞书 text 类型消息 payload"""
        text_body = f"{title}\n\n{content}" if title else content
        return {
            "msg_type": "text",
            "content": {"text": text_body},
        }

    @staticmethod
    def _build_interactive_payload(title: str, content: str) -> dict:
        """构建飞书 interactive (卡片) 类型消息 payload"""
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title or "通知",
                    }
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                    }
                ],
            },
        }

    def send_webhook(
        self,
        url: Optional[str] = None,
        title: str = "",
        content: str = "",
        msg_type: str = "interactive",
    ) -> dict:
        """发送飞书群机器人消息

        Args:
            url:      飞书 Webhook URL。为 None 时使用 FEISHU_WEBHOOK_URL 环境变量
            title:    消息标题
            content:  消息正文
            msg_type: 消息类型: "text" | "interactive" (默认 interactive)

        Returns:
            dict: {"success": bool, "status_code": int, "response": str}

        Raises:
            ValueError: url 为空时抛出
        """
        webhook_url = url or self.DEFAULT_WEBHOOK
        if not webhook_url:
            raise ValueError(
                "飞书 Webhook URL 为空，请传入 url 参数或设置 FEISHU_WEBHOOK_URL 环境变量"
            )

        if msg_type == "text":
            payload = self._build_text_payload(title, content)
        else:
            payload = self._build_interactive_payload(title, content)

        try:
            resp = requests.post(
                webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()
            success = result.get("StatusCode") == 0 or result.get("code") == 0
            logger.info(
                f"[FeishuBot] 消息发送{'成功' if success else '失败'}: "
                f"status={resp.status_code}, response={result}"
            )
            return {
                "success": success,
                "status_code": resp.status_code,
                "response": result,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[FeishuBot] 请求异常: {e}")
            return {"success": False, "status_code": 0, "response": str(e)}


# ===================================================================
# DingTalkBot — 钉钉群机器人
# ===================================================================

class DingTalkBot:
    """钉钉群机器人通知

    支持两种消息类型:
        - text:    纯文本消息
        - markdown: Markdown 格式消息

    环境变量:
        DINGTALK_WEBHOOK_URL — 默认钉钉群机器人 Webhook URL
    """

    DEFAULT_WEBHOOK = os.getenv("DINGTALK_WEBHOOK_URL", "")

    @staticmethod
    def _build_text_payload(title: str, content: str) -> dict:
        """构建钉钉 text 类型消息 payload"""
        text_body = f"{title}\n\n{content}" if title else content
        return {
            "msgtype": "text",
            "text": {"content": text_body},
        }

    @staticmethod
    def _build_markdown_payload(title: str, content: str) -> dict:
        """构建钉钉 markdown 类型消息 payload"""
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title or "通知",
                "text": content,
            },
        }

    def send_webhook(
        self,
        url: Optional[str] = None,
        title: str = "",
        content: str = "",
        msg_type: str = "markdown",
    ) -> dict:
        """发送钉钉群机器人消息

        Args:
            url:      钉钉 Webhook URL。为 None 时使用 DINGTALK_WEBHOOK_URL 环境变量
            title:    消息标题 (markdown 类型必填)
            content:  消息正文
            msg_type: 消息类型: "text" | "markdown" (默认 markdown)

        Returns:
            dict: {"success": bool, "status_code": int, "response": str}

        Raises:
            ValueError: url 为空时抛出
        """
        webhook_url = url or self.DEFAULT_WEBHOOK
        if not webhook_url:
            raise ValueError(
                "钉钉 Webhook URL 为空，请传入 url 参数或设置 DINGTALK_WEBHOOK_URL 环境变量"
            )

        if msg_type == "text":
            payload = self._build_text_payload(title, content)
        else:
            payload = self._build_markdown_payload(title, content)

        try:
            resp = requests.post(
                webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()
            # 钉钉成功返回: {"errcode": 0, "errmsg": "ok"}
            success = result.get("errcode") == 0
            logger.info(
                f"[DingTalkBot] 消息发送{'成功' if success else '失败'}: "
                f"status={resp.status_code}, response={result}"
            )
            return {
                "success": success,
                "status_code": resp.status_code,
                "response": result,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[DingTalkBot] 请求异常: {e}")
            return {"success": False, "status_code": 0, "response": str(e)}


# ===================================================================
# 快捷函数
# ===================================================================

_feishu_bot = FeishuBot()
_dingtalk_bot = DingTalkBot()


def send_feishu(
    url: Optional[str] = None,
    title: str = "",
    content: str = "",
    msg_type: str = "interactive",
) -> dict:
    """快捷发送飞书消息"""
    return _feishu_bot.send_webhook(url=url, title=title, content=content, msg_type=msg_type)


def send_dingtalk(
    url: Optional[str] = None,
    title: str = "",
    content: str = "",
    msg_type: str = "markdown",
) -> dict:
    """快捷发送钉钉消息"""
    return _dingtalk_bot.send_webhook(url=url, title=title, content=content, msg_type=msg_type)
