"""Events: Event Bus Layer interfaces — Interface + Adapter pattern.

This package defines the stable abstract contracts for event-driven communication.
Business code MUST depend only on these Protocols, never on concrete implementations.
Adapters include InProcessBus, RedisPubSubBus, RabbitMQBus, KafkaBus, etc.
"""
