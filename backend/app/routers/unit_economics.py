"""
链客宝 - M6 单位经济仪表盘
==============================
LTV/CAC/回收周期/毛利率等核心单位经济指标追踪与分析

注入点：成本数据录入 -> 指标计算 -> 仪表盘展示 -> 趋势分析
规则：纯新增，不修改现有业务逻辑
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class CostEntry(BaseModel):
    """成本条目（CAC组成部分）"""
    id: Optional[int] = None
    name: str
    category: str  # 市场推广/销售人力/渠道分成/工具订阅/其他
    amount: float
    period: str  # 月份 e.g. 2026-06
    description: str = ""
    created_at: str = ""

class RevenueEntry(BaseModel):
    """收入条目（LTV组成部分）"""
    id: Optional[int] = None
    customer_id: str
    customer_name: str
    plan: str  # 免费版/专业版/企业版
    revenue: float
    period: str  # 月份 e.g. 2026-06
    acquisition_channel: str = ""  # 展会/地推/线上/转介绍
    contract_months: int = 1
    created_at: str = ""

class UnitEconomicsSnapshot(BaseModel):
    """单位经济快照（按月份计算）"""
    id: Optional[int] = None
    period: str  # 月份 e.g. 2026-06
    cac: float = 0.0  # 客户获取成本
    ltv: float = 0.0  # 客户生命周期价值
    ltv_cac_ratio: float = 0.0
    avg_revenue_per_customer: float = 0.0
    avg_gross_margin: float = 0.0
    payback_months: float = 0.0  # 回收周期
    new_customers: int = 0
    churned_customers: int = 0
    total_active_customers: int = 0
    calculated_at: str = ""
    created_at: str = ""

class ChannelEconomics(BaseModel):
    """渠道经济分析"""
    channel: str
    period: str
    spend: float
    leads: int
    conversions: int
    cac: float
    revenue_from_channel: float
    roi: float
    created_at: str = ""

# ---------------------------------------------------------------------------
# 内存存储（可替换为数据库）
# ---------------------------------------------------------------------------

COST_ENTRIES: list[CostEntry] = [
    CostEntry(id=1, name="百度SEM关键词投放", category="市场推广", amount=25000.0, period="2026-06", description="B2B获客关键词竞价"),
    CostEntry(id=2, name="展会参展费用（2026上海）", category="市场推广", amount=35000.0, period="2026-06", description="上海企业服务展展位+物料"),
    CostEntry(id=3, name="电销团队人力成本", category="销售人力", amount=48000.0, period="2026-06", description="3人电销团队底薪+提成"),
    CostEntry(id=4, name="渠道合作伙伴分成", category="渠道分成", amount=12000.0, period="2026-06", description="3家渠道伙伴15%分成"),
    CostEntry(id=5, name="外呼系统月费", category="工具订阅", amount=3000.0, period="2026-06", description="AI外呼系统月费"),
]

REVENUE_ENTRIES: list[RevenueEntry] = [
    RevenueEntry(id=1, customer_id="C001", customer_name="智联科技", plan="企业版", revenue=12800.0, period="2026-06", acquisition_channel="线上"),
    RevenueEntry(id=2, customer_id="C002", customer_name="云帆数据", plan="专业版", revenue=6800.0, period="2026-06", acquisition_channel="展会"),
    RevenueEntry(id=3, customer_id="C003", customer_name="锐思咨询", plan="专业版", revenue=6800.0, period="2026-06", acquisition_channel="转介绍"),
    RevenueEntry(id=4, customer_id="C004", customer_name="博远科技", plan="企业版", revenue=12800.0, period="2026-06", acquisition_channel="线上"),
    RevenueEntry(id=5, customer_id="C005", customer_name="创享互联", plan="专业版", revenue=6800.0, period="2026-06", acquisition_channel="渠道"),
    RevenueEntry(id=6, customer_id="C006", customer_name="明略数据", plan="企业版", revenue=12800.0, period="2026-06", acquisition_channel="展会"),
    RevenueEntry(id=7, customer_id="C007", customer_name="华盛集团", plan="专业版", revenue=6800.0, period="2026-06", acquisition_channel="线上"),
    RevenueEntry(id=8, customer_id="C008", customer_name="聚量科技", plan="免费版", revenue=0.0, period="2026-06", acquisition_channel="线上"),
]

SNAPSHOTS: list[UnitEconomicsSnapshot] = [
    UnitEconomicsSnapshot(
        id=1, period="2026-06",
        cac=14400.0, ltv=42560.0, ltv_cac_ratio=2.96,
        avg_revenue_per_customer=8520.0, avg_gross_margin=0.72,
        payback_months=6.2, new_customers=7, churned_customers=1,
        total_active_customers=48
    )
]

CHANNEL_ECONOMICS: list[ChannelEconomics] = [
    ChannelEconomics(channel="线上", period="2026-06", spend=28000.0, leads=120, conversions=4, cac=7000.0, revenue_from_channel=32400.0, roi=1.16),
    ChannelEconomics(channel="展会", period="2026-06", spend=35000.0, leads=200, conversions=2, cac=17500.0, revenue_from_channel=19600.0, roi=0.56),
    ChannelEconomics(channel="转介绍", period="2026-06", spend=2000.0, leads=15, conversions=1, cac=2000.0, revenue_from_channel=6800.0, roi=3.40),
    ChannelEconomics(channel="渠道", period="2026-06", spend=8000.0, leads=30, conversions=1, cac=8000.0, revenue_from_channel=6800.0, roi=0.85),
]

# 内存ID计数器
_next_cost_id = 6
_next_revenue_id = 9
_next_snapshot_id = 2

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _calculate_unit_economics(period: str) -> UnitEconomicsSnapshot:
    """计算指定月份的单位经济指标"""
    costs = [c for c in COST_ENTRIES if c.period == period]
    revenues = [r for r in REVENUE_ENTRIES if r.period == period]

    total_cost = sum(c.amount for c in costs)
    paying_revenues = [r for r in revenues if r.revenue > 0]
    total_revenue = sum(r.revenue for r in paying_revenues)
    new_customers = len(revenues)

    cac = _compute_cac(total_cost, new_customers)
    avg_revenue = _compute_avg_revenue(total_revenue, paying_revenues)
    ltv = _compute_ltv(avg_revenue)
    ltv_cac_ratio = _compute_ratio(ltv, cac)
    payback_months = _compute_payback(cac, avg_revenue)

    return UnitEconomicsSnapshot(
        period=period,
        cac=cac,
        ltv=ltv,
        ltv_cac_ratio=ltv_cac_ratio,
        avg_revenue_per_customer=avg_revenue,
        avg_gross_margin=0.72,
        payback_months=payback_months,
        new_customers=new_customers,
        churned_customers=0,
        total_active_customers=0,
        calculated_at=datetime.utcnow().isoformat() + "Z"
    )


def _compute_cac(total_cost: float, new_customers: int) -> float:
    return round(total_cost / new_customers, 2) if new_customers > 0 else 0.0


def _compute_avg_revenue(total_revenue: float, paying_revenues: list) -> float:
    return round(total_revenue / len(paying_revenues), 2) if paying_revenues else 0.0


def _compute_ltv(avg_revenue: float) -> float:
    """估算LTV = 平均月收入 * 平均留存月数（假设平均12个月 * 0.7折损）"""
    return round(avg_revenue * 12 * 0.7, 2)


def _compute_ratio(ltv: float, cac: float) -> float:
    return round(ltv / cac, 2) if cac > 0 else 0.0


def _compute_payback(cac: float, avg_revenue: float) -> float:
    return round(cac / avg_revenue, 1) if avg_revenue > 0 else 0.0


def _score_ltv_cac_ratio(ratio: float) -> int:
    if ratio >= 3.0:
        return 25
    elif ratio >= 2.0:
        return 15
    elif ratio >= 1.0:
        return 5
    return -15


def _score_payback_months(months: float) -> int:
    if months <= 6:
        return 15
    elif months <= 12:
        return 5
    return -10


def _score_gross_margin(margin: float) -> int:
    if margin >= 0.7:
        return 10
    elif margin >= 0.5:
        return 5
    return -5


def _health_level(score: int) -> str:
    if score >= 80:
        return "优秀"
    elif score >= 60:
        return "良好"
    elif score >= 40:
        return "警告"
    return "危险"


# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException
    router = APIRouter(prefix="/api/unit-economics", tags=["单位经济仪表盘"])

    # === 成本管理 ===

    @router.get("/costs", summary="获取成本条目列表")
    async def list_costs(period: Optional[str] = None, category: Optional[str] = None):
        results = COST_ENTRIES
        if period:
            results = [c for c in results if c.period == period]
        if category:
            results = [c for c in results if c.category == category]
        return {"costs": results, "total": len(results), "total_amount": sum(c.amount for c in results)}

    @router.post("/costs", summary="录入成本条目")
    async def create_cost(cost: CostEntry):
        global _next_cost_id
        cost.id = _next_cost_id
        _next_cost_id += 1
        cost.created_at = datetime.utcnow().isoformat() + "Z"
        COST_ENTRIES.append(cost)
        return {"id": cost.id, "message": "成本条目录入成功"}

    @router.delete("/costs/{cost_id}", summary="删除成本条目")
    async def delete_cost(cost_id: int):
        for i, c in enumerate(COST_ENTRIES):
            if c.id == cost_id:
                COST_ENTRIES.pop(i)
                return {"message": "删除成功"}
        raise HTTPException(status_code=404, detail="成本条目不存在")

    # === 收入管理 ===

    @router.get("/revenues", summary="获取收入条目列表")
    async def list_revenues(period: Optional[str] = None, channel: Optional[str] = None):
        results = REVENUE_ENTRIES
        if period:
            results = [r for r in results if r.period == period]
        if channel:
            results = [r for r in results if r.acquisition_channel == channel]
        return {"revenues": results, "total": len(results), "total_revenue": sum(r.revenue for r in results)}

    @router.post("/revenues", summary="录入收入条目")
    async def create_revenue(revenue: RevenueEntry):
        global _next_revenue_id
        revenue.id = _next_revenue_id
        _next_revenue_id += 1
        revenue.created_at = datetime.utcnow().isoformat() + "Z"
        REVENUE_ENTRIES.append(revenue)
        return {"id": revenue.id, "message": "收入条目录入成功"}

    # === 单位经济计算与仪表盘 ===

    @router.get("/calculate/{period}", summary="计算指定月份的单位经济指标")
    async def calculate_period(period: str):
        """根据当月成本和收入数据，重新计算单位经济指标"""
        snapshot = _calculate_unit_economics(period)
        global _next_snapshot_id
        snapshot.id = _next_snapshot_id
        _next_snapshot_id += 1
        snapshot.created_at = datetime.utcnow().isoformat() + "Z"

        # 更新或追加
        for i, s in enumerate(SNAPSHOTS):
            if s.period == period:
                SNAPSHOTS[i] = snapshot
                break
        else:
            SNAPSHOTS.append(snapshot)

        return snapshot

    @router.get("/dashboard", summary="获取单位经济仪表盘数据")
    async def get_dashboard(period: Optional[str] = None):
        """返回核心指标总览"""
        target = period or "2026-06"
        snapshot = None
        for s in SNAPSHOTS:
            if s.period == target:
                snapshot = s
                break
        if not snapshot:
            snapshot = _calculate_unit_economics(target)

        return {
            "period": target,
            "snapshot": snapshot,
            "health_score": _calculate_health_score(snapshot),
            "warnings": _get_warnings(snapshot),
            "recommendations": _get_recommendations(snapshot)
        }

    @router.get("/channels", summary="获取各渠道经济分析")
    async def get_channel_economics(period: Optional[str] = None):
        results = CHANNEL_ECONOMICS
        if period:
            results = [c for c in results if c.period == period]
        # 按ROI排序
        results = sorted(results, key=lambda c: c.roi, reverse=True)
        return {"channels": results, "total": len(results)}

    @router.get("/trend", summary="获取单位经济趋势")
    async def get_trend():
        """返回多个月份的单位经济指标趋势"""
        return {"snapshots": SNAPSHOTS, "periods": [s.period for s in SNAPSHOTS]}

    # === 辅助函数 ===

    def _calculate_health_score(snapshot: UnitEconomicsSnapshot) -> dict:
        """综合健康评分 0-100"""
        score = 50  # 基准
        score += _score_ltv_cac_ratio(snapshot.ltv_cac_ratio)
        score += _score_payback_months(snapshot.payback_months)
        score += _score_gross_margin(snapshot.avg_gross_margin)
        score = max(0, min(100, score))
        level = _health_level(score)
        return {"score": score, "level": level}

    def _get_warnings(snapshot: UnitEconomicsSnapshot) -> list[str]:
        warnings = []
        if snapshot.ltv_cac_ratio < 2.0:
            warnings.append(f"LTV/CAC比值({snapshot.ltv_cac_ratio})低于健康线3.0，需优化获客效率")
        if snapshot.payback_months > 12:
            warnings.append(f"回收周期({snapshot.payback_months}个月)过长，建议优化定价或降低CAC")
        if snapshot.avg_gross_margin < 0.5:
            warnings.append(f"毛利率({snapshot.avg_gross_margin*100:.0f}%)偏低，需分析成本结构")
        return warnings

    def _get_recommendations(snapshot: UnitEconomicsSnapshot) -> list[str]:
        recs = []
        if snapshot.ltv_cac_ratio < 3.0:
            recs.append("建议1: 提高客单价或增加交叉销售拉高LTV")
            recs.append("建议2: 优化投放渠道降低CAC，重点关注ROI>1.5的渠道")
        if snapshot.payback_months > 6:
            recs.append("建议3: 缩短付费周期，提供年付折扣激励")
        recs.append("建议4: 持续监控各渠道ROI，加大高效渠道预算分配")
        return recs

    print("[M6] 单位经济仪表盘路由已加载 ✓")
    print(f"[M6] 成本条目: {len(COST_ENTRIES)} 条 | 收入条目: {len(REVENUE_ENTRIES)} 条 | 渠道: {len(CHANNEL_ECONOMICS)} 个")

except ImportError:
    print("[M6] FastAPI未安装，跳过路由注册（数据层已就绪）")
    router = None
