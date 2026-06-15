"""
审美评估系统 — AI 数字名片设计评估器
======================================
评估 AI 数字名片的整体设计质量，包括布局、内容、视觉、交互等维度。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 评估维度 & 权重
# ============================================================

EVALUATION_DIMENSIONS = {
    "layout": {
        "weight": 0.20,
        "name": "布局结构",
        "description": "信息层级清晰、布局合理、对齐一致",
    },
    "visual_design": {
        "weight": 0.25,
        "name": "视觉设计",
        "description": "配色和谐、字体可读、图标统一",
    },
    "content_quality": {
        "weight": 0.25,
        "name": "内容质量",
        "description": "信息完整、文案简洁、调用动作明确",
    },
    "brand_consistency": {
        "weight": 0.20,
        "name": "品牌一致性",
        "description": "Logo/配色/字体/语调符合品牌规范",
    },
    "interaction": {
        "weight": 0.10,
        "name": "交互体验",
        "description": "点击区域合理、交互动效流畅、响应及时",
    },
}


@dataclass
class DimensionScore:
    """单一维度评分"""
    dimension_key: str
    dimension_name: str
    score: float  # 0-100
    weight: float
    weighted_score: float
    comments: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dimension_key": self.dimension_key,
            "dimension_name": self.dimension_name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 1),
            "comments": self.comments,
        }


@dataclass
class CardEvaluationResult:
    """名片评估结果"""
    overall_score: float = 0.0
    dimensions: list = field(default_factory=list)
    strengths: list = field(default_factory=list)
    improvements: list = field(default_factory=list)
    passed: bool = False
    evaluate_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 1),
            "passed": self.passed,
            "evaluate_timestamp": self.evaluate_timestamp,
            "strengths": self.strengths,
            "improvements": self.improvements,
            "dimensions": [d.to_dict() if isinstance(d, DimensionScore) else d for d in self.dimensions],
        }


class CardDesignEvaluator:
    """
    AI 数字名片设计评估器。
    从布局、视觉、内容、品牌、交互五个维度评估名片设计质量。
    """

    def __init__(self, pass_threshold: float = 60.0):
        self.pass_threshold = pass_threshold
        self.dimensions = EVALUATION_DIMENSIONS
        logger.info(f"CardDesignEvaluator 初始化, 通过阈值: {pass_threshold}")

    def _score_layout(self, card_data: dict) -> DimensionScore:
        """评估布局结构"""
        score = 80.0  # 基础分
        comments = []

        alignment = card_data.get("alignment", "good")
        if alignment == "perfect":
            score += 10
            comments.append("布局对齐完美")
        elif alignment == "good":
            score += 5
            comments.append("布局对齐良好")
        elif alignment == "fair":
            score -= 10
            comments.append("布局对齐一般，建议优化间距")
        else:
            score -= 20
            comments.append("布局对齐较差，需要重构")

        sections = card_data.get("sections", [])
        if len(sections) >= 4:
            score += 5
            comments.append("信息分区完整")
        elif len(sections) <= 2:
            score -= 10
            comments.append("信息分区过少，建议增加")

        score = max(0, min(100, score))
        return DimensionScore(
            dimension_key="layout",
            dimension_name=self.dimensions["layout"]["name"],
            score=score,
            weight=self.dimensions["layout"]["weight"],
            weighted_score=score * self.dimensions["layout"]["weight"],
            comments=comments,
        )

    def _score_visual(self, card_data: dict) -> DimensionScore:
        """评估视觉设计"""
        score = 75.0
        comments = []

        color_harmony = card_data.get("color_harmony", "good")
        if color_harmony == "excellent":
            score += 15
            comments.append("配色和谐度高")
        elif color_harmony == "good":
            score += 5
            comments.append("配色基本和谐")
        elif color_harmony == "fair":
            score -= 10
            comments.append("配色需调整，建议使用品牌色板")
        else:
            score -= 20
            comments.append("配色冲突严重")

        font_readability = card_data.get("font_readability", "good")
        if font_readability == "excellent":
            score += 10
            comments.append("字体可读性优秀")
        elif font_readability == "poor":
            score -= 15
            comments.append("字体可读性差，建议增大字号或提高对比度")

        icon_quality = card_data.get("icon_quality", "good")
        if icon_quality == "poor":
            score -= 10
            comments.append("图标质量需提升")

        score = max(0, min(100, score))
        return DimensionScore(
            dimension_key="visual_design",
            dimension_name=self.dimensions["visual_design"]["name"],
            score=score,
            weight=self.dimensions["visual_design"]["weight"],
            weighted_score=score * self.dimensions["visual_design"]["weight"],
            comments=comments,
        )

    def _score_content(self, card_data: dict) -> DimensionScore:
        """评估内容质量"""
        score = 75.0
        comments = []

        info_completeness = card_data.get("info_completeness", 0.7)
        if info_completeness >= 0.9:
            score += 15
            comments.append("信息完整度高")
        elif info_completeness >= 0.7:
            score += 5
            comments.append("信息基本完整")
        else:
            score -= 15
            comments.append("信息缺失较多，建议补充")

        has_cta = card_data.get("has_cta", False)
        if has_cta:
            score += 10
            comments.append("包含明确的行动召唤按钮")
        else:
            score -= 5
            comments.append("缺少行动召唤按钮，建议添加")

        description_quality = card_data.get("description_quality", "good")
        if description_quality == "excellent":
            score += 5
            comments.append("文案简洁有力")
        elif description_quality == "poor":
            score -= 10
            comments.append("文案需优化，建议突出核心价值")

        score = max(0, min(100, score))
        return DimensionScore(
            dimension_key="content_quality",
            dimension_name=self.dimensions["content_quality"]["name"],
            score=score,
            weight=self.dimensions["content_quality"]["weight"],
            weighted_score=score * self.dimensions["content_quality"]["weight"],
            comments=comments,
        )

    def _score_brand(self, card_data: dict) -> DimensionScore:
        """评估品牌一致性"""
        score = 80.0
        comments = []

        brand_alignment = card_data.get("brand_alignment", "good")
        if brand_alignment == "perfect":
            score += 10
            comments.append("品牌一致性高")
        elif brand_alignment == "good":
            score += 5
            comments.append("品牌基本一致")
        elif brand_alignment == "fair":
            score -= 10
            comments.append("品牌一致性需加强")
        else:
            score -= 20
            comments.append("品牌一致性差，需全面调整")

        logo_quality = card_data.get("logo_quality", "good")
        if logo_quality == "poor":
            score -= 10
            comments.append("Logo 质量需提升")

        score = max(0, min(100, score))
        return DimensionScore(
            dimension_key="brand_consistency",
            dimension_name=self.dimensions["brand_consistency"]["name"],
            score=score,
            weight=self.dimensions["brand_consistency"]["weight"],
            weighted_score=score * self.dimensions["brand_consistency"]["weight"],
            comments=comments,
        )

    def _score_interaction(self, card_data: dict) -> DimensionScore:
        """评估交互体验"""
        score = 75.0
        comments = []

        tap_targets = card_data.get("tap_targets", "good")
        if tap_targets == "excellent":
            score += 15
            comments.append("点击区域设计合理")
        elif tap_targets == "poor":
            score -= 15
            comments.append("点击区域过小，需增大可点击区域")

        has_animation = card_data.get("has_animation", False)
        if has_animation:
            score += 10
            comments.append("包含微交互动效")

        responsive = card_data.get("responsive", True)
        if not responsive:
            score -= 10
            comments.append("未适配不同屏幕尺寸")

        score = max(0, min(100, score))
        return DimensionScore(
            dimension_key="interaction",
            dimension_name=self.dimensions["interaction"]["name"],
            score=score,
            weight=self.dimensions["interaction"]["weight"],
            weighted_score=score * self.dimensions["interaction"]["weight"],
            comments=comments,
        )

    def evaluate(self, card_data: dict) -> CardEvaluationResult:
        """
        执行名片设计评估。

        Args:
            card_data: 名片数据字典，包含布局、视觉、内容、品牌、交互各维度的信息

        Returns:
            CardEvaluationResult: 评估结果
        """
        dim_scores = [
            self._score_layout(card_data),
            self._score_visual(card_data),
            self._score_content(card_data),
            self._score_brand(card_data),
            self._score_interaction(card_data),
        ]

        overall = sum(d.weighted_score for d in dim_scores)

        # 生成亮点和改进项
        strengths = []
        improvements = []
        for d in dim_scores:
            if d.score >= 80:
                strengths.append(f"{d.dimension_name}: {d.score:.0f} 分 — 表现优秀")
            elif d.score < 60:
                improvements.append(f"{d.dimension_name}: {d.score:.0f} 分 — 需要改进")
                for c in d.comments:
                    improvements.append(f"  · {c}")

        passed = overall >= self.pass_threshold

        result = CardEvaluationResult(
            overall_score=overall,
            dimensions=dim_scores,
            strengths=strengths,
            improvements=improvements,
            passed=passed,
            evaluate_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        logger.info(f"名片设计评估完成: overall={overall:.1f}, passed={passed}")
        return result


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 CardDesignEvaluator 烟雾测试")
    print("=" * 60)

    evaluator = CardDesignEvaluator()

    # 测试1: 优秀名片
    excellent_card = {
        "alignment": "perfect",
        "sections": ["header", "contact", "services", "social", "cta"],
        "color_harmony": "excellent",
        "font_readability": "excellent",
        "icon_quality": "good",
        "info_completeness": 0.95,
        "has_cta": True,
        "description_quality": "excellent",
        "brand_alignment": "perfect",
        "logo_quality": "good",
        "tap_targets": "excellent",
        "has_animation": True,
        "responsive": True,
    }
    result_good = evaluator.evaluate(excellent_card)
    assert result_good.passed, "测试1失败：优秀名片应通过"
    print(f"✅ 测试1 优秀名片: overall={result_good.overall_score:.1f}, passed={result_good.passed}")

    # 测试2: 低分名片
    poor_card = {
        "alignment": "poor",
        "sections": ["header"],
        "color_harmony": "poor",
        "font_readability": "poor",
        "icon_quality": "poor",
        "info_completeness": 0.3,
        "has_cta": False,
        "description_quality": "poor",
        "brand_alignment": "poor",
        "logo_quality": "poor",
        "tap_targets": "poor",
        "has_animation": False,
        "responsive": False,
    }
    result_poor = evaluator.evaluate(poor_card)
    assert not result_poor.passed, "测试2失败：差名片应不通过"
    print(f"✅ 测试2 低分名片: overall={result_poor.overall_score:.1f}, passed={result_poor.passed}")

    # 测试3: 维度数量
    assert len(result_good.dimensions) == 5, "测试3失败：应有 5 个评估维度"
    print(f"✅ 测试3 维度数量: {len(result_good.dimensions)} 个维度")

    # 测试4: 评分上下界
    assert 0 <= result_good.overall_score <= 100, "测试4失败：总分应在 0-100"
    print(f"✅ 测试4 评分范围: overall={result_good.overall_score:.1f} (在 0-100 范围内)")

    print(f"\n🎉 所有烟雾测试通过!\n")
