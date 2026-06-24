"""
链客宝 Webhook 事件系统 v2
==========================
复用已有 webhook.py (HMAC-SHA256验证+模块路由)
新增:
  1. 事件注册表 — 标准化事件类型
  2. 订阅管理 — CRUD订阅端点
  3. 重试机制 — 指数退避+死信队列
  4. 事件负载标准化 — CloudEvents格式
"""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


# ============================================================
# 事件类型枚举
# ============================================================


class EventType(str, Enum):
    # 匹配事件
    MATCH_CREATED = "match.created"
    MATCH_ACCEPTED = "match.accepted"
    MATCH_REJECTED = "match.rejected"
    MATCH_COMPLETED = "match.completed"

    # 订单事件
    ORDER_CREATED = "order.created"
    ORDER_PAID = "order.paid"
    ORDER_SHIPPED = "order.shipped"
    ORDER_COMPLETED = "order.completed"
    ORDER_CANCELLED = "order.cancelled"

    # 支付事件
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"

    # 用户事件
    USER_REGISTERED = "user.registered"
    USER_VERIFIED = "user.verified"
    USER_TRUST_CHANGED = "user.trust_changed"

    # 企业事件
    ENTERPRISE_VERIFIED = "enterprise.verified"
    ENTERPRISE_UPDATED = "enterprise.updated"

    # 名片事件
    CARD_CREATED = "card.created"
    CARD_UPDATED = "card.updated"
    CARD_VIEWED = "card.viewed"


# ============================================================
# 事件负载 (CloudEvents 格式)
# ============================================================


@dataclass
class WebhookEvent:
    """标准化 Webhook 事件 (CloudEvents v1.0 子集)"""

    id: str
    type: EventType
    source: str = "liankebao/api"
    time: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    data: dict[str, Any] = field(default_factory=dict)
    data_content_type: str = "application/json"
    subject: str | None = None  # 关联资源ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "specversion": "1.0",
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "time": self.time,
            "data": self.data,
            "datacontenttype": self.data_content_type,
            "subject": self.subject,
        }


# ============================================================
# Webhook订阅管理
# ============================================================


@dataclass
class WebhookSubscription:
    """Webhook 订阅"""

    id: str
    url: str
    events: list[EventType]
    secret: str  # HMAC签名密钥
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utcnow()).isoformat())
    retry_count: int = 0
    last_delivery_at: str | None = None
    last_delivery_status: str | None = None


# 内存订阅存储 (生产应使用数据库)
_subscriptions: dict[str, WebhookSubscription] = {}

# 死信队列
_dead_letter_queue: list[dict[str, Any]] = []


def create_subscription(
    sub_id: str,
    url: str,
    events: list[EventType],
    secret: str | None = None,
) -> WebhookSubscription:
    """创建 Webhook 订阅"""
    if not secret:
        secret = hashlib.sha256(f"{sub_id}-{time.time()}".encode()).hexdigest()[:32]
    sub = WebhookSubscription(id=sub_id, url=url, events=events, secret=secret)
    _subscriptions[sub_id] = sub
    logger.info(f"Webhook订阅已创建: {sub_id} → {url}")
    return sub


def delete_subscription(sub_id: str) -> bool:
    """删除订阅"""
    if sub_id in _subscriptions:
        del _subscriptions[sub_id]
        return True
    return False


def get_subscriptions() -> list[WebhookSubscription]:
    """获取所有订阅"""
    return list(_subscriptions.values())


def get_subscriptions_by_event(event_type: EventType) -> list[WebhookSubscription]:
    """获取订阅特定事件类型的订阅列表"""
    return [s for s in _subscriptions.values() if s.active and event_type in s.events]


# ============================================================
# Webhook 发送器 (带重试+签名)
# ============================================================


class WebhookDispatcher:
    """
    Webhook 分发器
    - HMAC-SHA256 签名
    - 指数退避重试 (最多3次)
    - 死信队列
    - 超时控制
    """

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2  # 秒
    TIMEOUT = 10  # 秒

    @staticmethod
    def _sign(payload: bytes, secret: str) -> str:
        """HMAC-SHA256 签名"""
        mac = hmac.new(secret.encode(), payload, hashlib.sha256)
        return mac.hexdigest()

    @classmethod
    def dispatch(cls, event: WebhookEvent) -> dict[str, Any]:
        """分发事件到所有匹配的订阅"""
        event_dict = event.to_dict()
        payload = json.dumps(event_dict).encode()
        subs = get_subscriptions_by_event(event.type)
        results = {"total": len(subs), "success": 0, "failed": 0, "details": []}

        for sub in subs:
            signature = cls._sign(payload, sub.secret)
            headers = {
                "Content-Type": "application/json",
                "X-Liankebao-Signature": f"sha256={signature}",
                "X-Liankebao-Event": event.type.value,
                "X-Liankebao-Delivery": event.id,
                "User-Agent": "Liankebao-Webhook/2.0",
            }

            success = False
            for attempt in range(1, cls.MAX_RETRIES + 1):
                try:
                    req = Request(sub.url, data=payload, headers=headers, method="POST")
                    with urlopen(req, timeout=cls.TIMEOUT) as resp:
                        status = resp.status
                    if 200 <= status < 300:
                        success = True
                        sub.last_delivery_status = f"200 (attempt {attempt})"
                        break
                    else:
                        sub.last_delivery_status = f"{status} (attempt {attempt})"
                except Exception as e:
                    sub.last_delivery_status = f"error: {e} (attempt {attempt})"
                    if attempt < cls.MAX_RETRIES:
                        delay = cls.RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        time.sleep(delay)

            sub.last_delivery_at = datetime.now(UTC).isoformat()
            sub.retry_count += 1 if not success else 0

            detail = {
                "subscription_id": sub.id,
                "url": sub.url,
                "success": success,
                "status": sub.last_delivery_status,
            }
            results["details"].append(detail)

            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
                # 入死信队列
                _dead_letter_queue.append(
                    {
                        "event": event_dict,
                        "subscription_id": sub.id,
                        "failed_at": datetime.now(UTC).isoformat(),
                        "retries": cls.MAX_RETRIES,
                    }
                )
                logger.warning(f"Webhook交付失败: {sub.id} → {sub.url}")

        return results


# ============================================================
# 便捷函数
# ============================================================

_dispatcher = WebhookDispatcher()


def emit_event(event_type: EventType, data: dict[str, Any], subject: str | None = None) -> dict[str, Any]:
    """发送事件 — 主入口"""
    import uuid

    event = WebhookEvent(
        id=str(uuid.uuid4()),
        type=event_type,
        data=data,
        subject=subject,
    )
    return _dispatcher.dispatch(event)


def emit_match_created(match_data: dict[str, Any]) -> dict[str, Any]:
    """匹配创建事件"""
    return emit_event(EventType.MATCH_CREATED, match_data, subject=str(match_data.get("match_id")))


def emit_order_paid(order_data: dict[str, Any]) -> dict[str, Any]:
    """订单支付事件"""
    return emit_event(EventType.ORDER_PAID, order_data, subject=str(order_data.get("order_id")))


def emit_trust_changed(user_id: int, old_tier: str, new_tier: str, score: int) -> dict[str, Any]:
    """信任分变更事件"""
    return emit_event(
        EventType.USER_TRUST_CHANGED,
        {"user_id": user_id, "old_tier": old_tier, "new_tier": new_tier, "score": score},
        subject=str(user_id),
    )
