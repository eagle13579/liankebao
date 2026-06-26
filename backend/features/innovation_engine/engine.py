"""
链客宝 - 创新发现引擎 · 引擎编排器
====================================
编排完整的创新发现管道：扫描 → 分析 → 推荐。

管道流程：
1. 扫描阶段: 调用 OpportunityScanner 扫描多个数据源
2. 分析阶段: 调用 TrendAnalyzer 分析趋势和模式
3. 推荐阶段: 调用 OpportunityRecommender 排序和生成建议

使用方式：
    from features.innovation_engine import InnovationEngine

    engine = InnovationEngine()
    result = engine.run()
    report = result["recommendation"]
    print(report.summary)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from features.innovation_engine.opportunity_scanner import (
    MOCK_ENTERPRISES,
    MOCK_MATCHING_EVENTS,
    MOCK_NEEDS,
    MOCK_SEARCHES,
    OpportunityScanner,
    ScanResult,
)
from features.innovation_engine.trend_analyzer import TrendAnalyzer, TrendReport
from features.innovation_engine.recommender import OpportunityRecommender, RecommendationReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class PipelineStage:
    """管道阶段状态"""

    name: str
    success: bool = False
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class EngineResult:
    """引擎运行结果 — 包含所有阶段的输出"""

    scan_result: Optional[ScanResult] = None
    trend_report: Optional[TrendReport] = None
    recommendation: Optional[RecommendationReport] = None
    stages: list[PipelineStage] = field(default_factory=list)
    total_elapsed_seconds: float = 0.0
    success: bool = False
    error: Optional[str] = None
    run_at: str = ""

    def __post_init__(self) -> None:
        if not self.run_at:
            self.run_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 引擎配置
# ---------------------------------------------------------------------------


@dataclass
class EngineConfig:
    """引擎配置"""

    scan_unmet_needs: bool = True
    scan_match_failures: bool = True
    scan_search_voids: bool = True
    analyze_category_heat: bool = True
    analyze_supply_demand_gap: bool = True
    analyze_emerging_fields: bool = True
    min_days_unmatched: int = 7
    min_search_count: int = 10
    deduplicate: bool = True
    max_recommendations: int = 20


# ---------------------------------------------------------------------------
# 引擎实现
# ---------------------------------------------------------------------------


class InnovationEngine:
    """
    创新发现引擎 — 编排扫描 → 分析 → 推荐 完整管道。

    支持自定义数据源和配置，也支持使用默认的模拟数据。

    Examples:
        >>> engine = InnovationEngine()
        >>> result = engine.run()
        >>> result.success
        True
        >>> result.recommendation is not None
        True
    """

    def __init__(
        self,
        config: Optional[EngineConfig] = None,
        scanner: Optional[OpportunityScanner] = None,
        analyzer: Optional[TrendAnalyzer] = None,
        recommender: Optional[OpportunityRecommender] = None,
    ) -> None:
        """
        初始化创新发现引擎。

        Args:
            config: 引擎配置，默认使用 EngineConfig()
            scanner: 机会扫描器实例，默认创建新的
            analyzer: 趋势分析器实例，默认创建新的
            recommender: 机会推荐器实例，默认创建新的
        """
        self.config = config or EngineConfig()
        self.scanner = scanner or OpportunityScanner()
        self.analyzer = analyzer or TrendAnalyzer()
        self.recommender = recommender or OpportunityRecommender()

    def run(
        self,
        needs: Optional[list[dict[str, Any]]] = None,
        matching_events: Optional[list[dict[str, Any]]] = None,
        searches: Optional[list[dict[str, Any]]] = None,
        enterprises: Optional[list[dict[str, Any]]] = None,
    ) -> EngineResult:
        """
        执行完整的创新发现管道。

        三个阶段的详细流程：
        1. 扫描 — 扫描未满足需求、匹配失败、搜索真空
        2. 分析 — 分析品类热度、供需缺口、新兴领域
        3. 推荐 — 去重、评分、生成可执行建议

        Args:
            needs: 需求数据列表，默认使用 MOCK_NEEDS
            matching_events: 匹配记录列表，默认使用 MOCK_MATCHING_EVENTS
            searches: 搜索记录列表，默认使用 MOCK_SEARCHES
            enterprises: 企业数据列表，默认使用 MOCK_ENTERPRISES

        Returns:
            EngineResult 包含所有阶段输出
        """
        import time

        start = time.perf_counter()
        result = EngineResult()
        stages: list[PipelineStage] = []

        # 使用传入数据或默认模拟数据
        _needs = needs if needs is not None else MOCK_NEEDS
        _events = matching_events if matching_events is not None else MOCK_MATCHING_EVENTS
        _searches = searches if searches is not None else MOCK_SEARCHES
        _enterprises = enterprises if enterprises is not None else MOCK_ENTERPRISES

        # ----------------------------------------------------------
        # 阶段 1: 扫描
        # ----------------------------------------------------------
        logger.info("[InnovationEngine] 开始扫描阶段...")
        stage_scan = PipelineStage(name="scan")
        try:
            scan_start = time.perf_counter()
            partial_results: list[ScanResult] = []

            if self.config.scan_unmet_needs:
                partial = self.scanner.scan_unmet_needs(
                    needs=_needs,
                    min_days_unmatched=self.config.min_days_unmatched,
                )
                partial_results.append(partial)

            if self.config.scan_match_failures:
                partial = self.scanner.scan_match_failures(events=_events)
                partial_results.append(partial)

            if self.config.scan_search_voids:
                partial = self.scanner.scan_search_voids(
                    searches=_searches,
                    min_search_count=self.config.min_search_count,
                )
                partial_results.append(partial)

            # 合并所有扫描结果
            if partial_results:
                merged = partial_results[0]
                for p in partial_results[1:]:
                    merged.merge(p)
                result.scan_result = merged
            else:
                result.scan_result = ScanResult(scanner_name="engine_scan")

            stage_scan.success = True
            stage_scan.elapsed_seconds = round(time.perf_counter() - scan_start, 3)
            logger.info(
                "[InnovationEngine] 扫描完成: %d 条信号 (%.2fs)",
                result.scan_result.total_signals if result.scan_result else 0,
                stage_scan.elapsed_seconds,
            )
        except Exception as e:
            stage_scan.error = f"扫描阶段失败: {e}"
            logger.error("[InnovationEngine] %s", stage_scan.error)
        stages.append(stage_scan)

        # ----------------------------------------------------------
        # 阶段 2: 分析
        # ----------------------------------------------------------
        logger.info("[InnovationEngine] 开始分析阶段...")
        stage_analyze = PipelineStage(name="analyze")
        try:
            analyze_start = time.perf_counter()

            if result.scan_result and result.scan_result.signals:
                # 基于扫描信号分析
                result.trend_report = self.analyzer.analyze_signals(
                    result.scan_result
                )
            else:
                # 无扫描信号时直接基于原始数据分析
                result.trend_report = self.analyzer.analyze_full(
                    needs=_needs, searches=_searches
                )

            stage_analyze.success = True
            stage_analyze.elapsed_seconds = round(time.perf_counter() - analyze_start, 3)
            logger.info(
                "[InnovationEngine] 分析完成: %d 条洞察 (%.2fs)",
                result.trend_report.total_insights if result.trend_report else 0,
                stage_analyze.elapsed_seconds,
            )
        except Exception as e:
            stage_analyze.error = f"分析阶段失败: {e}"
            logger.error("[InnovationEngine] %s", stage_analyze.error)
        stages.append(stage_analyze)

        # ----------------------------------------------------------
        # 阶段 3: 推荐
        # ----------------------------------------------------------
        logger.info("[InnovationEngine] 开始推荐阶段...")
        stage_recommend = PipelineStage(name="recommend")
        try:
            recommend_start = time.perf_counter()

            if result.scan_result:
                result.recommendation = self.recommender.recommend_full(
                    scan_result=result.scan_result,
                    trend_report=result.trend_report,
                )

                # 限制推荐数量
                if self.config.max_recommendations > 0:
                    result.recommendation.opportunities = (
                        result.recommendation.opportunities[
                            :self.config.max_recommendations
                        ]
                    )
                    result.recommendation.total_opportunities = len(
                        result.recommendation.opportunities
                    )
            else:
                result.recommendation = RecommendationReport(
                    recommender_name=f"{self.name}.run"
                )
                result.recommendation.summary = "扫描结果为空，跳过推荐"

            stage_recommend.success = True
            stage_recommend.elapsed_seconds = round(
                time.perf_counter() - recommend_start, 3
            )
            logger.info(
                "[InnovationEngine] 推荐完成: %d 个机会 (%.2fs)",
                result.recommendation.total_opportunities if result.recommendation else 0,
                stage_recommend.elapsed_seconds,
            )
        except Exception as e:
            stage_recommend.error = f"推荐阶段失败: {e}"
            logger.error("[InnovationEngine] %s", stage_recommend.error)
        stages.append(stage_recommend)

        # ----------------------------------------------------------
        # 完成
        # ----------------------------------------------------------
        result.stages = stages
        result.total_elapsed_seconds = round(time.perf_counter() - start, 3)
        result.success = all(s.success for s in stages)
        if not result.success:
            errors = [s.error for s in stages if s.error]
            result.error = "; ".join(errors)

        logger.info(
            "[InnovationEngine] 管道完成: success=%s, total=%.2fs",
            result.success,
            result.total_elapsed_seconds,
        )

        return result

    @property
    def name(self) -> str:
        """引擎名称"""
        return "InnovationEngine"
