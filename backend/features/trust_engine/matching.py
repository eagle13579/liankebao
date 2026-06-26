"""
链客宝信任评分引擎 — 匹配引擎增强模块
========================================
迁移自旧版 trust_engine/matching.py，适配 chainke-full 0-1000 评分范围。

功能:
  Step 0 — 信任预过滤 (在匹配管线开始前)
  Step 7 — 信任加权修正 (在匹配管线结束后)

关联: matching_pipeline.py 中的 6 步评分管线
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from features.trust_engine.scoring import ScoreWeights
from features.trust_engine.tier import TrustTier, TrustLevel

logger = logging.getLogger(__name__)


# ── 配置 ──────────────────────────────────────────────────


@dataclass(frozen=True)
class MatchingConfig:
    """匹配引擎增强配置 (适配 0-1000 评分范围)"""

    # Step 0: 信任预过滤
    MIN_TRUST_FOR_MATCHING: float = 600.0   # 默认最低信任分要求 (对应旧版 60)
    LOW_EXPOSURE_THRESHOLD: float = 400.0   # 低于此值降权曝光 (对应旧版 40)
    LOW_EXPOSURE_WEIGHT: float = 0.5

    # Step 7: 信任加权
    TRUST_WEIGHT: float = ScoreWeights.TRUST_WEIGHT  # 0.15
    TOP_TRUST_BOOST: float = ScoreWeights.TOP_TRUST_BOOST  # 1.10
    TOP_TRUST_THRESHOLD: int = ScoreWeights.TOP_TRUST_THRESHOLD  # 900

    DEFAULT_MIN_TRUST: float = 0.0


# ── Step 0: 信任预过滤 ────────────────────────────────────


@dataclass
class PreFilterResult:
    """Step 0 预过滤结果"""

    passed: bool
    reason: str
    exposure_weight: float = 1.0
    trust_score: Optional[float] = None


def pre_filter_candidate(
    trust_score: float,
    min_trust_requirement: Optional[float] = None,
    config: Optional[MatchingConfig] = None,
) -> PreFilterResult:
    """Step 0: 信任预过滤 (PRD §4.3.3)

    在匹配管线开始时对候选方进行信任预过滤:
    1. 如果信任分 < 需求方最低要求 → 从候选池移除
    2. 如果信任分 < 400 → 标记为待完善，降低曝光权重50%

    Args:
        trust_score: 候选方的信任评分 [0, 1000]
        min_trust_requirement: 需求方最低信任要求 (None=不过滤)
        config: 匹配配置

    Returns:
        PreFilterResult
    """
    cfg = config or MatchingConfig()

    # 规则1: 低于需求方最低要求 → 移除
    if min_trust_requirement is not None and trust_score < min_trust_requirement:
        return PreFilterResult(
            passed=False,
            reason=(
                f"信任分 {trust_score:.1f} < 最低要求 {min_trust_requirement:.1f}, "
                f"已从候选池移除"
            ),
            trust_score=trust_score,
        )

    # 规则2: 低于低曝光阈值 → 降权
    if trust_score < cfg.LOW_EXPOSURE_THRESHOLD:
        return PreFilterResult(
            passed=True,
            reason=f"信任分 {trust_score:.1f} < {cfg.LOW_EXPOSURE_THRESHOLD:.0f}, 曝光权重降至 {cfg.LOW_EXPOSURE_WEIGHT}",
            exposure_weight=cfg.LOW_EXPOSURE_WEIGHT,
            trust_score=trust_score,
        )

    return PreFilterResult(
        passed=True,
        reason=f"信任分 {trust_score:.1f}, 正常曝光",
        trust_score=trust_score,
    )


# ── Step 7: 信任加权修正 ─────────────────────────────────


@dataclass
class PostWeightResult:
    """Step 7 加权修正结果"""

    original_score: float
    adjusted_score: float
    trust_boost: float
    boost_applied: float
    is_top_boosted: bool = False
    details: dict[str, Any] = field(default_factory=dict)


def post_weight_score(
    original_match_score: float,
    trust_score: float,
    config: Optional[MatchingConfig] = None,
) -> PostWeightResult:
    """Step 7: 信任加权修正 (PRD §4.3.3)

    在现有6步评分管线之后注入信任加权:
    1. trust_boost = trust_score / 1000 → [0.0, 1.0]
    2. if trust_boost > 0.6:
           final_score *= (1 + trust_boost × TRUST_WEIGHT)
    3. if trust_score >= 900:
           final_score *= 1.10  (顶级信任加成)

    Args:
        original_match_score: Step 6 输出的原始匹配分 [0, 1]
        trust_score: 候选方的信任评分 [0, 1000]
        config: 匹配配置

    Returns:
        PostWeightResult
    """
    cfg = config or MatchingConfig()
    trust_boost = trust_score / 1000.0  # [0.0, 1.0]
    adjusted = original_match_score
    boost_applied = 1.0
    is_top_boosted = False

    # 加权 (信任分 > 600 才激活)
    if trust_boost > 0.6:
        multiplier = 1.0 + trust_boost * cfg.TRUST_WEIGHT
        adjusted *= multiplier
        boost_applied = multiplier

    # 顶级信任额外加权
    if trust_score >= cfg.TOP_TRUST_THRESHOLD:
        adjusted *= cfg.TOP_TRUST_BOOST
        boost_applied *= cfg.TOP_TRUST_BOOST
        is_top_boosted = True

    adjusted = min(adjusted, 1.0)

    return PostWeightResult(
        original_score=original_match_score,
        adjusted_score=round(adjusted, 6),
        trust_boost=trust_boost,
        boost_applied=round(boost_applied, 6),
        is_top_boosted=is_top_boosted,
        details={
            "trust_score": trust_score,
            "trust_boost": round(trust_boost, 4),
            "base_multiplier": round(1.0 + trust_boost * cfg.TRUST_WEIGHT, 4)
            if trust_boost > 0.6
            else 1.0,
            "top_boost": cfg.TOP_TRUST_BOOST if is_top_boosted else 1.0,
        },
    )


# ── 完整的匹配增强管线 ────────────────────────────────────


@dataclass
class EnhancedMatchResult:
    """增强后的匹配结果"""

    candidate_id: Any
    original_score: float
    adjusted_score: float
    trust_score: float
    trust_tier: TrustLevel
    pre_filter: PreFilterResult
    post_weight: PostWeightResult


class TrustMatchingEnhancer:
    """信任匹配增强器

    封装 Step 0 + Step 7，提供完整的匹配增强管线。

    Usage:
        enhancer = TrustMatchingEnhancer()
        result = enhancer.enhance(
            candidate_id=42,
            original_match_score=0.85,
            trust_score=880.0,
            min_trust_requirement=600.0,
        )
        if result.pre_filter.passed:
            print(f"调整后匹配分: {result.adjusted_score}")
    """

    def __init__(self, config: Optional[MatchingConfig] = None) -> None:
        self.config = config or MatchingConfig()

    def enhance(
        self,
        candidate_id: Any,
        original_match_score: float,
        trust_score: float,
        min_trust_requirement: Optional[float] = None,
    ) -> EnhancedMatchResult:
        """执行完整的匹配增强管线 (Step 0 → Step 7)

        Args:
            candidate_id: 候选方ID
            original_match_score: Step 6 原始匹配分 [0, 1]
            trust_score: 信任评分 [0, 1000]
            min_trust_requirement: 需求方最低信任要求

        Returns:
            EnhancedMatchResult
        """
        # Step 0: 预过滤
        pre_filter = pre_filter_candidate(
            trust_score=trust_score,
            min_trust_requirement=min_trust_requirement,
            config=self.config,
        )

        if not pre_filter.passed:
            return EnhancedMatchResult(
                candidate_id=candidate_id,
                original_score=original_match_score,
                adjusted_score=0.0,
                trust_score=trust_score,
                trust_tier=TrustTier(trust_score).level,
                pre_filter=pre_filter,
                post_weight=PostWeightResult(
                    original_score=original_match_score,
                    adjusted_score=0.0,
                    trust_boost=trust_score / 1000.0,
                    boost_applied=0.0,
                ),
            )

        # Step 7: 加权修正
        post_weight = post_weight_score(
            original_match_score=original_match_score * pre_filter.exposure_weight,
            trust_score=trust_score,
            config=self.config,
        )

        return EnhancedMatchResult(
            candidate_id=candidate_id,
            original_score=original_match_score,
            adjusted_score=post_weight.adjusted_score,
            trust_score=trust_score,
            trust_tier=TrustTier(trust_score).level,
            pre_filter=pre_filter,
            post_weight=post_weight,
        )

    def sort_candidates(
        self,
        candidates: list[dict[str, Any]],
        trust_key: str = "trust_score",
        score_key: str = "match_score",
        min_trust: Optional[float] = None,
    ) -> list[EnhancedMatchResult]:
        """对候选列表执行增强排序

        Args:
            candidates: 候选列表，每项需包含 trust_score 和 match_score
            trust_key: 信任分字段名
            score_key: 匹配分字段名
            min_trust: 最低信任要求

        Returns:
            按调整后分数降序排列的增强结果列表
        """
        enhanced = []
        for cand in candidates:
            trust_score = cand.get(trust_key, 0.0)
            match_score = cand.get(score_key, 0.0)
            result = self.enhance(
                candidate_id=cand.get("id"),
                original_match_score=match_score,
                trust_score=trust_score,
                min_trust_requirement=min_trust,
            )
            enhanced.append(result)

        enhanced.sort(key=lambda r: r.adjusted_score, reverse=True)
        return enhanced

    @staticmethod
    def format_ranking(
        results: list[EnhancedMatchResult],
        top_n: int = 10,
    ) -> str:
        """格式化排名输出（调试/日志用）"""
        lines = ["┌─────────┬──────┬──────┬──────┬──────────────────────────┐"]
        lines.append("│ Rank    │ Trust│ Orig │ Adj  │ Note                     │")
        lines.append("├─────────┼──────┼──────┼──────┼──────────────────────────┤")
        for i, r in enumerate(results[:top_n], 1):
            if r.pre_filter.passed:
                note = f"{r.trust_tier.value} 曝光={r.pre_filter.exposure_weight}"
            else:
                note = f"❌ {r.pre_filter.reason[:30]}"
            lines.append(
                f"│ {i:<7} │ {r.trust_score:<4.0f} │ "
                f"{r.original_score:.3f} │ {r.adjusted_score:.3f} │ {note:<24} │"
            )
        lines.append("└─────────┴──────┴──────┴──────┴──────────────────────────┘")
        return "\n".join(lines)
