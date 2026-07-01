"""盖娅进化大脑 — 完整测试套件

Tests cover:
  1. GaiaKnowledge model creation and field validation
  2. GaiaEvolutionBrain.ingest_knowledge — basic knowledge ingestion
  3. GaiaEvolutionBrain.ingest_feedback — extreme ratings → knowledge, middling → skip
  4. GaiaEvolutionBrain.get_evolved_weights — returns None when no weights exist
  5. GaiaEvolutionBrain.process_evolution_cycle — end-to-end evolution
  6. GaiaEvolutionBrain.get_knowledge_base — semantic / keyword retrieval
  7. GaiaTrainingRun model creation and lifecycle
  8. GaiaModelWeights creation and update
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.gaia import (
    GaiaKnowledge,
    GaiaEvolutionEvent,
    GaiaTrainingRun,
    GaiaModelWeights,
)


# ══════════════════════════════════════════════════════════════════════
# 1. GaiaKnowledge model
# ══════════════════════════════════════════════════════════════════════


class TestGaiaKnowledgeModel:
    """Model creation, field defaults, and __repr__."""

    async def test_create_minimal(self, test_db):
        """Create a GaiaKnowledge with only required fields."""
        k = GaiaKnowledge(
            source="retrospective",
            knowledge_type="insight",
            title="测试知识",
            content="这是一个测试知识条目",
        )
        test_db.add(k)
        await test_db.commit()
        await test_db.refresh(k)

        assert k.id is not None
        assert k.id > 0
        assert k.source == "retrospective"
        assert k.knowledge_type == "insight"
        assert k.title == "测试知识"
        assert k.content == "这是一个测试知识条目"
        assert k.tags is None          # default
        assert k.confidence == 1.0     # default
        assert k.impact_score == 0.0   # default
        assert k.is_active is True     # default
        assert k.vector_embedded is False  # default
        assert k.created_at is not None
        assert k.updated_at is not None

    async def test_create_with_all_fields(self, test_db):
        """Create a GaiaKnowledge with all fields populated."""
        k = GaiaKnowledge(
            source="ab_test",
            source_id="exp_042",
            knowledge_type="optimization",
            title="A/B测试优化",
            content="B版本转化率提升12%",
            tags=["转化率", "UI优化"],
            confidence=0.92,
            impact_score=0.85,
            is_active=True,
            vector_embedded=True,
        )
        test_db.add(k)
        await test_db.commit()
        await test_db.refresh(k)

        assert k.source == "ab_test"
        assert k.source_id == "exp_042"
        assert k.knowledge_type == "optimization"
        assert k.tags == ["转化率", "UI优化"]
        assert k.confidence == 0.92
        assert k.impact_score == 0.85
        assert k.vector_embedded is True

    async def test_repr(self, test_db):
        """__repr__ returns a meaningful string."""
        k = GaiaKnowledge(
            source="system",
            knowledge_type="rule",
            title="repr测试",
            content="x",
            confidence=0.75,
        )
        test_db.add(k)
        await test_db.commit()
        await test_db.refresh(k)

        r = repr(k)
        assert "GaiaKnowledge" in r
        assert str(k.id) in r
        assert "system" in r
        assert "rule" in r

    async def test_default_confidence_clamped(self, test_db):
        """confidence defaults to 1.0 when not specified."""
        k = GaiaKnowledge(
            source="manual",
            knowledge_type="insight",
            title="默认置信度",
            content="默认值测试",
        )
        test_db.add(k)
        await test_db.commit()
        await test_db.refresh(k)
        assert k.confidence == 1.0

    async def test_indexes_created(self, test_db):
        """Verify __table_args__ indexes exist on gaia_knowledge."""
        from sqlalchemy import inspect

        def _check(conn):
            insp = inspect(conn)
            indices = {ix["name"] for ix in insp.get_indexes("gaia_knowledge")}
            assert "idx_gaia_knowledge_source" in indices
            assert "idx_gaia_knowledge_type" in indices
            assert "idx_gaia_knowledge_active" in indices

        conn = await test_db.connection()
        await conn.run_sync(_check)


# ══════════════════════════════════════════════════════════════════════
# 2. GaiaEvolutionBrain — ingest_knowledge
# ══════════════════════════════════════════════════════════════════════

# Patch the embedding backend so tests don't require real vector infra
@pytest_asyncio.fixture
async def brain():
    from app.ai.gaia_evolution_brain import GaiaEvolutionBrain
    with (
        patch("app.ai.gaia_evolution_brain.get_embedding_backend") as mock_backend,
        patch("app.ai.gaia_evolution_brain.get_vector_index") as mock_vindex,
    ):
        mock_backend.return_value.name = "mock"
        mock_backend.return_value.dimension = 128
        mock_vindex.return_value.size = 0
        mock_vindex.return_value.search = MagicMock(return_value=[])
        instance = GaiaEvolutionBrain()
        yield instance


class TestIngestKnowledge:
    """GaiaEvolutionBrain.ingest_knowledge — basic ingestion."""

    async def test_ingest_basic(self, test_db, brain):
        """A knowledge entry is created and an evolution event is recorded."""
        k = await brain.ingest_knowledge(
            db=test_db,
            source="retrospective",
            source_id="retro_001",
            knowledge_type="pattern",
            title="复盘提炼的模式",
            content="每次复盘后应该提炼3个可复用的原则",
            tags=["复盘", "原则"],
            confidence=0.9,
        )
        await test_db.commit()

        assert k.id is not None
        assert k.source == "retrospective"
        assert k.source_id == "retro_001"
        assert k.knowledge_type == "pattern"
        assert k.title == "复盘提炼的模式"
        assert "3个可复用的原则" in k.content
        assert k.tags == ["复盘", "原则"]
        assert k.confidence == 0.9
        assert k.impact_score == 0.9  # mirrors confidence
        assert k.is_active is True
        assert k.vector_embedded is False

        # An evolution event should have been recorded
        event = await test_db.execute(
            __import__("sqlalchemy").select(GaiaEvolutionEvent).where(
                GaiaEvolutionEvent.event_type == "knowledge_ingested"
            )
        )
        ev = event.scalars().first()
        assert ev is not None
        assert ev.reference_type == "knowledge"
        assert ev.reference_id == k.id

    async def test_ingest_without_tags(self, test_db, brain):
        """Tags can be omitted."""
        k = await brain.ingest_knowledge(
            db=test_db,
            source="system",
            source_id="auto_001",
            knowledge_type="rule",
            title="无标签测试",
            content="这条知识没有标签",
        )
        await test_db.commit()
        assert k.tags is None or k.tags == []
        assert k.id is not None

    async def test_ingest_confidence_clamping(self, test_db, brain):
        """Confidence is clamped to [0.0, 1.0]."""
        k_high = await brain.ingest_knowledge(
            db=test_db, source="manual", source_id="t1",
            knowledge_type="insight", title="过高", content="x", confidence=5.0,
        )
        assert k_high.confidence == 1.0

        k_low = await brain.ingest_knowledge(
            db=test_db, source="manual", source_id="t2",
            knowledge_type="insight", title="过低", content="x", confidence=-0.5,
        )
        assert k_low.confidence == 0.0

    async def test_ingest_source_id_is_optional(self, test_db, brain):
        """source_id defaults to empty string."""
        k = await brain.ingest_knowledge(
            db=test_db, source="manual",
            source_id="",
            knowledge_type="insight",
            title="无来源ID", content="测试",
        )
        await test_db.commit()
        assert k.source_id == ""
        assert k.id is not None


# ══════════════════════════════════════════════════════════════════════
# 3. GaiaEvolutionBrain — ingest_feedback
# ══════════════════════════════════════════════════════════════════════


class TestIngestFeedback:
    """Extreme ratings → knowledge; middling ratings → skip."""

    async def test_extreme_low_rating_creates_knowledge(self, test_db, brain):
        """Rating <= 2.0 creates a knowledge entry."""
        k = await brain.ingest_feedback(
            db=test_db,
            user_id=1,
            item_id=100,
            rating=1.5,
            source="recommendation",
            comment="完全不相关的内容",
        )
        await test_db.commit()
        assert k is not None
        assert k.source == "feedback"
        assert "1.5" in k.content or "完全不相关" in k.content

    async def test_extreme_high_rating_creates_knowledge(self, test_db, brain):
        """Rating >= 4.0 creates a knowledge entry."""
        k = await brain.ingest_feedback(
            db=test_db,
            user_id=2,
            item_id=200,
            rating=5.0,
            source="recommendation",
            comment="非常精准的推荐!",
        )
        await test_db.commit()
        assert k is not None
        assert "5.0" in k.content or "非常精准" in k.content

    async def test_mid_rating_returns_none(self, test_db, brain):
        """Rating between 2.0 and 4.0 does NOT create knowledge."""
        k = await brain.ingest_feedback(
            db=test_db,
            user_id=3,
            item_id=300,
            rating=3.0,
            source="recommendation",
        )
        await test_db.commit()
        assert k is None

        # But an event should still be recorded
        event = await test_db.execute(
            __import__("sqlalchemy").select(GaiaEvolutionEvent).where(
                GaiaEvolutionEvent.event_type == "feedback_recorded"
            )
        )
        ev = event.scalars().first()
        assert ev is not None

    async def test_feedback_without_comment(self, test_db, brain):
        """Feedback can work without a comment."""
        k = await brain.ingest_feedback(
            db=test_db,
            user_id=4,
            item_id=400,
            rating=1.0,
            source="recommendation",
        )
        await test_db.commit()
        assert k is not None
        assert isinstance(k.content, str)


# ══════════════════════════════════════════════════════════════════════
# 4. GaiaEvolutionBrain — get_evolved_weights (returns None initially)
# ══════════════════════════════════════════════════════════════════════


class TestGetEvolvedWeights:
    """Weight queries on empty / populated DB."""

    async def test_returns_none_when_no_weights(self, test_db, brain):
        """No weights exist for any module → returns None."""
        result = await brain.get_evolved_weights(test_db, "recommendation")
        assert result is None

        result = await brain.get_evolved_weights(test_db, "search")
        assert result is None

    async def test_returns_weights_after_insert(self, test_db, brain):
        """After inserting a model weight record, get_evolved_weights returns it."""
        w = GaiaModelWeights(
            module="recommendation",
            weights={"alpha": 0.7, "beta": 0.3},
            version="1.0.0",
            description="初始权重",
            is_active=True,
        )
        test_db.add(w)
        await test_db.commit()

        result = await brain.get_evolved_weights(test_db, "recommendation")
        assert result is not None
        assert result["module"] == "recommendation"
        assert result["weights"]["alpha"] == 0.7
        assert result["version"] == "1.0.0"

    async def test_returns_latest_active_version(self, test_db, brain):
        """Only active weights, latest first."""
        w1 = GaiaModelWeights(
            module="recommendation",
            weights={"v": 1},
            version="1.0.0",
            is_active=False,
        )
        w2 = GaiaModelWeights(
            module="recommendation",
            weights={"v": 2},
            version="2.0.0",
            is_active=True,
        )
        test_db.add_all([w1, w2])
        await test_db.commit()

        result = await brain.get_evolved_weights(test_db, "recommendation")
        assert result["version"] == "2.0.0"
        assert result["weights"]["v"] == 2

    async def test_different_modules_isolated(self, test_db, brain):
        """Weights for one module don't leak into another."""
        w = GaiaModelWeights(
            module="search",
            weights={"threshold": 0.8},
            version="1.0.0",
            is_active=True,
        )
        test_db.add(w)
        await test_db.commit()

        rec = await brain.get_evolved_weights(test_db, "recommendation")
        assert rec is None

        sea = await brain.get_evolved_weights(test_db, "search")
        assert sea is not None


# ══════════════════════════════════════════════════════════════════════
# 5. GaiaEvolutionBrain — process_evolution_cycle
# ══════════════════════════════════════════════════════════════════════


class TestProcessEvolutionCycle:
    """Full evolution cycle with mocked vector internals."""

    async def test_cycle_with_pending_knowledge(self, test_db, brain):
        """Evolution cycle processes pending knowledge and creates a training run."""
        # Insert some knowledge that needs embedding
        k1 = GaiaKnowledge(
            source="retrospective", source_id="r1",
            knowledge_type="pattern", title="原则1", content="第一个原则",
            is_active=True, vector_embedded=False,
        )
        k2 = GaiaKnowledge(
            source="retrospective", source_id="r2",
            knowledge_type="insight", title="洞察1", content="重要洞察",
            is_active=True, vector_embedded=False,
        )
        test_db.add_all([k1, k2])
        await test_db.commit()

        # Run evolution
        result = await brain.process_evolution_cycle(test_db, trigger="manual")
        await test_db.commit()

        assert result["status"] == "completed"
        assert result["knowledge_count"] == 2
        assert result["training_run_id"] is not None

        # A GaiaTrainingRun should have been created
        run = await test_db.get(GaiaTrainingRun, result["training_run_id"])
        assert run is not None
        assert run.status == "completed"
        assert run.knowledge_count == 2

    async def test_cycle_without_knowledge(self, test_db, brain):
        """Evolution cycle with no pending knowledge still completes."""
        result = await brain.process_evolution_cycle(test_db, trigger="manual")
        await test_db.commit()

        assert result["status"] == "completed"
        assert result["knowledge_count"] == 0

    async def test_cycle_trigger_variants(self, test_db, brain):
        """Different triggers are recorded properly."""
        for trigger in ("manual", "scheduled", "automatic", "api"):
            result = await brain.process_evolution_cycle(test_db, trigger=trigger)
            await test_db.commit()
            assert result["status"] == "completed", f"Failed for trigger={trigger}"

    async def test_cycle_records_events(self, test_db, brain):
        """Evolution cycle creates start and completion events."""
        await brain.process_evolution_cycle(test_db, trigger="manual")
        await test_db.commit()

        events = await test_db.execute(
            __import__("sqlalchemy").select(GaiaEvolutionEvent).where(
                GaiaEvolutionEvent.event_type.in_(["cycle_started", "cycle_completed"])
            )
        )
        ev_list = events.scalars().all()
        types = {e.event_type for e in ev_list}
        assert "cycle_started" in types
        assert "cycle_completed" in types


# ══════════════════════════════════════════════════════════════════════
# 6. GaiaEvolutionBrain — get_knowledge_base (semantic / keyword search)
# ══════════════════════════════════════════════════════════════════════


class TestKnowledgeBase:
    """Semantic and keyword-based knowledge retrieval."""

    async def test_keyword_search_returns_matches(self, test_db, brain):
        """Database fallback search returns matching knowledge."""
        k = GaiaKnowledge(
            source="manual", knowledge_type="insight",
            title="关于用户增长",
            content="用户增长的关键因素是口碑传播和产品体验",
            is_active=True, confidence=0.9, impact_score=0.8,
            vector_embedded=False,
        )
        test_db.add(k)
        await test_db.commit()

        results = await brain.get_knowledge_base(
            test_db, query="用户增长", limit=10,
        )
        assert len(results) >= 1
        assert results[0]["title"] == "关于用户增长"

    async def test_keyword_search_empty_db(self, test_db, brain):
        """Empty knowledge base returns empty list."""
        results = await brain.get_knowledge_base(
            test_db, query="anything", limit=10,
        )
        assert results == []

    async def test_keyword_search_with_filters(self, test_db, brain):
        """Filter by knowledge_type and source."""
        test_db.add_all([
            GaiaKnowledge(
                source="retrospective", knowledge_type="pattern",
                title="模式A", content="模式A内容",
                is_active=True, confidence=0.9,
            ),
            GaiaKnowledge(
                source="feedback", knowledge_type="preference",
                title="偏好B", content="模式A内容",
                is_active=True, confidence=0.8,
            ),
        ])
        await test_db.commit()

        # Filter by type
        results = await brain.get_knowledge_base(
            test_db, query="模式A", knowledge_type="pattern",
        )
        assert len(results) == 1
        assert results[0]["knowledge_type"] == "pattern"

        # Filter by source
        results = await brain.get_knowledge_base(
            test_db, query="模式A", source="feedback",
        )
        assert len(results) == 1
        assert results[0]["source"] == "feedback"

    async def test_min_confidence_filter(self, test_db, brain):
        """min_confidence excludes low-confidence entries."""
        test_db.add_all([
            GaiaKnowledge(
                source="manual", knowledge_type="insight",
                title="高置信度", content="高质量知识",
                is_active=True, confidence=0.95,
            ),
            GaiaKnowledge(
                source="manual", knowledge_type="insight",
                title="低置信度", content="低质量知识",
                is_active=True, confidence=0.3,
            ),
        ])
        await test_db.commit()

        results = await brain.get_knowledge_base(
            test_db, query="知识", min_confidence=0.8,
        )
        titles = {r["title"] for r in results}
        assert "高置信度" in titles
        assert "低置信度" not in titles

    async def test_inactive_excluded(self, test_db, brain):
        """Inactive (soft-deleted) knowledge is excluded."""
        test_db.add(
            GaiaKnowledge(
                source="manual", knowledge_type="insight",
                title="已删除", content="已删除知识",
                is_active=False, confidence=0.9,
            )
        )
        await test_db.commit()

        results = await brain.get_knowledge_base(
            test_db, query="已删除", limit=10,
        )
        assert len(results) == 0


# ══════════════════════════════════════════════════════════════════════
# 7. GaiaTrainingRun model
# ══════════════════════════════════════════════════════════════════════


class TestGaiaTrainingRunModel:
    """Training run creation and lifecycle."""

    async def test_create_pending_run(self, test_db):
        """Create a training run with default status."""
        run = GaiaTrainingRun(
            trigger="manual",
            knowledge_count=5,
            feedback_count=3,
            weights_count=10,
            vector_index_size=100,
        )
        test_db.add(run)
        await test_db.commit()
        await test_db.refresh(run)

        assert run.id is not None
        assert run.status == "pending"
        assert run.trigger == "manual"
        assert run.knowledge_count == 5
        assert run.duration_ms == 0
        assert run.started_at is None
        assert run.completed_at is None

    async def test_complete_run(self, test_db):
        """Mark a run as completed with timing and metrics."""
        run = GaiaTrainingRun(
            status="running",
            trigger="scheduled",
            knowledge_count=50,
            feedback_count=20,
            weights_count=15,
            vector_index_size=500,
            duration_ms=0,
            started_at=datetime.now(timezone.utc),
        )
        test_db.add(run)
        await test_db.commit()

        # Simulate completion
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = 12345
        run.metrics = {"accuracy": 0.95, "coverage": 0.82}
        await test_db.commit()
        await test_db.refresh(run)

        assert run.status == "completed"
        assert run.duration_ms == 12345
        assert run.metrics["accuracy"] == 0.95

    async def test_failed_run(self, test_db):
        """Failed run stores error message."""
        run = GaiaTrainingRun(
            status="failed",
            trigger="automatic",
            knowledge_count=0,
            error_message="向量索引写入超时",
        )
        test_db.add(run)
        await test_db.commit()
        await test_db.refresh(run)

        assert run.status == "failed"
        assert "超时" in run.error_message

    async def test_repr(self, test_db):
        """__repr__ should be informative."""
        run = GaiaTrainingRun(status="completed", trigger="manual")
        test_db.add(run)
        await test_db.commit()
        await test_db.refresh(run)

        r = repr(run)
        assert "GaiaTrainingRun" in r
        assert str(run.id) in r
        assert "completed" in r

    async def test_index_on_status(self, test_db):
        """Verify index exists on gaia_training_runs."""
        from sqlalchemy import inspect

        def _check(conn):
            insp = inspect(conn)
            indices = {ix["name"] for ix in insp.get_indexes("gaia_training_runs")}
            assert "idx_gaia_training_status" in indices

        conn = await test_db.connection()
        await conn.run_sync(_check)


# ══════════════════════════════════════════════════════════════════════
# 8. GaiaModelWeights update
# ══════════════════════════════════════════════════════════════════════


class TestGaiaModelWeights:
    """Weight record creation, versioning, and activation."""

    async def test_create_weights(self, test_db):
        """Create a weight record with a module and weights dict."""
        w = GaiaModelWeights(
            module="recommendation",
            weights={"alpha": 0.7, "beta": 0.3, "gamma": 0.1},
            version="1.0.0",
            description="推荐模块初始权重",
            is_active=True,
        )
        test_db.add(w)
        await test_db.commit()
        await test_db.refresh(w)

        assert w.id is not None
        assert w.module == "recommendation"
        assert w.weights["alpha"] == 0.7
        assert w.weights["beta"] == 0.3
        assert w.version == "1.0.0"
        assert w.is_active is True

    async def test_version_multiple_weights(self, test_db):
        """Multiple weight versions for the same module."""
        w1 = GaiaModelWeights(
            module="recommendation",
            weights={"v": 1},
            version="1.0.0",
            is_active=False,
        )
        w2 = GaiaModelWeights(
            module="recommendation",
            weights={"v": 2},
            version="2.0.0",
            is_active=True,
        )
        test_db.add_all([w1, w2])
        await test_db.commit()

        assert w1.is_active is False
        assert w2.is_active is True

    async def test_deactivate_old_weights(self, test_db):
        """Simulate deactivating old weights when a new version is set."""
        old = GaiaModelWeights(
            module="search",
            weights={"threshold": 0.5},
            version="1.0.0",
            is_active=True,
        )
        test_db.add(old)
        await test_db.commit()

        # Deactivate old
        old.is_active = False

        # Create new
        new = GaiaModelWeights(
            module="search",
            weights={"threshold": 0.75},
            version="2.0.0",
            is_active=True,
        )
        test_db.add(new)
        await test_db.commit()

        assert old.is_active is False
        assert new.is_active is True

    async def test_different_modules_independent(self, test_db):
        """Weights for different modules are independent."""
        weights_data = [
            GaiaModelWeights(module="recommendation", weights={"a": 1}, version="1.0", is_active=True),
            GaiaModelWeights(module="search", weights={"b": 2}, version="1.0", is_active=True),
            GaiaModelWeights(module="extractor", weights={"c": 3}, version="1.0", is_active=True),
        ]
        test_db.add_all(weights_data)
        await test_db.commit()

        from sqlalchemy import select
        result = await test_db.execute(
            select(GaiaModelWeights).where(GaiaModelWeights.is_active.is_(True))
        )
        active = result.scalars().all()
        assert len(active) == 3

    async def test_repr(self, test_db):
        """__repr__ should show module, version, active."""
        w = GaiaModelWeights(
            module="rag",
            weights={"top_k": 5},
            version="1.0.0",
            is_active=True,
        )
        test_db.add(w)
        await test_db.commit()
        await test_db.refresh(w)

        r = repr(w)
        assert "GaiaModelWeights" in r
        assert "rag" in r
        assert "1.0.0" in r

    async def test_index_on_module_active(self, test_db):
        """Verify composite index on gaia_model_weights."""
        from sqlalchemy import inspect

        def _check(conn):
            insp = inspect(conn)
            indices = {ix["name"] for ix in insp.get_indexes("gaia_model_weights")}
            assert "idx_gaia_weights_module_active" in indices

        conn = await test_db.connection()
        await conn.run_sync(_check)


# ══════════════════════════════════════════════════════════════════════
# 9. GaiaEvolutionEvent model (bonus coverage)
# ══════════════════════════════════════════════════════════════════════


class TestGaiaEvolutionEvent:
    """Event logging model."""

    async def test_create_event(self, test_db):
        """Create an evolution event."""
        ev = GaiaEvolutionEvent(
            event_type="weights_updated",
            event_source="system",
            description="推荐模块权重已更新",
            metadata={"module": "recommendation", "old_version": "1.0.0", "new_version": "1.1.0"},
            reference_type="weights",
            reference_id=1,
        )
        test_db.add(ev)
        await test_db.commit()
        await test_db.refresh(ev)

        assert ev.id is not None
        assert ev.event_type == "weights_updated"
        assert ev.metadata["module"] == "recommendation"
        assert ev.reference_id == 1

    async def test_event_indexes(self, test_db):
        """Verify event table indexes."""
        from sqlalchemy import inspect

        def _check(conn):
            insp = inspect(conn)
            indices = {ix["name"] for ix in insp.get_indexes("gaia_evolution_events")}
            assert "idx_gaia_event_type_time" in indices
            assert "idx_gaia_event_ref" in indices

        conn = await test_db.connection()
        await conn.run_sync(_check)
