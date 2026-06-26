"""
链客宝 - 统一数据管道 Feature
===============================
将散落在各路由模块（retention_insights / learning_center / unit_economics /
hypothesis_gate 等）中的数据采集、清洗、分析、输出能力整合为统一的管道。

能力矩阵：
┌──────────┬─────────────────────────────────────────────┐
│ 模块     │ 能力                                        │
├──────────┼─────────────────────────────────────────────┤
│ config   │ 管道全局配置（环境变量可覆盖）               │
│ collector│ 多数据源统一采集器（标准化 DataSource 输出） │
│ analyzer │ 多维度分析引擎（留存/学习/经济/假设）       │
│ pipeline │ 管道编排器（采集→清洗→分析→输出）           │
└──────────┴─────────────────────────────────────────────┘

快速开始:
    from backend.features.data_pipeline import DataPipeline, PipelineConfig

    pipeline = DataPipeline()
    report = pipeline.run()
    print(report.analyze_stage["insights"])

向后兼容:
    现有路由模块无需修改。本模块作为独立 Feature 存在，
    可逐步被现有路由 import 使用。
"""

from .config import (
    PipelineConfig,
    CollectorConfig,
    AnalyzerConfig,
)
from .collector import (
    BaseCollector,
    RetentionCollector,
    LearningCollector,
    EconomicsCollector,
    HypothesisCollector,
    DataSource,
    DataRecord,
    collect_all,
    get_collector,
    list_available_collectors,
)
from .analyzer import (
    BaseAnalyzer,
    RetentionAnalyzer,
    LearningAnalyzer,
    EconomicsAnalyzer,
    HypothesisAnalyzer,
    CompositeAnalyzer,
    AnalysisResult,
    get_analyzer,
    list_available_analyzers,
)
from .pipeline import (
    DataPipeline,
    DataCleaner,
    PipelineReport,
    PipelineStage,
    run_pipeline,
    run_collect_only,
    run_analyze_only,
)

__all__ = [
    # 配置
    "PipelineConfig",
    "CollectorConfig",
    "AnalyzerConfig",
    # 采集
    "BaseCollector",
    "RetentionCollector",
    "LearningCollector",
    "EconomicsCollector",
    "HypothesisCollector",
    "DataSource",
    "DataRecord",
    "collect_all",
    "get_collector",
    "list_available_collectors",
    # 分析
    "BaseAnalyzer",
    "RetentionAnalyzer",
    "LearningAnalyzer",
    "EconomicsAnalyzer",
    "HypothesisAnalyzer",
    "CompositeAnalyzer",
    "AnalysisResult",
    "get_analyzer",
    "list_available_analyzers",
    # 管道
    "DataPipeline",
    "DataCleaner",
    "PipelineReport",
    "PipelineStage",
    "run_pipeline",
    "run_collect_only",
    "run_analyze_only",
]

__version__ = "1.0.0"
__author__ = "链客宝 Data Team"
