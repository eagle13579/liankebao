"""InMemoryCache — CacheProtocol adapter backed by an in-memory dict with TTL support.

Dict-based storage with configurable default TTL, get_or_set() factory
support, and a background cleanup task that evicts expired keys.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from app.cache.interfaces import CacheProtocol

logger = logging.getLogger(__name__)


class InMemoryCache(CacheProtocol):
    """In-memory dict-based cache with per-key TTL.

    Features:
        - dict-based key/value storage
        - Per-key TTL (default from constructor, overridable per set())
        - Atomic increment()
        - get_or_set() with async factory callable
        - Background cleanup of expired keys
        - Thread-safe for sync methods (asyncio-compatible via lock)

    Args:
        default_ttl: Default TTL in seconds (0 = no expiry). Default 300.
        cleanup_interval: Seconds between expired-key cleanup runs. Default 60.
            Set to 0 to disable background cleanup.
    """

    def __init__(
        self,
        default_ttl: int = 300,
        cleanup_interval: int = 60,
    ) -> None:
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval

        # _data: key → (value, expiry_timestamp or None)
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.Lock()

        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background cleanup loop.

        Call this during application startup.
        """
        if self._cleanup_interval <= 0:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.debug("InMemoryCache cleanup started (interval=%ds)", self._cleanup_interval)

    async def stop(self) -> None:
        """Stop the background cleanup loop.

        Call this during application shutdown.
        """
        self._running = False
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.debug("InMemoryCache cleanup stopped")

    # ── CacheProtocol ─────────────────────────────────────────────────

    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the cache.

        Returns *default* if the key does not exist or has expired.
        """
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default

            value, expiry = entry
            if expiry is not None and time.monotonic() > expiry:
                # Expired — remove and return default
                del self._data[key]
                return default
            return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Store a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: TTL in seconds.  If None, uses *default_ttl* from init.
                0 means no expiry.

        Returns:
            Always True (operation is guaranteed in-memory).
        """
        resolved_ttl = self._default_ttl if ttl is None else ttl
        expiry: float | None = None
        if resolved_ttl > 0:
            expiry = time.monotonic() + resolved_ttl

        with self._lock:
            self._data[key] = (value, expiry)
        return True

    async def delete(self, key: str) -> bool:
        """Remove a key from the cache.

        Returns True if the key existed, False otherwise.
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache without fetching its value.

        Returns False for expired keys.
        """
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            _, expiry = entry
            if expiry is not None and time.monotonic() > expiry:
                del self._data[key]
                return False
            return True

    async def increment(self, key: str, delta: int = 1) -> int:
        """Atomically increment a numeric cache value.

        If the key does not exist, it is created with value *delta* and
        no expiry.

        Returns:
            The new value after incrementing.
        """
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._data[key] = (delta, None)
                return delta

            value, expiry = entry
            new_value = (value if isinstance(value, (int, float)) else 0) + delta
            self._data[key] = (new_value, expiry)
            return int(new_value)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int | None = None,
    ) -> Any:
        """Get a value, computing and caching it if missing (cache-aside).

        The *factory* is an async callable that produces the value on cache miss.

        NOTE: This is **not** a distributed lock — concurrent callers may
        both invoke the factory.  For in-process use this is fine; for
        distributed use, use Redis lock-based get_or_set.
        """
        value = await self.get(key)
        if value is not None:
            return value

        value = await factory()
        await self.set(key, value, ttl=ttl)
        return value

    # ─── Utility ──────────────────────────────────────────────────────

    async def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._data.clear()

    async def size(self) -> int:
        """Return the number of entries currently in the cache."""
        # Note: includes expired entries that haven't been cleaned yet
        with self._lock:
            return len(self._data)

    # ── Background cleanup ────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        """Periodically remove expired keys from the dict."""
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                self._evict_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error during InMemoryCache cleanup")

    def _evict_expired(self) -> None:
        """Remove all expired entries (called from the background loop)."""
        now = time.monotonic()
        with self._lock:
            expired_keys = [k for k, (_, expiry) in self._data.items() if expiry is not None and now > expiry]
            for k in expired_keys:
                del self._data[k]
            if expired_keys:
                logger.debug("Evicted %d expired cache entries", len(expired_keys))
