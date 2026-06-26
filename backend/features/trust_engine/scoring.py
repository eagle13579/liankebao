"""
链客宝信任评分引擎 — 三维评分模块
====================================
迁移自旧版 trust_engine/scoring.py，适配 chainke-full 模型结构。

三维评分（映射到 chainke-full TrustScore 模型的三个积分字段）:
  维度A: 认证可信度 (Verification) — 映射到 verification_points
  维度B: 行为可信度 (Behavior)    — 映射到 behavior_points
  维度C: 担保可信度 (Guarantee)   — 映射到 guarantee_points

评分范围:
  内部计算使用 0-100 原始分，外部接口统一映射到 0-1000 范围以适配
  chainke-full 现有 TrustScore 模型的 tier 分级阈值。

设计哲学: H08 阳光下行走 — 评分公式完全公开
"""

import math
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 权重常量（H08 公开透明）
# ============================================================


@dataclass(frozen=True)
class ScoreWeights:
    """三维评分权重 — 完全公开（H08阳光下行走）

    依据 PRD §4.1 权重定义:
        认证可信度: 40%  (映射旧版资质可信度)
        行为可信度: 35%  (映射旧版交易可信度)
        担保可信度: 25%  (映射旧版合规健康度)
    """

    VERIFICATION: float = 0.40  # 认证可信度（原资质可信度）
    BEHAVIOR: float = 0.35      # 行为可信度（原交易可信度）
    GUARANTEE: float = 0.25     # 担保可信度（原合规健康度）

    # 时间衰减
    DECAY_LAMBDA: float = 0.1

    # 顶级信任额外加权
    TRUST_WEIGHT: float = 0.15
    TOP_TRUST_BOOST: float = 1.10
    TOP_TRUST_THRESHOLD: int = 900  # chainke-full 0-1000 范围对应

    def __post_init__(self) -> None:
        total = self.VERIFICATION + self.BEHAVIOR + self.GUARANTEE
        if abs(total - 1.0) > 1e-9:
            logger.warning("ScoreWeights sum=%.4f, expected 1.0", total)


# ============================================================
# 评分明细数据结构
# ============================================================


@dataclass
class QualificationSubscores:
    """维度A: 认证可信度子指标（映射旧版资质可信度）"""

    cert_level: float = 0.0        # 认证等级 (0-30)
    cert_variety: float = 0.0      # 资质种类数 (0-25)
    cert_timeliness: float = 0.0   # 资质时效性 (0-20)
    id_depth: float = 0.0          # 实名深度 (0-15)
    platform_tenure: float = 0.0   # 平台验证时长 (0-10)

    @property
    def raw_total(self) -> float:
        """原始总分 (0-100)"""
        return (
            self.cert_level
            + self.cert_variety
            + self.cert_timeliness
            + self.id_depth
            + self.platform_tenure
        )

    @property
    def weighted(self) -> float:
        """加权后得分 (×40%)"""
        return self.raw_total * ScoreWeights.VERIFICATION


@dataclass
class TransactionSubscores:
    """维度B: 行为可信度子指标（映射旧版交易可信度，含衰减）"""

    trade_count: float = 0.0           # 成交笔数 (0-30)
    trade_amount: float = 0.0          # 成交金额 (0-25)
    positive_rate: float = 0.0         # 好评率 (0-20)
    dispute_rate: float = 0.0          # 纠纷率 (0-15, 越高分越低)
    repurchase_rate: float = 0.0       # 复购率 (0-10)
    months_since_last_trade: Optional[float] = None  # 距最近成交月数

    @property
    def raw_total(self) -> float:
        """原始总分 (0-100)"""
        return (
            self.trade_count
            + self.trade_amount
            + self.positive_rate
            + self.dispute_rate
            + self.repurchase_rate
        )

    def apply_decay(self, decay_lambda: float = ScoreWeights.DECAY_LAMBDA) -> float:
        """应用时间衰减"""
        if self.months_since_last_trade is None or self.months_since_last_trade <= 0:
            return self.raw_total
        decay_factor = math.exp(-decay_lambda * self.months_since_last_trade)
        return self.raw_total * decay_factor

    @property
    def weighted(self) -> float:
        """加权后得分 (×35%)"""
        return self.apply_decay() * ScoreWeights.BEHAVIOR


@dataclass
class ComplianceSubscores:
    """维度C: 担保可信度子指标（映射旧版合规健康度）"""

    qual_completeness: float = 0.0     # 资质完整度 (0-30)
    expiry_risk: float = 0.0           # 证书过期风险 (0-25)
    compliance_certs: float = 0.0      # 合规证书数 (0-20)
    audit_report: float = 0.0          # 审计报告 (0-15)
    update_frequency: float = 0.0      # 合规更新频率 (0-10)

    @property
    def raw_total(self) -> float:
        """原始总分 (0-100)"""
        return (
            self.qual_completeness
            + self.expiry_risk
            + self.compliance_certs
            + self.audit_report
            + self.update_frequency
        )

    @property
    def weighted(self) -> float:
        """加权后得分 (×25%)"""
        return self.raw_total * ScoreWeights.GUARANTEE


@dataclass
class ScoreBreakdown:
    """完整评分明细 — 供 API 透出"""

    qualification: QualificationSubscores = field(
        default_factory=QualificationSubscores
    )
    transaction: TransactionSubscores = field(default_factory=TransactionSubscores)
    compliance: ComplianceSubscores = field(default_factory=ComplianceSubscores)
    decay_factor: Optional[float] = None
    calculation_ts: str = ""

    @property
    def total(self) -> float:
        """综合评分 [0, 100]"""
        raw = (
            self.qualification.weighted
            + self.transaction.weighted
            + self.compliance.weighted
        )
        return round(max(0.0, min(100.0, raw)), 2)

    @property
    def total_scaled(self) -> float:
        """映射到 chainke-full 的 0-1000 范围"""
        return round(self.total * 10.0, 2)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（API输出用）"""
        return {
            "total": self.total,
            "total_scaled": self.total_scaled,
            "qualification": {
                "cert_level": self.qualification.cert_level,
                "cert_variety": self.qualification.cert_variety,
                "cert_timeliness": self.qualification.cert_timeliness,
                "id_depth": self.qualification.id_depth,
                "platform_tenure": self.qualification.platform_tenure,
                "raw_total": round(self.qualification.raw_total, 2),
                "weighted": round(self.qualification.weighted, 2),
            },
            "transaction": {
                "trade_count": self.transaction.trade_count,
                "trade_amount": self.transaction.trade_amount,
                "positive_rate": self.transaction.positive_rate,
                "dispute_rate": self.transaction.dispute_rate,
                "repurchase_rate": self.transaction.repurchase_rate,
                "months_since_last_trade": self.transaction.months_since_last_trade,
                "raw_total": round(self.transaction.raw_total, 2),
                "decayed_total": round(self.transaction.apply_decay(), 2),
                "decay_factor": round(self.decay_factor, 4)
                if self.decay_factor
                else None,
                "weighted": round(self.transaction.weighted, 2),
            },
            "compliance": {
                "qual_completeness": self.compliance.qual_completeness,
                "expiry_risk": self.compliance.expiry_risk,
                "compliance_certs": self.compliance.compliance_certs,
                "audit_report": self.compliance.audit_report,
                "update_frequency": self.compliance.update_frequency,
                "raw_total": round(self.compliance.raw_total, 2),
                "weighted": round(self.compliance.weighted, 2),
            },
            "calculation_ts": self.calculation_ts,
        }


# ============================================================
# 评分查询模型（用于从数据库读取的原始数据）
# ============================================================


@dataclass
class QualificationData:
    """认证/资质原始数据"""

    qualification_type: str
    is_active: bool
    expiry_date: Optional[date] = None
    created_at: Optional[datetime] = None


@dataclass
class TransactionData:
    """行为/交易原始数据"""

    total_trades: int = 0
    total_amount: float = 0.0
    positive_rate: float = 1.0  # 0.0-1.0
    dispute_count: int = 0
    total_rated: int = 0
    repurchase_count: int = 0
    last_trade_date: Optional[date] = None


@dataclass
class ComplianceData:
    """担保/合规原始数据"""

    active_qual_count: int = 0
    suggested_qual_count: int = 7
    expired_count: int = 0
    about_to_expire_count: int = 0
    compliance_cert_types: set[str] = field(default_factory=set)
    has_valid_audit: bool = False
    has_expired_audit: bool = False
    last_update_months: Optional[float] = None


# ============================================================
# 核心评分器
# ============================================================


class TrustScorer:
    """信任评分计算器

    依据 PRD §4.2 评分算法细则，计算三维评分加综合评分。
    适配 chainke-full 模型结构，提供 0-100 和 0-1000 双范围输出。

    Usage:
        scorer = TrustScorer()
        breakdown = scorer.calculate_breakdown(qual, txn, comp)
        print(breakdown.total)        # 0-100 范围
        print(breakdown.total_scaled) # 0-1000 范围
    """

    def __init__(self, weights: Optional[ScoreWeights] = None) -> None:
        self.weights = weights or ScoreWeights()

    # ── 维度A: 认证可信度评分 ──────────────────────────────────

    def score_cert_level(self, level_code: str) -> float:
        """认证等级评分 (0-30)"""
        mapping = {
            "none": 0.0,
            "basic": 10.0,
            "enterprise": 20.0,
            "advanced": 25.0,
            "diamond": 30.0,
        }
        return mapping.get(level_code, 0.0)

    def score_cert_variety(self, active_qual_count: int) -> float:
        """资质种类数评分 (0-25)，每项+5分，上限25分"""
        return min(active_qual_count * 5.0, 25.0)

    def score_cert_timeliness(self, expired_count: int) -> float:
        """资质时效性评分 (0-20)"""
        penalties = {0: 20.0, 1: 15.0, 2: 10.0}
        return penalties.get(expired_count, 0.0)

    def score_id_depth(self, id_level: str) -> float:
        """实名深度评分 (0-15)"""
        mapping = {
            "none": 0.0,
            "phone": 3.0,
            "id_card": 8.0,
            "legal_person_video": 15.0,
        }
        return mapping.get(id_level, 0.0)

    def score_platform_tenure(self, months_on_platform: float) -> float:
        """平台验证时长评分 (0-10)"""
        if months_on_platform >= 36:
            return 10.0
        if months_on_platform >= 24:
            return 8.0
        if months_on_platform >= 12:
            return 5.0
        return 3.0

    def score_qualification_dimension(
        self,
        cert_level: str,
        active_qual_count: int,
        expired_count: int,
        id_level: str,
        months_on_platform: float,
    ) -> QualificationSubscores:
        """计算认证可信度全部分值"""
        return QualificationSubscores(
            cert_level=self.score_cert_level(cert_level),
            cert_variety=self.score_cert_variety(active_qual_count),
            cert_timeliness=self.score_cert_timeliness(expired_count),
            id_depth=self.score_id_depth(id_level),
            platform_tenure=self.score_platform_tenure(months_on_platform),
        )

    # ── 维度B: 行为可信度评分 ──────────────────────────────────

    def score_trade_count(self, total_trades: int) -> float:
        """成交笔数评分 (0-30)"""
        if total_trades >= 21:
            return 30.0
        if total_trades >= 6:
            return 20.0
        if total_trades >= 1:
            return 10.0
        return 0.0

    def score_trade_amount(self, total_amount: float) -> float:
        """成交金额评分 (0-25)"""
        if total_amount >= 5_000_000:
            return 25.0
        if total_amount >= 1_000_000:
            return 20.0
        if total_amount >= 100_000:
            return 15.0
        if total_amount > 0:
            return 5.0
        return 0.0

    def score_positive_rate(self, positive_rate: float) -> float:
        """好评率评分 (0-20)"""
        if positive_rate >= 0.95:
            return 20.0
        if positive_rate >= 0.90:
            return 15.0
        if positive_rate >= 0.80:
            return 10.0
        return 0.0

    def score_dispute_rate(self, dispute_rate: float) -> float:
        """纠纷率评分 (0-15)，dispute_rate 为 0.0-1.0"""
        if dispute_rate <= 0.0:
            return 15.0
        if dispute_rate <= 0.01:
            return 10.0
        if dispute_rate <= 0.05:
            return 5.0
        return 0.0

    def score_repurchase_rate(self, repurchase_count: int) -> float:
        """复购率评分 (0-10)"""
        if repurchase_count >= 5:
            return 10.0
        if repurchase_count >= 3:
            return 7.0
        if repurchase_count >= 2:
            return 5.0
        if repurchase_count >= 1:
            return 3.0
        return 0.0

    def score_transaction_dimension(
        self,
        total_trades: int,
        total_amount: float,
        positive_rate: float,
        dispute_rate: float,
        repurchase_count: int,
        months_since_last_trade: Optional[float] = None,
    ) -> TransactionSubscores:
        """计算行为可信度全部分值"""
        return TransactionSubscores(
            trade_count=self.score_trade_count(total_trades),
            trade_amount=self.score_trade_amount(total_amount),
            positive_rate=self.score_positive_rate(positive_rate),
            dispute_rate=self.score_dispute_rate(dispute_rate),
            repurchase_rate=self.score_repurchase_rate(repurchase_count),
            months_since_last_trade=months_since_last_trade,
        )

    # ── 维度C: 担保可信度评分 ──────────────────────────────────

    def score_qual_completeness(
        self, active_count: int, suggested_count: int = 7
    ) -> float:
        """资质完整度评分 (0-30)"""
        if suggested_count <= 0:
            return 0.0
        ratio = min(active_count / suggested_count, 1.0)
        return ratio * 30.0

    def score_expiry_risk(
        self, expired_count: int, about_to_expire_count: int = 0
    ) -> float:
        """证书过期风险评分 (0-25)"""
        if expired_count >= 2:
            return 0.0
        if expired_count == 1:
            return 5.0
        if about_to_expire_count >= 1:
            return 15.0
        return 25.0

    def score_compliance_certs(self, cert_types: set[str]) -> float:
        """合规证书数评分 (0-20)"""
        count = len(cert_types)
        return min(count * 5.0, 20.0)

    def score_audit_report(self, has_valid: bool, has_expired: bool) -> float:
        """审计报告评分 (0-15)"""
        if has_valid:
            return 15.0
        if has_expired:
            return 5.0
        return 0.0

    def score_update_frequency(self, months_since_update: Optional[float]) -> float:
        """合规更新频率评分 (0-10)"""
        if months_since_update is None:
            return 0.0
        if months_since_update <= 3:
            return 10.0
        if months_since_update <= 6:
            return 7.0
        if months_since_update <= 12:
            return 4.0
        return 0.0

    def score_compliance_dimension(
        self,
        active_qual_count: int,
        suggested_qual_count: int,
        expired_count: int,
        about_to_expire_count: int,
        compliance_cert_types: set[str],
        has_valid_audit: bool,
        has_expired_audit: bool,
        months_since_update: Optional[float] = None,
    ) -> ComplianceSubscores:
        """计算担保可信度全部分值"""
        return ComplianceSubscores(
            qual_completeness=self.score_qual_completeness(
                active_qual_count, suggested_qual_count
            ),
            expiry_risk=self.score_expiry_risk(expired_count, about_to_expire_count),
            compliance_certs=self.score_compliance_certs(compliance_cert_types),
            audit_report=self.score_audit_report(has_valid_audit, has_expired_audit),
            update_frequency=self.score_update_frequency(months_since_update),
        )

    # ── 综合计算 ──────────────────────────────────────────────

    def calculate_breakdown(
        self,
        qual: QualificationSubscores,
        txn: TransactionSubscores,
        comp: ComplianceSubscores,
    ) -> ScoreBreakdown:
        """从三个维度的子分合成完整评分明细"""
        decay_factor = None
        if txn.months_since_last_trade is not None and txn.months_since_last_trade > 0:
            decay_factor = math.exp(
                -self.weights.DECAY_LAMBDA * txn.months_since_last_trade
            )

        return ScoreBreakdown(
            qualification=qual,
            transaction=txn,
            compliance=comp,
            decay_factor=decay_factor,
            calculation_ts=datetime.now(timezone.utc).isoformat(),
        )

    def calculate_from_raw_data(
        self,
        qual_data: QualificationData,
        txn_data: TransactionData,
        comp_data: ComplianceData,
        cert_level: str = "none",
        id_level: str = "none",
        months_on_platform: float = 0.0,
    ) -> ScoreBreakdown:
        """从原始数据直接计算完整评分（便捷方法）

        Args:
            qual_data: 认证/资质原始数据
            txn_data: 行为/交易原始数据
            comp_data: 担保/合规原始数据
            cert_level: 认证等级代码
            id_level: 实名深度代码
            months_on_platform: 入驻月数

        Returns:
            ScoreBreakdown 包含完整评分明细
        """
        qual_subs = self.score_qualification_dimension(
            cert_level=cert_level,
            active_qual_count=qual_data.active_qual_count,
            expired_count=qual_data.expired_count,
            id_level=id_level,
            months_on_platform=months_on_platform,
        )
        # 修正: 资质过期来自合规数据
        qual_subs.cert_timeliness = self.score_cert_timeliness(comp_data.expired_count)

        txn_subs = self.score_transaction_dimension(
            total_trades=txn_data.total_trades,
            total_amount=txn_data.total_amount,
            positive_rate=txn_data.positive_rate,
            dispute_rate=(txn_data.dispute_count / max(txn_data.total_rated, 1)),
            repurchase_count=txn_data.repurchase_count,
            months_since_last_trade=self._calc_months_since(txn_data.last_trade_date),
        )

        comp_subs = self.score_compliance_dimension(
            active_qual_count=comp_data.active_qual_count,
            suggested_qual_count=comp_data.suggested_qual_count,
            expired_count=comp_data.expired_count,
            about_to_expire_count=comp_data.about_to_expire_count,
            compliance_cert_types=comp_data.compliance_cert_types,
            has_valid_audit=comp_data.has_valid_audit,
            has_expired_audit=comp_data.has_expired_audit,
            months_since_update=comp_data.last_update_months,
        )

        return self.calculate_breakdown(qual_subs, txn_subs, comp_subs)

    @staticmethod
    def _calc_months_since(target_date: Optional[date]) -> Optional[float]:
        """计算从目标日期到现在的月数"""
        if target_date is None:
            return None
        delta = date.today() - target_date
        return max(0.0, delta.days / 30.44)

    # ── 与 chainke-full 模型对接的便捷方法 ────────────────────

    @staticmethod
    def scale_to_1000(score_100: float) -> float:
        """将 0-100 评分映射到 0-1000 范围"""
        return round(max(0.0, min(1000.0, score_100 * 10.0)), 2)

    @staticmethod
    def scale_to_100(score_1000: float) -> float:
        """将 0-1000 评分映射到 0-100 范围"""
        return round(max(0.0, min(100.0, score_1000 / 10.0)), 2)

    def breakdown_to_model_fields(
        self, breakdown: ScoreBreakdown
    ) -> dict[str, float]:
        """将 ScoreBreakdown 映射到 TrustScore 模型字段值"""
        return {
            "verification_points": round(breakdown.qualification.weighted * 10.0, 2),
            "behavior_points": round(breakdown.transaction.weighted * 10.0, 2),
            "guarantee_points": round(breakdown.compliance.weighted * 10.0, 2),
            "total_score": breakdown.total_scaled,
        }
