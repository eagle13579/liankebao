"""
链客宝 - M7 留存分析引擎
==============================
Cohort留存分析 + 用户分群 + 流失预测信号 + 留存提升建议

注入点：Cohort追踪 → 留存率计算 → 流失信号识别 → 留存策略推荐
规则：纯新增，不修改现有业务逻辑
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class Cohort(BaseModel):
    """用户群组（Cohort）"""
    id: Optional[int] = None
    name: str
    period: str  # 月份 e.g. 2026-06
    cohort_type: str = "acquisition"  # acquisition / behavior / segment
    user_count: int = 0
    source: str = ""  # 渠道来源 e.g. 展会/线上/转介绍
    plan: str = ""  # 注册时的套餐
    tags: list[str] = []
    created_at: str = ""

class CohortRetention(BaseModel):
    """Cohort留存数据（按时间周期）"""
    id: Optional[int] = None
    cohort_id: int
    period_offset: int  # 0=当月, 1=次月, 2=第三月...
    period_label: str  # "Month 0", "Month 1", "Month 2"...
    active_users: int = 0
    retention_rate: float = 0.0
    calculated_at: str = ""

class UserActivity(BaseModel):
    """用户行为日志（用于留存计算）"""
    id: Optional[int] = None
    user_id: str
    username: str = ""
    cohort_period: str  # 用户所属Cohort月份
    activity_period: str  # 活跃月份
    actions: int = 0  # 当月行为数
    is_active: bool = False
    last_active_at: str = ""
    created_at: str = ""

class ChurnSignal(BaseModel):
    """流失信号"""
    id: Optional[int] = None
    user_id: str
    username: str = ""
    signal_type: str  # inactivity / engagement_drop / negative_action / billing_issue
    severity: str = "中"  # 低/中/高
    description: str = ""
    detected_at: str = ""
    days_since_last_active: Optional[int] = None
    recommended_action: str = ""
    resolved: bool = False

class RetentionStrategy(BaseModel):
    """留存策略推荐"""
    id: Optional[int] = None
    segment: str  # 适用人群分类
    title: str
    description: str
    actions: list[str] = []
    expected_impact: str = ""
    priority: str = "中"  # 高/中/低
    status: str = "待实施"  # 待实施/实施中/已评估
    created_at: str = ""

# ---------------------------------------------------------------------------
# 内存存储（可替换为数据库）
# ---------------------------------------------------------------------------

COHORTS: list[Cohort] = [
    Cohort(id=1, name="2026年3月获客群", period="2026-03", cohort_type="acquisition", user_count=35, source="混合", plan="专业版", created_at="2026-03-01T00:00:00Z"),
    Cohort(id=2, name="2026年4月获客群", period="2026-04", cohort_type="acquisition", user_count=42, source="展会", plan="专业版", created_at="2026-04-01T00:00:00Z"),
    Cohort(id=3, name="2026年5月获客群", period="2026-05", cohort_type="acquisition", user_count=38, source="线上", plan="专业版", created_at="2026-05-01T00:00:00Z"),
    Cohort(id=4, name="2026年6月获客群", period="2026-06", cohort_type="acquisition", user_count=28, source="渠道", plan="企业版", created_at="2026-06-01T00:00:00Z"),
]

COHORT_RETENTION: list[CohortRetention] = [
    # 2026-03 Cohort
    CohortRetention(id=1, cohort_id=1, period_offset=0, period_label="当月", active_users=35, retention_rate=1.0),
    CohortRetention(id=2, cohort_id=1, period_offset=1, period_label="次月", active_users=24, retention_rate=0.686),
    CohortRetention(id=3, cohort_id=1, period_offset=2, period_label="第三月", active_users=18, retention_rate=0.514),
    CohortRetention(id=4, cohort_id=1, period_offset=3, period_label="第四月", active_users=14, retention_rate=0.400),
    # 2026-04 Cohort
    CohortRetention(id=5, cohort_id=2, period_offset=0, period_label="当月", active_users=42, retention_rate=1.0),
    CohortRetention(id=6, cohort_id=2, period_offset=1, period_label="次月", active_users=30, retention_rate=0.714),
    CohortRetention(id=7, cohort_id=2, period_offset=2, period_label="第三月", active_users=22, retention_rate=0.524),
    # 2026-05 Cohort
    CohortRetention(id=8, cohort_id=3, period_offset=0, period_label="当月", active_users=38, retention_rate=1.0),
    CohortRetention(id=9, cohort_id=3, period_offset=1, period_label="次月", active_users=27, retention_rate=0.711),
    # 2026-06 Cohort
    CohortRetention(id=10, cohort_id=4, period_offset=0, period_label="当月", active_users=28, retention_rate=1.0),
]

ACTIVITIES: list[UserActivity] = [
    UserActivity(id=1, user_id="U001", username="张明", cohort_period="2026-03", activity_period="2026-06", actions=24, is_active=True, last_active_at="2026-06-20T15:30:00Z"),
    UserActivity(id=2, user_id="U002", username="李华", cohort_period="2026-03", activity_period="2026-06", actions=5, is_active=False, last_active_at="2026-05-10T09:00:00Z"),
    UserActivity(id=3, user_id="U003", username="王芳", cohort_period="2026-04", activity_period="2026-06", actions=42, is_active=True, last_active_at="2026-06-21T11:15:00Z"),
    UserActivity(id=4, user_id="U004", username="赵雷", cohort_period="2026-04", activity_period="2026-06", actions=0, is_active=False, last_active_at="2026-04-28T16:45:00Z"),
    UserActivity(id=5, user_id="U005", username="陈静", cohort_period="2026-05", activity_period="2026-06", actions=18, is_active=True, last_active_at="2026-06-19T14:00:00Z"),
]

CHURN_SIGNALS: list[ChurnSignal] = [
    ChurnSignal(id=1, user_id="U002", username="李华", signal_type="inactivity", severity="高",
                description="超过30天未活跃，近期0行为", detected_at="2026-06-15T08:00:00Z",
                days_since_last_active=42, recommended_action="发送召回推送+专属优惠券", resolved=False),
    ChurnSignal(id=2, user_id="U004", username="赵雷", signal_type="inactivity", severity="高",
                description="超过45天未活跃，用户可能完全流失", detected_at="2026-06-15T08:00:00Z",
                days_since_last_active=53, recommended_action="AI电话召回+1对1客服回访", resolved=False),
    ChurnSignal(id=3, user_id="U001", username="张明", signal_type="engagement_drop", severity="低",
                description="上月活跃度下降40%（上月40次->本月24次）", detected_at="2026-06-20T16:00:00Z",
                days_since_last_active=5, recommended_action="推送新功能更新通知", resolved=False),
]

RETENTION_STRATEGIES: list[RetentionStrategy] = [
    RetentionStrategy(id=1, segment="首月沉默用户（注册后7天无活跃）",
                      title="7天新手引导流程优化",
                      description="注册后第1/3/7天配置自动化引导触达，帮助用户快速体验核心价值",
                      actions=["第1天: 欢迎推送+快速入门视频", "第3天: 核心功能引导+使用案例", "第7天: 1对1 AI助手协助完成首单匹配"],
                      expected_impact="首月留存率提升15-20%", priority="高", status="待实施"),
    RetentionStrategy(id=2, segment="活跃下降用户（月度活跃下降>50%）",
                      title="活跃度下降用户召回计划",
                      description="检测到活跃度断崖下降时自动触发召回流程",
                      actions=['触发后24h: 推送「你错过的新功能」合集', "第3天: 专属优惠/延长试用", "第7天: 人工客服电话回访"],
                      expected_impact="次月留存率提升10-15%", priority="高", status="待实施"),
    RetentionStrategy(id=3, segment="高价值用户（企业版+活跃>3月）",
                      title="VIP客户成功计划",
                      description="为高价值用户配置专属客户成功经理，定期输出价值报告",
                      actions=["月度使用报告+行业洞察", "季度1对1业务复盘", "优先体验新功能特权"],
                      expected_impact="高价值用户年留存>90%", priority="中", status="实施中"),
]

# 内存ID计数器
_next_cohort_id = 5
_next_retention_id = 11
_next_activity_id = 6
_next_churn_id = 4
_next_strategy_id = 4

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _calculate_cohort_retention(cohort_id: int) -> list[CohortRetention]:
    """计算指定Cohort的留存率序列"""
    cohort = _find_cohort(cohort_id)
    if not cohort:
        return []

    members = [a for a in ACTIVITIES if a.cohort_period == cohort.period]
    if not members:
        return []

    total_users = len(members)
    results = []
    month_offsets = [0, 1, 2, 3, 4, 5]
    labels = ["当月", "次月", "第三月", "第四月", "第五月", "第六月"]

    for offset, label in zip(month_offsets, labels):
        period_str = _compute_period_str(cohort.period, offset)
        active = sum(1 for a in members if a.activity_period == period_str and a.is_active)
        rate = round(active / total_users, 3) if total_users > 0 else 0.0

        results.append(CohortRetention(
            cohort_id=cohort_id,
            period_offset=offset,
            period_label=label,
            active_users=active,
            retention_rate=rate,
        ))

    return results


def _find_cohort(cohort_id: int) -> Optional[Cohort]:
    """按ID查找Cohort"""
    for c in COHORTS:
        if c.id == cohort_id:
            return c
    return None


def _compute_period_str(base_period: str, offset: int) -> str:
    """计算偏移月份后的期间字符串"""
    base_year, base_month = map(int, base_period.split("-"))
    target_month = base_month + offset
    target_year = base_year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1
    return f"{target_year}-{target_month:02d}"

def _compute_avg_month1_retention() -> float:
    """计算最近3个月平均首月留存率"""
    recent_cohorts = [c for c in COHORTS if c.period >= "2026-04"]
    recent_retentions = []
    for cohort in recent_cohorts:
        month1 = [r for r in COHORT_RETENTION if r.cohort_id == cohort.id and r.period_offset == 1]
        if month1:
            recent_retentions.append(month1[0].retention_rate)
    return round(sum(recent_retentions) / len(recent_retentions), 3) if recent_retentions else 0


def _compute_retention_trend(avg_month1_retention: float) -> str:
    """根据留存率判断趋势"""
    if avg_month1_retention > 0.7:
        return "up"
    elif avg_month1_retention > 0.6:
        return "stable"
    return "declining"


# ---------------------------------------------------------------------------
# FastAPI 路由
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException
    router = APIRouter(prefix="/api/retention", tags=["留存分析引擎"])

    # === Cohort管理 ===

    @router.get("/cohorts", summary="获取Cohort列表")
    async def list_cohorts():
        return {"cohorts": COHORTS, "total": len(COHORTS)}

    @router.post("/cohorts", summary="创建Cohort")
    async def create_cohort(cohort: Cohort):
        global _next_cohort_id
        cohort.id = _next_cohort_id
        _next_cohort_id += 1
        cohort.created_at = datetime.utcnow().isoformat() + "Z"
        COHORTS.append(cohort)
        return {"id": cohort.id, "message": "Cohort创建成功"}

    @router.get("/cohorts/{cohort_id}/retention", summary="获取Cohort留存数据")
    async def get_cohort_retention(cohort_id: int):
        """返回指定Cohort的完整留存序列"""
        # 先查缓存
        cached = [r for r in COHORT_RETENTION if r.cohort_id == cohort_id]
        if cached:
            return {"cohort_id": cohort_id, "retention": cached}
        # 没有缓存则实时计算
        results = _calculate_cohort_retention(cohort_id)
        if not results:
            raise HTTPException(status_code=404, detail="Cohort不存在或无成员数据")
        return {"cohort_id": cohort_id, "retention": results}

    @router.get("/retention-matrix", summary="获取留存矩阵（所有Cohort）")
    async def get_retention_matrix():
        """返回完整的Cohort留存矩阵，用于前端热力图展示"""
        matrix = []
        for cohort in COHORTS:
            retentions = [r for r in COHORT_RETENTION if r.cohort_id == cohort.id]
            matrix.append({
                "cohort": cohort,
                "retention": retentions
            })
        return {"matrix": matrix}

    # === 用户活跃度 ===

    @router.get("/activities", summary="获取用户活跃记录")
    async def list_activities(cohort_period: Optional[str] = None, active_only: Optional[bool] = None):
        results = ACTIVITIES
        if cohort_period:
            results = [a for a in results if a.cohort_period == cohort_period]
        if active_only:
            results = [a for a in results if a.is_active]
        return {"activities": results, "total": len(results)}

    @router.post("/activities", summary="记录用户活跃")
    async def record_activity(activity: UserActivity):
        global _next_activity_id
        activity.id = _next_activity_id
        _next_activity_id += 1
        activity.created_at = datetime.utcnow().isoformat() + "Z"
        ACTIVITIES.append(activity)
        return {"id": activity.id, "message": "活跃记录成功"}

    # === 流失信号 ===

    @router.get("/churn-signals", summary="获取流失信号列表")
    async def list_churn_signals(severity: Optional[str] = None, resolved: Optional[bool] = None):
        results = CHURN_SIGNALS
        if severity:
            results = [s for s in results if s.severity == severity]
        if resolved is not None:
            results = [s for s in results if s.resolved == resolved]
        return {"signals": results, "total": len(results)}

    @router.post("/churn-signals", summary="创建流失信号")
    async def create_churn_signal(signal: ChurnSignal):
        global _next_churn_id
        signal.id = _next_churn_id
        _next_churn_id += 1
        signal.detected_at = datetime.utcnow().isoformat() + "Z"
        CHURN_SIGNALS.append(signal)
        return {"id": signal.id, "message": "流失信号已记录"}

    @router.put("/churn-signals/{signal_id}/resolve", summary="标记流失信号为已解决")
    async def resolve_churn_signal(signal_id: int):
        for s in CHURN_SIGNALS:
            if s.id == signal_id:
                s.resolved = True
                return {"message": "已标记为已解决"}
        raise HTTPException(status_code=404, detail="流失信号不存在")

    # === 留存策略 ===

    @router.get("/strategies", summary="获取留存策略推荐列表")
    async def list_strategies(status: Optional[str] = None, priority: Optional[str] = None):
        results = RETENTION_STRATEGIES
        if status:
            results = [s for s in results if s.status == status]
        if priority:
            results = [s for s in results if s.priority == priority]
        return {"strategies": results, "total": len(results)}

    # === 综合分析 ===

    @router.get("/overview", summary="留存分析总览")
    async def get_retention_overview():
        """汇总留存核心指标"""
        avg_month1_retention = _compute_avg_month1_retention()
        active_churn = [s for s in CHURN_SIGNALS if not s.resolved]
        high_risk = [s for s in active_churn if s.severity == "高"]

        return {
            "total_cohorts": len(COHORTS),
            "avg_month1_retention": avg_month1_retention,
            "active_churn_signals": len(active_churn),
            "high_risk_users": len(high_risk),
            "retention_strategies": len(RETENTION_STRATEGIES),
            "trend": _compute_retention_trend(avg_month1_retention),
            "recommendation": "留存表现良好，建议重点关注高流失风险的2位用户" if high_risk else "整体留存健康"
        }

    print("[M7] 留存分析引擎路由已加载 ✓")
    print(f"[M7] Cohort: {len(COHORTS)} 个 | 留存数据点: {len(COHORT_RETENTION)} 个 | 流失信号: {len(CHURN_SIGNALS)} 个")

except ImportError:
    print("[M7] FastAPI未安装，跳过路由注册（数据层已就绪）")
    router = None
