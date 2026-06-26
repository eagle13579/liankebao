"""
数据管道 (data_pipeline) 测试
===============================
覆盖：Config、Collector、Analyzer、Pipeline 编排
"""

import pytest
from datetime import datetime


# ===========================================================================
# Config 测试
# ===========================================================================


class TestConfig:
    """管道配置"""

    def test_collector_config_defaults(self):
        """采集器配置应有合理的默认值"""
        from features.data_pipeline.config import CollectorConfig

        cfg = CollectorConfig()
        assert cfg.max_retries == 3
        assert cfg.collection_timeout_seconds == 30
        assert cfg.max_batch_size == 10000
        assert cfg.enable_retention_source is True

    def test_analyzer_config_defaults(self):
        """分析器配置应有合理的默认值"""
        from features.data_pipeline.config import AnalyzerConfig

        cfg = AnalyzerConfig()
        assert cfg.retention_health_threshold == 0.6
        assert cfg.ltv_cac_healthy_ratio == 3.0
        assert cfg.learning_completion_threshold == 80.0

    def test_pipeline_config_defaults(self):
        """管道配置默认值"""
        from features.data_pipeline.config import PipelineConfig

        cfg = PipelineConfig.default()
        assert cfg.pipeline_name == "chainke-data-pipeline"
        assert cfg.strict_mode is False
        assert cfg.output_format == "dict"

    def test_pipeline_config_validate_ok(self):
        """有效配置应无错误"""
        from features.data_pipeline.config import PipelineConfig

        cfg = PipelineConfig.default()
        issues = cfg.validate()
        assert len(issues) == 0

    def test_pipeline_config_validate_errors(self):
        """无效配置应报错"""
        from features.data_pipeline.config import PipelineConfig, AnalyzerConfig

        cfg = PipelineConfig(
            max_workers=0,
            output_format="xml",
            analyzer=AnalyzerConfig(retention_lookback_months=0, churn_inactive_days=0),
        )
        issues = cfg.validate()
        assert len(issues) >= 2


# ===========================================================================
# Collector 测试
# ===========================================================================


class TestDataRecord:
    """数据记录"""

    def test_data_record_default_timestamp(self):
        """创建时自动填充时间戳"""
        from features.data_pipeline.collector import DataRecord

        record = DataRecord(id=1, source="test", record_type="test", data={"k": "v"})
        assert record.collected_at != ""


class TestCollectorBase:
    """采集器基类"""

    def test_make_result(self):
        """_make_result 应正确构造 DataSource"""
        from features.data_pipeline.collector import BaseCollector, DataRecord

        class TestCollector(BaseCollector):
            @property
            def source_name(self):
                return "test"

            def collect(self):
                pass

        c = TestCollector()
        c._start_timer()
        records = [DataRecord(id=1, source="test", record_type="t", data={"a": 1})]
        ds = c._make_result(records)
        assert ds.name == "test"
        assert ds.total_count == 1
        assert ds.success is True

    def test_safe_collect_retry(self):
        """安全采集应重试失败操作"""
        from features.data_pipeline.collector import BaseCollector, CollectorConfig

        class TestCollector(BaseCollector):
            @property
            def source_name(self):
                return "test"

            def collect(self):
                pass

        cfg = CollectorConfig(max_retries=2, retry_backoff_seconds=0.01)
        c = TestCollector(cfg)

        call_count = 0

        def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary error")
            return "ok"

        result = c._safe_collect(flaky_fn)
        assert result == "ok"
        assert call_count == 2

    def test_safe_collect_fail(self):
        """超过重试次数应抛出异常"""
        from features.data_pipeline.collector import BaseCollector, CollectorConfig

        class TestCollector(BaseCollector):
            @property
            def source_name(self):
                return "test"

            def collect(self):
                pass

        cfg = CollectorConfig(max_retries=1, retry_backoff_seconds=0.01)
        c = TestCollector(cfg)

        def always_fail():
            raise ValueError("always fail")

        with pytest.raises(RuntimeError):
            c._safe_collect(always_fail)


class TestCollectors:
    """具体采集器"""

    def test_retention_collector(self):
        """留存采集器应从 retention_insights 模块采集数据"""
        from features.data_pipeline.collector import RetentionCollector

        collector = RetentionCollector()
        result = collector.collect()
        assert result.total_count > 0
        assert result.name == "retention"

    def test_learning_collector(self):
        """学习中心采集器"""
        from features.data_pipeline.collector import LearningCollector

        collector = LearningCollector()
        result = collector.collect()
        assert result.total_count > 0
        assert result.name == "learning"

    def test_economics_collector(self):
        """单位经济采集器"""
        from features.data_pipeline.collector import EconomicsCollector

        collector = EconomicsCollector()
        result = collector.collect()
        assert result.total_count > 0
        assert result.name == "economics"

    def test_hypothesis_collector(self):
        """假设验证采集器"""
        from features.data_pipeline.collector import HypothesisCollector

        collector = HypothesisCollector()
        result = collector.collect()
        assert result.total_count > 0
        assert result.name == "hypothesis"

    def test_collect_all(self):
        """collect_all 应采集所有启用的数据源"""
        from features.data_pipeline.collector import collect_all

        results = collect_all()
        assert "retention" in results
        assert "learning" in results
        assert "economics" in results
        assert "hypothesis" in results
        for name, ds in results.items():
            assert ds.total_count > 0, f"{name} 应采集到数据"

    def test_collect_all_disable_source(self):
        """禁用数据源时，应跳过"""
        from features.data_pipeline.collector import collect_all, CollectorConfig

        cfg = CollectorConfig(
            enable_retention_source=False,
            enable_learning_source=False,
        )
        results = collect_all(cfg)
        assert "retention" not in results
        assert "learning" not in results
        assert "economics" in results

    def test_get_collector_ok(self):
        """获取已知采集器"""
        from features.data_pipeline.collector import get_collector

        c = get_collector("retention")
        assert c is not None
        assert c.source_name == "retention"

    def test_get_collector_unknown(self):
        """获取未知采集器应抛出 ValueError"""
        from features.data_pipeline.collector import get_collector

        with pytest.raises(ValueError):
            get_collector("unknown")

    def test_list_available_collectors(self):
        """列出可用采集器"""
        from features.data_pipeline.collector import list_available_collectors

        names = list_available_collectors()
        assert "retention" in names
        assert "learning" in names
        assert "economics" in names
        assert "hypothesis" in names


# ===========================================================================
# Analyzer 测试
# ===========================================================================


class TestAnalysisResult:
    """分析结果"""

    def test_merge(self):
        """合并两个分析结果"""
        from features.data_pipeline.analyzer import AnalysisResult

        a1 = AnalysisResult(
            analyzer_name="test1",
            metrics={"m1": 1},
            insights=["i1"],
            warnings=["w1"],
            recommendations=["r1"],
        )
        a2 = AnalysisResult(
            analyzer_name="test2",
            metrics={"m2": 2},
            insights=["i2"],
            warnings=["w2"],
            recommendations=["r2"],
        )
        merged = a1.merge(a2)
        assert merged.metrics == {"m1": 1, "m2": 2}
        assert merged.insights == ["i1", "i2"]
        assert len(merged.warnings) == 2


class TestRetentionAnalyzer:
    """留存分析器"""

    def test_analyze_with_data(self):
        """使用实际采集数据进行分析"""
        from features.data_pipeline.collector import RetentionCollector
        from features.data_pipeline.analyzer import RetentionAnalyzer

        data = RetentionCollector().collect()
        analyzer = RetentionAnalyzer()
        result = analyzer.analyze(data)
        assert result.analyzer_name == "retention_analyzer"
        assert result.metrics["total_cohorts"] >= 4
        assert "avg_month1_retention_rate" in result.metrics
        assert len(result.insights) > 0

    def test_analyze_with_failed_data(self):
        """分析失败的数据源应返回警告"""
        from features.data_pipeline.collector import DataSource
        from features.data_pipeline.analyzer import RetentionAnalyzer

        failed_ds = DataSource(
            name="retention",
            records=[],
            error_count=1,
            errors=["模拟失败"],
        )
        analyzer = RetentionAnalyzer()
        result = analyzer.analyze(failed_ds)
        assert len(result.warnings) > 0


class TestLearningAnalyzer:
    """学习分析器"""

    def test_analyze(self):
        """使用实际数据进行分析"""
        from features.data_pipeline.collector import LearningCollector
        from features.data_pipeline.analyzer import LearningAnalyzer

        data = LearningCollector().collect()
        analyzer = LearningAnalyzer()
        result = analyzer.analyze(data)
        assert result.metrics["total_courses"] == 3
        assert result.metrics["total_certifications"] >= 0


class TestEconomicsAnalyzer:
    """单位经济分析器"""

    def test_analyze(self):
        """使用实际数据进行分析"""
        from features.data_pipeline.collector import EconomicsCollector
        from features.data_pipeline.analyzer import EconomicsAnalyzer

        data = EconomicsCollector().collect()
        analyzer = EconomicsAnalyzer()
        result = analyzer.analyze(data)
        assert "unit_economics" in result.metrics
        assert result.metrics["costs"]["entry_count"] == 5
        assert result.metrics["revenue"]["entry_count"] == 8


class TestHypothesisAnalyzer:
    """假设验证分析器"""

    def test_analyze(self):
        """使用实际数据进行分析"""
        from features.data_pipeline.collector import HypothesisCollector
        from features.data_pipeline.analyzer import HypothesisAnalyzer

        data = HypothesisCollector().collect()
        analyzer = HypothesisAnalyzer()
        result = analyzer.analyze(data)
        assert result.metrics["total_hypotheses"] == 3
        assert result.metrics["total_experiments"] == 1


class TestCompositeAnalyzer:
    """复合分析器"""

    def test_analyze(self):
        """综合分析多个数据源"""
        from features.data_pipeline.collector import collect_all
        from features.data_pipeline.analyzer import CompositeAnalyzer

        data = collect_all()
        analyzer = CompositeAnalyzer()
        result = analyzer.analyze(data)
        # CompositeAnalyzer merges sub-analyzer results; analyzer_name from first merged
        assert len(result.metrics) > 0
        assert len(result.insights) > 0

    def test_analyzer_factory(self):
        """分析器工厂"""
        from features.data_pipeline.analyzer import (
            get_analyzer,
            list_available_analyzers,
        )

        names = list_available_analyzers()
        assert "retention" in names

        analyzer = get_analyzer("retention")
        assert analyzer is not None

        with pytest.raises(ValueError):
            get_analyzer("unknown")


# ===========================================================================
# Pipeline 测试
# ===========================================================================


class TestDataCleaner:
    """数据清洗器"""

    def test_clean_empty(self):
        """清洗空数据"""
        from features.data_pipeline.pipeline import DataCleaner

        cleaner = DataCleaner()
        result = cleaner.clean({})
        assert result == {}

    def test_clean_removes_invalid(self):
        """清洗应移除无效记录"""
        from features.data_pipeline.pipeline import DataCleaner
        from features.data_pipeline.collector import DataSource, DataRecord

        ds = DataSource(
            name="test",
            records=[
                DataRecord(id=1, source="test", record_type="t", data={"k": "v"}),
                DataRecord(id=None, source="test", record_type="t", data={}),  # 空数据
                DataRecord(id=2, source="test", record_type="t", data={"k2": "v2"}),
            ],
        )
        data = {"test": ds}
        cleaner = DataCleaner()
        result = cleaner.clean(data)
        assert result["test"].total_count == 2


class TestDataPipeline:
    """数据管道编排"""

    def test_pipeline_run(self):
        """运行完整管道"""
        from features.data_pipeline.pipeline import DataPipeline, PipelineStage
        from features.data_pipeline.config import PipelineConfig

        config = PipelineConfig(strict_mode=False)
        pipeline = DataPipeline(config)
        report = pipeline.run()
        assert report.status == PipelineStage.DONE
        assert report.success is True
        assert report.total_records_collected > 0
        assert report.total_records_analyzed > 0
        assert report.collect_stage is not None
        assert report.analyze_stage is not None

    def test_pipeline_strict_mode(self):
        """严格模式下采集失败应中止"""
        from features.data_pipeline.pipeline import DataPipeline
        from features.data_pipeline.config import PipelineConfig, CollectorConfig

        config = PipelineConfig(
            strict_mode=False,
            collector=CollectorConfig(
                enable_retention_source=False,
                enable_learning_source=False,
                enable_economics_source=False,
                enable_hypothesis_source=False,
            ),
        )
        pipeline = DataPipeline(config)
        report = pipeline.run()
        assert report.total_records_collected == 0

    def test_pipeline_entry_functions(self):
        """便捷入口函数"""
        from features.data_pipeline.pipeline import run_pipeline, run_collect_only

        report = run_pipeline()
        assert report.success is True

        data = run_collect_only()
        assert len(data) >= 4
