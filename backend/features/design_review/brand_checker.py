"""
链客宝 - 品牌一致性检查器
=========================
对前端组件代码进行静态分析，检查品牌元素的⼀致性：
1. 颜色使用一致性（Tailwind 颜色类与品牌色对比）
2. 字体使用一致性（字体类名和字重使用）
3. 间距一致性（padding/margin/gap 模式）

所有分析基于代码层面的正则匹配，不做AI视觉识别。
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 链客宝品牌色定义（预期值）
# ---------------------------------------------------------------------------

# 品牌主色调 - 预期使用的 Tailwind 颜色类
BRAND_PRIMARY_COLORS: set[str] = {
    'blue-600', 'blue-700', 'blue-50', 'blue-100',
    'purple-600', 'purple-700',
}

# 文本颜色预期
BRAND_TEXT_COLORS: set[str] = {
    'gray-800', 'gray-700', 'gray-600', 'gray-500', 'gray-400', 'gray-900',
}

# 背景颜色预期
BRAND_BG_COLORS: set[str] = {
    'gray-50', 'white', 'gray-100',
    'blue-50', 'blue-600',
}

# 边框颜色预期
BRAND_BORDER_COLORS: set[str] = {
    'gray-100', 'gray-200', 'gray-300', 'blue-100', 'blue-200',
}

# 状态颜色
BRAND_STATUS_COLORS: set[str] = {
    'red-50', 'red-600', 'red-500',
    'green-600', 'green-50',
    'amber-50', 'amber-100', 'amber-700',
}

# 完整的品牌色集合
BRAND_COLORS: set[str] = (
    BRAND_PRIMARY_COLORS | BRAND_TEXT_COLORS | BRAND_BG_COLORS
    | BRAND_BORDER_COLORS | BRAND_STATUS_COLORS
)

# 品牌字体定义
BRAND_FONT_SIZES: set[str] = {
    'text-xs', 'text-sm', 'text-base', 'text-lg',
    'text-xl', 'text-2xl', 'text-3xl',
}
BRAND_FONT_WEIGHTS: set[str] = {
    'font-normal', 'font-medium', 'font-semibold', 'font-bold',
}

# 品牌间距模式（常用的 Tailwind 间距值）
BRAND_SPACING_PATTERNS: set[str] = {
    '1', '1.5', '2', '2.5', '3', '3.5', '4', '5', '6', '8', '10',
}


# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# 匹配 className 内容
RE_CLASSNAME = re.compile(
    r'className\s*=\s*["\'`]([^"\'`]*)["\'`]'
)

# 匹配具体颜色类
RE_COLOR_USAGE = re.compile(
    r'\b((?:text|bg|border|ring|outline|from|via|to|divide|placeholder|shadow|ring-offset)-(?:[a-z]+-\d{2,5}|white|black|transparent|current))\b'
)

# 匹配字体类
RE_FONT_CLASS = re.compile(
    r'\b(text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl))\b'
    r'|'
    r'\b(font-(?:thin|extralight|light|normal|medium|semibold|bold|extrabold|black))\b'
)

# 匹配间距类
RE_SPACING = re.compile(
    r'\b((?:p|px|py|pl|pr|pt|pb|m|mx|my|ml|mr|mt|mb|gap|gapx|gapy|space-x|space-y)-(?:0|0\.5|1|1\.5|2|2\.5|3|3\.5|4|5|6|7|8|9|10|11|12|14|16|20|24|28|32|36|40|44|48|52|56|60|64|72|80|96|px))\b'
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ColorUsageIssue:
    """颜色使用问题"""
    file_path: str
    location: str
    color_class: str
    color_category: str  # 'primary' | 'text' | 'bg' | 'border' | 'unknown'
    is_brand_aligned: bool
    description: str
    suggested_fix: str = ''
    severity: str = 'warning'


@dataclass
class FontUsageIssue:
    """字体使用问题"""
    file_path: str
    location: str
    font_class: str
    description: str
    severity: str = 'info'


@dataclass
class SpacingInconsistency:
    """间距不一致问题"""
    file_path: str
    location: str
    spacing_value: str
    context: str
    description: str
    severity: str = 'info'


@dataclass
class BrandCheckResult:
    """品牌一致性检查结果"""
    total_files_checked: int = 0
    color_issues: list[ColorUsageIssue] = field(default_factory=list)
    font_issues: list[FontUsageIssue] = field(default_factory=list)
    spacing_issues: list[SpacingInconsistency] = field(default_factory=list)

    # 统计
    color_usage_count: Counter[str] = field(default_factory=Counter)  # 颜色类 => 使用次数
    font_usage_count: Counter[str] = field(default_factory=Counter)   # 字体类 => 使用次数
    spacing_usage_count: Counter[str] = field(default_factory=Counter)  # 间距类 => 使用次数

    brand_alignment_ratio: float = 0.0  # 品牌一致率 (0~1)
    non_brand_colors: set[str] = field(default_factory=set)

    @property
    def score(self) -> int:
        """
        计算品牌一致性得分（0-100）

        基于:
        - 品牌色一致率（权重 50%）
        - 非品牌色数量（每个扣 2 分）
        - 字体使用规范（每个问题扣 5 分）
        """
        base = 100

        # 颜色一致率得分
        base = int(base * (0.5 + 0.5 * self.brand_alignment_ratio))

        # 扣分
        base -= len(self.non_brand_colors) * 2
        base -= len(self.font_issues) * 5
        base -= len(self.spacing_issues) * 2

        return max(0, min(100, base))

    @property
    def issue_count(self) -> int:
        return len(self.color_issues) + len(self.font_issues) + len(self.spacing_issues)


# ---------------------------------------------------------------------------
# 品牌一致性检查器
# ---------------------------------------------------------------------------


class BrandConsistencyChecker:
    """
    品牌一致性检查器

    分析前端代码中的 Tailwind 类使用情况，对比品牌定义的颜色、
    字体和间距规范，发现不一致之处。

    使用方式:
        checker = BrandConsistencyChecker(source_dir="src/")
        result = checker.check()
        print(f"品牌一致率: {result.brand_alignment_ratio:.1%}")
        print(f"得分: {result.score}")
    """

    def __init__(
        self,
        source_dir: str = "src/",
        brand_colors: Optional[set[str]] = None,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
    ) -> None:
        """
        初始化品牌一致性检查器

        Args:
            source_dir: 前端源码根目录
            brand_colors: 自定义品牌色集合（覆盖默认）
            include_patterns: 文件包含模式
            exclude_patterns: 文件排除模式
        """
        self.source_dir = Path(source_dir)
        self.brand_colors = brand_colors or BRAND_COLORS
        self.include_patterns = include_patterns or ['*.tsx', '*.ts', '*.jsx', '*.js']
        self.exclude_patterns = exclude_patterns or ['node_modules/', '.next/', 'dist/', '.git/']

        if not self.source_dir.exists():
            logger.warning("源目录不存在: %s", self.source_dir)

    def _should_include(self, file_path: Path) -> bool:
        """判断文件是否应包括在检查中"""
        rel = str(file_path.as_posix())
        for pattern in self.exclude_patterns:
            if pattern in rel:
                return False
        return file_path.suffix in {'.tsx', '.ts', '.jsx', '.js'}

    def _get_source_files(self) -> list[Path]:
        """递归获取所有源代码文件"""
        if not self.source_dir.exists():
            return []
        files: list[Path] = []
        for ext in ['.tsx', '.ts', '.jsx', '.js']:
            files.extend(self.source_dir.rglob(f'*{ext}'))
        return [f for f in files if self._should_include(f)]

    def _extract_class_names(self, content: str) -> list[str]:
        """从文件中提取所有 className 值"""
        classes: list[str] = []
        for match in RE_CLASSNAME.finditer(content):
            class_str = match.group(1)
            classes.extend(class_str.split())
        return classes

    def _check_colors(
        self,
        file_path: Path,
        classes: list[str],
    ) -> tuple[list[ColorUsageIssue], Counter[str], set[str]]:
        """
        检查颜色使用一致性

        Args:
            file_path: 文件路径
            classes: 提取的类名列表

        Returns:
            (颜色问题列表, 颜色使用统计, 非品牌色集合)
        """
        issues: list[ColorUsageIssue] = []
        color_counter: Counter[str] = Counter()
        non_brand: set[str] = set()

        lines = []
        try:
            lines = file_path.read_text(encoding='utf-8', errors='ignore').split('\n')
        except Exception:
            pass

        for cls in classes:
            color_match = RE_COLOR_USAGE.search(cls)
            if not color_match:
                continue

            full_class = color_match.group(1)
            color_counter[full_class] += 1

            # 提取颜色部分（去掉前缀）
            parts = full_class.split('-', 1)
            if len(parts) < 2:
                continue

            prefix = parts[0]
            color_value = parts[1]

            # 判断颜色分类
            if color_value in ('white', 'black', 'transparent', 'current'):
                continue

            # 比较颜色值（去掉前缀后再对比品牌色表）
            is_brand = color_value in self.brand_colors
            if not is_brand:
                non_brand.add(color_value)

            # 如果是非品牌色，记录
            if not is_brand:
                # 尝试确定位置
                location = '未知'
                for i, line in enumerate(lines, 1):
                    if cls in line and full_class in line:
                        location = f'第 {i} 行'
                        break

                issues.append(ColorUsageIssue(
                    file_path=str(file_path),
                    location=location,
                    color_class=full_class,
                    color_category=prefix,
                    is_brand_aligned=False,
                    description=f'使用非品牌色: {full_class} (颜色值: {color_value})',
                    suggested_fix=f'考虑替换为品牌色系中的对应值: {sorted(BRAND_PRIMARY_COLORS)[:3]}',
                    severity='info',
                ))

        return issues, color_counter, non_brand

    def _check_fonts(
        self,
        file_path: Path,
        classes: list[str],
    ) -> tuple[list[FontUsageIssue], Counter[str]]:
        """
        检查字体使用情况

        Args:
            file_path: 文件路径
            classes: 提取的类名列表

        Returns:
            字体问题列表和统计
        """
        issues: list[FontUsageIssue] = []
        font_counter: Counter[str] = Counter()

        lines = []
        try:
            lines = file_path.read_text(encoding='utf-8', errors='ignore').split('\n')
        except Exception:
            pass

        for cls in classes:
            font_match = RE_FONT_CLASS.search(cls)
            if not font_match:
                continue

            font_class = font_match.group(0)
            font_counter[font_class] += 1

            # 检查是否使用了非品牌字体大小
            if font_class.startswith('text-') and font_class not in BRAND_FONT_SIZES:
                location = '未知'
                for i, line in enumerate(lines, 1):
                    if font_class in line:
                        location = f'第 {i} 行'
                        break

                issues.append(FontUsageIssue(
                    file_path=str(file_path),
                    location=location,
                    font_class=font_class,
                    description=f'使用了非品牌字体大小: {font_class}（推荐: xs/sm/base/lg/xl/2xl/3xl）',
                    severity='info',
                ))

            # 检查是否使用了非品牌字重
            if font_class.startswith('font-') and font_class not in BRAND_FONT_WEIGHTS:
                location = '未知'
                for i, line in enumerate(lines, 1):
                    if font_class in line:
                        location = f'第 {i} 行'
                        break

                issues.append(FontUsageIssue(
                    file_path=str(file_path),
                    location=location,
                    font_class=font_class,
                    description=f'使用了非品牌字重: {font_class}（推荐: normal/medium/semibold/bold）',
                    severity='info',
                ))

        return issues, font_counter

    def _check_spacing(
        self,
        file_path: Path,
        classes: list[str],
    ) -> tuple[list[SpacingInconsistency], Counter[str]]:
        """
        检查间距使用情况

        Args:
            file_path: 文件路径
            classes: 提取的类名列表

        Returns:
            间距问题列表和统计
        """
        issues: list[SpacingInconsistency] = []
        spacing_counter: Counter[str] = Counter()

        lines = []
        try:
            lines = file_path.read_text(encoding='utf-8', errors='ignore').split('\n')
        except Exception:
            pass

        for cls in classes:
            spacing_match = RE_SPACING.search(cls)
            if not spacing_match:
                continue

            full_class = spacing_match.group(1)
            spacing_counter[full_class] += 1

            # 提取间距值
            parts = full_class.rsplit('-', 1)
            if len(parts) != 2:
                continue

            value = parts[1]

            # 标记不常用的间距值
            if value not in BRAND_SPACING_PATTERNS and value not in ('0', 'px'):
                location = '未知'
                for i, line in enumerate(lines, 1):
                    if full_class in line:
                        location = f'第 {i} 行'
                        break

                issues.append(SpacingInconsistency(
                    file_path=str(file_path),
                    location=location,
                    spacing_value=value,
                    context=full_class,
                    description=(
                        f'间距值 "{value}" 不属于常用间距模式'
                        f'（{", ".join(sorted(BRAND_SPACING_PATTERNS, key=lambda x: float(x)))}）'
                    ),
                    severity='info',
                ))

        return issues, spacing_counter

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def check(self) -> BrandCheckResult:
        """
        执行完整的品牌一致性检查

        分析所有源代码文件，检查颜色、字体和间距的品牌一致性。

        Returns:
            品牌一致性检查结果
        """
        result = BrandCheckResult()
        files = self._get_source_files()
        result.total_files_checked = len(files)

        if not files:
            logger.warning("未找到任何源代码文件（路径: %s）", self.source_dir)
            return result

        logger.info("开始品牌一致性检查，共 %d 个文件", len(files))

        total_color_classes = 0
        brand_aligned_count = 0

        for file_path in files:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                logger.debug("读取文件失败 %s: %s", file_path, e)
                continue

            classes = self._extract_class_names(content)
            if not classes:
                continue

            # 颜色检查
            color_issues, color_counter, non_brand = self._check_colors(
                file_path, classes
            )
            result.color_issues.extend(color_issues)
            result.color_usage_count.update(color_counter)
            result.non_brand_colors.update(non_brand)

            # 统计颜色品牌一致率（去掉前缀再比较）
            for cls, count in color_counter.items():
                total_color_classes += count
                # 去掉颜色类前缀（如 "text-", "bg-", "border-"），只比较颜色值
                color_parts = cls.split('-', 1)
                color_value_only = color_parts[1] if len(color_parts) > 1 else cls
                if color_value_only in self.brand_colors:
                    brand_aligned_count += count

            # 字体检查
            font_issues, font_counter = self._check_fonts(file_path, classes)
            result.font_issues.extend(font_issues)
            result.font_usage_count.update(font_counter)

            # 间距检查
            spacing_issues, spacing_counter = self._check_spacing(file_path, classes)
            result.spacing_issues.extend(spacing_issues)
            result.spacing_usage_count.update(spacing_counter)

        # 计算品牌一致率
        result.brand_alignment_ratio = (
            brand_aligned_count / total_color_classes
            if total_color_classes > 0
            else 1.0
        )

        logger.info(
            "品牌一致性检查完成: 得分 %d, 颜色一致率 %.1f%%, 问题 %d 个",
            result.score,
            result.brand_alignment_ratio * 100,
            result.issue_count,
        )

        return result

    @staticmethod
    def get_brand_color_summary(usage_count: Counter[str]) -> dict[str, dict]:
        """
        生成品牌色使用摘要

        Args:
            usage_count: 颜色使用统计 Counter

        Returns:
            按颜色分类的摘要 dict
        """
        summary: dict[str, dict] = {}
        for color, count in usage_count.most_common():
            prefix = color.split('-')[0]
            if prefix not in summary:
                summary[prefix] = {'total': 0, 'details': {}}
            summary[prefix]['total'] += count
            summary[prefix]['details'][color] = count
        return summary
