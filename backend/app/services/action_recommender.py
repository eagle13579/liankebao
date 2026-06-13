"""评分后自动下一步行动推荐引擎

核心功能：当供应商/企业通过匹配引擎评分后，自动根据评分输出推荐的下一步行动。

评分阈值规则（可配置）：
  高分段 (≥80)  → 推送签约（触发 e签宝）
  中分段 (50-79) → AI 自动邀约对接会
  低分段 (<50)   → 培育序列（自动发送资料/提醒）

设计原则：
  - 纯规则驱动，无外部 API 依赖
  - 策略可配置：通过 ActionRuleConfig 动态调整阈值和行动内容
  - 支持评分归一化：兼容 0.0~1.0 和 0~100 两种分数格式
  - 对标 Salesforce Einstein Next Best Action
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# 行动类型枚举
# ============================================================
class ActionType(str, Enum):
    """推荐的下一步行动类型"""

    SIGN_CONTRACT = "sign_contract"  # 推送签约（触发 e签宝）
    INVITE_EVENT = "invite_event"  # AI 自动邀约对接会
    NURTURE_SEQUENCE = "nurture_sequence"  # 培育序列（自动发送资料/提醒）
    MANUAL_REVIEW = "manual_review"  # 人工复核（边界情况）


# ============================================================
# 分数段级别枚举
# ============================================================
class ScoreLevel(str, Enum):
    """基于评分的分级标签"""

    HIGH = "high"  # 高分段
    MEDIUM = "medium"  # 中分段
    LOW = "low"  # 低分段


# ============================================================
# 可配置的规则定义
# ============================================================
@dataclass
class ActionRule:
    """单条行动推荐规则

    Attributes:
        min_score: 最低分数（含）
        max_score: 最高分数（含）
        action_type: 推荐行动类型
        priority: 优先级（数字越小越优先）
        display_name: 前端展示名称
        description: 行动描述
        action_data: 行动携带的额外数据（如签约模板ID、对接会ID等）
        label: 分数段标签
    """

    min_score: float
    max_score: float
    action_type: ActionType
    priority: int
    display_name: str
    description: str
    action_data: dict[str, Any] = field(default_factory=dict)
    label: ScoreLevel | None = None


# ============================================================
# 默认策略配置
# ============================================================
DEFAULT_RULES: list[ActionRule] = [
    # 高分段：≥80 → 推送签约
    ActionRule(
        min_score=80.0,
        max_score=100.0,
        action_type=ActionType.SIGN_CONTRACT,
        priority=1,
        display_name="推送电子签约",
        description="企业匹配度极高，建议立即推送电子签约流程，锁定合作",
        label=ScoreLevel.HIGH,
        action_data={
            "action_hint": "触发 e签宝签约流程",
            "auto_trigger": True,
            "requires_approval": False,
            "suggested_channel": "system",
        },
    ),
    # 中分段：50-79 → AI 自动邀约对接会
    ActionRule(
        min_score=50.0,
        max_score=79.99,
        action_type=ActionType.INVITE_EVENT,
        priority=2,
        display_name="AI自动邀约对接会",
        description="匹配度良好，建议通过 AI 自动邀请参加线上闭门对接会，促进深入了解",
        label=ScoreLevel.MEDIUM,
        action_data={
            "action_hint": "触发 AI 自动邀约流程",
            "auto_trigger": True,
            "requires_approval": False,
            "suggested_channel": "ai_automatic",
            "event_type": "online_matching",
        },
    ),
    # 低分段：<50 → 培育序列
    ActionRule(
        min_score=0.0,
        max_score=49.99,
        action_type=ActionType.NURTURE_SEQUENCE,
        priority=3,
        display_name="启动培育序列",
        description="匹配度较低，建议自动加入培育序列，持续发送资料、案例和提醒，提升意向",
        label=ScoreLevel.LOW,
        action_data={
            "action_hint": "加入培育序列（自动发送资料/提醒）",
            "auto_trigger": True,
            "requires_approval": False,
            "suggested_channel": "automated",
            "nurture_days": 30,
            "nurture_frequency": "weekly",
        },
    ),
]


# ============================================================
# 推荐结果模型
# ============================================================
@dataclass
class ActionRecommendation:
    """一条完整的行动推荐结果"""

    action_type: ActionType
    action_type_display: str
    score_level: ScoreLevel | None
    score: float
    score_normalized: float  # 归一化到 0~100
    rule: ActionRule
    confidence: float  # 推荐置信度（基于分数距离阈值边界的程度）
    alternatives: list[dict] = field(default_factory=list)  # 备选行动


# ============================================================
# 核心推荐引擎
# ============================================================
class ActionRecommender:
    """评分后自动下一步行动推荐引擎

    用法:
        recommender = ActionRecommender()
        result = recommender.recommend(score=85.0)
        # → SignContract 行动

        result = recommender.recommend(score=0.65, score_scale="0-1")
        # → 自动将 0.65 归一化为 65 → InviteEvent 行动
    """

    def __init__(self, rules: list[ActionRule] | None = None):
        """初始化推荐引擎

        Args:
            rules: 自定义规则列表，为空时使用 DEFAULT_RULES
        """
        self._rules = sorted(
            rules or DEFAULT_RULES,
            key=lambda r: r.priority,
        )
        logger.info(
            "ActionRecommender 初始化完成",
            extra={"rule_count": len(self._rules)},
        )

    @property
    def rules(self) -> list[ActionRule]:
        """获取当前规则列表（防御性拷贝）"""
        return list(self._rules)

    def update_rules(self, rules: list[ActionRule]) -> None:
        """动态更新推荐规则（支持运行时热更新）"""
        self._rules = sorted(rules, key=lambda r: r.priority)
        logger.info(
            "推荐规则已更新",
            extra={"new_rule_count": len(self._rules)},
        )

    # ---------------------------------------------------------
    # 分数归一化
    # ---------------------------------------------------------
    @staticmethod
    def normalize_score(score: float, scale: str = "0-100") -> float:
        """将评分归一化到 0~100 区间

        Args:
            score: 原始评分
            scale: 来源分数制式，支持 '0-100'（默认）、'0-1'

        Returns:
            归一化后的 0~100 分数
        """
        if scale == "0-1":
            return round(max(0.0, min(1.0, score)) * 100.0, 2)
        if scale == "0-100":
            return round(max(0.0, min(100.0, score)), 2)
        # 未知制式，尝试自动检测
        if 0.0 <= score <= 1.0:
            return round(score * 100.0, 2)
        return round(max(0.0, min(100.0, score)), 2)

    # ---------------------------------------------------------
    # 置信度计算
    # ---------------------------------------------------------
    @staticmethod
    def _compute_confidence(score: float, rule: ActionRule) -> float:
        """计算推荐置信度

        分数在阈值区间中心时置信度最高，靠近边界时降低。

        Args:
            score: 归一化分数 (0~100)
            rule: 匹配的规则

        Returns:
            0.0 ~ 1.0 的置信度
        """
        span = rule.max_score - rule.min_score
        if span <= 0:
            return 1.0
        center = (rule.min_score + rule.max_score) / 2
        distance_from_center = abs(score - center)
        # 线性衰减：边界处 0.5，中心处 1.0
        confidence = 1.0 - (distance_from_center / (span / 2)) * 0.5
        return max(0.5, min(1.0, confidence))

    # ---------------------------------------------------------
    # 备选行动推荐
    # ---------------------------------------------------------
    def _get_alternatives(
        self, score: float, matched_rule: ActionRule
    ) -> list[dict]:
        """获取备选行动（当主要推荐不适用时的降级方案）

        Args:
            score: 归一化分数
            matched_rule: 当前匹配的主要规则

        Returns:
            备选行动列表
        """
        alternatives = []
        for rule in self._rules:
            if rule is matched_rule:
                continue
            # 只推荐相邻级别的行动作为备选
            alternatives.append(
                {
                    "action_type": rule.action_type.value,
                    "display_name": rule.display_name,
                    "description": rule.description,
                    "reason": f"备选方案：{rule.display_name}",
                }
            )
        return alternatives

    # ---------------------------------------------------------
    # 主推荐方法
    # ---------------------------------------------------------
    def recommend(
        self,
        score: float,
        score_scale: str = "0-100",
        entity_id: int | None = None,
        entity_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ActionRecommendation:
        """根据评分输出推荐的下一步行动

        Args:
            score: 评分值（来自匹配引擎）
            score_scale: 分数制式，'0-100'（默认）或 '0-1'
            entity_id: 被评分实体 ID（企业/产品/供应商）
            entity_type: 实体类型（enterprise / product / supplier）
            context: 额外上下文信息（如用户角色、历史行为等）

        Returns:
            ActionRecommendation 推荐结果

        Raises:
            ValueError: 评分超出有效范围
        """
        # ---- 1. 归一化 ----
        normalized_score = self.normalize_score(score, score_scale)

        if normalized_score < 0 or normalized_score > 100:
            raise ValueError(
                f"评分值无效: {score} (归一化后: {normalized_score})，"
                f"期望 0~100 范围"
            )

        # ---- 2. 匹配规则 ----
        matched_rule = None
        for rule in self._rules:
            if rule.min_score <= normalized_score <= rule.max_score:
                matched_rule = rule
                break

        # 无匹配规则 → 返回人工复核
        if matched_rule is None:
            matched_rule = ActionRule(
                min_score=0.0,
                max_score=100.0,
                action_type=ActionType.MANUAL_REVIEW,
                priority=99,
                display_name="人工复核",
                description="评分未能匹配已知规则，建议人工复核处理",
                label=None,
                action_data={"requires_approval": True},
            )

        # ---- 3. 计算置信度 ----
        confidence = self._compute_confidence(normalized_score, matched_rule)

        # ---- 4. 获取备选 ----
        alternatives = self._get_alternatives(normalized_score, matched_rule)

        # ---- 5. 构建结果 ----
        recommendation = ActionRecommendation(
            action_type=matched_rule.action_type,
            action_type_display=matched_rule.display_name,
            score_level=matched_rule.label,
            score=score,
            score_normalized=normalized_score,
            rule=matched_rule,
            confidence=confidence,
            alternatives=alternatives,
        )

        logger.info(
            "行动推荐完成",
            extra={
                "entity_id": entity_id,
                "entity_type": entity_type,
                "original_score": score,
                "normalized_score": normalized_score,
                "action_type": matched_rule.action_type.value,
                "score_level": matched_rule.label.value if matched_rule.label else None,
                "confidence": round(confidence, 4),
            },
        )

        return recommendation

    # ---------------------------------------------------------
    # 批量推荐
    # ---------------------------------------------------------
    def recommend_batch(
        self,
        scores: list[dict[str, Any]],
        score_scale: str = "0-100",
    ) -> list[ActionRecommendation]:
        """批量评分推荐

        Args:
            scores: 评分列表，每个元素为 dict，需包含 'score' 键，
                    可选 'entity_id', 'entity_type', 'context'
            score_scale: 分数制式

        Returns:
            推荐结果列表
        """
        results = []
        for item in scores:
            result = self.recommend(
                score=item["score"],
                score_scale=score_scale,
                entity_id=item.get("entity_id"),
                entity_type=item.get("entity_type"),
                context=item.get("context"),
            )
            results.append(result)
        return results

    # ---------------------------------------------------------
    # 序列化工具
    # ---------------------------------------------------------
    @staticmethod
    def recommendation_to_dict(
        rec: ActionRecommendation,
    ) -> dict[str, Any]:
        """将推荐结果序列化为字典（用于 API 响应）"""
        return {
            "action_type": rec.action_type.value,
            "action_type_display": rec.action_type_display,
            "score_level": rec.score_level.value if rec.score_level else None,
            "score": rec.score,
            "score_normalized": rec.score_normalized,
            "confidence": round(rec.confidence, 4),
            "description": rec.rule.description,
            "action_data": rec.rule.action_data,
            "alternatives": rec.alternatives,
        }


# ============================================================
# 模块级单例（惰性初始化）
# ============================================================
_recommender_instance: ActionRecommender | None = None


def get_action_recommender() -> ActionRecommender:
    """获取全局 ActionRecommender 单例"""
    global _recommender_instance
    if _recommender_instance is None:
        _recommender_instance = ActionRecommender()
    return _recommender_instance
