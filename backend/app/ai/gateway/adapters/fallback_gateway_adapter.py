"""FallbackAIGateway — AIGatewayProtocol adapter with primary → fallback chain.

Wraps a list of AIGatewayProtocol instances and implements a fallback chain:

    1. Try the *primary* gateway.
    2. If it fails, try *fallback_1*.
    3. If that fails, try *fallback_2*.
    4. … and so on until all gateways are exhausted.

Each method (chat, embed, stream_chat) follows the same fallback pattern.
If every gateway in the chain fails, the last exception is re-raised.

Key features:
    - Configurable fallback chain (primary + any number of fallbacks)
    - Per-gateway success/failure metrics
    - Detailed logging of which gateway served each request
    - Optional failure logging (default: enabled)

Usage:
    primary = DirectAIGateway(...)
    fallback1 = OpenAIGateway(...)
    fallback2 = OllamaGateway(...)

    gateway = FallbackAIGateway(gateways=[primary, fallback1, fallback2])
    response = await gateway.chat(request)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.ai.gateway.interfaces import (
    AIGatewayProtocol,
    AIRequest,
    AIResponse,
    EmbeddingRequest,
    EmbeddingResponse,
)

logger = logging.getLogger(__name__)


class AllGatewaysFailedError(Exception):
    """Raised when every gateway in the fallback chain has failed.

    Attributes:
        errors: List of (gateway_index, gateway_name, exception) tuples
            for diagnostic purposes.
    """

    def __init__(
        self,
        errors: list[tuple[int, str, Exception]],
        message: str = "All AI gateways in the fallback chain failed",
    ) -> None:
        self.errors = errors
        self.details = "; ".join(f"[{idx}]{name}: {exc}" for idx, name, exc in errors)
        super().__init__(f"{message}. Details: {self.details}")


class FallbackAIGateway(AIGatewayProtocol):
    """AIGatewayProtocol adapter implementing a primary → fallback chain.

    Takes an ordered list of AIGatewayProtocol instances. The first gateway
    is the *primary*, subsequent gateways are *fallbacks* tried in order
    when the primary (or previous fallback) fails.

    Each method (chat, embed, stream_chat) follows the same pattern:
        1. Iterate through gateways in order.
        2. On success, return the response and log which gateway served.
        3. On failure, log the error and try the next gateway.
        4. If all gateways fail, raise AllGatewaysFailedError.

    Metrics:
        - Per-gateway success and failure counts are tracked in
          ``self.gateway_metrics``.

    Args:
        gateways: Ordered list of AIGatewayProtocol instances. The first
            element is the primary; the rest are fallbacks.
        log_on_fallback: If True (default), log a warning when falling
            back to a secondary gateway.  If False, only errors are logged.
    """

    def __init__(
        self,
        gateways: list[AIGatewayProtocol],
        *,
        log_on_fallback: bool = True,
    ) -> None:
        if not gateways:
            raise ValueError("At least one gateway must be provided")

        self._gateways = gateways
        self._log_on_fallback = log_on_fallback

        # ── Per-gateway metrics ─────────────────────────────────────
        self.gateway_metrics: list[dict[str, int]] = [
            {"successes": 0, "failures": 0, "name": self._gateway_name(gw)} for gw in gateways
        ]

        self._total_requests: int = 0
        self._total_errors: int = 0

    # ── Public metrics ──────────────────────────────────────────────

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "gateways": self.gateway_metrics,
        }

    # ── AIGatewayProtocol ───────────────────────────────────────────

    async def chat(self, request: AIRequest) -> AIResponse:
        """Send a chat completion with fallback across all gateways."""
        self._total_requests += 1
        errors: list[tuple[int, str, Exception]] = []

        for idx, gateway in enumerate(self._gateways):
            try:
                response = await gateway.chat(request)

                # Success — record and return
                self.gateway_metrics[idx]["successes"] += 1
                self._log_gateway_used("chat", idx, gateway, request)
                return response

            except Exception as exc:
                self.gateway_metrics[idx]["failures"] += 1
                name = self._gateway_name(gateway)
                errors.append((idx, name, exc))

                if idx < len(self._gateways) - 1:
                    # More fallbacks available
                    self._log_fallback("chat", idx, name, exc, request)
                else:
                    # Last gateway — log the final failure
                    logger.error(
                        "FallbackAIGateway.chat ALL gateways failed for "
                        "request=%s model=%s. Last error from [%d]%s: %s",
                        request.request_id[:8],
                        request.model,
                        idx,
                        name,
                        exc,
                    )

        # All gateways exhausted
        self._total_errors += 1
        raise AllGatewaysFailedError(errors)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings with fallback across all gateways."""
        self._total_requests += 1
        errors: list[tuple[int, str, Exception]] = []

        for idx, gateway in enumerate(self._gateways):
            try:
                response = await gateway.embed(request)

                self.gateway_metrics[idx]["successes"] += 1
                self._log_gateway_used("embed", idx, gateway, request)
                return response

            except Exception as exc:
                self.gateway_metrics[idx]["failures"] += 1
                name = self._gateway_name(gateway)
                errors.append((idx, name, exc))

                if idx < len(self._gateways) - 1:
                    self._log_fallback("embed", idx, name, exc, request)
                else:
                    logger.error(
                        "FallbackAIGateway.embed ALL gateways failed for model=%s. Last error from [%d]%s: %s",
                        request.model,
                        idx,
                        name,
                        exc,
                    )

        self._total_errors += 1
        raise AllGatewaysFailedError(errors)

    async def stream_chat(
        self,
        request: AIRequest,
    ) -> AsyncIterator[str]:
        """Streaming chat completion with fallback across all gateways.

        Because streaming is a generator, errors inside the stream are
        surfaced as a yielded error string. If every gateway fails before
        any streaming begins, the fallback chain iterates synchronously
        (by consuming the async generators immediately for the non-last
        gateways) and the last gateway's stream is returned to the caller.

        If a gateway starts streaming but fails mid-stream, the last
        yielded error string indicates the failure and the caller sees it.
        """
        self._total_requests += 1
        errors: list[tuple[int, str, Exception]] = []

        for idx, gateway in enumerate(self._gateways):
            try:
                stream = gateway.stream_chat(request)
                self.gateway_metrics[idx]["successes"] += 1
                self._log_gateway_used("stream_chat", idx, gateway, request)

                # Yield from this gateway's stream
                async for token in stream:
                    yield token
                return  # Stream completed successfully

            except Exception as exc:
                self.gateway_metrics[idx]["failures"] += 1
                name = self._gateway_name(gateway)
                errors.append((idx, name, exc))

                if idx < len(self._gateways) - 1:
                    self._log_fallback("stream_chat", idx, name, exc, request)
                else:
                    logger.error(
                        "FallbackAIGateway.stream_chat ALL gateways failed for "
                        "request=%s model=%s. Last error from [%d]%s: %s",
                        request.request_id[:8],
                        request.model,
                        idx,
                        name,
                        exc,
                    )

        # All gateways exhausted — yield error
        self._total_errors += 1
        yield f"Error: All {len(self._gateways)} gateways failed"

    # ── Internals ───────────────────────────────────────────────────

    def _log_gateway_used(
        self,
        method: str,
        idx: int,
        gateway: AIGatewayProtocol,
        request: AIRequest | EmbeddingRequest,
    ) -> None:
        """Log which gateway successfully handled a request."""
        name = self._gateway_name(gateway)
        model = getattr(request, "model", "unknown")
        logger.info(
            "FallbackAIGateway.%s served by [%d]%s (model=%s)",
            method,
            idx,
            name,
            model,
        )

    def _log_fallback(
        self,
        method: str,
        idx: int,
        name: str,
        exc: Exception,
        request: AIRequest | EmbeddingRequest,
    ) -> None:
        """Log a fallback event when a gateway fails."""
        if not self._log_on_fallback:
            return

        model = getattr(request, "model", "unknown")
        next_idx = idx + 1
        logger.warning(
            "FallbackAIGateway.%s: [%d]%s failed for model=%s (request=%s). Falling back to gateway [%d]. Error: %s",
            method,
            idx,
            name,
            model,
            getattr(request, "request_id", "?")[:8],
            next_idx,
            exc,
        )

    @staticmethod
    def _gateway_name(gateway: AIGatewayProtocol) -> str:
        """Return a human-readable name for a gateway instance."""
        return type(gateway).__name__

    async def close(self) -> None:
        """Forward close to all gateways that support it."""
        for gateway in self._gateways:
            if hasattr(gateway, "close") and callable(gateway.close):
                try:
                    await gateway.close()
                except Exception as exc:
                    logger.warning(
                        "FallbackAIGateway.close: error closing %s: %s",
                        self._gateway_name(gateway),
                        exc,
                    )
