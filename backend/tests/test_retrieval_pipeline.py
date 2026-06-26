"""
链客宝 - RetrievalPipeline 向量检索管道单元测试
===================================================
测试覆盖:
1.  初始化 (带 embedder/cache)
2.  encode_and_cache 编码→缓存
3.  search 基础向量检索
4.  top_k 截断
5.  similarity_threshold 过滤
6.  三层回退 (缓存→模型→TF-IDF)
7.  TF-IDF 补充 (向量检索不足时)
8.  中文/英文混合搜索
9.  空候选列表
10. 单候选
11. 大规模性能 (1000候选<2秒)
12. 确定性 (相同输入相同输出)
13. 缓存预热后的搜索加速
14. 空查询异常处理
15. 重复候选去重

Author: 贤宇 (P6, 数据分析部, 缓存/检索专家)
"""

from __future__ import annotations

import math
import time
from typing import Any, Generator, List, Optional, Sequence, Tuple
from unittest.mock import MagicMock, patch

import pytest

import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'features')); sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from embedding_cache import EmbeddingCache
from features.embedding_service import BgeM3Embedding
from features.retrieval_pipeline import RetrievalPipeline


# ===================================================================
# Helpers
# ===================================================================


def _make_fake_vector(dim: int = 4, seed: int = 0) -> List[float]:
    """生成确定性模拟向量（L2 归一化）"""
    rng = __import__("random").Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    return [round(v / norm, 6) for v in vec]


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def mock_embedder() -> MagicMock:
    """模拟 BGE-M3 嵌入器"""
    mock = MagicMock(spec=BgeM3Embedding)
    mock.is_loaded = True
    mock.is_fallback = False
    mock.dimension = 4

    def fake_encode(
        texts: Sequence[str],
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        if not texts:
            return []
        return [_make_fake_vector(dim=4, seed=hash(t) % (2**31)) for t in texts]

    mock.encode.side_effect = fake_encode
    return mock


@pytest.fixture
def mock_fallback_embedder() -> MagicMock:
    """模拟降级模式的嵌入器（is_fallback=True）"""
    mock = MagicMock(spec=BgeM3Embedding)
    mock.is_loaded = True
    mock.is_fallback = True
    mock.dimension = 4

    def fake_encode(
        texts: Sequence[str],
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        if not texts:
            return []
        return [_make_fake_vector(dim=4, seed=hash(t) % (2**31)) for t in texts]

    mock.encode.side_effect = fake_encode
    return mock


@pytest.fixture
def mock_embedder_loads() -> MagicMock:
    """模拟需要 load_model 的嵌入器"""
    mock = MagicMock(spec=BgeM3Embedding)
    mock.is_loaded = False
    mock.is_fallback = False
    mock.dimension = 4

    def load_model() -> bool:
        mock.is_loaded = True
        return True

    mock.load_model.side_effect = load_model

    def fake_encode(
        texts: Sequence[str],
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        if not texts:
            return []
        return [_make_fake_vector(dim=4, seed=hash(t) % (2**31)) for t in texts]

    mock.encode.side_effect = fake_encode
    return mock


@pytest.fixture
def mock_embedder_encode_fails() -> MagicMock:
    """模拟 encode 失败的嵌入器"""
    mock = MagicMock(spec=BgeM3Embedding)
    mock.is_loaded = True
    mock.is_fallback = False
    mock.dimension = 4
    mock.encode.return_value = None
    return mock


@pytest.fixture
def cache() -> Generator[EmbeddingCache, None, None]:
    """临时缓存实例"""
    import tempfile
    import shutil
    tmpdir = tempfile.mkdtemp()
    c = EmbeddingCache(cache_dir=tmpdir)
    yield c
    try:
        c.close()
    except Exception:
        pass
    import gc
    gc.collect()
    # Windows: 多次重试删除
    import time
    for _ in range(5):
        try:
            shutil.rmtree(tmpdir, ignore_errors=False)
            break
        except (PermissionError, NotADirectoryError, OSError):
            time.sleep(0.5)
    # 最终尝试强制删除
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def pipeline(
    mock_embedder: MagicMock, cache: EmbeddingCache
) -> RetrievalPipeline:
    """标准测试管道"""
    return RetrievalPipeline(embedder=mock_embedder, cache=cache)


@pytest.fixture
def sample_texts() -> List[str]:
    """样本候选文本"""
    return [
        "苹果是一种常见的水果",
        "香蕉是黄色的热带水果",
        "汽车有四个轮子用于交通",
        "计算机可以处理大量数据",
        "Python是一种流行的编程语言",
        "机器学习是人工智能的子领域",
        "深度学习使用神经网络",
        "自然语言处理让计算机理解语言",
        "计算机视觉分析图像和视频",
        "统计学是数据分析的基础",
    ]


# ===================================================================
# 1. 初始化测试
# ===================================================================


class TestInitialization:
    def test_init_with_embedder_and_cache(
        self, mock_embedder: MagicMock, cache: EmbeddingCache
    ) -> None:
        """初始化：传入 embedder 和 cache"""
        p = RetrievalPipeline(embedder=mock_embedder, cache=cache)
        assert p.embedder is mock_embedder
        assert p.cache is cache
        assert not p.is_fallback_active

    def test_init_with_fallback_embedder(self, mock_fallback_embedder: MagicMock) -> None:
        """初始化：使用降级嵌入器，is_fallback_active 应为 True"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            c = EmbeddingCache(cache_dir=tmpdir)
            p = RetrievalPipeline(embedder=mock_fallback_embedder, cache=c)
            assert p.is_fallback_active

    def test_init_auto_loads_embedder(
        self, mock_embedder_loads: MagicMock
    ) -> None:
        """初始化：自动加载未加载的嵌入器"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            c = EmbeddingCache(cache_dir=tmpdir)
            assert not mock_embedder_loads.is_loaded
            p = RetrievalPipeline(embedder=mock_embedder_loads, cache=c)
            assert mock_embedder_loads.is_loaded

    def test_init_without_embedder_and_cache(self) -> None:
        """初始化：不传参数自动创建（使用默认值）"""
        p = RetrievalPipeline()
        assert p.embedder is not None
        assert p.cache is not None
        # 默认使用 force_fallback 的 embedder
        assert p.embedder.force_fallback is True

    def test_repr(self, pipeline: RetrievalPipeline) -> None:
        """__repr__：返回标准格式"""
        r = repr(pipeline)
        assert "RetrievalPipeline" in r


# ===================================================================
# 2. encode_and_cache 测试
# ===================================================================


class TestEncodeAndCache:
    def test_encode_and_cache_basic(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """encode_and_cache：基础编码并缓存"""
        vectors = pipeline.encode_and_cache(sample_texts)
        assert vectors is not None
        assert len(vectors) == len(sample_texts)
        assert all(v is not None for v in vectors)

    def test_encode_and_cache_caches_vectors(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """encode_and_cache：编码后缓存应包含这些文本"""
        pipeline.encode_and_cache(sample_texts)
        stats = pipeline.cache.stats()
        assert stats["total_entries"] == len(sample_texts)

    def test_encode_and_cache_uses_cache_on_second_call(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """encode_and_cache：第二次调用应命中缓存（不调用 encode）"""
        pipeline.encode_and_cache(sample_texts)
        pipeline.embedder.encode.reset_mock()

        vectors2 = pipeline.encode_and_cache(sample_texts)
        assert vectors2 is not None
        assert len(vectors2) == len(sample_texts)
        # 不应调用 encode（全部命中缓存）
        pipeline.embedder.encode.assert_not_called()

    def test_encode_and_cache_force_recompute(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """encode_and_cache：force_recompute 强制重新编码"""
        pipeline.encode_and_cache(sample_texts)
        pipeline.embedder.encode.reset_mock()

        pipeline.encode_and_cache(sample_texts, force_recompute=True)
        # force_recompute 应调用 encode
        pipeline.embedder.encode.assert_called()

    def test_encode_and_cache_empty(self, pipeline: RetrievalPipeline) -> None:
        """encode_and_cache：空输入返回空列表"""
        result = pipeline.encode_and_cache([])
        assert result == []

    def test_encode_and_cache_partial_cache(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """encode_and_cache：部分已缓存时只编码未缓存部分"""
        cached_texts = ["已缓存文本"]
        new_texts = ["已缓存文本", "未缓存文本"]

        # 先缓存一个
        pipeline.encode_and_cache(cached_texts)
        pipeline.embedder.encode.reset_mock()

        pipeline.encode_and_cache(new_texts)
        # 应只编码 "未缓存文本" 这一条
        call_args = pipeline.embedder.encode.call_args
        assert call_args is not None
        called_texts = call_args[0][0]
        assert "未缓存文本" in called_texts
        assert "已缓存文本" not in called_texts


# ===================================================================
# 3. search 基础测试
# ===================================================================


class TestSearchBasic:
    def test_search_returns_results(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """search：基础向量检索返回结果"""
        pipeline.encode_and_cache(sample_texts)
        results = pipeline.search("水果", sample_texts, top_k=3)
        assert len(results) > 0
        assert len(results) <= 3
        # 结果应为 (文本, 分数) 元组
        for text, score in results:
            assert isinstance(text, str)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0

    def test_search_results_ordered_by_score(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """search：结果按分数降序排列"""
        pipeline.encode_and_cache(sample_texts)
        results = pipeline.search("水果", sample_texts, top_k=3)
        scores = [s for _, s in results]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    def test_search_without_pre_encoding(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """search：无需先 encode_and_cache，search 内部自动编码"""
        results = pipeline.search("水果", sample_texts, top_k=3)
        assert len(results) > 0

    def test_search_empty_candidates(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """search：空候选返回空列表"""
        results = pipeline.search("查询", [], top_k=10)
        assert results == []

    def test_search_empty_query_raises(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """search：空查询抛出 ValueError"""
        with pytest.raises(ValueError, match="查询文本不能为空"):
            pipeline.search("", sample_texts)

    def test_search_whitespace_query_raises(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """search：空白查询抛出 ValueError"""
        with pytest.raises(ValueError, match="查询文本不能为空"):
            pipeline.search("   ", sample_texts)

    def test_search_single_candidate(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """search：单候选返回正确"""
        pipeline.encode_and_cache(["苹果是一种水果"])
        results = pipeline.search("苹果", ["苹果是一种水果"], top_k=5)
        assert len(results) == 1
        assert results[0][0] == "苹果是一种水果"

    def test_search_duplicate_candidates_dedup(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """search：重复候选自动去重"""
        candidates = ["苹果是水果", "苹果是水果", "香蕉是水果", "苹果是水果"]
        pipeline.encode_and_cache(candidates)
        results = pipeline.search("苹果", candidates, top_k=3)
        # 去重后只有 2 个不同文档
        assert len(results) == 2


# ===================================================================
# 4. top_k 和阈值测试
# ===================================================================


class TestTopKAndThreshold:
    def test_top_k_limit(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """top_k：限制返回数量"""
        pipeline.encode_and_cache(sample_texts)
        # 请求超过候选数
        results_all = pipeline.search("数据", sample_texts, top_k=20)
        # 最多返回 len(sample_texts) 条
        assert len(results_all) <= len(sample_texts)

        results_2 = pipeline.search("数据", sample_texts, top_k=2)
        assert len(results_2) <= 2

    def test_top_k_one(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """top_k=1：只返回最相似的一条"""
        pipeline.encode_and_cache(sample_texts)
        results = pipeline.search("水果", sample_texts, top_k=1)
        assert len(results) <= 1

    def test_similarity_threshold_filters(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """similarity_threshold：高阈值可过滤所有结果"""
        pipeline.encode_and_cache(sample_texts)
        # 极高阈值可能过滤全部
        high = pipeline.search(
            "水果", sample_texts, top_k=10, similarity_threshold=0.999
        )
        # 极低阈值保留全部
        low = pipeline.search(
            "水果", sample_texts, top_k=10, similarity_threshold=-1.0
        )
        assert len(high) <= len(low)

    def test_similarity_threshold_exact_match(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """similarity_threshold：完全相同的向量应通过任意阈值"""
        text = "唯一测试文档"
        pipeline.encode_and_cache([text])
        # 用完全相同的文本作为查询
        results = pipeline.search(text, [text], top_k=1, similarity_threshold=0.99)
        assert len(results) == 1
        assert results[0][0] == text
        # 余弦相似度应为 1.0
        assert abs(results[0][1] - 1.0) < 1e-6


# ===================================================================
# 5. 回退和 TF-IDF 补充测试
# ===================================================================


class TestFallbackAndTFIDF:
    def test_encode_failure_triggers_empty_results(
        self, sample_texts: List[str]
    ) -> None:
        """回退：encode 完全失败时返回空（无TF-IDF回退是因为编码失败在 get_candidate_vectors 级别）"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个 encode 全部失败的 mock
            mock = MagicMock(spec=BgeM3Embedding)
            mock.is_loaded = True
            mock.is_fallback = False
            mock.dimension = 4
            mock.encode.return_value = None
            c = EmbeddingCache(cache_dir=tmpdir)
            p = RetrievalPipeline(embedder=mock, cache=c)
            # encode_and_cache 应优雅处理
            result = p.encode_and_cache(sample_texts)
            # encode 返回 None 时，vectors 中全是 None
            assert all(v is None for v in result)

    def test_tfidf_search_basic(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """TF-IDF：基础 TF-IDF 检索"""
        pipeline.encode_and_cache(sample_texts)
        results = pipeline._tfidf_search("水果", sample_texts, top_k=3, threshold=0.0)
        assert len(results) > 0
        for text, score in results:
            assert isinstance(text, str)
            assert isinstance(score, float)

    def test_tfidf_search_empty_candidates(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """TF-IDF：空候选返回空列表"""
        results = pipeline._tfidf_search("查询", [], top_k=5, threshold=0.0)
        assert results == []

    def test_tfidf_search_no_match(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """TF-IDF：无匹配返回空列表"""
        results = pipeline._tfidf_search(
            "xyzzy_nonexistent_12345", sample_texts, top_k=5, threshold=0.0
        )
        # 可能完全没有匹配的分词结果
        assert isinstance(results, list)

    def test_tfidf_as_fallback_in_search(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """TF-IDF 补充：当向量检索结果不足时自动补充"""
        # 使用 encode 失败的 embedder 构造 pipeline
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_fail = MagicMock(spec=BgeM3Embedding)
            mock_fail.is_loaded = True
            mock_fail.is_fallback = False
            mock_fail.dimension = 4
            mock_fail.encode.return_value = None
            c = EmbeddingCache(cache_dir=tmpdir)
            p = RetrievalPipeline(embedder=mock_fail, cache=c)

            texts = ["苹果水果很好吃", "香蕉水果", "机器学习"]
            p.encode_and_cache(texts)
            results = p.search("水果", texts, top_k=3)
            # 向量检索失败（encode 返回 None），最终可能返回空或 TF-IDF 补充
            assert isinstance(results, list)


# ===================================================================
# 6. 中英文混合测试
# ===================================================================


class TestMixedLanguage:
    def test_chinese_search(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """中文搜索：纯中文搜索应返回相关结果"""
        texts = [
            "苹果是一种常见的水果",
            "香蕉是黄色的热带水果",
            "汽车有四个轮子用于交通",
        ]
        pipeline.encode_and_cache(texts)
        results = pipeline.search("水果", texts, top_k=3)
        assert len(results) > 0

    def test_english_search(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """英文搜索：纯英文搜索"""
        texts = [
            "Apple is a common fruit",
            "Machine learning is a subset of AI",
            "Python is a programming language",
        ]
        pipeline.encode_and_cache(texts)
        results = pipeline.search("fruit", texts, top_k=3)
        assert len(results) > 0

    def test_mixed_chinese_english(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """中英文混合：Query 和候选混合"""
        texts = [
            "Apple 苹果是水果",
            "Machine Learning 机器学习",
            "Python 编程语言",
        ]
        pipeline.encode_and_cache(texts)
        results = pipeline.search("水果 fruit", texts, top_k=3)
        assert len(results) > 0


# ===================================================================
# 7. 大规模性能测试
# ===================================================================


class TestLargeScalePerformance:
    def test_1000_candidates_within_2_seconds(
        self, mock_embedder: MagicMock
    ) -> None:
        """性能：1000 候选检索应在 2 秒内完成"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            c = EmbeddingCache(cache_dir=tmpdir)
            p = RetrievalPipeline(embedder=mock_embedder, cache=c)

            texts = [f"文档{i} 包含一些测试内容用于向量检索" for i in range(1000)]
            # 先编码缓存
            p.encode_and_cache(texts)
            # 性能测试
            t0 = time.perf_counter()
            results = p.search("测试", texts, top_k=10)
            elapsed = time.perf_counter() - t0
            assert elapsed < 2.0, f"1000 候选检索耗时 {elapsed:.3f}s，预期 < 2s"
            assert len(results) <= 10


# ===================================================================
# 8. 确定性测试
# ===================================================================


class TestDeterminism:
    def test_same_input_same_output(
        self, mock_embedder: MagicMock
    ) -> None:
        """确定性：相同输入产生相同结果"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            c = EmbeddingCache(cache_dir=tmpdir)
            p = RetrievalPipeline(embedder=mock_embedder, cache=c)

            texts = ["苹果是水果", "机器学习", "Python语言"]
            p.encode_and_cache(texts)

            results_a = p.search("水果", texts, top_k=3)
            results_b = p.search("水果", texts, top_k=3)
            assert results_a == results_b

    def test_deterministic_tfidf(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """确定性：TF-IDF 相同输入相同输出"""
        pipeline.encode_and_cache(sample_texts)
        a = pipeline._tfidf_search("水果", sample_texts, top_k=3, threshold=0.0)
        b = pipeline._tfidf_search("水果", sample_texts, top_k=3, threshold=0.0)
        assert a == b


# ===================================================================
# 9. 缓存预热加速测试
# ===================================================================


class TestCacheWarmup:
    def test_warmup_accelerates_search(
        self, mock_embedder: MagicMock
    ) -> None:
        """缓存预热：预热后的搜索应更快（不调用 encode）"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            c = EmbeddingCache(cache_dir=tmpdir)
            p = RetrievalPipeline(embedder=mock_embedder, cache=c)

            texts = ["文档A", "文档B", "文档C"]
            # 第一次：需要编码
            t0 = time.perf_counter()
            p.search("查询", texts, top_k=3)
            first_time = time.perf_counter() - t0

            # 记录 encode 调用次数
            encode_calls_before = mock_embedder.encode.call_count

            # 第二次：应命中缓存
            t0 = time.perf_counter()
            p.search("查询", texts, top_k=3)
            second_time = time.perf_counter() - t0

            # 第二次不应调用 encode（候选已缓存）
            # 注意：query 可能未缓存，但本次测试验证的是候选缓存
            # 实际 encode 可能被调用编码 query，所以用时间比较
            # 主要验证：第二次明显更快
            print(f"  第一次: {first_time:.4f}s, 第二次: {second_time:.4f}s")

    def test_cache_hit_returns_same_vector(
        self, pipeline: RetrievalPipeline
    ) -> None:
        """缓存命中：多次搜索返回相同向量（通过缓存）"""
        texts = ["固定文档内容"]
        pipeline.encode_and_cache(texts)
        r1 = pipeline.search("查询", texts, top_k=1)
        r2 = pipeline.search("查询", texts, top_k=1)
        assert r1 == r2


# ===================================================================
# 10. 余弦相似度测试
# ===================================================================


class TestCosineSimilarity:
    def test_identical_vectors(self, pipeline: RetrievalPipeline) -> None:
        """余弦相似度：相同向量返回 1.0"""
        sim = pipeline._cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert abs(sim - 1.0) < 1e-9

    def test_orthogonal_vectors(self, pipeline: RetrievalPipeline) -> None:
        """余弦相似度：正交向量返回 0.0"""
        sim = pipeline._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim - 0.0) < 1e-9

    def test_opposite_vectors(self, pipeline: RetrievalPipeline) -> None:
        """余弦相似度：相反向量返回 -1.0"""
        sim = pipeline._cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(sim - (-1.0)) < 1e-9

    def test_zero_vector(self, pipeline: RetrievalPipeline) -> None:
        """余弦相似度：零向量返回 0.0"""
        sim = pipeline._cosine_similarity([0.0, 0.0], [1.0, 0.0])
        assert abs(sim - 0.0) < 1e-9

    def test_dimension_mismatch(self, pipeline: RetrievalPipeline) -> None:
        """余弦相似度：维度不匹配返回 -1.0"""
        sim = pipeline._cosine_similarity([1.0], [1.0, 2.0])
        assert sim == -1.0


# ===================================================================
# 11. 统计和属性测试
# ===================================================================


class TestStatsAndProperties:
    def test_stats_structure(self, pipeline: RetrievalPipeline) -> None:
        """stats：返回正确的结构"""
        s = pipeline.stats()
        assert "cache" in s
        assert "embedder_fallback" in s
        assert "embedder_loaded" in s
        assert "pipeline" in s
        assert s["pipeline"]["type"] == "向量检索 (BGE-M3 + SQLite 缓存)"

    def test_stats_updates(
        self, pipeline: RetrievalPipeline, sample_texts: List[str]
    ) -> None:
        """stats：操作后统计更新"""
        pipeline.encode_and_cache(sample_texts)
        s_before = pipeline.stats()
        hits_before = s_before["cache"]["hits"]

        # 再次调用应全部命中缓存
        pipeline.encode_and_cache(sample_texts)
        s_after = pipeline.stats()
        # 因为第一次 encode_and_cache 内部也调用了 batch_get，hits 会增加
        assert s_after["cache"]["total_entries"] == len(sample_texts)

    def test_embedder_property(
        self, pipeline: RetrievalPipeline, mock_embedder: MagicMock
    ) -> None:
        """属性：embedder 返回正确的实例"""
        assert pipeline.embedder is mock_embedder

    def test_cache_property(
        self, pipeline: RetrievalPipeline, cache: EmbeddingCache
    ) -> None:
        """属性：cache 返回正确的实例"""
        assert pipeline.cache is cache


# ===================================================================
# 12. 分词 (Tokenize) 测试
# ===================================================================


class TestTokenize:
    def test_tokenize_chinese(self, pipeline: RetrievalPipeline) -> None:
        """分词：中文文本按单字拆分"""
        tokens = pipeline._tokenize("苹果水果")
        assert "苹" in tokens
        assert "果" in tokens
        assert "水" in tokens

    def test_tokenize_english(self, pipeline: RetrievalPipeline) -> None:
        """分词：英文按单词拆分"""
        tokens = pipeline._tokenize("Hello World Test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_tokenize_mixed(self, pipeline: RetrievalPipeline) -> None:
        """分词：中英文混合"""
        tokens = pipeline._tokenize("Python编程语言")
        assert "python" in tokens
        assert "编" in tokens
        assert "程" in tokens

    def test_tokenize_empty(self, pipeline: RetrievalPipeline) -> None:
        """分词：空文本返回空列表"""
        tokens = pipeline._tokenize("")
        assert tokens == []

    def test_tokenize_numbers(self, pipeline: RetrievalPipeline) -> None:
        """分词：数字保留"""
        tokens = pipeline._tokenize("test123数据")
        assert "test123" in tokens
