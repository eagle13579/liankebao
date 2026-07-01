"""Broker: Service Communication Layer interfaces — Interface + Adapter pattern.

This package defines the stable abstract contracts for inter-service communication.
Business code MUST depend only on these Protocols, never on concrete implementations.
Adapters can be in-process (local), Redis pub/sub, RabbitMQ, Kafka, gRPC, etc.
"""
