"""AI Gateway interfaces — unified AI model invocation contracts.

Architecture principle:
    Every AI model call (chat, embedding, streaming) goes through
    AIGatewayProtocol. This decouples business logic from:
        - Which LLM provider is used (DeepSeek, OpenAI, Anthropic, Ollama)
        - Whether the model runs locally or in the cloud
        - Cost tracking and token accounting
        - Model versioning and A/B testing of model outputs

    Model routing decisions live in ModelRegistryProtocol, allowing
    dynamic fallback: DeepSeek → OpenAI → Anthropic → local Ollama.

These contracts are STABLE — they will never change as the AI layer
scales from a single DeepSeek API key to a multi-provider, multi-model
routing mesh with cost optimization and latency-aware fallback.
"""

from __future__ import annotations

import dataclasses
import time
import uuid
from typing import Any, AsyncIterator, Protocol, runtime_checkable


# ======================================================================
# Data Models
# ======================================================================


@dataclasses.dataclass
class AIRequest:
    """A request to an AI chat/completion model.

    Attributes:
        model: Model identifier (e.g. "deepseek-chat", "gpt-4", "claude-3-opus").
        prompt: System prompt or instruction context.
        messages: List of conversation messages. Each message is a dict
            with keys "role" (system/user/assistant/tool) and "content".
        temperature: Sampling temperature (0.0 = deterministic, 2.0 = very random).
        max_tokens: Maximum tokens to generate in the response.
        stream: If True, return response as a stream of tokens.
        tools: Optional list of tool definitions for function-calling.
        response_format: Optional dict specifying structured output format
            (e.g. {"type": "json_object"}).
        user_id: Optional user identifier for rate limiting and tracking.
        request_id: Unique identifier for this request (auto-generated).
    """

    model: str
    prompt: str = ""
    messages: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    response_format: dict[str, Any] | None = None
    user_id: str | None = None
    request_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must not be empty")
        self.temperature = max(0.0, min(2.0, self.temperature))
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {self.max_tokens}")


@dataclasses.dataclass
class AIResponse:
    """The result of a non-streaming AI chat completion.

    Attributes:
        content: The generated text content.
        model: Which model produced the response (may differ from request).
        usage: Token usage breakdown {"prompt_tokens": N, "completion_tokens": N,
            "total_tokens": N}.
        latency_ms: End-to-end latency in milliseconds.
        finish_reason: Why the generation stopped (stop, length, content_filter, tool_calls).
        tool_calls: Any tool calls the model made.
        request_id: Matches the original request ID for correlation.
    """

    content: str
    model: str
    usage: dict[str, int] = dataclasses.field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    tool_calls: list[dict[str, Any]] | None = None
    request_id: str = ""


@dataclasses.dataclass
class EmbeddingRequest:
    """A request to generate vector embeddings.

    Attributes:
        texts: One or more text strings to embed.
        model: Embedding model identifier (e.g. "text-embedding-3-small", "m3e").
        user_id: Optional user identifier for tracking.
    """

    texts: list[str]
    model: str = "text-embedding-3-small"
    user_id: str | None = None

    def __post_init__(self) -> None:
        if not self.texts:
            raise ValueError("texts list must not be empty")
        if not self.model.strip():
            raise ValueError("model must not be empty")


@dataclasses.dataclass
class EmbeddingResponse:
    """The result of an embedding generation request.

    Attributes:
        embeddings: List of embedding vectors, one per input text.
            Each vector is a list of floats.
        model: Which model produced the embeddings.
        dimension: The dimensionality of each embedding vector.
        usage: Token usage {"prompt_tokens": N, "total_tokens": N}.
        latency_ms: End-to-end latency in milliseconds.
    """

    embeddings: list[list[float]]
    model: str
    dimension: int
    usage: dict[str, int] = dataclasses.field(default_factory=dict)
    latency_ms: float = 0.0


# ======================================================================
# AI Gateway Protocol
# ======================================================================


@runtime_checkable
class AIGatewayProtocol(Protocol):
    """Unified interface for all AI model interactions.

    Provides three core operations:
        1. chat() — Standard chat completion (non-streaming)
        2. stream_chat() — Streaming chat completion (token-by-token)
        3. embed() — Vector embedding generation

    Each adapter (DeepSeek, OpenAI, Ollama, etc.) implements this protocol,
    allowing seamless swapping without changing business logic.
    """

    async def chat(self, request: AIRequest) -> AIResponse:
        """Send a chat completion request and wait for the full response.

        Args:
            request: The chat completion request parameters.

        Returns:
            AIResponse with generated content and metadata.

        Raises:
            ConnectionError: If the AI provider is unreachable.
            TimeoutError: If the request exceeds the configured timeout.
            ValueError: If the request parameters are invalid.
        """
        ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate vector embeddings for one or more text inputs.

        Args:
            request: The embedding request with texts and model selection.

        Returns:
            EmbeddingResponse with generated vectors.

        Raises:
            ConnectionError: If the embedding provider is unreachable.
        """
        ...

    async def stream_chat(
        self,
        request: AIRequest,
    ) -> AsyncIterator[str]:
        """Send a streaming chat completion request.

        Yields content tokens as they are generated by the model.
        The final yielded value is the complete response text.

        Args:
            request: The chat completion request (stream=True will be forced).

        Yields:
            Text tokens as they arrive from the AI provider.

        Raises:
            ConnectionError: If the AI provider is unreachable.
        """
        # Ensure streaming mode is enabled
        request = dataclasses.replace(request, stream=True)
        ...


# ======================================================================
# Model Registry Protocol
# ======================================================================


@runtime_checkable
class ModelRegistryProtocol(Protocol):
    """Model registry — routing, discovery, and configuration of AI models.

    The registry determines which model to use for a given task,
    handles fallback chains, and provides model metadata.
    """

    async def get_model(self, model_id: str) -> dict[str, Any] | None:
        """Get metadata and configuration for a registered model.

        Args:
            model_id: Model identifier (e.g. "deepseek-chat", "gpt-4").

        Returns:
            Dict with keys: id, provider, capabilities, context_length,
            pricing (per 1K tokens), rate_limits, and any custom config.
            Returns None if the model is not registered.
        """
        ...

    async def list_models(
        self,
        capability: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all registered models, optionally filtered by capability.

        Args:
            capability: Optional filter (e.g. "chat", "embedding", "vision").

        Returns:
            List of model metadata dicts (same schema as get_model).
        """
        ...

    async def get_default(self, task: str = "chat") -> str:
        """Get the default model ID for a given task type.

        Args:
            task: Task type ("chat", "embedding", "vision", "tool_use").

        Returns:
            The model identifier string to use by default.

        Note:
            This method can implement dynamic routing based on:
                - Current latency of each provider
                - Cost optimization rules
                - A/B test experiment assignments
                - Geographic region fallback
        """
        ...

    async def resolve(
        self,
        requested_model: str,
        fallback_chain: list[str] | None = None,
    ) -> str:
        """Resolve a model request, applying fallback logic.

        Args:
            requested_model: The model the caller wants to use.
            fallback_chain: Ordered list of fallback models if the
                requested one is unavailable. If None, uses the
                registry's built-in fallback configuration.

        Returns:
            The model ID that should actually be used.
        """
        ...


# ======================================================================
# AI Metrics Provider Protocol
# ======================================================================


@runtime_checkable
class AIMetricsProviderProtocol(Protocol):
    """Cost and usage tracking for AI model invocations.

    Every chat and embedding call records metrics for:
        - Cost tracking (per model, per user, per project)
        - Token usage trends and anomaly detection
        - Latency monitoring and provider health
        - Budget management and rate limit awareness
    """

    async def record_call(
        self,
        request: AIRequest | EmbeddingRequest,
        response: AIResponse | EmbeddingResponse,
        provider: str = "",
    ) -> None:
        """Record a completed AI model call for cost/usage tracking.

        Args:
            request: The original request.
            response: The response with usage and latency data.
            provider: Which provider handled the call (e.g. "deepseek", "openai").
        """
        ...

    async def get_usage(
        self,
        since: float | None = None,
        until: float | None = None,
        model: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Query aggregated usage statistics.

        Args:
            since: Unix timestamp for the start of the window.
            until: Unix timestamp for the end of the window.
            model: Filter by model ID.
            user_id: Filter by user.

        Returns:
            Dict with keys: total_tokens, total_cost, total_requests,
            avg_latency_ms, and breakdown by model/provider.
        """
        ...

    async def get_cost_estimate(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
    ) -> float:
        """Estimate the cost of a hypothetical AI call.

        Args:
            model: The model to estimate cost for.
            prompt_tokens: Number of input tokens.
            completion_tokens: Expected number of output tokens.

        Returns:
            Estimated cost in the system's base currency (e.g., USD).
        """
        ...
