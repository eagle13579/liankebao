"""DirectAIGateway — AIGatewayProtocol adapter that calls DeepSeek API directly.

Wraps the DeepSeek chat completion and embedding APIs via async HTTP (httpx).
Includes:
    - chat() for standard completions
    - stream_chat() for streaming token-by-token responses
    - embed() for vector embeddings
    - Basic retry logic (3 attempts with exponential backoff)
    - Graceful fallback: returns error message on failure
    - Metrics tracking (latency, tokens, cost estimate)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

import httpx

from app.ai.gateway.interfaces import (
    AIRequest,
    AIResponse,
    AIGatewayProtocol,
    EmbeddingRequest,
    EmbeddingResponse,
)
from app.config import settings

logger = logging.getLogger(__name__)

# ── DeepSeek API endpoints ───────────────────────────────────────────────
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_EMBED_URL = "https://api.deepseek.com/v1/embeddings"

# Cost per 1K tokens (USD) — approximate as of 2025. Update as needed.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 0.00027, "output": 0.00110},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    "deepseek-coder": {"input": 0.00014, "output": 0.00028},
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
}

MAX_RETRIES = 3
BASE_BACKOFF_SEC = 1.0


class DirectAIGateway(AIGatewayProtocol):
    """Direct HTTP AI Gateway — calls DeepSeek API (or compatible) directly.

    Uses ``httpx.AsyncClient`` for all HTTP communication.  API key is
    read from ``settings.DEEPSEEK_API_KEY``.

    Retry behaviour:
        - On 429 (rate limit), 502, 503, 504 → retry up to 3 times
        - Exponential backoff: 1s, 2s, 4s
        - Other errors are returned immediately as failure responses
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """Initialise the DeepSeek gateway.

        Args:
            api_key: DeepSeek API key.  Falls back to
                ``settings.DEEPSEEK_API_KEY`` or ``settings.EMBEDDING_API_KEY``.
            base_url: Base URL for DeepSeek API.  Falls back to
                ``settings.DEEPSEEK_API_URL``.
            timeout: Default HTTP request timeout in seconds.
            max_retries: Number of retry attempts for retriable failures.
        """
        self._api_key = api_key or settings.DEEPSEEK_API_KEY or settings.EMBEDDING_API_KEY
        self._base_url = (base_url or settings.DEEPSEEK_API_URL or DEEPSEEK_CHAT_URL).rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

        # ── Metrics accumulator (in-memory, reset on restart) ────────
        self.metrics: dict[str, Any] = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_latency_ms": 0.0,
            "errors": 0,
        }

        self._client: httpx.AsyncClient | None = None

    # ── HTTP client lifecycle ─────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init an httpx AsyncClient (reused across calls)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── AIGatewayProtocol ─────────────────────────────────────────────

    async def chat(self, request: AIRequest) -> AIResponse:
        """Send a chat completion request to DeepSeek.

        Returns an AIResponse with generated content and metadata.
        On failure returns an AIResponse with an error message in content.
        """
        start = time.monotonic()
        self.metrics["total_requests"] += 1

        payload = self._build_chat_payload(request)
        url = self._chat_url()

        last_error: str | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                client = await self._get_client()
                response = await client.post(url, json=payload)

                if response.is_success:
                    data = response.json()
                    elapsed_ms = (time.monotonic() - start) * 1000.0

                    # Parse response
                    choice = data["choices"][0]
                    message = choice.get("message", {})
                    content = message.get("content", "")
                    finish_reason = choice.get("finish_reason", "stop")
                    tool_calls = message.get("tool_calls")

                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
                    usage_dict = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    }

                    model_used = data.get("model", request.model)
                    cost = self._estimate_cost(
                        model_used, prompt_tokens, completion_tokens
                    )

                    # Update metrics
                    self.metrics["total_tokens"] += total_tokens
                    self.metrics["total_cost"] += cost
                    self.metrics["total_latency_ms"] += elapsed_ms

                    return AIResponse(
                        content=content,
                        model=model_used,
                        usage=usage_dict,
                        latency_ms=elapsed_ms,
                        finish_reason=finish_reason,
                        tool_calls=tool_calls,
                        request_id=request.request_id,
                    )

                # Handle retriable status codes
                if response.status_code in (429, 502, 503, 504):
                    wait = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                    logger.warning(
                        "DeepSeek API returned %d (attempt %d/%d). "
                        "Retrying in %.1fs...",
                        response.status_code,
                        attempt,
                        self._max_retries,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    continue

                # Non-retriable error
                last_error = f"HTTP {response.status_code}: {response.text}"
                self.metrics["errors"] += 1
                return AIResponse(
                    content=f"Error: {last_error}",
                    model=request.model,
                    usage={},
                    latency_ms=(time.monotonic() - start) * 1000.0,
                    finish_reason="error",
                    request_id=request.request_id,
                )

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                wait = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "DeepSeek API connection error (attempt %d/%d): %s. "
                    "Retrying in %.1fs...",
                    attempt,
                    self._max_retries,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
                last_error = str(exc)
                continue
            except Exception as exc:
                logger.exception("Unexpected error calling DeepSeek chat API")
                self.metrics["errors"] += 1
                return AIResponse(
                    content=f"Unexpected error: {exc}",
                    model=request.model,
                    usage={},
                    latency_ms=(time.monotonic() - start) * 1000.0,
                    finish_reason="error",
                    request_id=request.request_id,
                )

        # All retries exhausted
        self.metrics["errors"] += 1
        return AIResponse(
            content=f"All retries exhausted. Last error: {last_error}",
            model=request.model,
            usage={},
            latency_ms=(time.monotonic() - start) * 1000.0,
            finish_reason="error",
            request_id=request.request_id,
        )

    async def stream_chat(
        self,
        request: AIRequest,
    ) -> AsyncIterator[str]:
        """Streaming chat completion — yields content tokens as they arrive.

        The caller iterates over this async generator to receive tokens.
        The final yielded value is always the full concatenated response.

        On error, yields an error message and stops.
        """
        request = self._ensure_streaming(request)
        payload = self._build_chat_payload(request)
        url = self._chat_url()

        client = await self._get_client()
        full_content = ""
        attempt = 0

        while attempt < self._max_retries:
            attempt += 1
            try:
                async with client.stream("POST", url, json=payload) as response:
                    if not response.is_success:
                        error_text = await response.aread()
                        logger.warning(
                            "Stream chat error (attempt %d/%d): %s",
                            attempt,
                            self._max_retries,
                            error_text,
                        )
                        if attempt < self._max_retries:
                            wait = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                            await asyncio.sleep(wait)
                            continue
                        yield f"Error: HTTP {response.status_code}"
                        return

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        import json
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                full_content += token
                                yield token
                        except json.JSONDecodeError:
                            continue
                    return

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.warning(
                    "Stream chat connection error (attempt %d/%d): %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt < self._max_retries:
                    wait = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                    await asyncio.sleep(wait)
                else:
                    yield f"Error: {exc}"
                    return
            except Exception as exc:
                logger.exception("Unexpected error in stream_chat")
                yield f"Error: {exc}"
                return

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate vector embeddings via DeepSeek embedding API.

        Falls back to returning an empty embedding list on failure.
        """
        start = time.monotonic()
        self.metrics["total_requests"] += 1

        payload = {
            "model": request.model,
            "input": request.texts,
        }
        url = self._embed_url()

        last_error: str | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                client = await self._get_client()
                response = await client.post(url, json=payload)

                if response.is_success:
                    data = response.json()
                    elapsed_ms = (time.monotonic() - start) * 1000.0

                    embeddings = [item["embedding"] for item in data["data"]]
                    dimension = len(embeddings[0]) if embeddings else 0
                    model_used = data.get("model", request.model)
                    usage = data.get("usage", {})
                    total_tokens = usage.get("total_tokens", 0)

                    self.metrics["total_tokens"] += total_tokens
                    self.metrics["total_latency_ms"] += elapsed_ms

                    return EmbeddingResponse(
                        embeddings=embeddings,
                        model=model_used,
                        dimension=dimension,
                        usage={
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "total_tokens": total_tokens,
                        },
                        latency_ms=elapsed_ms,
                    )

                if response.status_code in (429, 502, 503, 504):
                    wait = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                    logger.warning(
                        "DeepSeek embed API %d (attempt %d/%d). Retrying in %.1fs...",
                        response.status_code,
                        attempt,
                        self._max_retries,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    continue

                last_error = f"HTTP {response.status_code}: {response.text}"
                self.metrics["errors"] += 1
                return EmbeddingResponse(
                    embeddings=[],
                    model=request.model,
                    dimension=0,
                    usage={},
                    latency_ms=(time.monotonic() - start) * 1000.0,
                )

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                wait = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "DeepSeek embed connection error (attempt %d/%d): %s. "
                    "Retrying...",
                    attempt,
                    self._max_retries,
                    exc,
                )
                await asyncio.sleep(wait)
                last_error = str(exc)
                continue
            except Exception as exc:
                logger.exception("Unexpected error calling DeepSeek embed API")
                self.metrics["errors"] += 1
                return EmbeddingResponse(
                    embeddings=[],
                    model=request.model,
                    dimension=0,
                    usage={},
                    latency_ms=(time.monotonic() - start) * 1000.0,
                )

        self.metrics["errors"] += 1
        return EmbeddingResponse(
            embeddings=[],
            model=request.model,
            dimension=0,
            usage={},
            latency_ms=(time.monotonic() - start) * 1000.0,
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _build_chat_payload(self, request: AIRequest) -> dict[str, Any]:
        """Build the JSON payload for a DeepSeek chat completion request."""
        messages: list[dict[str, str]] = []
        if request.prompt:
            messages.append({"role": "system", "content": request.prompt})
        messages.extend(request.messages)

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }

        if request.tools:
            payload["tools"] = request.tools
        if request.response_format:
            payload["response_format"] = request.response_format

        return payload

    def _chat_url(self) -> str:
        """Return the chat completion endpoint URL."""
        if "/chat/completions" in self._base_url:
            return self._base_url
        return f"{self._base_url}/chat/completions"

    def _embed_url(self) -> str:
        """Return the embeddings endpoint URL."""
        if "/embeddings" in self._base_url:
            return self._base_url.replace("/chat/completions", "/embeddings")
        return f"{self._base_url}/embeddings"

    @staticmethod
    def _ensure_streaming(request: AIRequest) -> AIRequest:
        """Force streaming to be enabled for stream_chat."""
        import dataclasses
        return dataclasses.replace(request, stream=True)

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD based on model pricing lookup."""
        pricing = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (
            (prompt_tokens / 1000.0) * pricing.get("input", 0.0)
            + (completion_tokens / 1000.0) * pricing.get("output", 0.0)
        )
        return round(cost, 6)
