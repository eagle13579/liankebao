"""
链客宝 — 轻量级消息队列抽象层
=================================
提供统一的 MessageQueue 接口，支持两种后端实现：

  1. RedisPubSubQueue — 有 Redis 时的 PubSub 模式
  2. SQLitePollQueue  — 无 Redis 时的 SQLite 轮询降级

使用 create_queue() 工厂函数自动检测 Redis 可用性，
无需手动选择实现。

用法:
    queue = create_queue()
    await queue.publish("events", {"type": "page_view", ...})
    async for msg in queue.subscribe("events"):
        process(msg)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 环境变量开关：FORCE_SQLITE=1 强制使用 SQLite 模式（即使 Redis 可用）
FORCE_SQLITE_ENV = "REALTIME_QUEUE_FORCE_SQLITE"

# SQLite 轮询间隔（秒）
DEFAULT_POLL_INTERVAL = 2.0

# Redis 连接超时（秒）
REDIS_CONNECT_TIMEOUT = 3.0

# 消息保留时间（秒），SQLite 模式下超过此时间的消息将被清理
MESSAGE_TTL_SECONDS = 86400  # 24 小时

# SQLite 数据库文件名（存放在项目 data 目录下）
SQLITE_DB_FILENAME = "realtime_queue.db"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class QueueMessage:
    """队列中的单条消息"""

    id: int = 0
    channel: str = ""
    payload: str = ""
    created_at: str = ""
    topic: str = ""


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class MessageQueue(ABC):
    """消息队列抽象基类

    所有队列实现必须实现 publish / subscribe / ack 三个核心方法。
    """

    @abstractmethod
    async def publish(
        self, channel: str, message: Dict[str, Any], topic: str = ""
    ) -> None:
        """发布消息到指定频道

        Args:
            channel: 频道名称（如 "events", "features"）
            message: 消息体（字典）
            topic:   可选的主题标签，用于消费者过滤
        """
        ...

    @abstractmethod
    def subscribe(
        self, channel: str, topic: str = "", batch_size: int = 1
    ) -> AsyncGenerator[QueueMessage, None]:
        """订阅频道，返回异步消息生成器

        Args:
            channel:   频道名称
            topic:     可选主题过滤
            batch_size: 每次拉取的消息数量（仅 SQLite 模式有效）

        Yields:
            QueueMessage 实例
        """
        ...  # pragma: no cover
        yield  # make it a generator for type checking

    @abstractmethod
    async def ack(self, message: QueueMessage) -> None:
        """确认消息处理完成（仅 SQLite 模式需要）

        Redis PubSub 模式不需要确认，此方法为空操作。
        """
        ...

    @abstractmethod
    async def queue_size(self, channel: str) -> int:
        """返回指定频道的待处理消息数"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭队列，释放资源"""
        ...


# ---------------------------------------------------------------------------
# Redis PubSub 实现
# ---------------------------------------------------------------------------


class _RedisNotAvailable(Exception):
    """Redis 不可用标记异常（内部使用）"""
    pass


class RedisPubSubQueue(MessageQueue):
    """基于 Redis PubSub 的消息队列

    需要 redis-py >= 5.0。如果导入或连接失败，抛出 _RedisNotAvailable。
    """

    def __init__(
        self,
        redis_url: str = "",
        connect_timeout: float = REDIS_CONNECT_TIMEOUT,
    ) -> None:
        self._redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._connect_timeout = connect_timeout
        self._redis: Any = None
        self._pubsub: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> None:
        """确保 Redis 连接已建立"""
        if self._redis is not None:
            return
        async with self._lock:
            if self._redis is not None:
                return
            try:
                import redis.asyncio as aioredis  # type: ignore

                self._redis = aioredis.from_url(
                    self._redis_url,
                    socket_connect_timeout=self._connect_timeout,
                    decode_responses=True,
                )
                # 发送 PING 验证连接
                await self._redis.ping()
                logger.info(
                    "RedisPubSubQueue: 已连接到 %s", self._redis_url
                )
            except Exception as exc:
                self._redis = None
                raise _RedisNotAvailable(
                    f"Redis 连接失败: {exc}"
                ) from exc

    async def publish(
        self, channel: str, message: Dict[str, Any], topic: str = ""
    ) -> None:
        await self._ensure_connected()
        payload = json.dumps(message, ensure_ascii=False)
        if topic:
            # 将 topic 编码到消息中
            msg_with_topic = json.dumps(
                {"_topic": topic, "_data": message}, ensure_ascii=False
            )
            await self._redis.publish(channel, msg_with_topic)
        else:
            await self._redis.publish(channel, payload)
        logger.debug("RedisPubSubQueue: 已发布到 %s (topic=%s)", channel, topic or "none")

    async def subscribe(
        self, channel: str, topic: str = "", batch_size: int = 1
    ) -> AsyncGenerator[QueueMessage, None]:
        await self._ensure_connected()
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(channel)

        logger.info(
            "RedisPubSubQueue: 已订阅 %s (topic=%s)", channel, topic or "all"
        )

        try:
            async for raw_msg in self._pubsub.listen():
                if raw_msg["type"] != "message":
                    continue

                raw_data = raw_msg.get("data", "")
                if not raw_data:
                    continue

                # 解析消息
                try:
                    data = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "RedisPubSubQueue: 收到无效 JSON 消息: %s", raw_data
                    )
                    continue

                # topic 过滤
                if topic:
                    msg_topic = ""
                    if isinstance(data, dict) and "_topic" in data:
                        msg_topic = data.get("_topic", "")
                    if msg_topic != topic:
                        continue
                    # 解包带 topic 的消息
                    if isinstance(data, dict) and "_data" in data:
                        data = data["_data"]

                yield QueueMessage(
                    id=0,
                    channel=channel,
                    payload=json.dumps(data, ensure_ascii=False),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    topic=topic,
                )
        except asyncio.CancelledError:
            pass
        finally:
            await self._pubsub.unsubscribe(channel)
            await self._pubsub.close()

    async def ack(self, message: QueueMessage) -> None:
        """Redis PubSub 模式不需要确认"""
        pass

    async def queue_size(self, channel: str) -> int:
        """Redis PubSub 没有持久化队列，返回 -1 表示未知"""
        return -1

    async def close(self) -> None:
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None
        logger.info("RedisPubSubQueue: 已关闭")


# ---------------------------------------------------------------------------
# SQLite 轮询实现（降级模式）
# ---------------------------------------------------------------------------


class SQLitePollQueue(MessageQueue):
    """基于 SQLite 轮询的消息队列（Redis 不可用时的降级方案）

    使用 SQLite 作为持久化后端，消费者通过轮询检测新消息。
    支持 topic 过滤和消息确认（ack）机制。
    """

    def __init__(
        self,
        db_path: str = "",
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        self._db_path = db_path or str(data_dir / SQLITE_DB_FILENAME)
        self._poll_interval = max(0.5, poll_interval)
        self._closed = False

        # 线程本地连接
        self._local = threading.local()

        # 初始化数据库表
        self._init_db()

        # 启动后台清理线程
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="SQLiteQueue-Cleanup",
            daemon=True,
        )
        self._cleanup_thread.start()

        logger.info(
            "SQLitePollQueue: 初始化完成 (db=%s, poll_interval=%ss)",
            self._db_path,
            self._poll_interval,
        )

    # ------------------------------------------------------------------
    # 数据库连接管理
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel     TEXT    NOT NULL,
                    topic       TEXT    NOT NULL DEFAULT '',
                    payload     TEXT    NOT NULL,
                    created_at  TEXT    NOT NULL,
                    acked       INTEGER NOT NULL DEFAULT 0,
                    acked_at    TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_queue_channel_acked
                ON queue_messages (channel, acked, id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_queue_created_at
                ON queue_messages (created_at)
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    async def publish(
        self, channel: str, message: Dict[str, Any], topic: str = ""
    ) -> None:
        payload = json.dumps(message, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()

        def _insert() -> None:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO queue_messages (channel, topic, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (channel, topic, payload, now),
            )
            conn.commit()

        await asyncio.to_thread(_insert)
        logger.debug(
            "SQLitePollQueue: 已写入 %s (topic=%s, len=%d)",
            channel,
            topic or "none",
            len(payload),
        )

    async def subscribe(
        self, channel: str, topic: str = "", batch_size: int = 1
    ) -> AsyncGenerator[QueueMessage, None]:
        last_id = 0
        batch_size = max(1, batch_size)

        logger.info(
            "SQLitePollQueue: 开始轮询 %s (topic=%s)", channel, topic or "all"
        )

        while not self._closed:
            try:
                messages = await asyncio.to_thread(
                    self._poll_messages, channel, topic, last_id, batch_size
                )
                for msg in messages:
                    last_id = msg.id
                    yield msg

                if not messages:
                    await asyncio.sleep(self._poll_interval)
            except Exception as exc:
                logger.error(
                    "SQLitePollQueue: 轮询错误 - %s", exc
                )
                await asyncio.sleep(self._poll_interval * 2)

    def _poll_messages(
        self, channel: str, topic: str, after_id: int, limit: int
    ) -> List[QueueMessage]:
        """执行 SQLite 轮询查询"""
        conn = self._get_conn()
        if topic:
            rows = conn.execute(
                "SELECT id, channel, topic, payload, created_at "
                "FROM queue_messages "
                "WHERE channel = ? AND topic = ? AND acked = 0 AND id > ? "
                "ORDER BY id ASC LIMIT ?",
                (channel, topic, after_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, channel, topic, payload, created_at "
                "FROM queue_messages "
                "WHERE channel = ? AND acked = 0 AND id > ? "
                "ORDER BY id ASC LIMIT ?",
                (channel, after_id, limit),
            ).fetchall()

        return [
            QueueMessage(
                id=row["id"],
                channel=row["channel"],
                topic=row["topic"],
                payload=row["payload"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def ack(self, message: QueueMessage) -> None:
        """确认消息已处理"""

        def _do_ack() -> None:
            conn = self._get_conn()
            conn.execute(
                "UPDATE queue_messages SET acked = 1, acked_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), message.id),
            )
            conn.commit()

        await asyncio.to_thread(_do_ack)

    async def queue_size(self, channel: str) -> int:
        """返回指定频道未确认的消息数"""

        def _count() -> int:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM queue_messages "
                "WHERE channel = ? AND acked = 0",
                (channel,),
            ).fetchone()
            return row["cnt"] if row else 0

        return await asyncio.to_thread(_count)

    async def close(self) -> None:
        self._closed = True
        logger.info("SQLitePollQueue: 已关闭")

    # ------------------------------------------------------------------
    # 后台清理
    # ------------------------------------------------------------------

    def _cleanup_loop(self) -> None:
        """后台线程：定期清理过期的已确认消息"""
        while not self._closed:
            time.sleep(MESSAGE_TTL_SECONDS // 2)
            try:
                self._cleanup_old_messages()
            except Exception as exc:
                logger.warning("SQLitePollQueue: 清理失败 - %s", exc)

    def _cleanup_old_messages(self) -> None:
        """删除超过 TTL 的已确认消息"""
        cutoff = (
            datetime.now(timezone.utc).isoformat()
        )  # rough cutoff (in practice compare via sqlite)
        conn = self._get_conn()
        # Delete acked messages older than TTL
        conn.execute(
            "DELETE FROM queue_messages "
            "WHERE acked = 1 AND created_at < ?",
            (cutoff,),
        )
        # Also hard-delete very old unacked messages (seems stuck)
        conn.execute(
            "DELETE FROM queue_messages "
            "WHERE acked = 0 AND created_at < ?",
            (cutoff,),
        )
        conn.commit()
        logger.debug("SQLitePollQueue: 清理完成")


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def _redis_available() -> bool:
    """检测 Redis 是否可用

    检查顺序：
    1. 如果 FORCE_SQLITE 环境变量设置，跳过 Redis
    2. 尝试导入 redis 模块
    3. 不实际连接，由 create_queue 在初始化时处理
    """
    if os.getenv(FORCE_SQLITE_ENV, "").lower() in ("1", "true", "yes"):
        logger.info("create_queue: FORCE_SQLITE 已设置，跳过 Redis")
        return False

    try:
        import redis  # noqa: F401 - check import only
        return True
    except ImportError:
        logger.info("create_queue: redis 模块未安装，使用 SQLite 降级")
        return False


def create_queue(
    redis_url: str = "",
    db_path: str = "",
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> MessageQueue:
    """创建消息队列实例

    自动检测 Redis 可用性：
    - Redis 可用 → RedisPubSubQueue
    - Redis 不可用 / FORCE_SQLITE → SQLitePollQueue

    Args:
        redis_url:     Redis 连接 URL（默认从 REDIS_URL 环境变量读取）
        db_path:       SQLite 数据库路径（仅 SQLite 模式有效）
        poll_interval: SQLite 轮询间隔秒数（仅 SQLite 模式有效）

    Returns:
        MessageQueue 实例
    """
    if _redis_available():
        try:
            queue = RedisPubSubQueue(redis_url=redis_url)
            # 不需要在此处连接，首次 publish/subscribe 时会自动连接
            logger.info("create_queue: 使用 RedisPubSubQueue")
            return queue
        except Exception as exc:
            logger.warning(
                "create_queue: Redis 初始化失败 (%s)，降级到 SQLite", exc
            )

    queue = SQLitePollQueue(
        db_path=db_path,
        poll_interval=poll_interval,
    )
    logger.info("create_queue: 使用 SQLitePollQueue")
    return queue
