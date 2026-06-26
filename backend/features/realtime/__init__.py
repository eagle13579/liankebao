"""链客宝 — 实时事件流与消息队列模块

提供轻量级消息队列抽象层和用户行为事件流管道。
支持 Redis PubSub / SQLite 轮询双模式降级。

模块:
  queue         - 消息队列抽象（Redis PubSub / SQLite 轮询）
  event_stream  - 用户行为事件定义、生产者与消费者

用法:
    from features.realtime.queue import create_queue, MessageQueue
    from features.realtime.event_stream import (
        UserEvent, EventType,
        EventProducer, EventConsumer,
    )

    queue = create_queue()  # 自动检测 Redis 可用性
    producer = EventProducer(queue)
    consumer = EventConsumer(queue)
"""

from features.realtime.queue import (
    MessageQueue,
    RedisPubSubQueue,
    SQLitePollQueue,
    create_queue,
)

from features.realtime.event_stream import (
    UserEvent,
    EventType,
    EventProducer,
    EventConsumer,
    make_page_view_event,
    make_match_click_event,
    make_connect_request_event,
    make_feedback_event,
)

__all__ = [
    "MessageQueue",
    "RedisPubSubQueue",
    "SQLitePollQueue",
    "create_queue",
    "UserEvent",
    "EventType",
    "EventProducer",
    "EventConsumer",
    "make_page_view_event",
    "make_match_click_event",
    "make_connect_request_event",
    "make_feedback_event",
]

__version__ = "1.0.0"
