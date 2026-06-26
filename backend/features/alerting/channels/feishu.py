"""
飞书通知通道 (FeishuNotifier)
==============================
通过飞书 Webhook 发送告警通知，支持三种消息类型:
- text:       纯文本消息
- markdown:   Markdown 富文本消息（飞书卡片）
- interactive: 飞书 Interactive Card（结构化卡片）

环境变量:
    FEISHU_WEBHOOK_URL: 飞书机器人 Webhook URL

快速开始:
    from backend.features.alerting.channels.feishu import FeishuNotifier

    notifier = FeishuNotifier()
    notifier.send_text("Hello, 链客宝!")
    notifier.send_markdown("**告警**: 数据库连接超时")
    notifier.send_card("系统告警", "CPU 使用率超过 90%", level="CRITICAL")
"""

import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# 环境变量名
ENV_FEISHU_WEBHOOK_URL = "FEISHU_WEBHOOK_URL"

# 默认请求超时（秒）
_DEFAULT_TIMEOUT = 10


class FeishuMessageType(Enum):
    """飞书消息类型"""

    TEXT = "text"
    MARKDOWN = "markdown"
    INTERACTIVE = "interactive"


class FeishuNotifier:
    """飞书 Webhook 通知通道

    封装对飞书机器人 Webhook 的调用，支持文本、Markdown 和 Interactive Card 三种消息格式。

    Usage:
        notifier = FeishuNotifier(webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        notifier.send_text("服务已启动")
        notifier.send_markdown("**警告**: 磁盘使用率 **85%**")
        notifier.send_card("严重告警", "服务不可用", level="CRITICAL")
    """

    def __init__(self, webhook_url: Optional[str] = None) -> None:
        """初始化飞书通知通道

        Args:
            webhook_url: 飞书 Webhook URL。不传则从环境变量 FEISHU_WEBHOOK_URL 读取。
                        两者都为空时，消息仅记录日志不会发送。
        """
        self._webhook_url = webhook_url or os.environ.get(ENV_FEISHU_WEBHOOK_URL, "")
        if not self._webhook_url:
            logger.warning(
                "FeishuNotifier: 未配置 Webhook URL "
                "(可通过构造函数参数或 %s 环境变量设置)",
                ENV_FEISHU_WEBHOOK_URL,
            )

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def send_text(self, text: str, title: str = "链客宝通知") -> bool:
        """发送纯文本消息

        Args:
            text:  消息正文
            title: 消息标题

        Returns:
            True 表示发送成功或无配置，False 表示发送失败
        """
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": [
                    {"tag": "markdown", "content": text},
                    self._footer_element(),
                ],
            },
        }
        return self._send(payload)

    def send_markdown(self, markdown: str, title: str = "链客宝通知") -> bool:
        """发送 Markdown 富文本消息

        Args:
            markdown: Markdown 格式的消息内容
            title:    消息卡片标题

        Returns:
            True 表示发送成功或无配置，False 表示发送失败
        """
        return self.send_text(markdown, title=title)

    def send_card(
        self,
        title: str,
        content: str,
        level: str = "INFO",
        fields: Optional[list[dict[str, str]]] = None,
    ) -> bool:
        """发送结构化 Interactive Card

        Args:
            title:   卡片标题
            content: 卡片正文（支持 Markdown）
            level:   告警级别 (INFO / WARN / CRITICAL)
            fields:  可选字段列表，格式: [{"key": "指标", "value": "数值"}, ...]

        Returns:
            True 表示发送成功或无配置，False 表示发送失败
        """
        elements: list[dict[str, Any]] = []

        # 正文
        elements.append({"tag": "markdown", "content": content})

        # 可选字段表
        if fields:
            elements.append({"tag": "hr"})
            for f in fields:
                elements.append(
                    {
                        "tag": "column_set",
                        "flex_mode": "bisect",
                        "background_style": "default",
                        "columns": [
                            {
                                "tag": "column",
                                "width": "weighted",
                                "weight": 1,
                                "elements": [
                                    {
                                        "tag": "plain_text",
                                        "content": f.get("key", ""),
                                    }
                                ],
                            },
                            {
                                "tag": "column",
                                "width": "weighted",
                                "weight": 2,
                                "elements": [
                                    {
                                        "tag": "lark_md",
                                        "content": f.get("value", ""),
                                    }
                                ],
                            },
                        ],
                    }
                )

        # 颜色映射
        color_map = {
            "CRITICAL": "red",
            "WARN": "orange",
            "INFO": "blue",
            "DEBUG": "grey",
        }
        header_color = color_map.get(level.upper(), "blue")

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": header_color,
                },
                "elements": [*elements, self._footer_element()],
            },
        }
        return self._send(payload)

    def send_alert(
        self,
        title: str,
        message: str,
        level: str = "INFO",
        metric: Optional[str] = None,
        value: Optional[str] = None,
    ) -> bool:
        """发送标准告警消息（便捷方法）

        整合标题、级别、指标和数值到一个告警卡片中。

        Args:
            title:   告警标题
            message: 告警描述
            level:   告警级别 (INFO / WARN / CRITICAL)
            metric:  触发指标名称（可选）
            value:   当前值（可选）

        Returns:
            True 表示发送成功或无配置，False 表示发送失败
        """
        fields = []
        if metric:
            fields.append({"key": "指标", "value": metric})
        if value:
            fields.append({"key": "当前值", "value": value})

        return self.send_card(
            title=f"[{level}] {title}",
            content=message,
            level=level,
            fields=fields if fields else None,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _send(self, payload: dict[str, Any]) -> bool:
        """发送消息到飞书 Webhook

        Args:
            payload: 飞书 API 请求体（字典）

        Returns:
            True 表示成功或无配置，False 表示失败
        """
        if not self._webhook_url:
            logger.info("FeishuNotifier: Webhook URL 未配置，消息已忽略")
            return True

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            self._webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            resp = urlopen(req, timeout=_DEFAULT_TIMEOUT)
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("StatusCode") == 0:
                logger.debug("FeishuNotifier: 消息推送成功")
                return True
            else:
                logger.warning("FeishuNotifier: 推送返回异常 - %s", body)
                return False
        except URLError as exc:
            logger.error("FeishuNotifier: 网络错误 - %s", exc)
            return False
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("FeishuNotifier: 推送异常 - %s", exc)
            return False

    @staticmethod
    def _footer_element() -> dict[str, Any]:
        """生成卡片底部元信息元素"""
        return {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": (
                        f"链客宝监控系统 · "
                        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    ),
                },
            ],
        }

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def webhook_url(self) -> Optional[str]:
        """当前配置的 Webhook URL"""
        return self._webhook_url or None

    @webhook_url.setter
    def webhook_url(self, url: str) -> None:
        """动态设置 Webhook URL"""
        self._webhook_url = url
