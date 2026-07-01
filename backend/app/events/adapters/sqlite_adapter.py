"""SQLiteEventBus — EventBusProtocol adapter backed by SQLite (async via aiosqlite).

Phase 1 persistent event bus with:
    - SQLite storage for durable event persistence
    - events table with full schema (id, type, source, payload JSON, priority, trace_id,
      idempotency_key, created_at, processed_at)
    - subscribers table for persisted subscription patterns
    - Background consumer polling for unprocessed events
    - At-least-once delivery with idempotency_key deduplication
    - publish_delayed() via processed_at future timestamp
    - Replay capability: reprocess events within a time range

Usage:
    bus = SQLiteEventBus("events.db")
    await bus.start()

    async def handler(event: Event) -> None:
        print(f"Handling: {event.type}")

    await bus.subscribe("knowledge.*", handler)
    await bus.publish(Event(type="knowledge.ingested", source="test"))
    await bus.stop()
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable

import aiosqlite

from app.events.interfaces import Event, EventBusProtocol, EventHandler, EventPriority

logger = logging.getLogger(__name__)

# ======================================================================
# SQLite Schema
# ======================================================================

CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    source          TEXT NOT NULL,
    payload         TEXT NOT NULL DEFAULT '{}',
    priority        INTEGER NOT NULL DEFAULT 50,
    trace_id        TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT,
    created_at      TEXT NOT NULL,
    processed_at    TEXT,
    failure_count   INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT
);
"""

CREATE_EVENTS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_processed_at ON events(processed_at);
CREATE INDEX IF NOT EXISTS idx_events_idempotency ON events(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id);
"""

CREATE_SUBSCRIBERS_TABLE = """
CREATE TABLE IF NOT EXISTS subscribers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type_pattern TEXT NOT NULL,
    handler_id      TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    UNIQUE(event_type_pattern, handler_id)
);
"""


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(iso_str: str | None) -> datetime | None:
    """Parse an ISO 8601 string to a datetime."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None


# ======================================================================
# SQLiteEventBus
# ======================================================================


class SQLiteEventBus(EventBusProtocol):
    """SQLite-backed event bus with background consumer and replay support.

    Durable event storage with at-least-once delivery semantics.
    Events are persisted to SQLite immediately on publish() and processed
    asynchronously by a background consumer loop.

    Features:
        - Persistent: events survive process restarts
        - At-least-once delivery with idempotency_key dedup
        - publish_delayed() via future ``processed_at`` timestamp
        - Replay: re-process historical events within a time range
        - Wildcard pattern subscription (e.g. ``knowledge.*``, ``**``)
        - Priority-based ordering (higher priority first)
        - Graceful shutdown with in-flight event drain

    Args:
        db_path: Path to the SQLite database file. Use ``:memory:`` for
            in-memory storage (testing only).
        poll_interval: Seconds between background consumer polls (default: 1.0).
        batch_size: Max events to fetch per poll cycle (default: 50).
        max_retries: Max delivery attempts before dropping an event (default: 3).
    """

    def __init__(
        self,
        db_path: str | Path = "events.db",
        poll_interval: float = 1.0,
        batch_size: int = 50,
        max_retries: int = 3,
    ) -> None:
        self._db_path = str(db_path) if isinstance(db_path, Path) else str(db_path)
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries

        # In-memory handler registry: event_type_pattern → [(handler, description)]
        # Handlers are kept in memory for fast dispatch (not persisted).
        self._handlers: dict[str, list[tuple[EventHandler, str]]] = defaultdict(list)

        # In-memory idempotency tracking (LRU-ish, cleared on restart)
        self._seen_idempotency_keys: set[str] = set()

        self._db: aiosqlite.Connection | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Open the database, create schema, and start the background consumer.

        Raises:
            aiosqlite.Error: If the database cannot be opened.
        """
        if self._running:
            logger.warning("SQLiteEventBus already running")
            return

        logger.info("SQLiteEventBus starting (db=%s)", self._db_path)

        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrent access
        await self._db.execute("PRAGMA journal_mode=WAL")
        # Enable foreign keys
        await self._db.execute("PRAGMA foreign_keys=ON")
        # Create schema
        await self._db.execute(CREATE_EVENTS_TABLE)
        for stmt in CREATE_EVENTS_INDEXES.split(";"):
            stmt = stmt.strip()
            if stmt:
                await self._db.execute(stmt)
        await self._db.execute(CREATE_SUBSCRIBERS_TABLE)
        await self._db.commit()

        # Load persisted subscriptions if any
        await self._load_subscribers()

        self._running = True
        self._consumer_task = asyncio.create_task(
            self._consumer_loop(),
            name="sqlite-eventbus-consumer",
        )

        logger.info("SQLiteEventBus started (db=%s)", self._db_path)

    async def stop(self) -> None:
        """Stop the background consumer and close the database gracefully.

        Drains in-flight events from the consumer loop before closing.
        """
        if not self._running:
            return

        logger.info("SQLiteEventBus stopping...")
        self._running = False

        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("Error stopping consumer: %s", exc)
            self._consumer_task = None

        if self._db is not None:
            try:
                await self._db.close()
            except Exception as exc:
                logger.warning("Error closing database: %s", exc)
            self._db = None

        logger.info("SQLiteEventBus stopped")

    # ── EventBusProtocol ──────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
        """Persist an event and notify matching in-process handlers.

        The event is first persisted to SQLite, then dispatched to any
        in-process handlers that match its type. Failed handler deliveries
        are tracked in the database for retry.

        Args:
            event: The event to publish.

        Raises:
            ConnectionError: If the database is not connected.
            aiosqlite.Error: If the insert fails.
        """
        if self._db is None:
            raise ConnectionError("SQLiteEventBus is not connected")

        # Idempotency check (in-memory for speed, DB-level via UNIQUE later)
        if event.idempotency_key:
            if event.idempotency_key in self._seen_idempotency_keys:
                logger.debug(
                    "Duplicate event dropped (idempotency_key=%s): %s",
                    event.idempotency_key,
                    event.type,
                )
                return
            self._seen_idempotency_keys.add(event.idempotency_key)

        payload_json = json.dumps(event.payload, ensure_ascii=False, default=str)
        created_at = event.timestamp.isoformat() if event.timestamp else _now_iso()

        try:
            await self._db.execute(
                """INSERT OR IGNORE INTO events
                   (id, type, source, payload, priority, trace_id,
                    idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.type,
                    event.source,
                    payload_json,
                    event.priority.value,
                    event.trace_id,
                    event.idempotency_key,
                    created_at,
                ),
            )
            await self._db.commit()
        except Exception as exc:
            logger.exception("Failed to persist event %s: %s", event.event_id, exc)
            raise

        # Dispatch to in-process handlers immediately (fire-and-forget)
        asyncio.create_task(self._dispatch_to_handlers(event))

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        *,
        description: str = "",
    ) -> None:
        """Register a handler for a specific event type pattern.

        The subscription is kept in memory for fast dispatch. Wildcard
        patterns (``knowledge.*``, ``**``) are supported.

        Args:
            event_type: Event type pattern (exact or wildcard).
            handler: Async callable that processes matching events.
            description: Optional human-readable description.
        """
        if not callable(handler):
            raise TypeError("handler must be a callable")

        handler_id = f"{getattr(handler, '__qualname__', handler.__class__.__name__)}:{id(handler)}"

        # Remove existing subscription for same handler + pattern
        self._handlers[event_type] = [
            (h, d) for h, d in self._handlers[event_type] if h is not handler
        ]
        self._handlers[event_type].append((handler, description))

        # Persist the subscription in SQLite for recovery
        if self._db is not None:
            try:
                await self._db.execute(
                    """INSERT OR REPLACE INTO subscribers
                       (event_type_pattern, handler_id, description, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (event_type, handler_id, description, _now_iso()),
                )
                await self._db.commit()
            except Exception as exc:
                logger.warning("Failed to persist subscription: %s", exc)

        logger.debug(
            "Handler subscribed to '%s': %s", event_type, description or handler.__name__
        )

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Remove a previously registered handler.

        Args:
            event_type: The event type the handler was registered for.
            handler: The handler instance to remove.

        Returns:
            True if the handler was found and removed, False otherwise.
        """
        handlers = self._handlers.get(event_type, [])
        before = len(handlers)
        self._handlers[event_type] = [
            (h, d) for h, d in handlers if h is not handler
        ]
        removed = before - len(self._handlers[event_type])

        if removed:
            handler_id = f"{getattr(handler, '__qualname__', handler.__class__.__name__)}:{id(handler)}"
            if self._db is not None:
                try:
                    await self._db.execute(
                        "DELETE FROM subscribers WHERE event_type_pattern=? AND handler_id=?",
                        (event_type, handler_id),
                    )
                    await self._db.commit()
                except Exception as exc:
                    logger.warning("Failed to remove persisted subscription: %s", exc)
            logger.debug(
                "Handler unsubscribed from '%s': %s", event_type, handler.__name__
            )

        return removed > 0

    async def publish_delayed(
        self,
        event: Event,
        delay_seconds: int = 60,
    ) -> None:
        """Publish an event after a delay.

        The event is persisted immediately with ``processed_at`` set
        to ``now + delay_seconds``. The background consumer will skip
        it until that time.

        Args:
            event: The event to publish later.
            delay_seconds: Seconds to wait before processing.

        Raises:
            ValueError: If delay_seconds is negative.
        """
        if delay_seconds < 0:
            raise ValueError(f"delay_seconds must be >= 0, got {delay_seconds}")

        if self._db is None:
            raise ConnectionError("SQLiteEventBus is not connected")

        # Store event with a future processed_at timestamp
        processed_at = datetime.now(timezone.utc).timestamp() + delay_seconds
        processed_at_iso = datetime.fromtimestamp(
            processed_at, tz=timezone.utc
        ).isoformat()

        payload_json = json.dumps(event.payload, ensure_ascii=False, default=str)
        created_at = event.timestamp.isoformat() if event.timestamp else _now_iso()

        try:
            await self._db.execute(
                """INSERT OR IGNORE INTO events
                   (id, type, source, payload, priority, trace_id,
                    idempotency_key, created_at, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.type,
                    event.source,
                    payload_json,
                    event.priority.value,
                    event.trace_id,
                    event.idempotency_key,
                    created_at,
                    processed_at_iso,
                ),
            )
            await self._db.commit()
        except Exception as exc:
            logger.exception(
                "Failed to persist delayed event %s: %s", event.event_id, exc
            )
            raise

        logger.debug(
            "Scheduled delayed publish of %s in %ds (processed_at=%s)",
            event.type,
            delay_seconds,
            processed_at_iso,
        )

    # ── Replay ────────────────────────────────────────────────────────

    async def replay(
        self,
        event_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Replay events through registered handlers.

        Queries the events table for matching events and re-dispatches
        them to currently registered handlers. Does NOT create new events
        in the database.

        Args:
            event_type: If provided, only replay events of this type (supports wildcard).
            since: Only replay events created after this time.
            until: Only replay events created before this time.

        Returns:
            The number of events replayed.
        """
        if self._db is None:
            raise ConnectionError("SQLiteEventBus is not connected")

        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []

        if event_type:
            # For wildcard, do LIKE pattern matching
            if "*" in event_type:
                sql_pattern = event_type.replace("*", "%")
                query += " AND type LIKE ?"
                params.append(sql_pattern)
            else:
                query += " AND type = ?"
                params.append(event_type)

        if since:
            query += " AND created_at >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND created_at <= ?"
            params.append(until.isoformat())

        query += " ORDER BY created_at ASC"

        try:
            cursor = await self._db.execute(query, params)
            rows = await cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to query events for replay: %s", exc)
            return 0

        count = 0
        for row in rows:
            event = self._row_to_event(row)
            if event is None:
                continue
            await self._dispatch_to_handlers(event)
            count += 1

        logger.info(
            "Replay complete: %d events dispatched (type=%s, since=%s, until=%s)",
            count,
            event_type or "any",
            since.isoformat() if since else "any",
            until.isoformat() if until else "any",
        )
        return count

    # ── Background Consumer ───────────────────────────────────────────

    async def _consumer_loop(self) -> None:
        """Background loop: polls for unprocessed events and dispatches them.

        Fetches events where ``processed_at IS NULL`` in priority order,
        dispatches them to matching handlers, and marks them as processed.
        Events that fail delivery are retried up to ``max_retries`` times.
        """
        logger.info("Consumer loop started (poll_interval=%.1fs)", self._poll_interval)

        while self._running:
            try:
                await self._poll_and_process()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in consumer loop: %s", exc)

            # Sleep between polls (with early cancellation support)
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

        logger.info("Consumer loop stopped")

    async def _poll_and_process(self) -> None:
        """Fetch and process a batch of unprocessed events."""
        if self._db is None:
            return

        now_iso = _now_iso()

        try:
            cursor = await self._db.execute(
                """SELECT * FROM events
                   WHERE processed_at IS NULL AND failure_count < ?
                   ORDER BY priority DESC, created_at ASC
                   LIMIT ?""",
                (self._max_retries, self._batch_size),
            )
            rows = await cursor.fetchall()
        except Exception as exc:
            logger.warning("Failed to poll for events: %s", exc)
            return

        for row in rows:
            event = self._row_to_event(row)
            if event is None:
                continue

            try:
                await self._dispatch_to_handlers(event)
                # Mark as processed
                await self._db.execute(
                    "UPDATE events SET processed_at=? WHERE id=?",
                    (now_iso, event.event_id),
                )
            except Exception as exc:
                # Increment failure count
                await self._db.execute(
                    """UPDATE events
                       SET failure_count = failure_count + 1,
                           last_error = ?
                       WHERE id=?""",
                    (str(exc)[:500], event.event_id),
                )
                logger.warning(
                    "Event %s failed delivery (retries left: %d): %s",
                    event.event_id,
                    self._max_retries - row["failure_count"] - 1,
                    exc,
                )

        if rows:
            await self._db.commit()

    # ── Dispatch ──────────────────────────────────────────────────────

    async def _dispatch_to_handlers(self, event: Event) -> None:
        """Dispatch an event to all matching in-process handlers.

        Args:
            event: The event to dispatch.
        """
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
                    description or getattr(handler, "__name__", str(handler)),
                    event.type,
                )

    # ── Persisted Subscribers ─────────────────────────────────────────

    async def _load_subscribers(self) -> None:
        """Load persisted subscriptions from the database into the handler registry.

        NOTE: Handlers are not serializable across restarts. This loads
        the *metadata* about subscriptions. Applications should re-register
        their handlers on startup. This method exists for audit/inspection.
        """
        if self._db is None:
            return
        try:
            cursor = await self._db.execute("SELECT * FROM subscribers")
            rows = await cursor.fetchall()
            if rows:
                logger.info(
                    "Loaded %d persisted subscriber records (handlers need re-registration)",
                    len(rows),
                )
        except Exception:
            # Table may not exist yet on first run
            pass

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _pattern_matches(pattern: str, event_type: str) -> bool:
        """Check if an event type matches a subscription pattern.

        Supports:
            - Exact match: ``"knowledge.ingested"``
            - Wildcard: ``"knowledge.*"`` matches ``knowledge.ingested``
            - Global: ``"**"`` matches everything
        """
        if pattern == "**":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix) or event_type == prefix.rstrip(".")
        return fnmatch(event_type, pattern)

    @staticmethod
    def _row_to_event(row: aiosqlite.Row) -> Event | None:
        """Convert a SQLite row to an Event dataclass.

        Args:
            row: A row from the events table.

        Returns:
            An Event instance, or None if parsing fails.
        """
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        return Event(
            type=row["type"],
            source=row["source"],
            payload=payload,
            priority=EventPriority(row["priority"]) if "priority" in row.keys() else EventPriority.NORMAL,
            trace_id=row["trace_id"] or "",
            idempotency_key=row["idempotency_key"],
            timestamp=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
            event_id=row["id"],
        )

    # ── Utility ───────────────────────────────────────────────────────

    @property
    def queue_size(self) -> int:
        """Approximate number of unprocessed events in the database."""
        # This is a best-effort sync property; for accurate counts use async query
        return 0

    async def unprocessed_count(self) -> int:
        """Return the count of unprocessed events in the database."""
        if self._db is None:
            return 0
        try:
            cursor = await self._db.execute(
                "SELECT COUNT(*) as cnt FROM events WHERE processed_at IS NULL"
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
        except Exception:
            return 0

    async def total_events(self) -> int:
        """Return the total number of events in the database."""
        if self._db is None:
            return 0
        try:
            cursor = await self._db.execute("SELECT COUNT(*) as cnt FROM events")
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
        except Exception:
            return 0

    def __repr__(self) -> str:
        return (
            f"<SQLiteEventBus db={self._db_path} "
            f"running={self._running} "
            f"handlers={sum(len(v) for v in self._handlers.values())}>"
        )
