"""
Redis 客户端连接池 — 为 AI 数字名片提供高性能缓存层。

支持:
  - 连接池管理（自动重连、健康检查）
  - 序列化/反序列化（JSON + pickle 回退）
  - 原子操作（setnx, incr, expire）
  - 连接超时自动 recovery
"""

import json
import logging
import pickle
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 全局 Redis 客户端实例 ────────────────────────────────────────────────
_redis_client: Optional["RedisClient"] = None


def get_redis() -> Optional["RedisClient"]:
    """获取全局 Redis 客户端实例（可能为 None — 缓存不可用时降级）"""
    return _redis_client


def init_redis(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: str = "",
    max_connections: int = 20,
    socket_timeout: float = 2.0,
    socket_connect_timeout: float = 2.0,
    retry_on_timeout: bool = True,
    decode_responses: bool = False,
) -> Optional["RedisClient"]:
    """初始化全局 Redis 客户端连接池

    Args:
        host: Redis 主机地址
        port: Redis 端口
        db: 数据库编号
        password: 密码（可选）
        max_connections: 连接池大小
        socket_timeout: 读写超时（秒）
        socket_connect_timeout: 连接超时（秒）
        retry_on_timeout: 超时是否重试

    Returns:
        RedisClient 实例，连接失败返回 None
    """
    global _redis_client
    try:
        _redis_client = RedisClient(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            retry_on_timeout=retry_on_timeout,
            decode_responses=decode_responses,
        )
        # 健康检查
        _redis_client.ping()
        logger.info(f"Redis 连接池初始化成功: {host}:{port}/{db}, pool_size={max_connections}")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis 初始化失败，缓存不可用（降级运行）: {e}")
        _redis_client = None
        return None


class RedisClient:
    """Redis 客户端包装器 — 带连接池、序列化、降级处理"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str = "",
        max_connections: int = 20,
        socket_timeout: float = 2.0,
        socket_connect_timeout: float = 2.0,
        retry_on_timeout: bool = True,
        decode_responses: bool = False,
    ):
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._max_connections = max_connections
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._retry_on_timeout = retry_on_timeout
        self._decode_responses = decode_responses
        self._pool = None
        self._redis = None
        self._connect()

    def _connect(self) -> None:
        """建立连接池"""
        try:
            import redis as _redis_module
            from redis.connection import ConnectionPool

            # 构建连接 URL
            if self._password:
                url = f"redis://:{self._password}@{self._host}:{self._port}/{self._db}"
            else:
                url = f"redis://{self._host}:{self._port}/{self._db}"

            self._pool = ConnectionPool.from_url(
                url,
                max_connections=self._max_connections,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                retry_on_timeout=self._retry_on_timeout,
                decode_responses=self._decode_responses,
                health_check_interval=30,
            )
            self._redis = _redis_module.Redis(connection_pool=self._pool)
        except ImportError:
            logger.error("redis 库未安装。请执行: pip install redis")
            raise
        except Exception as e:
            logger.error(f"Redis 连接失败: {e}")
            raise

    @property
    def client(self):
        """获取原始 Redis 客户端"""
        if self._redis is None:
            self._connect()
        return self._redis

    # ── 连接管理 ──────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """健康检查"""
        try:
            return self.client.ping()
        except Exception:
            return False

    def close(self) -> None:
        """关闭连接池"""
        if self._pool is not None:
            self._pool.disconnect()
            self._pool = None
            self._redis = None

    # ── 序列化 ────────────────────────────────────────────────────────────

    @staticmethod
    def _serialize(value: Any) -> bytes:
        """序列化值（优先 JSON，回退 pickle）"""
        try:
            return json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        except (TypeError, ValueError):
            return pickle.dumps(value)

    @staticmethod
    def _deserialize(data: bytes) -> Any:
        """反序列化值"""
        if data is None:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                return pickle.loads(data)
            except Exception:
                return data

    # ── 核心操作 ──────────────────────────────────────────────────────────

    def get(self, key: str) -> Any:
        """获取缓存值"""
        try:
            data = self.client.get(key)
            if data is None:
                return None
            return self._deserialize(data)
        except Exception as e:
            logger.warning(f"Redis get 失败 (key={key}): {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 表示永不过期

        Returns:
            是否成功
        """
        try:
            data = self._serialize(value)
            if ttl is not None:
                return bool(self.client.setex(key, ttl, data))
            return bool(self.client.set(key, data))
        except Exception as e:
            logger.warning(f"Redis set 失败 (key={key}): {e}")
            return False

    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            logger.warning(f"Redis delete 失败 (key={key}): {e}")
            return False

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists 失败 (key={key}): {e}")
            return False

    def expire(self, key: str, ttl: int) -> bool:
        """设置过期时间"""
        try:
            return bool(self.client.expire(key, ttl))
        except Exception as e:
            logger.warning(f"Redis expire 失败 (key={key}): {e}")
            return False

    def ttl(self, key: str) -> int:
        """获取剩余过期时间（秒），-1 不过期，-2 不存在"""
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.warning(f"Redis ttl 失败 (key={key}): {e}")
            return -2

    def incr(self, key: str, amount: int = 1) -> int | None:
        """原子自增"""
        try:
            return self.client.incr(key, amount)
        except Exception as e:
            logger.warning(f"Redis incr 失败 (key={key}): {e}")
            return None

    # ── 批量操作 ──────────────────────────────────────────────────────────

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """批量获取"""
        try:
            raw_values = self.client.mget(keys)
            result = {}
            for key, raw in zip(keys, raw_values):
                if raw is not None:
                    result[key] = self._deserialize(raw)
            return result
        except Exception as e:
            logger.warning(f"Redis mget 失败: {e}")
            return {}

    def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """批量设置"""
        try:
            pipe = self.client.pipeline()
            for key, value in mapping.items():
                data = self._serialize(value)
                if ttl is not None:
                    pipe.setex(key, ttl, data)
                else:
                    pipe.set(key, data)
            pipe.execute()
            return True
        except Exception as e:
            logger.warning(f"Redis 批量 set 失败: {e}")
            return False

    # ── 键扫描 ────────────────────────────────────────────────────────────

    def scan_keys(self, pattern: str) -> list[str]:
        """扫描匹配的键（生产环境慎用大范围 scan）"""
        try:
            cursor = 0
            keys = []
            while True:
                cursor, batch = self.client.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break
            return keys
        except Exception as e:
            logger.warning(f"Redis scan 失败 (pattern={pattern}): {e}")
            return []

    # ── 缓存键构建工具 ───────────────────────────────────────────────────

    @staticmethod
    def make_key(prefix: str, *parts, suffix: str = "") -> str:
        """构建带命名空间的缓存键

        用法:
            RedisClient.make_key("match", user_a_id, user_b_id)
            # -> "match:42:57"

            RedisClient.make_key("vector_index", "embeddings")
            # -> "vector_index:embeddings"
        """
        key = ":".join(str(p) for p in parts)
        if prefix:
            key = f"{prefix}:{key}"
        if suffix:
            key = f"{key}:{suffix}"
        return key
