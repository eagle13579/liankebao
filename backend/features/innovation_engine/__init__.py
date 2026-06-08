"""
创新发现引擎 (Innovation Engine)
===================================
扫描未满足需求机会、分析行业趋势、交叉推荐高价值创新方向。

铁律六：只新增不覆盖，独立模块。
"""

from features.innovation_engine.engine import InnovationEngine, InnovationScanReport
from features.innovation_engine.opportunity_scanner import Opportunity, OpportunityScanner, OpportunityScanResult
from features.innovation_engine.trend_analyzer import Trend, TrendAnalyzer, TrendAnalysisResult
from features.innovation_engine.recommender import OpportunityRecommender, RecommendResult, Recommendation

# 导出默认 Engine 实例
default_engine = InnovationEngine()

__all__ = [
    "InnovationEngine",
    "InnovationScanReport",
    "Opportunity",
    "OpportunityScanner",
    "OpportunityScanResult",
    "Trend",
    "TrendAnalyzer",
    "TrendAnalysisResult",
    "OpportunityRecommender",
    "RecommendResult",
    "Recommendation",
    "default_engine",
]
