"""Trust-Enhanced Matching — integrates trust tiers into match results"""

import logging

logger = logging.getLogger(__name__)


class TrustMatchingEnhancer:
    """
    Enhances match results with trust information.
    Bridges trust_engine (app/trust_engine.py) with matching_engine.
    """

    @staticmethod
    def enhance_match_result(match: dict, trust_data: dict | None = None) -> dict:
        """Add trust tier and match level to a match result"""
        if trust_data:
            match["trust_tier"] = trust_data.get("trust_tier", "bronze")
            match["match_level"] = trust_data.get("match_level", "manual")
            match["total_score"] = trust_data.get("total_score", 0)
        else:
            match["trust_tier"] = "bronze"
            match["match_level"] = "manual"
            match["total_score"] = 0
        return match

    @staticmethod
    def filter_by_match_level(
        matches: list[dict],
        min_level: str = "manual",
    ) -> list[dict]:
        """Filter matches by minimum match level requirement"""
        level_order = {"instant": 3, "assisted": 2, "manual": 1}
        min_val = level_order.get(min_level, 1)
        return [m for m in matches if level_order.get(m.get("match_level", "manual"), 1) >= min_val]

    @staticmethod
    def rank_by_trust(matches: list[dict]) -> list[dict]:
        """Rank matches combining match_score and trust_score"""

        def _combined_key(m: dict) -> float:
            match_score = m.get("match_score", 0.0)
            total_score = m.get("total_score", 0)
            trust_norm = total_score / 1000.0  # normalize to 0-1
            return match_score * 0.7 + trust_norm * 0.3

        return sorted(matches, key=_combined_key, reverse=True)
