"""
链客宝 - 创新发现引擎 · 机会扫描器
====================================
扫描链客宝平台内的用户行为数据、企业需求数据、匹配数据，
发现未被满足的市场机会信号。

信号类型：
1. 匹配失败记录 — 供需匹配未能达成的原因和上下文
2. 未满足需求 — 企业发布但长期未获匹配的需求
3. 高频搜索无结果 — 用户反复搜索但平台上无对应供给
4. 需求突变 — 某类需求短时间内激增
5. 供需缺口 — 需求量大但供给方少的领域

设计原则：
- 每个扫描方法职责单一，只检测一种信号
- 所有方法返回统一的 OpportunitySignal 结构
- 不修改任何现有模块的数据
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class OpportunitySignal:
    """机会信号 — 扫描器输出的最小单元"""

    signal_id: str  # 唯一标识 e.g. "match_fail_001"
    signal_type: str  # match_failure / unmet_need / search_void / demand_spike / supply_gap
    source: str  # 数据来源 e.g. "matching_events", "needs", "search"
    title: str  # 简短描述
    description: str  # 详细说明
    category: str = ""  # 品类/领域
    confidence: float = 0.0  # 0.0-1.0 置信度
    frequency: int = 1  # 出现的频次
    related_entities: list[dict[str, Any]] = field(default_factory=list)
    raw_data: Optional[dict[str, Any]] = None  # 原始数据快照
    detected_at: str = ""

    def __post_init__(self) -> None:
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ScanResult:
    """一次扫描的完整结果"""

    scanner_name: str
    signals: list[OpportunitySignal] = field(default_factory=list)
    total_signals: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    scanned_at: str = ""

    def __post_init__(self) -> None:
        if not self.scanned_at:
            self.scanned_at = datetime.now(timezone.utc).isoformat()
        self.total_signals = len(self.signals)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def merge(self, other: "ScanResult") -> "ScanResult":
        """合并另一个扫描结果"""
        self.signals.extend(other.signals)
        self.total_signals = len(self.signals)
        self.errors.extend(other.errors)
        self.elapsed_seconds += other.elapsed_seconds
        return self


# ---------------------------------------------------------------------------
# 内存数据源（MVP 模拟数据）
# 实际使用时替换为数据库查询或现有模块的直接引用
# ---------------------------------------------------------------------------

# 模拟的未满足需求数据
MOCK_NEEDS: list[dict[str, Any]] = [
    {
        "id": "need_001",
        "enterprise_name": "智联科技",
        "title": "寻找工业AI视觉检测供应商",
        "category": "AI技术",
        "status": "unmatched",
        "created_at": "2026-05-20T09:00:00Z",
        "days_unmatched": 19,
        "urgency": "high",
        "budget_range": "50-100万",
    },
    {
        "id": "need_002",
        "enterprise_name": "云帆数据",
        "title": "需要大数据清洗与标注服务商",
        "category": "数据服务",
        "status": "unmatched",
        "created_at": "2026-05-25T14:30:00Z",
        "days_unmatched": 14,
        "urgency": "medium",
        "budget_range": "20-50万",
    },
    {
        "id": "need_003",
        "enterprise_name": "锐思咨询",
        "title": "寻求区块链供应链金融解决方案",
        "category": "区块链",
        "status": "unmatched",
        "created_at": "2026-06-01T10:00:00Z",
        "days_unmatched": 7,
        "urgency": "low",
        "budget_range": "100万以上",
    },
    {
        "id": "need_004",
        "enterprise_name": "博远科技",
        "title": "寻找跨境电商SaaS平台合作伙伴",
        "category": "SaaS",
        "status": "partially_matched",
        "created_at": "2026-05-10T08:00:00Z",
        "days_unmatched": 29,
        "urgency": "high",
        "budget_range": "30-80万",
    },
]

# 模拟的匹配失败记录
MOCK_MATCHING_EVENTS: list[dict[str, Any]] = [
    {
        "id": "match_001",
        "need_id": "need_001",
        "supplier_name": "视界科技",
        "match_score": 0.35,
        "fail_reason": "技术方案不匹配 — 需要深度学习方案，供应商提供传统CV方案",
        "category": "AI技术",
        "occurred_at": "2026-05-22T11:00:00Z",
    },
    {
        "id": "match_002",
        "need_id": "need_002",
        "supplier_name": "数栈科技",
        "match_score": 0.42,
        "fail_reason": "预算不匹配 — 需求方预算20-50万，供应商最低报价80万",
        "category": "数据服务",
        "occurred_at": "2026-05-27T09:30:00Z",
    },
    {
        "id": "match_003",
        "need_id": "need_003",
        "supplier_name": "链信科技",
        "match_score": 0.28,
        "fail_reason": "地域不匹配 — 需求方在深圳，供应商主要服务华东地区",
        "category": "区块链",
        "occurred_at": "2026-06-02T14:00:00Z",
    },
    {
        "id": "match_004",
        "need_id": "need_004",
        "supplier_name": "易链科技",
        "match_score": 0.55,
        "fail_reason": "服务范围不匹配 — 供应商只做ERP实施，不做完整SaaS平台",
        "category": "SaaS",
        "occurred_at": "2026-05-15T16:00:00Z",
    },
    {
        "id": "match_005",
        "need_id": "",
        "supplier_name": "",
        "match_score": 0.0,
        "fail_reason": "无可用供应商 — 品类'碳中和咨询'在平台无任何注册供应商",
        "category": "碳中和",
        "occurred_at": "2026-06-05T10:00:00Z",
    },
]

# 模拟的高频搜索无结果记录
MOCK_SEARCHES: list[dict[str, Any]] = [
    {
        "id": "search_001",
        "keyword": "碳中和认证服务",
        "category": "碳中和",
        "search_count": 47,
        "result_count": 0,
        "last_searched_at": "2026-06-07T15:00:00Z",
        "user_segments": ["制造业", "能源企业"],
    },
    {
        "id": "search_002",
        "keyword": "低代码平台开发",
        "category": "软件开发",
        "search_count": 35,
        "result_count": 0,
        "last_searched_at": "2026-06-06T10:30:00Z",
        "user_segments": ["IT服务", "互联网"],
    },
    {
        "id": "search_003",
        "keyword": "数字人直播解决方案",
        "category": "AI技术",
        "search_count": 28,
        "result_count": 0,
        "last_searched_at": "2026-06-07T09:00:00Z",
        "user_segments": ["电商", "零售"],
    },
    {
        "id": "search_004",
        "keyword": "出海合规法律咨询",
        "category": "企业服务",
        "search_count": 22,
        "result_count": 0,
        "last_searched_at": "2026-06-05T11:00:00Z",
        "user_segments": ["跨境电商", "制造业"],
    },
    {
        "id": "search_005",
        "keyword": "AI客服机器人定制",
        "category": "AI技术",
        "search_count": 18,
        "result_count": 0,
        "last_searched_at": "2026-06-04T14:00:00Z",
        "user_segments": ["电商", "金融"],
    },
]

# 模拟的企业数据
MOCK_ENTERPRISES: list[dict[str, Any]] = [
    {
        "id": "ent_001",
        "name": "智联科技",
        "industry": "制造业",
        "scale": "中型",
        "region": "华东",
        "active_needs_count": 3,
        "unmatched_rate": 0.67,
        "joined_at": "2026-03-01",
    },
    {
        "id": "ent_002",
        "name": "云帆数据",
        "industry": "IT/互联网",
        "scale": "小型",
        "region": "华南",
        "active_needs_count": 5,
        "unmatched_rate": 0.80,
        "joined_at": "2026-04-15",
    },
    {
        "id": "ent_003",
        "name": "锐思咨询",
        "industry": "企业服务",
        "scale": "小型",
        "region": "华北",
        "active_needs_count": 2,
        "unmatched_rate": 0.50,
        "joined_at": "2026-05-01",
    },
]


# ---------------------------------------------------------------------------
# 信号计数器（用于生成唯一 signal_id）
# ---------------------------------------------------------------------------
_signal_counter: int = 0


def _next_signal_id(prefix: str = "sig") -> str:
    """生成自增信号ID"""
    global _signal_counter
    _signal_counter += 1
    return f"{prefix}_{_signal_counter:04d}"


# ---------------------------------------------------------------------------
# 扫描器实现
# ---------------------------------------------------------------------------


class OpportunityScanner:
    """
    机会扫描器 — 扫描链客宝平台数据，发现未被满足的市场机会信号。

    支持的扫描类型：
    - scan_unmet_needs: 扫描长期未匹配的需求
    - scan_match_failures: 扫描匹配失败的事件
    - scan_search_voids: 扫描高频搜索但无结果的领域
    - scan_all: 执行全部扫描并合并结果
    """

    def __init__(self) -> None:
        self.name: str = "opportunity_scanner"

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def scan_unmet_needs(
        self,
        needs: Optional[list[dict[str, Any]]] = None,
        min_days_unmatched: int = 7,
    ) -> ScanResult:
        """
        扫描长期未匹配的需求。

        Args:
            needs: 需求数据列表，默认使用 MOCK_NEEDS
            min_days_unmatched: 最少未匹配天数阈值

        Returns:
            扫描结果，包含未满足需求信号
        """
        data = needs if needs is not None else MOCK_NEEDS
        signals: list[OpportunitySignal] = []

        for need in data:
            days = need.get("days_unmatched", 0)
            if days < min_days_unmatched:
                continue

            urgency = need.get("urgency", "low")
            confidence_map = {"high": 0.85, "medium": 0.65, "low": 0.40}
            confidence = confidence_map.get(urgency, 0.5)

            signal = OpportunitySignal(
                signal_id=_next_signal_id("unmet"),
                signal_type="unmet_need",
                source="needs",
                title=f"未满足需求: {need.get('title', '')}",
                description=(
                    f"企业「{need.get('enterprise_name', '未知')}」发布的需求"
                    f"已 {days} 天未获得有效匹配，"
                    f"预算范围: {need.get('budget_range', '未公开')}"
                ),
                category=need.get("category", ""),
                confidence=confidence,
                frequency=1,
                related_entities=[
                    {
                        "type": "enterprise",
                        "id": need.get("id", ""),
                        "name": need.get("enterprise_name", ""),
                    }
                ],
                raw_data=need,
            )
            signals.append(signal)

        return ScanResult(
            scanner_name=f"{self.name}.scan_unmet_needs",
            signals=signals,
        )

    def scan_match_failures(
        self,
        events: Optional[list[dict[str, Any]]] = None,
    ) -> ScanResult:
        """
        扫描匹配失败的事件，分析失败原因。

        Args:
            events: 匹配事件数据列表，默认使用 MOCK_MATCHING_EVENTS

        Returns:
            扫描结果，包含匹配失败信号
        """
        data = events if events is not None else MOCK_MATCHING_EVENTS
        signals: list[OpportunitySignal] = []

        # 按品类聚合失败原因
        failures_by_category: dict[str, list[dict]] = {}
        for event in data:
            cat = event.get("category", "未知")
            if cat not in failures_by_category:
                failures_by_category[cat] = []
            failures_by_category[cat].append(event)

        for category, cat_events in failures_by_category.items():
            fail_reasons = [e.get("fail_reason", "") for e in cat_events]
            avg_score = sum(
                e.get("match_score", 0) for e in cat_events
            ) / len(cat_events)
            has_total_void = any(
                "无可用供应商" in (e.get("fail_reason", "") or "")
                for e in cat_events
            )

            # 聚合失败原因形成信号
            signal = OpportunitySignal(
                signal_id=_next_signal_id("match"),
                signal_type="match_failure",
                source="matching_events",
                title=f"匹配缺口: {category}领域匹配困难",
                description=(
                    f"{category}领域近期待匹配需求 {len(cat_events)} 个，"
                    f"平均匹配评分 {avg_score:.2f}。"
                    f"主要失败原因: {'; '.join(fail_reasons[:3])}"
                    + ("【注意】该品类存在供应商完全空白的情况" if has_total_void else "")
                ),
                category=category,
                confidence=0.75 if has_total_void else 0.55,
                frequency=len(cat_events),
                related_entities=[
                    {
                        "type": "match_event",
                        "id": e.get("id", ""),
                        "reason": e.get("fail_reason", ""),
                        "score": e.get("match_score", 0),
                    }
                    for e in cat_events
                ],
                raw_data={"category": category, "events": cat_events},
            )
            signals.append(signal)

        return ScanResult(
            scanner_name=f"{self.name}.scan_match_failures",
            signals=signals,
        )

    def scan_search_voids(
        self,
        searches: Optional[list[dict[str, Any]]] = None,
        min_search_count: int = 10,
    ) -> ScanResult:
        """
        扫描高频搜索但无结果的领域（搜索真空区）。

        Args:
            searches: 搜索记录数据列表，默认使用 MOCK_SEARCHES
            min_search_count: 最少搜索次数阈值

        Returns:
            扫描结果，包含搜索真空信号
        """
        data = searches if searches is not None else MOCK_SEARCHES
        signals: list[OpportunitySignal] = []

        for s in data:
            count = s.get("search_count", 0)
            if count < min_search_count:
                continue

            # 搜索频次越高，信号置信度越高
            confidence = min(0.5 + (count - min_search_count) * 0.01, 0.95)

            signal = OpportunitySignal(
                signal_id=_next_signal_id("void"),
                signal_type="search_void",
                source="search",
                title=f"搜索真空: 「{s.get('keyword', '')}」供不应求",
                description=(
                    f"关键词「{s.get('keyword', '')}」已被搜索 {count} 次"
                    f"但平台内无匹配结果，"
                    f"搜索用户群体: {', '.join(s.get('user_segments', []))}"
                ),
                category=s.get("category", ""),
                confidence=confidence,
                frequency=count,
                related_entities=[
                    {
                        "type": "search_keyword",
                        "keyword": s.get("keyword", ""),
                        "count": count,
                        "segments": s.get("user_segments", []),
                    }
                ],
                raw_data=s,
            )
            signals.append(signal)

        return ScanResult(
            scanner_name=f"{self.name}.scan_search_voids",
            signals=signals,
        )

    def scan_all(
        self,
        needs: Optional[list[dict[str, Any]]] = None,
        events: Optional[list[dict[str, Any]]] = None,
        searches: Optional[list[dict[str, Any]]] = None,
    ) -> ScanResult:
        """
        执行全部扫描并合并所有信号。

        Args:
            needs: 需求数据
            events: 匹配事件数据
            searches: 搜索记录数据

        Returns:
            合并后的扫描结果
        """
        import time

        start = time.perf_counter()
        result = ScanResult(scanner_name=f"{self.name}.scan_all")

        for scan_fn in [
            self.scan_unmet_needs,
            self.scan_match_failures,
            self.scan_search_voids,
        ]:
            try:
                # 传入正确的参数给每个扫描器
                kwargs: dict[str, Any] = {}
                if scan_fn == self.scan_unmet_needs and needs is not None:
                    kwargs["needs"] = needs
                if scan_fn == self.scan_match_failures and events is not None:
                    kwargs["events"] = events
                if scan_fn == self.scan_search_voids and searches is not None:
                    kwargs["searches"] = searches
                partial = scan_fn(**kwargs)
                result.merge(partial)
            except Exception as e:
                err_msg = f"{scan_fn.__name__} 扫描失败: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)

        result.elapsed_seconds = round(time.perf_counter() - start, 3)
        return result
