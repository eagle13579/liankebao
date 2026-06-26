"""
链客宝信任评分引擎 (Trust Engine)
====================================

迁移自旧版链客宝 trust_engine，适配 chainke-full 现有模型。

核心模块:
  - scoring:   三维评分（认证可信度 + 行为可信度 + 担保可信度）
  - tier:      四级分级系统（bronze/silver/gold/platinum）
  - matching:  匹配引擎增强（Step 0 预过滤 + Step 7 加权）

设计哲学:
  H03 (合规进化): 合规资质透明化 = 撮合信任资产
  H08 (阳光下行走): 评分公式完全公开，越透明越没人质疑

Usage:
    from features.trust_engine.scoring import TrustScorer
    from features.trust_engine.tier import TrustTier
    from features.trust_engine.matching import TrustMatchingEnhancer

    scorer = TrustScorer()
    breakdown = scorer.calculate_breakdown(...)
    tier = TrustTier(breakdown.total).level
"""

from features.trust_engine.scoring import (
    TrustScorer,
    ScoreBreakdown,
    ScoreWeights,
    QualificationSubscores,
    TransactionSubscores,
    ComplianceSubscores,
    QualificationData,
    TransactionData,
    ComplianceData,
)
from features.trust_engine.tier import (
    TrustTier,
    TrustLevel,
    TierConfig,
    get_trust_tier,
    TIER_DEFINITIONS,
)
from features.trust_engine.matching import (
    TrustMatchingEnhancer,
    MatchingConfig,
    PreFilterResult,
    PostWeightResult,
    EnhancedMatchResult,
    pre_filter_candidate,
    post_weight_score,
)

__all__ = [
    "TrustScorer",
    "ScoreBreakdown",
    "ScoreWeights",
    "QualificationSubscores",
    "TransactionSubscores",
    "ComplianceSubscores",
    "QualificationData",
    "TransactionData",
    "ComplianceData",
    "TrustTier",
    "TrustLevel",
    "TierConfig",
    "get_trust_tier",
    "TIER_DEFINITIONS",
    "TrustMatchingEnhancer",
    "MatchingConfig",
    "PreFilterResult",
    "PostWeightResult",
    "EnhancedMatchResult",
    "pre_filter_candidate",
    "post_weight_score",
]

__version__ = "2.0.0"
