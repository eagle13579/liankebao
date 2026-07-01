"""RedisCache — CacheProtocol adapter backed by Redis (async via redis.asyncio).

Phase 1 distributed cache adapter with:
    - Connection management via URL or host/port/db/password
    - TTL support per key (default from config, overridable per set())
    - Atomic increment via INCR
    - get_or_set with async factory (cache-aside pattern)
    - Namespace prefix support for key isolation
    - Graceful fallback: logs warning and raises on connection failure

Usage:
    cache = RedisCache.from_url("redis://localhost:6379/0", prefix="liankebao:cache")
    await cache.start()
    await cache.set("my_key", {"hello": "world"}, ttl=300)
    value = await cache.get("my_key")
    await cache.stop()
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable
from typing import Any

from app.cache.interfaces import CacheProtocol

logger = logging.getLogger(__name__)


# ======================================================================
# Configuration
# ======================================================================


@dataclasses.dataclass
class RedisConfig:
    """Configuration for connecting to a Redis instance.

    Attributes:
        host: Redis server hostname (default: "localhost").
        port: Redis server port (default: 6379).
        db: Redis database index (default: 0).
        password: Optional Redis AUTH password.
        ssl: Whether to use SSL/TLS connection (default: False).
        socket_timeout: Socket operations timeout in seconds (default: 5.0).
        socket_connect_timeout: Connection timeout in seconds (default: 5.0).
        max_connections: Maximum pool size (default: 50).
        prefix: Global key prefix applied to all operations (e.g. "liankebao:cache").
        namespace: Logical namespace for key isolation (e.g. "session", "knowledge").
        default_ttl: Default TTL in seconds for cached entries (default: 300, 0 = no expiry).
    """

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    ssl: bool = False
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    max_connections: int = 50
    prefix: str = ""
    namespace: str = "default"
    default_ttl: int = 300

    @property
    def redis_url(self) -> str:
        """Build a redis:// or rediss:// URL from the config parameters.

        Returns:
            A Redis connection URL string.
        """
        scheme = "rediss" if self.ssl else "redis"
        auth_part = f":{self.password}@" if self.password else ""
        return f"{scheme}://{auth_part}{self.host}:{self.port}/{self.db}"


# ======================================================================
# RedisCache Adapter
# ======================================================================


class RedisCache(CacheProtocol):
    """Async Redis cache adapter implementing CacheProtocol.

    Features:
        - Connection pooling via redis.asyncio
        - JSON serialization for complex values
        - Per-key TTL with configurable default
        - Atomic INCR for increment()
        - Cache-aside pattern via get_or_set()
        - Namespace-prefixed keys to isolate cache domains
        - Graceful connection failure with logged warnings

    Raises:
        ConnectionError: If Redis is unavailable on init/operation.
    """

    def __init__(
        self,
        config: RedisConfig | None = None,
    ) -> None:
        """Initialize the Redis cache adapter.

        Does NOT connect to Redis — call start() to connect.

        Args:
            config: RedisConfig instance. If None, uses defaults.
        """
        self._config = config or RedisConfig()
        self._redis: Any = None
        self._pool: Any = None
        self._running = False

    @classmethod
    def from_url(
        cls,
        url: str,
        prefix: str = "",
        namespace: str = "default",
        default_ttl: int = 300,
        **kwargs: Any,
    ) -> RedisCache:
        """Create a RedisCache instance from a Redis URL.

        Args:
            url: Redis URL (e.g. "redis://localhost:6379/0").
            prefix: Global key prefix.
            namespace: Logical namespace.
            default_ttl: Default TTL in seconds.
            **kwargs: Additional redis.asyncio connection parameters.

        Returns:
            A configured RedisCache instance (not yet connected).
        """
        config = RedisConfig(
            prefix=prefix,
            namespace=namespace,
            default_ttl=default_ttl,
        )
        # Store the URL for later connection
        instance = cls(config=config)
        instance._connection_url = url
        instance._connection_kwargs = kwargs
        return instance

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Connect to Redis and verify the connection.

        Raises:
            ConnectionError: If Redis is unreachable or authentication fails.
        """
        if self._running:
            logger.warning("RedisCache is already connected")
            return

        try:
            import redis.asyncio as aioredis

            url = getattr(self, "_connection_url", None)
            kwargs = getattr(self, "_connection_kwargs", {})

            if url:
                # Connect via URL
                self._redis = await aioredis.from_url(
                    url,
                    socket_timeout=self._config.socket_timeout,
                    socket_connect_timeout=self._config.socket_connect_timeout,
                    max_connections=self._config.max_connections,
                    **kwargs,
                )
            else:
                # Connect via host/port
                self._redis = aioredis.Redis(
                    host=self._config.host,
                    port=self._config.port,
                    db=self._config.db,
                    password=self._config.password,
                    ssl=self._config.ssl,
                    socket_timeout=self._config.socket_timeout,
                    socket_connect_timeout=self._config.socket_connect_timeout,
                    max_connections=self._config.max_connections,
                )

            # Verify connection with PING
            await self._redis.ping()
            self._running = True
            logger.info(
                "RedisCache connected: %s:%d/%d (prefix=%r, namespace=%r, ttl=%ds)",
                self._config.host,
                self._config.port,
                self._config.db,
                self._config.prefix or "(none)",
                self._config.namespace,
                self._config.default_ttl,
            )

        except ImportError as exc:
            logger.error("redis.asyncio not available: %s", exc)
            raise RuntimeError("redis package is required. Install with: pip install redis") from exc
        except Exception as exc:
            logger.warning(
                "Redis connection failed (%s:%d): %s — cache operations will raise",
                self._config.host,
                self._config.port,
                exc,
            )
            self._redis = None
            self._running = False
            raise ConnectionError(f"Redis unavailable at {self._config.host}:{self._config.port}: {exc}") from exc

    async def stop(self) -> None:
        """Close the Redis connection gracefully."""
        if not self._running:
            return

        self._running = False
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                logger.exception("Error closing Redis connection")
            self._redis = None
        logger.info("RedisCache disconnected")

    # ── Key Prefixing ─────────────────────────────────────────────────

    def _prefixed_key(self, key: str) -> str:
        """Apply the global prefix and namespace to a key.

        Args:
            key: The raw cache key.

        Returns:
            The prefixed key string.
        """
        parts = [p for p in (self._config.prefix, self._config.namespace, key) if p]
        return ":".join(parts)

    @staticmethod
    def _serialize(value: Any) -> str:
        """Serialize a value to a JSON string for Redis storage.

        Args:
            value: The value to serialize.

        Returns:
            JSON string representation.
        """
        if isinstance(value, (str, int, float, bool)):
            return json.dumps(value, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize(data: bytes | str | None) -> Any:
        """Deserialize a Redis value from JSON string.

        Args:
            data: The raw bytes/string from Redis.

        Returns:
            The deserialized Python object, or None if data is None.
        """
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return data

    # ── CacheProtocol ─────────────────────────────────────────────────

    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the cache.

        Args:
            key: The cache key.
            default: Value to return if the key does not exist.

        Returns:
            The cached (deserialized) value, or *default* if not found.

        Raises:
            ConnectionError: If Redis is unavailable.
        """
        if self._redis is None:
            raise ConnectionError("Redis is not connected")
        try:
            data = await self._redis.get(self._prefixed_key(key))
            if data is None:
                return default
            return self._deserialize(data)
        except Exception as exc:
            logger.warning("Redis GET '%s' failed: %s", key, exc)
            raise ConnectionError(f"Redis operation failed: {exc}") from exc

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Store a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache (will be JSON-serialized).
            ttl: TTL in seconds. If None, uses the default from config.
                 0 or negative means no expiry.

        Returns:
            True if the value was successfully cached.

        Raises:
            ConnectionError: If Redis is unavailable.
        """
        if self._redis is None:
            raise ConnectionError("Redis is not connected")
        resolved_ttl = self._config.default_ttl if ttl is None else ttl
        prefixed = self._prefixed_key(key)
        serialized = self._serialize(value)

        try:
            if resolved_ttl and resolved_ttl > 0:
                await self._redis.setex(prefixed, resolved_ttl, serialized)
            else:
                await self._redis.set(prefixed, serialized)
            return True
        except Exception as exc:
            logger.warning("Redis SET '%s' failed: %s", key, exc)
            raise ConnectionError(f"Redis operation failed: {exc}") from exc

    async def delete(self, key: str) -> bool:
        """Remove a key from the cache.

        Args:
            key: The cache key to remove.

        Returns:
            True if the key existed and was removed, False otherwise.

        Raises:
            ConnectionError: If Redis is unavailable.
        """
        if self._redis is None:
            raise ConnectionError("Redis is not connected")
        try:
            result = await self._redis.delete(self._prefixed_key(key))
            return result > 0
        except Exception as exc:
            logger.warning("Redis DEL '%s' failed: %s", key, exc)
            raise ConnectionError(f"Redis operation failed: {exc}") from exc

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache without fetching its value.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.

        Raises:
            ConnectionError: If Redis is unavailable.
        """
        if self._redis is None:
            raise ConnectionError("Redis is not connected")
        try:
            return bool(await self._redis.exists(self._prefixed_key(key)))
        except Exception as exc:
            logger.warning("Redis EXISTS '%s' failed: %s", key, exc)
            raise ConnectionError(f"Redis operation failed: {exc}") from exc

    async def increment(self, key: str, delta: int = 1) -> int:
        """Atomically increment a numeric cache value.

        If the key does not exist, Redis INCRBY creates it at value *delta*.

        Args:
            key: The cache key.
            delta: Amount to increment (can be negative for decrement).

        Returns:
            The new value after incrementing.

        Raises:
            ConnectionError: If Redis is unavailable.
        """
        if self._redis is None:
            raise ConnectionError("Redis is not connected")
        try:
            result = await self._redis.incrby(self._prefixed_key(key), delta)
            return int(result)
        except Exception as exc:
            logger.warning("Redis INCRBY '%s' failed: %s", key, exc)
            raise ConnectionError(f"Redis operation failed: {exc}") from exc

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int | None = None,
    ) -> Any:
        """Get a value, computing and caching it if missing (cache-aside pattern).

        NOTE: This is **not** a distributed lock — concurrent callers may
        both invoke the factory. For distributed locking, use SETNX-based
        get_or_set or Redis locks.

        Args:
            key: The cache key.
            factory: Async callable that produces the value on cache miss.
            ttl: TTL in seconds for the cached value. If None, uses default.

        Returns:
            The cached (or freshly computed) value.

        Raises:
            ConnectionError: If Redis is unavailable.
        """
        value = await self.get(key)
        if value is not None:
            return value

        value = await factory()
        await self.set(key, value, ttl=ttl)
        return value

    # ── Utility ───────────────────────────────────────────────────────

    async def clear(self) -> None:
        """Flush all keys with the configured prefix/namespace.

        WARNING: This scans and deletes ALL keys matching the prefix.
        Use with caution in production.
        """
        if self._redis is None:
            raise ConnectionError("Redis is not connected")
        try:
            pattern = f"{self._prefixed_key('*')}"
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=500)
                if keys:
                    await self._redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            if deleted:
                logger.info("RedisCache cleared %d keys matching %r", deleted, pattern)
        except Exception as exc:
            logger.warning("RedisCache clear failed: %s", exc)
            raise ConnectionError(f"Redis clear failed: {exc}") from exc

    async def size(self) -> int:
        """Return the approximate number of keys with the configured prefix.

        Uses SCAN (not DBSIZE) to count only keys within the namespace.

        Returns:
            Approximate count of keys matching the prefix/namespace.
        """
        if self._redis is None:
            raise ConnectionError("Redis is not connected")
        try:
            pattern = f"{self._prefixed_key('*')}"
            cursor = 0
            count = 0
            while True:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=500)
                count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception as exc:
            logger.warning("RedisCache size check failed: %s", exc)
            raise ConnectionError(f"Redis operation failed: {exc}") from exc

    @property
    def is_connected(self) -> bool:
        """Whether the Redis connection is active."""
        return self._running and self._redis is not None

    def __repr__(self) -> str:
        return (
            f"<RedisCache connected={self.is_connected} "
            f"host={self._config.host}:{self._config.port}/{self._config.db} "
            f"prefix={self._config.prefix or '(none)'}>"
        )
