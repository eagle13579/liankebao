"""
链客宝 - 评估报告生成器
========================
将检查结果生成为结构化、可读性强的评估报告。

支持多种输出格式：
- dict: Python dict 格式
- text: 纯文本可读格式（控制台友好）
- markdown: Markdown 格式化报告
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .ui_checker import UiCheckResult
from .brand_checker import BrandCheckResult
from .card_design_evaluator import CardDesignScore

logger = logging.getLogger(__name__)


class ReportFormat(Enum):
    """报告格式枚举"""
    DICT = 'dict'
    TEXT = 'text'
    MARKDOWN = 'markdown'


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _score_to_grade(score: int) -> str:
    """将分数转换为等级"""
    if score >= 90:
        return 'A (优秀)'
    elif score >= 80:
        return 'B (良好)'
    elif score >= 70:
        return 'C (一般)'
    elif score >= 60:
        return 'D (待改进)'
    else:
        return 'F (不及格)'


def _score_to_emoji(score: int) -> str:
    """分数对应表情符号"""
    if score >= 90:
        return '🟢'
    elif score >= 70:
        return '🟡'
    else:
        return '🔴'


def _indent(text: str, level: int = 1) -> str:
    """缩进文本"""
    return '  ' * level + text


def _format_issue_list(
    issues: list[Any],
    title: str,
    max_items: int = 10,
) -> str:
    """格式化问题列表为可读文本"""
    if not issues:
        return f'  ✓ {title}: 无问题\n'

    lines = [f'  ⚠ {title}: {len(issues)} 个问题']
    for issue in issues[:max_items]:
        severity = getattr(issue, 'severity', 'info')
        sev_icon = {'error': '❌', 'warning': '⚠️', 'info': '💡'}.get(severity, '•')
        file_path = getattr(issue, 'file_path', '')
        description = getattr(issue, 'description', str(issue))
        lines.append(f'    {sev_icon} [{file_path}] {description}')

    if len(issues) > max_items:
        lines.append(f'    ... 还有 {len(issues) - max_items} 个问题未显示')

    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# 报告生成器
# ---------------------------------------------------------------------------


class ReviewReportGenerator:
    """
    评估报告生成器

    将审美评估系统的各检查器结果整合为可读性强的报告，
    支持 dict / text / markdown 三种格式。

    使用方式:
        generator = ReviewReportGenerator(
            ui_result=ui_result,
            brand_result=brand_result,
            card_score=card_score,
        )
        # 生成纯文本报告
        report = generator.generate(format=ReportFormat.TEXT)
        print(report)

        # 生成 MD 报告
        md_report = generator.generate(format=ReportFormat.MARKDOWN)
    """

    def __init__(
        self,
        project_name: str = '链客宝',
        ui_result: Optional[UiCheckResult] = None,
        brand_result: Optional[BrandCheckResult] = None,
        card_score: Optional[CardDesignScore] = None,
    ) -> None:
        """
        初始化报告生成器

        Args:
            project_name: 项目名称
            ui_result: UI一致性检查结果
            brand_result: 品牌一致性检查结果
            card_score: 名片设计评分
        """
        self.project_name = project_name
        self.ui_result = ui_result or UiCheckResult()
        self.brand_result = brand_result or BrandCheckResult()
        self.card_score = card_score or CardDesignScore()

    def _calculate_overall_score(self) -> int:
        """计算综合评分（加权平均）"""
        ui_score = self.ui_result.score
        brand_score = self.brand_result.score
        card_score = self.card_score.overall_score

        # 加权: UI 30%, 品牌 30%, 名片 40%
        total = int(ui_score * 0.30 + brand_score * 0.30 + card_score * 0.40)
        return max(0, min(100, total))

    def _summary_dict(self) -> dict[str, Any]:
        """构建摘要 dict"""
        ui_score = self.ui_result.score
        brand_score = self.brand_result.score
        card_score = self.card_score.overall_score
        overall = self._calculate_overall_score()

        return {
            'project': self.project_name,
            'timestamp': datetime.now().isoformat(),
            'overall': {
                'score': overall,
                'grade': _score_to_grade(overall),
            },
            'dimensions': {
                'ui_consistency': {
                    'score': ui_score,
                    'grade': _score_to_grade(ui_score),
                    'files_checked': self.ui_result.total_files_checked,
                    'issues': self.ui_result.issue_count,
                },
                'brand_consistency': {
                    'score': brand_score,
                    'grade': _score_to_grade(brand_score),
                    'files_checked': self.brand_result.total_files_checked,
                    'issues': self.brand_result.issue_count,
                    'brand_alignment_ratio': round(self.brand_result.brand_alignment_ratio, 3),
                },
                'card_design': {
                    'score': card_score,
                    'grade': _score_to_grade(card_score),
                    'sub_scores': {
                        'structure': self.card_score.structure_score,
                        'field_coverage': self.card_score.field_coverage_score,
                        'component_architecture': self.card_score.component_score,
                        'theme_usage': self.card_score.theme_score,
                    },
                },
            },
            'summary': self._generate_summary_text(overall, ui_score, brand_score, card_score),
        }

    def _generate_summary_text(
        self,
        overall: int,
        ui_score: int,
        brand_score: int,
        card_score: int,
    ) -> str:
        """生成总结文本"""
        parts: list[str] = []

        if overall >= 80:
            parts.append(f'{self.project_name} 审美评估整体良好。')
        elif overall >= 60:
            parts.append(f'{self.project_name} 审美评估存在一定改进空间。')
        else:
            parts.append(f'{self.project_name} 审美评估需要重点关注和改进。')

        parts.append(f'综合得分 {overall} 分。')
        parts.append(f'UI一致性 {ui_score} 分，品牌一致性 {brand_score} 分，名片设计 {card_score} 分。')

        return ' '.join(parts)

    def _generate_text_report(self) -> str:
        """生成纯文本报告（控制台友好）"""
        overall = self._calculate_overall_score()
        ui_score = self.ui_result.score
        brand_score = self.brand_result.score
        card_score = self.card_score.overall_score

        lines: list[str] = []
        sep = '=' * 60

        # 标题
        lines.append(sep)
        lines.append(f'  {self.project_name} - 审美评估报告')
        lines.append(f'  生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append(sep)
        lines.append('')

        # 总体评分
        lines.append(f'  📊 综合评分: {overall}/100 {_score_to_emoji(overall)} ({_score_to_grade(overall)})')
        lines.append('')

        # 各维度评分
        lines.append('  ── 维度评分 ──')
        lines.append(f'    🖥 UI一致性:     {ui_score:>3}/100 {_score_to_emoji(ui_score)} ({_score_to_grade(ui_score)})')
        lines.append(f'    🎨 品牌一致性:   {brand_score:>3}/100 {_score_to_emoji(brand_score)} ({_score_to_grade(brand_score)})')
        lines.append(f'    📇 名片设计:     {card_score:>3}/100 {_score_to_emoji(card_score)} ({_score_to_grade(card_score)})')
        lines.append('')

        # 统计概要
        lines.append('  ── 统计概要 ──')
        lines.append(f'    检查文件数: {self.ui_result.total_files_checked} 个')
        lines.append(f'    颜色品牌一致率: {self.brand_result.brand_alignment_ratio:.1%}')
        lines.append(f'    总问题数: {self.ui_result.issue_count + self.brand_result.issue_count} 个')
        lines.append('')

        # UI 一致性问题
        lines.append('  ── UI一致性问题 ──')
        if self.ui_result.component_naming_issues:
            lines.append(_format_issue_list(
                self.ui_result.component_naming_issues,
                '组件命名问题',
            ))
        if self.ui_result.style_inconsistencies:
            lines.append(_format_issue_list(
                self.ui_result.style_inconsistencies,
                '样式不一致',
            ))
        if self.ui_result.responsive_layout_issues:
            lines.append(_format_issue_list(
                self.ui_result.responsive_layout_issues,
                '响应式布局问题',
            ))
        if not self.ui_result.issue_count:
            lines.append('  ✓ 未发现UI一致性问题')
        lines.append('')

        # 品牌一致性问题
        lines.append('  ── 品牌一致性问题 ──')
        if self.brand_result.color_issues:
            lines.append(_format_issue_list(
                self.brand_result.color_issues,
                '颜色使用问题',
                max_items=5,
            ))
        if self.brand_result.font_issues:
            lines.append(_format_issue_list(
                self.brand_result.font_issues,
                '字体使用问题',
                max_items=5,
            ))
        if self.brand_result.non_brand_colors:
            lines.append(f'  非品牌色: {", ".join(sorted(self.brand_result.non_brand_colors)[:10])}')
        if not self.brand_result.issue_count:
            lines.append('  ✓ 未发现品牌一致性问题')
        lines.append('')

        # 名片设计
        lines.append('  ── 名片设计详情 ──')
        lines.append(f'    结构评分: {self.card_score.structure_score}/100')
        lines.append(f'    字段覆盖评分: {self.card_score.field_coverage_score}/100')
        lines.append(f'    组件架构评分: {self.card_score.component_score}/100')
        lines.append(f'    主题使用评分: {self.card_score.theme_score}/100')

        if self.card_score.missing_components:
            lines.append(f'    缺失组件: {", ".join(self.card_score.missing_components)}')
        if self.card_score.recommendations:
            lines.append('    改进建议:')
            for rec in self.card_score.recommendations[:5]:
                lines.append(f'      💡 {rec}')
        lines.append('')

        # 总结
        lines.append(sep)
        lines.append(f'  总结: {self._generate_summary_text(overall, ui_score, brand_score, card_score)}')
        lines.append(sep)

        return '\n'.join(lines)

    def _generate_markdown_report(self) -> str:
        """生成 Markdown 格式报告"""
        overall = self._calculate_overall_score()
        ui_score = self.ui_result.score
        brand_score = self.brand_result.score
        card_score = self.card_score.overall_score

        lines: list[str] = []
        lines.append(f'# {self.project_name} 审美评估报告')
        lines.append('')
        lines.append(f'> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append('')

        # 总体评分
        lines.append(f'## 📊 综合评分: {overall}/100 ({_score_to_grade(overall)})')
        lines.append('')

        # 各维度
        lines.append('| 维度 | 分数 | 等级 |')
        lines.append('|------|------|------|')
        lines.append(f'| UI一致性 | {ui_score}/100 | {_score_to_grade(ui_score)} |')
        lines.append(f'| 品牌一致性 | {brand_score}/100 | {_score_to_grade(brand_score)} |')
        lines.append(f'| 名片设计 | {card_score}/100 | {_score_to_grade(card_score)} |')
        lines.append('')

        # 名片子维度
        lines.append('### 名片设计子维度')
        lines.append('')
        lines.append('| 指标 | 分数 |')
        lines.append('|------|------|')
        lines.append(f'| 页面结构 | {self.card_score.structure_score}/100 |')
        lines.append(f'| 字段覆盖 | {self.card_score.field_coverage_score}/100 |')
        lines.append(f'| 组件架构 | {self.card_score.component_score}/100 |')
        lines.append(f'| 主题使用 | {self.card_score.theme_score}/100 |')
        lines.append('')

        # 统计
        lines.append('### 统计概要')
        lines.append('')
        lines.append(f'- 检查文件: {self.ui_result.total_files_checked} 个')
        lines.append(f'- 颜色品牌一致率: {self.brand_result.brand_alignment_ratio:.1%}')
        lines.append(f'- 总问题数: {self.ui_result.issue_count + self.brand_result.issue_count} 个')
        lines.append('')

        # 问题清单
        if self.ui_result.issue_count > 0 or self.brand_result.issue_count > 0:
            lines.append('### ⚠️ 发现的问题')
            lines.append('')

            if self.ui_result.component_naming_issues:
                lines.append('#### 组件命名问题')
                for issue in self.ui_result.component_naming_issues[:5]:
                    lines.append(f'- `{issue.file_path}`: {issue.description}')
                lines.append('')

            if self.ui_result.style_inconsistencies:
                lines.append('#### 样式不一致')
                for issue in self.ui_result.style_inconsistencies[:5]:
                    lines.append(f'- `{issue.file_path}` ({issue.location}): {issue.description}')
                lines.append('')

            if self.brand_result.color_issues:
                lines.append('#### 非品牌色使用')
                colors_str = ', '.join(sorted(self.brand_result.non_brand_colors)[:10])
                lines.append(f'- 非品牌色: `{colors_str}`')
                lines.append('')

        # 建议
        if self.card_score.recommendations:
            lines.append('### 💡 改进建议')
            lines.append('')
            for rec in self.card_score.recommendations:
                lines.append(f'- {rec}')
            lines.append('')

        # 总结
        lines.append('---')
        lines.append('')
        lines.append(f'**总结**: {self._generate_summary_text(overall, ui_score, brand_score, card_score)}')
        lines.append('')

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def generate(
        self,
        fmt: ReportFormat = ReportFormat.TEXT,
    ) -> Any:
        """
        生成评估报告

        Args:
            fmt: 报告格式（dict / text / markdown）

        Returns:
            根据 fmt 不同返回 dict 或 str
        """
        logger.info("生成评估报告（格式: %s）", fmt.value)

        if fmt == ReportFormat.DICT:
            return self._summary_dict()
        elif fmt == ReportFormat.MARKDOWN:
            return self._generate_markdown_report()
        else:
            return self._generate_text_report()

    def generate_json(self, indent: int = 2) -> str:
        """
        生成 JSON 格式报告

        Args:
            indent: JSON 缩进空格数

        Returns:
            JSON 字符串
        """
        data = self._summary_dict()
        return json.dumps(data, ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# 便捷入口
# ---------------------------------------------------------------------------


def generate_review_report(
    ui_result: Optional[UiCheckResult] = None,
    brand_result: Optional[BrandCheckResult] = None,
    card_score: Optional[CardDesignScore] = None,
    fmt: str = 'text',
) -> Any:
    """
    快速生成审美评估报告

    Args:
        ui_result: UI一致性检查结果
        brand_result: 品牌一致性检查结果
        card_score: 名片设计评分
        fmt: 格式 ('dict', 'text', 'markdown', 'json')

    Returns:
        报告内容
    """
    generator = ReviewReportGenerator(
        ui_result=ui_result,
        brand_result=brand_result,
        card_score=card_score,
    )

    if fmt == 'json':
        return generator.generate_json()

    try:
        report_fmt = ReportFormat(fmt)
    except ValueError:
        logger.warning("不支持的格式 '%s'，使用 text", fmt)
        report_fmt = ReportFormat.TEXT

    return generator.generate(fmt=report_fmt)
