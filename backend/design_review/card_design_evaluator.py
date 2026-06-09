"""
链客宝 - 名片设计评估器
========================
对 business-card 相关组件和页面进行静态分析，评估：
1. 名片页面结构合理性（Step 流程完整性）
2. 字段覆盖度（标准名片字段是否齐全）
3. 主题使用情况（modern/classic/minimal 主题一致性）
4. 组件解耦度（组件是否可复用、职责单一）

所有分析基于代码层面的静态扫描，不做AI视觉识别。
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 名片设计规范
# ---------------------------------------------------------------------------

# 标准名片字段（期望在字段类型定义中出现）
EXPECTED_CARD_FIELDS: set[str] = {
    'name', 'position', 'company',
    'phone', 'email', 'wechat',
    'address', 'website',
}

# 相册页面类型（期望在枚举中出现）
EXPECTED_ALBUM_PAGE_TYPES: set[str] = {
    'cover', 'contact', 'company', 'qrcode',
}

# 主题
EXPECTED_THEMES: set[str] = {
    'modern', 'classic', 'minimal',
}

# Step 流程
EXPECTED_STEPS: list[str] = ['upload', 'review', 'preview', 'matched']

# UI 组件期望（每个名片页面子组件）
EXPECTED_CARD_COMPONENTS: set[str] = {
    'UploadZone', 'ReviewForm', 'FlipBook',
    'CommonConnections', 'ShareActions',
    'MatchResultsPanel', 'QRCodeModal', 'StepIndicator',
    'AlbumPageContent', 'FieldInput',
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class CardAlbumStructure:
    """名片相册结构分析"""
    page_types_found: set[str] = field(default_factory=set)
    page_types_missing: set[str] = field(default_factory=set)
    structure_score: int = 100

    @property
    def page_type_count(self) -> int:
        return len(self.page_types_found)


@dataclass
class CardFieldCoverage:
    """名片字段覆盖率"""
    fields_found: set[str] = field(default_factory=set)
    fields_missing: set[str] = field(default_factory=set)
    coverage_ratio: float = 0.0
    field_score: int = 0


@dataclass
class ThemeUsage:
    """主题使用分析"""
    themes_found: set[str] = field(default_factory=set)
    theme_consistency: bool = True
    issues: list[str] = field(default_factory=list)


@dataclass
class CardDesignScore:
    """名片设计评分"""
    overall_score: int = 0
    structure_score: int = 0       # 页面结构分
    field_coverage_score: int = 0  # 字段覆盖分
    component_score: int = 0       # 组件架构分
    theme_score: int = 0           # 主题使用分

    structure: Optional[CardAlbumStructure] = None
    field_coverage: Optional[CardFieldCoverage] = None
    theme_usage: Optional[ThemeUsage] = None

    missing_components: list[str] = field(default_factory=list)
    extra_components_found: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 名片设计评估器
# ---------------------------------------------------------------------------


class CardDesignEvaluator:
    """
    名片设计评估器

    对业务卡片（business-card）组件进行静态代码分析，
    评估设计质量、字段覆盖度和组件结构合理性。

    使用方式:
        evaluator = CardDesignEvaluator(card_dir="src/pages/business-card/")
        score = evaluator.evaluate()
        print(f"名片设计评分: {score.overall_score}")
    """

    def __init__(
        self,
        card_dir: str = "src/pages/business-card/",
        components_dir: str = "src/components/",
    ) -> None:
        """
        初始化名片设计评估器

        Args:
            card_dir: 名片页面目录
            components_dir: 通用组件目录
        """
        self.card_dir = Path(card_dir)
        self.components_dir = Path(components_dir)

        if not self.card_dir.exists():
            logger.warning("名片目录不存在: %s", self.card_dir)
        if not self.components_dir.exists():
            logger.warning("组件目录不存在: %s", self.components_dir)

    def _read_file_safe(self, path: Path) -> str:
        """安全地读取文件内容"""
        try:
            return path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.debug("读取文件失败 %s: %s", path, e)
            return ''

    def _analyze_page_structure(self) -> CardAlbumStructure:
        """
        分析名片页面结构

        检查 types.ts 中是否有预期的相册页面类型定义。

        Returns:
            相册结构分析结果
        """
        structure = CardAlbumStructure()

        # 检查 types.ts
        types_file = self.card_dir / 'types.ts'
        if types_file.exists():
            content = self._read_file_safe(types_file)
            found_page_types: set[str] = set()

            # 查找 AlbumPage type 定义
            type_pattern = re.compile(r"type\s*:\s*['\"]([^'\"]+)['\"]")
            for match in type_pattern.finditer(content):
                val = match.group(1)
                if val in EXPECTED_ALBUM_PAGE_TYPES:
                    found_page_types.add(val)

            # 查找 type 字面量
            literal_pattern = re.compile(r"['\"](?:cover|contact|company|qrcode)['\"]")
            for match in literal_pattern.finditer(content):
                val = match.group(0).strip("'\"")
                found_page_types.add(val)

            structure.page_types_found = found_page_types
            structure.page_types_missing = EXPECTED_ALBUM_PAGE_TYPES - found_page_types

            missing_count = len(structure.page_types_missing)
            structure.structure_score = max(0, 100 - missing_count * 25)
        else:
            structure.page_types_missing = EXPECTED_ALBUM_PAGE_TYPES.copy()
            structure.structure_score = 0

        return structure

    def _analyze_field_coverage(self) -> CardFieldCoverage:
        """
        分析名片字段覆盖率

        检查 types.ts 中 CardFields 接口定义的字段。

        Returns:
            字段覆盖率分析结果
        """
        coverage = CardFieldCoverage()

        types_file = self.card_dir / 'types.ts'
        if types_file.exists():
            content = self._read_file_safe(types_file)

            found_fields: set[str] = set()
            # 匹配接口中的字段定义
            field_pattern = re.compile(r'(\w+)\s*[:?]\s*(?:string|number|boolean)')
            for match in field_pattern.finditer(content):
                field_name = match.group(1)
                if field_name in EXPECTED_CARD_FIELDS:
                    found_fields.add(field_name)

            coverage.fields_found = found_fields
            coverage.fields_missing = EXPECTED_CARD_FIELDS - found_fields
            coverage.coverage_ratio = (
                len(found_fields) / len(EXPECTED_CARD_FIELDS)
                if EXPECTED_CARD_FIELDS
                else 0.0
            )
            coverage.field_score = int(coverage.coverage_ratio * 100)
        else:
            coverage.fields_missing = EXPECTED_CARD_FIELDS.copy()
            coverage.coverage_ratio = 0.0
            coverage.field_score = 0

        return coverage

    def _analyze_themes(self) -> ThemeUsage:
        """
        分析主题使用情况

        检查 types.ts 中是否有 theme 字段和相关枚举，以及
        各组件中主题的引用方式。

        Returns:
            主题使用分析结果
        """
        theme = ThemeUsage()
        theme_issues: list[str] = []

        # 检查 types.ts 中的主题定义
        types_file = self.card_dir / 'types.ts'
        if types_file.exists():
            content = self._read_file_safe(types_file)

            # 查找主题枚举或字面量
            for expected in EXPECTED_THEMES:
                if expected in content:
                    theme.themes_found.add(expected)

            # 检查是否有 theme 字段
            if 'theme' not in content:
                theme_issues.append('types.ts 中未定义 theme 字段')

        # 检查页面文件中主题的使用
        page_file = self.card_dir / 'BusinessCardPage.tsx'
        if page_file.exists():
            content = self._read_file_safe(page_file)
            if 'theme' not in content and 'album_meta' not in content:
                theme_issues.append('页面组件未引用 theme 或 album_meta')

        if theme_issues:
            theme.theme_consistency = False
            theme.issues = theme_issues

        return theme

    def _analyze_components(self) -> tuple[list[str], list[str], list[str]]:
        """
        分析使用组件情况

        检查 BusinessCardPage.tsx 中 import 的子组件，
        以及子组件目录下的实际文件列表。

        Returns:
            (缺失组件, 额外组件, 警告信息)
        """
        missing: list[str] = []
        extra: list[str] = []
        warnings: list[str] = []

        # 获取所有已存在的子组件
        card_components_dir = self.card_dir / 'components'
        existing_components: set[str] = set()

        if card_components_dir.exists():
            tsx_files = list(card_components_dir.glob('*.tsx'))
            for f in tsx_files:
                # 去掉后缀
                existing_components.add(f.stem)

        # 检查期望组件
        for comp in EXPECTED_CARD_COMPONENTS:
            if comp not in existing_components:
                # 可能是导入但文件名不同的情况，检查 import
                missing.append(comp)

        # 检查期望组件的导入
        page_file = self.card_dir / 'BusinessCardPage.tsx'
        if page_file.exists():
            content = self._read_file_safe(page_file)
            import_pattern = re.compile(r"import\s+(?:\w+\s*,\s*)?\{?\s*(\w+)\s*\}?\s+from")
            imported_names: set[str] = set()
            for match in import_pattern.finditer(content):
                imported_names.add(match.group(1))

            # 标记明确缺失的组件（既不在目录中，也未导入）
            missing = [
                c for c in EXPECTED_CARD_COMPONENTS
                if c not in existing_components and c not in imported_names
            ]
        else:
            missing = list(EXPECTED_CARD_COMPONENTS)
            warnings.append('BusinessCardPage.tsx 不存在')

        # 记录额外组件（存在于目录中但不在期望列表中）
        extra = list(existing_components - EXPECTED_CARD_COMPONENTS)

        return missing, extra, warnings

    def _generate_recommendations(
        self,
        structure: CardAlbumStructure,
        coverage: CardFieldCoverage,
        theme: ThemeUsage,
        missing_components: list[str],
    ) -> list[str]:
        """生成改进建议"""
        recommendations: list[str] = []

        if structure.page_types_missing:
            recommendations.append(
                f'相册缺少页面类型: {", ".join(structure.page_types_missing)}'
            )

        if coverage.fields_missing:
            recommendations.append(
                f'标准名片字段缺失: {", ".join(coverage.fields_missing)}'
            )

        if not theme.theme_consistency:
            recommendations.append(
                '主题使用不一致，建议统一使用 AlbumMeta 中的 theme 字段'
            )

        if missing_components:
            recommendations.append(
                f'缺少以下预期组件: {", ".join(missing_components)}'
            )

        if not recommendations:
            recommendations.append('名片设计整体良好，建议持续关注组件复用性')

        return recommendations

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def evaluate(self) -> CardDesignScore:
        """
        执行名片设计评估

        分析 business-card 页面目录和组件，从结构、字段覆盖、
        组件架构和主题使用四个维度评分。

        Returns:
            名片设计评分
        """
        score = CardDesignScore()

        if not self.card_dir.exists():
            logger.error("名片目录不存在: %s", self.card_dir)
            score.warnings.append(f'名片目录不存在: {self.card_dir}')
            score.overall_score = 0
            return score

        logger.info("开始名片设计评估: %s", self.card_dir)

        # 1. 页面结构分析
        structure = self._analyze_page_structure()
        score.structure = structure
        score.structure_score = structure.structure_score
        logger.debug("页面结构得分: %d", structure.structure_score)

        # 2. 字段覆盖分析
        field_coverage = self._analyze_field_coverage()
        score.field_coverage = field_coverage
        score.field_coverage_score = field_coverage.field_score
        logger.debug("字段覆盖得分: %d (%.1f%%)", field_coverage.field_score, field_coverage.coverage_ratio * 100)

        # 3. 主题使用分析
        theme_usage = self._analyze_themes()
        score.theme_usage = theme_usage
        score.theme_score = 100 if theme_usage.theme_consistency else 60
        if not theme_usage.theme_consistency:
            score.warnings.extend(theme_usage.issues)
        logger.debug("主题使用得分: %d", score.theme_score)

        # 4. 组件分析
        missing, extra, warnings = self._analyze_components()
        score.missing_components = missing
        score.extra_components_found = extra
        score.warnings.extend(warnings)
        score.component_score = max(0, 100 - len(missing) * 15)
        logger.debug("组件架构得分: %d (缺失 %d 个组件)", score.component_score, len(missing))

        # 5. 总分计算（加权）
        score.overall_score = int(
            score.structure_score * 0.25
            + score.field_coverage_score * 0.30
            + score.component_score * 0.25
            + score.theme_score * 0.20
        )

        # 6. 建议
        score.recommendations = self._generate_recommendations(
            structure, field_coverage, theme_usage, missing
        )

        logger.info(
            "名片设计评估完成: 总分 %d (结构=%d, 字段=%d, 组件=%d, 主题=%d)",
            score.overall_score,
            score.structure_score,
            score.field_coverage_score,
            score.component_score,
            score.theme_score,
        )

        return score

    def evaluate_single_file(self, file_path: str) -> dict[str, Any]:
        """
        评估单个名片相关文件

        Args:
            file_path: 文件路径

        Returns:
            文件评估信息 dict
        """
        path = Path(file_path)
        if not path.exists():
            return {'error': f'文件不存在: {file_path}'}

        content = self._read_file_safe(path)
        info: dict[str, Any] = {
            'file': str(path),
            'size': len(content),
            'lines': content.count('\n') + 1,
        }

        # 检测类型定义
        if 'export interface' in content:
            interfaces = re.findall(r'export interface (\w+)', content)
            info['interfaces'] = interfaces

        # 检测组件定义
        components = re.findall(
            r'(?:export\s+default\s+function|export\s+default\s+const)\s+(\w+)',
            content,
        )
        if components:
            info['components'] = components

        # 检测字段定义
        fields = re.findall(r'(\w+)\s*[:?]\s*(string|number|boolean)', content)
        if fields:
            info['fields'] = [f[0] for f in fields]

        # 检测 import 的组件
        imports = re.findall(r"import\s+\{?\s*(\w+(?:\s*,\s*\w+)*)\s*\}?\s+from\s+['\"]\.", content)
        if imports:
            local_imports: list[str] = []
            for imp in imports:
                local_imports.extend(i.strip() for i in imp.split(','))
            info['local_imports'] = local_imports

        return info
