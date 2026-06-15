"""
创新发现引擎 — 趋势分析器
============================
分析行业趋势和热词变化，基于模拟数据进行演示。

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

MOCK_TRENDS = [
    {
        "id": "trend-001",
        "name": "AI Agent 自动化工作流",
        "category": "人工智能",
        "momentum": 9.5,  # 1-10
        "growth_rate": 0.85,
        "related_keywords": ["AI助理", "工作流自动化", "RPA升级", "大模型应用"],
        "source": "行业报告 + 链客宝搜索热词",
        "last_updated": "2026-03-15T08:00:00Z",
    },
    {
        "id": "trend-002",
        "name": "产业互联网 SaaS 下沉",
        "category": "商业模式",
        "momentum": 8.2,
        "growth_rate": 0.62,
        "related_keywords": ["SaaS+服务", "行业垂直", "中小企业数字化", "订阅经济"],
        "source": "投融资数据 + 用户调研",
        "last_updated": "2026-03-14T10:00:00Z",
    },
    {
        "id": "trend-003",
        "name": "Web3 与数字身份",
        "category": "区块链",
        "momentum": 5.8,
        "growth_rate": 0.15,
        "related_keywords": ["DID", "数字钱包", "NFT名片", "去中心化身份"],
        "source": "开发者社区 + 技术博客",
        "last_updated": "2026-03-10T09:00:00Z",
    },
    {
        "id": "trend-004",
        "name": "AI 原生营销内容生成",
        "category": "营销",
        "momentum": 8.8,
        "growth_rate": 0.91,
        "related_keywords": ["AIGC", "短视频脚本", "营销文案", "个性化推荐"],
        "source": "链客宝用户行为 + 行业报告",
        "last_updated": "2026-03-15T12:00:00Z",
    },
    {
        "id": "trend-005",
        "name": "企业碳足迹与 ESG 合规",
        "category": "可持续发展",
        "momentum": 6.5,
        "growth_rate": 0.45,
        "related_keywords": ["碳核算", "ESG报告", "绿色供应链", "碳中和"],
        "source": "政策动态 + 企业咨询数据",
        "last_updated": "2026-03-12T14:00:00Z",
    },
    {
        "id": "trend-006",
        "name": "跨境出海一站式服务",
        "category": "国际化",
        "momentum": 8.0,
        "growth_rate": 0.72,
        "related_keywords": ["跨境电商", "海外社媒", "本地化", "国际支付"],
        "source": "链客宝需求池 + 投融资报告",
        "last_updated": "2026-03-13T11:00:00Z",
    },
    {
        "id": "trend-007",
        "name": "AI 驱动的个性化学习与培训",
        "category": "教育",
        "momentum": 7.5,
        "growth_rate": 0.55,
        "related_keywords": ["自适应学习", "AI导师", "技能图谱", "微学习"],
        "source": "教育科技报告 + 用户调研",
        "last_updated": "2026-03-11T09:00:00Z",
    },
]


@dataclass
class Trend:
    """趋势数据模型"""
    id: str
    name: str
    category: str
    momentum: float  # 1-10
    growth_rate: float  # -1 到 1
    related_keywords: list = field(default_factory=list)
    source: str = ""
    last_updated: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrendAnalysisResult:
    """趋势分析结果"""
    trends: list = field(default_factory=list)
    total_count: int = 0
    hot_trend_count: int = 0  # momentum >= 8
    avg_momentum: float = 0.0
    categories: list = field(default_factory=list)
    analysis_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "total_count": self.total_count,
            "hot_trend_count": self.hot_trend_count,
            "avg_momentum": round(self.avg_momentum, 2),
            "categories": self.categories,
            "analysis_timestamp": self.analysis_timestamp,
            "trends": [t.to_dict() if isinstance(t, Trend) else t for t in self.trends],
        }


class TrendAnalyzer:
    """
    趋势分析器。
    分析行业趋势动量、增长率和热词分布。
    """

    def __init__(self, hot_threshold: float = 8.0):
        self.hot_threshold = hot_threshold
        logger.info(f"TrendAnalyzer 初始化, 热门阈值: {hot_threshold}")

    def analyze(self, category: Optional[str] = None, min_momentum: Optional[float] = None) -> TrendAnalysisResult:
        """
        执行趋势分析。

        Args:
            category: 按类别筛选
            min_momentum: 最小动量值筛选

        Returns:
            TrendAnalysisResult: 分析结果
        """
        raw = MOCK_TRENDS

        if category:
            raw = [t for t in raw if t["category"] == category]

        if min_momentum is not None:
            raw = [t for t in raw if t["momentum"] >= min_momentum]

        trends = [Trend(**item) for item in raw]
        categories = sorted(set(t.category for t in trends))
        hot_trends = [t for t in trends if t.momentum >= self.hot_threshold]
        avg_momentum = sum(t.momentum for t in trends) / len(trends) if trends else 0.0

        result = TrendAnalysisResult(
            trends=trends,
            total_count=len(trends),
            hot_trend_count=len(hot_trends),
            avg_momentum=avg_momentum,
            categories=categories,
            analysis_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        logger.info(f"趋势分析完成: 共 {result.total_count} 个趋势, "
                     f"热门 {result.hot_trend_count} 个, 平均动量 {result.avg_momentum:.1f}")
        return result


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 TrendAnalyzer 烟雾测试")
    print("=" * 60)

    analyzer = TrendAnalyzer()

    # 测试1: 全量分析
    result = analyzer.analyze()
    assert result.total_count > 0, "测试1失败：应有分析结果"
    print(f"✅ 测试1 全量分析: {result.total_count} 个趋势, 平均动量 {result.avg_momentum}")

    # 测试2: 按类别筛选
    result_ai = analyzer.analyze(category="人工智能")
    assert len(result_ai.trends) >= 1, "测试2失败：应匹配人工智能类别"
    print(f"✅ 测试2 类别筛选: {len(result_ai.trends)} 个 AI 趋势")

    # 测试3: 热门趋势统计
    assert result.hot_trend_count > 0, "测试3失败：应有热门趋势"
    print(f"✅ 测试3 热门趋势: {result.hot_trend_count} 个热门趋势 (momentum >= {analyzer.hot_threshold})")

    # 测试4: 类别聚合
    assert len(result.categories) > 0, "测试4失败：应有类别列表"
    print(f"✅ 测试4 类别聚合: {len(result.categories)} 个类别 ({', '.join(result.categories)})")

    print(f"\n🎉 所有烟雾测试通过!\n")
