"""
链客宝信任评分引擎 — 四级分级系统
====================================
适配 chainke-full 现有 TrustScore 模型的分级体系:
    0-300   🟤 bronze   （待完善）
    301-500 ⚪ silver   （基础级）
    501-700 🟡 gold     （良好级）
    701-1000 🟣 platinum （优秀级）

迁移自旧版 trust_engine/tier.py 的五级系统 (pending/basic/good/excellent/top)。

联动: PRD §4.5 信任等级与会员体系联动表
"""

import enum
import logging
from dataclasses import dataclass
from typing import Union

logger = logging.getLogger(__name__)


# ============================================================
# 等级枚举 (适配 chainke-full 现有等级)
# ============================================================


class TrustLevel(str, enum.Enum):
    """信任等级枚举 (四级，对应 chainke-full TrustScore 模型等级)

    映射旧版五级 -> 新版四级:
        pending(0-39)  -> bronze(0-300)
        basic(40-59)   -> silver(301-500)
        good(60-79)    -> gold(501-700)
        excellent(80-100)/top(90-100) -> platinum(701-1000)
    """

    BRONZE = "bronze"       # 0-300   待完善
    SILVER = "silver"       # 301-500 基础级
    GOLD = "gold"           # 501-700 良好级
    PLATINUM = "platinum"   # 701-1000 优秀级


# ============================================================
# 等级配置
# ============================================================


@dataclass(frozen=True)
class TierConfig:
    """单个等级配置"""

    level: TrustLevel
    label_cn: str
    label_en: str
    icon: str
    min_score: float
    max_score: float
    match_weight: float           # 匹配加权系数
    membership_requirement: str   # 对应会员权益
    color: str                    # 显示颜色

    def contains(self, score: float) -> bool:
        """判断分数是否在该等级范围内"""
        return self.min_score <= score <= self.max_score


# ── 四级分级定义 ──────────────────────────────────────────

TIER_DEFINITIONS: list[TierConfig] = [
    TierConfig(
        level=TrustLevel.BRONZE,
        label_cn="待完善",
        label_en="Bronze",
        icon="🟤",
        min_score=0.0,
        max_score=300.0,
        match_weight=0.5,
        membership_requirement="免费会员，建议上传资质提升评分",
        color="#9CA3AF",
    ),
    TierConfig(
        level=TrustLevel.SILVER,
        label_cn="基础级",
        label_en="Silver",
        icon="⚪",
        min_score=301.0,
        max_score=500.0,
        match_weight=0.8,
        membership_requirement="免费+金卡，可参与匹配但非优先",
        color="#F59E0B",
    ),
    TierConfig(
        level=TrustLevel.GOLD,
        label_cn="良好级",
        label_en="Gold",
        icon="🟡",
        min_score=501.0,
        max_score=700.0,
        match_weight=1.0,
        membership_requirement='金卡默认等级，获得"可信"标签',
        color="#10B981",
    ),
    TierConfig(
        level=TrustLevel.PLATINUM,
        label_cn="优秀级",
        label_en="Platinum",
        icon="🟣",
        min_score=701.0,
        max_score=1000.0,
        match_weight=1.15,
        membership_requirement='钻石会员门槛之一，获得"优秀"标签',
        color="#3B82F6",
    ),
]

# 等级查找表（从高到低排序）
_LEVEL_BY_SCORE: list[TierConfig] = sorted(
    TIER_DEFINITIONS, key=lambda t: t.min_score, reverse=True
)


class TrustTier:
    """信任等级分类器

    根据综合评分判定所属等级，并提供等级相关属性和验证。
    适配 chainke-full 0-1000 评分范围。

    Usage:
        tier = TrustTier(865.0)  # 0-1000 范围
        print(tier.level)        # TrustLevel.PLATINUM
        print(tier.label_cn)     # "优秀级"
        print(tier.icon)         # "🟣"
    """

    def __init__(self, score: float) -> None:
        if not isinstance(score, (int, float)):
            raise TypeError(f"score must be numeric, got {type(score).__name__}")
        self.score = max(0.0, min(1000.0, float(score)))
        self._config = self._resolve(self.score)

    # ── 解析 ──────────────────────────────────────────────

    @staticmethod
    def _resolve(score: float) -> TierConfig:
        """根据分数找到对应的等级配置"""
        for tier_cfg in _LEVEL_BY_SCORE:
            if score >= tier_cfg.min_score:
                return tier_cfg
        return TIER_DEFINITIONS[0]  # fallback: BRONZE

    # ── 属性委派 ──────────────────────────────────────────

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
        """显示字符串，如 '🟣 优秀级 (865)'"""
        return f"{self.icon} {self.label_cn} ({self.score:.0f})"

    # ── 等级判断 ─────────────────────────────────────────

    def is_bronze(self) -> bool:
        return self.level == TrustLevel.BRONZE

    def is_silver(self) -> bool:
        return self.level == TrustLevel.SILVER

    def is_gold(self) -> bool:
        return self.level == TrustLevel.GOLD

    def is_platinum(self) -> bool:
        return self.level == TrustLevel.PLATINUM

    def is_above(self, other: Union["TrustLevel", str, "TrustTier"]) -> bool:
        """判断当前等级是否高于指定等级"""
        other_level = self._resolve_level(other)
        return self._config.min_score > self._get_threshold(other_level)

    def is_below(self, other: Union["TrustLevel", str, "TrustTier"]) -> bool:
        """判断当前等级是否低于指定等级"""
        other_level = self._resolve_level(other)
        return self._config.max_score < self._get_threshold(other_level)

    @staticmethod
    def _resolve_level(other: Union["TrustLevel", str, "TrustTier"]) -> TrustLevel:
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

    # ── 序列化 ───────────────────────────────────────────

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


# ============================================================
# 快捷函数（兼容 chainke-full 现有 get_trust_tier API）
# ============================================================


def get_trust_tier(score: float) -> str:
    """从分数直接获取等级字符串（快捷函数，兼容现有接口）

    Args:
        score: 信任评分 (0-1000)

    Returns:
        str: "bronze" / "silver" / "gold" / "platinum"
    """
    return TrustTier(score).level.value


def validate_score(score: float) -> None:
    """验证信任评分是否在合法范围内 [0, 1000]"""
    if not isinstance(score, (int, float)):
        raise ValueError(f"Score must be numeric, got {type(score).__name__}")
    if score < 0 or score > 1000:
        raise ValueError(f"Score must be in [0, 1000], got {score}")


def is_diamond_eligible(score: float, cert_count: int) -> bool:
    """钻石会员准入条件检查

    信任评分 ≥ 700 (链客宝 platinum 门槛) 或 企业认证+3项以上合规证书
    """
    return score >= 700.0 or cert_count >= 3


def is_board_eligible(
    score: float, has_audit_report: bool, is_ceo: bool = True
) -> bool:
    """私董会准入条件检查

    信任评分 ≥ 900 + 第三方审计报告已上传且有效
    """
    return score >= 900.0 and has_audit_report and is_ceo
