"""
创新发现引擎 — 机会推荐器
============================
基于 Scanner 扫描结果和 Analyzer 分析结果进行交叉推荐。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from features.innovation_engine.opportunity_scanner import Opportunity, OpportunityScanResult
from features.innovation_engine.trend_analyzer import Trend, TrendAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class Recommendation:
    """推荐结果"""
    opportunity: Opportunity
    matched_trends: list = field(default_factory=list)
    relevance_score: float = 0.0
    recommendation_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "opportunity": self.opportunity.to_dict(),
            "matched_trends": [t.to_dict() if isinstance(t, Trend) else t for t in self.matched_trends],
            "relevance_score": round(self.relevance_score, 2),
            "recommendation_reason": self.recommendation_reason,
        }


@dataclass
class RecommendResult:
    """推荐结果汇总"""
    recommendations: list = field(default_factory=list)
    total: int = 0
    high_priority: int = 0
    recommend_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "high_priority": self.high_priority,
            "recommend_timestamp": self.recommend_timestamp,
            "recommendations": [r.to_dict() if isinstance(r, Recommendation) else r for r in self.recommendations],
        }


class OpportunityRecommender:
    """
    机会推荐器。
    将扫描结果与分析结果进行交叉匹配，生成推荐排序。
    """

    # 类别映射表：机会类别 ↔ 趋势关键词
    CATEGORY_KEYWORD_MAP = {
        "内容生成": ["AIGC", "AI 原生营销", "营销文案", "个性化推荐"],
        "匹配对接": ["SaaS+服务", "产业互联网", "中小企业数字化"],
        "设计优化": ["AI 原生营销", "AIGC"],
        "AI 助理": ["AI助理", "工作流自动化", "大模型应用", "AI Agent"],
        "活动工具": ["SaaS+服务", "中小企业数字化"],
        "数据分析": ["AI Agent", "大模型应用", "SaaS+服务"],
    }

    def __init__(self, min_relevance: float = 0.3):
        self.min_relevance = min_relevance
        logger.info(f"OpportunityRecommender 初始化, 最小相关度: {min_relevance}")

    def _calc_relevance(self, opportunity: Opportunity, trends: list) -> (float, list, str):
        """
        计算机会点与趋势的相关度。

        Returns:
            (score, matched_trends, reason) 元组
        """
        matched = []
        feedback_keywords = " ".join(opportunity.signals).lower()
        opp_title_desc = f"{opportunity.title} {opportunity.description}".lower()
        category_keywords = self.CATEGORY_KEYWORD_MAP.get(opportunity.category, [])

        for trend in trends:
            trend_keywords = " ".join(trend.related_keywords).lower()
            trend_name = trend.name.lower()

            # 关键词匹配
            keyword_hits = sum(1 for kw in category_keywords if kw.lower() in trend_keywords or kw.lower() in trend_name)
            signal_hits = sum(1 for sig_keyword in [opportunity.title, opportunity.category] if sig_keyword.lower() in trend_keywords)

            # momentum 权重
            momentum_factor = trend.momentum / 10.0

            if keyword_hits > 0 or signal_hits > 0:
                score = (keyword_hits * 0.4 + signal_hits * 0.3) * momentum_factor
                if score >= self.min_relevance:
                    matched.append((trend, score))

        # 按分数降序
        matched.sort(key=lambda x: x[1], reverse=True)
        matched_trends = [m[0] for m in matched]
        total_score = sum(m[1] for m in matched) / max(len(matched), 1) if matched else 0.0

        # 生成推荐理由
        if matched_trends:
            trend_names = ", ".join(t.name for t in matched_trends[:3])
            reason = f"与热门趋势「{trend_names}」高度相关，建议优先投入资源"
        else:
            reason = "独立机会点，需进一步验证市场信号"

        return total_score, matched_trends, reason

    def recommend(
        self,
        scan_result: OpportunityScanResult,
        analysis_result: TrendAnalysisResult,
        top_k: Optional[int] = None,
    ) -> RecommendResult:
        """
        执行交叉推荐。

        Args:
            scan_result: OpportunityScanner 的扫描结果
            analysis_result: TrendAnalyzer 的分析结果
            top_k: 返回 top_k 条推荐（None 返回全部）

        Returns:
            RecommendResult: 推荐结果
        """
        trends = analysis_result.trends
        recommendations = []

        for opp in scan_result.opportunities:
            score, matched_trends, reason = self._calc_relevance(opp, trends)
            rec = Recommendation(
                opportunity=opp,
                matched_trends=matched_trends,
                relevance_score=score,
                recommendation_reason=reason,
            )
            recommendations.append(rec)

        # 按相关度降序
        recommendations.sort(key=lambda r: r.relevance_score, reverse=True)

        if top_k is not None:
            recommendations = recommendations[:top_k]

        high_priority = sum(1 for r in recommendations if r.relevance_score >= 0.6)

        result = RecommendResult(
            recommendations=recommendations,
            total=len(recommendations),
            high_priority=high_priority,
            recommend_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        logger.info(f"推荐完成: 共 {result.total} 条推荐, 高优先级 {result.high_priority} 条")
        return result


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 OpportunityRecommender 烟雾测试")
    print("=" * 60)

    from features.innovation_engine.opportunity_scanner import OpportunityScanner
    from features.innovation_engine.trend_analyzer import TrendAnalyzer

    scanner = OpportunityScanner()
    analyzer = TrendAnalyzer()
    recommender = OpportunityRecommender()

    scan_result = scanner.scan()
    analysis_result = analyzer.analyze()

    # 测试1: 交叉推荐非空
    result = recommender.recommend(scan_result, analysis_result)
    assert result.total > 0, "测试1失败：应有推荐结果"
    print(f"✅ 测试1 交叉推荐: {result.total} 条推荐")

    # 测试2: 高优先级计数
    if result.high_priority > 0:
        print(f"✅ 测试2 高优先级: {result.high_priority} 条")
    else:
        print(f"⚠️  测试2 高优先级: 0 条 (阈值较高)")

    # 测试3: top_k 限制
    result_top3 = recommender.recommend(scan_result, analysis_result, top_k=3)
    assert len(result_top3.recommendations) <= 3, "测试3失败：应限制为 top_k 条"
    print(f"✅ 测试3 top_k 限制: {len(result_top3.recommendations)} 条 (请求 3 条)")

    # 测试4: 排序验证 (降序)
    scores = [r.relevance_score for r in result.recommendations]
    assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)), "测试4失败：应降序排列"
    print(f"✅ 测试4 排序验证: 确实降序排列")

    print(f"\n🎉 所有烟雾测试通过!\n")
