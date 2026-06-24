"""
链客宝信任评分引擎 (Trust Engine)
===================================

信任基础设施核心包，提供：
  - scoring:   三维评分（资质可信度40% + 交易可信度35% + 合规健康度25%）
  - tier:      五级分级系统（待完善/基础级/良好级/优秀级/顶级）
  - matching:  匹配引擎增强（Step 0 预过滤 + Step 7 加权）

设计哲学:
  H03 (合规进化): 合规资质透明化 = 撮合信任资产
  H08 (阳光下行走): 评分公式完全公开，越透明越没人质疑

Usage:
    from trust_engine.scoring import TrustScorer
    from trust_engine.tier import TrustTier
    from trust_engine.matching import TrustMatchingEnhancer

    scorer = TrustScorer()
    score = scorer.calculate(user_id=42, db_session=session)
    tier = TrustTier(score.total).level
"""

from trust_engine.scoring import TrustScorer, ScoreBreakdown, ScoreWeights
from trust_engine.tier import TrustTier, TrustLevel, TierConfig
from trust_engine.matching import TrustMatchingEnhancer, MatchingConfig

__all__ = [
    "TrustScorer",
    "ScoreBreakdown",
    "ScoreWeights",
    "TrustTier",
    "TrustLevel",
    "TierConfig",
    "TrustMatchingEnhancer",
    "MatchingConfig",
]

__version__ = "1.0.0"
