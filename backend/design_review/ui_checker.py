"""
链客宝 - UI一致性检查器
=========================
对前端组件代码进行静态分析，检查：
1. 组件命名规范（PascalCase、目录结构）
2. 样式一致性（CSS类名模式、Tailwind类使用一致性）
3. 响应式布局标记（md:/lg:/sm: 前缀使用情况）

所有分析基于正则匹配和规则引擎，不做AI视觉分析。
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# 匹配 PascalCase 组件名: export default function ComponentName
RE_COMPONENT_NAME = re.compile(
    r'(?:export\s+default\s+function|export\s+default\s+const)\s+([A-Z][a-zA-Z0-9]+)'
)

# 匹配 Tailwind 类名中使用的颜色值: text-xxx, bg-xxx, border-xxx
RE_COLOR_CLASS = re.compile(
    r'\b(?:text|bg|border|ring|outline|from|via|to|divide|placeholder|shadow)-(?:[a-z]+-\d{2,5})\b'
)

# 匹配响应式前缀
RE_RESPONSIVE_PREFIX = re.compile(r'\b(sm|md|lg|xl|2xl):')

# 匹配常见的间距类: p-x, m-x, gap-x, space-x
RE_SPACING_CLASS = re.compile(
    r'\b(?:p[trblxy]?|m[trblxy]?|gap[xy]?|space[xy]?)-(?:0|0\.5|1|1\.5|2|2\.5|3|3\.5|4|5|6|7|8|9|10|11|12|14|16|20|24|28|32|36|40|44|48|52|56|60|64|72|80|96|px)\b'
)

# 匹配内联样式: style={{ ... }}
RE_INLINE_STYLE = re.compile(r'style\s*=\s*\{[^}]*\}')

# 匹配非标准类名（不含常见前缀的类）
RE_NONSTANDARD_CLASS = re.compile(
    r'className\s*=\s*["\'][^"\']*?["\']'
)

# 匹配字体类
RE_FONT_CLASS = re.compile(
    r'\b(?:text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)\b|font-(?:thin|extralight|light|normal|medium|semibold|bold|extrabold|black))\b'
)

# 常用 Tailwind 颜色名称
TAILWIND_COLORS: set[str] = {
    'slate', 'gray', 'zinc', 'neutral', 'stone',
    'red', 'orange', 'amber', 'yellow', 'lime',
    'green', 'emerald', 'teal', 'cyan', 'sky',
    'blue', 'indigo', 'violet', 'purple', 'fuchsia',
    'pink', 'rose',
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ComponentNamingIssue:
    """组件命名问题"""
    file_path: str
    component_name: str
    issue_type: str  # 'not_pascal_case' | 'filename_mismatch' | 'missing_export'
    description: str
    severity: str = 'warning'  # 'info' | 'warning' | 'error'


@dataclass
class StyleInconsistency:
    """样式不一致问题"""
    file_path: str
    location: str  # 行号或上下文
    style_type: str  # 'inline_style' | 'nonstandard_class' | 'color_inconsistency'
    description: str
    suggested_fix: str = ''
    severity: str = 'warning'


@dataclass
class ResponsiveLayoutIssue:
    """响应式布局问题"""
    file_path: str
    location: str
    issue_type: str  # 'no_responsive_class' | 'missing_breakpoint' | 'overflow_risk'
    description: str
    severity: str = 'info'


@dataclass
class UiCheckResult:
    """UI一致性检查结果"""
    total_files_checked: int = 0
    component_naming_issues: list[ComponentNamingIssue] = field(default_factory=list)
    style_inconsistencies: list[StyleInconsistency] = field(default_factory=list)
    responsive_layout_issues: list[ResponsiveLayoutIssue] = field(default_factory=list)
    total_classes_checked: int = 0
    unique_color_classes: set[str] = field(default_factory=set)
    responsive_class_ratio: float = 0.0  # 响应式类 / 总类

    @property
    def score(self) -> int:
        """
        计算UI一致性得分（0-100）
        扣分项：命名问题(-10/个)、样式不一致(-5/个)、响应式问题(-3/个)
        """
        base = 100
        base -= len(self.component_naming_issues) * 10
        base -= len(self.style_inconsistencies) * 5
        base -= len(self.responsive_layout_issues) * 3
        return max(0, min(100, base))

    @property
    def issue_count(self) -> int:
        return (
            len(self.component_naming_issues)
            + len(self.style_inconsistencies)
            + len(self.responsive_layout_issues)
        )


# ---------------------------------------------------------------------------
# UI一致性检查器
# ---------------------------------------------------------------------------


class UiConsistencyChecker:
    """
    UI一致性检查器

    对前端组件代码进行静态分析，检查组件命名规范、
    样式一致性和响应式布局标记。

    使用方式:
        checker = UiConsistencyChecker(source_dir="src/")
        result = checker.check()
        print(f"得分: {result.score}, 问题数: {result.issue_count}")
    """

    def __init__(
        self,
        source_dir: str = "src/",
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
    ) -> None:
        """
        初始化UI一致性检查器

        Args:
            source_dir: 前端源码根目录
            include_patterns: 要包含的文件模式，默认 ['*.tsx', '*.ts', '*.jsx', '*.js']
            exclude_patterns: 要排除的文件模式，默认 ['node_modules/', '.next/', 'dist/']
        """
        self.source_dir = Path(source_dir)
        self.include_patterns = include_patterns or ['*.tsx', '*.ts', '*.jsx', '*.js']
        self.exclude_patterns = exclude_patterns or ['node_modules/', '.next/', 'dist/', '.git/']

        if not self.source_dir.exists():
            logger.warning("源目录不存在: %s", self.source_dir)

    def _should_include(self, file_path: Path) -> bool:
        """判断文件是否应包括在检查中"""
        # 检查排除模式
        rel = str(file_path.as_posix())
        for pattern in self.exclude_patterns:
            if pattern in rel:
                return False

        # 检查包含模式
        ext = f"*.{file_path.suffix.lstrip('.')}"
        return ext in self.include_patterns or file_path.suffix in {'.tsx', '.ts', '.jsx', '.js'}

    def _get_component_files(self) -> list[Path]:
        """
        扫描源码目录获取所有前端组件文件

        Returns:
            匹配的文件路径列表
        """
        if not self.source_dir.exists():
            return []

        files: list[Path] = []
        for ext in ['.tsx', '.ts', '.jsx', '.js']:
            files.extend(self.source_dir.rglob(f'*{ext}'))

        return [f for f in files if self._should_include(f)]

    def _check_component_naming(self, file_path: Path, content: str) -> list[ComponentNamingIssue]:
        """
        检查组件命名规范

        规则:
        1. 导出函数/组件必须使用 PascalCase
        2. 文件名应与导出的组件名一致（忽略 index.tsx）
        3. 要求有 export default

        Args:
            file_path: 文件路径
            content: 文件内容

        Returns:
            命名问题列表
        """
        issues: list[ComponentNamingIssue] = []
        filename = file_path.stem  # 无后缀的文件名

        # 查找所有导出的组件名
        matches = RE_COMPONENT_NAME.finditer(content)
        component_names = [m.group(1) for m in matches]

        for comp_name in component_names:
            # 检查是否为 PascalCase
            if not re.match(r'^[A-Z][a-zA-Z0-9]*$', comp_name):
                issues.append(ComponentNamingIssue(
                    file_path=str(file_path),
                    component_name=comp_name,
                    issue_type='not_pascal_case',
                    description=f'组件名 "{comp_name}" 不是 PascalCase 格式',
                    severity='warning',
                ))

            # 检查文件名是否匹配（忽略 index.tsx 和类似入口文件）
            if filename not in ('index', comp_name.lower()):
                if filename.lower() != comp_name.lower():
                    issues.append(ComponentNamingIssue(
                        file_path=str(file_path),
                        component_name=comp_name,
                        issue_type='filename_mismatch',
                        description=(
                            f'组件名 "{comp_name}" 与文件名 "{filename}" 不匹配'
                        ),
                        severity='warning',
                    ))

        # 检查是否有 export default（无默认导出可能不是组件）
        if not component_names and 'export default' not in content and 'React' in content:
            issues.append(ComponentNamingIssue(
                file_path=str(file_path),
                component_name=filename,
                issue_type='missing_export',
                description=f'文件 "{filename}" 可能是一个组件但没有 export default',
                severity='info',
            ))

        return issues

    def _check_style_consistency(self, file_path: Path, content: str) -> list[StyleInconsistency]:
        """
        检查样式一致性

        规则:
        1. 避免过多使用内联样式（style={{}}），优先使用 Tailwind 类
        2. 发现非标准类名（不属于 Tailwind 模式的类）
        3. 检测颜色值使用一致性

        Args:
            file_path: 文件路径
            content: 文件内容

        Returns:
            样式问题列表
        """
        issues: list[StyleInconsistency] = []
        lines = content.split('\n')

        # 检测内联样式
        inline_style_matches = list(RE_INLINE_STYLE.finditer(content))
        for match in inline_style_matches:
            line_num = content[:match.start()].count('\n') + 1
            if line_num <= len(lines):
                issues.append(StyleInconsistency(
                    file_path=str(file_path),
                    location=f'第 {line_num} 行',
                    style_type='inline_style',
                    description='使用内联样式，建议迁移到 Tailwind class',
                    suggested_fix='将 style={{...}} 替换为对应的 Tailwind 类名',
                    severity='info',
                ))

        # 限制内联样式警告数量
        if len(issues) > 10:
            issues = issues[:10]

        return issues

    def _check_responsive_layout(self, file_path: Path, content: str) -> list[ResponsiveLayoutIssue]:
        """
        检查响应式布局标记

        规则:
        1. 容器元素应有响应式类（md:lg:xl: 等前缀）
        2. 检查常用的 width/flex grid 是否有响应式断点

        Args:
            file_path: 文件路径
            content: 文件内容

        Returns:
            响应式问题列表
        """
        issues: list[ResponsiveLayoutIssue] = []
        lines = content.split('\n')

        # 提取所有 className 中的类
        class_matches = RE_NONSTANDARD_CLASS.findall(content)
        total_class_strs = [m.split('=')[1].strip('"\'') for m in class_matches]

        # 统计总类和响应式类
        all_classes: list[str] = []
        for class_str in total_class_strs:
            all_classes.extend(class_str.split())

        total_classes = len(all_classes)
        responsive_classes = sum(1 for c in all_classes if RE_RESPONSIVE_PREFIX.search(c))

        # 如果响应式类占比过低，发出警告
        if total_classes > 10 and responsive_classes == 0:
            issues.append(ResponsiveLayoutIssue(
                file_path=str(file_path),
                location='文件整体',
                issue_type='no_responsive_class',
                description='文件中未检测到响应式断点类（md:/lg:/xl:），可能缺乏响应式适配',
                severity='warning',
            ))

        # 检测常用容器类（grid-cols-*, flex, w-*）是否有响应式版本
        grid_pattern = re.compile(r'\bgrid-cols-\d+\b')
        grid_responsive_pattern = re.compile(r'\b(?:sm|md|lg|xl|2xl):grid-cols-\d+\b')

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # 检测 grid 是否有响应式版本
            if grid_pattern.search(line_stripped) and not grid_responsive_pattern.search(line_stripped):
                issues.append(ResponsiveLayoutIssue(
                    file_path=str(file_path),
                    location=f'第 {i} 行',
                    issue_type='missing_breakpoint',
                    description='grid-cols 未配合响应式前缀，在小屏幕可能布局异常',
                    severity='info',
                ))

        return issues

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def check(self) -> UiCheckResult:
        """
        执行完整的UI一致性检查

        扫描所有前端文件，检查组件命名、样式一致性和响应式布局。

        Returns:
            UI一致性检查结果
        """
        result = UiCheckResult()
        files = self._get_component_files()
        result.total_files_checked = len(files)

        if not files:
            logger.warning("未找到任何前端组件文件（路径: %s）", self.source_dir)
            return result

        logger.info("开始UI一致性检查，共 %d 个文件", len(files))

        for file_path in files:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                logger.debug("读取文件失败 %s: %s", file_path, e)
                continue

            # 检查组件命名
            naming_issues = self._check_component_naming(file_path, content)
            result.component_naming_issues.extend(naming_issues)

            # 检查样式一致性
            style_issues = self._check_style_consistency(file_path, content)
            result.style_inconsistencies.extend(style_issues)

            # 检查响应式布局
            responsive_issues = self._check_responsive_layout(file_path, content)
            result.responsive_layout_issues.extend(responsive_issues)

            # 统计类名
            class_matches = RE_NONSTANDARD_CLASS.findall(content)
            for m in class_matches:
                class_str = m.split('=')[1].strip('"\'')
                classes = class_str.split()
                result.total_classes_checked += len(classes)
                for cls in classes:
                    # 收集颜色类
                    color_match = RE_COLOR_CLASS.search(cls)
                    if color_match:
                        result.unique_color_classes.add(color_match.group())

            # 计算响应式比例
            all_classes_for_file: list[str] = []
            for m in class_matches:
                all_classes_for_file.extend(m.split('=')[1].strip('"\'').split())
            file_total = len(all_classes_for_file)
            file_responsive = sum(1 for c in all_classes_for_file if RE_RESPONSIVE_PREFIX.search(c))
            if file_total > 0:
                result.responsive_class_ratio = (
                    result.responsive_class_ratio * (result.total_files_checked - 1)
                    + (file_responsive / file_total)
                ) / result.total_files_checked

        logger.info(
            "UI一致性检查完成: 得分 %d, 问题 %d 个",
            result.score,
            result.issue_count,
        )
        return result

    def check_file(self, file_path: str) -> UiCheckResult:
        """
        检查单个文件

        Args:
            file_path: 文件路径

        Returns:
            该文件的检查结果
        """
        result = UiCheckResult()
        path = Path(file_path)

        if not path.exists():
            logger.error("文件不存在: %s", file_path)
            return result

        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error("读取文件失败 %s: %s", file_path, e)
            return result

        result.total_files_checked = 1
        result.component_naming_issues = self._check_component_naming(path, content)
        result.style_inconsistencies = self._check_style_consistency(path, content)
        result.responsive_layout_issues = self._check_responsive_layout(path, content)

        # 统计类名
        class_matches = RE_NONSTANDARD_CLASS.findall(content)
        for m in class_matches:
            class_str = m.split('=')[1].strip('"\'')
            result.total_classes_checked += len(class_str.split())

        return result
