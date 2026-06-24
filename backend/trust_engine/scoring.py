"""Trust-based Scoring — adjusts match scores by trust level"""

import logging

logger = logging.getLogger(__name__)

TRUST_MULTIPLIERS = {
    "platinum": 1.15,  # +15% boost
    "gold": 1.08,  # +8% boost
    "silver": 1.0,  # neutral
    "bronze": 0.85,  # -15% penalty
    "none": 0.7,  # -30% penalty
}


class TrustScorer:
    """
    Adjusts match scores based on trust tier.
    Bridge between trust_engine (app/trust_engine.py) and matching_engine scoring.
    """

    @staticmethod
    def adjust_score(base_score: float, trust_tier: str = "none") -> float:
        """Apply trust multiplier to a base match score"""
        multiplier = TRUST_MULTIPLIERS.get(trust_tier, 1.0)
        adjusted = base_score * multiplier
        return max(0.0, min(1.0, adjusted))

    @staticmethod
    def get_trust_multiplier(trust_tier: str) -> float:
        """Get the multiplier value for a trust tier"""
        return TRUST_MULTIPLIERS.get(trust_tier, 1.0)
