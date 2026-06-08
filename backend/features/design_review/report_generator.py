"""
审美评估系统 — 评估报告生成器
================================
支持 text / dict / markdown 三种格式的评估报告输出。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Union

from features.design_review.ui_checker import UICheckResult
from features.design_review.brand_checker import BrandCheckResult
from features.design_review.card_design_evaluator import CardEvaluationResult

logger = logging.getLogger(__name__)


@dataclass
class DesignReviewReport:
    """完整评估报告"""
    ui_result: Optional[UICheckResult] = None
    brand_result: Optional[BrandCheckResult] = None
    card_eval_result: Optional[CardEvaluationResult] = None
    overall_grade: str = ""  # A / B / C / D / F
    summary: str = ""
    report_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "overall_grade": self.overall_grade,
            "summary": self.summary,
            "report_timestamp": self.report_timestamp,
            "ui_check": self.ui_result.to_dict() if self.ui_result else None,
            "brand_check": self.brand_result.to_dict() if self.brand_result else None,
            "card_evaluation": self.card_eval_result.to_dict() if self.card_eval_result else None,
        }


class ReportGenerator:
    """
    评估报告生成器。
    支持三种输出格式：text / dict / markdown。
    """

    @staticmethod
    def _calculate_overall_grade(
        ui_result: Optional[UICheckResult],
        brand_result: Optional[BrandCheckResult],
        card_eval_result: Optional[CardEvaluationResult],
    ) -> tuple:
        """计算综合等级和摘要"""
        scores = []

        if ui_result:
            scores.append(("UI一致性", ui_result.score))
        if brand_result:
            scores.append(("品牌一致性", brand_result.brand_score))
        if card_eval_result:
            scores.append(("名片设计", card_eval_result.overall_score))

        if not scores:
            return "N/A", "无评估数据"

        avg_score = sum(s for _, s in scores) / len(scores)

        if avg_score >= 90:
            grade = "A"
            summary = "优秀 — 设计质量卓越，建议保持"
        elif avg_score >= 75:
            grade = "B"
            summary = "良好 — 设计质量较高，少数细节可优化"
        elif avg_score >= 60:
            grade = "C"
            summary = "一般 — 设计基本合格，建议针对性改进"
        elif avg_score >= 40:
            grade = "D"
            summary = "较差 — 存在较多问题，建议重新设计"
        else:
            grade = "F"
            summary = "不合格 — 需要全面重构"

        detail = " | ".join(f"{name}: {s:.0f}分" for name, s in scores)
        summary = f"{summary}（{detail}）"

        return grade, summary

    def generate_report(
        self,
        format: str = "dict",
        ui_result: Optional[UICheckResult] = None,
        brand_result: Optional[BrandCheckResult] = None,
        card_eval_result: Optional[CardEvaluationResult] = None,
    ) -> Union[dict, str]:
        """
        生成评估报告。

        Args:
            format: 输出格式 — "dict", "text", "markdown"
            ui_result: UI 一致性检查结果
            brand_result: 品牌一致性检查结果
            card_eval_result: 名片设计评估结果

        Returns:
            指定格式的报告
        """
        grade, summary = self._calculate_overall_grade(ui_result, brand_result, card_eval_result)

        report = DesignReviewReport(
            ui_result=ui_result,
            brand_result=brand_result,
            card_eval_result=card_eval_result,
            overall_grade=grade,
            summary=summary,
            report_timestamp=datetime.utcnow().isoformat() + "Z",
        )

        if format == "dict":
            return report.to_dict()

        if format == "text":
            return self._to_text(report)

        if format == "markdown":
            return self._to_markdown(report)

        raise ValueError(f"不支持的格式: {format}，支持 dict / text / markdown")

    def _to_text(self, report: DesignReviewReport) -> str:
        """生成纯文本报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("  审美评估报告")
        lines.append("=" * 60)
        lines.append(f"综合等级: {report.overall_grade}")
        lines.append(f"评估摘要: {report.summary}")
        lines.append(f"报告时间: {report.report_timestamp}")
        lines.append("")

        if report.ui_result:
            ui = report.ui_result
            lines.append("── UI 一致性检查 ──")
            lines.append(f"  分数: {ui.score}/100 | 通过: {'是' if ui.passed else '否'}")
            lines.append(f"  问题数: {ui.total_checks} (错误 {ui.error_count}, 警告 {ui.warning_count})")
            for issue in ui.issues[:5]:
                lines.append(f"  [{issue.severity.upper()}] {issue.message}")
            lines.append("")

        if report.brand_result:
            br = report.brand_result
            lines.append("── 品牌一致性检查 ──")
            lines.append(f"  分数: {br.brand_score}/100 | 通过: {'是' if br.passed else '否'}")
            lines.append(f"  问题数: {br.total_checks} (错误 {br.error_count}, 警告 {br.warning_count})")
            for issue in br.issues[:5]:
                lines.append(f"  [{issue.severity.upper()}] {issue.message}")
            lines.append("")

        if report.card_eval_result:
            ce = report.card_eval_result
            lines.append("── 名片设计评估 ──")
            lines.append(f"  总分: {ce.overall_score:.1f}/100 | 通过: {'是' if ce.passed else '否'}")
            lines.append("  各维度:")
            for d in ce.dimensions:
                lines.append(f"    {d.dimension_name}: {d.score:.0f}/100 (权重 {d.weight:.0%})")
            lines.append("")

        return "\n".join(lines)

    def _to_markdown(self, report: DesignReviewReport) -> str:
        """生成 Markdown 格式报告"""
        md = []
        md.append("# 审美评估报告")
        md.append("")
        md.append(f"**综合等级**: {report.overall_grade}")
        md.append(f"**评估摘要**: {report.summary}")
        md.append(f"**报告时间**: {report.report_timestamp}")
        md.append("")

        if report.ui_result:
            ui = report.ui_result
            md.append("## UI 一致性检查")
            md.append("")
            md.append(f"- **分数**: {ui.score}/100")
            md.append(f"- **状态**: {'✅ 通过' if ui.passed else '❌ 不通过'}")
            md.append(f"- **问题**: {ui.total_checks} 个（错误 {ui.error_count}, 警告 {ui.warning_count}）")
            if ui.issues:
                md.append("")
                md.append("### 问题列表")
                md.append("")
                for issue in ui.issues:
                    icon = "🔴" if issue.severity == "error" else ("🟡" if issue.severity == "warning" else "🔵")
                    md.append(f"- {icon} **[{issue.severity.upper()}]** {issue.message}")
            md.append("")

        if report.brand_result:
            br = report.brand_result
            md.append("## 品牌一致性检查")
            md.append("")
            md.append(f"- **分数**: {br.brand_score}/100")
            md.append(f"- **状态**: {'✅ 通过' if br.passed else '❌ 不通过'}")
            md.append(f"- **问题**: {br.total_checks} 个（错误 {br.error_count}, 警告 {br.warning_count}）")
            if br.issues:
                md.append("")
                md.append("### 问题列表")
                md.append("")
                for issue in br.issues:
                    icon = "🔴" if issue.severity == "error" else ("🟡" if issue.severity == "warning" else "🔵")
                    md.append(f"- {icon} **[{issue.severity.upper()}]** {issue.message}")
            md.append("")

        if report.card_eval_result:
            ce = report.card_eval_result
            md.append("## 名片设计评估")
            md.append("")
            md.append(f"- **总分**: {ce.overall_score:.1f}/100")
            md.append(f"- **状态**: {'✅ 通过' if ce.passed else '❌ 不通过'}")
            md.append("")
            md.append("### 各维度评分")
            md.append("")
            md.append("| 维度 | 分数 | 权重 | 加权分 |")
            md.append("|------|------|------|--------|")
            for d in ce.dimensions:
                md.append(f"| {d.dimension_name} | {d.score:.0f} | {d.weight:.0%} | {d.weighted_score:.1f} |")
            md.append("")
            if ce.strengths:
                md.append("### 亮点")
                md.append("")
                for s in ce.strengths:
                    md.append(f"- ✅ {s}")
                md.append("")
            if ce.improvements:
                md.append("### 改进建议")
                md.append("")
                for imp in ce.improvements:
                    md.append(f"- 💡 {imp}")
                md.append("")

        return "\n".join(md)


# ============================================================
# 烟雾测试
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("🧪 ReportGenerator 烟雾测试")
    print("=" * 60)

    from features.design_review.ui_checker import UIChecker
    from features.design_review.brand_checker import BrandChecker
    from features.design_review.card_design_evaluator import CardDesignEvaluator

    ui_checker = UIChecker()
    brand_checker = BrandChecker()
    evaluator = CardDesignEvaluator()
    generator = ReportGenerator()

    # 测试数据
    perfect_design = {
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

    ui_result = ui_checker.check(perfect_design)
    brand_result = brand_checker.check_brand(perfect_design)
    card_result = evaluator.evaluate(perfect_design)

    # 测试1: dict 格式
    report_dict = generator.generate_report("dict", ui_result, brand_result, card_result)
    assert isinstance(report_dict, dict), "测试1失败：应返回 dict"
    assert "overall_grade" in report_dict, "测试1失败：dict 应包含 overall_grade"
    print(f"✅ 测试1 dict 格式: overall_grade={report_dict['overall_grade']}")

    # 测试2: text 格式
    report_text = generator.generate_report("text", ui_result, brand_result, card_result)
    assert isinstance(report_text, str), "测试2失败：应返回 str"
    assert "综合等级" in report_text, "测试2失败：text 应包含综合等级"
    print(f"✅ 测试2 text 格式: 包含关键信息 ({len(report_text)} 字符)")

    # 测试3: markdown 格式
    report_md = generator.generate_report("markdown", ui_result, brand_result, card_result)
    assert isinstance(report_md, str), "测试3失败：应返回 str"
    assert "# 审美评估报告" in report_md, "测试3失败：markdown 应包含标题"
    print(f"✅ 测试3 markdown 格式: 包含标题 ({len(report_md)} 字符)")

    # 测试4: 空结果
    report_empty = generator.generate_report("dict")
    assert report_empty["overall_grade"] == "N/A", "测试4失败：空结果等级应为 N/A"
    print(f"✅ 测试4 空结果: overall_grade={report_empty['overall_grade']}")

    print(f"\n🎉 所有烟雾测试通过!\n")
