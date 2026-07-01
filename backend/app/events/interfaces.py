"""Event Bus interfaces — async event-driven communication contracts.

Architecture principle:
    All inter-component communication that is not request-response
    goes through the event bus. This decouples publishers from subscribers
    and enables eventual consistency, audit trails, and reactive workflows.

    Components communicate by:
        1. Publishing events (fire-and-forget or fire-and-forget-with-delay)
        2. Subscribing to event types they care about
        3. Handling events via registered EventHandler callbacks

These contracts are STABLE — they will never change as the eventing layer
scales from in-process callbacks to a global Kafka cluster with CQRS.
"""

from __future__ import annotations

import dataclasses
import enum
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

# ======================================================================
# Event Priority
# ======================================================================


class EventPriority(enum.IntEnum):
    """Priority levels for event processing ordering.

    Higher priority events are processed before lower priority events
    when the bus has multiple events queued.

    CRITICAL: 100 — System integrity events (payment, auth, data loss prevention).
               Processed with highest urgency; typically blocking.
    HIGH:     75  — User-facing events that affect UX.
    NORMAL:   50  — Default priority for standard business events.
    LOW:      25  — Background analytics, logging, telemetry.
    """

    CRITICAL = 100
    HIGH = 75
    NORMAL = 50
    LOW = 25


# ======================================================================
# Event Data Model
# ======================================================================


@dataclasses.dataclass
class Event:
    """An immutable domain event for inter-component communication.

    Events are the currency of the system — every meaningful occurrence
    is published as an Event and consumed by interested handlers.

    Attributes:
        type: Event type identifier (e.g. "knowledge.ingested",
            "evolution.cycle.completed", "weights.deployed").
            Subscribers filter by this field.
        source: Name/ID of the component that published the event.
        payload: Arbitrary JSON-serializable data attached to the event.
        priority: Processing priority (defaults to NORMAL).
        trace_id: Distributed tracing ID for correlating events across components.
        idempotency_key: Optional unique key for deduplication.
            If provided, the bus guarantees at-most-once delivery for this key.
        timestamp: When the event was created (UTC, set automatically).
        event_id: Unique identifier for this event instance (set automatically).
    """

    type: str
    source: str
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    trace_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)
    idempotency_key: str | None = None
    timestamp: datetime = dataclasses.field(default_factory=lambda: datetime.now(UTC))
    event_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise ValueError("event type must not be empty")
        if not self.source.strip():
            raise ValueError("event source must not be empty")


# ======================================================================
# Event Handler
# ======================================================================


class EventHandler(Protocol):
    """Callable that processes a single event.

    Handlers are registered with EventBusProtocol.subscribe() and
    invoked when an event of matching type is published.

    Handlers should be idempotent — the bus may deliver the same event
    more than once (at-least-once delivery).
    """

    async def __call__(self, event: Event) -> None:
        """Process the event.

        Args:
            event: The published event to handle.

        Raises:
            Exception: If processing fails, the bus will handle retry
                       according to its configuration.
        """
        ...


# ======================================================================
# Event Bus Protocol
# ======================================================================


@runtime_checkable
class EventBusProtocol(Protocol):
    """Core event bus — publish, subscribe, and manage event handlers.

    The event bus is the nervous system of the application.
    All inter-component communication flows through it.
    """

    async def publish(self, event: Event) -> None:
        """Publish an event immediately to all matching subscribers.

        Args:
            event: The event to publish.

        Note:
            This is fire-and-forget from the publisher's perspective.
            The bus delivers the event asynchronously to all subscribers.
            If the bus cannot enqueue the event, it MAY raise an exception.
        """
        ...

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        *,
        description: str = "",
    ) -> None:
        """Register a handler for a specific event type.

        Args:
            event_type: The event type string to subscribe to.
                Supports exact match ("knowledge.ingested") or wildcard
                patterns ("knowledge.*", "evolution.**").
            handler: Async callable that processes matching events.
            description: Optional human-readable description of this subscription.
        """
        ...

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Remove a previously registered handler.

        Args:
            event_type: The event type the handler was registered for.
            handler: The handler instance to remove.

        Returns:
            True if the handler was found and removed, False otherwise.
        """
        ...

    async def publish_delayed(
        self,
        event: Event,
        delay_seconds: int = 60,
    ) -> None:
        """Publish an event after a delay.

        Args:
            event: The event to publish later.
            delay_seconds: Seconds to wait before publishing.

        Note:
            Implementations may use:
                - asyncio.create_task + asyncio.sleep (in-process)
                - Redis sorted sets / delayed queues
                - RabbitMQ delayed message exchange
                - Kafka scheduled message delivery
        """
        ...


# ======================================================================
# Event Store Protocol
# ======================================================================


@runtime_checkable
class EventStoreProtocol(Protocol):
    """Event persistence — store and replay events for audit and recovery.

    Every event published through the bus SHOULD be persisted to the
    event store for:
        - Audit trail and compliance
        - Debugging and observability
        - Event sourcing / CQRS replay
        - Incident recovery
    """

    async def append(self, event: Event) -> None:
        """Persist an event to the store.

        Args:
            event: The event to persist. The store should handle
                deduplication via event_id if possible.
        """
        ...

    async def get(
        self,
        event_id: str,
    ) -> Event | None:
        """Retrieve a single event by its ID.

        Args:
            event_id: The unique event identifier.

        Returns:
            The event if found, None otherwise.
        """
        ...

    async def query(
        self,
        event_type: str | None = None,
        source: str | None = None,
        trace_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Query persisted events with flexible filters.

        Args:
            event_type: Filter by event type (supports wildcard "knowledge.*").
            source: Filter by publishing component.
            trace_id: Filter by distributed tracing ID.
            since: Lower bound for event timestamp.
            until: Upper bound for event timestamp.
            limit: Maximum events to return.
            offset: Number of events to skip.

        Returns:
            List of matching events, ordered by timestamp descending.
        """
        ...

    async def replay(
        self,
        event_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Replay events through the event bus, re-triggering all handlers.

        Args:
            event_type: If provided, only replay events of this type.
            since: Only replay events after this time.
            until: Only replay events before this time.

        Returns:
            The number of events replayed.
        """
        ...
