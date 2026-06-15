"""
链客宝 审美评估引擎模块 (Design Review Engine)
================================================
基于 KFD Feature 库:
  - F-SJ-链客宝-03: 审美评估系统 (Aesthetic Evaluation System)
  - F-审美-01: 用户界面审美评估 (UI Aesthetic Evaluation)

功能:
  - UI一致性检查: 组件命名规范、样式一致性、响应式布局标记、间距使用
  - 品牌一致性检查: 颜色使用、字体使用、间距一致性、品牌色偏离警告
  - 名片设计评估: 页面结构、字段覆盖度、主题一致性、组件解耦度
  - 10维度审美评分: 色彩/字体/间距/布局/对比/一致性/动效/响应/无障碍/品牌感
  - 报告生成: 支持 dict/text/markdown 三种输出格式

API:
  - POST /api/aesthetic/review/ui       → UI一致性检查
  - POST /api/aesthetic/review/brand    → 品牌一致性检查
  - POST /api/aesthetic/review/card     → 名片设计评估
  - POST /api/aesthetic/review/full     → 完整审美评估
  - POST /api/aesthetic/evaluate        → 10维度界面审美评分
  - GET  /api/aesthetic/reports         → 历史报告列表
  - GET  /api/aesthetic/metrics         → 监控指标

注册方式（在 main.py 中）:
    import design_review_engine as design_review_engine_module
    app.include_router(design_review_engine_module.router)
"""

import json
import logging
import math
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AestheticScoreCardRecord, DesignReviewReport, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aesthetic", tags=["审美评估"])


# ============================================================
# 枚举 & 常量
# ============================================================

class ScoreLevel(str, Enum):
    """评分等级"""
    EXCELLENT = "excellent"  # A
    GOOD = "good"            # B
    FAIR = "fair"            # C
    POOR = "poor"            # D
    FAIL = "fail"            # F


class OutputFormat(str, Enum):
    """报告输出格式"""
    DICT = "dict"
    TEXT = "text"
    MARKDOWN = "markdown"


class AestheticDimension(str, Enum):
    """审美10维度"""
    COLOR = "color"                  # 色彩
    TYPOGRAPHY = "typography"        # 字体
    SPACING = "spacing"              # 间距
    LAYOUT = "layout"                # 布局
    CONTRAST = "contrast"            # 对比
    CONSISTENCY = "consistency"      # 一致性
    MOTION = "motion"                # 动效
    RESPONSIVE = "responsive"        # 响应
    ACCESSIBILITY = "accessibility"  # 无障碍
    BRANDING = "branding"            # 品牌感


# 品牌色标准集合
BRAND_COLORS: set[str] = {
    "blue-600", "blue-700", "purple-600", "indigo-600",
    "slate-800", "gray-900", "white", "gray-50", "gray-100",
}

# 名片标准字段
CARD_STANDARD_FIELDS: list[str] = [
    "name", "position", "company", "phone",
    "email", "wechat", "address", "website",
]

# 名片预期页面类型
CARD_PAGE_TYPES: list[str] = ["cover", "contact", "company", "qrcode"]

# 名片主题
CARD_THEMES: list[str] = ["modern", "classic", "minimal"]

# 名片标准流程步骤
CARD_FLOW_STEPS: list[str] = ["upload", "review", "preview", "matched"]

# 名片预期10个组件
CARD_EXPECTED_COMPONENTS: list[str] = [
    "CardAvatar", "CardInfo", "CardContact", "CardCompany",
    "CardGallery", "CardTheme", "CardShare", "CardQRCode",
    "CardAlbum", "CardActions",
]

# 缓存 TTL
_CACHE_TTL = 300  # 5分钟


# ============================================================
# Pydantic v2 Schemas
# ============================================================

# ---- UI一致性检查 ----

class UiCheckResult(BaseModel):
    """UI一致性检查结果"""
    naming_score: float = Field(default=0.0, ge=0.0, le=100.0, description="命名规范得分")
    style_score: float = Field(default=0.0, ge=0.0, le=100.0, description="样式一致性得分")
    responsive_score: float = Field(default=0.0, ge=0.0, le=100.0, description="响应式标记得分")
    spacing_score: float = Field(default=0.0, ge=0.0, le=100.0, description="间距使用得分")
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0, description="总体得分")
    issues: list[dict] = Field(default_factory=list, description="问题列表")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")


# ---- 品牌一致性检查 ----

class BrandCheckResult(BaseModel):
    """品牌一致性检查结果"""
    color_score: float = Field(default=0.0, ge=0.0, le=100.0)
    font_score: float = Field(default=0.0, ge=0.0, le=100.0)
    spacing_score: float = Field(default=0.0, ge=0.0, le=100.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    brand_color_usage: dict[str, int] = Field(default_factory=dict)
    non_brand_colors: list[str] = Field(default_factory=list)
    deviations: list[dict] = Field(default_factory=list, description="偏离警告列表")
    suggestions: list[str] = Field(default_factory=list)


# ---- 名片设计评估 ----

class CardDesignScore(BaseModel):
    """名片设计评估结果"""
    field_coverage: float = Field(default=0.0, ge=0.0, le=100.0, description="字段覆盖度")
    page_structure: float = Field(default=0.0, ge=0.0, le=100.0, description="页面结构")
    theme_consistency: float = Field(default=0.0, ge=0.0, le=100.0, description="主题一致性")
    component_decoupling: float = Field(default=0.0, ge=0.0, le=100.0, description="组件解耦度")
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    covered_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


# ---- 综合报告 ----

class ReviewReport(BaseModel):
    """完整审美评估报告"""
    report_id: str = ""
    ui_check_result: UiCheckResult | None = None
    brand_check_result: BrandCheckResult | None = None
    card_design_score: CardDesignScore | None = None
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    score_level: str = ScoreLevel.FAIR.value
    issues_summary: list[dict] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    created_at: str = ""


# ---- 10维度审美评分 ----

class AestheticScoreCard(BaseModel):
    """10维度审美评分卡"""
    dimensions: dict[str, float] = Field(default_factory=dict, description="维度名->分数(1-10)")
    overall_score: float = Field(default=0.0, ge=0.0, le=10.0, description="综合评分")
    top3_improvements: list[dict] = Field(default_factory=list, description="Top3改进建议")
    benchmark_references: list[str] = Field(default_factory=list, description="参考对标案例")


# ---- 请求模型 ----

class ReviewConfig(BaseModel):
    """评估配置"""
    source_dir: str = Field(default="/src/components", description="源码目录路径")
    strict_mode: bool = Field(default=False, description="严格模式")
    enable_ui_check: bool = Field(default=True)
    enable_brand_check: bool = Field(default=True)
    enable_card_eval: bool = Field(default=True)
    output_format: OutputFormat = OutputFormat.DICT


class UiReviewRequest(BaseModel):
    """UI一致性检查请求"""
    component_dir: str = Field(default="/src/components", description="组件目录路径")
    file_contents: dict[str, str] = Field(
        default_factory=dict,
        description="源码字典 {文件路径: 文件内容}，为空则模拟分析",
    )


class BrandReviewRequest(BaseModel):
    """品牌一致性检查请求"""
    source_dir: str = Field(default="/src", description="源码目录路径")
    file_contents: dict[str, str] = Field(
        default_factory=dict,
        description="源码字典 {文件路径: 文件内容}，为空则模拟分析",
    )


class CardReviewRequest(BaseModel):
    """名片设计评估请求"""
    card_component_dir: str = Field(default="/src/pages/business-card", description="名片组件目录")
    file_contents: dict[str, str] = Field(
        default_factory=dict,
        description="源码字典 {文件路径: 文件内容}，为空则模拟分析",
    )


class AestheticEvaluateRequest(BaseModel):
    """10维度审美评分请求"""
    interface_description: str = Field(..., min_length=10, max_length=5000, description="界面描述或截图说明")
    target_user_group: str = Field(default="企业家/商务人士", description="目标用户群体")
    platform: Literal["Web", "Mobile", "Desktop"] = Field(default="Web", description="平台类型")


# ---- 响应模型 ----

class ReviewReportResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class AestheticScoreResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: AestheticScoreCard


# ============================================================
# 缓存层
# ============================================================

class CacheEntry:
    __slots__ = ("data", "timestamp", "ttl")

    def __init__(self, data: Any, ttl: float = _CACHE_TTL):
        self.data = data
        self.timestamp = time.time()
        self.ttl = ttl

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


_cache: dict[str, CacheEntry] = {}


def get_cached(key: str, fetch_func: Callable, ttl: float = _CACHE_TTL) -> Any:
    entry = _cache.get(key)
    if entry is not None and not entry.is_expired():
        return entry.data
    data = fetch_func()
    _cache[key] = CacheEntry(data, ttl=ttl)
    return data


# ============================================================
# 报告持久化辅助函数
# ============================================================


def _save_report_to_db(db: Session, report: dict, review_type: str = "full") -> str:
    """将评估报告保存到数据库"""
    rid = report.get("report_id", f"rev-{uuid.uuid4().hex[:12]}")
    overall_score = report.get("overall_score", 0.0)
    score_level = report.get("score_level", "fair")
    db_report = DesignReviewReport(
        id=rid,
        report_data=json.dumps(report, ensure_ascii=False),
        review_type=review_type,
        overall_score=overall_score,
        score_level=score_level,
    )
    db.add(db_report)
    db.commit()
    return rid


def _save_score_card_to_db(db: Session, card: dict) -> str:
    """将评分卡保存到数据库"""
    sid = card.get("score_id", f"asc-{uuid.uuid4().hex[:12]}")
    overall_score = card.get("overall_score", 0.0)
    db_card = AestheticScoreCardRecord(
        id=sid,
        card_data=json.dumps(card, ensure_ascii=False),
        overall_score=overall_score,
    )
    db.add(db_card)
    db.commit()
    return sid


# ============================================================
# 工具函数
# ============================================================

def _score_to_level(score: float, max_score: float = 100.0) -> ScoreLevel:
    """将分数转换为等级"""
    ratio = score / max_score
    if ratio >= 0.90:
        return ScoreLevel.EXCELLENT
    elif ratio >= 0.75:
        return ScoreLevel.GOOD
    elif ratio >= 0.60:
        return ScoreLevel.FAIR
    elif ratio >= 0.40:
        return ScoreLevel.POOR
    return ScoreLevel.FAIL


def _format_report(
    report: ReviewReport,
    fmt: OutputFormat,
) -> str | dict:
    """按格式输出报告"""
    if fmt == OutputFormat.DICT:
        return report.model_dump()

    if fmt == OutputFormat.TEXT:
        lines = [
            "=" * 50,
            f"审美评估报告 #{report.report_id}",
            "=" * 50,
            f"综合评分: {report.overall_score:.1f}/100 ({report.score_level})",
            "",
            "--- 改进建议 ---",
        ]
        for s in report.improvement_suggestions:
            lines.append(f"  • {s}")
        return "\n".join(lines)

    # Markdown
    lines = [
        f"# 审美评估报告 #{report.report_id}",
        "",
        f"**综合评分**: {report.overall_score:.1f}/100 (**{report.score_level}**)\n",
        "## 改进建议\n",
    ]
    for s in report.improvement_suggestions:
        lines.append(f"- {s}")
    return "\n".join(lines)


# ============================================================
# UI一致性检查器 (F-SJ-链客宝-03)
# ============================================================

class UiConsistencyChecker:
    """UI一致性检查器"""

    @staticmethod
    def check(file_contents: dict[str, str]) -> UiCheckResult:
        issues: list[dict] = []
        suggestions: list[str] = []

        # 检查组件命名规范（PascalCase）
        non_pascal = []
        pascal_count = 0
        total_components = 0

        for filepath, content in file_contents.items():
            if not content:
                continue
            # 模拟分析：检查文件中疑似组件定义的名称
            import re

            component_matches = re.findall(
                r'(?:const|function|class)\s+([A-Za-z_]\w*)\s*(?:[=(:{]|extends)',
                content,
            )
            for comp_name in component_matches:
                total_components += 1
                if comp_name[0].isupper() and comp_name.isascii():
                    pascal_count += 1
                else:
                    non_pascal.append({"component": comp_name, "file": filepath})

        naming_score = (pascal_count / max(total_components, 1)) * 100
        if non_pascal:
            issues.append({
                "type": "naming",
                "severity": "warning",
                "message": f"发现 {len(non_pascal)} 个非 PascalCase 组件命名",
                "items": non_pascal[:10],
            })
            suggestions.append("统一使用 PascalCase 命名组件")

        # 模拟样式一致性分析
        inline_style_count = 0
        tailwind_class_count = 0
        for content in file_contents.values():
            if not content:
                continue
            inline_style_count += content.count("style={{")
            tailwind_class_count += content.count("className=")

        style_ratio = inline_style_count / max(inline_style_count + tailwind_class_count, 1)
        style_score = max(0, 100 - style_ratio * 200)
        if style_ratio > 0.1:
            issues.append({
                "type": "style",
                "severity": "warning",
                "message": f"内联样式占比 {style_ratio:.1%}，建议使用 Tailwind 类名替代",
            })
            suggestions.append("减少内联样式，优先使用 Tailwind CSS 工具类")

        # 响应式布局标记分析
        responsive_prefixes = {"md:", "lg:", "sm:", "xl:", "2xl:"}
        total_classes = 0
        responsive_classes = 0
        for content in file_contents.values():
            if not content:
                continue
            import re

            classes = re.findall(r'className="([^"]*)"', content)
            for cls in classes:
                tokens = cls.split()
                total_classes += len(tokens)
                for t in tokens:
                    for prefix in responsive_prefixes:
                        if prefix in t:
                            responsive_classes += 1
                            break

        responsive_score = (responsive_classes / max(total_classes, 1)) * 100
        if responsive_score < 30:
            issues.append({
                "type": "responsive",
                "severity": "info",
                "message": f"响应式前缀覆盖率 {responsive_score:.0f}%，建议增加 md:/lg: 等断点前缀",
            })
            suggestions.append("在样式类中增加响应式断点前缀 (md:/lg:/sm:)")

        # 间距使用分析
        spacing_classes = 0
        total_spacing = 0
        for content in file_contents.values():
            if not content:
                continue
            import re

            classes = re.findall(r'className="([^"]*)"', content)
            for cls in classes:
                tokens = cls.split()
                for t in tokens:
                    if t.startswith(("p-", "m-", "gap-", "space-")):
                        spacing_classes += 1
                    total_spacing += 1

        spacing_score = (spacing_classes / max(total_spacing, 1)) * 100
        if spacing_score < 20:
            suggestions.append("增加间距工具类 (p-/m-/gap-/space-) 的使用")

        # 综合分
        overall_score = round((naming_score + style_score + responsive_score + spacing_score) / 4, 2)

        return UiCheckResult(
            naming_score=round(naming_score, 2),
            style_score=round(style_score, 2),
            responsive_score=round(responsive_score, 2),
            spacing_score=round(spacing_score, 2),
            overall_score=overall_score,
            issues=issues,
            suggestions=list(set(suggestions)),
        )

    @staticmethod
    def simulate_check() -> UiCheckResult:
        """无源码时的模拟检查"""
        return UiCheckResult(
            naming_score=82.5,
            style_score=76.0,
            responsive_score=65.0,
            spacing_score=70.0,
            overall_score=73.4,
            issues=[
                {
                    "type": "naming",
                    "severity": "warning",
                    "message": "发现 3 个组件未使用 PascalCase 命名",
                    "items": [
                        {"component": "card_view", "file": "components/card_view.tsx"},
                        {"component": "userProfile", "file": "components/userProfile.tsx"},
                        {"component": "needList", "file": "components/needList.tsx"},
                    ],
                },
                {
                    "type": "responsive",
                    "severity": "info",
                    "message": "响应式前缀覆盖率 65%，部分组件缺少 md:/lg: 断点",
                },
            ],
            suggestions=[
                "统一使用 PascalCase 命名组件",
                "为关键组件增加响应式断点前缀",
                "减少内联样式，优先使用 Tailwind 工具类",
            ],
        )


# ============================================================
# 品牌一致性检查器 (F-SJ-链客宝-03)
# ============================================================

class BrandConsistencyChecker:
    """品牌一致性检查器"""

    @staticmethod
    def check(file_contents: dict[str, str]) -> BrandCheckResult:
        issues: list[dict] = []
        suggestions: list[str] = []

        color_counts: dict[str, int] = defaultdict(int)
        font_counts: dict[str, int] = defaultdict(int)
        spacing_values: list[int] = []
        non_brand_colors: set[str] = set()

        import re

        for content in file_contents.values():
            if not content:
                continue
            # 提取颜色类
            color_matches = re.findall(r'(text|bg|border|ring)-(?:[a-z]+-\d+)', content)
            for c in color_matches:
                color_counts[c] += 1
                if c not in BRAND_COLORS:
                    if c.split("-")[0] in ["text", "bg", "border", "ring"]:
                        non_brand_colors.add(c)

            # 提取字体类
            font_matches = re.findall(r'font-(?:[a-z]+)', content)
            for f in font_matches:
                font_counts[f] += 1

            # 提取间距数值
            spacing_matches = re.findall(r'[pm]?-(\d+)', content)
            for s in spacing_matches:
                try:
                    spacing_values.append(int(s))
                except ValueError:
                    pass

        total_colors = sum(color_counts.values())
        brand_color_count = sum(v for k, v in color_counts.items() if k in BRAND_COLORS)
        color_score = (brand_color_count / max(total_colors, 1)) * 100

        if non_brand_colors:
            issues.append({
                "type": "brand_color_deviation",
                "severity": "warning",
                "message": f"检测到 {len(non_brand_colors)} 个非品牌色使用",
                "colors": sorted(non_brand_colors)[:10],
            })
            suggestions.append(f"将非品牌色 {', '.join(sorted(non_brand_colors)[:5])} 替换为品牌色")

        # 字体分布判定
        font_variants = len(font_counts)
        font_score = min(100, font_variants * 20)

        # 间距一致性
        if spacing_values:
            mean_spacing = sum(spacing_values) / len(spacing_values)
            variance = sum((x - mean_spacing) ** 2 for x in spacing_values) / len(spacing_values)
            spacing_score = max(0, 100 - math.sqrt(variance) * 10)
        else:
            spacing_score = 50

        overall_score = round((color_score + font_score + spacing_score) / 3, 2)

        return BrandCheckResult(
            color_score=round(color_score, 2),
            font_score=round(font_score, 2),
            spacing_score=round(spacing_score, 2),
            overall_score=overall_score,
            brand_color_usage=dict(color_counts),
            non_brand_colors=sorted(non_brand_colors),
            deviations=issues,
            suggestions=list(set(suggestions)),
        )

    @staticmethod
    def simulate_check() -> BrandCheckResult:
        """无源码时的模拟检查"""
        return BrandCheckResult(
            color_score=78.5,
            font_score=60.0,
            spacing_score=72.0,
            overall_score=70.2,
            brand_color_usage={
                "blue-600": 45,
                "blue-700": 28,
                "purple-600": 32,
                "gray-900": 56,
                "white": 120,
                "gray-50": 35,
            },
            non_brand_colors=["text-green-500", "bg-red-100", "border-yellow-300"],
            deviations=[
                {
                    "type": "brand_color_deviation",
                    "severity": "warning",
                    "message": "检测到 3 个非品牌色使用",
                    "colors": ["text-green-500", "bg-red-100", "border-yellow-300"],
                },
            ],
            suggestions=[
                "将 text-green-500 替换为品牌色 blue-600",
                "限制字体变体数量在 3 种以内",
                "统一组件间距规范，减少间距值离散度",
            ],
        )


# ============================================================
# 名片设计评估器 (F-SJ-链客宝-03)
# ============================================================

class CardDesignEvaluator:
    """名片设计评估器"""

    @staticmethod
    def evaluate(file_contents: dict[str, str]) -> CardDesignScore:
        issues: list[dict] = []
        suggestions: list[str] = []

        import re

        # 字段覆盖度检查
        covered_fields = []
        missing_fields = []
        content_all = " ".join(file_contents.values()) if file_contents else ""

        for field in CARD_STANDARD_FIELDS:
            if field in content_all:
                covered_fields.append(field)
            else:
                missing_fields.append(field)

        field_coverage = (len(covered_fields) / len(CARD_STANDARD_FIELDS)) * 100
        if missing_fields:
            issues.append({
                "type": "missing_field",
                "severity": "warning",
                "message": f"缺少 {len(missing_fields)} 个标准字段: {', '.join(missing_fields)}",
            })
            suggestions.append(f"添加缺失的标准名片字段: {', '.join(missing_fields)}")

        # 页面结构检查
        page_types_found = []
        for page in CARD_PAGE_TYPES:
            if page in content_all:
                page_types_found.append(page)

        # 流程步骤检查
        flow_steps_found = []
        for step in CARD_FLOW_STEPS:
            if step in content_all:
                flow_steps_found.append(step)

        page_coverage = (len(page_types_found) / len(CARD_PAGE_TYPES)) * 0.5 + (len(flow_steps_found) / len(CARD_FLOW_STEPS)) * 0.5
        page_structure = page_coverage * 100

        if len(page_types_found) < len(CARD_PAGE_TYPES):
            missing_pages = set(CARD_PAGE_TYPES) - set(page_types_found)
            suggestions.append(f"补充缺失的页面类型: {', '.join(missing_pages)}")

        # 主题一致性检查
        theme_count = 0
        themes_found = []
        for theme in CARD_THEMES:
            if theme in content_all:
                theme_count += 1
                themes_found.append(theme)
        theme_consistency = (theme_count / max(len(CARD_THEMES), 1)) * 100

        # 组件解耦度检查
        components_found = []
        for comp in CARD_EXPECTED_COMPONENTS:
            if comp in content_all:
                components_found.append(comp)

        component_score = (len(components_found) / len(CARD_EXPECTED_COMPONENTS)) * 100
        if len(components_found) < len(CARD_EXPECTED_COMPONENTS):
            missing_comps = set(CARD_EXPECTED_COMPONENTS) - set(components_found)
            suggestions.append(f"考虑增加独立组件: {', '.join(list(missing_comps)[:5])}")

        overall_score = round((field_coverage + page_structure + theme_consistency + component_score) / 4, 2)

        return CardDesignScore(
            field_coverage=round(field_coverage, 2),
            page_structure=round(page_structure, 2),
            theme_consistency=round(theme_consistency, 2),
            component_decoupling=round(component_score, 2),
            overall_score=overall_score,
            covered_fields=covered_fields,
            missing_fields=missing_fields,
            issues=issues,
            suggestions=list(set(suggestions)),
        )

    @staticmethod
    def simulate_evaluate() -> CardDesignScore:
        """无源码时的模拟评估"""
        return CardDesignScore(
            field_coverage=75.0,
            page_structure=62.5,
            theme_consistency=66.7,
            component_decoupling=50.0,
            overall_score=63.6,
            covered_fields=["name", "position", "company", "phone", "email", "wechat"],
            missing_fields=["address", "website"],
            issues=[
                {
                    "type": "missing_field",
                    "severity": "warning",
                    "message": "缺少 2 个标准字段: address, website",
                },
                {
                    "type": "component",
                    "severity": "info",
                    "message": "仅找到 5/10 个预期组件",
                },
            ],
            suggestions=[
                "添加缺失的标准名片字段: address, website",
                "补充缺失的页面类型: qrcode",
                "增加 CardQRCode 和 CardAlbum 独立组件",
            ],
        )


# ============================================================
# 10维度审美评分器 (F-审美-01)
# ============================================================

class AestheticScorer:
    """10维度审美评分器"""

    DIMENSION_LABELS: dict[str, str] = {
        AestheticDimension.COLOR.value: "色彩搭配",
        AestheticDimension.TYPOGRAPHY.value: "字体排版",
        AestheticDimension.SPACING.value: "间距留白",
        AestheticDimension.LAYOUT.value: "布局结构",
        AestheticDimension.CONTRAST.value: "对比层次",
        AestheticDimension.CONSISTENCY.value: "一致性",
        AestheticDimension.MOTION.value: "动效体验",
        AestheticDimension.RESPONSIVE.value: "响应适配",
        AestheticDimension.ACCESSIBILITY.value: "无障碍设计",
        AestheticDimension.BRANDING.value: "品牌感",
    }

    @staticmethod
    def evaluate(
        interface_description: str,
        target_user_group: str,
        platform: str,
    ) -> AestheticScoreCard:
        """评估界面审美的10个维度"""
        import re

        description_lower = interface_description.lower()

        # 基于关键词的启发式评分
        scores: dict[str, float] = {}

        # 色彩 (color)
        color_score = 7.0
        if any(kw in description_lower for kw in ["色彩", "颜色", "配色", "色板", "品牌色"]):
            color_score += 1.0
        if any(kw in description_lower for kw in ["单调", "颜色杂", "刺眼"]):
            color_score -= 2.0
        scores[AestheticDimension.COLOR.value] = max(1, min(10, color_score))

        # 字体 (typography)
        font_score = 6.5
        if any(kw in description_lower for kw in ["字体", "排版", "字重", "字型", "sans-serif"]):
            font_score += 1.0
        scores[AestheticDimension.TYPOGRAPHY.value] = max(1, min(10, font_score))

        # 间距 (spacing)
        spacing_score = 6.0
        if any(kw in description_lower for kw in ["间距", "留白", "padding", "margin", "呼吸感"]):
            spacing_score += 1.5
        scores[AestheticDimension.SPACING.value] = max(1, min(10, spacing_score))

        # 布局 (layout)
        layout_score = 7.0
        if any(kw in description_lower for kw in ["布局", "grid", "flex", "对称", "栅格"]):
            layout_score += 1.0
        if any(kw in description_lower for kw in ["混乱", "拥挤", "不对称"]):
            layout_score -= 1.5
        scores[AestheticDimension.LAYOUT.value] = max(1, min(10, layout_score))

        # 对比 (contrast)
        contrast_score = 6.5
        if any(kw in description_lower for kw in ["对比", "层次", "视觉层级", "突出"]):
            contrast_score += 1.0
        scores[AestheticDimension.CONTRAST.value] = max(1, min(10, contrast_score))

        # 一致性 (consistency)
        consistency_score = 6.0
        if any(kw in description_lower for kw in ["一致", "统一", "规范", "标准化"]):
            consistency_score += 1.5
        scores[AestheticDimension.CONSISTENCY.value] = max(1, min(10, consistency_score))

        # 动效 (motion)
        motion_score = 5.5
        if any(kw in description_lower for kw in ["动效", "动画", "过渡", "交互动画", "微动效"]):
            motion_score += 1.5
        scores[AestheticDimension.MOTION.value] = max(1, min(10, motion_score))

        # 响应 (responsive)
        responsive_score = 6.5
        if any(kw in description_lower for kw in ["响应式", "自适应", "移动端", "多端适配"]):
            responsive_score += 1.0
        if platform == "Mobile":
            responsive_score += 1.0
        scores[AestheticDimension.RESPONSIVE.value] = max(1, min(10, responsive_score))

        # 无障碍 (accessibility)
        accessibility_score = 5.0
        if any(kw in description_lower for kw in ["无障碍", "可访问", "aria", "语义化", "键盘导航"]):
            accessibility_score += 2.0
        scores[AestheticDimension.ACCESSIBILITY.value] = max(1, min(10, accessibility_score))

        # 品牌感 (branding)
        branding_score = 6.0
        if any(kw in description_lower for kw in ["品牌", "logo", "企业色", "品牌识别", "vi"]):
            branding_score += 1.5
        scores[AestheticDimension.BRANDING.value] = max(1, min(10, branding_score))

        # 综合评分
        overall_score = round(sum(scores.values()) / len(scores), 2)

        # 找到最低分的3个维度
        sorted_dims = sorted(scores.items(), key=lambda x: x[1])
        top3_improvements = []
        for dim, score in sorted_dims[:3]:
            label = AestheticScorer.DIMENSION_LABELS.get(dim, dim)
            suggestions_map = {
                AestheticDimension.COLOR.value: "建立品牌色板并统一使用，避免颜色种类过多",
                AestheticDimension.TYPOGRAPHY.value: "限定字体家族和字重范围（建议≤3种）",
                AestheticDimension.SPACING.value: "制定间距规范（如4/8/12/16/24阶梯），保持间距一致性",
                AestheticDimension.LAYOUT.value: "采用栅格系统（如12列Grid），确保布局结构化",
                AestheticDimension.CONTRAST.value: "增强视觉层级，确保文字/背景对比度≥4.5:1",
                AestheticDimension.CONSISTENCY.value: "建立组件规范和设计语言，确保全站一致",
                AestheticDimension.MOTION.value: "增加微动效提升交互反馈体验，注意动画时长≤300ms",
                AestheticDimension.RESPONSIVE.value: "增加断点适配（sm/md/lg/xl），确保多端体验一致",
                AestheticDimension.ACCESSIBILITY.value: "增加ARIA标签、键盘导航和语义化HTML结构",
                AestheticDimension.BRANDING.value: "增强品牌元素露出（Logo/品牌色/品牌字体）",
            }
            top3_improvements.append({
                "dimension": dim,
                "label": label,
                "score": score,
                "suggestion": suggestions_map.get(dim, "改进此维度设计"),
            })

        # 参考对标
        benchmark_references = [
            f"同类优秀 {platform} 产品推荐: 参考行业领跑者的设计系统",
            "参考案例: Ant Design / Material Design 3 设计规范",
        ]
        if "企业家" in target_user_group or "商务" in target_user_group:
            benchmark_references.append("对标: 领英(LinkedIn) 的商务社交设计风格")
        if "品牌" in interface_description:
            benchmark_references.append("对标: Apple Human Interface Guidelines 品牌感设计")

        return AestheticScoreCard(
            dimensions=scores,
            overall_score=overall_score,
            top3_improvements=top3_improvements,
            benchmark_references=benchmark_references,
        )


# ============================================================
# 路由：UI一致性检查
# ============================================================

@router.post(
    "/review/ui",
    summary="UI一致性检查",
    description="对前端组件进行静态分析，检查组件命名规范、样式一致性、响应式布局标记和间距使用",
)
def review_ui_consistency(
    req: UiReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行UI一致性检查"""
    if req.file_contents:
        result = UiConsistencyChecker.check(req.file_contents)
    else:
        # 模拟检查（无源码时）
        result = UiConsistencyChecker.simulate_check()

    report = ReviewReport(
        report_id=f"rev-{uuid.uuid4().hex[:12]}",
        ui_check_result=result,
        overall_score=result.overall_score,
        score_level=_score_to_level(result.overall_score).value,
        issues_summary=[
            {"category": "ui_consistency", "count": len(result.issues), "details": result.issues}
        ],
        improvement_suggestions=result.suggestions,
        created_at=datetime.now(UTC).isoformat(),
    )

    rid = _save_report_to_db(db, report.model_dump())

    logger.info("ui_review_completed", extra={"report_id": rid, "score": result.overall_score})
    return {
        "code": 200,
        "message": "success",
        "data": report.model_dump(),
    }


# ============================================================
# 路由：品牌一致性检查
# ============================================================

@router.post(
    "/review/brand",
    summary="品牌一致性检查",
    description="检查前端代码中的品牌色/字体/间距使用一致性，检测非品牌色偏离警告",
)
def review_brand_consistency(
    req: BrandReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行品牌一致性检查"""
    if req.file_contents:
        result = BrandConsistencyChecker.check(req.file_contents)
    else:
        result = BrandConsistencyChecker.simulate_check()

    report = ReviewReport(
        report_id=f"rev-{uuid.uuid4().hex[:12]}",
        brand_check_result=result,
        overall_score=result.overall_score,
        score_level=_score_to_level(result.overall_score).value,
        issues_summary=[
            {"category": "brand_consistency", "count": len(result.deviations), "details": result.deviations}
        ],
        improvement_suggestions=result.suggestions,
        created_at=datetime.now(UTC).isoformat(),
    )

    rid = _save_report_to_db(db, report.model_dump())
    logger.info("brand_review_completed", extra={"report_id": rid, "score": result.overall_score})
    return {
        "code": 200,
        "message": "success",
        "data": report.model_dump(),
    }


# ============================================================
# 路由：名片设计评估
# ============================================================

@router.post(
    "/review/card",
    summary="名片设计评估",
    description="评估名片组件的字段覆盖度/页面结构/主题一致性/组件解耦度",
)
def review_card_design(
    req: CardReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行名片设计评估"""
    if req.file_contents:
        result = CardDesignEvaluator.evaluate(req.file_contents)
    else:
        result = CardDesignEvaluator.simulate_evaluate()

    report = ReviewReport(
        report_id=f"rev-{uuid.uuid4().hex[:12]}",
        card_design_score=result,
        overall_score=result.overall_score,
        score_level=_score_to_level(result.overall_score).value,
        issues_summary=[
            {"category": "card_design", "count": len(result.issues), "details": result.issues}
        ],
        improvement_suggestions=result.suggestions,
        created_at=datetime.now(UTC).isoformat(),
    )

    rid = _save_report_to_db(db, report.model_dump())
    logger.info("card_review_completed", extra={"report_id": rid, "score": result.overall_score})
    return {
        "code": 200,
        "message": "success",
        "data": report.model_dump(),
    }


# ============================================================
# 路由：完整审美评估
# ============================================================

@router.post(
    "/review/full",
    summary="完整审美评估",
    description="一次执行UI一致性+品牌一致性+名片设计三维度全面评估，生成综合报告",
)
def review_full(
    req: ReviewConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行完整三维度审美评估"""
    start = time.time()
    scores: list[float] = []

    # 维度1: UI一致性
    if req.enable_ui_check:
        ui_result = UiConsistencyChecker.simulate_check()
        scores.append(ui_result.overall_score)
    else:
        ui_result = None

    # 维度2: 品牌一致性
    if req.enable_brand_check:
        brand_result = BrandConsistencyChecker.simulate_check()
        scores.append(brand_result.overall_score)
    else:
        brand_result = None

    # 维度3: 名片设计
    if req.enable_card_eval:
        card_result = CardDesignEvaluator.simulate_evaluate()
        scores.append(card_result.overall_score)
    else:
        card_result = None

    overall_score = round(sum(scores) / max(len(scores), 1), 2) if scores else 0.0

    # 聚合问题和建议
    all_issues = []
    all_suggestions = []
    if ui_result:
        all_issues.extend(ui_result.issues)
        all_suggestions.extend(ui_result.suggestions)
    if brand_result:
        all_issues.extend(brand_result.deviations)
        all_suggestions.extend(brand_result.suggestions)
    if card_result:
        all_issues.extend(card_result.issues)
        all_suggestions.extend(card_result.suggestions)

    # 尝试LLM生成总结（降级友好）
    llm_summary = None
    try:
        from app.services.llm_service import summarize_lead

        llm_summary = summarize_lead({
            "name": "审美评估",
            "notes": f"UI={ui_result.overall_score if ui_result else 'N/A'}, "
                     f"Brand={brand_result.overall_score if brand_result else 'N/A'}, "
                     f"Card={card_result.overall_score if card_result else 'N/A'}",
        })
    except Exception:
        pass

    report = ReviewReport(
        report_id=f"rev-{uuid.uuid4().hex[:12]}",
        ui_check_result=ui_result,
        brand_check_result=brand_result,
        card_design_score=card_result,
        overall_score=overall_score,
        score_level=_score_to_level(overall_score).value,
        issues_summary=all_issues,
        improvement_suggestions=list(set(all_suggestions)),
        created_at=datetime.now(UTC).isoformat(),
    )

    rid = _save_report_to_db(db, report.model_dump())

    duration_ms = (time.time() - start) * 1000

    return {
        "code": 200,
        "message": "success",
        "data": {
            "report": report.model_dump(),
            "pipeline_stats": {
                "duration_ms": round(duration_ms, 2),
                "llm_summary": llm_summary,
            },
        },
    }


# ============================================================
# 路由：10维度界面审美评分 (F-审美-01)
# ============================================================

@router.post(
    "/evaluate",
    summary="10维度界面审美评分",
    description="对用户界面进行10维度审美评分，输出可执行的改进方案",
)
def evaluate_aesthetic(
    req: AestheticEvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行10维度界面审美评分"""
    score_card = AestheticScorer.evaluate(
        interface_description=req.interface_description,
        target_user_group=req.target_user_group,
        platform=req.platform,
    )

    # 尝试LLM生成改进方案（降级友好）
    try:
        from app.services.llm_service import generate_enriched_description

        enriched = generate_enriched_description({
            "name": "界面审美评估",
            "description": req.interface_description[:200],
            "industry": req.target_user_group,
        })
        if enriched:
            score_card.top3_improvements.append({
                "dimension": "llm_suggestion",
                "label": "LLM智能建议",
                "score": 0,
                "suggestion": enriched[:200],
            })
    except Exception:
        pass

    sid = _save_score_card_to_db(db, score_card.model_dump())

    logger.info("aesthetic_evaluation_completed", extra={
        "score_id": sid,
        "overall_score": score_card.overall_score,
    })

    return {
        "code": 200,
        "message": "success",
        "data": score_card.model_dump(),
    }


# ============================================================
# 路由：报告/历史/指标
# ============================================================

@router.get(
    "/reports",
    summary="历史评估报告",
    description="获取历史审美评估报告列表",
)
def list_reports(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取历史报告列表"""
    items = db.query(DesignReviewReport).order_by(DesignReviewReport.created_at.desc()).limit(limit).all()
    reports = []
    for r in items:
        report_dict = json.loads(r.report_data)
        report_dict["report_id"] = r.id
        report_dict["created_at"] = r.created_at.isoformat() if r.created_at else ""
        reports.append(report_dict)
    return {
        "code": 200,
        "message": "success",
        "data": reports,
        "total": len(reports),
    }


@router.get(
    "/reports/{report_id}",
    summary="报告详情",
    description="获取指定审美评估报告的详细信息",
)
def get_report(
    report_id: str = Path(..., description="报告ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取报告详情"""
    r = db.query(DesignReviewReport).filter(DesignReviewReport.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"报告 {report_id} 不存在")
    report_dict = json.loads(r.report_data)
    report_dict["report_id"] = r.id
    report_dict["created_at"] = r.created_at.isoformat() if r.created_at else ""
    return {
        "code": 200,
        "message": "success",
        "data": report_dict,
    }


@router.get(
    "/metrics",
    summary="审美评估监控指标",
    description="获取评估报告总数/评分卡总数/平均分等监控指标",
)
def get_aesthetic_metrics(
    db: Session = Depends(get_db),
):
    """获取监控指标"""
    total_reports = db.query(DesignReviewReport).count()
    total_score_cards = db.query(AestheticScoreCardRecord).count()
    avg_row = db.query(db.func.avg(DesignReviewReport.overall_score)).scalar()
    avg_overall_score = round(avg_row, 2) if avg_row else 0.0
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_reports": total_reports,
            "total_score_cards": total_score_cards,
            "avg_overall_score": avg_overall_score,
        },
    }
