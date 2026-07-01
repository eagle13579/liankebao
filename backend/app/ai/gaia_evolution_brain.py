"""盖娅进化大脑 — 核心服务

单例服务，汇聚复盘提炼、用户反馈、A/B测试产出等知识，
通过向量索引与权重进化持续驱动模型适应与优化。

用法:
    brain = get_gaia_brain()
    await brain.ingest_knowledge(source="retrospective", source_id="retro_001", ...)
    await brain.ingest_feedback(user_id=1, item_id=100, rating=4.5, source="recommendation")
    await brain.process_evolution_cycle()
    weights = brain.get_evolved_weights(module="recommendation")
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select, func as sa_func, desc, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.vector_search import (
    get_embedding_backend,
    get_vector_index,
    VectorSearchIndex,
)
from app.models.gaia import (
    GaiaKnowledge,
    GaiaEvolutionEvent,
    GaiaTrainingRun,
    GaiaModelWeights,
)

logger = logging.getLogger(__name__)


# ======================================================================
# 单例锁与实例
# ======================================================================

_gaia_brain_instance: GaiaEvolutionBrain | None = None
_gaia_brain_lock = threading.Lock()


def get_gaia_brain() -> GaiaEvolutionBrain:
    """获取盖娅进化大脑单例"""
    global _gaia_brain_instance
    if _gaia_brain_instance is not None:
        return _gaia_brain_instance
    with _gaia_brain_lock:
        if _gaia_brain_instance is None:
            _gaia_brain_instance = GaiaEvolutionBrain()
    return _gaia_brain_instance


# ======================================================================
# 盖娅进化大脑
# ======================================================================


class GaiaEvolutionBrain:
    """盖娅进化大脑

    核心职责:
    1. 知识摄取 — 接收来自各模块的知识/反馈/A/B测试结果
    2. 进化循环 — 聚合知识、向量化、更新权重、产出进化模型参数
    3. 权重查询 — 供 recommendation/search/extractor 等模块查询当前进化权重
    4. 语义检索 — 从知识库中检索最相关的进化知识
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._vector_index: VectorSearchIndex | None = None
        self._backend = get_embedding_backend()
        logger.info(
            "GaiaEvolutionBrain 已初始化, embedding backend=%s, dim=%d",
            self._backend.name,
            self._backend.dimension,
        )

    # ── 属性 ──────────────────────────────────────────────────────

    @property
    def vector_index(self) -> VectorSearchIndex:
        """获取或初始化向量搜索索引（惰性初始化）"""
        if self._vector_index is None:
            self._vector_index = get_vector_index()
        return self._vector_index

    # ── 知识摄取 ──────────────────────────────────────────────────

    async def ingest_knowledge(
        self,
        db: AsyncSession,
        source: str,
        source_id: str,
        knowledge_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 1.0,
    ) -> GaiaKnowledge:
        """摄取一条进化知识

        Args:
            db: 数据库会话
            source: 知识来源 (retrospective | feedback | ab_test | manual | system)
            source_id: 来源标识
            knowledge_type: 知识类型 (insight | pattern | rule | preference | behavior | optimization)
            title: 知识标题
            content: 知识详细内容
            tags: 标签列表
            confidence: 置信度 0.0 ~ 1.0

        Returns:
            创建的知识条目
        """
        knowledge = GaiaKnowledge(
            source=source,
            source_id=source_id,
            knowledge_type=knowledge_type,
            title=title,
            content=content,
            tags=tags or [],
            confidence=max(0.0, min(1.0, confidence)),
            impact_score=confidence,
            is_active=True,
            vector_embedded=False,
        )
        db.add(knowledge)
        await db.flush()

        # 记录事件
        await self._record_event(
            db,
            event_type="knowledge_ingested",
            event_source="api",
            description=f"知识已摄取: [{knowledge_type}] {title[:80]}",
            metadata={
                "source": source,
                "source_id": source_id,
                "knowledge_type": knowledge_type,
                "knowledge_id": knowledge.id,
                "confidence": confidence,
            },
            reference_type="knowledge",
            reference_id=knowledge.id,
        )

        logger.info(
            "知识已摄取 id=%d source=%s type=%s title=%s",
            knowledge.id, source, knowledge_type, title[:60],
        )
        return knowledge

    async def ingest_feedback(
        self,
        db: AsyncSession,
        user_id: int,
        item_id: int,
        rating: float,
        source: str = "recommendation",
        comment: str | None = None,
    ) -> GaiaKnowledge | None:
        """摄取一条用户反馈作为进化知识

        当评分极端（<=2 或 >=4）时，自动转化为知识条目存入知识库。

        Args:
            db: 数据库会话
            user_id: 用户ID
            item_id: 评价对象ID
            rating: 评分 (1.0 ~ 5.0)
            source: 来源
            comment: 反馈评论文本

        Returns:
            如果生成了知识条目则返回，否则返回 None
        """
        # 仅极端评分（差评或好评）自动转化为知识
        if rating > 2.0 and rating < 4.0:
            # 记录事件但不生成知识
            await self._record_event(
                db,
                event_type="feedback_recorded",
                event_source="api",
                description=f"用户 {user_id} 对 {item_id} 评分 {rating}",
                metadata={
                    "user_id": user_id,
                    "item_id": item_id,
                    "rating": rating,
                    "source": source,
                },
            )
            return None

        # 构建知识内容
        sentiment = "好评" if rating >= 4.0 else "差评"
        title = f"用户{user_id}对{item_id}的{sentiment}反馈"
        content_parts = [f"用户 {user_id} 对项目 {item_id} 的{sentiment}反馈, 评分: {rating}"]
        if comment:
            content_parts.append(f"评语: {comment}")
        content = ". ".join(content_parts)

        knowledge = await self.ingest_knowledge(
            db=db,
            source="feedback",
            source_id=f"feedback_{user_id}_{item_id}",
            knowledge_type="preference" if rating >= 4.0 else "behavior",
            title=title,
            content=content,
            tags=["feedback", sentiment, source],
            confidence=rating / 5.0,
        )
        return knowledge

    # ── 进化循环 ──────────────────────────────────────────────────

    async def process_evolution_cycle(
        self,
        db: AsyncSession,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        """执行一次进化循环

        步骤:
        1. 聚合近期活跃的知识条目
        2. 将新知识嵌入向量索引
        3. 基于知识模式计算并更新模型权重
        4. 存储训练运行记录

        Args:
            db: 数据库会话
            trigger: 触发方式 (manual | scheduled | automatic | api)

        Returns:
            进化结果摘要
        """
        cycle_start = time.monotonic()

        # 记录事件：循环开始
        await self._record_event(
            db,
            event_type="cycle_started",
            event_source=trigger,
            description="进化循环开始",
        )

        try:
            # 1. 聚合近期未向量化的知识
            pending_knowledge = await self._collect_pending_knowledge(db)
            knowledge_ids = [k.id for k in pending_knowledge]
            knowledge_count = len(knowledge_ids)

            # 2. 嵌入到向量索引
            if pending_knowledge:
                await self._embed_knowledge_batch(db, pending_knowledge)

            # 3. 收集反馈并更新权重
            feedback_count = 0
            weights_updated = await self._compute_and_update_weights(db)
            weights_count = weights_updated

            # 4. 更新向量索引
            vector_index_size = self.vector_index.size

            # 5. 记录训练运行
            elapsed_ms = int((time.monotonic() - cycle_start) * 1000)
            training_run = GaiaTrainingRun(
                status="completed",
                trigger=trigger,
                knowledge_count=knowledge_count,
                feedback_count=feedback_count,
                weights_count=weights_count,
                vector_index_size=vector_index_size,
                duration_ms=elapsed_ms,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(training_run)
            await db.flush()

            # 记录事件：循环完成
            await self._record_event(
                db,
                event_type="cycle_completed",
                event_source=trigger,
                description=f"进化循环完成: {knowledge_count} 条知识, {weights_count} 个权重更新",
                metadata={
                    "knowledge_count": knowledge_count,
                    "feedback_count": feedback_count,
                    "weights_count": weights_count,
                    "vector_index_size": vector_index_size,
                    "duration_ms": elapsed_ms,
                },
                reference_type="training_run",
                reference_id=training_run.id,
            )

            result = {
                "status": "completed",
                "training_run_id": training_run.id,
                "knowledge_count": knowledge_count,
                "feedback_count": feedback_count,
                "weights_count": weights_count,
                "vector_index_size": vector_index_size,
                "duration_ms": elapsed_ms,
            }

            logger.info("进化循环完成: %s", result)
            return result

        except Exception as e:
            elapsed_ms = int((time.monotonic() - cycle_start) * 1000)
            logger.error("进化循环失败: %s", e, exc_info=True)

            # 记录失败事件
            await self._record_event(
                db,
                event_type="cycle_completed",
                event_source=trigger,
                description=f"进化循环失败: {e!s}",
                metadata={"error": str(e), "duration_ms": elapsed_ms},
            )

            # 记录失败的训练运行
            training_run = GaiaTrainingRun(
                status="failed",
                trigger=trigger,
                duration_ms=elapsed_ms,
                error_message=str(e),
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(training_run)

            return {
                "status": "failed",
                "error": str(e),
                "duration_ms": elapsed_ms,
            }

    async def _collect_pending_knowledge(self, db: AsyncSession) -> list[GaiaKnowledge]:
        """收集尚未向量化的活跃知识条目"""
        stmt = (
            select(GaiaKnowledge)
            .where(GaiaKnowledge.is_active.is_(True))
            .where(GaiaKnowledge.vector_embedded.is_(False))
            .order_by(GaiaKnowledge.created_at.asc())
            .limit(500)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _embed_knowledge_batch(
        self, db: AsyncSession, knowledge_list: list[GaiaKnowledge],
    ) -> None:
        """将知识批量嵌入向量索引"""
        for knowledge in knowledge_list:
            text = f"{knowledge.title}. {knowledge.content}"
            if knowledge.tags:
                tags_str = " ".join(
                    t for t in (knowledge.tags or []) if isinstance(t, str)
                )
                text = f"{text} [{tags_str}]"

            # 使用 content_type="gaia_knowledge" 和 knowledge.id 作为 ID
            self.vector_index.add_or_update(
                content_type="gaia_knowledge",
                content_id=knowledge.id,
                content=text,
                metadata={
                    "knowledge_type": knowledge.knowledge_type,
                    "source": knowledge.source,
                    "confidence": knowledge.confidence,
                },
            )
            # 标记已向量化
            knowledge.vector_embedded = True

        await db.flush()
        logger.info("向量索引已更新: %d 条知识", len(knowledge_list))

    async def _compute_and_update_weights(self, db: AsyncSession) -> int:
        """基于知识模式分析，计算并更新各模块权重

        策略:
        - 统计各类知识的占比，调整模块权重
        - 高置信度、高影响的知识获得更高权重
        
        Returns:
            更新的权重模块数
        """
        # 获取最近活跃知识的统计信息
        stmt = (
            select(
                GaiaKnowledge.knowledge_type,
                sa_func.count().label("count"),
                sa_func.avg(GaiaKnowledge.confidence).label("avg_confidence"),
                sa_func.avg(GaiaKnowledge.impact_score).label("avg_impact"),
            )
            .where(GaiaKnowledge.is_active.is_(True))
            .group_by(GaiaKnowledge.knowledge_type)
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return 0

        total = sum(r.count for r in rows) if rows else 1

        # 构建基础权重配置
        type_weights: dict[str, float] = {}
        for row in rows:
            ratio = row.count / max(total, 1)
            type_weights[row.knowledge_type] = round(
                ratio * (row.avg_confidence or 0.5) * (row.avg_impact or 0.5),
                4,
            )

        # 为各模块计算进化权重
        module_weights: dict[str, dict[str, Any]] = {
            "recommendation": {
                "preference_weight": type_weights.get("preference", 0.5),
                "behavior_weight": type_weights.get("behavior", 0.3),
                "pattern_weight": type_weights.get("pattern", 0.2),
                "insight_weight": type_weights.get("insight", 0.1),
                "confidence_threshold": 0.6,
                "total_knowledge": total,
            },
            "search": {
                "semantic_weight": type_weights.get("pattern", 0.4),
                "optimization_weight": type_weights.get("optimization", 0.3),
                "rule_weight": type_weights.get("rule", 0.2),
                "insight_weight": type_weights.get("insight", 0.1),
                "confidence_threshold": 0.5,
                "total_knowledge": total,
            },
            "extractor": {
                "pattern_weight": type_weights.get("pattern", 0.4),
                "rule_weight": type_weights.get("rule", 0.3),
                "optimization_weight": type_weights.get("optimization", 0.2),
                "insight_weight": type_weights.get("insight", 0.1),
                "total_knowledge": total,
            },
            "writing": {
                "preference_weight": type_weights.get("preference", 0.4),
                "optimization_weight": type_weights.get("optimization", 0.3),
                "behavior_weight": type_weights.get("behavior", 0.2),
                "pattern_weight": type_weights.get("pattern", 0.1),
                "total_knowledge": total,
            },
            "optimization": {
                "optimization_weight": type_weights.get("optimization", 0.5),
                "pattern_weight": type_weights.get("pattern", 0.3),
                "insight_weight": type_weights.get("insight", 0.2),
                "total_knowledge": total,
            },
            "rag": {
                "insight_weight": type_weights.get("insight", 0.4),
                "knowledge_weight": type_weights.get("knowledge", 0.3),
                "pattern_weight": type_weights.get("pattern", 0.2),
                "rule_weight": type_weights.get("rule", 0.1),
                "total_knowledge": total,
            },
            "knowledge_graph": {
                "relation_weight": type_weights.get("pattern", 0.5),
                "insight_weight": type_weights.get("insight", 0.3),
                "rule_weight": type_weights.get("rule", 0.2),
                "total_knowledge": total,
            },
        }

        # 写入数据库
        updated_count = 0
        for module, weights in module_weights.items():
            # 检查是否已有活跃记录
            existing_stmt = (
                select(GaiaModelWeights)
                .where(GaiaModelWeights.module == module)
                .where(GaiaModelWeights.is_active.is_(True))
                .order_by(GaiaModelWeights.created_at.desc())
                .limit(1)
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalars().first()

            if existing and existing.weights == weights:
                # 权重未变化，跳过
                continue

            # 停用旧的活跃记录
            if existing:
                existing.is_active = False

            # 创建新版本
            new_weights = GaiaModelWeights(
                module=module,
                weights=weights,
                version=self._next_version(existing.version if existing else "0.0.0"),
                description=f"进化循环自动更新 - {total} 条知识",
                is_active=True,
            )
            db.add(new_weights)
            updated_count += 1

        await db.flush()

        if updated_count > 0:
            # 记录事件
            await self._record_event(
                db,
                event_type="weights_updated",
                event_source="system",
                description=f"进化权重已更新: {updated_count} 个模块",
                metadata={
                    "modules_updated": updated_count,
                    "modules": list(module_weights.keys()),
                    "knowledge_total": total,
                },
            )

        logger.info("进化权重已更新: %d 个模块", updated_count)
        return updated_count

    @staticmethod
    def _next_version(current: str) -> str:
        """递增版本号 (major.minor.patch)"""
        try:
            parts = current.split(".")
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            patch += 1
            if patch >= 100:
                patch = 0
                minor += 1
                if minor >= 100:
                    minor = 0
                    major += 1
            return f"{major}.{minor}.{patch}"
        except (ValueError, IndexError):
            return "1.0.0"

    # ── 权重查询 ──────────────────────────────────────────────────

    async def get_evolved_weights(
        self,
        db: AsyncSession,
        module: str,
    ) -> dict[str, Any] | None:
        """获取指定模块的当前进化权重

        Args:
            db: 数据库会话
            module: 模块标识 (recommendation | search | extractor | writing | optimization | rag | knowledge_graph)

        Returns:
            权重字典，如未找到返回 None
        """
        stmt = (
            select(GaiaModelWeights)
            .where(GaiaModelWeights.module == module)
            .where(GaiaModelWeights.is_active.is_(True))
            .order_by(GaiaModelWeights.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        weights_record = result.scalars().first()

        if weights_record is None:
            logger.info("未找到模块 %s 的进化权重", module)
            return None

        return {
            "module": weights_record.module,
            "version": weights_record.version,
            "weights": weights_record.weights,
            "description": weights_record.description,
            "updated_at": weights_record.updated_at.isoformat() if weights_record.updated_at else None,
        }

    # ── 知识库语义检索 ────────────────────────────────────────────

    async def get_knowledge_base(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 10,
        knowledge_type: str | None = None,
        source: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        """从知识库中检索最相关的知识条目

        优先使用向量语义搜索，若向量索引为空则回退到数据库关键词搜索。

        Args:
            db: 数据库会话
            query: 检索查询文本
            limit: 返回结果数量上限
            knowledge_type: 按知识类型过滤
            source: 按来源过滤
            min_confidence: 最低置信度阈值

        Returns:
            知识条目列表（按相关性排序）
        """
        # 优先向量搜索
        if self.vector_index.size > 0:
            vector_results = self.vector_index.search(query, top_k=limit)
            if vector_results:
                # 从向量结果中提取知识 ID
                knowledge_ids = []
                for r in vector_results:
                    meta = r.get("metadata", {})
                    if meta.get("content_type") == "gaia_knowledge":
                        knowledge_ids.append(meta.get("content_id"))

                if knowledge_ids:
                    stmt = select(GaiaKnowledge).where(
                        GaiaKnowledge.id.in_(knowledge_ids),
                        GaiaKnowledge.is_active.is_(True),
                        GaiaKnowledge.confidence >= min_confidence,
                    )
                    if knowledge_type:
                        stmt = stmt.where(GaiaKnowledge.knowledge_type == knowledge_type)
                    if source:
                        stmt = stmt.where(GaiaKnowledge.source == source)

                    result = await db.execute(stmt)
                    knowledge_map = {k.id: k for k in result.scalars().all()}

                    # 按向量搜索排序
                    items = []
                    for kid in knowledge_ids:
                        if kid in knowledge_map:
                            k = knowledge_map[kid]
                            items.append(self._knowledge_to_dict(k))
                    return items[:limit]

        # 回退: 数据库全文搜索
        query_filter = f"%{query}%"
        stmt = (
            select(GaiaKnowledge)
            .where(GaiaKnowledge.is_active.is_(True))
            .where(GaiaKnowledge.confidence >= min_confidence)
            .where(
                (GaiaKnowledge.title.ilike(query_filter))
                | (GaiaKnowledge.content.ilike(query_filter))
            )
            .order_by(GaiaKnowledge.confidence.desc(), GaiaKnowledge.impact_score.desc())
            .limit(limit)
        )
        if knowledge_type:
            stmt = stmt.where(GaiaKnowledge.knowledge_type == knowledge_type)
        if source:
            stmt = stmt.where(GaiaKnowledge.source == source)

        result = await db.execute(stmt)
        knowledge_list = result.scalars().all()

        return [self._knowledge_to_dict(k) for k in knowledge_list]

    # ── 状态查询 ──────────────────────────────────────────────────

    async def get_status(self, db: AsyncSession) -> dict[str, Any]:
        """获取进化大脑状态概览"""
        # 知识统计
        count_stmt = select(sa_func.count()).select_from(GaiaKnowledge)
        total_knowledge = (await db.execute(count_stmt)).scalar() or 0

        active_stmt = (
            select(sa_func.count())
            .select_from(GaiaKnowledge)
            .where(GaiaKnowledge.is_active.is_(True))
        )
        active_knowledge = (await db.execute(active_stmt)).scalar() or 0

        embedded_stmt = (
            select(sa_func.count())
            .select_from(GaiaKnowledge)
            .where(GaiaKnowledge.vector_embedded.is_(True))
        )
        embedded_count = (await db.execute(embedded_stmt)).scalar() or 0

        # 训练统计
        training_count_stmt = select(sa_func.count()).select_from(GaiaTrainingRun)
        total_training_runs = (await db.execute(training_count_stmt)).scalar() or 0

        last_training_stmt = (
            select(GaiaTrainingRun)
            .order_by(GaiaTrainingRun.created_at.desc())
            .limit(1)
        )
        last_training_result = await db.execute(last_training_stmt)
        last_training = last_training_result.scalars().first()

        # 权重统计
        weight_count_stmt = select(sa_func.count()).select_from(GaiaModelWeights)
        total_weights = (await db.execute(weight_count_stmt)).scalar() or 0

        active_weight_stmt = (
            select(sa_func.count())
            .select_from(GaiaModelWeights)
            .where(GaiaModelWeights.is_active.is_(True))
        )
        active_weights = (await db.execute(active_weight_stmt)).scalar() or 0

        return {
            "brain_status": "active",
            "embedding_provider": self._backend.name,
            "embedding_dimension": self._backend.dimension,
            "vector_index_size": self.vector_index.size,
            "knowledge": {
                "total": total_knowledge,
                "active": active_knowledge,
                "embedded": embedded_count,
            },
            "training": {
                "total_runs": total_training_runs,
                "last_run": {
                    "id": last_training.id if last_training else None,
                    "status": last_training.status if last_training else None,
                    "trigger": last_training.trigger if last_training else None,
                    "completed_at": (
                        last_training.completed_at.isoformat()
                        if last_training and last_training.completed_at
                        else None
                    ),
                }
                if last_training
                else None,
            },
            "weights": {
                "total_versions": total_weights,
                "active_weights": active_weights,
            },
        }

    # ── 事件查询 ──────────────────────────────────────────────────

    async def get_events(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 50,
        event_type: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """获取进化事件日志（分页）

        Returns:
            (items, total)
        """
        stmt = select(GaiaEvolutionEvent).order_by(GaiaEvolutionEvent.created_at.desc())
        count_stmt = select(sa_func.count()).select_from(GaiaEvolutionEvent)

        if event_type:
            stmt = stmt.where(GaiaEvolutionEvent.event_type == event_type)
            count_stmt = count_stmt.where(GaiaEvolutionEvent.event_type == event_type)

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        events = result.scalars().all()

        total = (await db.execute(count_stmt)).scalar() or 0

        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_source": e.event_source,
                "description": e.description,
                "metadata": e.event_meta,
                "reference_type": e.reference_type,
                "reference_id": e.reference_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ], total

    # ── 训练记录查询 ──────────────────────────────────────────────

    async def get_training_runs(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """获取训练运行记录（分页）

        Returns:
            (items, total)
        """
        stmt = select(GaiaTrainingRun).order_by(GaiaTrainingRun.created_at.desc())
        count_stmt = select(sa_func.count()).select_from(GaiaTrainingRun)

        if status:
            stmt = stmt.where(GaiaTrainingRun.status == status)
            count_stmt = count_stmt.where(GaiaTrainingRun.status == status)

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        runs = result.scalars().all()

        total = (await db.execute(count_stmt)).scalar() or 0

        return [
            {
                "id": r.id,
                "status": r.status,
                "trigger": r.trigger,
                "knowledge_count": r.knowledge_count,
                "feedback_count": r.feedback_count,
                "weights_count": r.weights_count,
                "vector_index_size": r.vector_index_size,
                "duration_ms": r.duration_ms,
                "metrics": r.metrics,
                "error_message": r.error_message,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ], total

    # ── 内部辅助方法 ──────────────────────────────────────────────

    async def _record_event(
        self,
        db: AsyncSession,
        event_type: str,
        event_source: str = "system",
        description: str = "",
        metadata: dict[str, Any] | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> GaiaEvolutionEvent:
        """记录一条进化事件"""
        event = GaiaEvolutionEvent(
            event_type=event_type,
            event_source=event_source,
            description=description,
            metadata=metadata,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        db.add(event)
        return event

    @staticmethod
    def _knowledge_to_dict(knowledge: GaiaKnowledge) -> dict[str, Any]:
        """将知识条目转为字典"""
        return {
            "id": knowledge.id,
            "source": knowledge.source,
            "source_id": knowledge.source_id,
            "knowledge_type": knowledge.knowledge_type,
            "title": knowledge.title,
            "content": knowledge.content,
            "tags": knowledge.tags,
            "confidence": knowledge.confidence,
            "impact_score": knowledge.impact_score,
            "is_active": knowledge.is_active,
            "vector_embedded": knowledge.vector_embedded,
            "created_at": knowledge.created_at.isoformat() if knowledge.created_at else None,
            "updated_at": knowledge.updated_at.isoformat() if knowledge.updated_at else None,
        }
