# =============================================================================
# 链客宝信任评分引擎 — 五级分级系统
# =============================================================================
# 依据 PRD §4.2 综合评分分级:
#    0-39   ❌ 待完善  (pending)
#    40-59  ⚠️ 基础级  (basic)
#    60-79  ✅ 良好级  (good)
#    80-89  ⭐ 优秀级  (excellent)
#    90-100 👑 顶级    (top)
#
# 联动: PRD §4.5 信任等级与会员体系联动表
# =============================================================================

import enum
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── 等级枚举 ──────────────────────────────────────────────────────────────

class TrustLevel(str, enum.Enum):
    """信任等级枚举 (五级)

    对应 PRD §4.2 分级 + §4.5 联动
    """
    PENDING = "pending"         # ❌ 0-39  待完善
    BASIC = "basic"             # ⚠️ 40-59 基础级
    GOOD = "good"               # ✅ 60-79 良好级
    EXCELLENT = "excellent"     # ⭐ 80-89 优秀级
    TOP = "top"                 # 👑 90-100 顶级


# ── 等级配置 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TierConfig:
    """单个等级配置"""
    level: TrustLevel
    label_cn: str
    label_en: str
    icon: str
    min_score: float
    max_score: float
    match_weight: float          # 匹配加权系数 (PRD §4.5)
    membership_requirement: str  # 对应会员权益
    color: str                   # 显示颜色

    def contains(self, score: float) -> bool:
        """判断分数是否在该等级范围内"""
        return self.min_score <= score <= self.max_score


# ── 五级分级定义 (PRD §4.2 + §4.5) ──────────────────────────────────────

TIER_DEFINITIONS: list[TierConfig] = [
    TierConfig(
        level=TrustLevel.PENDING,
        label_cn="待完善",
        label_en="Pending",
        icon="❌",
        min_score=0.0,
        max_score=39.99,
        match_weight=0.5,        # 降权
        membership_requirement="免费会员，建议上传资质提升评分",
        color="#9CA3AF",         # 灰色
    ),
    TierConfig(
        level=TrustLevel.BASIC,
        label_cn="基础级",
        label_en="Basic",
        icon="⚠️",
        min_score=40.0,
        max_score=59.99,
        match_weight=0.8,
        membership_requirement="免费+金卡，可参与匹配但非优先",
        color="#F59E0B",         # 琥珀色
    ),
    TierConfig(
        level=TrustLevel.GOOD,
        label_cn="良好级",
        label_en="Good",
        icon="✅",
        min_score=60.0,
        max_score=79.99,
        match_weight=1.0,        # 基准
        membership_requirement='金卡默认等级，获得"可信"标签',
        color="#10B981",         # 绿色
    ),
    TierConfig(
        level=TrustLevel.EXCELLENT,
        label_cn="优秀级",
        label_en="Excellent",
        icon="⭐",
        min_score=80.0,
        max_score=89.99,
        match_weight=1.15,
        membership_requirement='钻石会员门槛之一，获得"优秀"标签',
        color="#3B82F6",         # 蓝色
    ),
    TierConfig(
        level=TrustLevel.TOP,
        label_cn="顶级",
        label_en="Top",
        icon="👑",
        min_score=90.0,
        max_score=100.0,
        match_weight=1.30,
        membership_requirement="私董会准入条件之一，首页推荐加权",
        color="#8B5CF6",         # 紫色
    ),
]


# ── 等级查找表 ──────────────────────────────────────────────────────────

_LEVEL_BY_SCORE: list[TierConfig] = sorted(
    TIER_DEFINITIONS, key=lambda t: t.min_score, reverse=True
)


class TrustTier:
    """信任等级分类器

    根据综合评分判定所属等级，并提供等级相关属性和验证。

    Usage:
        tier = TrustTier(86.5)
        print(tier.level)        # TrustLevel.EXCELLENT
        print(tier.label_cn)     # "优秀级"
        print(tier.icon)         # "⭐"
        print(tier.match_weight) # 1.15
    """

    def __init__(self, score: float) -> None:
        if not isinstance(score, (int, float)):
            raise TypeError(f"score must be numeric, got {type(score).__name__}")
        self.score = max(0.0, min(100.0, float(score)))
        self._config = self._resolve(self.score)

    # ── 解析 ────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve(score: float) -> TierConfig:
        """根据分数找到对应的等级配置"""
        for tier_cfg in _LEVEL_BY_SCORE:
            if score >= tier_cfg.min_score:
                return tier_cfg
        return TIER_DEFINITIONS[0]  # fallback: PENDING

    # ── 属性委派 ─────────────────────────────────────────────────────────

    @property
    def level(self) -> TrustLevel:
        return self._config.level

    @property
    def label_cn(self) -> str:
        return self._config.label_cn

    @property
    def label_en(self) -> str:
        return self._config.label_en

    @property
    def icon(self) -> str:
        return self._config.icon

    @property
    def min_score(self) -> float:
        return self._config.min_score

    @property
    def max_score(self) -> float:
        return self._config.max_score

    @property
    def match_weight(self) -> float:
        return self._config.match_weight

    @property
    def membership_requirement(self) -> str:
        return self._config.membership_requirement

    @property
    def color(self) -> str:
        return self._config.color

    @property
    def display(self) -> str:
        """显示字符串，如 '👑 顶级 (95)'"""
        return f"{self.icon} {self.label_cn} ({self.score:.0f})"

    # ── 等级判断 ─────────────────────────────────────────────────────────

    def is_pending(self) -> bool:
        return self.level == TrustLevel.PENDING

    def is_basic(self) -> bool:
        return self.level == TrustLevel.BASIC

    def is_good(self) -> bool:
        return self.level == TrustLevel.GOOD

    def is_excellent(self) -> bool:
        return self.level == TrustLevel.EXCELLENT

    def is_top(self) -> bool:
        return self.level == TrustLevel.TOP

    def is_above(self, other: "TrustLevel | str | TrustTier") -> bool:
        """判断当前等级是否高于指定等级"""
        other_level = self._resolve_level(other)
        return self._config.min_score > self._get_threshold(other_level)

    def is_below(self, other: "TrustLevel | str | TrustTier") -> bool:
        """判断当前等级是否低于指定等级"""
        other_level = self._resolve_level(other)
        return self._config.max_score < self._get_threshold(other_level)

    @staticmethod
    def _resolve_level(other: "TrustLevel | str | TrustTier") -> TrustLevel:
        if isinstance(other, TrustTier):
            return other.level
        if isinstance(other, str):
            return TrustLevel(other)
        if isinstance(other, TrustLevel):
            return other
        raise TypeError(f"Unsupported type: {type(other).__name__}")

    @staticmethod
    def _get_threshold(level: TrustLevel) -> float:
        for cfg in TIER_DEFINITIONS:
            if cfg.level == level:
                return cfg.min_score
        return 0.0

    # ── 序列化 ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, object]:
        """序列化为字典（API输出用）"""
        return {
            "score": self.score,
            "level": self.level.value,
            "label_cn": self.label_cn,
            "label_en": self.label_en,
            "icon": self.icon,
            "color": self.color,
            "display": self.display,
            "match_weight": self.match_weight,
            "membership_requirement": self.membership_requirement,
        }

    def __repr__(self) -> str:
        return f"<TrustTier {self.display}>"


# ── 验证函数 ──────────────────────────────────────────────────────────────

def validate_score(score: float) -> None:
    """验证信任评分是否在合法范围内 [0, 100]"""
    if not isinstance(score, (int, float)):
        raise ValueError(f"Score must be numeric, got {type(score).__name__}")
    if score < 0 or score > 100:
        raise ValueError(
            f"Score must be in [0, 100], got {score}"
        )


def level_from_score(score: float) -> TrustLevel:
    """从分数直接获取等级枚举（快捷函数）"""
    return TrustTier(score).level


def is_diamond_eligible(score: float, cert_count: int) -> bool:
    """钻石会员准入条件检查 (PRD §4.5)

    原条件: 年费¥4,999
    新增条件: 信任评分 ≥ 80 或 企业认证+3项以上合规证书
    """
    return score >= 80.0 or cert_count >= 3


def is_board_eligible(
    score: float, has_audit_report: bool, is_ceo: bool = True
) -> bool:
    """私董会准入条件检查 (PRD §4.5)

    原条件: 创始人/CEO + 年营收≥500万 + 成交≥2次
    新增条件: 信任评分 ≥ 90 + 第三方审计报告已上传且有效
    """
    return score >= 90.0 and has_audit_report and is_ceo
