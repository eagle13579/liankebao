"""
链客宝 - 数据管道编排器
==========================
定义完整的数据流：采集 → 清洗 → 分析 → 输出

管道阶段：
1. COLLECT  — 从各路由模块采集原始数据
2. CLEAN    — 数据清洗、去重、格式标准化
3. ANALYZE  — 执行多维度分析
4. OUTPUT   — 格式化输出结果

设计原则：
- 每个阶段可独立启用/禁用
- 支持严格模式（出错即中止）和容错模式（继续执行）
- 提供完整的运行报告
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .config import PipelineConfig
from .collector import (
    DataSource,
    collect_all,
    CollectorConfig,
)
from .analyzer import (
    AnalysisResult,
    BaseAnalyzer,
    CompositeAnalyzer,
    RetentionAnalyzer,
    LearningAnalyzer,
    EconomicsAnalyzer,
    HypothesisAnalyzer,
    AnalyzerConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 管道阶段定义
# ---------------------------------------------------------------------------


class PipelineStage(Enum):
    """管道阶段枚举"""

    INIT = "init"
    COLLECT = "collect"
    CLEAN = "clean"
    ANALYZE = "analyze"
    OUTPUT = "output"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# 管道运行结果
# ---------------------------------------------------------------------------


@dataclass
class PipelineReport:
    """管道运行报告"""

    pipeline_name: str = ""
    status: PipelineStage = PipelineStage.INIT
    started_at: str = ""
    finished_at: str = ""
    elapsed_seconds: float = 0.0

    # 各阶段统计
    collect_stage: Optional[dict[str, Any]] = None
    clean_stage: Optional[dict[str, Any]] = None
    analyze_stage: Optional[dict[str, Any]] = None
    output_stage: Optional[dict[str, Any]] = None

    # 汇总
    total_records_collected: int = 0
    total_records_analyzed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """管道是否成功完成"""
        return self.status == PipelineStage.DONE


# ---------------------------------------------------------------------------
# 数据清洗器
# ---------------------------------------------------------------------------


class DataCleaner:
    """数据清洗与标准化"""

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig.default()

    def clean(self, data: dict[str, DataSource]) -> dict[str, DataSource]:
        """
        清洗所有数据源

        操作：
        1. 移除无效记录（None ID 或空数据）
        2. 去除完全重复的记录
        3. 补充缺失的时间戳
        """
        cleaned: dict[str, DataSource] = {}
        total_removed = 0

        for source_name, source_data in data.items():
            try:
                before = len(source_data.records)
                seen_keys: set[str] = set()
                valid_records = []

                for record in source_data.records:
                    # 跳过无效数据
                    if not record.data:
                        total_removed += 1
                        continue

                    # 去重（基于 source + record_type + id 或 content hash）
                    dedup_key = f"{record.source}:{record.record_type}:{record.id}"
                    if dedup_key in seen_keys:
                        total_removed += 1
                        continue
                    seen_keys.add(dedup_key)

                    # 补充时间戳
                    if not record.collected_at:
                        record.collected_at = datetime.utcnow().isoformat() + "Z"

                    valid_records.append(record)

                after = len(valid_records)
                logger.debug(
                    "[cleaner] %s: 清洗前 %d 条, 清洗后 %d 条, 移除 %d 条",
                    source_name, before, after, before - after,
                )

                # 构建清洗后的 DataSource
                cleaned[source_name] = DataSource(
                    name=source_name,
                    records=valid_records,
                    total_count=after,
                    error_count=source_data.error_count,
                    errors=source_data.errors,
                    elapsed_seconds=source_data.elapsed_seconds,
                )
            except Exception as e:
                logger.warning("[cleaner] %s 清洗失败: %s", source_name, e)
                cleaned[source_name] = source_data  # 保底返回原始数据

        return cleaned


# ---------------------------------------------------------------------------
# 管道编排器
# ---------------------------------------------------------------------------


class DataPipeline:
    """
    统一数据管道编排器

    使用方式:
        pipeline = DataPipeline()
        report = pipeline.run()

        # 或使用自定义配置
        config = PipelineConfig(strict_mode=True)
        pipeline = DataPipeline(config)
        report = pipeline.run()
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig.default()
        self._setup_logging()

        # 内部状态
        self._stage = PipelineStage.INIT
        self._raw_data: dict[str, DataSource] = {}
        self._cleaned_data: dict[str, DataSource] = {}
        self._analysis_result: Optional[AnalysisResult] = None
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._start_time: float = 0.0

    def _setup_logging(self) -> None:
        """配置日志级别"""
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="[data_pipeline] %(levelname)s %(message)s",
            force=False,
        )

    # ------------------------------------------------------------------
    # 阶段执行
    # ------------------------------------------------------------------

    def _stage_collect(self) -> None:
        """阶段1: 数据采集"""
        self._stage = PipelineStage.COLLECT
        logger.info("[pipeline] === 阶段: 数据采集 ===")

        try:
            self._raw_data = collect_all(self.config.collector)
        except Exception as e:
            self._handle_error(f"采集阶段失败: {e}")
            return

        total = sum(ds.total_count for ds in self._raw_data.values())
        errors = sum(ds.error_count for ds in self._raw_data.values())
        logger.info("[pipeline] 采集完成: %d 条记录, %d 个错误", total, errors)

        if errors > 0:
            for name, ds in self._raw_data.items():
                if ds.errors:
                    for err in ds.errors:
                        self._warnings.append(f"[{name}] {err}")

    def _stage_clean(self) -> None:
        """阶段2: 数据清洗"""
        self._stage = PipelineStage.CLEAN
        logger.info("[pipeline] === 阶段: 数据清洗 ===")

        try:
            cleaner = DataCleaner(self.config)
            self._cleaned_data = cleaner.clean(self._raw_data)
        except Exception as e:
            self._handle_error(f"清洗阶段失败: {e}")
            return

        total = sum(ds.total_count for ds in self._cleaned_data.values())
        logger.info("[pipeline] 清洗完成: %d 条有效记录", total)

    def _stage_analyze(self) -> None:
        """阶段3: 数据分析"""
        self._stage = PipelineStage.ANALYZE
        logger.info("[pipeline] === 阶段: 数据分析 ===")

        try:
            analyzer = CompositeAnalyzer(config=self.config.analyzer)
            self._analysis_result = analyzer.analyze(self._cleaned_data)
        except Exception as e:
            self._handle_error(f"分析阶段失败: {e}")
            return

        logger.info(
            "[pipeline] 分析完成: %d 个指标, %d 条洞察, %d 条建议",
            len(self._analysis_result.metrics),
            len(self._analysis_result.insights),
            len(self._analysis_result.recommendations),
        )

    def _stage_output(self) -> dict[str, Any]:
        """阶段4: 输出格式化"""
        self._stage = PipelineStage.OUTPUT
        logger.info("[pipeline] === 阶段: 格式化输出 ===")

        if self._analysis_result is None:
            return {"status": "no_data", "message": "无分析结果可输出"}

        # 构建结构化输出
        output: dict[str, Any] = {
            "pipeline": self.config.pipeline_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "success",
            "stages": {
                "collect": {
                    "sources": list(self._raw_data.keys()),
                    "total_records": sum(
                        ds.total_count for ds in self._raw_data.values()
                    ),
                },
                "clean": {
                    "total_records": sum(
                        ds.total_count for ds in self._cleaned_data.values()
                    ),
                },
                "analyze": {
                    "analyzer": self._analysis_result.analyzer_name,
                    "metrics_count": len(self._analysis_result.metrics),
                    "insights_count": len(self._analysis_result.insights),
                    "recommendations_count": len(self._analysis_result.recommendations),
                },
            },
            "metrics": self._analysis_result.metrics,
            "insights": self._analysis_result.insights,
            "warnings": self._analysis_result.warnings,
            "recommendations": self._analysis_result.recommendations,
        }

        if self._errors:
            output["errors"] = self._errors

        # 根据配置格式化
        fmt = self.config.output_format
        logger.info("[pipeline] 输出格式: %s", fmt)

        return output

    # ------------------------------------------------------------------
    # 错误处理
    # ------------------------------------------------------------------

    def _handle_error(self, msg: str) -> None:
        """处理管道错误"""
        self._errors.append(msg)
        logger.error("[pipeline] %s", msg)
        if self.config.strict_mode:
            self._stage = PipelineStage.FAILED
            raise RuntimeError(msg)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def run(self) -> PipelineReport:
        """
        执行完整数据管道

        Returns:
            管道运行报告
        """
        self._start_time = time.perf_counter()
        started_at = datetime.utcnow().isoformat() + "Z"
        logger.info(
            "[pipeline] ====== %s 启动 (strict=%s, parallel=%s) ======",
            self.config.pipeline_name,
            self.config.strict_mode,
            self.config.parallel_execution,
        )

        # 阶段1: 采集
        self._stage_collect()
        if self._stage == PipelineStage.FAILED:
            return self._build_report(started_at)

        # 阶段2: 清洗
        self._stage_clean()
        if self._stage == PipelineStage.FAILED:
            return self._build_report(started_at)

        # 阶段3: 分析
        self._stage_analyze()
        if self._stage == PipelineStage.FAILED:
            return self._build_report(started_at)

        # 阶段4: 输出
        output = self._stage_output()

        # 成功
        self._stage = PipelineStage.DONE
        elapsed = round(time.perf_counter() - self._start_time, 3)
        logger.info(
            "[pipeline] ====== 管道完成, 耗时 %.3fs ======", elapsed,
        )

        return self._build_report(started_at, output=output)

    def _build_report(
        self,
        started_at: str,
        output: Optional[dict] = None,
    ) -> PipelineReport:
        """构建管道运行报告"""
        elapsed = round(time.perf_counter() - self._start_time, 3)

        collect_info = self._build_collect_stage_info()
        clean_info = self._build_clean_stage_info()
        analyze_info = self._build_analyze_stage_info()

        return PipelineReport(
            pipeline_name=self.config.pipeline_name,
            status=self._stage,
            started_at=started_at,
            finished_at=datetime.utcnow().isoformat() + "Z",
            elapsed_seconds=elapsed,
            collect_stage=collect_info,
            clean_stage=clean_info,
            analyze_stage=analyze_info,
            output_stage=output,
            total_records_collected=(
                sum(ds.total_count for ds in self._raw_data.values())
                if self._raw_data else 0
            ),
            total_records_analyzed=(
                sum(ds.total_count for ds in self._cleaned_data.values())
                if self._cleaned_data else 0
            ),
            errors=self._errors,
            warnings=self._warnings,
        )

    # ------------------------------------------------------------------
    # 子报告构建器
    # ------------------------------------------------------------------

    def _build_collect_stage_info(self) -> Optional[dict[str, Any]]:
        """构建采集阶段统计"""
        if not self._raw_data:
            return None
        return {
            "sources": list(self._raw_data.keys()),
            "source_details": {
                name: {
                    "records": ds.total_count,
                    "errors": ds.error_count,
                    "elapsed": ds.elapsed_seconds,
                }
                for name, ds in self._raw_data.items()
            },
            "total_records": sum(ds.total_count for ds in self._raw_data.values()),
            "total_errors": sum(ds.error_count for ds in self._raw_data.values()),
        }

    def _build_clean_stage_info(self) -> Optional[dict[str, Any]]:
        """构建清洗阶段统计"""
        if not self._cleaned_data:
            return None
        return {
            "total_records": sum(
                ds.total_count for ds in self._cleaned_data.values()
            ),
        }

    def _build_analyze_stage_info(self) -> Optional[dict[str, Any]]:
        """构建分析阶段统计"""
        if not self._analysis_result:
            return None
        return {
            "analyzer": self._analysis_result.analyzer_name,
            "metrics": len(self._analysis_result.metrics),
            "insights": len(self._analysis_result.insights),
            "warnings": len(self._analysis_result.warnings),
            "recommendations": len(self._analysis_result.recommendations),
        }

    def run_async(self) -> PipelineReport:
        """
        异步运行管道（占位符，后续接入 Celery / asyncio）

        当前为同步占位，返回与 run() 相同的结果。
        """
        logger.info("[pipeline] 异步模式未启用，回退为同步执行")
        return self.run()


# ---------------------------------------------------------------------------
# 便捷入口函数
# ---------------------------------------------------------------------------


def run_pipeline(
    config: Optional[PipelineConfig] = None,
) -> PipelineReport:
    """
    快速运行数据管道

    Args:
        config: 管道配置（可选）

    Returns:
        管道运行报告
    """
    pipeline = DataPipeline(config or PipelineConfig.default())
    return pipeline.run()


def run_collect_only(
    config: Optional[CollectorConfig] = None,
) -> dict[str, DataSource]:
    """
    仅执行数据采集阶段

    Args:
        config: 采集器配置（可选）

    Returns:
        各数据源的采集结果
    """
    return collect_all(config)


def run_analyze_only(
    data: dict[str, DataSource],
    config: Optional[AnalyzerConfig] = None,
) -> AnalysisResult:
    """
    仅执行数据分析（需预先准备好采集数据）

    Args:
        data: 数据源名称 -> DataSource 的映射
        config: 分析器配置（可选）

    Returns:
        分析结果
    """
    analyzer = CompositeAnalyzer(config=config)
    return analyzer.analyze(data)
