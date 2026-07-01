"""Repositories: Data Access Layer interfaces — Interface + Adapter pattern.

This package defines the stable abstract contracts for all data access.
Business code MUST depend only on these Protocols, never on concrete implementations.
Implementations (SQLAlchemy, Redis, MongoDB, etc.) are swappable adapters behind these interfaces.

Usage:
    from app.repositories.interfaces import RepositoryProtocol, KnowledgeRepositoryProtocol
"""
