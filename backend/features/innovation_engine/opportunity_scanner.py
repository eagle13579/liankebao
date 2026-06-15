"""
创新发现引擎 — 机会扫描器
============================
扫描未满足需求的机会点，基于模拟数据进行演示。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 模拟数据集
# ============================================================

MOCK_OPPORTUNITIES = [
    {
        "id": "opp-001",
        "title": "AI 自动生成行业分析报告",
        "description": "企业家和投资人每周需要阅读大量行业研报，但现有工具无法一键生成定制化的分析摘要和趋势判断。",
        "category": "内容生成",
        "pain_level": 8,
        "market_size": "large",
        "signals": ["用户调研中 73% 的人表示愿意付费", "竞品 A 上线 3 个月增长 200%"],
        "created_at": "2026-01-15T08:00:00Z",
    },
    {
        "id": "opp-002",
        "title": "智能供需匹配 — 产业链上下游对接",
        "description": "中小企业缺乏高效的渠道找到上下游合作伙伴，现有的 B2B 平台匹配精度低、沟通成本高。",
        "category": "匹配对接",
        "pain_level": 9,
        "market_size": "very_large",
        "signals": ["链客宝内测用户 NPS 达 72", "需求池中 68% 的需求与上下游对接相关"],
        "created_at": "2026-01-20T10:30:00Z",
    },
    {
        "id": "opp-003",
        "title": "AI 数字名片智能迭代建议",
        "description": "用户上传名片后，系统仅做 OCR 识别，缺乏对名片设计、内容策略、品牌一致性的深度诊断和优化建议。",
        "category": "设计优化",
        "pain_level": 6,
        "market_size": "medium",
        "signals": ["名片模块日均上传量 1200+", "用户反馈中 41% 提到设计相关需求"],
        "created_at": "2026-02-01T14:00:00Z",
    },
    {
        "id": "opp-004",
        "title": "创业者 AI 分身 — 7x24 智能接待",
        "description": "创业者无法 7x24 响应潜在客户/合作伙伴的咨询，需要一个能够学习其话术和知识的 AI 分身进行初步接待。",
        "category": "AI 助理",
        "pain_level": 9,
        "market_size": "very_large",
        "signals": ["竞品 B 已完成种子轮 500 万美金", "链客宝用户中 55% 表示有兴趣"],
        "created_at": "2026-02-10T09:00:00Z",
    },
    {
        "id": "opp-005",
        "title": "线下活动智能撮合与名片交换",
        "description": "线下活动中参与者无法高效地找到对的人交流，名片交换流程繁琐且缺少后续跟进机制。",
        "category": "活动工具",
        "pain_level": 7,
        "market_size": "large",
        "signals": ["链客宝活动功能月活增长 34%", "活动后跟进率仅 12%，存在巨大提升空间"],
        "created_at": "2026-02-18T16:00:00Z",
    },
    {
        "id": "opp-006",
        "title": "创业团队关键指标看板",
        "description": "创业者需要快速了解核心业务指标（获客成本、转化率、留存等），但缺乏统一的可视化看板和行业基准对比。",
        "category": "数据分析",
        "pain_level": 8,
        "market_size": "large",
        "signals": ["SaaS 行业类似产品 ARR 超 1000 万", "用户需求池中排名第 3"],
        "created_at": "2026-03-01T11:00:00Z",
    },
]


@dataclass
class Opportunity:
    """机会点数据模型"""
    id: str
    title: str
    description: str
    category: str
    pain_level: int  # 1-10
    market_size: str  # small / medium / large / very_large
    signals: list = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OpportunityScanResult:
    """扫描结果"""
    opportunities: list = field(default_factory=list)
    total_count: int = 0
    high_priority_count: int = 0
    scan_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "total_count": self.total_count,
            "high_priority_count": self.high_priority_count,
            "scan_timestamp": self.scan_timestamp,
            "opportunities": [o.to_dict() if isinstance(o, Opportunity) else o for o in self.opportunities],
        }


class OpportunityScanner:
    """
    未满足需求机会扫描器。
    基于多维信号（用户反馈、竞品动态、市场数据）扫描潜在机会点。
    """

    def __init__(self, min_pain_threshold: int = 5):
        self.min_pain_threshold = min_pain_threshold
        logger.info(f"OpportunityScanner 初始化, 最小疼痛阈值: {min_pain_threshold}")

    def scan(self, category: Optional[str] = None, min_pain: Optional[int] = None) -> OpportunityScanResult:
        """
        执行机会扫描。

        Args:
            category: 按类别筛选
            min_pain: 覆盖默认最小疼痛阈值

        Returns:
            OpportunityScanResult: 扫描结果
        """
        threshold = min_pain if min_pain is not None else self.min_pain_threshold
        raw = MOCK_OPPORTUNITIES

        if category:
            raw = [o for o in raw if o["category"] == category]

        opportunities = []
        for item in raw:
            if item["pain_level"] >= threshold:
                opp = Opportunity(**item)
                opportunities.append(opp)

        high_priority = [o for o in opportunities if o.pain_level >= 8]

        result = OpportunityScanResult(
            opportunities=opportunities,
            total_count=len(opportunities),
            high_priority_count=len(high_priority),
            scan_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        logger.info(f"机会扫描完成: 共 {result.total_count} 个机会, "
                     f"高优先级 {result.high_priority_count} 个")
        return result


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 OpportunityScanner 烟雾测试")
    print("=" * 60)

    scanner = OpportunityScanner()

    # 测试1: 全量扫描
    result = scanner.scan()
    assert result.total_count > 0, "测试1失败：应该有扫描结果"
    print(f"✅ 测试1 全量扫描: {result.total_count} 个机会")

    # 测试2: 按类别筛选
    result_ai = scanner.scan(category="AI 助理")
    assert len(result_ai.opportunities) >= 1, "测试2失败：应匹配 AI 助理类别"
    print(f"✅ 测试2 类别筛选: {len(result_ai.opportunities)} 个 AI 助理机会")

    # 测试3: 高疼痛阈值
    result_high = scanner.scan(min_pain=9)
    for opp in result_high.opportunities:
        assert opp.pain_level >= 9, "测试3失败：应只返回 pain_level >= 9 的机会"
    print(f"✅ 测试3 高疼痛阈值: {result_high.total_count} 个 pain>=9 的机会")

    # 测试4: 空结果场景
    result_empty = scanner.scan(category="不存在的类别", min_pain=1)
    assert result_empty.total_count == 0, "测试4失败：应返回空结果"
    print(f"✅ 测试4 空结果场景: 正确返回空列表")

    print(f"\n🎉 所有烟雾测试通过!\n")
