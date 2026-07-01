"""AI Gateway adapter implementations — Interface + Adapter pattern.

This package contains concrete implementations of AI gateway interfaces.
Each adapter wraps a specific AI provider (DeepSeek, OpenAI, Anthropic, Ollama, etc.).

Phase 0-1:
    DirectAIGateway — Direct HTTP calls to DeepSeek API.

Phase 2:
    CachedAIGateway  — Wraps any AIGatewayProtocol with caching (via CacheProtocol),
                       rate limiting (token bucket), and circuit breaker.
    FallbackAIGateway — Wraps a list of AIGatewayProtocol instances and implements
                       a primary → fallback chain for resilience.
"""

from app.ai.gateway.adapters.cached_gateway_adapter import CachedAIGateway
from app.ai.gateway.adapters.direct_api_adapter import DirectAIGateway
from app.ai.gateway.adapters.fallback_gateway_adapter import FallbackAIGateway

__all__ = [
    "CachedAIGateway",
    "DirectAIGateway",
    "FallbackAIGateway",
]
