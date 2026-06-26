"""
链客宝 - 创新发现引擎
======================
自动扫描链客宝平台内的用户行为数据、企业需求数据、匹配数据，
发现未被满足的市场机会，推荐给平台运营。

MVP 版本支持以下核心能力：
1. 机会扫描 — 扫描匹配失败、未满足需求、搜索真空等信号
2. 趋势分析 — 分析品类热度、供需缺口、新兴领域
3. 机会推荐 — 排序、去重、生成可执行建议

使用方式:
    from features.innovation_engine import InnovationEngine

    engine = InnovationEngine()
    result = engine.run()

    # 查看推荐结果
    for opp in result.recommendation.opportunities[:5]:
        print(f"[{opp.priority}] {opp.title} (评分: {opp.score})")

模块结构:
    - opportunity_scanner.py: 机会扫描器
    - trend_analyzer.py: 趋势分析器
    - recommender.py: 机会推荐器
    - engine.py: 引擎编排器（统一入口）
"""

from .engine import EngineConfig, EngineResult, InnovationEngine, PipelineStage
from .opportunity_scanner import (
    MOCK_ENTERPRISES,
    MOCK_MATCHING_EVENTS,
    MOCK_NEEDS,
    MOCK_SEARCHES,
    OpportunityScanner,
    OpportunitySignal,
    ScanResult,
)
from .recommender import (
    ActionStep,
    OpportunityRecommender,
    RecommendationReport,
    RecommendedOpportunity,
)
from .trend_analyzer import TrendAnalyzer, TrendInsight, TrendReport

__all__ = [
    # Engine
    "InnovationEngine",
    "EngineConfig",
    "EngineResult",
    "PipelineStage",
    # Scanner
    "OpportunityScanner",
    "OpportunitySignal",
    "ScanResult",
    # Analyzer
    "TrendAnalyzer",
    "TrendInsight",
    "TrendReport",
    # Recommender
    "OpportunityRecommender",
    "RecommendedOpportunity",
    "RecommendationReport",
    "ActionStep",
    # Mock data (for testing/demo)
    "MOCK_NEEDS",
    "MOCK_MATCHING_EVENTS",
    "MOCK_SEARCHES",
    "MOCK_ENTERPRISES",
]

__version__ = "0.1.0"
