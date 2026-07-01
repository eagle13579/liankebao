"""盖娅训练管线 — 进化训练管道

负责从反馈/知识/交互中收集训练数据，分析模式，
计算进化权重，并部署到生产环境。

用法:
    trainer = get_gaia_trainer()
    result = await trainer.run_training_cycle(db)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.vector_search import (
    get_embedding_backend,
    get_vector_index,
    VectorSearchIndex,
    embed_text,
)
from app.ai.gaia_evolution_brain import get_gaia_brain, GaiaEvolutionBrain
from app.models.gaia import (
    GaiaKnowledge,
    GaiaTrainingRun,
    GaiaModelWeights,
    GaiaEvolutionEvent,
)

logger = logging.getLogger(__name__)


# ======================================================================
# 单例
# ======================================================================

_gaia_trainer_instance: GaiaTrainer | None = None


def get_gaia_trainer() -> GaiaTrainer:
    """获取盖娅训练管线单例"""
    global _gaia_trainer_instance
    if _gaia_trainer_instance is None:
        _gaia_trainer_instance = GaiaTrainer()
    return _gaia_trainer_instance


# ======================================================================
# 训练管线
# ======================================================================


class GaiaTrainer:
    """盖娅训练管线

    完整训练管线:
    1. collect_training_data() — 收集反馈 + 知识 + 交互数据
    2. compute_evolved_weights() — 分析模式，计算新权重
    3. update_vector_index() — 刷新向量搜索索引
    4. deploy_weights() — 写入新的模型权重到数据库
    5. run_training_cycle() — 编排完整的训练管线
    """

    def __init__(self):
        self._brain: GaiaEvolutionBrain | None = None
        self._backend = get_embedding_backend()
        logger.info("GaiaTrainer 已初始化, embedding=%s", self._backend.name)

    @property
    def brain(self) -> GaiaEvolutionBrain:
        if self._brain is None:
            self._brain = get_gaia_brain()
        return self._brain

    # ── 收集训练数据 ──────────────────────────────────────────────

    async def collect_training_data(
        self,
        db: AsyncSession,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """收集训练数据

        收集三类数据:
        - 知识数据: 活跃的 GaiaKnowledge 条目
        - 反馈数据: 从知识库中筛选的反馈类知识
        - 交互数据: 统计分析各类型知识的分布

        Args:
            db: 数据库会话
            limit: 各类数据的收集上限

        Returns:
            {
                "knowledge": [...],
                "knowledge_count": int,
                "knowledge_types": {...},
                "feedback_entries": int,
                "high_confidence_entries": int,
            }
        """
        # 1. 收集所有活跃知识
        stmt = (
            select(GaiaKnowledge)
            .where(GaiaKnowledge.is_active.is_(True))
            .order_by(GaiaKnowledge.confidence.desc(), GaiaKnowledge.impact_score.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        # 2. 统计分析
        type_distribution: dict[str, int] = {}
        source_distribution: dict[str, int] = {}
        feedback_count = 0
        high_conf_count = 0
        total_confidence = 0.0

        for k in knowledge_list:
            type_distribution[k.knowledge_type] = type_distribution.get(k.knowledge_type, 0) + 1
            source_distribution[k.source] = source_distribution.get(k.source, 0) + 1
            total_confidence += k.confidence

            if k.source == "feedback":
                feedback_count += 1
            if k.confidence >= 0.8:
                high_conf_count += 1

        avg_confidence = total_confidence / max(len(knowledge_list), 1)

        return {
            "knowledge": [
                {
                    "id": k.id,
                    "type": k.knowledge_type,
                    "source": k.source,
                    "confidence": k.confidence,
                    "impact_score": k.impact_score,
                    "title": k.title,
                    "content": k.content[:200],  # 摘要
                }
                for k in knowledge_list
            ],
            "knowledge_count": len(knowledge_list),
            "knowledge_types": type_distribution,
            "knowledge_sources": source_distribution,
            "feedback_entries": feedback_count,
            "high_confidence_entries": high_conf_count,
            "avg_confidence": round(avg_confidence, 4),
        }

    # ── 计算进化权重 ──────────────────────────────────────────────

    async def compute_evolved_weights(
        self,
        db: AsyncSession,
    ) -> dict[str, dict[str, Any]]:
        """分析知识模式，计算各模块的进化权重

        分析维度:
        - 知识类型分布 -> 各模块权重倾向
        - 置信度加权 -> 高置信度知识主导权重
        - 影响评分 -> 高频知识类型获得更高权重

        Returns:
            {module_name: {weight_key: value, ...}}
        """
        # 获取知识统计
        stmt = (
            select(
                GaiaKnowledge.knowledge_type,
                sa_func.count().label("count"),
                sa_func.avg(GaiaKnowledge.confidence).label("avg_confidence"),
                sa_func.sum(GaiaKnowledge.impact_score).label("total_impact"),
            )
            .where(GaiaKnowledge.is_active.is_(True))
            .group_by(GaiaKnowledge.knowledge_type)
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            logger.info("无活跃知识数据，返回默认权重")
            return self._default_weights()

        total = sum(r.count for r in rows)
        total_impact = sum(r.total_impact or 0 for r in rows) or 1.0

        # 计算各类型的加权重要性 (0.0 ~ 1.0)
        type_importance: dict[str, float] = {}
        for row in rows:
            count_ratio = row.count / max(total, 1)
            impact_ratio = (row.total_impact or 0) / total_impact
            importance = count_ratio * 0.6 + impact_ratio * 0.4
            importance *= row.avg_confidence or 0.5
            type_importance[row.knowledge_type] = round(min(1.0, importance), 4)

        # 构建各模块的进化权重
        module_weights: dict[str, dict[str, Any]] = {
            "recommendation": {
                "preference_weight": type_importance.get("preference", 0.3),
                "behavior_weight": type_importance.get("behavior", 0.25),
                "pattern_weight": type_importance.get("pattern", 0.2),
                "insight_weight": type_importance.get("insight", 0.15),
                "optimization_weight": type_importance.get("optimization", 0.1),
                "diversity_factor": 0.2,
                "recency_factor": 0.3,
                "confidence_threshold": 0.6,
                "total_knowledge_basis": total,
            },
            "search": {
                "semantic_weight": type_importance.get("pattern", 0.35),
                "optimization_weight": type_importance.get("optimization", 0.25),
                "rule_weight": type_importance.get("rule", 0.2),
                "insight_weight": type_importance.get("insight", 0.1),
                "behavior_weight": type_importance.get("behavior", 0.1),
                "confidence_threshold": 0.5,
                "rerank_weight": 0.3,
                "total_knowledge_basis": total,
            },
            "extractor": {
                "pattern_weight": type_importance.get("pattern", 0.3),
                "rule_weight": type_importance.get("rule", 0.25),
                "optimization_weight": type_importance.get("optimization", 0.2),
                "insight_weight": type_importance.get("insight", 0.15),
                "behavior_weight": type_importance.get("behavior", 0.1),
                "confidence_threshold": 0.8,
                "field_boost": 1.2,
                "total_knowledge_basis": total,
            },
            "writing": {
                "preference_weight": type_importance.get("preference", 0.3),
                "optimization_weight": type_importance.get("optimization", 0.25),
                "behavior_weight": type_importance.get("behavior", 0.2),
                "pattern_weight": type_importance.get("pattern", 0.15),
                "insight_weight": type_importance.get("insight", 0.1),
                "creativity_factor": 0.3,
                "formality_factor": 0.5,
                "total_knowledge_basis": total,
            },
            "optimization": {
                "optimization_weight": type_importance.get("optimization", 0.4),
                "pattern_weight": type_importance.get("pattern", 0.25),
                "behavior_weight": type_importance.get("behavior", 0.2),
                "insight_weight": type_importance.get("insight", 0.15),
                "confidence_threshold": 0.7,
                "impact_multiplier": 1.5,
                "total_knowledge_basis": total,
            },
            "rag": {
                "insight_weight": type_importance.get("insight", 0.3),
                "knowledge_weight": type_importance.get("knowledge", 0.25),
                "pattern_weight": type_importance.get("pattern", 0.2),
                "rule_weight": type_importance.get("rule", 0.15),
                "optimization_weight": type_importance.get("optimization", 0.1),
                "context_window_boost": 1.0,
                "temperature_adjustment": 0.1,
                "total_knowledge_basis": total,
            },
            "knowledge_graph": {
                "relation_weight": type_importance.get("pattern", 0.35),
                "insight_weight": type_importance.get("insight", 0.25),
                "rule_weight": type_importance.get("rule", 0.2),
                "optimization_weight": type_importance.get("optimization", 0.1),
                "behavior_weight": type_importance.get("behavior", 0.1),
                "depth_factor": 0.5,
                "breadth_factor": 0.5,
                "total_knowledge_basis": total,
            },
        }

        logger.info("进化权重计算完成: %d 个模块, %d 条知识依据", len(module_weights), total)
        return module_weights

    @staticmethod
    def _default_weights() -> dict[str, dict[str, Any]]:
        """返回默认权重配置"""
        return {
            "recommendation": {
                "preference_weight": 0.3, "behavior_weight": 0.25, "pattern_weight": 0.2,
                "insight_weight": 0.15, "optimization_weight": 0.1, "diversity_factor": 0.2,
                "recency_factor": 0.3, "confidence_threshold": 0.6, "total_knowledge_basis": 0,
            },
            "search": {
                "semantic_weight": 0.35, "optimization_weight": 0.25, "rule_weight": 0.2,
                "insight_weight": 0.1, "behavior_weight": 0.1, "confidence_threshold": 0.5,
                "rerank_weight": 0.3, "total_knowledge_basis": 0,
            },
            "extractor": {
                "pattern_weight": 0.3, "rule_weight": 0.25, "optimization_weight": 0.2,
                "insight_weight": 0.15, "behavior_weight": 0.1, "confidence_threshold": 0.8,
                "field_boost": 1.2, "total_knowledge_basis": 0,
            },
            "writing": {
                "preference_weight": 0.3, "optimization_weight": 0.25, "behavior_weight": 0.2,
                "pattern_weight": 0.15, "insight_weight": 0.1, "creativity_factor": 0.3,
                "formality_factor": 0.5, "total_knowledge_basis": 0,
            },
            "optimization": {
                "optimization_weight": 0.4, "pattern_weight": 0.25, "behavior_weight": 0.2,
                "insight_weight": 0.15, "confidence_threshold": 0.7, "impact_multiplier": 1.5,
                "total_knowledge_basis": 0,
            },
            "rag": {
                "insight_weight": 0.3, "knowledge_weight": 0.25, "pattern_weight": 0.2,
                "rule_weight": 0.15, "optimization_weight": 0.1, "context_window_boost": 1.0,
                "temperature_adjustment": 0.1, "total_knowledge_basis": 0,
            },
            "knowledge_graph": {
                "relation_weight": 0.35, "insight_weight": 0.25, "rule_weight": 0.2,
                "optimization_weight": 0.1, "behavior_weight": 0.1, "depth_factor": 0.5,
                "breadth_factor": 0.5, "total_knowledge_basis": 0,
            },
        }

    # ── 更新向量索引 ──────────────────────────────────────────────

    async def update_vector_index(
        self,
        db: AsyncSession,
    ) -> int:
        """刷新向量搜索索引中所有活跃知识的 embedding

        策略: 对尚未向量化的知识进行增量更新。
        如果 force_rebuild=True，则重建整个索引。

        Args:
            db: 数据库会话

        Returns:
            更新的条目数
        """
        updated = 0
        vector_idx = get_vector_index()

        # 获取未嵌入的知识条目
        stmt = (
            select(GaiaKnowledge)
            .where(GaiaKnowledge.is_active.is_(True))
            .where(GaiaKnowledge.vector_embedded.is_(False))
            .limit(500)
        )
        result = await db.execute(stmt)
        pending = list(result.scalars().all())

        for knowledge in pending:
            text = f"{knowledge.title}. {knowledge.content}"
            if knowledge.tags:
                tags_str = " ".join(
                    t for t in (knowledge.tags or []) if isinstance(t, str)
                )
                text = f"{text} [{tags_str}]"

            vector_idx.add_or_update(
                content_type="gaia_knowledge",
                content_id=knowledge.id,
                content=text,
                metadata={
                    "knowledge_type": knowledge.knowledge_type,
                    "source": knowledge.source,
                    "confidence": knowledge.confidence,
                },
            )
            knowledge.vector_embedded = True
            updated += 1

        if updated > 0:
            await db.flush()
            logger.info("向量索引已更新: %d 条新知识", updated)

        return updated

    # ── 部署权重 ──────────────────────────────────────────────────

    async def deploy_weights(
        self,
        db: AsyncSession,
        module_weights: dict[str, dict[str, Any]],
        training_run_id: int | None = None,
    ) -> int:
        """将计算出的权重部署到 gaia_model_weights 表

        策略:
        - 将旧活跃权重标记为非活跃
        - 创建新权重记录（版本递增）

        Args:
            db: 数据库会话
            module_weights: {module: weights_dict}
            training_run_id: 关联的训练记录 ID

        Returns:
            部署的权重模块数
        """
        deployed = 0
        for module, weights in module_weights.items():
            # 查找当前活跃版本
            existing_stmt = (
                select(GaiaModelWeights)
                .where(GaiaModelWeights.module == module)
                .where(GaiaModelWeights.is_active.is_(True))
                .order_by(GaiaModelWeights.created_at.desc())
                .limit(1)
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalars().first()

            # 检查是否与当前版本相同
            if existing and existing.weights == weights:
                logger.debug("模块 %s 权重未变化，跳过", module)
                continue

            # 停用旧版本
            if existing:
                existing.is_active = False

            # 计算新版本号
            old_version = existing.version if existing else "0.0.0"
            new_version = self._bump_version(old_version)

            # 创建新权重记录
            new_entry = GaiaModelWeights(
                module=module,
                weights=weights,
                version=new_version,
                description=f"训练管线部署 - 知识依据: {weights.get('total_knowledge_basis', 0)} 条",
                training_run_id=training_run_id,
                is_active=True,
            )
            db.add(new_entry)
            deployed += 1

        if deployed > 0:
            await db.flush()
            logger.info("权重已部署: %d 个模块", deployed)

        # 记录事件
        if deployed > 0:
            event = GaiaEvolutionEvent(
                event_type="weights_updated",
                event_source="trainer",
                description=f"训练管线部署权重: {deployed} 个模块",
                metadata={"modules_deployed": deployed},
                reference_type="training_run",
                reference_id=training_run_id,
            )
            db.add(event)

        return deployed

    @staticmethod
    def _bump_version(current: str) -> str:
        """递增补丁版本号"""
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

    # ── 完整训练管线 ──────────────────────────────────────────────

    async def run_training_cycle(
        self,
        db: AsyncSession,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        """运行完整的训练管线

        编排步骤:
        1. collect_training_data() — 收集训练数据
        2. update_vector_index() — 更新向量索引
        3. compute_evolved_weights() — 计算进化权重
        4. deploy_weights() — 部署新权重
        5. 记录训练运行结果

        Args:
            db: 数据库会话
            trigger: 触发方式

        Returns:
            训练结果摘要
        """
        cycle_start = time.monotonic()
        logger.info("训练管线开始 (trigger=%s)", trigger)

        # 创建训练记录
        training_run = GaiaTrainingRun(
            status="running",
            trigger=trigger,
            started_at=datetime.now(timezone.utc),
        )
        db.add(training_run)
        await db.flush()
        training_run_id = training_run.id

        # 记录开始事件
        event = GaiaEvolutionEvent(
            event_type="training_started",
            event_source=trigger,
            description=f"训练管线开始 (run_id={training_run_id})",
            reference_type="training_run",
            reference_id=training_run_id,
        )
        db.add(event)

        try:
            # Step 1: 收集训练数据
            logger.info("Step 1/4: 收集训练数据...")
            training_data = await self.collect_training_data(db)
            knowledge_count = training_data["knowledge_count"]
            feedback_count = training_data["feedback_entries"]

            # Step 2: 更新向量索引
            logger.info("Step 2/4: 更新向量索引...")
            vector_updated = await self.update_vector_index(db)
            vector_index_size = get_vector_index().size

            # Step 3: 计算进化权重
            logger.info("Step 3/4: 计算进化权重...")
            evolved_weights = await self.compute_evolved_weights(db)
            weights_count = len(evolved_weights)

            # Step 4: 部署权重
            logger.info("Step 4/4: 部署权重...")
            deployed = await self.deploy_weights(
                db, evolved_weights, training_run_id=training_run_id,
            )

            # 完成训练记录
            elapsed_ms = int((time.monotonic() - cycle_start) * 1000)
            training_run.status = "completed"
            training_run.knowledge_count = knowledge_count
            training_run.feedback_count = feedback_count
            training_run.weights_count = deployed
            training_run.vector_index_size = vector_index_size
            training_run.duration_ms = elapsed_ms
            training_run.completed_at = datetime.now(timezone.utc)
            training_run.metrics = {
                "knowledge_types": training_data["knowledge_types"],
                "knowledge_sources": training_data["knowledge_sources"],
                "avg_confidence": training_data["avg_confidence"],
                "high_confidence_entries": training_data["high_confidence_entries"],
                "vector_updated": vector_updated,
                "weights_deployed": deployed,
            }

            # 记录完成事件
            event = GaiaEvolutionEvent(
                event_type="training_completed",
                event_source=trigger,
                description=(
                    f"训练管线完成: {knowledge_count} 条知识, "
                    f"{deployed} 个权重更新 ({elapsed_ms}ms)"
                ),
                metadata={
                    "knowledge_count": knowledge_count,
                    "feedback_count": feedback_count,
                    "weights_deployed": deployed,
                    "vector_index_size": vector_index_size,
                    "duration_ms": elapsed_ms,
                },
                reference_type="training_run",
                reference_id=training_run_id,
            )
            db.add(event)

            result = {
                "status": "completed",
                "training_run_id": training_run_id,
                "knowledge_count": knowledge_count,
                "feedback_count": feedback_count,
                "weights_deployed": deployed,
                "vector_index_size": vector_index_size,
                "vector_updated": vector_updated,
                "duration_ms": elapsed_ms,
                "knowledge_types": training_data["knowledge_types"],
                "avg_confidence": training_data["avg_confidence"],
            }

            logger.info("训练管线完成: %s", result)
            return result

        except Exception as e:
            elapsed_ms = int((time.monotonic() - cycle_start) * 1000)
            logger.error("训练管线失败: %s", e, exc_info=True)

            training_run.status = "failed"
            training_run.duration_ms = elapsed_ms
            training_run.error_message = str(e)
            training_run.completed_at = datetime.now(timezone.utc)

            # 记录失败事件
            event = GaiaEvolutionEvent(
                event_type="training_failed",
                event_source=trigger,
                description=f"训练管线失败: {e!s}",
                metadata={"error": str(e), "duration_ms": elapsed_ms},
                reference_type="training_run",
                reference_id=training_run_id,
            )
            db.add(event)

            return {
                "status": "failed",
                "training_run_id": training_run_id,
                "error": str(e),
                "duration_ms": elapsed_ms,
            }
