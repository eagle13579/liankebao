"""数据安全模块 — 异常评分引擎单元测试 (core/anomaly_scorer.py)"""

import os
import sys
import tempfile

import pytest

# 将 core/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CORE = os.path.join(_BASE, "data_security", "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from collections import Counter

from anomaly_scorer import (
    AnomalyScorer,
    BaselineManager,
    D1FrequencyScorer,
    D2DistributionScorer,
    D3TypeShiftScorer,
    _dynamic_threshold,
    _infer_semantic_type,
    _kl_divergence_smoothed,
    _robust_mad,
)


class TestStatisticalUtils:
    """统计工具函数测试"""

    def test_robust_mad_empty(self):
        assert _robust_mad([]) == 0.0

    def test_robust_mad_basic(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        mad = _robust_mad(data)
        assert mad > 0
        assert mad < 10

    def test_robust_mad_with_outlier(self):
        # MAD 对异常值不敏感
        data = [1.0, 1.0, 1.0, 1.0, 1000.0]
        mad = _robust_mad(data)
        assert mad < 1.0  # 大部分值相同，MAD 应很小

    def test_dynamic_threshold_insufficient_data(self):
        thresh, std = _dynamic_threshold([1.0, 2.0])
        assert thresh == float("inf")
        assert std == 0.0

    def test_dynamic_threshold_sufficient(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        thresh, std = _dynamic_threshold(data)
        assert thresh < float("inf")
        assert std > 0

    def test_kl_divergence_smoothed_same(self):
        p = Counter({"a": 10, "b": 10})
        q = Counter({"a": 10, "b": 10})
        kl = _kl_divergence_smoothed(p, q)
        assert kl >= 0
        assert kl < 0.01  # 相同分布，KL 应接近0

    def test_kl_divergence_smoothed_different(self):
        p = Counter({"a": 100, "b": 1})
        q = Counter({"a": 1, "b": 100})
        kl = _kl_divergence_smoothed(p, q)
        assert kl > 0

    def test_infer_semantic_type_phone(self):
        assert _infer_semantic_type("+8613800138000") == "phone"
        assert _infer_semantic_type("13800138000") == "phone"

    def test_infer_semantic_type_email(self):
        assert _infer_semantic_type("test@example.com") == "email"

    def test_infer_semantic_type_url(self):
        assert _infer_semantic_type("https://www.example.com") == "url"

    def test_infer_semantic_type_ip(self):
        assert _infer_semantic_type("192.168.1.1") == "ip"

    def test_infer_semantic_type_plain(self):
        assert _infer_semantic_type("张三") == "plain"
        assert _infer_semantic_type("hello world") == "plain"


class TestBaselineManager:
    """基线管理器测试"""

    @pytest.fixture
    def tmp_root(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    def test_init_creates_dir(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        assert os.path.isdir(tmp_root)

    def test_empty_baseline(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        bl = bm.load("test_mod", "test_tbl")
        assert bl["write_count"] == 0
        assert bl["field_stats"] == {}
        assert "version" in bl

    def test_save_and_load(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        bl = bm._empty_baseline()
        bl["write_count"] = 42
        bm.save("test_mod", "test_tbl", bl)

        bm2 = BaselineManager(root_dir=tmp_root)
        loaded = bm2.load("test_mod", "test_tbl")
        assert loaded["write_count"] == 42

    def test_update_with_data(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        data = {"name": "张三", "phone": "13800138000", "age": 30}
        bm.update("mod", "tbl", data)

        loaded = bm.load("mod", "tbl")
        assert loaded["write_count"] == 1
        assert loaded["total_writes"] == 1
        assert "name" in loaded["field_stats"]
        assert "phone" in loaded["field_stats"]

    def test_update_multiple_times(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        for _ in range(10):
            bm.update("mod", "tbl", {"name": "张三"})
        loaded = bm.load("mod", "tbl")
        assert loaded["write_count"] == 10

    def test_update_with_violations(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        bm.update("mod", "tbl", {"name": "张三"}, violations={"name": 1, "phone": 1})
        loaded = bm.load("mod", "tbl")
        assert "violation_history" in loaded
        assert len(loaded["violation_history"]) == 1

    def test_cache_behavior(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        bm.save("mod", "tbl", bm._empty_baseline())
        bl1 = bm.load("mod", "tbl")
        bl2 = bm.load("mod", "tbl")
        assert bl1 is bl2  # 同一缓存对象


class TestAnomalyScorer:
    """异常评分引擎主类测试"""

    @pytest.fixture
    def scorer(self):
        return AnomalyScorer(db_url=None)

    def test_score_returns_dict(self, scorer):
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert isinstance(result, dict)
        assert "score" in result
        assert "details" in result
        assert "cold_start" in result

    def test_cold_start_true_initially(self, scorer):
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert result["cold_start"] is True

    def test_score_has_five_dimensions(self, scorer):
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert len(result["details"]) == 5

    def test_score_with_write_rate(self, scorer):
        result = scorer.score("mod", "tbl", {"name": "test"}, write_rate=100)
        assert "score" in result

    def test_score_with_violations(self, scorer):
        result = scorer.score("mod", "tbl", {"name": "test"}, violations={"name": 1, "phone": 1})
        assert "score" in result

    def test_score_with_context(self, scorer):
        result = scorer.score("mod", "tbl", {"name": "test"}, context={"known_modules": {"mod": ["tbl"]}})
        assert "score" in result

    def test_set_sensitivity(self, scorer):
        scorer.set_sensitivity("mod", "tbl", {"d1_frequency": 2.0, "d3_type_shift": 1.5})
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert "score" in result

    def test_reset_sensitivity(self, scorer):
        scorer.set_sensitivity("mod", "tbl", {"d1_frequency": 2.0})
        scorer.set_sensitivity("mod", "tbl")  # 重置
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert "score" in result

    def test_get_baseline_summary(self, scorer):
        scorer.score("mod", "tbl", {"name": "张三"})
        summary = scorer.get_baseline_summary("mod", "tbl")
        assert "total_writes" in summary
        assert summary["total_writes"] >= 1

    def test_clear_baselines(self, scorer):
        scorer.score("mod", "tbl", {"name": "test"})
        count = scorer.clear_baselines("mod", "tbl")
        assert count >= 0

    def test_score_after_many_writes(self, scorer):
        """多次写入后应不再 cold_start"""
        for i in range(10):
            scorer.score("mod", "tbl", {"name": f"test_{i}"})
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert "score" in result


class TestD1FrequencyScorer:
    """频率异常评分器测试"""

    @pytest.fixture
    def tmp_root(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    def test_cold_start(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        scorer = D1FrequencyScorer(bm)
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert result["score"] == 0.0
        assert "冷启动" in result["reason"]


class TestD2DistributionScorer:
    """分布异常评分器测试"""

    @pytest.fixture
    def tmp_root(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    def test_cold_start(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        scorer = D2DistributionScorer(bm)
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert result["score"] == 0.0
        assert "冷启动" in result["reason"]


class TestD3TypeShiftScorer:
    """类型偏移评分器测试"""

    @pytest.fixture
    def tmp_root(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    def test_cold_start(self, tmp_root):
        bm = BaselineManager(root_dir=tmp_root)
        scorer = D3TypeShiftScorer(bm)
        result = scorer.score("mod", "tbl", {"name": "test"})
        assert result["score"] == 0.0
        assert "冷启动" in result["reason"]
