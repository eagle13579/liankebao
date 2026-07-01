"""SQLAlchemyKnowledgeRepository — KnowledgeRepositoryProtocol adapter backed by SQLAlchemy async session.

Wraps AsyncSession to provide CRUD + semantic search + weight queries
for the Gaia Knowledge system. Uses SQLAlchemy 2.0 style (select(), not query).

Phase 0: search_semantic() falls back to keyword search (LIKE) since
vector search is not yet deployed.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.gaia import GaiaKnowledge, GaiaModelWeights
from app.repositories.interfaces import KnowledgeRepositoryProtocol, QuerySpec

logger = logging.getLogger(__name__)


class SQLAlchemyKnowledgeRepository(KnowledgeRepositoryProtocol):
    """Knowledge repository backed by SQLAlchemy async session.

    Wraps an existing AsyncSession to fulfil the KnowledgeRepositoryProtocol.
    Session lifecycle (create/commit/rollback) is managed externally — the
    caller (or a unit-of-work / dependency injection container) is responsible
    for providing a session that is already bound to a transaction context.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an existing SQLAlchemy AsyncSession.

        Args:
            session: An async SQLAlchemy session (e.g. from FastAPI dependency).
        """
        self._session = session

    # ── Internal helpers ──────────────────────────────────────────────

    def _apply_filters(self, stmt: Select, filters: dict[str, Any]) -> Select:
        """Apply QuerySpec filters to a select statement.

        Supports:
            field=value           → equality
            field__contains=val   → LIKE '%val%'
            field__gt=val         → >
            field__gte=val        → >=
            field__lt=val         → <
            field__lte=val        → <=
            field__in=[...]       → IN (...)
            field__ne=val         → !=
        """
        conditions: list[Any] = []
        for field, value in filters.items():
            if "__" in field:
                field_name, op = field.rsplit("__", 1)
                column = getattr(GaiaKnowledge, field_name, None)
                if column is None:
                    logger.warning("Unknown filter field: %s", field)
                    continue
                if op == "contains":
                    conditions.append(column.ilike(f"%{value}%"))
                elif op == "gt":
                    conditions.append(column > value)
                elif op == "gte":
                    conditions.append(column >= value)
                elif op == "lt":
                    conditions.append(column < value)
                elif op == "lte":
                    conditions.append(column <= value)
                elif op == "in":
                    conditions.append(column.in_(value))
                elif op == "ne":
                    conditions.append(column != value)
                else:
                    logger.warning("Unknown filter operator: %s", op)
            else:
                column = getattr(GaiaKnowledge, field, None)
                if column is None:
                    logger.warning("Unknown filter field: %s", field)
                    continue
                conditions.append(column == value)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        return stmt

    def _apply_ordering(self, stmt: Select, order_by: list[str]) -> Select:
        """Apply order_by clauses.

        Prefix with ``-`` for descending, e.g. ``"-created_at"``.
        """
        for field_spec in order_by:
            if field_spec.startswith("-"):
                column = getattr(GaiaKnowledge, field_spec[1:], None)
                if column is not None:
                    stmt = stmt.order_by(column.desc())
            else:
                column = getattr(GaiaKnowledge, field_spec, None)
                if column is not None:
                    stmt = stmt.order_by(column.asc())
        return stmt

    def _spec_to_select(self, spec: QuerySpec) -> Select:
        """Build a SELECT statement from a QuerySpec."""
        stmt = select(GaiaKnowledge)
        stmt = self._apply_filters(stmt, spec.filters)
        stmt = self._apply_ordering(stmt, spec.order_by)
        stmt = stmt.offset(spec.offset).limit(spec.limit)
        return stmt

    async def _scalar(self, stmt: Select) -> Any | None:
        """Fetch a single scalar result."""
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _scalars(self, stmt: Select) -> list[Any]:
        """Fetch multiple scalar results."""
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── CRUD ──────────────────────────────────────────────────────────

    async def get(self, key: int) -> Any | None:
        """Fetch a knowledge entry by its integer primary key."""
        stmt = select(GaiaKnowledge).where(GaiaKnowledge.id == key)
        return await self._scalar(stmt)

    async def find(self, spec: QuerySpec) -> list[Any]:
        """Find knowledge entries matching the query specification."""
        stmt = self._spec_to_select(spec)
        return await self._scalars(stmt)

    async def count(self, spec: QuerySpec | None = None) -> int:
        """Count knowledge entries matching optional filters."""
        stmt = select(func.count(GaiaKnowledge.id))
        if spec is not None and spec.filters:
            stmt = self._apply_filters(stmt, spec.filters)
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def save(self, entity: Any) -> Any:
        """Persist a knowledge entry (create or update).

        If the entity has an ``id`` that already exists in the database it
        will be merged (update); otherwise it is inserted (create).
        """
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, key: int) -> bool:
        """Delete a knowledge entry by its integer ID.

        Returns True if a row was deleted, False if not found.
        """
        entity = await self.get(key)
        if entity is None:
            return False
        await self._session.delete(entity)
        await self._session.flush()
        return True

    # ── Domain-specific ───────────────────────────────────────────────

    async def search_semantic(
        self,
        query: str,
        top_k: int = 10,
        confidence_min: float = 0.0,
    ) -> list[Any]:
        """Semantic search via keyword fallback (LIKE on title + content).

        Phase 0 implementation: performs a simple keyword search across
        ``title`` and ``content`` columns using SQL ILIKE. Results are
        ordered by ``impact_score`` descending and filtered by
        ``confidence >= confidence_min``.

        Later phases will replace this with a proper vector-similarity search.
        """
        if not query.strip():
            return []

        like_pattern = f"%{query}%"
        stmt = (
            select(GaiaKnowledge)
            .where(
                and_(
                    or_(
                        GaiaKnowledge.title.ilike(like_pattern),
                        GaiaKnowledge.content.ilike(like_pattern),
                    ),
                    GaiaKnowledge.confidence >= confidence_min,
                    GaiaKnowledge.is_active.is_(True),
                )
            )
            .order_by(GaiaKnowledge.impact_score.desc())
            .limit(top_k)
        )
        return await self._scalars(stmt)

    async def get_active_weights(self) -> dict[str, Any]:
        """Retrieve the currently active model weights across all modules.

        Queries the ``gaia_model_weights`` table for rows where
        ``is_active`` is True and returns a dict mapping module name to
        its weight configuration.

        Returns:
            Dict like ``{"recommendation": {...}, "search": {...}, ...}``.
        """
        stmt = (
            select(GaiaModelWeights)
            .where(GaiaModelWeights.is_active.is_(True))
        )
        rows = await self._scalars(stmt)
        result: dict[str, Any] = {}
        for row in rows:
            result[row.module] = {
                "weights": row.weights,
                "version": row.version,
                "description": row.description,
                "training_run_id": row.training_run_id,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        return result
