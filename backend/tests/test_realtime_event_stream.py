"""
链客宝 — 事件流管道单元测试
============================
测试覆盖:
1. EventProducer.publish — 正常发布事件 (正常路径)
2. EventProducer.publish_batch — 批量发布 (正常路径)
3. EventProducer 便捷方法 (正常路径)
4. EventConsumer.register_handler — 处理器注册 (正常路径+异常)
5. EventConsumer.process_single — 单条消费 (正常路径)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from features.realtime.event_stream import (
    EventConsumer,
    EventProducer,
    EventType,
    UserEvent,
    make_page_view_event,
    make_match_click_event,
    make_connect_request_event,
    make_feedback_event,
    _update_feature_from_event,
)
from features.realtime.queue import MessageQueue, QueueMessage


# ===================================================================
# Mock 消息队列
# ===================================================================


class MockQueue(MessageQueue):
    """完全可控的 Mock 消息队列"""

    def __init__(self) -> None:
        self.published: List[tuple] = []
        self._subscribe_gen: Optional[AsyncGenerator[QueueMessage, None]] = None
        self._acked: List[QueueMessage] = []

    async def publish(
        self, channel: str, message: Dict[str, Any], topic: str = ""
    ) -> None:
        self.published.append((channel, message, topic))

    def subscribe(
        self, channel: str, topic: str = "", batch_size: int = 1
    ) -> AsyncGenerator[QueueMessage, None]:
        return self._build_subscribe_gen()

    async def _build_subscribe_gen(self):
        """空的订阅生成器（永不 yield）"""
        if False:
            yield  # pragma: no cover

    async def ack(self, message: QueueMessage) -> None:
        self._acked.append(message)

    async def queue_size(self, channel: str) -> int:
        return len([p for p in self.published if p[0] == channel])

    async def close(self) -> None:
        pass


class MockQueueWithMessages(MockQueue):
    """带预置消息的 Mock 队列"""

    def __init__(self, messages: List[QueueMessage]) -> None:
        super().__init__()
        self._messages = messages
        self._index = 0

    async def _build_subscribe_gen(self):
        for msg in self._messages:
            yield msg


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def mock_queue() -> MockQueue:
    return MockQueue()


@pytest.fixture
def producer(mock_queue: MockQueue) -> EventProducer:
    return EventProducer(mock_queue)


@pytest.fixture
def sample_event() -> UserEvent:
    return make_page_view_event(
        user_id="u1",
        target_id="c1",
        session_id="sess-001",
        page="matches",
        extra={"source": "search"},
    )


# ===================================================================
# 测试 1: EventProducer.publish
# ===================================================================


class TestEventProducerPublish:
    """事件发布测试"""

    @pytest.mark.asyncio
    async def test_publish_sends_to_queue(
        self, producer: EventProducer, sample_event: UserEvent
    ) -> None:
        """publish 应调用 queue.publish"""
        await producer.publish(sample_event)
        assert len(producer.queue.published) == 1

        channel, message, topic = producer.queue.published[0]
        assert channel == "user_events"
        assert message["event_type"] == "page_view"
        assert message["user_id"] == "u1"
        assert topic == "page_view"

    @pytest.mark.asyncio
    async def test_publish_with_custom_topic(
        self, producer: EventProducer, sample_event: UserEvent
    ) -> None:
        """自定义 topic 应覆盖默认 topic"""
        await producer.publish(sample_event, topic="custom_topic")
        _, _, topic = producer.queue.published[0]
        assert topic == "custom_topic"

    @pytest.mark.asyncio
    async def test_publish_event_has_all_required_fields(
        self, producer: EventProducer, sample_event: UserEvent
    ) -> None:
        """发布的事件应包含 event_id 和 timestamp"""
        await producer.publish(sample_event)
        _, message, _ = producer.queue.published[0]
        assert "event_id" in message
        assert "timestamp" in message
        assert "source" in message


# ===================================================================
# 测试 2: EventProducer.publish_batch
# ===================================================================


class TestEventProducerBatch:
    """批量发布测试"""

    @pytest.mark.asyncio
    async def test_publish_batch_all_succeed(
        self, producer: EventProducer
    ) -> None:
        """批量发布所有事件应成功"""
        events = [
            make_page_view_event(user_id=f"u{i}", page="home")
            for i in range(3)
        ]
        count = await producer.publish_batch(events)
        assert count == 3
        assert len(producer.queue.published) == 3

    @pytest.mark.asyncio
    async def test_publish_batch_empty_list(
        self, producer: EventProducer
    ) -> None:
        """空列表应返回 0"""
        count = await producer.publish_batch([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_publish_batch_continues_on_error(
        self, producer: EventProducer
    ) -> None:
        """部分失败时应继续发布其余事件并返回成功数"""
        # 让第一个发布成功，第二个抛出异常
        original_publish = producer.publish

        call_count = 0

        async def failing_publish(event, topic=""):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("publish failed")
            await original_publish(event, topic=topic)

        with patch.object(producer, "publish", failing_publish):
            events = [
                make_page_view_event(user_id="u1", page="a"),
                make_page_view_event(user_id="u2", page="b"),
                make_page_view_event(user_id="u3", page="c"),
            ]
            count = await producer.publish_batch(events)
            assert count == 2  # 成功 2 个（第 2 个失败后被吞掉，第 3 个成功）


# ===================================================================
# 测试 3: 便捷方法
# ===================================================================


class TestConvenienceMethods:
    """便捷发布方法测试"""

    @pytest.mark.asyncio
    async def test_publish_page_view(
        self, producer: EventProducer
    ) -> None:
        """publish_page_view 应创建并发布 page_view 事件"""
        event = await producer.publish_page_view(
            user_id="u1", page="profile", extra={"section": "intro"}
        )
        assert event.event_type == EventType.PAGE_VIEW
        assert event.user_id == "u1"
        assert event.metadata["page"] == "profile"

        _, message, _ = producer.queue.published[0]
        assert message["event_type"] == "page_view"

    @pytest.mark.asyncio
    async def test_publish_match_click(
        self, producer: EventProducer
    ) -> None:
        """publish_match_click 应创建并发布 match_click 事件"""
        event = await producer.publish_match_click(
            user_id="u1", target_id="c1", position=2, match_score=0.95
        )
        assert event.event_type == EventType.MATCH_CLICK
        assert event.metadata["position"] == 2
        assert event.metadata["match_score"] == 0.95

    @pytest.mark.asyncio
    async def test_publish_connect_request(
        self, producer: EventProducer
    ) -> None:
        """publish_connect_request 应创建并发布 connect_request 事件"""
        event = await producer.publish_connect_request(
            user_id="u1", target_id="c1", method="wechat", message="你好"
        )
        assert event.event_type == EventType.CONNECT_REQUEST
        assert event.metadata["method"] == "wechat"
        assert event.metadata["message"] == "你好"

    @pytest.mark.asyncio
    async def test_publish_feedback(
        self, producer: EventProducer
    ) -> None:
        """publish_feedback 应创建并发布 feedback 事件"""
        event = await producer.publish_feedback(
            user_id="u1", target_id="c1", rating="dislike", comment="no thanks"
        )
        assert event.event_type == EventType.FEEDBACK
        assert event.metadata["rating"] == "dislike"
        assert event.metadata["comment"] == "no thanks"


# ===================================================================
# 测试 4: EventConsumer 处理器注册
# ===================================================================


class TestConsumerHandlers:
    """处理器注册测试"""

    @pytest.fixture
    def consumer(self, mock_queue: MockQueue) -> EventConsumer:
        return EventConsumer(mock_queue)

    def test_register_handler(self, consumer: EventConsumer) -> None:
        """register_handler 应存储可调用对象"""
        handler = MagicMock()
        consumer.register_handler(EventType.PAGE_VIEW, handler)
        assert consumer.get_handler(EventType.PAGE_VIEW) is handler

    def test_register_handler_overwrites_existing(
        self, consumer: EventConsumer
    ) -> None:
        """注册相同类型应覆盖已有处理器"""
        handler1 = MagicMock()
        handler2 = MagicMock()
        consumer.register_handler(EventType.PAGE_VIEW, handler1)
        consumer.register_handler(EventType.PAGE_VIEW, handler2)
        assert consumer.get_handler(EventType.PAGE_VIEW) is handler2

    def test_register_non_callable_raises(
        self, consumer: EventConsumer
    ) -> None:
        """非可调用对象应抛出 ValueError"""
        with pytest.raises(ValueError, match="必须是可调用对象"):
            consumer.register_handler(EventType.PAGE_VIEW, "not_callable")  # type: ignore[arg-type]

    def test_default_handlers_registered(
        self, consumer: EventConsumer
    ) -> None:
        """初始化时应为所有事件类型注册默认处理器"""
        for event_type in EventType:
            handler = consumer.get_handler(event_type)
            assert handler is not None
            assert callable(handler)

    def test_custom_handlers_on_init(
        self, mock_queue: MockQueue
    ) -> None:
        """初始化时传入自定义处理器"""
        custom = MagicMock()
        consumer = EventConsumer(
            mock_queue,
            handlers={EventType.PAGE_VIEW: custom},
        )
        assert consumer.get_handler(EventType.PAGE_VIEW) is custom
        # 其他类型仍有默认处理器
        assert consumer.get_handler(EventType.MATCH_CLICK) is not None


# ===================================================================
# 测试 5: EventConsumer.process_single
# ===================================================================


class TestConsumerProcessSingle:
    """单条消费测试"""

    @pytest.mark.asyncio
    async def test_process_single_consumes_event(
        self, sample_event: UserEvent
    ) -> None:
        """process_single 应消费并返回事件"""
        raw_msg = QueueMessage(
            id=1,
            channel="user_events",
            payload=json.dumps(sample_event.to_dict(), ensure_ascii=False),
            created_at="2025-01-01T00:00:00",
        )
        queue = MockQueueWithMessages([raw_msg])
        consumer = EventConsumer(queue)

        result = await consumer.process_single(timeout=5.0)
        assert result is not None
        assert result.event_id == sample_event.event_id
        assert result.event_type == EventType.PAGE_VIEW
        assert result.user_id == "u1"

    @pytest.mark.asyncio
    async def test_process_single_timeout_returns_none(
        self, mock_queue: MockQueue
    ) -> None:
        """超时应返回 None"""
        consumer = EventConsumer(mock_queue)
        result = await consumer.process_single(timeout=0.1)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_single_calls_handler(self) -> None:
        """process_single 应调用已注册的处理器"""
        event = make_page_view_event(user_id="u1", page="home")
        raw_msg = QueueMessage(
            id=1,
            channel="user_events",
            payload=json.dumps(event.to_dict(), ensure_ascii=False),
            created_at="2025-01-01T00:00:00",
        )
        queue = MockQueueWithMessages([raw_msg])
        handler = MagicMock()
        consumer = EventConsumer(queue, handlers={EventType.PAGE_VIEW: handler})

        result = await consumer.process_single(timeout=5.0)
        assert result is not None
        handler.assert_called_once()
        # 验证处理器收到的确实是 UserEvent 实例
        called_event = handler.call_args[0][0]
        assert isinstance(called_event, UserEvent)
        assert called_event.user_id == "u1"

    @pytest.mark.asyncio
    async def test_process_single_auto_acks(self) -> None:
        """process_single 应自动确认消息"""
        event = make_page_view_event(user_id="u1", page="home")
        raw_msg = QueueMessage(
            id=1,
            channel="user_events",
            payload=json.dumps(event.to_dict(), ensure_ascii=False),
            created_at="2025-01-01T00:00:00",
        )
        queue = MockQueueWithMessages([raw_msg])
        consumer = EventConsumer(queue)

        await consumer.process_single(timeout=5.0)
        assert len(queue._acked) == 1
        assert queue._acked[0].id == 1

    @pytest.mark.asyncio
    async def test_process_single_invalid_json(self) -> None:
        """无效 JSON 应被捕获并返回 None"""
        raw_msg = QueueMessage(
            id=2,
            channel="user_events",
            payload="not valid json {{{",
            created_at="2025-01-01T00:00:00",
        )
        queue = MockQueueWithMessages([raw_msg])
        consumer = EventConsumer(queue)

        result = await consumer.process_single(timeout=5.0)
        assert result is None
        # 无效消息也应被 ack
        assert len(queue._acked) == 1
