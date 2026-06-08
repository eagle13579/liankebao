"""
创新发现引擎 — 编排引擎
============================
编排 OpportunityScanner、TrendAnalyzer、OpportunityRecommender 三个组件，
提供 run_innovation_scan() 完整流程。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from features.innovation_engine.opportunity_scanner import OpportunityScanner, OpportunityScanResult
from features.innovation_engine.trend_analyzer import TrendAnalyzer, TrendAnalysisResult
from features.innovation_engine.recommender import OpportunityRecommender, RecommendResult

logger = logging.getLogger(__name__)


@dataclass
class InnovationScanReport:
    """创新扫描完整报告"""
    scan_result: Optional[OpportunityScanResult] = None
    analysis_result: Optional[TrendAnalysisResult] = None
    recommend_result: Optional[RecommendResult] = None
    report_timestamp: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "report_timestamp": self.report_timestamp,
            "summary": self.summary,
            "scan": self.scan_result.to_dict() if self.scan_result else None,
            "analysis": self.analysis_result.to_dict() if self.analysis_result else None,
            "recommendations": self.recommend_result.to_dict() if self.recommend_result else None,
        }


class InnovationEngine:
    """
    创新发现引擎主引擎。
    一键执行：扫描机会 → 分析趋势 → 交叉推荐。
    """

    def __init__(
        self,
        scanner: Optional[OpportunityScanner] = None,
        analyzer: Optional[TrendAnalyzer] = None,
        recommender: Optional[OpportunityRecommender] = None,
    ):
        self.scanner = scanner or OpportunityScanner()
        self.analyzer = analyzer or TrendAnalyzer()
        self.recommender = recommender or OpportunityRecommender()
        logger.info("InnovationEngine 初始化完成")

    def run_innovation_scan(
        self,
        scan_category: Optional[str] = None,
        scan_min_pain: Optional[int] = None,
        trend_category: Optional[str] = None,
        trend_min_momentum: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> InnovationScanReport:
        """
        执行完整创新扫描流程。

        Args:
            scan_category: 机会扫描类别筛选
            scan_min_pain: 机会扫描最小疼痛阈值
            trend_category: 趋势分析类别筛选
            trend_min_momentum: 趋势分析最小动量值
            top_k: 推荐返回数量

        Returns:
            InnovationScanReport: 完整扫描报告
        """
        logger.info("=" * 60)
        logger.info("🔍 开始创新扫描流程")
        logger.info("=" * 60)

        # 步骤1: 扫描机会
        logger.info("步骤 1/3: 扫描未满足需求机会点...")
        scan_result = self.scanner.scan(category=scan_category, min_pain=scan_min_pain)
        logger.info(f"       → 发现 {scan_result.total_count} 个机会点 "
                     f"(高优先级: {scan_result.high_priority_count})")

        # 步骤2: 分析趋势
        logger.info("步骤 2/3: 分析行业趋势...")
        analysis_result = self.analyzer.analyze(category=trend_category, min_momentum=trend_min_momentum)
        logger.info(f"       → 发现 {analysis_result.total_count} 个趋势 "
                     f"(热门: {analysis_result.hot_trend_count}, "
                     f"平均动量: {analysis_result.avg_momentum:.1f})")

        # 步骤3: 交叉推荐
        logger.info("步骤 3/3: 交叉推荐...")
        recommend_result = self.recommender.recommend(scan_result, analysis_result, top_k=top_k)
        logger.info(f"       → 生成 {recommend_result.total} 条推荐 "
                     f"(高优先级: {recommend_result.high_priority})")

        # 生成摘要
        summary = (
            f"创新扫描完成: 发现 {scan_result.total_count} 个机会点, "
            f"{analysis_result.total_count} 个趋势, "
            f"生成 {recommend_result.total} 条交叉推荐"
        )

        report = InnovationScanReport(
            scan_result=scan_result,
            analysis_result=analysis_result,
            recommend_result=recommend_result,
            report_timestamp=datetime.utcnow().isoformat() + "Z",
            summary=summary,
        )

        logger.info(summary)
        return report


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 InnovationEngine 烟雾测试")
    print("=" * 60)

    engine = InnovationEngine()

    # 测试1: 完整流程
    report = engine.run_innovation_scan()
    assert report.scan_result is not None, "测试1失败：scan_result 不应为空"
    assert report.analysis_result is not None, "测试1失败：analysis_result 不应为空"
    assert report.recommend_result is not None, "测试1失败：recommend_result 不应为空"
    print(f"✅ 测试1 完整流程: 扫描 {report.scan_result.total_count} 机会, "
          f"{report.analysis_result.total_count} 趋势, "
          f"{report.recommend_result.total} 推荐")

    # 测试2: 带筛选参数
    report_filtered = engine.run_innovation_scan(
        scan_category="AI 助理",
        trend_min_momentum=7.0,
        top_k=5,
    )
    assert len(report_filtered.recommend_result.recommendations) <= 5, "测试2失败：应限制 top_k"
    print(f"✅ 测试2 带筛选: {report_filtered.scan_result.total_count} 机会, "
          f"{report_filtered.recommend_result.total} 推荐 (top_k=5)")

    # 测试3: report.to_dict 可序列化
    report_dict = report.to_dict()
    assert "summary" in report_dict, "测试3失败：report_dict 应有 summary 字段"
    assert "scan" in report_dict, "测试3失败：report_dict 应有 scan 字段"
    assert "analysis" in report_dict, "测试3失败：report_dict 应有 analysis 字段"
    assert "recommendations" in report_dict, "测试3失败：report_dict 应有 recommendations 字段"
    print(f"✅ 测试3 序列化: report.to_dict() 包含全部关键字段")

    # 测试4: 空筛选场景（不匹配任何内容）
    report_empty = engine.run_innovation_scan(
        scan_category="不存在的类别",
        trend_min_momentum=999,
    )
    assert report_empty.scan_result.total_count == 0, "测试4失败：应返回0机会"
    assert report_empty.analysis_result.total_count == 0, "测试4失败：应返回0趋势"
    print(f"✅ 测试4 空筛选: 正确返回空结果 (0 机会, 0 趋势, {report_empty.recommend_result.total} 推荐)")

    # 测试5: 自定义组件
    custom_scanner = OpportunityScanner(min_pain_threshold=9)
    custom_engine = InnovationEngine(scanner=custom_scanner)
    custom_report = custom_engine.run_innovation_scan()
    assert custom_report.scan_result.total_count <= report.scan_result.total_count, \
        "测试5失败：高阈值应返回更少结果"
    print(f"✅ 测试5 自定义组件: 高阈值扫描 → {custom_report.scan_result.total_count} 机会 "
          f"(默认: {report.scan_result.total_count})")

    # 测试6: 推荐结果排序
    scores = [r.relevance_score for r in report.recommend_result.recommendations]
    assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)), "测试6失败：应降序排列"
    print(f"✅ 测试6 推荐排序: 降序排列验证通过")

    # 测试7: 平行多次调用
    for i in range(3):
        r = engine.run_innovation_scan(top_k=2)
        assert len(r.recommend_result.recommendations) <= 2, f"测试7失败：第{i+1}次调用不符合 top_k"
    print(f"✅ 测试7 多次调用: 3 次平行调用均正常")

    print(f"\n🎉 全部 7 项烟雾测试通过!\n")
