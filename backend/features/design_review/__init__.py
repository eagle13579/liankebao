"""
审美评估系统 (Design Review)
==============================
UI 一致性检查、品牌一致性检查、AI 数字名片设计评估、评估报告生成。

铁律六：只新增不覆盖，独立模块。
"""

from features.design_review.engine import DesignReviewEngine, DesignReviewResult
from features.design_review.ui_checker import UIChecker, UICheckResult, UIIssue
from features.design_review.brand_checker import BrandChecker, BrandCheckResult, BrandIssue, BrandProfile
from features.design_review.card_design_evaluator import CardDesignEvaluator, CardEvaluationResult, DimensionScore
from features.design_review.report_generator import ReportGenerator, DesignReviewReport

# 导出默认 Engine 实例
default_engine = DesignReviewEngine()

__all__ = [
    "DesignReviewEngine",
    "DesignReviewResult",
    "UIChecker",
    "UICheckResult",
    "UIIssue",
    "BrandChecker",
    "BrandCheckResult",
    "BrandIssue",
    "BrandProfile",
    "CardDesignEvaluator",
    "CardEvaluationResult",
    "DimensionScore",
    "ReportGenerator",
    "DesignReviewReport",
    "default_engine",
]
