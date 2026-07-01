"""CachedAIGateway — AIGatewayProtocol adapter with caching, rate limiting, and circuit breaker.

Wraps any AIGatewayProtocol (the "inner" gateway) and adds production-grade
resilience features on top:

    - **Caching** — Responses are cached via CacheProtocol. On cache hit the
      cached response is returned immediately; on miss the inner gateway is
      called and the result is cached.
    - **Rate limiting** — Per-model token-bucket rate limiter. Configurable
      requests-per-minute (RPM). Requests that exceed the limit raise a
      RateLimitError.
    - **Circuit breaker** — After *threshold* consecutive failures the circuit
      opens and all subsequent requests fail fast for *cooldown* seconds before
      allowing a single probe request.
    - **Metrics** — Tracks cache hit rate, latency percentiles (p50/p90/p99),
      and total request/error counts.

Usage:
    direct = DirectAIGateway(...)
    cache = RedisCache(...)
    gateway = CachedAIGateway(inner=direct, cache=cache, cache_ttl=3600)
    response = await gateway.chat(request)
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import logging
import math
import time
from collections import deque
from typing import Any, AsyncIterator

from app.ai.gateway.interfaces import (
    AIRequest,
    AIResponse,
    AIGatewayProtocol,
    EmbeddingRequest,
    EmbeddingResponse,
)
from app.cache.interfaces import CacheProtocol

logger = logging.getLogger(__name__)


# ======================================================================
# Custom Exceptions
# ======================================================================


class RateLimitError(Exception):
    """Raised when the rate limit for a model is exceeded."""

    def __init__(self, model: str, retry_after: float) -> None:
        self.model = model
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for model '{model}'. "
            f"Retry after {retry_after:.1f}s."
        )


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open (too many recent failures)."""

    def __init__(self, model: str, cooldown_remaining: float) -> None:
        self.model = model
        self.cooldown_remaining = cooldown_remaining
        super().__init__(
            f"Circuit breaker open for model '{model}'. "
            f"Cooldown remaining: {cooldown_remaining:.1f}s."
        )


# ======================================================================
# Token Bucket Rate Limiter
# ======================================================================


class TokenBucket:
    """Per-key token bucket rate limiter (async-safe).

    Each bucket holds up to *capacity* tokens. Tokens are replenished at
    *refill_rate* tokens per second.  If a request finds the bucket empty
    it is denied.
    """

    __slots__ = ("_capacity", "_refill_rate", "_tokens", "_last_refill")

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume *tokens* from the bucket.

        Returns:
            True if tokens were consumed, False if insufficient tokens remain.
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        """Number of tokens currently available."""
        self._refill()
        return self._tokens

    @property
    def wait_time(self) -> float:
        """Estimated seconds until one token becomes available."""
        self._refill()
        if self._tokens >= 1.0:
            return 0.0
        if self._refill_rate <= 0:
            return math.inf
        return (1.0 - self._tokens) / self._refill_rate


# ======================================================================
# Circuit Breaker State
# ======================================================================


@dataclasses.dataclass
class CircuitBreakerState:
    """Mutable state for a single circuit breaker."""

    failures: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    circuit_open: bool = False
    circuit_open_time: float = 0.0
    total_successes: int = 0
    total_failures: int = 0


# ======================================================================
# Latency Histogram (for p50 / p90 / p99)
# ======================================================================


class LatencyHistogram:
    """Tracks latency percentiles using a bounded sliding window of samples."""

    def __init__(self, max_samples: int = 1000) -> None:
        self._samples: deque[float] = deque(maxlen=max_samples)

    def record(self, latency_ms: float) -> None:
        self._samples.append(latency_ms)

    def percentile(self, p: float) -> float:
        """Compute the *p*-th percentile of recorded latencies.

        Args:
            p: Percentile as a float (e.g. 50.0, 90.0, 99.0).

        Returns:
            The latency value at that percentile, or 0.0 if no samples.
        """
        if not self._samples:
            return 0.0
        sorted_samples = sorted(self._samples)
        index = int(math.ceil(p / 100.0 * len(sorted_samples))) - 1
        index = max(0, min(index, len(sorted_samples) - 1))
        return sorted_samples[index]

    @property
    def p50(self) -> float:
        return self.percentile(50.0)

    @property
    def p90(self) -> float:
        return self.percentile(90.0)

    @property
    def p99(self) -> float:
        return self.percentile(99.0)

    def snapshot(self) -> dict[str, float]:
        return {
            "p50": self.p50,
            "p90": self.p90,
            "p99": self.p99,
            "count": len(self._samples),
        }


# ======================================================================
# CachedAIGateway
# ======================================================================


class CachedAIGateway(AIGatewayProtocol):
    """AIGatewayProtocol wrapper adding caching, rate limiting, and circuit breaker.

    This adapter wraps another AIGatewayProtocol (the *inner* gateway) and
    transparently adds:

        1. **Response caching** via CacheProtocol — identical requests
           (same model + messages hash) return cached results.
        2. **Per-model rate limiting** using token buckets — configurable
           via *rate_limit_rpm* (requests per minute per model).
        3. **Circuit breaker** — opens after *circuit_breaker_threshold*
           consecutive failures, stays open for *circuit_breaker_cooldown*
           seconds, then allows a single probe.
        4. **Metrics** — cache hit rate, latency p50/p90/p99, error counts.

    Caching:
        - ``chat()``: keyed by ``model + sha256(messages + prompt)``.
        - ``embed()``: keyed by ``model + sha256(texts)``.
        - ``stream_chat()``: buffers the full response, caches it, then
          yields the buffered content.  On cache hit, replays from cache.

    Args:
        inner: The wrapped AIGatewayProtocol instance.
        cache: CacheProtocol instance for response caching.
        cache_ttl: TTL in seconds for cached responses (default: 3600).
        rate_limit_rpm: Max requests per minute per model (0 = no limit).
        circuit_breaker_threshold: Consecutive failures before circuit opens
            (default: 3).
        circuit_breaker_cooldown: Seconds the circuit stays open before
            allowing a probe (default: 30).
    """

    def __init__(
        self,
        inner: AIGatewayProtocol,
        cache: CacheProtocol,
        *,
        cache_ttl: int = 3600,
        rate_limit_rpm: int = 0,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown: float = 30.0,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._rate_limit_rpm = rate_limit_rpm
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._circuit_breaker_cooldown = circuit_breaker_cooldown

        # ── Per-model rate limiters ─────────────────────────────────
        self._buckets: dict[str, TokenBucket] = {}

        # ── Per-model circuit breakers ──────────────────────────────
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}

        # ── Metrics ─────────────────────────────────────────────────
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._chat_latency = LatencyHistogram()
        self._embed_latency = LatencyHistogram()
        self._errors: int = 0
        self._total_requests: int = 0

    # ── Public metrics access ───────────────────────────────────────

    @property
    def cache_hit_count(self) -> int:
        return self._cache_hits

    @property
    def cache_miss_count(self) -> int:
        return self._cache_misses

    @property
    def cache_hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return self._cache_hits / total

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "chat_latency": self._chat_latency.snapshot(),
            "embed_latency": self._embed_latency.snapshot(),
            "errors": self._errors,
            "total_requests": self._total_requests,
        }

    # ── AIGatewayProtocol ───────────────────────────────────────────

    async def chat(self, request: AIRequest) -> AIResponse:
        """Send a chat completion with caching, rate limiting, and circuit breaker."""
        self._total_requests += 1
        model = request.model

        # 1. Rate limiting check
        await self._check_rate_limit(model)

        # 2. Circuit breaker check
        self._check_circuit_breaker(model)

        # 3. Build cache key and check cache
        cache_key = self._build_chat_cache_key(request)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            response = self._deserialize_response(cached)
            logger.debug(
                "CachedAIGateway CACHE HIT (chat) for model=%s request=%s",
                model,
                request.request_id[:8],
            )
            return response

        self._cache_misses += 1
        start = time.monotonic()

        try:
            response = await self._inner.chat(request)
        except Exception as exc:
            self._record_failure(model)
            self._errors += 1
            raise

        elapsed_ms = (time.monotonic() - start) * 1000.0
        self._record_success(model)
        self._chat_latency.record(elapsed_ms)

        # Cache the response (serialized)
        serialized = self._serialize_response(response)
        await self._cache.set(cache_key, serialized, ttl=self._cache_ttl)

        return response

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings with caching, rate limiting, and circuit breaker."""
        self._total_requests += 1
        model = request.model

        await self._check_rate_limit(model)
        self._check_circuit_breaker(model)

        cache_key = self._build_embed_cache_key(request)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            response = self._deserialize_embedding_response(cached)
            logger.debug(
                "CachedAIGateway CACHE HIT (embed) for model=%s",
                model,
            )
            return response

        self._cache_misses += 1
        start = time.monotonic()

        try:
            response = await self._inner.embed(request)
        except Exception as exc:
            self._record_failure(model)
            self._errors += 1
            raise

        elapsed_ms = (time.monotonic() - start) * 1000.0
        self._record_success(model)
        self._embed_latency.record(elapsed_ms)

        serialized = self._serialize_embedding_response(response)
        await self._cache.set(cache_key, serialized, ttl=self._cache_ttl)

        return response

    async def stream_chat(
        self,
        request: AIRequest,
    ) -> AsyncIterator[str]:
        """Streaming chat completion with caching and resilience.

        On cache hit: yields tokens from the cached full response.
        On cache miss: buffers all tokens, caches the full response,
        then yields tokens.

        Note:
            Rate limiting and circuit breaker checks are performed before
            the stream starts.  Because streaming yields a generator, errors
            inside the stream are surfaced as a yielded error string, not as
            an exception.
        """
        self._total_requests += 1
        model = request.model

        await self._check_rate_limit(model)
        self._check_circuit_breaker(model)

        cache_key = self._build_chat_cache_key(request)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            response = self._deserialize_response(cached)
            logger.debug(
                "CachedAIGateway CACHE HIT (stream_chat) for model=%s request=%s",
                model,
                request.request_id[:8],
            )
            # Replay cached content token-by-token (split by spaces for realism)
            content = response.content
            for token in self._tokenize_response(content):
                yield token
            return

        self._cache_misses += 1
        start = time.monotonic()
        full_content: list[str] = []

        try:
            async for token in self._inner.stream_chat(request):
                full_content.append(token)
                yield token
        except Exception as exc:
            self._record_failure(model)
            self._errors += 1
            yield f"Error: {exc}"
            return

        elapsed_ms = (time.monotonic() - start) * 1000.0
        self._record_success(model)
        self._chat_latency.record(elapsed_ms)

        # Cache the full response
        complete_content = "".join(full_content)
        cached_response = AIResponse(
            content=complete_content,
            model=model,
            usage={},
            latency_ms=elapsed_ms,
            finish_reason="stop",
            request_id=request.request_id,
        )
        serialized = self._serialize_response(cached_response)
        await self._cache.set(cache_key, serialized, ttl=self._cache_ttl)

    # ── Rate limiting ───────────────────────────────────────────────

    async def _check_rate_limit(self, model: str) -> None:
        """Raise RateLimitError if the model's token bucket is empty."""
        if self._rate_limit_rpm <= 0:
            return

        if model not in self._buckets:
            # Refill rate = RPM / 60 tokens per second
            self._buckets[model] = TokenBucket(
                capacity=self._rate_limit_rpm,
                refill_rate=self._rate_limit_rpm / 60.0,
            )

        bucket = self._buckets[model]
        if not bucket.consume(1.0):
            retry_after = bucket.wait_time
            logger.warning(
                "Rate limit exceeded for model '%s'. Retry after %.1fs",
                model,
                retry_after,
            )
            raise RateLimitError(model=model, retry_after=retry_after)

    # ── Circuit breaker ─────────────────────────────────────────────

    def _get_circuit_breaker(self, model: str) -> CircuitBreakerState:
        """Get (or create) the circuit breaker state for *model*."""
        if model not in self._circuit_breakers:
            self._circuit_breakers[model] = CircuitBreakerState()
        return self._circuit_breakers[model]

    def _check_circuit_breaker(self, model: str) -> None:
        """Raise CircuitBreakerOpenError if the circuit is open."""
        cb = self._get_circuit_breaker(model)
        if not cb.circuit_open:
            return

        # Check if cooldown has elapsed → allow probe
        elapsed = time.monotonic() - cb.circuit_open_time
        if elapsed >= self._circuit_breaker_cooldown:
            logger.info(
                "Circuit breaker HALF-OPEN for model '%s' (cooldown elapsed). "
                "Allowing probe request.",
                model,
            )
            cb.circuit_open = False
            cb.consecutive_failures = 0
            return

        remaining = self._circuit_breaker_cooldown - elapsed
        raise CircuitBreakerOpenError(model=model, cooldown_remaining=remaining)

    def _record_success(self, model: str) -> None:
        """Record a successful call for circuit breaker tracking."""
        cb = self._get_circuit_breaker(model)
        cb.consecutive_failures = 0
        cb.total_successes += 1
        # Close the circuit on success
        cb.circuit_open = False

    def _record_failure(self, model: str) -> None:
        """Record a failure — may trip the circuit breaker."""
        cb = self._get_circuit_breaker(model)
        cb.consecutive_failures += 1
        cb.total_failures += 1
        cb.last_failure_time = time.monotonic()

        if cb.consecutive_failures >= self._circuit_breaker_threshold:
            cb.circuit_open = True
            cb.circuit_open_time = time.monotonic()
            logger.warning(
                "Circuit breaker OPEN for model '%s' after %d consecutive failures. "
                "Cooldown: %.1fs",
                model,
                cb.consecutive_failures,
                self._circuit_breaker_cooldown,
            )

    # ── Cache key helpers ───────────────────────────────────────────

    @staticmethod
    def _build_chat_cache_key(request: AIRequest) -> str:
        """Build a deterministic cache key for a chat request.

        Key format: ``ai:chat:{model}:{content_hash}``
        """
        content_parts = []
        if request.prompt:
            content_parts.append(f"system:{request.prompt}")
        for msg in request.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content_parts.append(f"{role}:{content}")
        if request.tools:
            content_parts.append(f"tools:{json.dumps(request.tools, sort_keys=True)}")
        if request.response_format:
            content_parts.append(
                f"format:{json.dumps(request.response_format, sort_keys=True)}"
            )

        raw = "||".join(content_parts)
        content_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ai:chat:{request.model}:{content_hash}"

    @staticmethod
    def _build_embed_cache_key(request: EmbeddingRequest) -> str:
        """Build a deterministic cache key for an embedding request.

        Key format: ``ai:embed:{model}:{texts_hash}``
        """
        raw = "||".join(request.texts)
        texts_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ai:embed:{request.model}:{texts_hash}"

    # ── Serialization helpers ───────────────────────────────────────

    @staticmethod
    def _serialize_response(response: AIResponse) -> str:
        """Serialize an AIResponse to a JSON string for caching."""
        return json.dumps(
            {
                "content": response.content,
                "model": response.model,
                "usage": response.usage,
                "latency_ms": response.latency_ms,
                "finish_reason": response.finish_reason,
                "tool_calls": response.tool_calls,
                "request_id": response.request_id,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_response(data: str) -> AIResponse:
        """Deserialize a cached JSON string back to an AIResponse."""
        obj = json.loads(data) if isinstance(data, str) else data
        return AIResponse(
            content=obj["content"],
            model=obj["model"],
            usage=obj.get("usage", {}),
            latency_ms=obj.get("latency_ms", 0.0),
            finish_reason=obj.get("finish_reason", "stop"),
            tool_calls=obj.get("tool_calls"),
            request_id=obj.get("request_id", ""),
        )

    @staticmethod
    def _serialize_embedding_response(response: EmbeddingResponse) -> str:
        """Serialize an EmbeddingResponse to a JSON string for caching."""
        return json.dumps(
            {
                "embeddings": response.embeddings,
                "model": response.model,
                "dimension": response.dimension,
                "usage": response.usage,
                "latency_ms": response.latency_ms,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_embedding_response(data: str) -> EmbeddingResponse:
        """Deserialize a cached JSON string back to an EmbeddingResponse."""
        obj = json.loads(data) if isinstance(data, str) else data
        return EmbeddingResponse(
            embeddings=obj["embeddings"],
            model=obj["model"],
            dimension=obj.get("dimension", 0),
            usage=obj.get("usage", {}),
            latency_ms=obj.get("latency_ms", 0.0),
        )

    @staticmethod
    def _tokenize_response(content: str) -> list[str]:
        """Split cached content into token-sized chunks for stream replay.

        This splits on whitespace boundaries to simulate streaming tokens.
        Each chunk is returned with a trailing space (except the last) to
        approximate how an LLM stream would behave.
        """
        if not content:
            return [""]
        words = content.split(" ")
        tokens: list[str] = []
        for i, word in enumerate(words):
            if i < len(words) - 1:
                tokens.append(word + " ")
            else:
                tokens.append(word)
        return tokens

    async def close(self) -> None:
        """Forward close to the inner gateway if it supports it."""
        if hasattr(self._inner, "close") and callable(self._inner.close):
            await self._inner.close()
