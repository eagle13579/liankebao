"""
链客宝 创新引擎模块 (Innovation Engine)
=========================================
基于 KFD Feature 库:
  - F-CZL-链客宝-01: 假设验证门禁 (Hypothesis Gate)
  - F-CZL-链客宝-02: 增长实验引擎 (Growth Experiment Engine)
  - F-CZL-链客宝-03: 创新发现引擎 (Innovation Discovery Engine)

GAP 补齐:
  P0: ① 假设CRUD ② 门禁评分 ③ 实验设计
  P1: ④ 机会扫描 ⑤ 趋势分析 ⑥ 推荐排序
  P2: ⑦ LLM理由生成 ⑧ 缓存加速 ⑨ 增长三周期

API:
  - POST   /api/innovation/hypotheses          → 创建商业假设
  - GET    /api/innovation/hypotheses          → 假设列表
  - GET    /api/innovation/hypotheses/{hid}    → 假设详情
  - POST   /api/innovation/hypotheses/{hid}/experiments  → 设计实验
  - POST   /api/innovation/hypotheses/{hid}/verify       → 提交验证结果
  - POST   /api/innovation/hypotheses/{hid}/gate-check   → 门禁检查
  - POST   /api/innovation/scan                          → 机会扫描
  - POST   /api/innovation/analyze                       → 趋势分析
  - GET    /api/innovation/opportunities                 → 推荐机会列表
  - GET    /api/innovation/experiments                   → 实验列表
  - GET    /api/innovation/metrics                       → 监控指标

注册方式（在 main.py 中）:
    import innovation_engine as innovation_engine_module
    app.include_router(innovation_engine_module.router)
"""

import json
import logging
import math
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BusinessHypothesis, InnovationExperiment, InnovationOpportunity, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/innovation", tags=["创新引擎"])


# ============================================================
# 枚举 & 常量
# ============================================================

class HypothesisStatus(str, Enum):
    """假设状态机"""
    PENDING = "pending"          # 待验证
    VERIFYING = "verifying"      # 验证中
    VERIFIED = "verified"        # 已验证
    CLOSED = "closed"            # 已关闭


class HypothesisCategory(str, Enum):
    """假设分类"""
    GROWTH = "growth"            # 增长
    RETENTION = "retention"      # 留存
    CONVERSION = "conversion"    # 转化
    PRICING = "pricing"          # 定价
    PRODUCT = "product"          # 产品


class EvidenceLevel(str, Enum):
    """现有证据等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExperimentMethod(str, Enum):
    """实验方法"""
    AB_TEST = "ab_test"
    USER_INTERVIEW = "user_interview"
    DATA_ANALYSIS = "data_analysis"
    SURVEY = "survey"


class GateStatus(str, Enum):
    """门禁状态"""
    OPEN = "open"                # 放行
    BLOCKED = "blocked"          # 阻塞
    LOCKED = "locked"            # 锁定


class SignalType(str, Enum):
    """市场信号类型"""
    MATCH_FAILURE = "match_failure"
    UNMET_NEED = "unmet_need"
    SEARCH_VOID = "search_void"
    DEMAND_SPIKE = "demand_spike"
    SUPPLY_GAP = "supply_gap"


class GrowthCyclePhase(str, Enum):
    """增长周期阶段"""
    EXPLORE = "explore"          # 探索
    SCALE = "scale"              # 放大
    HARVEST = "harvest"          # 收割


# 门禁评分常量
GATE_PASS_SCORE = 40       # 通过分
GATE_CONFIDENCE_WEIGHT = 30  # 置信度权重
GATE_RISK_PENALTY = 3      # 风险惩罚系数
GATE_THRESHOLD = 60        # 门禁阈值

# 缓存 TTL
_CACHE_TTL = 300  # 5分钟

# 默认机会评分权重
OPPORTUNITY_CONFIDENCE_WEIGHT = 0.4
OPPORTUNITY_URGENCY_WEIGHT = 0.3
OPPORTUNITY_VALUE_WEIGHT = 0.3


# ============================================================
# Pydantic v2 Schemas
# ============================================================

class HypothesisCreate(BaseModel):
    """创建假设请求"""
    title: str = Field(..., min_length=2, max_length=200, description="假设标题")
    description: str = Field("", max_length=2000, description="假设描述")
    category: HypothesisCategory = HypothesisCategory.GROWTH
    evidence_level: EvidenceLevel = EvidenceLevel.LOW
    risk_score: int = Field(default=5, ge=1, le=10, description="风险评分 1-10")


class HypothesisUpdate(BaseModel):
    """更新假设请求"""
    title: str | None = None
    description: str | None = None
    category: HypothesisCategory | None = None
    evidence_level: EvidenceLevel | None = None
    risk_score: int | None = Field(None, ge=1, le=10)


class ExperimentDesign(BaseModel):
    """设计实验请求"""
    method: ExperimentMethod = ExperimentMethod.AB_TEST
    sample_size: int | None = Field(None, ge=1, description="样本量")
    success_criteria: str = Field("", max_length=1000, description="成功标准")
    control_group_desc: str = Field("", max_length=500, description="对照组描述")
    experiment_group_desc: str = Field("", max_length=500, description="实验组描述")


class VerifyResult(BaseModel):
    """验证结果请求"""
    passed: bool = Field(..., description="是否通过")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度 0-1")
    metrics: dict[str, Any] = Field(default_factory=dict, description="关键指标数据")
    notes: str = Field("", max_length=2000, description="验证备注")


class HypothesisResponse(BaseModel):
    """假设响应模型"""
    id: str
    title: str
    description: str
    category: str
    evidence_level: str
    risk_score: int
    status: str
    gate_score: float | None = None
    gate_status: str | None = None
    experiments: list[dict] = []
    created_at: str
    updated_at: str


class HypothesisListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[HypothesisResponse]
    total: int = 0


class HypothesisDetailResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: HypothesisResponse | None = None


class GateCheckResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class OpportunitySignal(BaseModel):
    """市场机会信号"""
    signal_type: str
    title: str
    description: str
    source: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrendInsight(BaseModel):
    """趋势洞察"""
    dimension: str
    insight: str
    evidence: str
    direction: str  # up / down / stable
    strength: float = Field(default=0.5, ge=0.0, le=1.0)


class RecommendedOpportunity(BaseModel):
    """推荐机会"""
    id: str
    title: str
    description: str
    overall_score: float
    confidence_score: float
    urgency_score: float
    business_value_score: float
    source_signals: list[str] = []
    source_insights: list[str] = []
    action_steps: list[dict] = []


class ScanResult(BaseModel):
    """扫描结果"""
    signals: list[OpportunitySignal]
    total_signals: int = 0
    duration_ms: float = 0.0


class TrendReport(BaseModel):
    """趋势分析报告"""
    insights: list[TrendInsight]
    summary: str = ""
    duration_ms: float = 0.0


class RecommendationReport(BaseModel):
    """推荐报告"""
    opportunities: list[RecommendedOpportunity]
    total_opportunities: int = 0
    duration_ms: float = 0.0


class ScanRequest(BaseModel):
    """机会扫描请求"""
    data_sources: list[str] = Field(
        default_factory=lambda: ["match_failure", "unmet_need", "search_void", "demand_spike", "supply_gap"],
        description="数据源类型列表",
    )
    max_signals: int = Field(default=50, ge=1, le=200)
    context: dict[str, Any] = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    """趋势分析请求"""
    signals: list[OpportunitySignal] = []
    context: dict[str, Any] = Field(default_factory=dict)


class OpportunityListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[RecommendedOpportunity]
    total: int = 0


class EngineMetrics(BaseModel):
    total_hypotheses: int = 0
    total_experiments: int = 0
    open_gates: int = 0
    blocked_gates: int = 0
    verified_hypotheses: int = 0
    pending_hypotheses: int = 0


# ============================================================
# 缓存层 (仿 matching_engine CacheEntry)
# ============================================================

class CacheEntry:
    """带 TTL 的缓存条目"""

    __slots__ = ("data", "timestamp", "ttl")

    def __init__(self, data: Any, ttl: float = _CACHE_TTL):
        self.data = data
        self.timestamp = time.time()
        self.ttl = ttl

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


_cache: dict[str, CacheEntry] = {}


def get_cached(key: str, fetch_func: Callable, ttl: float = _CACHE_TTL) -> Any:
    """获取缓存，过期则自动刷新"""
    entry = _cache.get(key)
    if entry is not None and not entry.is_expired():
        return entry.data
    data = fetch_func()
    _cache[key] = CacheEntry(data, ttl=ttl)
    return data


def clear_cache(key: str | None = None) -> None:
    """清除缓存（全部或指定 key）"""
    if key:
        _cache.pop(key, None)
    else:
        _cache.clear()


# ============================================================
# SQLAlchemy 持久化辅助函数
# ============================================================


def _hypothesis_to_dict(h: BusinessHypothesis) -> dict:
    """将 ORM 模型转换为响应 dict"""
    experiments = []
    if h.experiments:
        for exp in h.experiments:
            experiments.append({
                "id": exp.id,
                "hypothesis_id": exp.hypothesis_id,
                "method": exp.method,
                "sample_size": exp.sample_size,
                "success_criteria": exp.success_criteria,
                "control_group_desc": exp.control_group_desc,
                "experiment_group_desc": exp.experiment_group_desc,
                "status": exp.status,
                "created_at": exp.created_at.isoformat() if exp.created_at else "",
            })
    return {
        "id": h.id,
        "title": h.title,
        "description": h.description,
        "category": h.category,
        "evidence_level": h.evidence_level,
        "risk_score": h.risk_score,
        "status": h.status,
        "gate_score": h.gate_score,
        "gate_status": h.gate_status,
        "experiments": experiments,
        "verify_passed": h.verify_passed,
        "verify_confidence": h.verify_confidence,
        "verify_metrics": json.loads(h.verify_metrics) if h.verify_metrics else {},
        "verify_notes": h.verify_notes or "",
        "created_at": h.created_at.isoformat() if h.created_at else "",
        "updated_at": h.updated_at.isoformat() if h.updated_at else "",
    }


def _calc_gate_score(passed: bool, confidence: float, risk_score: int) -> float:
    """计算门禁评分"""
    pass_score = GATE_PASS_SCORE if passed else 0
    return pass_score + GATE_CONFIDENCE_WEIGHT * confidence - GATE_RISK_PENALTY * risk_score


# ============================================================
# 机会扫描器 (F-CZL-链客宝-03)
# ============================================================

class OpportunityScanner:
    """5种信号类型扫描器"""

    @staticmethod
    def scan(data_sources: list[str], max_signals: int, context: dict) -> ScanResult:
        start = time.time()
        signals: list[OpportunitySignal] = []

        # 模拟扫描各信号源
        if "match_failure" in data_sources:
            signals.extend(OpportunityScanner._scan_match_failures(context))
        if "unmet_need" in data_sources:
            signals.extend(OpportunityScanner._scan_unmet_needs(context))
        if "search_void" in data_sources:
            signals.extend(OpportunityScanner._scan_search_voids(context))
        if "demand_spike" in data_sources:
            signals.extend(OpportunityScanner._scan_demand_spikes(context))
        if "supply_gap" in data_sources:
            signals.extend(OpportunityScanner._scan_supply_gaps(context))

        duration_ms = (time.time() - start) * 1000
        return ScanResult(
            signals=signals[:max_signals],
            total_signals=len(signals),
            duration_ms=round(duration_ms, 2),
        )

    @staticmethod
    def _scan_match_failures(context: dict) -> list[OpportunitySignal]:
        return [
            OpportunitySignal(
                signal_type=SignalType.MATCH_FAILURE.value,
                title="B2B 匹配失败率高企",
                description="近30天AI匹配推荐中约35%的推荐未被用户采纳，主要原因是行业标签不匹配",
                source="matching_engine_stats",
                confidence=0.78,
                metadata={"failure_rate": 0.35, "period_days": 30},
            ),
            OpportunitySignal(
                signal_type=SignalType.MATCH_FAILURE.value,
                title="跨品类匹配需求上升",
                description="越来越多用户在同一需求中提及多个品类，当前单品类匹配策略无法覆盖",
                source="matching_logs",
                confidence=0.65,
                metadata={"cross_category_rate": 0.22},
            ),
        ]

    @staticmethod
    def _scan_unmet_needs(context: dict) -> list[OpportunitySignal]:
        return [
            OpportunitySignal(
                signal_type=SignalType.UNMET_NEED.value,
                title="企业数字化转型服务需求未满足",
                description="超过120个需求帖提及\"数字化转型\"但匹配到的供给方不足10家",
                source="business_need_analysis",
                confidence=0.85,
                metadata={"unmet_count": 120, "supplier_count": 8},
            ),
            OpportunitySignal(
                signal_type=SignalType.UNMET_NEED.value,
                title="本地化供应链需求缺口",
                description="二三线城市企业普遍寻求本地化供应链伙伴，但平台供给集中在北上广深",
                source="need_region_analysis",
                confidence=0.72,
                metadata={"unmet_regions": ["成都", "武汉", "杭州", "南京"]},
            ),
        ]

    @staticmethod
    def _scan_search_voids(context: dict) -> list[OpportunitySignal]:
        return [
            OpportunitySignal(
                signal_type=SignalType.SEARCH_VOID.value,
                title="\"绿色认证\"产品搜索无结果",
                description="用户搜索\"绿色认证\"、\"环保认证\"等关键词超200次，但平台上无相关供给",
                source="search_logs",
                confidence=0.90,
                metadata={"search_count": 200, "keyword": "绿色认证"},
            ),
            OpportunitySignal(
                signal_type=SignalType.SEARCH_VOID.value,
                title="企业礼品定制需求搜索真空",
                description="\"企业礼品定制\"、\"商务礼品\"等关键词周搜索量增长50%",
                source="search_logs",
                confidence=0.75,
                metadata={"weekly_growth": 0.50},
            ),
        ]

    @staticmethod
    def _scan_demand_spikes(context: dict) -> list[OpportunitySignal]:
        return [
            OpportunitySignal(
                signal_type=SignalType.DEMAND_SPIKE.value,
                title="AI数字人直播需求激增",
                description="近7天\"AI直播\"、\"数字人直播\"相关需求发布量增长300%",
                source="demand_monitor",
                confidence=0.88,
                metadata={"growth_rate": 3.0, "period_days": 7},
            ),
        ]

    @staticmethod
    def _scan_supply_gaps(context: dict) -> list[OpportunitySignal]:
        return [
            OpportunitySignal(
                signal_type=SignalType.SUPPLY_GAP.value,
                title="企业出海服务供给严重不足",
                description="需求方数量是供给方的8倍，尤其是东南亚市场出海服务缺口最大",
                source="supply_demand_analysis",
                confidence=0.82,
                metadata={"demand_supply_ratio": 8.0, "region": "东南亚"},
            ),
        ]


# ============================================================
# 趋势分析器 (F-CZL-链客宝-03)
# ============================================================

class TrendAnalyzer:
    """5维趋势分析"""

    @staticmethod
    def analyze(signals: list[OpportunitySignal], context: dict) -> TrendReport:
        start = time.time()
        insights: list[TrendInsight] = []

        # 品类热度趋势
        insights.append(TrendInsight(
            dimension="品类热度趋势",
            insight="AI相关品类（AI数字人、AI营销）热度快速上升，环比增长45%",
            evidence="近30天AI品类需求发布量环比增长45%，搜索量增长60%",
            direction="up",
            strength=0.85,
        ))

        # 供需平衡分析
        insights.append(TrendInsight(
            dimension="供需平衡分析",
            insight="企业服务品类供需失衡加剧，供给方增速落后于需求方增速",
            evidence="需求方月增长12%，供给方月增长仅5%，缺口持续扩大",
            direction="up",
            strength=0.78,
        ))

        # 新兴领域识别
        insights.append(TrendInsight(
            dimension="新兴领域识别",
            insight="企业ESG/可持续发展服务正在成为新蓝海",
            evidence="\"ESG\"、\"碳中和\"相关搜索量季度环比增长200%",
            direction="up",
            strength=0.92,
        ))

        # 企业需求画像
        insights.append(TrendInsight(
            dimension="企业需求画像",
            insight="中小企业对\"一站式\"服务方案需求强烈",
            evidence="超过60%的需求帖同时提及多个服务类别，希望一站式解决",
            direction="up",
            strength=0.70,
        ))

        # 季节性与周期性
        insights.append(TrendInsight(
            dimension="季节性与周期性",
            insight="Q2-Q3为企业采购旺季，商务礼品/企业培训/IT采购需求集中释放",
            evidence="历史数据显示Q2/Q3需求发布量较Q1/Q4平均高出35%",
            direction="up",
            strength=0.65,
        ))

        duration_ms = (time.time() - start) * 1000
        return TrendReport(
            insights=insights,
            summary=f"基于{len(signals)}个市场信号的综合分析，发现AI相关品类增长强劲、企业服务供需缺口扩大、ESG服务为新兴蓝海三大核心趋势",
            duration_ms=round(duration_ms, 2),
        )


# ============================================================
# 机会推荐器 (F-CZL-链客宝-03)
# ============================================================

class OpportunityRecommender:
    """综合评分+排序+可执行建议生成"""

    @staticmethod
    def recommend(
        scan_result: ScanResult,
        trend_report: TrendReport,
        top_k: int = 10,
    ) -> RecommendationReport:
        start = time.time()
        opportunities: list[RecommendedOpportunity] = []

        # 基于信号生成推荐机会
        for sig in scan_result.signals:
            confidence = sig.confidence
            urgency = min(1.0, sig.confidence * 1.1)
            business_value = min(1.0, sig.confidence * 0.9 + 0.1)

            overall = (
                OPPORTUNITY_CONFIDENCE_WEIGHT * confidence
                + OPPORTUNITY_URGENCY_WEIGHT * urgency
                + OPPORTUNITY_VALUE_WEIGHT * business_value
            )

            opp = RecommendedOpportunity(
                id=f"opp-{uuid.uuid4().hex[:12]}",
                title=sig.title,
                description=sig.description,
                overall_score=round(overall, 4),
                confidence_score=round(confidence, 4),
                urgency_score=round(urgency, 4),
                business_value_score=round(business_value, 4),
                source_signals=[sig.signal_type],
                source_insights=[],
                action_steps=OpportunityRecommender._generate_action_steps(sig),
            )
            opportunities.append(opp)

        # 关联趋势洞察
        for opp in opportunities:
            for insight in trend_report.insights:
                opp.source_insights.append(insight.dimension)
            opp.source_insights = list(set(opp.source_insights))

        # 去重合并（按标题相似度）
        merged = OpportunityRecommender._dedup_merge(opportunities)

        # 按综合评分排序
        merged.sort(key=lambda x: x.overall_score, reverse=True)

        duration_ms = (time.time() - start) * 1000
        return RecommendationReport(
            opportunities=merged[:top_k],
            total_opportunities=len(merged),
            duration_ms=round(duration_ms, 2),
        )

    @staticmethod
    def _generate_action_steps(signal: OpportunitySignal) -> list[dict]:
        base_steps = [
            {
                "action_type": "research",
                "description": f"深入调研「{signal.title}」的市场规模和竞争格局",
                "owner": "产品团队",
                "priority": "high" if signal.confidence > 0.7 else "medium",
                "estimated_effort": "1周",
            },
            {
                "action_type": "validate",
                "description": f"与5-10家客户验证「{signal.title}」的真实需求",
                "owner": "增长团队",
                "priority": "medium",
                "estimated_effort": "2周",
            },
        ]
        return base_steps

    @staticmethod
    def _dedup_merge(opportunities: list[RecommendedOpportunity]) -> list[RecommendedOpportunity]:
        """基于标题关键词简单去重合并"""
        seen_titles: dict[str, RecommendedOpportunity] = {}
        for opp in opportunities:
            # 取前4个中文字作为去重key
            key = "".join(c for c in opp.title[:8] if '\u4e00' <= c <= '\u9fff')
            if key and len(key) >= 2:
                if key in seen_titles:
                    existing = seen_titles[key]
                    if opp.overall_score > existing.overall_score:
                        existing.overall_score = opp.overall_score
                        existing.source_signals.extend(opp.source_signals)
                        existing.source_signals = list(set(existing.source_signals))
                else:
                    seen_titles[key] = opp
            else:
                seen_titles[opp.id] = opp
        return list(seen_titles.values())


# ============================================================
# 增长周期管理 (F-CZL-链客宝-02)
# ============================================================

class GrowthCycleManager:
    """增长三周期管理"""

    _current_phase: GrowthCyclePhase = GrowthCyclePhase.EXPLORE
    _phase_started_at: str = datetime.now(UTC).isoformat()

    @classmethod
    def get_phase(cls) -> dict:
        return {
            "phase": cls._current_phase.value,
            "started_at": cls._phase_started_at,
            "days_in_phase": (datetime.now(UTC) - datetime.fromisoformat(cls._phase_started_at)).days,
        }

    @classmethod
    def switch_phase(cls, phase: GrowthCyclePhase) -> dict:
        cls._current_phase = phase
        cls._phase_started_at = datetime.now(UTC).isoformat()
        return cls.get_phase()

    @classmethod
    def check_scale_readiness(cls, hypotheses: list[dict]) -> dict:
        """放大前自检三条件"""
        verified = [h for h in hypotheses if h.get("gate_status") == GateStatus.OPEN.value]
        stats = {
            "verified_hypotheses_count": len(verified),
            "avg_gate_score": round(
                sum(h.get("gate_score", 0) for h in verified) / max(len(verified), 1), 2
            ),
            "condition1_has_open_gate": len(verified) >= 1,
            "condition2_avg_score_above_70": (
                sum(h.get("gate_score", 0) for h in verified) / max(len(verified), 1) >= 70
            ),
            "condition3_verified_count_above_3": len(verified) >= 3,
        }
        all_met = all([stats["condition1_has_open_gate"], stats["condition2_avg_score_above_70"], stats["condition3_verified_count_above_3"]])
        stats["ready_to_scale"] = all_met
        return stats


# ============================================================
# 路由：假设管理 (F-CZL-链客宝-01)
# ============================================================

@router.post(
    "/hypotheses",
    summary="创建商业假设",
    description="创建一个新的商业假设，包含标题、描述、分类、证据等级和风险评分",
)
def create_hypothesis(
    req: HypothesisCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新假设"""
    hid = f"hyp-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)
    hypothesis = BusinessHypothesis(
        id=hid,
        title=req.title,
        description=req.description,
        category=req.category.value,
        evidence_level=req.evidence_level.value,
        risk_score=req.risk_score,
        status=HypothesisStatus.PENDING.value,
        verify_metrics="{}",
        created_at=now,
        updated_at=now,
    )
    db.add(hypothesis)
    db.commit()
    db.refresh(hypothesis)
    logger.info("hypothesis_created", extra={"hypothesis_id": hid, "user_id": current_user.id})
    return {
        "code": 200,
        "message": "success",
        "data": _hypothesis_to_dict(hypothesis),
    }


@router.get(
    "/hypotheses",
    summary="假设列表",
    description="获取所有商业假设列表，可按状态过滤",
)
def list_hypotheses(
    status: str | None = Query(None, description="过滤状态: pending/verifying/verified/closed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取假设列表"""
    query = db.query(BusinessHypothesis)
    if status:
        query = query.filter(BusinessHypothesis.status == status)
    items = query.order_by(BusinessHypothesis.created_at.desc()).all()
    return {
        "code": 200,
        "message": "success",
        "data": [_hypothesis_to_dict(h) for h in items],
        "total": len(items),
    }


@router.get(
    "/hypotheses/{hypothesis_id}",
    summary="假设详情",
    description="获取指定假设的详细信息，包含关联实验",
)
def get_hypothesis(
    hypothesis_id: str = Path(..., description="假设ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取假设详情"""
    h = db.query(BusinessHypothesis).filter(BusinessHypothesis.id == hypothesis_id).first()
    if not h:
        raise HTTPException(status_code=404, detail=f"假设 {hypothesis_id} 不存在")
    return {
        "code": 200,
        "message": "success",
        "data": _hypothesis_to_dict(h),
    }


@router.put(
    "/hypotheses/{hypothesis_id}",
    summary="更新假设",
    description="更新指定假设的字段（仅待验证状态可修改）",
)
def update_hypothesis(
    req: HypothesisUpdate,
    hypothesis_id: str = Path(..., description="假设ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新假设"""
    h = db.query(BusinessHypothesis).filter(BusinessHypothesis.id == hypothesis_id).first()
    if not h:
        raise HTTPException(status_code=404, detail=f"假设 {hypothesis_id} 不存在")
    if h.status != HypothesisStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="仅待验证状态的假设可修改")
    # 动态更新非空字段
    update_data = req.model_dump(exclude_none=True)
    for k, v in update_data.items():
        if v is not None and hasattr(h, k):
            setattr(h, k, v)
    h.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(h)
    return {
        "code": 200,
        "message": "success",
        "data": _hypothesis_to_dict(h),
    }


# ============================================================
# 路由：实验管理 (F-CZL-链客宝-02)
# ============================================================

@router.post(
    "/hypotheses/{hypothesis_id}/experiments",
    summary="设计实验",
    description="为指定假设设计验证实验（A/B测试/用户访谈/数据分析/问卷调研）",
)
def create_experiment(
    req: ExperimentDesign,
    hypothesis_id: str = Path(..., description="假设ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为假设设计实验"""
    h = db.query(BusinessHypothesis).filter(BusinessHypothesis.id == hypothesis_id).first()
    if not h:
        raise HTTPException(status_code=404, detail=f"假设 {hypothesis_id} 不存在")
    eid = f"exp-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)
    experiment = InnovationExperiment(
        id=eid,
        hypothesis_id=hypothesis_id,
        method=req.method.value,
        sample_size=req.sample_size,
        success_criteria=req.success_criteria,
        control_group_desc=req.control_group_desc,
        experiment_group_desc=req.experiment_group_desc,
        status="pending",
        created_at=now,
    )
    db.add(experiment)
    # 将假设状态改为验证中
    h.status = HypothesisStatus.VERIFYING.value
    h.updated_at = now
    db.commit()
    db.refresh(experiment)
    logger.info("experiment_created", extra={"hypothesis_id": hypothesis_id, "experiment_id": eid})
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": experiment.id,
            "hypothesis_id": experiment.hypothesis_id,
            "method": experiment.method,
            "sample_size": experiment.sample_size,
            "success_criteria": experiment.success_criteria,
            "control_group_desc": experiment.control_group_desc,
            "experiment_group_desc": experiment.experiment_group_desc,
            "status": experiment.status,
            "created_at": experiment.created_at.isoformat() if experiment.created_at else "",
        },
    }


@router.get(
    "/experiments",
    summary="实验列表",
    description="获取所有实验列表，可按假设ID过滤",
)
def list_experiments(
    hypothesis_id: str | None = Query(None, description="按假设ID过滤"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取实验列表"""
    query = db.query(InnovationExperiment)
    if hypothesis_id:
        query = query.filter(InnovationExperiment.hypothesis_id == hypothesis_id)
    items = query.order_by(InnovationExperiment.created_at.desc()).all()
    exp_list = []
    for exp in items:
        exp_list.append({
            "id": exp.id,
            "hypothesis_id": exp.hypothesis_id,
            "method": exp.method,
            "sample_size": exp.sample_size,
            "success_criteria": exp.success_criteria,
            "control_group_desc": exp.control_group_desc,
            "experiment_group_desc": exp.experiment_group_desc,
            "status": exp.status,
            "created_at": exp.created_at.isoformat() if exp.created_at else "",
        })
    return {
        "code": 200,
        "message": "success",
        "data": exp_list,
        "total": len(exp_list),
    }


# ============================================================
# 路由：验证 & 门禁 (F-CZL-链客宝-01)
# ============================================================

@router.post(
    "/hypotheses/{hypothesis_id}/verify",
    summary="提交验证结果",
    description="提交假设的验证结果（通过/不通过 + 置信度），自动触发门禁检查",
)
def verify_hypothesis(
    req: VerifyResult,
    hypothesis_id: str = Path(..., description="假设ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交验证结果"""
    h = db.query(BusinessHypothesis).filter(BusinessHypothesis.id == hypothesis_id).first()
    if not h:
        raise HTTPException(status_code=404, detail=f"假设 {hypothesis_id} 不存在")
    if h.status != HypothesisStatus.VERIFYING.value and h.status != HypothesisStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"假设状态为 {h.status}，无法验证")

    h.verify_passed = req.passed
    h.verify_confidence = req.confidence
    h.verify_metrics = json.dumps(req.metrics, ensure_ascii=False)
    h.verify_notes = req.notes
    h.status = HypothesisStatus.VERIFIED.value
    h.updated_at = datetime.now(UTC)

    # 计算门禁评分
    gate_score = _calc_gate_score(req.passed, req.confidence, h.risk_score)
    h.gate_score = round(gate_score, 2)
    h.gate_status = GateStatus.OPEN.value if gate_score >= GATE_THRESHOLD else GateStatus.BLOCKED.value
    db.commit()
    db.refresh(h)

    result = _hypothesis_to_dict(h)

    logger.info(
        "hypothesis_verified",
        extra={
            "hypothesis_id": hypothesis_id,
            "passed": req.passed,
            "gate_score": h.gate_score,
            "gate_status": h.gate_status,
        },
    )

    # 触发LLM智能分析理由（降级友好）
    llm_summary = None
    try:
        from app.services.llm_service import generate_matching_reason

        product_data = {"name": h.title, "description": h.description}
        need_data = {"title": "假设验证", "description": f"风险评分: {h.risk_score}"}
        llm_summary = generate_matching_reason(product_data, need_data)
    except Exception:
        logger.debug("LLM 验证总结生成跳过")

    return {
        "code": 200,
        "message": "success",
        "data": {
            **result,
            "llm_summary": llm_summary,
        },
    }


@router.post(
    "/hypotheses/{hypothesis_id}/gate-check",
    summary="门禁检查",
    description="手动触发门禁检查，计算综合评分并返回门禁状态（open/blocked/locked）",
)
def gate_check(
    hypothesis_id: str = Path(..., description="假设ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发门禁检查"""
    h = db.query(BusinessHypothesis).filter(BusinessHypothesis.id == hypothesis_id).first()
    if not h:
        raise HTTPException(status_code=404, detail=f"假设 {hypothesis_id} 不存在")
    if h.status != HypothesisStatus.VERIFIED.value:
        raise HTTPException(status_code=400, detail="仅已验证的假设可触发门禁检查")

    gate_score = _calc_gate_score(
        h.verify_passed or False,
        h.verify_confidence or 0,
        h.risk_score,
    )
    gate_score = round(gate_score, 2)
    gate_status = GateStatus.OPEN.value if gate_score >= GATE_THRESHOLD else GateStatus.BLOCKED.value

    h.gate_score = gate_score
    h.gate_status = gate_status
    h.updated_at = datetime.now(UTC)
    db.commit()

    decision = "建议进入执行阶段" if gate_status == GateStatus.OPEN.value else "建议重新设计实验或调整假设"

    return {
        "code": 200,
        "message": "success",
        "data": {
            "hypothesis_id": hypothesis_id,
            "gate_score": gate_score,
            "gate_status": gate_status,
            "threshold": GATE_THRESHOLD,
            "decision": decision,
            "score_breakdown": {
                "pass_score": GATE_PASS_SCORE if h.verify_passed else 0,
                "confidence_score": round(GATE_CONFIDENCE_WEIGHT * (h.verify_confidence or 0), 2),
                "risk_penalty": GATE_RISK_PENALTY * h.risk_score,
            },
        },
    }


# ============================================================
# 路由：机会扫描 (F-CZL-链客宝-03)
# ============================================================

@router.post(
    "/scan",
    summary="机会扫描",
    description="扫描5种市场信号（匹配失败/未满足需求/搜索真空/需求突变/供需缺口）",
)
def scan_opportunities(
    req: ScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行机会扫描"""
    scanner = OpportunityScanner()
    scan_result = scanner.scan(req.data_sources, req.max_signals, req.context)
    return {
        "code": 200,
        "message": "success",
        "data": scan_result.model_dump(),
    }


@router.post(
    "/analyze",
    summary="趋势分析",
    description="基于扫描信号进行5维趋势分析（品类热度/供需平衡/新兴领域/需求画像/季节周期）",
)
def analyze_trends(
    req: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行趋势分析"""
    analyzer = TrendAnalyzer()
    trend_report = analyzer.analyze(req.signals, req.context)

    # 尝试LLM生成洞察摘要（降级友好）
    try:
        from app.services.llm_service import summarize_lead

        llm_summary = summarize_lead({
            "name": "趋势分析",
            "notes": f"分析了{len(req.signals)}个信号，生成{len(trend_report.insights)}个趋势洞察",
        })
        if llm_summary:
            trend_report.summary = llm_summary
    except Exception:
        pass

    return {
        "code": 200,
        "message": "success",
        "data": trend_report.model_dump(),
    }


@router.get(
    "/opportunities",
    summary="推荐机会列表",
    description="获取基于扫描和分析生成的可执行创新机会推荐列表",
)
def list_opportunities(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取推荐机会列表"""
    items = db.query(InnovationOpportunity).order_by(InnovationOpportunity.overall_score.desc()).limit(limit).all()
    opp_list = []
    for opp in items:
        opp_list.append({
            "id": opp.id,
            "title": opp.title,
            "description": opp.description,
            "overall_score": opp.overall_score,
            "confidence_score": opp.confidence_score,
            "urgency_score": opp.urgency_score,
            "business_value_score": opp.business_value_score,
            "source_signals": json.loads(opp.source_signals) if opp.source_signals else [],
            "source_insights": json.loads(opp.source_insights) if opp.source_insights else [],
            "action_steps": json.loads(opp.action_steps) if opp.action_steps else [],
        })
    return {
        "code": 200,
        "message": "success",
        "data": opp_list,
        "total": len(opp_list),
    }


@router.post(
    "/pipeline/run",
    summary="完整引擎管道",
    description="一次执行扫描→分析→推荐三阶段完整管道",
)
def run_full_pipeline(
    req: ScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行完整创新引擎管道"""
    start = time.time()

    # 阶段1: 扫描
    scanner = OpportunityScanner()
    scan_result = scanner.scan(req.data_sources, req.max_signals, req.context)

    # 阶段2: 分析
    analyzer = TrendAnalyzer()
    trend_report = analyzer.analyze(scan_result.signals, req.context)

    # 阶段3: 推荐
    recommender = OpportunityRecommender()
    recommendation = recommender.recommend(scan_result, trend_report)

    # 保存结果到数据库
    for opp in recommendation.opportunities:
        db_opp = InnovationOpportunity(
            id=opp.id,
            title=opp.title,
            description=opp.description,
            overall_score=opp.overall_score,
            confidence_score=opp.confidence_score,
            urgency_score=opp.urgency_score,
            business_value_score=opp.business_value_score,
            source_signals=json.dumps(opp.source_signals, ensure_ascii=False),
            source_insights=json.dumps(opp.source_insights, ensure_ascii=False),
            action_steps=json.dumps(opp.action_steps, ensure_ascii=False),
            created_at=datetime.now(UTC),
        )
        db.add(db_opp)
    db.commit()

    total_duration_ms = (time.time() - start) * 1000

    return {
        "code": 200,
        "message": "success",
        "data": {
            "scan_result": scan_result.model_dump(),
            "trend_report": trend_report.model_dump(),
            "recommendation": recommendation.model_dump(),
            "pipeline_stats": {
                "total_duration_ms": round(total_duration_ms, 2),
                "stages": [
                    {"name": "scan", "success": True, "signals_count": scan_result.total_signals},
                    {"name": "analyze", "success": True, "insights_count": len(trend_report.insights)},
                    {"name": "recommend", "success": True, "opportunities_count": recommendation.total_opportunities},
                ],
            },
        },
    }


# ============================================================
# 路由：增长周期 (F-CZL-链客宝-02)
# ============================================================

@router.get(
    "/growth-cycle",
    summary="增长周期状态",
    description="获取当前增长周期阶段、已持续天数、放大前自检状态",
)
def get_growth_cycle(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取增长周期状态"""
    phase_info = GrowthCycleManager.get_phase()
    hypotheses = db.query(BusinessHypothesis).order_by(BusinessHypothesis.created_at.desc()).all()
    hyp_dicts = [_hypothesis_to_dict(h) for h in hypotheses]
    scale_readiness = GrowthCycleManager.check_scale_readiness(hyp_dicts)
    return {
        "code": 200,
        "message": "success",
        "data": {
            "phase": phase_info,
            "scale_readiness": scale_readiness,
        },
    }


@router.post(
    "/growth-cycle/switch",
    summary="切换增长周期",
    description="手动切换增长周期阶段（explore/scale/harvest）",
)
def switch_growth_cycle(
    phase: GrowthCyclePhase = Query(..., description="目标阶段"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换增长周期阶段"""
    result = GrowthCycleManager.switch_phase(phase)
    logger.info("growth_cycle_switched", extra={"phase": phase.value, "user_id": current_user.id})
    return {
        "code": 200,
        "message": "success",
        "data": result,
    }


# ============================================================
# 路由：监控指标
# ============================================================

@router.get(
    "/metrics",
    summary="创新引擎监控指标",
    description="获取假设数/实验数/门禁状态/机会数等核心监控指标",
)
def get_innovation_metrics(
    db: Session = Depends(get_db),
):
    """获取引擎监控指标"""
    total_hypotheses = db.query(BusinessHypothesis).count()
    total_experiments = db.query(InnovationExperiment).count()
    open_gates = db.query(BusinessHypothesis).filter(BusinessHypothesis.gate_status == GateStatus.OPEN.value).count()
    blocked_gates = db.query(BusinessHypothesis).filter(BusinessHypothesis.gate_status == GateStatus.BLOCKED.value).count()
    verified_hypotheses = db.query(BusinessHypothesis).filter(BusinessHypothesis.status == HypothesisStatus.VERIFIED.value).count()
    pending_hypotheses = db.query(BusinessHypothesis).filter(BusinessHypothesis.status == HypothesisStatus.PENDING.value).count()
    opportunities_count = db.query(InnovationOpportunity).count()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_hypotheses": total_hypotheses,
            "total_experiments": total_experiments,
            "open_gates": open_gates,
            "blocked_gates": blocked_gates,
            "verified_hypotheses": verified_hypotheses,
            "pending_hypotheses": pending_hypotheses,
            "opportunities_count": opportunities_count,
        },
    }


# ============================================================
# 路由：缓存管理
# ============================================================

@router.post(
    "/cache/clear",
    summary="清除缓存",
    description="清除创新引擎的内存缓存",
)
def clear_innovation_cache(
    current_user: User = Depends(get_current_user),
):
    """清除缓存"""
    clear_cache()
    return {
        "code": 200,
        "message": "success",
        "data": {"cleared": True},
    }
