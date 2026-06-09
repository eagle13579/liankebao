"""
链客宝 - 创新发现引擎 · 机会推荐器
====================================
对扫描和分析发现的机会进行排序、去重、评分，
并生成可执行建议供平台运营使用。

核心功能：
1. 机会评分 — 综合置信度、紧迫性、商业价值进行打分
2. 去重合并 — 合并相似的信号和洞察，避免冗余
3. 排序 — 按优先级、品类、信号类型排列
4. 建议生成 — 为每个机会生成可执行的操作建议
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .opportunity_scanner import OpportunitySignal, ScanResult
from .trend_analyzer import TrendInsight, TrendReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class ActionStep:
    """可执行的操作步骤"""

    step_order: int
    action: str  # "recruit_supplier" / "notify_demand" / "create_category" / "market_push" / "investigate"
    description: str
    assignee: str = ""  # 负责角色 e.g. "运营", "商务", "产品"
    priority: str = "中"  # 高/中/低
    estimated_effort: str = ""  # e.g. "2-3天", "1周"


@dataclass
class RecommendedOpportunity:
    """推荐机会 — 推荐器输出的最小单元"""

    opportunity_id: str
    title: str
    description: str
    category: str = ""
    score: float = 0.0  # 综合评分 0.0-100.0
    priority: str = "中"  # 高/中/低
    signal_type: str = ""
    confidence: float = 0.0
    business_value: str = ""  # 商业价值评估
    action_steps: list[ActionStep] = field(default_factory=list)
    source_signals: list[str] = field(default_factory=list)  # 关联的 signal_id
    source_insights: list[str] = field(default_factory=list)  # 关联的 insight_id
    tags: list[str] = field(default_factory=list)
    recommended_at: str = ""

    def __post_init__(self) -> None:
        if not self.recommended_at:
            self.recommended_at = datetime.now(timezone.utc).isoformat()


@dataclass
class RecommendationReport:
    """推荐报告 — 推荐器输出的完整结果"""

    recommender_name: str
    opportunities: list[RecommendedOpportunity] = field(default_factory=list)
    total_opportunities: int = 0
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()
        self.total_opportunities = len(self.opportunities)

    @property
    def top_opportunities(self) -> list[RecommendedOpportunity]:
        """返回评分最高的前5个机会"""
        return sorted(
            self.opportunities,
            key=lambda x: x.score,
            reverse=True,
        )[:5]

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# 推荐器计数器
# ---------------------------------------------------------------------------
_opportunity_counter: int = 0


def _next_opportunity_id() -> str:
    """生成自增机会ID"""
    global _opportunity_counter
    _opportunity_counter += 1
    return f"opp_{_opportunity_counter:04d}"


# ---------------------------------------------------------------------------
# 推荐器实现
# ---------------------------------------------------------------------------


class OpportunityRecommender:
    """
    机会推荐器 — 对扫描和分析结果进行排序、去重、生成可执行建议。

    支持的方法：
    - deduplicate_and_merge: 去重合并相似的信号
    - score_opportunities: 为信号打分
    - generate_action_steps: 生成可执行操作步骤
    - recommend_from_signals: 基于扫描信号生成推荐
    - recommend_full: 基于扫描+分析结果生成完整推荐
    """

    def __init__(self) -> None:
        self.name: str = "opportunity_recommender"

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def deduplicate_and_merge(
        self,
        signals: list[OpportunitySignal],
    ) -> list[OpportunitySignal]:
        """
        去重合并相似的信号。

        合并规则：
        - 同品类+同信号类型的，合并为一条（频率累加）
        - 标题相似的，合并为一条

        Args:
            signals: 原始信号列表

        Returns:
            去重后的信号列表
        """
        # 按 (category, signal_type) 分组
        groups: dict[tuple[str, str], list[OpportunitySignal]] = {}
        for sig in signals:
            key = (sig.category or "", sig.signal_type)
            if key not in groups:
                groups[key] = []
            groups[key].append(sig)

        merged: list[OpportunitySignal] = []
        for (cat, stype), sigs in groups.items():
            if len(sigs) == 1:
                merged.append(sigs[0])
            else:
                # 合并同组信号
                primary = sigs[0]
                total_freq = sum(s.frequency for s in sigs)
                avg_conf = sum(s.confidence for s in sigs) / len(sigs)
                descriptions = [s.description for s in sigs]

                merged_signal = OpportunitySignal(
                    signal_id=primary.signal_id,
                    signal_type=stype,
                    source=primary.source,
                    title=primary.title,
                    description=(
                        f"合并 {len(sigs)} 条相似信号: "
                        f"{'; '.join(descriptions[:3])}"
                    ),
                    category=cat,
                    confidence=min(avg_conf + 0.1, 0.98),
                    frequency=total_freq,
                    related_entities=primary.related_entities,
                    raw_data=primary.raw_data,
                )
                merged.append(merged_signal)

        return merged

    def score_opportunity(self, signal: OpportunitySignal) -> float:
        """
        为单个信号计算综合评分 (0-100)。

        评分公式：
        score = confidence * 30 + frequency_score * 25
              + urgency_score * 25 + category_score * 20

        Args:
            signal: 机会信号

        Returns:
            综合评分 (0-100)
        """
        # 置信度得分 (0-30)
        confidence_score = signal.confidence * 30

        # 频次得分 (0-25)
        freq = signal.frequency
        if freq >= 50:
            frequency_score = 25
        elif freq >= 30:
            frequency_score = 20
        elif freq >= 15:
            frequency_score = 15
        elif freq >= 5:
            frequency_score = 10
        else:
            frequency_score = 5

        # 信号类型紧迫性得分 (0-25)
        urgency_map = {
            "search_void": 25,  # 搜索真空最紧迫 — 明确的需求信号
            "match_failure": 20,  # 匹配失败 — 供需不匹配
            "unmet_need": 18,  # 未满足需求 — 等待中
            "demand_spike": 22,  # 需求激增
            "supply_gap": 20,  # 供给缺口
        }
        urgency_score = urgency_map.get(signal.signal_type, 10)

        # 品类价值得分 (0-20)
        category_value_map: dict[str, float] = {
            "AI技术": 18,
            "大数据": 16,
            "区块链": 14,
            "SaaS": 16,
            "企业服务": 14,
            "数据服务": 15,
            "碳中和": 12,
            "软件开发": 13,
        }
        category_score = category_value_map.get(signal.category, 10)

        total = confidence_score + frequency_score + urgency_score + category_score
        return round(min(total, 100.0), 1)

    def _score_to_priority(self, score: float) -> str:
        """将评分映射为优先级等级"""
        if score >= 70:
            return "高"
        elif score >= 45:
            return "中"
        else:
            return "低"

    def _generate_steps_for_signal(
        self,
        signal: OpportunitySignal,
    ) -> list[ActionStep]:
        """
        根据信号类型生成可执行操作步骤。

        Args:
            signal: 机会信号

        Returns:
            操作步骤列表
        """
        steps: list[ActionStep] = []
        score = self.score_opportunity(signal)
        priority = self._score_to_priority(score)

        base_steps: dict[str, list[ActionStep]] = {
            "search_void": [
                ActionStep(
                    step_order=1,
                    action="recruit_supplier",
                    description=f"定向招募「{signal.category}」领域的供应商入驻",
                    assignee="商务",
                    priority=priority,
                    estimated_effort="1-2周",
                ),
                ActionStep(
                    step_order=2,
                    action="notify_demand",
                    description="向搜索用户推送品类即将上线的预告通知",
                    assignee="运营",
                    priority=priority,
                    estimated_effort="1天",
                ),
                ActionStep(
                    step_order=3,
                    action="market_push",
                    description="在搜索结果页引导用户提交需求，积累供给侧数据",
                    assignee="产品",
                    priority=priority,
                    estimated_effort="3天",
                ),
            ],
            "match_failure": [
                ActionStep(
                    step_order=1,
                    action="investigate",
                    description=f"深入分析「{signal.category}」领域匹配失败根因",
                    assignee="产品",
                    priority=priority,
                    estimated_effort="2-3天",
                ),
                ActionStep(
                    step_order=2,
                    action="recruit_supplier",
                    description=f"补充「{signal.category}」领域的多样化供应商",
                    assignee="商务",
                    priority=priority,
                    estimated_effort="1-2周",
                ),
                ActionStep(
                    step_order=3,
                    action="create_category",
                    description="优化匹配算法，增加更细粒度的品类筛选维度",
                    assignee="产品",
                    priority=priority,
                    estimated_effort="1周",
                ),
            ],
            "unmet_need": [
                ActionStep(
                    step_order=1,
                    action="notify_demand",
                    description=f"主动联系需求方，了解具体需求和期望",
                    assignee="运营",
                    priority=priority,
                    estimated_effort="1天",
                ),
                ActionStep(
                    step_order=2,
                    action="recruit_supplier",
                    description=f"在供应商库中定向寻找匹配的服务商",
                    assignee="商务",
                    priority=priority,
                    estimated_effort="3-5天",
                ),
                ActionStep(
                    step_order=3,
                    action="market_push",
                    description="将未匹配需求发布到供应商推荐榜",
                    assignee="运营",
                    priority=priority,
                    estimated_effort="1天",
                ),
            ],
        }

        default_steps = [
            ActionStep(
                step_order=1,
                action="investigate",
                description=f"评估「{signal.category}」领域机会的商业可行性",
                assignee="运营",
                priority=priority,
                estimated_effort="2天",
            ),
        ]

        steps = base_steps.get(signal.signal_type, default_steps)
        return steps

    def recommend_from_signals(
        self,
        scan_result: ScanResult,
    ) -> RecommendationReport:
        """
        基于扫描结果生成推荐机会。

        Args:
            scan_result: 扫描结果

        Returns:
            推荐报告
        """
        import time

        start = time.perf_counter()
        report = RecommendationReport(
            recommender_name=f"{self.name}.recommend_from_signals"
        )

        if not scan_result.signals:
            report.summary = "无信号数据，无法生成推荐"
            report.elapsed_seconds = round(time.perf_counter() - start, 3)
            return report

        # 1. 去重
        merged_signals = self.deduplicate_and_merge(scan_result.signals)

        # 2. 评分、排序并生成推荐
        opportunities: list[RecommendedOpportunity] = []
        for sig in merged_signals:
            score = self.score_opportunity(sig)
            priority = self._score_to_priority(score)

            opp = RecommendedOpportunity(
                opportunity_id=_next_opportunity_id(),
                title=sig.title,
                description=sig.description,
                category=sig.category,
                score=score,
                priority=priority,
                signal_type=sig.signal_type,
                confidence=sig.confidence,
                business_value=self._assess_business_value(sig, score),
                action_steps=self._generate_steps_for_signal(sig),
                source_signals=[sig.signal_id],
                tags=[sig.category, sig.signal_type, priority],
            )
            opportunities.append(opp)

        # 3. 按评分降序排序
        opportunities.sort(key=lambda x: x.score, reverse=True)

        report.opportunities = opportunities
        report.total_opportunities = len(opportunities)
        report.elapsed_seconds = round(time.perf_counter() - start, 3)

        if opportunities:
            top = opportunities[0]
            report.summary = (
                f"推荐完成: 发现 {report.total_opportunities} 个机会，"
                f"最高优先级: {top.title} (评分 {top.score})"
            )
        else:
            report.summary = "推荐完成: 未生成推荐机会"

        return report

    def recommend_full(
        self,
        scan_result: ScanResult,
        trend_report: Optional[TrendReport] = None,
    ) -> RecommendationReport:
        """
        基于扫描结果和趋势分析生成完整推荐。

        Args:
            scan_result: 扫描结果
            trend_report: 趋势分析报告（可选）

        Returns:
            完整推荐报告
        """
        import time

        start = time.perf_counter()
        report = self.recommend_from_signals(scan_result)

        # 融合趋势分析洞察
        if trend_report and trend_report.insights:
            # 用趋势洞察丰富推荐的描述
            high_value_insights = sorted(
                trend_report.insights,
                key=lambda x: x.confidence,
                reverse=True,
            )

            for i, insight in enumerate(high_value_insights[:3]):
                # 尝试找到匹配品类的机会
                matched_opps = [
                    opp for opp in report.opportunities
                    if opp.category == insight.category
                ]
                if matched_opps:
                    for opp in matched_opps:
                        opp.source_insights.append(insight.insight_id)
                        opp.description += (
                            f"\n【趋势背景】{insight.description}"
                        )

            # 融合摘要
            top_insight_titles = [
                ins.title for ins in high_value_insights[:3]
            ]
            original_summary = report.summary
            report.summary = (
                f"{original_summary} | "
                f"趋势洞察: {'; '.join(top_insight_titles)}"
            )

        report.recommender_name = f"{self.name}.recommend_full"
        report.elapsed_seconds = round(time.perf_counter() - start, 3)

        return report

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _assess_business_value(
        signal: OpportunitySignal,
        score: float,
    ) -> str:
        """
        评估信号的商业价值。

        Args:
            signal: 机会信号
            score: 综合评分

        Returns:
            商业价值描述
        """
        if score >= 75:
            return (
                f"高价值机会: 「{signal.category}」领域供需缺口明确，"
                f"优先引入供应商可快速提升平台交易匹配率"
            )
        elif score >= 50:
            return (
                f"中等价值: 「{signal.category}」领域存在改进空间，"
                f"建议纳入近期运营计划"
            )
        else:
            return (
                f"观察机会: 「{signal.category}」领域可择机优化，"
                f"目前非紧急事项"
            )
