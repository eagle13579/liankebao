"""Repository interfaces — Data Access Layer contracts.

Every repository follows Interface + Adapter:
    Interface (Protocol) → what you depend on
    Adapter (implementing class) → what you swap out

Generic RepositoryProtocol[T] provides CRUD for any entity type.
Domain-specific protocols (KnowledgeRepositoryProtocol, GaiaEventRepositoryProtocol, etc.)
extend the generic protocol with domain queries.

These contracts are STABLE — they will never change as implementations
scale from SQLite through PostgreSQL to CockroachDB global clusters.
"""

from __future__ import annotations

import abc
import dataclasses
from typing import (
    Any,
    Generic,
    Optional,
    Protocol,
    TypeVar,
    runtime_checkable,
)

T = TypeVar("T")  # Entity type handled by the repository
TKey = TypeVar("TKey")  # Primary key type (int, str, UUID, etc.)


# ======================================================================
# Query Specification
# ======================================================================


@dataclasses.dataclass
class QuerySpec:
    """Declarative query specification — framework-agnostic.

    Encodes a query's filtering, ordering, pagination, and cursor-based
    continuation in a single immutable dataclass. Each adapter translates
    this into its native query language (SQL WHERE, MongoDB filter, etc.).

    Attributes:
        filters: Mapping of field → value for equality filtering.
            Supports special values: {"field__contains": val}, {"field__gt": val},
            {"field__gte": val}, {"field__lt": val}, {"field__lte": val},
            {"field__in": [val1, val2]}, {"field__ne": val}.
        order_by: List of "field" (ascending) or "-field" (descending).
        offset: Number of records to skip (for offset-based pagination).
        limit: Maximum records to return.
        cursor: Opaque cursor string for keyset/cursor-based pagination.
            When provided, offset is ignored in favor of cursor-based navigation.
    """

    filters: dict[str, Any] = dataclasses.field(default_factory=dict)
    order_by: list[str] = dataclasses.field(default_factory=list)
    offset: int = 0
    limit: int = 100
    cursor: str | None = None

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError(f"limit must be >= 1, got {self.limit}")
        if self.offset < 0:
            raise ValueError(f"offset must be >= 0, got {self.offset}")


# ======================================================================
# Generic Repository Protocol
# ======================================================================


@runtime_checkable
class RepositoryProtocol(Protocol[T]):
    """Generic CRUD contract for a single entity type.

    Type parameter ``T`` is the entity class (dataclass, ORM model, or Pydantic model).
    All methods are async because any backend (even in-memory) should be
    callable from async contexts without blocking.

    Implementations provide:
        * SQLAlchemyAsyncRepository[T] — for relational databases
        * InMemoryRepository[T] — for tests and prototyping
        * RedisRepository[T] — for fast caching-backed reads
        * MongoRepository[T] — for document stores
    """

    # ── Read ──────────────────────────────────────────────────────

    async def get(self, key: TKey) -> T | None:
        """Fetch a single entity by its primary key.

        Args:
            key: Primary key value.

        Returns:
            The entity if found, None otherwise.
        """
        ...

    async def find(self, spec: QuerySpec) -> list[T]:
        """Find entities matching the query specification.

        Args:
            spec: Declarative query spec with filters, ordering, pagination.

        Returns:
            List of matching entities (empty list if none match).
        """
        ...

    async def count(self, spec: QuerySpec | None = None) -> int:
        """Count entities matching optional filters.

        Args:
            spec: Query spec with filters (pagination fields are ignored for count).

        Returns:
            Total count of matching records.
        """
        ...

    # ── Write ─────────────────────────────────────────────────────

    async def save(self, entity: T) -> T:
        """Create or update an entity (upsert semantics).

        Args:
            entity: The entity to persist. If it has an ID/primary key
                that already exists, the implementation will update;
                otherwise it will insert.

        Returns:
            The persisted entity (with generated ID if applicable).
        """
        ...

    async def delete(self, key: TKey) -> bool:
        """Delete an entity by its primary key.

        Args:
            key: Primary key of the entity to delete.

        Returns:
            True if an entity was deleted, False if not found.
        """
        ...


# ======================================================================
# Domain-Specific Repository Protocols
# ======================================================================


@runtime_checkable
class KnowledgeRepositoryProtocol(Protocol):
    """Gaia Knowledge repository — semantic + CRUD for evolved knowledge.

    Extends the generic pattern with domain-specific queries needed
    by the Gaia Evolution Brain and related services.
    """

    async def get(self, key: int) -> Any | None:
        """Fetch a knowledge entry by its integer ID."""
        ...

    async def find(self, spec: QuerySpec) -> list[Any]:
        """Find knowledge entries matching the query spec."""
        ...

    async def count(self, spec: QuerySpec | None = None) -> int:
        """Count knowledge entries."""
        ...

    async def save(self, entity: Any) -> Any:
        """Persist a knowledge entry."""
        ...

    async def delete(self, key: int) -> bool:
        """Delete a knowledge entry by ID."""
        ...

    async def search_semantic(
        self,
        query: str,
        top_k: int = 10,
        confidence_min: float = 0.0,
    ) -> list[Any]:
        """Semantic search across knowledge entries.

        Uses the configured embedding backend + vector index to find
        the most semantically relevant knowledge entries.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return.
            confidence_min: Minimum confidence threshold (0.0–1.0).

        Returns:
            Ranked list of knowledge entries with relevance scores.
        """
        ...

    async def get_active_weights(self) -> dict[str, Any]:
        """Retrieve the current active model weights across all modules.

        Returns:
            Dictionary mapping module name (e.g. 'recommendation', 'search')
            to its weight configuration dict.
        """
        ...


@runtime_checkable
class GaiaEventRepositoryProtocol(Protocol):
    """Gaia evolution event log repository.

    Tracks all evolution lifecycle events for full-chain observability.
    """

    async def get(self, key: int) -> Any | None:
        """Fetch an event by its integer ID."""
        ...

    async def find(self, spec: QuerySpec) -> list[Any]:
        """Find events matching the query spec."""
        ...

    async def count(self, spec: QuerySpec | None = None) -> int:
        """Count events."""
        ...

    async def save(self, entity: Any) -> Any:
        """Persist an event."""
        ...

    async def delete(self, key: int) -> bool:
        """Delete an event by ID."""
        ...

    async def query_events(
        self,
        event_type: str | None = None,
        source: str | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
        since: Any | None = None,
        until: Any | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        """Query evolution events with flexible filters.

        Args:
            event_type: Filter by event type (knowledge_ingested, cycle_started, etc.).
            source: Filter by event source (api, scheduler, manual, internal).
            reference_type: Filter by associated object type.
            reference_id: Filter by associated object ID.
            since: Lower bound for created_at (datetime or iso-format string).
            until: Upper bound for created_at.
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            List of matching evolution events, ordered by created_at descending.
        """
        ...


@runtime_checkable
class TrainingRunRepositoryProtocol(Protocol):
    """Gaia training run repository.

    Records every evolution training cycle with full metrics & error tracking.
    """

    async def get(self, key: int) -> Any | None:
        """Fetch a training run by its integer ID."""
        ...

    async def find(self, spec: QuerySpec) -> list[Any]:
        """Find training runs matching the query spec."""
        ...

    async def count(self, spec: QuerySpec | None = None) -> int:
        """Count training runs."""
        ...

    async def save(self, entity: Any) -> Any:
        """Persist a training run."""
        ...

    async def delete(self, key: int) -> bool:
        """Delete a training run by ID."""
        ...

    async def query_runs(
        self,
        status: str | None = None,
        trigger: str | None = None,
        since: Any | None = None,
        until: Any | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Any]:
        """Query training runs with flexible filters.

        Args:
            status: Filter by status (pending, running, completed, failed).
            trigger: Filter by trigger type (manual, scheduled, automatic, api).
            since: Lower bound for created_at.
            until: Upper bound for created_at.
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            List of matching training runs, ordered by created_at descending.
        """
        ...


@runtime_checkable
class WeightRepositoryProtocol(Protocol):
    """Model weights repository — versioned weight management.

    Manages evolutionary weight versions across all AI modules.
    """

    async def get(self, key: int) -> Any | None:
        """Fetch a weight record by its integer ID."""
        ...

    async def find(self, spec: QuerySpec) -> list[Any]:
        """Find weight records matching the query spec."""
        ...

    async def count(self, spec: QuerySpec | None = None) -> int:
        """Count weight records."""
        ...

    async def save(self, entity: Any) -> Any:
        """Persist (create or update) a weight record."""
        ...

    async def delete(self, key: int) -> bool:
        """Delete a weight record by ID."""
        ...

    async def get_active_weights(self, module: str | None = None) -> dict[str, Any]:
        """Get currently active (deployed) weights.

        Args:
            module: If provided, return only weights for this module.
                If None, return all modules' active weights.

        Returns:
            If module is specified: the weight dict for that module.
            If module is None: dict of {module_name: weight_dict, ...}.
        """
        ...

    async def deploy_weights(
        self,
        module: str,
        weights: dict[str, Any],
        version: str,
        description: str = "",
        training_run_id: int | None = None,
    ) -> Any:
        """Deploy a new version of weights for a module.

        This deactivates the previous active version and creates a new one.

        Args:
            module: Module identifier (recommendation, search, extractor, etc.).
            weights: The weight configuration dict.
            version: Semantic version string (e.g. "1.3.0").
            description: Human-readable changelog/description.
            training_run_id: Optional link to the training run that produced these weights.

        Returns:
            The newly created weight entity.
        """
        ...
