"""
链客宝 — 用户行为事件流管道
=============================
定义用户行为事件类型、事件生产者和消费者。

事件类型:
  - page_view:        页面浏览
  - match_click:      匹配结果点击
  - connect_request:  连接请求（交换名片、发起沟通）
  - feedback:         用户反馈（赞/踩/举报）

管道流程:
  API 层 -> EventProducer.publish() -> MessageQueue -> EventConsumer -> 特征更新

用法:
    from features.realtime.event_stream import EventProducer, EventConsumer
    from features.realtime.queue import create_queue

    queue = create_queue()
    producer = EventProducer(queue)
    consumer = EventConsumer(queue)

    # 发布事件
    await producer.publish_page_view(user_id="u1", target_id="c1", page="matches")

    # 消费事件
    await consumer.process_events()
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

from features.realtime.queue import MessageQueue

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """用户行为事件类型"""
    PAGE_VIEW = "page_view"
    MATCH_CLICK = "match_click"
    CONNECT_REQUEST = "connect_request"
    FEEDBACK = "feedback"

    @classmethod
    def list(cls) -> List[str]:
        return [e.value for e in cls]


def _new_event_id() -> str:
    import uuid
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserEvent(BaseModel):
    """用户行为事件通用模型"""

    event_id: str = Field(default_factory=_new_event_id, description="事件唯一 ID（自动生成）")
    event_type: EventType = Field(..., description="事件类型")
    user_id: str = Field(..., description="发起事件的用户 ID")
    target_id: str = Field(default="", description="目标对象 ID（如名片 ID、匹配 ID）")
    session_id: str = Field(default="", description="会话 ID（用于关联同一会话内的事件）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="事件附加元数据")
    timestamp: str = Field(default_factory=_now_iso, description="事件发生时间（ISO 格式，自动生成）")
    source: str = Field(default="api", description="事件来源（api / webhook / batch）")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UserEvent:
        return cls(**data)


def make_page_view_event(
    user_id: str,
    target_id: str = "",
    session_id: str = "",
    page: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> UserEvent:
    """创建 page_view 事件"""
    metadata = {"page": page, **(extra or {})}
    return UserEvent(
        event_type=EventType.PAGE_VIEW,
        user_id=user_id,
        target_id=target_id,
        session_id=session_id,
        metadata=metadata,
    )


def make_match_click_event(
    user_id: str,
    target_id: str,
    session_id: str = "",
    position: int = 0,
    match_score: float = 0.0,
    extra: Optional[Dict[str, Any]] = None,
) -> UserEvent:
    """创建 match_click 事件"""
    metadata = {"position": position, "match_score": match_score, **(extra or {})}
    return UserEvent(
        event_type=EventType.MATCH_CLICK,
        user_id=user_id,
        target_id=target_id,
        session_id=session_id,
        metadata=metadata,
    )


def make_connect_request_event(
    user_id: str,
    target_id: str,
    session_id: str = "",
    method: str = "card_exchange",
    message: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> UserEvent:
    """创建 connect_request 事件"""
    metadata = {"method": method, "message": message, **(extra or {})}
    return UserEvent(
        event_type=EventType.CONNECT_REQUEST,
        user_id=user_id,
        target_id=target_id,
        session_id=session_id,
        metadata=metadata,
    )


def make_feedback_event(
    user_id: str,
    target_id: str,
    session_id: str = "",
    rating: str = "like",
    comment: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> UserEvent:
    """创建 feedback 事件"""
    metadata = {"rating": rating, "comment": comment, **(extra or {})}
    return UserEvent(
        event_type=EventType.FEEDBACK,
        user_id=user_id,
        target_id=target_id,
        session_id=session_id,
        metadata=metadata,
    )


EventHandler = Callable[[UserEvent], Any]


def _update_feature_from_event(event: UserEvent) -> None:
    """默认特征更新回调（占位，可被替换）"""
    logger.info(
        "[FeatureUpdate] type=%s user=%s target=%s metadata=%s",
        event.event_type.value,
        event.user_id,
        event.target_id,
        json.dumps(event.metadata, ensure_ascii=False),
    )


class EventProducer:
    """用户行为事件生产者 — 从 API 层接收事件，写入消息队列"""

    def __init__(self, queue: MessageQueue) -> None:
        self._queue = queue
        self._channel = "user_events"
        logger.info("EventProducer: 初始化完成 (channel=%s)", self._channel)

    async def publish(self, event: UserEvent, topic: str = "") -> None:
        """发布单个事件到消息队列"""
        await self._queue.publish(
            self._channel,
            event.to_dict(),
            topic=topic or event.event_type.value,
        )
        logger.debug(
            "EventProducer: 已发布 event_id=%s type=%s user=%s",
            event.event_id, event.event_type.value, event.user_id,
        )

    async def publish_batch(self, events: List[UserEvent], topic: str = "") -> int:
        """批量发布事件"""
        count = 0
        for event in events:
            try:
                await self.publish(event, topic=topic)
                count += 1
            except Exception as exc:
                logger.error("EventProducer: 发布失败 event_id=%s - %s", event.event_id, exc)
        logger.info("EventProducer: 批量发布完成 (%d/%d)", count, len(events))
        return count

    async def publish_page_view(
        self, user_id: str, target_id: str = "", session_id: str = "",
        page: str = "", extra: Optional[Dict[str, Any]] = None,
    ) -> UserEvent:
        """便捷方法：发布 page_view 事件"""
        event = make_page_view_event(user_id=user_id, target_id=target_id,
                                      session_id=session_id, page=page, extra=extra)
        await self.publish(event)
        return event

    async def publish_match_click(
        self, user_id: str, target_id: str, session_id: str = "",
        position: int = 0, match_score: float = 0.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> UserEvent:
        """便捷方法：发布 match_click 事件"""
        event = make_match_click_event(user_id=user_id, target_id=target_id,
                                        session_id=session_id, position=position,
                                        match_score=match_score, extra=extra)
        await self.publish(event)
        return event

    async def publish_connect_request(
        self, user_id: str, target_id: str, session_id: str = "",
        method: str = "card_exchange", message: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> UserEvent:
        """便捷方法：发布 connect_request 事件"""
        event = make_connect_request_event(user_id=user_id, target_id=target_id,
                                            session_id=session_id, method=method,
                                            message=message, extra=extra)
        await self.publish(event)
        return event

    async def publish_feedback(
        self, user_id: str, target_id: str, session_id: str = "",
        rating: str = "like", comment: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> UserEvent:
        """便捷方法：发布 feedback 事件"""
        event = make_feedback_event(user_id=user_id, target_id=target_id,
                                     session_id=session_id, rating=rating,
                                     comment=comment, extra=extra)
        await self.publish(event)
        return event

    @property
    def queue(self) -> MessageQueue:
        return self._queue


class EventConsumer:
    """用户行为事件消费者 — 从消息队列读取事件，执行已注册的事件处理器"""

    def __init__(
        self,
        queue: MessageQueue,
        handlers: Optional[Dict[EventType, EventHandler]] = None,
    ) -> None:
        self._queue = queue
        self._channel = "user_events"
        self._handlers: Dict[EventType, EventHandler] = {}
        self._register_default_handlers()
        if handlers:
            for event_type, handler in handlers.items():
                self.register_handler(event_type, handler)
        logger.info("EventConsumer: 初始化完成 (channel=%s, handlers=%d)",
                     self._channel, len(self._handlers))

    def _register_default_handlers(self) -> None:
        for event_type in EventType:
            self._handlers[event_type] = _update_feature_from_event

    def register_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """注册指定事件类型的处理器"""
        if not callable(handler):
            raise ValueError(f"handler 必须是可调用对象，收到 {type(handler)}")
        self._handlers[event_type] = handler
        logger.info("EventConsumer: 已注册处理器 type=%s handler=%s",
                     event_type.value,
                     getattr(handler, "__name__", type(handler).__name__))

    def get_handler(self, event_type: EventType) -> Optional[EventHandler]:
        return self._handlers.get(event_type)

    async def process_events(
        self, topic: str = "", batch_size: int = 10, auto_ack: bool = True,
    ) -> int:
        """消费并处理事件（阻塞，持续运行）"""
        processed = 0
        logger.info("EventConsumer: 开始消费 (topic=%s, batch_size=%d)",
                     topic or "all", batch_size)
        async for raw_msg in self._queue.subscribe(
            self._channel, topic=topic, batch_size=batch_size
        ):
            try:
                data = json.loads(raw_msg.payload)
                event = UserEvent.from_dict(data)
                handler = self._handlers.get(event.event_type)
                if handler is None:
                    logger.warning("EventConsumer: 无处理器 type=%s (event_id=%s)",
                                    event.event_type.value, event.event_id)
                else:
                    try:
                        handler(event)
                    except Exception as exc:
                        logger.error("EventConsumer: 处理器执行失败 type=%s event_id=%s - %s",
                                      event.event_type.value, event.event_id, exc)
                if auto_ack:
                    await self._queue.ack(raw_msg)
                processed += 1
                if processed % 100 == 0:
                    logger.info("EventConsumer: 已处理 %d 个事件", processed)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("EventConsumer: 消息解析失败 - %s (payload=%s...)",
                                exc, raw_msg.payload[:200])
                if auto_ack:
                    await self._queue.ack(raw_msg)
        return processed

    async def process_single(self, topic: str = "", timeout: float = 10.0) -> Optional[UserEvent]:
        """消费单条事件（非阻塞，超时返回 None）"""
        import asyncio

        async def _consume_one() -> Optional[UserEvent]:
            async for raw_msg in self._queue.subscribe(self._channel, topic=topic, batch_size=1):
                try:
                    data = json.loads(raw_msg.payload)
                    event = UserEvent.from_dict(data)
                    handler = self._handlers.get(event.event_type)
                    if handler:
                        try:
                            handler(event)
                        except Exception as exc:
                            logger.error("EventConsumer: 单次处理器执行失败 - %s", exc)
                    await self._queue.ack(raw_msg)
                    return event
                except Exception as exc:
                    logger.warning("EventConsumer: 单次消费解析失败 - %s", exc)
                    await self._queue.ack(raw_msg)
                    return None
            return None

        try:
            return await asyncio.wait_for(_consume_one(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    @property
    def queue(self) -> MessageQueue:
        return self._queue

    @property
    def channel(self) -> str:
        return self._channel
