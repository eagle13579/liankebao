"""
AI数字名片 实时推荐引擎
=======================
基于用户行为 + 关系图谱 + 语义相似度的多维度实时推荐。

推荐算法:
  1. 协同过滤: 基于标签供需匹配的协同推荐 (40%)
  2. 关系图谱: 基于知识图谱的社交关系推荐 (30%)
  3. 语义相似: 基于向量搜索的语义相似推荐 (30%)

功能:
  - 个人推荐: 为指定用户生成个性化推荐列表
  - 发现推荐: 全局发现页推荐
  - 相似名片: 基于特定用户/画册的相似推荐
  - 混合排序: 多维度分数加权融合

反馈闭环集成:
  - 用户对推荐结果的 👍/👎/⭐ 反馈影响后续推荐排序
  - 通过 FeedbackLoop.get_feedback_boost() 获取权重乘数
  - 反馈权重的范围为 [0.6, 1.5]
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.feedback_loop import apply_feedback_boost, get_feedback_loop
from app.ai.knowledge_graph import CachedKnowledgeGraphBuilder, KnowledgeGraphBuilder
from app.ai.vector_search import VectorSearchEngine, cosine_similarity
from app.cache import cache
from app.models.brochure import Brochure
from app.models.tag import MatchRecord, UserTag
from app.models.trust import TrustNetwork
from app.models.user import User
from app.models.visitor import VisitorLog

logger = logging.getLogger(__name__)


# ======================================================================
# 数据模型
# ======================================================================


@dataclass
class RecommendItem:
    """推荐条目"""
    user_id: int
    name: str
    company: str = ""
    title: str = ""
    avatar: str = ""
    intro: str = ""
    score: float = 0.0
    tag_match_score: float = 0.0
    graph_score: float = 0.0
    semantic_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    common_tags: list[str] = field(default_factory=list)
    match_type: str = "mixed"  # tag | graph | semantic | mixed

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "company": self.company,
            "title": self.title,
            "avatar": self.avatar,
            "intro": self.intro[:300] if self.intro else "",
            "score": round(self.score, 4),
            "tag_match_score": round(self.tag_match_score, 4),
            "graph_score": round(self.graph_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "reasons": self.reasons,
            "common_tags": self.common_tags,
            "match_type": self.match_type,
        }


@dataclass
class RecommendResult:
    """推荐结果"""
    items: list[RecommendItem] = field(default_factory=list)
    total: int = 0
    strategy_used: str = ""

    def to_dict(self) -> dict:
        return {
            "items": [i.to_dict() for i in self.items],
            "total": self.total,
            "strategy_used": self.strategy_used,
        }


# ======================================================================
# 推荐引擎
# ======================================================================


class RecommendEngine:
    """实时推荐引擎 - 多维度混合推荐"""

    WEIGHT_TAG_MATCH = 0.40   # 标签匹配权重 (默认, 在线学习会覆盖)
    WEIGHT_GRAPH = 0.30       # 图谱社交权重 (默认)
    WEIGHT_SEMANTIC = 0.30    # 语义相似权重 (默认)
    _online_weights_loaded = False

    def __init__(self, db: AsyncSession):
        self.db = db
        self.graph_builder = CachedKnowledgeGraphBuilder(db)
        self.vector_engine = VectorSearchEngine(db)
        self._load_online_weights()

    @classmethod
    def _load_online_weights(cls):
        """从在线学习引擎加载调整后的权重"""
        if cls._online_weights_loaded:
            return
        try:
            from app.ai.online_learning import get_online_weight
            w_tag = get_online_weight("tag_match")
            w_graph = get_online_weight("graph")
            w_semantic = get_online_weight("semantic")
            if w_tag and w_graph and w_semantic:
                cls.WEIGHT_TAG_MATCH = w_tag
                cls.WEIGHT_GRAPH = w_graph
                cls.WEIGHT_SEMANTIC = w_semantic
                logger.info(
                    "在线学习权重已加载: tag=%.4f, graph=%.4f, semantic=%.4f",
                    w_tag, w_graph, w_semantic,
                )
            cls._online_weights_loaded = True
        except Exception as e:
            logger.debug("在线学习权重加载跳过: %s", e)

    @classmethod
    def refresh_online_weights(cls):
        """重新从在线学习引擎加载权重 (运行时权重热更新)"""
        try:
            from app.ai.online_learning import get_online_weight
            w_tag = get_online_weight("tag_match")
            w_graph = get_online_weight("graph")
            w_semantic = get_online_weight("semantic")
            if w_tag and w_graph and w_semantic:
                old_tag, old_graph, old_semantic = (
                    cls.WEIGHT_TAG_MATCH, cls.WEIGHT_GRAPH, cls.WEIGHT_SEMANTIC,
                )
                cls.WEIGHT_TAG_MATCH = w_tag
                cls.WEIGHT_GRAPH = w_graph
                cls.WEIGHT_SEMANTIC = w_semantic
                logger.info(
                    "在线学习权重热更新: tag=%.4f→%.4f, graph=%.4f→%.4f, semantic=%.4f→%.4f",
                    old_tag, w_tag, old_graph, w_graph, old_semantic, w_semantic,
                )
                return True
        except Exception as e:
            logger.warning("在线学习权重热更新失败: %s", e)
        return False

    async def personalize_recommend(
        self,
        user_id: int,
        top_k: int = 20,
        exclude_ids: list[int] | None = None,
        strategy: str = "hybrid",
    ) -> RecommendResult:
        """个性化推荐 - 为指定用户生成推荐列表

        Args:
            user_id: 目标用户 ID
            top_k: 返回数量
            exclude_ids: 排除的用户 ID 列表（如已匹配用户）
            strategy: 推荐策略 (tag | graph | semantic | hybrid)

        Returns:
            RecommendResult
        """
        exclude_set = set(exclude_ids or [])
        exclude_set.add(user_id)

        # 获取当前用户信息
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            return RecommendResult(strategy_used=strategy)

        # 各维度并行评分
        import asyncio

        tag_scores = {}
        graph_scores = {}
        semantic_scores = {}

        tasks = []
        if strategy in ("tag", "hybrid"):
            tasks.append(self._score_by_tag_match(user_id, exclude_set))
        if strategy in ("graph", "hybrid"):
            tasks.append(self._score_by_graph(user_id, exclude_set))
        if strategy in ("semantic", "hybrid"):
            tasks.append(self._score_by_semantic(user_id, exclude_set))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, dict):
                if "tag" in str(r.get("type", "")):
                    tag_scores = r.get("scores", {})
                elif "graph" in str(r.get("type", "")):
                    graph_scores = r.get("scores", {})
                elif "semantic" in str(r.get("type", "")):
                    semantic_scores = r.get("scores", {})
            elif isinstance(r, tuple):
                # 兼容直接返回 (scores_dict, type_str)
                scores, score_type = r
                if score_type == "tag":
                    tag_scores = scores
                elif score_type == "graph":
                    graph_scores = scores
                elif score_type == "semantic":
                    semantic_scores = scores

        # 融合评分
        all_candidates = set(tag_scores.keys()) | set(graph_scores.keys()) | set(semantic_scores.keys())
        all_candidates -= exclude_set

        # 在线学习 & 数据网络效应
        _aff_tracker = OnlineLearningTracker()
        _aff_weights = _aff_tracker.get_user_affinities(user_id)
        _network_aff = _aff_tracker.get_network_affinities(user_id, depth=2)
        _trending = _aff_tracker.get_trending_tags(hours=24)
        _trending_max = max(_trending.values()) if _trending else 1

        items = []
        for cid in all_candidates:
            t_score = tag_scores.get(cid, 0.0)
            g_score = graph_scores.get(cid, 0.0)
            s_score = semantic_scores.get(cid, 0.0)

            # 加权融合
            if strategy == "tag":
                final_score = t_score
            elif strategy == "graph":
                final_score = g_score
            elif strategy == "semantic":
                final_score = s_score
            else:  # hybrid
                final_score = (
                    self.WEIGHT_TAG_MATCH * t_score
                    + self.WEIGHT_GRAPH * g_score
                    + self.WEIGHT_SEMANTIC * s_score
                )

            # 在线学习调整：行为权重提升 [1.0, 1.3]
            _boost = _aff_weights.get(cid, 1.0)
            if _boost > 1.0:
                final_score = final_score * _boost

            # 数据网络效应提升 [1.0, 1.2]
            # 协同过滤：与当前用户有共同点击模式的目标加权
            # 热门推荐：近期被高频点击的目标加权
            _network_boost = 1.0
            if cid in _network_aff:
                _network_boost = max(_network_boost, 1.0 + 0.15 * _network_aff[cid])
            if cid in _trending:
                _trending_ratio = _trending[cid] / _trending_max
                _network_boost = max(_network_boost, 1.0 + 0.15 * min(1.0, _trending_ratio))
            if _network_boost > 1.0:
                final_score = final_score * _network_boost

            # 反馈闭环调整: 用户对推荐结果的 👍/👎/⭐ 评分影响
            # 权重范围 [0.6, 1.5]，来自 FeedbackLoop 的 SQLite 持久化权重
            _feedback_boost = get_feedback_loop().get_feedback_boost(user_id, cid)
            if _feedback_boost != 1.0:
                final_score = final_score * _feedback_boost

            # 获取用户详情
            item = await self._build_recommend_item(cid, final_score, t_score, g_score, s_score)
            if item:
                items.append(item)

        # 排序
        items.sort(key=lambda x: x.score, reverse=True)

        return RecommendResult(
            items=items[:top_k],
            total=len(items),
            strategy_used=strategy,
        )

    async def _score_by_tag_match(
        self,
        user_id: int,
        exclude_set: set[int],
    ) -> tuple[dict[int, float], str]:
        """标签匹配评分 - 供需匹配度"""
        # 获取当前用户的 provide/need 标签
        result = await self.db.execute(
            select(UserTag).where(UserTag.user_id == user_id)
        )
        my_tags = result.scalars().all()
        my_provide = {t.tag: t.weight for t in my_tags if t.tag_type == "provide"}
        my_need = {t.tag: t.weight for t in my_tags if t.tag_type == "need"}

        if not my_provide and not my_need:
            return {}, "tag"

        scores = {}

        # 对每个标签查找匹配用户
        for tag, weight in my_provide.items():
            result = await self.db.execute(
                select(UserTag).where(
                    UserTag.tag == tag,
                    UserTag.tag_type == "need",
                    UserTag.user_id.not_in(list(exclude_set)),
                ).limit(50)
            )
            for ut in result.scalars().all():
                scores[ut.user_id] = scores.get(ut.user_id, 0) + weight * ut.weight

        for tag, weight in my_need.items():
            result = await self.db.execute(
                select(UserTag).where(
                    UserTag.tag == tag,
                    UserTag.tag_type == "provide",
                    UserTag.user_id.not_in(list(exclude_set)),
                ).limit(50)
            )
            for ut in result.scalars().all():
                scores[ut.user_id] = scores.get(ut.user_id, 0) + weight * ut.weight

        # 归一化到 [0, 1]
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                scores = {k: v / max_score for k, v in scores.items()}

        return scores, "tag"

    async def _score_by_graph(
        self,
        user_id: int,
        exclude_set: set[int],
    ) -> tuple[dict[int, float], str]:
        """图谱社交评分 - 基于关系图谱"""
        candidates = await self.graph_builder.get_recommendation_candidates(user_id, max_candidates=100)

        scores = {}
        for c in candidates:
            cid = c.get("properties", {}).get("user_id")
            if cid and cid not in exclude_set:
                scores[cid] = c.get("recommendation_score", 0)

        # 归一化
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                scores = {k: v / max_score for k, v in scores.items()}

        return scores, "graph"

    async def _score_by_semantic(
        self,
        user_id: int,
        exclude_set: set[int],
    ) -> tuple[dict[int, float], str]:
        """语义相似评分 - 基于向量搜索"""
        try:
            # 构建用户查询文本
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            if not user:
                return {}, "semantic"

            query_parts = []
            if user.intro:
                query_parts.append(user.intro)
            if user.company:
                query_parts.append(user.company)
            if user.title:
                query_parts.append(user.title)

            # 获取用户标签
            result = await self.db.execute(
                select(UserTag).where(UserTag.user_id == user_id)
            )
            tags = result.scalars().all()
            tag_texts = [t.tag for t in tags]
            if tag_texts:
                query_parts.extend(tag_texts)

            query = " ".join(query_parts) if query_parts else user.name

            # 向量搜索
            search_results = await self.vector_engine.search(query=query, top_k=50, min_score=0.0)

            scores = {}
            for r in search_results:
                uid = r.get("user_id")
                score = r.get("score", 0.0)
                if uid and uid not in exclude_set:
                    scores[uid] = score

            return scores, "semantic"
        except Exception as e:
            logger.warning(f"Semantic scoring failed: {e}")
            return {}, "semantic"

    async def _build_recommend_item(
        self,
        user_id: int,
        final_score: float,
        tag_score: float,
        graph_score: float,
        semantic_score: float,
    ) -> Optional[RecommendItem]:
        """构建推荐条目"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            return None

        # 确定匹配类型
        scores_map = {
            "tag": tag_score,
            "graph": graph_score,
            "semantic": semantic_score,
        }
        match_type = max(scores_map, key=scores_map.get)

        # 构建理由
        reasons = []
        if tag_score > 0.3:
            reasons.append("标签供需匹配度高")
        if graph_score > 0.3:
            reasons.append("有共同社交关系链")
        if semantic_score > 0.3:
            reasons.append("业务描述语义相似")

        if not reasons:
            reasons.append("综合匹配")

        # 获取共同标签
        common_tags = []
        result = await self.db.execute(
            select(UserTag).where(UserTag.user_id == user_id)
        )
        common_tags = [t.tag for t in result.scalars().all()[:5]]

        return RecommendItem(
            user_id=user.id,
            name=user.name,
            company=user.company,
            title=user.title,
            avatar=user.avatar,
            intro=user.intro,
            score=final_score,
            tag_match_score=tag_score,
            graph_score=graph_score,
            semantic_score=semantic_score,
            reasons=reasons,
            common_tags=common_tags,
            match_type=match_type,
        )

    async def discover(
        self,
        user_id: int,
        top_k: int = 30,
        purpose: str | None = None,
    ) -> RecommendResult:
        """发现推荐 - 发现页全局推荐

        Args:
            user_id: 当前用户 ID
            top_k: 返回数量
            purpose: 筛选用途 (partner/client/investor/supplier)

        Returns:
            RecommendResult
        """
        # 获取所有活跃用户（排除当前用户）
        query = select(User).where(User.id != user_id)

        if purpose:
            # 通过画册用途筛选
            result = await self.db.execute(
                select(Brochure.user_id).where(
                    Brochure.purpose == purpose,
                    Brochure.status == "published",
                ).distinct()
            )
            user_ids = [row for row in result.scalars().all()]
            if user_ids:
                query = query.where(User.id.in_(user_ids))
            else:
                return RecommendResult(strategy_used="discover")

        result = await self.db.execute(query.limit(100))
        users = result.scalars().all()

        # 获取用户标签用于计算匹配度
        result = await self.db.execute(
            select(UserTag).where(UserTag.user_id == user_id)
        )
        my_tags = result.scalars().all()
        my_provide = {t.tag: t.weight for t in my_tags if t.tag_type == "provide"}
        my_need = {t.tag: t.weight for t in my_tags if t.tag_type == "need"}

        items = []
        for target_user in users:
            # 简单的标签匹配度计算
            result = await self.db.execute(
                select(UserTag).where(UserTag.user_id == target_user.id)
            )
            their_tags = result.scalars().all()
            their_provide = {t.tag: t.weight for t in their_tags if t.tag_type == "provide"}
            their_need = {t.tag: t.weight for t in their_tags if t.tag_type == "need"}

            score = 0.0
            common = []
            for tag, weight in my_provide.items():
                if tag in their_need:
                    score += weight * their_need[tag]
                    common.append(tag)
            for tag, weight in my_need.items():
                if tag in their_provide:
                    score += weight * their_provide[tag]
                    common.append(tag)

            if score > 0:
                items.append(RecommendItem(
                    user_id=target_user.id,
                    name=target_user.name,
                    company=target_user.company,
                    title=target_user.title,
                    avatar=target_user.avatar,
                    intro=target_user.intro,
                    score=score,
                    tag_match_score=score,
                    common_tags=list(set(common))[:5],
                    reasons=["标签匹配"] if common else ["推荐用户"],
                    match_type="tag",
                ))

        # 如果没有标签匹配，按活跃度推荐
        if not items:
            for target_user in users[:top_k]:
                items.append(RecommendItem(
                    user_id=target_user.id,
                    name=target_user.name,
                    company=target_user.company,
                    title=target_user.title,
                    avatar=target_user.avatar,
                    intro=target_user.intro,
                    score=0.5,
                    reasons=["发现用户"],
                    match_type="discover",
                ))

        items.sort(key=lambda x: x.score, reverse=True)
        return RecommendResult(items=items[:top_k], total=len(items), strategy_used="discover")

    async def similar_users(
        self,
        target_user_id: int,
        current_user_id: int,
        top_k: int = 10,
    ) -> RecommendResult:
        """相似名片推荐 - 基于指定用户查找相似用户

        Args:
            target_user_id: 目标用户（参考用户）
            current_user_id: 当前用户（用于排除自身）
            top_k: 返回数量

        Returns:
            RecommendResult
        """
        exclude_set = {target_user_id, current_user_id}

        # 1. 向量搜索：基于目标用户的内容找相似
        result = await self.db.execute(select(User).where(User.id == target_user_id))
        target_user = result.scalars().first()
        if not target_user:
            return RecommendResult(strategy_used="similar")

        query_parts = []
        if target_user.intro:
            query_parts.append(target_user.intro)
        if target_user.company:
            query_parts.append(target_user.company)
        if target_user.title:
            query_parts.append(target_user.title)

        result = await self.db.execute(
            select(UserTag).where(UserTag.user_id == target_user_id)
        )
        tags = result.scalars().all()
        query_parts.extend([t.tag for t in tags])

        query = " ".join(query_parts) if query_parts else target_user.name

        try:
            search_results = await self.vector_engine.search(query=query, top_k=top_k + 5, min_score=0.0)
        except Exception as e:
            logger.warning(f"Vector search for similar users failed: {e}")
            search_results = []

        # 2. 同行业推荐
        peer_scores = {}
        if target_user.company:
            result = await self.db.execute(
                select(User).where(
                    User.company == target_user.company,
                    User.id.not_in(list(exclude_set)),
                ).limit(10)
            )
            for peer in result.scalars().all():
                peer_scores[peer.id] = 0.9

        # 3. 相同标签推荐
        tag_scores = {}
        for t in tags:
            result = await self.db.execute(
                select(UserTag).where(
                    UserTag.tag == t.tag,
                    UserTag.user_id.not_in(list(exclude_set)),
                ).limit(5)
            )
            for ut in result.scalars().all():
                tag_scores[ut.user_id] = tag_scores.get(ut.user_id, 0) + t.weight

        if tag_scores:
            max_ts = max(tag_scores.values())
            if max_ts > 0:
                tag_scores = {k: v / max_ts for k, v in tag_scores.items()}

        # 合并所有候选
        all_candidates = {}
        for r in search_results:
            uid = r.get("user_id")
            if uid and uid not in exclude_set:
                all_candidates[uid] = all_candidates.get(uid, 0) + r.get("score", 0) * 0.5

        for uid, score in peer_scores.items():
            all_candidates[uid] = all_candidates.get(uid, 0) + score * 0.3

        for uid, score in tag_scores.items():
            all_candidates[uid] = all_candidates.get(uid, 0) + score * 0.2

        # 构建结果
        items = []
        sorted_ids = sorted(all_candidates.items(), key=lambda x: x[1], reverse=True)[:top_k]
        for cid, score in sorted_ids:
            item = await self._build_recommend_item(cid, score, tag_scores.get(cid, 0), 0, score)
            if item:
                items.append(item)

        return RecommendResult(items=items, total=len(items), strategy_used="similar")


# ======================================================================
# 在线学习引擎 - 行为追踪与权重调整
# ======================================================================

import sqlite3
import os
import time


class OnlineLearningTracker:
    """在线学习追踪器 - 基于用户行为调整推荐权重

    通过 SQLite 持久化记录用户的点击/分享行为，
    计算用户对不同对象的偏好权重，用于在线学习调整推荐评分。
    """

    DB_DIR = "data"

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = os.path.join(self.DB_DIR, "online_learning.db")
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS click_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_click_user ON click_events(user_id);
                CREATE INDEX IF NOT EXISTS idx_click_target ON click_events(target_id);

                CREATE TABLE IF NOT EXISTS share_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_share_user ON share_events(user_id);
                CREATE INDEX IF NOT EXISTS idx_share_target ON share_events(target_id);

                CREATE TABLE IF NOT EXISTS affinity_weights (
                    user_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (user_id, target_id)
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def track_click(self, user_id: int, target_id: int):
        """记录点击行为

        Args:
            user_id: 当前用户 ID
            target_id: 被点击的用户 ID
        """
        conn = self._get_conn()
        try:
            now = time.time()
            conn.execute(
                "INSERT INTO click_events (user_id, target_id, created_at) VALUES (?, ?, ?)",
                (user_id, target_id, now),
            )
            self._update_affinity(conn, user_id, target_id, event_type="click")
            conn.commit()
        finally:
            conn.close()

    def track_share(self, user_id: int, target_id: int):
        """记录分享行为

        Args:
            user_id: 当前用户 ID
            target_id: 被分享的用户 ID
        """
        conn = self._get_conn()
        try:
            now = time.time()
            conn.execute(
                "INSERT INTO share_events (user_id, target_id, created_at) VALUES (?, ?, ?)",
                (user_id, target_id, now),
            )
            self._update_affinity(conn, user_id, target_id, event_type="share")
            conn.commit()
        finally:
            conn.close()

    def _update_affinity(self, conn: sqlite3.Connection, user_id: int, target_id: int, event_type: str):
        """更新偏好权重

        点击权重 +0.05，分享权重 +0.15（分享比点击价值更高）
        上限 1.3，自然衰减回到 1.0
        """
        increment = 0.05 if event_type == "click" else 0.15
        now = time.time()

        row = conn.execute(
            "SELECT weight FROM affinity_weights WHERE user_id = ? AND target_id = ?",
            (user_id, target_id),
        ).fetchone()

        if row:
            current = row["weight"]
            # 时间衰减：超过7天未交互，权重向1.0回归
            old_row = conn.execute(
                "SELECT created_at FROM click_events WHERE user_id = ? AND target_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id, target_id),
            ).fetchone()
            if old_row and (now - old_row["created_at"]) > 7 * 86400:
                current = max(1.0, current - 0.1)
            new_weight = min(1.3, current + increment)
            conn.execute(
                "UPDATE affinity_weights SET weight = ?, updated_at = ? WHERE user_id = ? AND target_id = ?",
                (new_weight, now, user_id, target_id),
            )
        else:
            new_weight = min(1.3, 1.0 + increment)
            conn.execute(
                "INSERT OR REPLACE INTO affinity_weights (user_id, target_id, weight, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, target_id, new_weight, now),
            )

    def get_user_affinities(self, user_id: int) -> dict[int, float]:
        """获取用户偏好权重映射

        根据历史行为计算用户对不同对象的偏好权重。
        返回 { target_id: weight } 字典，weight 范围 [1.0, 1.3]。

        Args:
            user_id: 用户 ID

        Returns:
            dict[int, float]: 目标用户 ID 到偏好权重的映射
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT target_id, weight FROM affinity_weights WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return {row["target_id"]: row["weight"] for row in rows}
        finally:
            conn.close()

    def get_user_click_count(self, user_id: int, days: int = 30) -> int:
        """获取用户近期点击次数

        Args:
            user_id: 用户 ID
            days: 统计天数

        Returns:
            int: 点击次数
        """
        conn = self._get_conn()
        try:
            cutoff = time.time() - days * 86400
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM click_events WHERE user_id = ? AND created_at >= ?",
                (user_id, cutoff),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_user_share_count(self, user_id: int, days: int = 30) -> int:
        """获取用户近期分享次数

        Args:
            user_id: 用户 ID
            days: 统计天数

        Returns:
            int: 分享次数
        """
        conn = self._get_conn()
        try:
            cutoff = time.time() - days * 86400
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM share_events WHERE user_id = ? AND created_at >= ?",
                (user_id, cutoff),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def decay_old_weights(self, max_age_days: int = 30):
        """衰减旧权重 - 定期清理长时间未交互的权重数据

        Args:
            max_age_days: 超过此天数未更新的权重将重置为 1.0
        """
        conn = self._get_conn()
        try:
            cutoff = time.time() - max_age_days * 86400
            conn.execute(
                "UPDATE affinity_weights SET weight = 1.0, updated_at = ? WHERE updated_at < ?",
                (time.time(), cutoff),
            )
            conn.commit()
        finally:
            conn.close()

    def cleanup_old_events(self, max_age_days: int = 90):
        """清理旧事件记录 - 保留近期行为数据

        Args:
            max_age_days: 超过此天数的行为记录将被删除
        """
        conn = self._get_conn()
        try:
            cutoff = time.time() - max_age_days * 86400
            conn.execute("DELETE FROM click_events WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM share_events WHERE created_at < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 数据网络效应：协同过滤 + 热门标签
    # ------------------------------------------------------------------

    def get_network_affinities(self, user_id: int, depth: int = 2) -> dict[int, float]:
        """获取用户关联网络 — 协同过滤

        基于"喜欢X的人也喜欢Y"原理：
        1. 查找与当前用户点击过相同目标的其他"相似用户"
        2. 从相似用户点击过的目标中发现新目标
        3. depth=2 时扩展到二级关联（相似用户的相似用户）

        Args:
            user_id: 用户 ID
            depth: 关联深度 (1=直接关联, 2=二级关联)

        Returns:
            dict[int, float]: {target_id: affinity_score} 亲和度 [0, 1]
        """
        conn = self._get_conn()
        try:
            # 当前用户点击过的目标
            my_targets = set(
                r["target_id"] for r in conn.execute(
                    "SELECT DISTINCT target_id FROM click_events WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            )
            if not my_targets:
                return {}

            # 一级：找"相似用户"（点击过相同目标的其他用户）
            placeholders = ",".join("?" for _ in my_targets)
            similar_uids = set(
                r["user_id"] for r in conn.execute(
                    f"SELECT DISTINCT user_id FROM click_events "
                    f"WHERE target_id IN ({placeholders}) AND user_id != ?",
                    (*list(my_targets), user_id),
                ).fetchall()
            )
            if not similar_uids:
                return {}

            # 统计相似用户点击过的目标（协同过滤核心）
            su_ph = ",".join("?" for _ in similar_uids)
            rows = conn.execute(
                f"SELECT target_id, COUNT(DISTINCT user_id) AS user_cnt "
                f"FROM click_events "
                f"WHERE user_id IN ({su_ph}) "
                f"GROUP BY target_id ORDER BY user_cnt DESC",
                (*list(similar_uids),),
            ).fetchall()

            max_cnt = max((r["user_cnt"] for r in rows), default=1)
            affinities = {}
            for r in rows:
                tid = r["target_id"]
                if tid not in my_targets and tid != user_id:
                    affinities[tid] = r["user_cnt"] / max_cnt

            # 二级关联扩展
            if depth >= 2 and similar_uids:
                second_level_uids = set()
                for suid in similar_uids:
                    su_targets = set(
                        r["target_id"] for r in conn.execute(
                            "SELECT DISTINCT target_id FROM click_events WHERE user_id = ?",
                            (suid,),
                        ).fetchall()
                    )
                    if su_targets:
                        su_ph2 = ",".join("?" for _ in su_targets)
                        rows2 = conn.execute(
                            f"SELECT DISTINCT user_id FROM click_events "
                            f"WHERE target_id IN ({su_ph2}) "
                            f"AND user_id NOT IN (?, ?)",
                            (*list(su_targets), suid, user_id),
                        ).fetchall()
                        for r2 in rows2:
                            second_level_uids.add(r2["user_id"])

                if second_level_uids:
                    sl_ph = ",".join("?" for _ in second_level_uids)
                    rows_sl = conn.execute(
                        f"SELECT target_id, COUNT(DISTINCT user_id) AS user_cnt "
                        f"FROM click_events "
                        f"WHERE user_id IN ({sl_ph}) "
                        f"GROUP BY target_id ORDER BY user_cnt DESC",
                        (*list(second_level_uids),),
                    ).fetchall()
                    max_sl = max((r["user_cnt"] for r in rows_sl), default=1)
                    for r in rows_sl:
                        tid = r["target_id"]
                        if tid not in my_targets and tid != user_id and tid not in affinities:
                            affinities[tid] = 0.5 * (r["user_cnt"] / max_sl)  # 二级衰减

            return affinities
        finally:
            conn.close()

    def get_trending_tags(self, hours: int = 24) -> dict[int, int]:
        """获取热门目标 — 基于近期点击热度

        从最近 N 小时的点击数据中提取被点击最多的目标，
        用于冷启动推荐 — 新用户或缺乏行为数据的场景。

        Args:
            hours: 统计时间窗口（小时）

        Returns:
            dict[int, int]: {target_id: click_count} 按热度降序（最多50个）
        """
        conn = self._get_conn()
        try:
            cutoff = time.time() - hours * 3600
            rows = conn.execute(
                "SELECT target_id, COUNT(*) AS cnt FROM click_events "
                "WHERE created_at >= ? "
                "GROUP BY target_id ORDER BY cnt DESC LIMIT 50",
                (cutoff,),
            ).fetchall()
            return {row["target_id"]: row["cnt"] for row in rows}
        finally:
            conn.close()
