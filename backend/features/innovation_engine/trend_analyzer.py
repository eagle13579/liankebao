"""
链客宝 - 创新发现引擎 · 趋势分析器
====================================
分析供需变化趋势、热门品类、增长领域等宏观市场信号。

分析维度：
1. 品类热度趋势 — 各品类需求发布量、搜索量的时间变化
2. 供需平衡分析 — 各品类的需求/供给比率
3. 新兴领域识别 — 近期快速增长的新品类
4. 企业需求画像 — 按行业/地域/规模聚合的需求特征
5. 季节性与周期性 — 需求的时间模式

设计原则：
- 基于扫描器输出或原始数据进行分析
- 输出标准化的 TrendReport 结构
- 所有分析可独立运行，互相解耦
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from features.innovation_engine.opportunity_scanner import OpportunitySignal, ScanResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class TrendInsight:
    """趋势洞察 — 分析器输出的最小单元"""

    insight_id: str
    insight_type: str  # category_heat / supply_demand_gap / emerging_field / demand_profile / seasonal
    title: str
    description: str
    category: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    related_signals: list[str] = field(default_factory=list)  # signal_id references
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class TrendReport:
    """趋势分析完整报告"""

    analyzer_name: str
    insights: list[TrendInsight] = field(default_factory=list)
    total_insights: int = 0
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    analyzed_at: str = ""

    def __post_init__(self) -> None:
        if not self.analyzed_at:
            self.analyzed_at = datetime.now(timezone.utc).isoformat()
        self.total_insights = len(self.insights)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# 洞察计数器
# ---------------------------------------------------------------------------
_insight_counter: int = 0


def _next_insight_id(prefix: str = "ins") -> str:
    """生成自增洞察ID"""
    global _insight_counter
    _insight_counter += 1
    return f"{prefix}_{_insight_counter:04d}"


# ---------------------------------------------------------------------------
# 趋势分析器实现
# ---------------------------------------------------------------------------


class TrendAnalyzer:
    """
    趋势分析器 — 分析供需趋势、热门品类和增长领域。

    支持的分析方法：
    - analyze_category_heat: 分析各品类热度
    - analyze_supply_demand_gap: 分析供需缺口
    - analyze_emerging_fields: 识别新兴领域
    - analyze_signals: 基于扫描信号进行趋势分析
    - analyze_full: 执行完整趋势分析
    """

    def __init__(self) -> None:
        self.name: str = "trend_analyzer"

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def analyze_category_heat(
        self,
        signals: Optional[list[OpportunitySignal]] = None,
        needs: Optional[list[dict[str, Any]]] = None,
        searches: Optional[list[dict[str, Any]]] = None,
    ) -> TrendReport:
        """
        分析各品类的热度趋势。

        综合需求数量、搜索频次、信号频率来判断品类热度。

        Args:
            signals: 扫描信号列表（可选）
            needs: 需求数据（可选）
            searches: 搜索数据（可选）

        Returns:
            趋势报告，包含品类热度洞察
        """
        insights: list[TrendInsight] = []

        # 从需求数据统计品类分布
        category_demand: dict[str, int] = {}
        if needs:
            for n in needs:
                cat = n.get("category", "未知")
                category_demand[cat] = category_demand.get(cat, 0) + 1

        # 从搜索数据统计品类搜索热度
        category_search: dict[str, int] = {}
        if searches:
            for s in searches:
                cat = s.get("category", "未知")
                count = s.get("search_count", 0)
                category_search[cat] = category_search.get(cat, 0) + count

        # 从信号统计
        category_signal: dict[str, int] = {}
        if signals:
            for sig in signals:
                cat = sig.category or "未知"
                category_signal[cat] = category_signal.get(cat, 0) + 1

        # 合并计算品类热度
        all_categories = set(category_demand.keys())
        all_categories.update(category_search.keys())
        all_categories.update(category_signal.keys())

        category_heat: list[tuple[str, float, dict]] = []
        for cat in all_categories:
            demand_score = category_demand.get(cat, 0) * 2.0  # 需求权重高
            search_score = category_search.get(cat, 0) * 0.5
            signal_score = category_signal.get(cat, 0) * 1.5
            total_score = demand_score + search_score + signal_score

            category_heat.append(
                (cat, total_score, {"demand_count": category_demand.get(cat, 0),
                                    "search_count": category_search.get(cat, 0),
                                    "signal_count": category_signal.get(cat, 0)})
            )

        # 排序：热度从高到低
        category_heat.sort(key=lambda x: x[1], reverse=True)

        # 生成洞察
        if category_heat:
            total = sum(ch[1] for ch in category_heat)
            for rank, (cat, score, details) in enumerate(category_heat[:5], 1):
                pct = round(score / total * 100, 1) if total > 0 else 0
                insight = TrendInsight(
                    insight_id=_next_insight_id("heat"),
                    insight_type="category_heat",
                    title=f"品类热度 #{rank}: {cat}",
                    description=(
                        f"{cat}品类综合热度评分 {score:.1f}（占比 {pct}%），"
                        f"需求 {details['demand_count']} 个，"
                        f"搜索 {details['search_count']} 次，"
                        f"信号 {details['signal_count']} 个"
                    ),
                    category=cat,
                    metrics={
                        "heat_score": round(score, 2),
                        "percentage": pct,
                        "rank": rank,
                        **details,
                    },
                    confidence=min(0.5 + rank * 0.08, 0.95),
                )
                insights.append(insight)

        return TrendReport(
            analyzer_name=f"{self.name}.analyze_category_heat",
            insights=insights,
        )

    def analyze_supply_demand_gap(
        self,
        signals: Optional[list[OpportunitySignal]] = None,
    ) -> TrendReport:
        """
        分析供需缺口 — 需求量大但供给不足的领域。

        Args:
            signals: 扫描信号列表

        Returns:
            趋势报告，包含供需缺口洞察
        """
        insights: list[TrendInsight] = []

        if not signals:
            return TrendReport(
                analyzer_name=f"{self.name}.analyze_supply_demand_gap",
                insights=[],
                summary="无信号数据，无法分析供需缺口",
            )

        # 按品类聚合信号
        category_signals: dict[str, list[OpportunitySignal]] = {}
        for sig in signals:
            cat = sig.category or "未知"
            if cat not in category_signals:
                category_signals[cat] = []
            category_signals[cat].append(sig)

        for cat, cat_sigs in category_signals.items():
            # 统计各类型信号
            match_fails = [s for s in cat_sigs if s.signal_type == "match_failure"]
            search_voids = [s for s in cat_sigs if s.signal_type == "search_void"]
            unmet_needs = [s for s in cat_sigs if s.signal_type == "unmet_need"]

            if not match_fails and not search_voids and not unmet_needs:
                continue

            gap_score = (
                len(match_fails) * 1.5
                + len(search_voids) * 2.0
                + len(unmet_needs) * 1.0
            )
            total_frequency = sum(s.frequency for s in cat_sigs)

            severity = (
                "严重" if gap_score > 10 else
                "中等" if gap_score > 5 else
                "轻微"
            )

            insight = TrendInsight(
                insight_id=_next_insight_id("gap"),
                insight_type="supply_demand_gap",
                title=f"供需缺口: {cat} (缺口等级: {severity})",
                description=(
                    f"{cat}领域存在明显供需缺口。"
                    f"匹配失败 {len(match_fails)} 次，"
                    f"搜索真空 {len(search_voids)} 个，"
                    f"未满足需求 {len(unmet_needs)} 个。"
                    f"缺口综合评分: {gap_score:.1f}"
                ),
                category=cat,
                metrics={
                    "gap_score": round(gap_score, 2),
                    "severity": severity,
                    "match_failures": len(match_fails),
                    "search_voids": len(search_voids),
                    "unmet_needs": len(unmet_needs),
                    "total_frequency": total_frequency,
                },
                confidence=min(0.3 + gap_score * 0.05, 0.95),
                related_signals=[s.signal_id for s in cat_sigs[:5]],
            )
            insights.append(insight)

        # 按缺口评分排序
        insights.sort(
            key=lambda x: x.metrics.get("gap_score", 0),
            reverse=True,
        )

        return TrendReport(
            analyzer_name=f"{self.name}.analyze_supply_demand_gap",
            insights=insights,
        )

    def analyze_emerging_fields(
        self,
        searches: Optional[list[dict[str, Any]]] = None,
        needs: Optional[list[dict[str, Any]]] = None,
    ) -> TrendReport:
        """
        识别新兴领域 — 搜索量快速增长但平台供给不足的细分领域。

        Args:
            searches: 搜索记录数据
            needs: 需求数据

        Returns:
            趋势报告，包含新兴领域洞察
        """
        insights: list[TrendInsight] = []

        # 基于搜索真空数据识别新兴领域
        search_data = searches if searches is not None else []
        need_data = needs if needs is not None else []

        # 统计搜索关键词中的新兴主题（搜索量高且无结果的）
        emerging_keywords: list[dict] = []
        for s in search_data:
            count = s.get("search_count", 0)
            if count >= 15:  # 高频搜索阈值
                emerging_keywords.append({
                    "keyword": s.get("keyword", ""),
                    "category": s.get("category", ""),
                    "count": count,
                    "segments": s.get("user_segments", []),
                })

        # 统一需求中频率高的品类
        demand_categories: dict[str, int] = {}
        for n in need_data:
            cat = n.get("category", "未知")
            demand_categories[cat] = demand_categories.get(cat, 0) + 1

        # 生成新兴领域洞察
        for kw in emerging_keywords:
            keyword = kw["keyword"]
            category = kw["category"]
            count = kw["count"]

            # 检查该品类是否有对应的需求
            demand_match_count = demand_categories.get(category, 0)

            insight = TrendInsight(
                insight_id=_next_insight_id("emerging"),
                insight_type="emerging_field",
                title=f"新兴领域: {keyword}",
                description=(
                    f"「{keyword}」被搜索 {count} 次但无匹配结果，"
                    f"相关品类「{category}」有 {demand_match_count} 个需求。"
                    f"该领域存在明确的供给空白，建议优先引入供应商。"
                    f"搜索用户来自: {', '.join(kw['segments'])}"
                ),
                category=category,
                metrics={
                    "keyword": keyword,
                    "search_count": count,
                    "demand_count": demand_match_count,
                    "user_segments": kw["segments"],
                },
                confidence=min(0.4 + count * 0.015, 0.95),
            )
            insights.append(insight)

        return TrendReport(
            analyzer_name=f"{self.name}.analyze_emerging_fields",
            insights=insights,
        )

    def analyze_signals(self, scan_result: ScanResult) -> TrendReport:
        """
        基于扫描器输出的信号进行趋势分析。

        综合调用 analyze_category_heat、analyze_supply_demand_gap
        和 analyze_emerging_fields。

        Args:
            scan_result: 扫描器输出结果

        Returns:
            综合分析报告
        """
        import time

        start = time.perf_counter()
        report = TrendReport(analyzer_name=f"{self.name}.analyze_signals")

        if not scan_result.success:
            report.errors.append("扫描结果包含错误，趋势分析可能不完整")
            report.errors.extend(scan_result.errors)

        signals = scan_result.signals

        try:
            heat_report = self.analyze_category_heat(signals=signals)
            report.insights.extend(heat_report.insights)
            report.errors.extend(heat_report.errors)
        except Exception as e:
            err_msg = f"品类热度分析失败: {e}"
            logger.error(err_msg)
            report.errors.append(err_msg)

        try:
            gap_report = self.analyze_supply_demand_gap(signals=signals)
            report.insights.extend(gap_report.insights)
            report.errors.extend(gap_report.errors)
        except Exception as e:
            err_msg = f"供需缺口分析失败: {e}"
            logger.error(err_msg)
            report.errors.append(err_msg)

        report.total_insights = len(report.insights)
        report.elapsed_seconds = round(time.perf_counter() - start, 3)

        if report.insights:
            top = report.insights[0]
            report.summary = (
                f"趋势分析完成: 共 {report.total_insights} 条洞察，"
                f"最显著: {top.title} (置信度 {top.confidence:.0%})"
            )
        else:
            report.summary = "趋势分析完成: 未发现显著趋势"

        return report

    def analyze_full(
        self,
        scan_result: Optional[ScanResult] = None,
        needs: Optional[list[dict[str, Any]]] = None,
        searches: Optional[list[dict[str, Any]]] = None,
    ) -> TrendReport:
        """
        执行完整趋势分析。

        Args:
            scan_result: 扫描结果（可选），如果有则基于信号分析
            needs: 需求数据（可选）
            searches: 搜索数据（可选）

        Returns:
            完整趋势报告
        """
        import time

        start = time.perf_counter()
        report = TrendReport(analyzer_name=f"{self.name}.analyze_full")

        if scan_result:
            try:
                signal_report = self.analyze_signals(scan_result)
                report.insights.extend(signal_report.insights)
                report.errors.extend(signal_report.errors)
            except Exception as e:
                err_msg = f"基于信号的趋势分析失败: {e}"
                logger.error(err_msg)
                report.errors.append(err_msg)
        else:
            # 独立分析，不依赖扫描结果
            try:
                heat_report = self.analyze_category_heat(
                    needs=needs, searches=searches
                )
                report.insights.extend(heat_report.insights)
            except Exception as e:
                err_msg = f"品类热度分析失败: {e}"
                logger.error(err_msg)
                report.errors.append(err_msg)

            try:
                emerging_report = self.analyze_emerging_fields(
                    searches=searches, needs=needs
                )
                report.insights.extend(emerging_report.insights)
            except Exception as e:
                err_msg = f"新兴领域分析失败: {e}"
                logger.error(err_msg)
                report.errors.append(err_msg)

        report.total_insights = len(report.insights)
        report.elapsed_seconds = round(time.perf_counter() - start, 3)

        if report.insights:
            top = report.insights[0]
            report.summary = (
                f"完整趋势分析完成: 共 {report.total_insights} 条洞察，"
                f"核心发现: {top.title}"
            )
        else:
            report.summary = "完整趋势分析完成: 未发现显著趋势"

        return report
