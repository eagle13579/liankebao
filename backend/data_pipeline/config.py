"""
链客宝 - 数据管道配置
========================
统一数据管道的全局配置，包含数据源连接、
管道参数、调度策略等可调优项。

设计原则：
1. 所有配置集中管理，避免散落在各个模块
2. 支持环境变量覆盖（通过 os.getenv 前缀）
3. 提供合理的默认值，开箱即用
"""

import os
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# 管道全局配置
# ---------------------------------------------------------------------------

@dataclass
class CollectorConfig:
    """数据采集器配置"""

    # 是否启用实时采集（否则使用缓存数据）
    realtime_collection: bool = False

    # 采集超时（秒）
    collection_timeout_seconds: int = 30

    # 批量采集最大条目数（防止 OOM）
    max_batch_size: int = 10_000

    # 数据源启用开关
    enable_retention_source: bool = True
    enable_learning_source: bool = True
    enable_economics_source: bool = True
    enable_hypothesis_source: bool = True
    enable_growth_source: bool = True

    # 采集重试策略
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> "CollectorConfig":
        """从环境变量构造配置，支持前缀 DATA_PIPELINE_COLLECTOR_"""
        prefix = "DATA_PIPELINE_COLLECTOR_"
        return cls(
            realtime_collection=os.getenv(f"{prefix}REALTIME", "false").lower() == "true",
            collection_timeout_seconds=int(os.getenv(f"{prefix}TIMEOUT", "30")),
            max_batch_size=int(os.getenv(f"{prefix}MAX_BATCH", "10000")),
            enable_retention_source=os.getenv(f"{prefix}RETENTION", "true").lower() == "true",
            enable_learning_source=os.getenv(f"{prefix}LEARNING", "true").lower() == "true",
            enable_economics_source=os.getenv(f"{prefix}ECONOMICS", "true").lower() == "true",
            enable_hypothesis_source=os.getenv(f"{prefix}HYPOTHESIS", "true").lower() == "true",
            enable_growth_source=os.getenv(f"{prefix}GROWTH", "true").lower() == "true",
            max_retries=int(os.getenv(f"{prefix}MAX_RETRIES", "3")),
            retry_backoff_seconds=float(os.getenv(f"{prefix}RETRY_BACKOFF", "1.0")),
        )


@dataclass
class AnalyzerConfig:
    """数据分析引擎配置"""

    # 留存分析参数
    retention_lookback_months: int = 6
    retention_health_threshold: float = 0.6  # 首月留存健康线

    # 用户活跃判定阈值（月行为数）
    active_threshold: int = 1

    # 流失判定参数
    churn_inactive_days: int = 30
    churn_engagement_drop_ratio: float = 0.5  # 活跃度下降比例

    # 单位经济参数
    ltv_retention_factor: float = 0.7  # 留存折损系数
    ltv_avg_lifetime_months: int = 12
    ltv_cac_healthy_ratio: float = 3.0

    # 学习分析参数
    learning_completion_threshold: float = 80.0  # 完成阈值(%)

    @classmethod
    def from_env(cls) -> "AnalyzerConfig":
        """从环境变量构造配置"""
        prefix = "DATA_PIPELINE_ANALYZER_"
        return cls(
            retention_lookback_months=int(os.getenv(f"{prefix}RETENTION_LOOKBACK", "6")),
            retention_health_threshold=float(os.getenv(f"{prefix}RETENTION_HEALTH", "0.6")),
            active_threshold=int(os.getenv(f"{prefix}ACTIVE_THRESHOLD", "1")),
            churn_inactive_days=int(os.getenv(f"{prefix}CHURN_INACTIVE_DAYS", "30")),
            churn_engagement_drop_ratio=float(os.getenv(f"{prefix}CHURN_DROP_RATIO", "0.5")),
            ltv_retention_factor=float(os.getenv(f"{prefix}LTV_RETENTION", "0.7")),
            ltv_avg_lifetime_months=int(os.getenv(f"{prefix}LTV_LIFETIME", "12")),
            ltv_cac_healthy_ratio=float(os.getenv(f"{prefix}LTV_CAC_HEALTHY", "3.0")),
            learning_completion_threshold=float(os.getenv(f"{prefix}LEARNING_COMPLETION", "80.0")),
        )


@dataclass
class PipelineConfig:
    """管道编排器全局配置"""

    # 管道名称标识
    pipeline_name: str = "chainke-data-pipeline"

    # 是否启用严格模式（出错即中止）
    strict_mode: bool = False

    # 是否启用并行处理
    parallel_execution: bool = False

    # 最大并行工作数
    max_workers: int = 4

    # 日志级别
    log_level: str = "INFO"  # DEBUG / INFO / WARNING / ERROR

    # 输出格式化
    output_format: str = "dict"  # dict / json / csv

    # 子配置
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    analyzer: AnalyzerConfig = field(default_factory=AnalyzerConfig)

    @classmethod
    def default(cls) -> "PipelineConfig":
        """返回默认配置"""
        return cls()

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """从环境变量构造完整管道配置"""
        prefix = "DATA_PIPELINE_"
        return cls(
            pipeline_name=os.getenv(f"{prefix}NAME", "chainke-data-pipeline"),
            strict_mode=os.getenv(f"{prefix}STRICT", "false").lower() == "true",
            parallel_execution=os.getenv(f"{prefix}PARALLEL", "false").lower() == "true",
            max_workers=int(os.getenv(f"{prefix}MAX_WORKERS", "4")),
            log_level=os.getenv(f"{prefix}LOG_LEVEL", "INFO"),
            output_format=os.getenv(f"{prefix}OUTPUT_FORMAT", "dict"),
            collector=CollectorConfig.from_env(),
            analyzer=AnalyzerConfig.from_env(),
        )

    def validate(self) -> list[str]:
        """校验配置有效性，返回警告/错误列表"""
        issues: list[str] = []
        if self.max_workers < 1:
            issues.append("max_workers 不能小于 1")
        if self.analyzer.retention_lookback_months < 1:
            issues.append("retention_lookback_months 不能小于 1")
        if self.analyzer.churn_inactive_days < 1:
            issues.append("churn_inactive_days 不能小于 1")
        if self.output_format not in ("dict", "json", "csv"):
            issues.append(f"不支持的输出格式: {self.output_format}")
        return issues
