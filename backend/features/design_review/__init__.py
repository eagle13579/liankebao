"""
链客宝 - 审美评估系统 Feature
=================================
对链客宝前端页面进行静态代码分析，评估UI一致性、品牌一致性和名片设计质量。

能力矩阵：
┌──────────────────┬─────────────────────────────────────────────┐
│ 模块             │ 能力                                        │
├──────────────────┼─────────────────────────────────────────────┤
│ ui_checker       │ UI一致性检查（组件命名、样式、响应式标记）  │
│ brand_checker    │ 品牌一致性检查（颜色/字体/间距等）          │
│ card_evaluator   │ 名片设计评估（业务卡片组件设计质量）        │
│ report_generator │ 评估报告生成（结构化可读报告）              │
│ engine           │ 编排器（调度各检查器并整合结果）            │
└──────────────────┴─────────────────────────────────────────────┘

快速开始:
    from backend.features.design_review import DesignReviewEngine, ReviewConfig

    engine = DesignReviewEngine()
    report = engine.run()
    print(report.overall_score)
    print(report.issues)

数据来源:
    - src/components/       — 组件库
    - src/pages/            — 页面目录（business-card/、admin/ 等）
    - src/styles/           — 样式配置（如果有 tailwind 配置）

注意: 本引擎做的是**代码层面静态分析**（检查CSS类名一致性、
组件结构合理性），不是AI视觉分析。使用Python正则匹配和规则引擎
分析前端代码文件。
"""

from .engine import (
    DesignReviewEngine,
    ReviewConfig,
    ReviewReport,
    ScoreLevel,
    run_review,
)
from .ui_checker import (
    UiConsistencyChecker,
    UiCheckResult,
    ComponentNamingIssue,
    StyleInconsistency,
    ResponsiveLayoutIssue,
)
from .brand_checker import (
    BrandConsistencyChecker,
    BrandCheckResult,
    ColorUsageIssue,
    FontUsageIssue,
    SpacingInconsistency,
)
from .card_design_evaluator import (
    CardDesignEvaluator,
    CardDesignScore,
    CardAlbumStructure,
    CardFieldCoverage,
    ThemeUsage,
)
from .report_generator import (
    ReviewReportGenerator,
    ReportFormat,
    generate_review_report,
)

__all__ = [
    # Engine
    "DesignReviewEngine",
    "ReviewConfig",
    "ReviewReport",
    "ScoreLevel",
    "run_review",
    # UI Checker
    "UiConsistencyChecker",
    "UiCheckResult",
    "ComponentNamingIssue",
    "StyleInconsistency",
    "ResponsiveLayoutIssue",
    # Brand Checker
    "BrandConsistencyChecker",
    "BrandCheckResult",
    "ColorUsageIssue",
    "FontUsageIssue",
    "SpacingInconsistency",
    # Card Evaluator
    "CardDesignEvaluator",
    "CardDesignScore",
    "CardAlbumStructure",
    "CardFieldCoverage",
    "ThemeUsage",
    # Report Generator
    "ReviewReportGenerator",
    "ReportFormat",
    "generate_review_report",
]

__version__ = "0.1.0"
__author__ = "链客宝 Design Review Team"
