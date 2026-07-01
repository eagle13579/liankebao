"""AI Gateway: AI Service Abstraction Layer — Interface + Adapter pattern.

This package defines the stable abstract contracts for AI model invocation.
Business code MUST depend only on these Protocols, never on concrete implementations.
Adapters include DeepSeekAdapter, OpenAIAdapter, AnthropicAdapter, OllamaAdapter, etc.
"""
