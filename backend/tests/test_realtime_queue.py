"""
链客宝 — 消息队列单元测试
=========================
测试覆盖:
1. SQLitePollQueue publish + queue_size (正常路径)
2. SQLitePollQueue subscribe 接收消息 (正常路径)
3. SQLitePollQueue ack 减少待处理数 (正常路径)
4. SQLitePollQueue 按 topic 过滤订阅 (正常路径)
5. SQLitePollQueue 空队列订阅不崩溃 (边界)
6. create_queue 工厂函数强制 SQLite (边界/异常)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any, AsyncGenerator, Dict, Generator, List

import pytest

from features.realtime.queue import (
    FORCE_SQLITE_ENV,
    SQLitePollQueue,
    QueueMessage,
    create_queue,
    _redis_available,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def db_path() -> Generator[str, None, None]:
    """提供临时 SQLite 数据库路径"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # 清理
    import gc
    gc.collect()
    for _ in range(3):
        try:
            os.unlink(path)
            break
        except PermissionError:
            time.sleep(0.1)
            gc.collect()
        except FileNotFoundError:
            break


@pytest.fixture
def queue(db_path: str) -> SQLitePollQueue:
    """SQLitePollQueue 实例（极短轮询间隔，加速测试）"""
    q = SQLitePollQueue(db_path=db_path, poll_interval=0.5)
    yield q
    # 清理
    try:
        asyncio.run(q.close())
    except Exception:
        pass


@pytest.fixture
def sample_message() -> Dict[str, Any]:
    return {"user_id": "u1", "action": "test", "value": 42}


# ===================================================================
# 辅助函数
# ===================================================================


async def _collect_n(
    gen: AsyncGenerator[QueueMessage, None],
    n: int,
    timeout: float = 5.0,
) -> List[QueueMessage]:
    """从异步生成器中收集最多 n 条消息（带超时）"""
    results: List[QueueMessage] = []

    async def _collect() -> None:
        async for msg in gen:
            results.append(msg)
            if len(results) >= n:
                break

    try:
        await asyncio.wait_for(_collect(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return results


# ===================================================================
# 测试 1: 发布 + 队列大小
# ===================================================================


class TestPublishAndQueueSize:
    """测试 publish 和 queue_size 正常路径"""

    @pytest.mark.asyncio
    async def test_publish_increases_queue_size(
        self, queue: SQLitePollQueue, sample_message: Dict[str, Any]
    ) -> None:
        """发布一条消息后 queue_size 应返回 1"""
        assert await queue.queue_size("events") == 0
        await queue.publish("events", sample_message)
        assert await queue.queue_size("events") == 1

    @pytest.mark.asyncio
    async def test_publish_multiple_messages(
        self, queue: SQLitePollQueue, sample_message: Dict[str, Any]
    ) -> None:
        """发布多条消息后 queue_size 正确累计"""
        for i in range(5):
            msg = {**sample_message, "seq": i}
            await queue.publish("events", msg)
        assert await queue.queue_size("events") == 5

    @pytest.mark.asyncio
    async def test_queue_size_separate_channels(
        self, queue: SQLitePollQueue, sample_message: Dict[str, Any]
    ) -> None:
        """不同频道的消息分别计数"""
        await queue.publish("ch_a", sample_message)
        await queue.publish("ch_a", sample_message)
        await queue.publish("ch_b", sample_message)
        assert await queue.queue_size("ch_a") == 2
        assert await queue.queue_size("ch_b") == 1
        assert await queue.queue_size("ch_c") == 0


# ===================================================================
# 测试 2: 订阅接收消息
# ===================================================================


class TestSubscribe:
    """测试 subscribe 正常路径"""

    @pytest.mark.asyncio
    async def test_subscribe_receives_published_message(
        self, queue: SQLitePollQueue, sample_message: Dict[str, Any]
    ) -> None:
        """发布后订阅应收到消息"""
        await queue.publish("events", sample_message)

        gen = queue.subscribe("events", batch_size=10)
        messages = await _collect_n(gen, 1)
        gen.aclose()

        assert len(messages) >= 1
        msg = messages[0]
        assert msg.channel == "events"
        assert "user_id" in msg.payload
        assert msg.id > 0

    @pytest.mark.asyncio
    async def test_subscribe_multiple_messages(
        self, queue: SQLitePollQueue
    ) -> None:
        """多条消息按顺序投递"""
        for i in range(3):
            await queue.publish("events", {"seq": i, "data": f"msg-{i}"})

        gen = queue.subscribe("events", batch_size=10)
        messages = await _collect_n(gen, 3, timeout=3.0)
        gen.aclose()

        assert len(messages) >= 3
        for i, msg in enumerate(messages[:3]):
            import json
            payload = json.loads(msg.payload)
            assert payload["seq"] == i


# ===================================================================
# 测试 3: ack 确认
# ===================================================================


class TestAck:
    """测试 ack 确认机制"""

    @pytest.mark.asyncio
    async def test_ack_reduces_queue_size(
        self, queue: SQLitePollQueue, sample_message: Dict[str, Any]
    ) -> None:
        """确认消息后 queue_size 应减少"""
        await queue.publish("events", sample_message)
        assert await queue.queue_size("events") == 1

        # 订阅获取消息
        gen = queue.subscribe("events", batch_size=1)
        msg = await _collect_n(gen, 1, timeout=3.0)
        gen.aclose()

        if msg:
            await queue.ack(msg[0])
            # 等待 SQLite 写入完成
            await asyncio.sleep(0.1)
            assert await queue.queue_size("events") == 0

    @pytest.mark.asyncio
    async def test_ack_after_subscribe_prevents_redelivery(
        self, queue: SQLitePollQueue, sample_message: Dict[str, Any]
    ) -> None:
        """已确认的消息不应再次投递"""
        await queue.publish("events", sample_message)

        # 第一次订阅并确认
        gen1 = queue.subscribe("events", batch_size=1)
        msgs1 = await _collect_n(gen1, 1, timeout=3.0)
        gen1.aclose()
        if msgs1:
            await queue.ack(msgs1[0])

        # 第二次订阅不应再收到同一消息
        gen2 = queue.subscribe("events", batch_size=1)
        msgs2 = await _collect_n(gen2, 1, timeout=2.0)
        gen2.aclose()

        assert len(msgs2) == 0


# ===================================================================
# 测试 4: Topic 过滤
# ===================================================================


class TestTopicFilter:
    """测试 topic 消息过滤"""

    @pytest.mark.asyncio
    async def test_subscribe_with_topic_filter(
        self, queue: SQLitePollQueue
    ) -> None:
        """订阅指定 topic 只收到匹配消息"""
        await queue.publish("events", {"msg": "alpha"}, topic="topic_a")
        await queue.publish("events", {"msg": "beta"}, topic="topic_b")
        await queue.publish("events", {"msg": "alpha2"}, topic="topic_a")

        gen = queue.subscribe("events", topic="topic_a", batch_size=10)
        messages = await _collect_n(gen, 2, timeout=3.0)
        gen.aclose()

        assert len(messages) >= 2
        import json
        for msg in messages:
            payload = json.loads(msg.payload)
            assert payload["msg"].startswith("alpha")

    @pytest.mark.asyncio
    async def test_subscribe_topic_no_match(
        self, queue: SQLitePollQueue
    ) -> None:
        """没有匹配 topic 时返回空"""
        await queue.publish("events", {"msg": "hello"}, topic="topic_a")

        gen = queue.subscribe("events", topic="nonexistent", batch_size=10)
        messages = await _collect_n(gen, 1, timeout=2.0)
        gen.aclose()

        assert len(messages) == 0


# ===================================================================
# 测试 5: 边界情况
# ===================================================================


class TestEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_empty_queue_subscribe_does_not_crash(
        self, queue: SQLitePollQueue
    ) -> None:
        """空队列订阅不应崩溃，超时应正常退出"""
        gen = queue.subscribe("events", batch_size=1)

        async def _iterate_one() -> None:
            async for msg in gen:
                pytest.fail("不应收到消息")

        try:
            await asyncio.wait_for(_iterate_one(), timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            await gen.aclose()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_poll_interval_clamped(
        self, queue: SQLitePollQueue
    ) -> None:
        """poll_interval 下限应为 0.5 秒"""
        assert queue._poll_interval >= 0.5

    @pytest.mark.asyncio
    async def test_batch_size_min_clamped(
        self, queue: SQLitePollQueue, sample_message: Dict[str, Any]
    ) -> None:
        """batch_size 最小值为 1"""
        await queue.publish("events", sample_message)
        gen = queue.subscribe("events", batch_size=0)  # 应被夹紧到 1
        msgs = await _collect_n(gen, 1, timeout=3.0)
        gen.aclose()
        assert len(msgs) >= 1


# ===================================================================
# 测试 6: 工厂函数
# ===================================================================


class TestCreateQueue:
    """测试 create_queue 工厂函数"""

    def test_create_queue_force_sqlite(self, db_path: str) -> None:
        """FORCE_SQLITE 环境变量应强制使用 SQLite"""
        os.environ[FORCE_SQLITE_ENV] = "1"
        try:
            queue = create_queue(db_path=db_path)
            assert isinstance(queue, SQLitePollQueue)
        finally:
            os.environ.pop(FORCE_SQLITE_ENV, None)

    def test_redis_available_force_sqlite(self) -> None:
        """FORCE_SQLITE 时 _redis_available 返回 False"""
        os.environ[FORCE_SQLITE_ENV] = "true"
        try:
            assert _redis_available() is False
        finally:
            os.environ.pop(FORCE_SQLITE_ENV, None)

    def test_create_queue_custom_params(self, db_path: str) -> None:
        """自定义参数传递给 SQLitePollQueue"""
        os.environ[FORCE_SQLITE_ENV] = "1"
        try:
            queue = create_queue(db_path=db_path, poll_interval=1.5)
            assert isinstance(queue, SQLitePollQueue)
            assert queue._poll_interval == 1.5
            assert db_path in queue._db_path
        finally:
            os.environ.pop(FORCE_SQLITE_ENV, None)
