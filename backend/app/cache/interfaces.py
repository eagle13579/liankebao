"""Cache interfaces — caching abstraction contracts.

Architecture principle:
    Every cache consumer depends on CacheProtocol — never on Redis, Memcached,
    or any concrete implementation. This allows:
        - Hot swap from in-memory → Redis → Redis Cluster → Global CDN cache
        - Transparent two-tier caching (local + distributed)
        - Testability with InMemoryCache adapter
        - Zero code changes when the caching topology evolves

These contracts are STABLE — they will never change as caching
scales from a single process dict to a global Redis Cluster with CDN edge caching.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

# ======================================================================
# Configuration
# ======================================================================


@dataclasses.dataclass
class CacheConfig:
    """Configuration for a cache layer.

    Attributes:
        ttl: Default time-to-live in seconds for cached entries (0 = no expiry).
        namespace: Logical namespace to isolate cache keys across services
            (e.g. "gaia", "recommendation", "session").
        prefix: String prefix prepended to all keys (useful for Redis key naming
            conventions like "liankebao:cache:").
    """

    ttl: int = 300  # 5 minutes default
    namespace: str = "default"
    prefix: str = ""

    def __post_init__(self) -> None:
        if self.ttl < 0:
            raise ValueError(f"ttl must be >= 0, got {self.ttl}")


# ======================================================================
# Cache Key Builder
# ======================================================================


class CacheKey:
    """Utility for building deterministic, namespaced cache keys.

    Usage:
        key = CacheKey.build("knowledge", id=42, lang="zh")
        # => "liankebao:knowledge:42:zh"  (or "knowledge:42:zh" without prefix)
    """

    SEPARATOR = ":"

    @classmethod
    def build(cls, *parts: str | int, namespace: str = "", prefix: str = "") -> str:
        """Build a cache key from logical parts.

        Args:
            *parts: Ordered key segments (e.g. "knowledge", str(entity_id)).
            namespace: Optional namespace to isolate keys.
            prefix: Optional global prefix.

        Returns:
            A deterministic key string: "prefix:namespace:part1:part2:..."
        """
        segments = [p for p in (prefix, namespace) if p]
        segments.extend(str(p) for p in parts)
        filtered = [s for s in segments if s]
        return cls.SEPARATOR.join(filtered)

    @classmethod
    def from_dict(cls, data: dict[str, Any], namespace: str = "", prefix: str = "") -> str:
        """Build a cache key from a dictionary (sorted for determinism).

        Useful for parameterized cache keys like {"user_id": 1, "type": "preferences"}.

        Args:
            data: Dictionary of key-value pairs.
            namespace: Optional namespace.
            prefix: Optional global prefix.

        Returns:
            A deterministic key string with a content-hash suffix for uniqueness.
        """
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        content_hash = hashlib.sha256(serialized.encode()).hexdigest()[:12]
        return cls.build(content_hash, namespace=namespace, prefix=prefix)

    @classmethod
    def hash(cls, value: str, namespace: str = "", prefix: str = "") -> str:
        """Build a cache key from a hashed value.

        Useful for long or sensitive values that should not appear as plaintext keys.

        Args:
            value: The value to hash.
            namespace: Optional namespace.
            prefix: Optional global prefix.

        Returns:
            A deterministic key based on SHA-256 of the value.
        """
        digest = hashlib.sha256(value.encode()).hexdigest()
        return cls.build(digest[:16], namespace=namespace, prefix=prefix)


# ======================================================================
# Cache Protocol
# ======================================================================


@runtime_checkable
class CacheProtocol(Protocol):
    """Core cache abstraction — get, set, delete with async interface.

    All cache operations are async to support both synchronous backends
    (in-memory dict) and asynchronous backends (Redis, Memcached asyncio).
    """

    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the cache.

        Args:
            key: The cache key.
            default: Value to return if the key does not exist.

        Returns:
            The cached value, or *default* if not found.
        """
        ...

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Store a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache (must be serializable).
            ttl: Time-to-live in seconds. If None, uses the adapter's default TTL.

        Returns:
            True if the value was successfully cached.
        """
        ...

    async def delete(self, key: str) -> bool:
        """Remove a key from the cache.

        Args:
            key: The cache key to remove.

        Returns:
            True if the key existed and was removed, False otherwise.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache without fetching its value.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        ...

    async def increment(self, key: str, delta: int = 1) -> int:
        """Atomically increment a numeric cache value.

        If the key does not exist, it is created with value *delta*.

        Args:
            key: The cache key.
            delta: Amount to increment (can be negative for decrement).

        Returns:
            The new value after incrementing.
        """
        ...

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any | None],
        ttl: int | None = None,
    ) -> Any:
        """Get a value, computing and caching it if missing (cache-aside pattern).

        This is the atomic equivalent of:
            value = await cache.get(key)
            if value is None:
                value = await factory()
                await cache.set(key, value, ttl=ttl)
            return value

        Args:
            key: The cache key.
            factory: Async callable that produces the value on cache miss.
                The callable's return value will be cached.
            ttl: TTL in seconds for the cached value. If None, uses default.

        Returns:
            The cached (or freshly computed) value.
        """
        ...


# ======================================================================
# Two-Tier Cache Protocol
# ======================================================================


@runtime_checkable
class TwoTierCacheProtocol(Protocol):
    """Two-tier (L1 + L2) cache abstraction.

    L1: Local, ultra-fast cache (e.g., in-memory dict, lru_cache).
        Milliseconds latency, limited capacity, per-process.
    L2: Shared, distributed cache (e.g., Redis, Memcached, CDN).
        Sub-millisecond to milliseconds latency, large capacity, cluster-wide.

    Reads check L1 first, then L2, populating L1 on L2 hit.
    Writes update both tiers (write-through), or L2 only with L1 invalidation.

    Implementations:
        * TwoTierCache(L1=InMemoryCache, L2=RedisCache) — standard pattern
        * TwoTierCache(L1=InMemoryCache, L2=ClusterRedisCache) — global scale
    """

    async def get(self, key: str, default: Any = None) -> Any:
        """Get from L1 → L2. Populates L1 on L2 hit."""
        ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Write-through to both L1 and L2."""
        ...

    async def delete(self, key: str) -> bool:
        """Delete from both L1 and L2."""
        ...

    async def invalidate_l1(self, key: str) -> bool:
        """Invalidate only the L1 cache entry (L2 remains intact).

        Useful after a write that should be immediately visible cluster-wide
        but doesn't need to wait for L2 write.
        """
        ...

    async def get_l2_only(self, key: str, default: Any = None) -> Any:
        """Bypass L1 and read directly from L2.

        Useful for debugging or when L1 may have stale data after a cluster-wide update.
        """
        ...
