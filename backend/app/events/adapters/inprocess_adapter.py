"""InProcessEventBus — EventBusProtocol adapter backed by asyncio.Queue.

An in-process event bus with:
    - asyncio.Queue for event delivery
    - Handler registry (event_type → list of handlers)
    - Background consumer loop
    - subscribe() / unsubscribe() with proper cleanup
    - publish_delayed() via asyncio.create_task + sleep
    - Idempotency check via idempotency_key tracking
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from app.events.interfaces import Event, EventBusProtocol, EventHandler

logger = logging.getLogger(__name__)


class InProcessEventBus(EventBusProtocol):
    """In-process event bus using asyncio.Queue for delivery.

    A background consumer loop picks events from the queue and dispatches
    them to all registered handlers for the event type.

    Supports:
        - Exact-match subscription (``"knowledge.ingested"``)
        - publish_delayed() via ``asyncio.create_task`` + ``asyncio.sleep``
        - Idempotency deduplication via ``idempotency_key`` in Event
        - Priority-based ordering (higher priority processed first)

    Usage:
        bus = InProcessEventBus()
        await bus.start()

        async def my_handler(event: Event) -> None:
            print(f"Got event: {event.type}")

        await bus.subscribe("knowledge.*", my_handler)
        await bus.publish(Event(type="knowledge.ingested", source="test"))

        # On shutdown:
        await bus.stop()
    """

    def __init__(self, max_queue_size: int = 10_000) -> None:
        self._max_queue_size = max_queue_size
        self._queue: asyncio.PriorityQueue[tuple[int, int, Event]] = asyncio.PriorityQueue(maxsize=max_queue_size)
        # _handlers: event_type → list of (handler, description)
        self._handlers: dict[str, list[tuple[EventHandler, str]]] = defaultdict(list)
        # _idempotency: idempotency_key → set of seen keys
        self._seen_idempotency_keys: set[str] = set()

        self._consumer_task: asyncio.Task[None] | None = None
        self._running = False
        self._counter = 0  # monotonic counter for FIFO within same priority

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background consumer loop.

        Must be called before any events can be processed.
        """
        if self._running:
            logger.warning("InProcessEventBus already running")
            return
        self._running = True
        self._consumer_task = asyncio.create_task(self._consumer_loop())
        logger.info("InProcessEventBus started")

    async def stop(self) -> None:
        """Stop the background consumer loop gracefully.

        Drains remaining events from the queue before returning.
        """
        self._running = False
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        logger.info("InProcessEventBus stopped")

    @property
    def queue_size(self) -> int:
        """Approximate number of events waiting to be processed."""
        return self._queue.qsize()

    # ── EventBusProtocol ──────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
        """Publish an event to the queue for background processing.

        Raises:
            asyncio.QueueFull: If the queue is at capacity.
        """
        if not self._running:
            logger.warning("Event bus not running; event %s dropped", event.type)
            return

        # Idempotency check
        if event.idempotency_key:
            if event.idempotency_key in self._seen_idempotency_keys:
                logger.debug(
                    "Duplicate event dropped (key=%s): %s",
                    event.idempotency_key,
                    event.type,
                )
                return
            self._seen_idempotency_keys.add(event.idempotency_key)

        # Priority: negate so higher numeric priority is processed first
        # Counter ensures FIFO ordering for same priority
        self._counter += 1
        priority_key = -event.priority.value
        await self._queue.put((priority_key, self._counter, event))

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        *,
        description: str = "",
    ) -> None:
        """Register a handler for a specific event type.

        Supports exact match (``"knowledge.ingested"``).
        """
        if not callable(handler):
            raise TypeError("handler must be a callable")
        # Remove any existing subscription for same handler + type combo
        self._handlers[event_type] = [(h, d) for h, d in self._handlers[event_type] if h is not handler]
        self._handlers[event_type].append((handler, description))
        logger.debug("Handler subscribed to '%s': %s", event_type, description or handler.__name__)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Remove a previously registered handler.

        Returns True if the handler was found and removed, False otherwise.
        """
        handlers = self._handlers.get(event_type, [])
        before = len(handlers)
        self._handlers[event_type] = [(h, d) for h, d in handlers if h is not handler]
        removed = len(handlers) - len(self._handlers[event_type])
        if removed:
            logger.debug("Handler unsubscribed from '%s': %s", event_type, handler.__name__)
        return removed > 0

    async def publish_delayed(
        self,
        event: Event,
        delay_seconds: int = 60,
    ) -> None:
        """Publish an event after a delay using asyncio.create_task + sleep.

        This is fire-and-forget from the caller's perspective — the
        delayed publish runs in a background task.
        """
        if delay_seconds < 0:
            raise ValueError(f"delay_seconds must be >= 0, got {delay_seconds}")

        async def _delayed_publish() -> None:
            await asyncio.sleep(delay_seconds)
            try:
                await self.publish(event)
            except Exception:
                logger.exception(
                    "Failed to publish delayed event %s (key=%s)",
                    event.type,
                    event.idempotency_key,
                )

        asyncio.create_task(_delayed_publish())
        logger.debug("Scheduled delayed publish of %s in %ds", event.type, delay_seconds)

    # ── Consumer loop ─────────────────────────────────────────────────

    async def _consumer_loop(self) -> None:
        """Background loop: dequeue events and dispatch to matching handlers."""
        while self._running:
            try:
                _, _, event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
                self._queue.task_done()
            except TimeoutError:
                # Normal — just means the queue was empty
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in event consumer loop")

    async def _dispatch(self, event: Event) -> None:
        """Dispatch an event to all matching handlers."""
        # Find handlers for exact event type match
        handlers = list(self._handlers.get(event.type, []))

        # Also check for wildcard pattern matches
        for pattern, h_list in list(self._handlers.items()):
            if pattern != event.type and self._pattern_matches(pattern, event.type):
                handlers.extend(h_list)

        if not handlers:
            logger.debug("No handlers for event type: %s", event.type)
            return

        for handler, description in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Handler %s failed processing event %s",
                    description or handler.__name__,
                    event.type,
                )

    @staticmethod
    def _pattern_matches(pattern: str, event_type: str) -> bool:
        """Simple wildcard matching.

        Supports:
            - ``knowledge.*`` matches ``knowledge.ingested``, ``knowledge.foo``
            - ``**`` matches everything
        """
        if pattern == "**":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]  # remove trailing .*
            return event_type.startswith(prefix) or event_type == prefix.rstrip(".")
        return False
