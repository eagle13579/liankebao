"""
审美评估系统 — 编排引擎
==========================
编排 UIChecker、BrandChecker、CardDesignEvaluator、ReportGenerator 四个组件，
提供 run_design_review() 完整流程。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from features.design_review.ui_checker import UIChecker, UICheckResult
from features.design_review.brand_checker import BrandChecker, BrandCheckResult, BrandProfile
from features.design_review.card_design_evaluator import CardDesignEvaluator, CardEvaluationResult
from features.design_review.report_generator import ReportGenerator, DesignReviewReport

logger = logging.getLogger(__name__)


@dataclass
class DesignReviewResult:
    """审美评估完整结果"""
    report: Optional[DesignReviewReport] = None
    report_text: str = ""
    report_markdown: str = ""
    review_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "review_timestamp": self.review_timestamp,
            "report": self.report.to_dict() if self.report else None,
            "report_text": self.report_text,
            "report_markdown": self.report_markdown,
        }


class DesignReviewEngine:
    """
    审美评估系统主引擎。
    一键执行：UI 一致性检查 → 品牌一致性检查 → 名片设计评估 → 报告生成。
    """

    def __init__(
        self,
        ui_checker: Optional[UIChecker] = None,
        brand_checker: Optional[BrandChecker] = None,
        evaluator: Optional[CardDesignEvaluator] = None,
        report_generator: Optional[ReportGenerator] = None,
    ):
        self.ui_checker = ui_checker or UIChecker()
        self.brand_checker = brand_checker or BrandChecker()
        self.evaluator = evaluator or CardDesignEvaluator()
        self.report_generator = report_generator or ReportGenerator()
        logger.info("DesignReviewEngine 初始化完成")

    def run_design_review(
        self,
        design_data: dict,
        brand_profile: Optional[BrandProfile] = None,
        report_format: str = "all",
    ) -> DesignReviewResult:
        """
        执行完整审美评估流程。

        Args:
            design_data: 设计数据字典
            brand_profile: 品牌档案（可选，覆盖默认品牌）
            report_format: 报告格式 — "dict" / "text" / "markdown" / "all"

        Returns:
            DesignReviewResult: 完整评估结果
        """
        logger.info("=" * 60)
        logger.info("🎨 开始审美评估流程")
        logger.info("=" * 60)

        # 如果提供了品牌档案，使用它
        if brand_profile:
            self.brand_checker = BrandChecker(brand_profile=brand_profile)

        # 步骤1: UI 一致性检查
        logger.info("步骤 1/4: UI 一致性检查...")
        ui_result = self.ui_checker.check(design_data)
        logger.info(f"       → score={ui_result.score}, "
                     f"errors={ui_result.error_count}, warnings={ui_result.warning_count}")

        # 步骤2: 品牌一致性检查
        logger.info("步骤 2/4: 品牌一致性检查...")
        brand_result = self.brand_checker.check_brand(design_data)
        logger.info(f"       → brand_score={brand_result.brand_score}, "
                     f"errors={brand_result.error_count}, warnings={brand_result.warning_count}")

        # 步骤3: 名片设计评估
        logger.info("步骤 3/4: 名片设计评估...")
        card_result = self.evaluator.evaluate(design_data)
        logger.info(f"       → overall={card_result.overall_score:.1f}, passed={card_result.passed}")

        # 步骤4: 报告生成
        logger.info("步骤 4/4: 报告生成...")

        report = None
        report_text = ""
        report_markdown = ""

        if report_format in ("dict", "all"):
            report_dict = self.report_generator.generate_report(
                "dict", ui_result, brand_result, card_result,
            )
            report = DesignReviewReport(
                ui_result=ui_result,
                brand_result=brand_result,
                card_eval_result=card_result,
                overall_grade=report_dict.get("overall_grade", "N/A"),
                summary=report_dict.get("summary", ""),
                report_timestamp=report_dict.get("report_timestamp", ""),
            )

        if report_format in ("text", "all"):
            report_text = self.report_generator.generate_report(
                "text", ui_result, brand_result, card_result,
            )

        if report_format in ("markdown", "all"):
            report_markdown = self.report_generator.generate_report(
                "markdown", ui_result, brand_result, card_result,
            )

        result = DesignReviewResult(
            report=report,
            report_text=report_text,
            report_markdown=report_markdown,
            review_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        grade = report.overall_grade if report else "N/A"
        logger.info(f"审美评估完成: 综合等级 {grade}")

        return result


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 DesignReviewEngine 烟雾测试")
    print("=" * 60)

    engine = DesignReviewEngine()

    # 测试数据
    excellent_design = {
        "colors": ["#1A73E8", "#FFFFFF"],
        "brand_colors": ["#1A73E8", "#FFFFFF"],
        "spacings": [4, 8, 12, 16, 24],
        "fonts": ["Inter", "PingFang SC"],
        "border_radii": [4, 8],
        "icon_styles": ["outline"],
        "logo": {"present": True, "size": 128},
        "tone": "professional",
        "has_tagline": True,
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

    # 测试1: 完整流程 (all 格式)
    result = engine.run_design_review(excellent_design, report_format="all")
    assert result.report is not None, "测试1失败：report 不应为空"
    assert len(result.report_text) > 0, "测试1失败：report_text 不应为空"
    assert len(result.report_markdown) > 0, "测试1失败：report_markdown 不应为空"
    print(f"✅ 测试1 完整流程: grade={result.report.overall_grade}, "
          f"text={len(result.report_text)}chars, md={len(result.report_markdown)}chars")

    # 测试2: dict 格式
    result_dict = engine.run_design_review(excellent_design, report_format="dict")
    assert result_dict.report is not None, "测试2失败：报告应存在"
    assert result_dict.report.overall_grade != "", "测试2失败：应有等级"
    print(f"✅ 测试2 dict格式: grade={result_dict.report.overall_grade}")

    # 测试3: text 格式
    result_text = engine.run_design_review(excellent_design, report_format="text")
    assert len(result_text.report_text) > 0, "测试3失败：应有 text 报告"
    print(f"✅ 测试3 text格式: {len(result_text.report_text)} 字符")

    # 测试4: markdown 格式
    result_md = engine.run_design_review(excellent_design, report_format="markdown")
    assert len(result_md.report_markdown) > 0, "测试4失败：应有 markdown 报告"
    print(f"✅ 测试4 markdown格式: {len(result_md.report_markdown)} 字符")

    # 测试5: 自定义品牌档案
    custom_profile = BrandProfile(
        name="测试品牌",
        primary_color="#FF6600",
        secondary_color="#000000",
        font_families=["CustomFont"],
        tone="innovative",
        has_logo=True,
        tagline="测试用",
    )
    custom_design = {**excellent_design}
    custom_design["colors"] = ["#FF6600", "#000000"]
    custom_design["fonts"] = ["CustomFont"]
    custom_design["tone"] = "innovative"
    result_custom = engine.run_design_review(custom_design, brand_profile=custom_profile)
    assert result_custom.report.overall_grade in ("A", "B"), "测试5失败：自定义品牌应得高等级"
    print(f"✅ 测试5 自定义品牌: grade={result_custom.report.overall_grade}")

    # 测试6: 低分场景
    poor_design = {
        "colors": ["#FF0000", "#00FF00", "#0000FF", "#FFA500"],
        "spacings": [3, 7, 11, 15],
        "fonts": ["FontA", "FontB", "FontC", "FontD"],
        "border_radii": [3, 7, 11],
        "icon_styles": ["outline", "filled"],
        "logo": {"present": False},
        "tone": "casual",
        "has_tagline": False,
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
    result_poor = engine.run_design_review(poor_design)
    assert result_poor.report.overall_grade in ("D", "F"), "测试6失败：低分设计应得低等级"
    print(f"✅ 测试6 低分场景: grade={result_poor.report.overall_grade}")

    # 测试7: 平行多次调用
    for i in range(3):
        r = engine.run_design_review(excellent_design, report_format="dict")
        assert r.report is not None, f"测试7失败：第{i+1}次调用结果为空"
    print(f"✅ 测试7 多次调用: 3 次平行调用均正常")

    print(f"\n🎉 全部 7 项烟雾测试通过!\n")
