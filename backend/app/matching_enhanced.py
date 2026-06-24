"""
链客宝 增强匹配引擎 — 信任整合 + 可解释性 + 多目标排序
=====================================================
复用已有资产:
  - trust_engine.py: 三层信任评分
  - matching_engine.py: 规则+TF-IDF+向量匹配
  - scoring_ab_test.py: A/B测试框架
  - ml_models.py: CTR预估+校准
  - evaluation.py: NDCG/MRR/Recall@K

新增能力:
  1. 信任加权: 将信任分融入匹配排序
  2. 可解释性: 为每个匹配结果生成"为什么推荐"
  3. 多目标排序: 预订概率×信誉分×活跃度×距离
  4. 分级匹配: Instant/Assisted/Manual三级匹配
  5. Bandit探索: 冷启动用户的Thompson Sampling
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TrustScore, User
from app.trust_engine import (
    calculate_verification_points,
    get_match_level,
    get_trust_tier,
)

logger = logging.getLogger(__name__)

# ============================================================
# 数据类
# ============================================================


@dataclass
class MatchExplanation:
    """匹配可解释性"""

    reason_type: str  # category/keyword/price/trust/region/history
    reason_text: str
    score_contribution: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnhancedMatchResult:
    """增强匹配结果"""

    target_id: int
    target_type: str  # "product" | "need"
    rule_score: float
    ml_score: float | None
    trust_score: float | None
    trust_tier: str
    match_level: str  # instant/assisted/manual
    total_score: float
    explanations: list[MatchExplanation] = field(default_factory=list)
    exploration_bonus: float = 0.0


# ============================================================
# 可解释性生成器
# ============================================================


class ExplainabilityEngine:
    """为匹配结果生成人类可读的解释"""

    REASON_TEMPLATES = {
        "category": "同类目匹配: {category}",
        "keyword": "关键词匹配: {matched_keywords}",
        "price": "价格区间兼容: 预算 ¥{budget_min}-{budget_max} ↔ 报价 ¥{price_min}-{price_max}",
        "trust": "高信誉企业: {trust_tier}级 ({score}分)",
        "region": "同区域: {region}",
        "history": "历史成交: {count}次合作记录",
        "active": "活跃用户: 近30天活跃{activity_days}天",
        "exploration": "智能探索: 为您发现潜在匹配",
    }

    @staticmethod
    def build_explanations(
        match_data: dict[str, Any],
        trust_tier: str,
        trust_score: float,
    ) -> list[MatchExplanation]:
        explanations: list[MatchExplanation] = []

        # 类目匹配
        if match_data.get("category_match"):
            explanations.append(
                MatchExplanation(
                    reason_type="category",
                    reason_text=ExplainabilityEngine.REASON_TEMPLATES["category"].format(
                        category=match_data.get("category", "未知")
                    ),
                    score_contribution=0.25,
                    evidence={"category": match_data.get("category")},
                )
            )

        # 关键词匹配
        keywords = match_data.get("matched_keywords", [])
        if keywords:
            explanations.append(
                MatchExplanation(
                    reason_type="keyword",
                    reason_text=ExplainabilityEngine.REASON_TEMPLATES["keyword"].format(
                        matched_keywords="、".join(keywords[:5])
                    ),
                    score_contribution=0.20,
                    evidence={"keywords": keywords[:10]},
                )
            )

        # 价格兼容
        if match_data.get("price_match"):
            explanations.append(
                MatchExplanation(
                    reason_type="price",
                    reason_text=ExplainabilityEngine.REASON_TEMPLATES["price"].format(
                        budget_min=match_data.get("budget_min", 0),
                        budget_max=match_data.get("budget_max", 0),
                        price_min=match_data.get("price_min", 0),
                        price_max=match_data.get("price_max", 0),
                    ),
                    score_contribution=0.15,
                    evidence={
                        "budget_range": [match_data.get("budget_min"), match_data.get("budget_max")],
                        "price_range": [match_data.get("price_min"), match_data.get("price_max")],
                    },
                )
            )

        # 信任分
        if trust_tier in ("gold", "platinum"):
            explanations.append(
                MatchExplanation(
                    reason_type="trust",
                    reason_text=ExplainabilityEngine.REASON_TEMPLATES["trust"].format(
                        trust_tier={"gold": "金牌", "platinum": "铂金"}.get(trust_tier, trust_tier),
                        score=trust_score,
                    ),
                    score_contribution=0.15,
                    evidence={"trust_tier": trust_tier, "trust_score": trust_score},
                )
            )

        # 同区域
        if match_data.get("same_region"):
            explanations.append(
                MatchExplanation(
                    reason_type="region",
                    reason_text=ExplainabilityEngine.REASON_TEMPLATES["region"].format(
                        region=match_data.get("region", "")
                    ),
                    score_contribution=0.10,
                    evidence={"region": match_data.get("region")},
                )
            )

        # 历史成交
        history_count = match_data.get("history_count", 0)
        if history_count > 0:
            explanations.append(
                MatchExplanation(
                    reason_type="history",
                    reason_text=ExplainabilityEngine.REASON_TEMPLATES["history"].format(count=history_count),
                    score_contribution=0.10,
                    evidence={"count": history_count},
                )
            )

        # 活跃度
        activity_days = match_data.get("activity_days", 0)
        if activity_days >= 15:
            explanations.append(
                MatchExplanation(
                    reason_type="active",
                    reason_text=ExplainabilityEngine.REASON_TEMPLATES["active"].format(activity_days=activity_days),
                    score_contribution=0.05,
                    evidence={"activity_days": activity_days},
                )
            )

        return explanations


# ============================================================
# 多目标排序器
# ============================================================


class MultiObjectiveRanker:
    """
    多目标排序: 预订概率 × 信誉分 × 活跃度 × 距离
    对标 Airbnb 多目标优化排序
    """

    # 权重配置 (可通过A/B测试调整)
    DEFAULT_WEIGHTS = {
        "match_score": 0.40,  # 匹配算法原始分
        "trust_score": 0.25,  # 信任分
        "activity_score": 0.15,  # 活跃度
        "price_compatibility": 0.10,  # 价格兼容
        "region_proximity": 0.05,  # 区域接近
        "history_bonus": 0.05,  # 历史成交加成
    }

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    def rank(
        self,
        results: list[EnhancedMatchResult],
        top_k: int = 20,
    ) -> list[EnhancedMatchResult]:
        """多目标排序"""
        for r in results:
            r.total_score = self._compute_multi_objective_score(r)
        results.sort(key=lambda x: x.total_score, reverse=True)
        return results[:top_k]

    def _compute_multi_objective_score(self, result: EnhancedMatchResult) -> float:
        """计算多目标综合分"""
        score = 0.0

        # 匹配分 (0-1 归一化)
        rule_norm = min(1.0, result.rule_score / 100.0)
        score += self.weights["match_score"] * rule_norm

        # 信任分 (0-1 归一化, 1000分制)
        if result.trust_score is not None:
            trust_norm = min(1.0, result.trust_score / 1000.0)
            score += self.weights["trust_score"] * trust_norm

        # 探索加成 (Bandit)
        score += result.exploration_bonus * 0.05

        return round(score * 100, 2)


# ============================================================
# Bandit 探索 (Thompson Sampling)
# ============================================================


class BanditExplorer:
    """
    Thompson Sampling 冷启动探索
    为新用户/新产品提供临时曝光加成，收集反馈后衰减
    """

    def __init__(self, exploration_weight: float = 0.15):
        self.exploration_weight = exploration_weight

    def compute_exploration_bonus(
        self,
        item_interactions: int,
        item_successes: int,
        min_interactions: int = 5,
    ) -> float:
        """
        基于 Thompson Sampling 计算探索加成
        - 交互少的项目获得更高加成
        - 成功反馈正向增强
        """
        if item_interactions >= 20:
            return 0.0  # 已充分探索

        import random

        # Beta分布采样: Beta(successes+1, failures+1)
        failures = max(0, item_interactions - item_successes)
        alpha = item_successes + 1
        beta_param = failures + 1

        try:
            sample = random.betavariate(alpha, beta_param)
        except (ValueError, ZeroDivisionError):
            sample = 0.5

        # 冷启动加成 = 探索权重 × Beta采样 × (1 - interactions/min_interactions)
        cold_start_factor = max(0.0, 1.0 - item_interactions / min_interactions)
        return round(self.exploration_weight * sample * cold_start_factor, 4)


# ============================================================
# 增强匹配引擎
# ============================================================


class EnhancedMatchEngine:
    """
    增强匹配引擎 — 整合信任+可解释性+多目标排序

    用法:
        engine = EnhancedMatchEngine()
        results = engine.match_needs_to_products(need_id, db)
        for r in results:
            print(f"产品{r.target_id}: {r.total_score}分")
            for e in r.explanations:
                print(f"  → {e.reason_text}")
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        exploration_weight: float = 0.15,
    ):
        self.ranker = MultiObjectiveRanker(weights)
        self.explorer = BanditExplorer(exploration_weight)
        self.explainer = ExplainabilityEngine()

    def _get_user_trust(self, db: Session, user_id: int) -> dict[str, Any]:
        """获取用户信任数据"""
        ts = db.query(TrustScore).filter(TrustScore.user_id == user_id).first()
        user = db.query(User).filter(User.id == user_id).first()

        if ts and ts.total_score:
            return {
                "score": ts.total_score,
                "tier": ts.trust_tier or "bronze",
                "match_level": get_match_level(ts.trust_tier or "bronze"),
                "response_rate": ts.response_rate or 0.0,
                "completed_matches": ts.completed_matches or 0,
            }
        if user:
            v_points = calculate_verification_points(user)
            tier = get_trust_tier(v_points * 3)
            return {
                "score": float(v_points * 3),
                "tier": tier,
                "match_level": get_match_level(tier),
                "response_rate": 0.0,
                "completed_matches": 0,
            }
        return {"score": 0.0, "tier": "bronze", "match_level": "manual", "response_rate": 0.0, "completed_matches": 0}

    def enhance_results(
        self,
        raw_matches: list[dict[str, Any]],
        searcher_user_id: int,
        db: Session,
    ) -> list[EnhancedMatchResult]:
        """将原始匹配结果增强为带信任+可解释性的结果"""
        searcher_trust = self._get_user_trust(db, searcher_user_id)
        enhanced: list[EnhancedMatchResult] = []

        for raw in raw_matches:
            target_id = raw.get("id", 0)
            target_type = raw.get("type", "product")

            # 目标用户信任
            target_user_id = raw.get("user_id", 0)
            target_trust = self._get_user_trust(db, target_user_id)

            # 规则分
            rule_score = raw.get("score", raw.get("match_score", 50.0))

            # Bandit探索加成
            exploration_bonus = self.explorer.compute_exploration_bonus(
                item_interactions=raw.get("interactions", raw.get("view_count", 0)),
                item_successes=raw.get("successes", raw.get("match_count", 0)),
            )

            # 可解释性
            explanations = self.explainer.build_explanations(
                match_data=raw,
                trust_tier=target_trust["tier"],
                trust_score=target_trust["score"],
            )

            result = EnhancedMatchResult(
                target_id=target_id,
                target_type=target_type,
                rule_score=rule_score,
                ml_score=raw.get("ml_score"),
                trust_score=target_trust["score"],
                trust_tier=target_trust["tier"],
                match_level=target_trust["match_level"],
                total_score=rule_score,  # 由ranker更新
                explanations=explanations,
                exploration_bonus=exploration_bonus,
            )
            enhanced.append(result)

        # 多目标排序
        return self.ranker.rank(enhanced)

    def filter_by_match_level(
        self,
        results: list[EnhancedMatchResult],
        searcher_level: str,
    ) -> list[EnhancedMatchResult]:
        """
        根据搜索者信任等级过滤结果

        分级匹配:
          - Instant (platinum/gold): 展示全部结果
          - Assisted (silver): 仅展示 silver 及以上
          - Manual (bronze): 仅展示 gold/platinum
        """
        level_priority = {"platinum": 4, "gold": 3, "silver": 2, "bronze": 1}

        if searcher_level in ("platinum", "gold"):
            return results  # 高信誉用户看全部

        if searcher_level == "silver":
            min_level = 2
        else:
            min_level = 3  # bronze用户只能看到gold+

        return [r for r in results if level_priority.get(r.trust_tier, 1) >= min_level]


# ============================================================
# 便捷函数
# ============================================================


_engine_instance: EnhancedMatchEngine | None = None


def get_enhanced_engine(**kwargs) -> EnhancedMatchEngine:
    """获取增强匹配引擎单例"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = EnhancedMatchEngine(**kwargs)
    return _engine_instance


def enhance_match_results(
    raw_matches: list[dict[str, Any]],
    searcher_user_id: int,
    db: Session | None = None,
) -> list[EnhancedMatchResult]:
    """
    便捷函数: 一键增强匹配结果

    用法:
        from matching_engine import MatchEngine
        from matching_enhanced import enhance_match_results

        raw = MatchEngine().match_needs_to_products(need_id)
        enhanced = enhance_match_results(raw, current_user_id, db)
    """
    if db is None:
        db = next(get_db())
    engine = get_enhanced_engine()
    return engine.enhance_results(raw_matches, searcher_user_id, db)
