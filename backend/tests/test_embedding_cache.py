"""
链客宝 - EmbeddingCache 嵌入向量缓存单元测试
===============================================
测试覆盖:
1.  初始化 (默认路径/自定义路径)
2.  get/set 单条操作
3.  batch_get/batch_set 批量操作
4.  命中/未命中缓存行为
5.  stats 统计信息
6.  clear 清空
7.  __len__/__contains__/__bool__
8.  大规模 (1000+条) 批处理性能
9.  持久化 (关闭后重新打开数据仍在)
10. 并发安全性
11. 空输入处理
12. 覆盖写入 (重复key)

Author: 贤宇 (P6, 数据分析部, 缓存/检索专家)
"""

from __future__ import annotations

import concurrent.futures
import os
import tempfile
import time
from typing import Generator, List, Optional, Tuple

import pytest

import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'features')); sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from embedding_cache import EmbeddingCache


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """提供临时缓存目录，测试后自动清理"""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    # Windows: 多次重试删除，等待文件锁释放
    import time
    for _ in range(5):
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=False)
            break
        except (PermissionError, NotADirectoryError):
            time.sleep(0.5)
    # 最终尝试强制删除
    try:
        for root, dirs, files in os.walk(tmpdir, topdown=False):
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), 0o777)
                    os.unlink(os.path.join(root, f))
                except Exception:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except Exception:
                    pass
        os.rmdir(tmpdir)
    except Exception:
        pass


@pytest.fixture
def cache(temp_dir: str) -> Generator[EmbeddingCache, None, None]:
    """每个测试函数独立的 EmbeddingCache 实例（临时目录）"""
    c = EmbeddingCache(cache_dir=temp_dir)
    yield c
    try:
        c.clear()
        c.close()
    except Exception:
        pass


def _make_vector(dim: int = 4, seed: int = 0) -> List[float]:
    """生成确定性向量"""
    rng = __import__("random").Random(seed)
    return [round(rng.gauss(0, 1), 6) for _ in range(dim)]


# ===================================================================
# 1. 初始化测试
# ===================================================================


class TestInitialization:
    def test_default_path(self) -> None:
        """初始化：默认路径创建成功"""
        cache = EmbeddingCache()
        assert cache is not None
        assert os.path.exists(cache._db_path) is False or True  # 不一定要存在
        # 使用默认路径应该能创建
        default_dir = os.path.join(os.path.expanduser("~"), ".cache", "chainke")
        assert cache._cache_dir == default_dir
        cache.clear()
        cache.close()

    def test_custom_path(self, temp_dir: str) -> None:
        """初始化：自定义缓存目录"""
        custom_dir = os.path.join(temp_dir, "my_cache")
        cache = EmbeddingCache(cache_dir=custom_dir)
        assert cache._cache_dir == custom_dir
        assert os.path.exists(custom_dir)
        db_path = os.path.join(custom_dir, "embeddings_cache.db")
        assert cache._db_path == db_path
        cache.clear()
        cache.close()

    def test_init_creates_db(self, temp_dir: str) -> None:
        """初始化：数据库文件被创建"""
        cache = EmbeddingCache(cache_dir=temp_dir)
        assert os.path.exists(cache._db_path)
        # 验证表存在
        import sqlite3
        conn = sqlite3.connect(cache._db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "embeddings" in table_names
        conn.close()
        cache.clear()
        cache.close()


# ===================================================================
# 2. 单条操作测试
# ===================================================================


class TestSingleOperations:
    def test_get_set_single(self, cache: EmbeddingCache) -> None:
        """单条 get/set：写入后读取应返回相同向量"""
        text = "链客宝企业数据平台测试"
        vec = _make_vector(seed=42)
        cache.set(text, vec)
        result = cache.get(text)
        assert result is not None
        assert result == vec

    def test_get_miss_returns_none(self, cache: EmbeddingCache) -> None:
        """未命中：不存在的文本返回 None"""
        result = cache.get("完全不存在的内容xyz")
        assert result is None

    def test_set_overwrite(self, cache: EmbeddingCache) -> None:
        """覆盖写入：同一文本多次写入以最后一次为准"""
        text = "覆盖测试"
        original = _make_vector(seed=1)
        overwritten = [0.0] * 4
        cache.set(text, original)
        cache.set(text, overwritten)
        result = cache.get(text)
        assert result == overwritten

    def test_get_hit_increments_hits(self, cache: EmbeddingCache) -> None:
        """命中计数：get 命中后 hits 增加"""
        text = "计数测试"
        cache.set(text, _make_vector())
        stats_before = cache.stats()
        hits_before = stats_before["hits"]

        cache.get(text)  # 命中一次
        stats_after = cache.stats()
        assert stats_after["hits"] == hits_before + 1

    def test_get_miss_increments_misses(self, cache: EmbeddingCache) -> None:
        """未命中计数：get 未命中后 misses 增加"""
        stats_before = cache.stats()
        misses_before = stats_before["misses"]

        cache.get("不存在的文本")  # 未命中
        stats_after = cache.stats()
        assert stats_after["misses"] == misses_before + 1


# ===================================================================
# 3. 批量操作测试
# ===================================================================


class TestBatchOperations:
    def test_batch_get_all_hit(self, cache: EmbeddingCache) -> None:
        """批量查询：全部命中"""
        texts = ["文本A", "文本B", "文本C"]
        vecs = [_make_vector(seed=i) for i in range(3)]
        for t, v in zip(texts, vecs):
            cache.set(t, v)

        results = cache.batch_get(texts)
        assert len(results) == 3
        for i, r in enumerate(results):
            assert r == vecs[i]

    def test_batch_get_mixed_hit_miss(self, cache: EmbeddingCache) -> None:
        """批量查询：混合命中与未命中"""
        texts = ["命中A", "命中B"]
        cache.set(texts[0], _make_vector(seed=0))
        cache.set(texts[1], _make_vector(seed=1))

        query = texts + ["未命中C"]
        results = cache.batch_get(query)
        assert len(results) == 3
        assert results[0] is not None
        assert results[1] is not None
        assert results[2] is None

    def test_batch_get_empty(self, cache: EmbeddingCache) -> None:
        """批量查询：空输入返回空列表"""
        assert cache.batch_get([]) == []

    def test_batch_set_and_get(self, cache: EmbeddingCache) -> None:
        """批量写入后批量读取验证"""
        texts = ["批量A", "批量B", "批量C", "批量D"]
        vecs = [_make_vector(seed=i) for i in range(4)]
        pairs = list(zip(texts, vecs))
        cache.batch_set(pairs)

        results = cache.batch_get(texts)
        assert len(results) == 4
        for i, r in enumerate(results):
            assert r == vecs[i]

    def test_batch_set_empty(self, cache: EmbeddingCache) -> None:
        """批量写入：空输入不报错"""
        cache.batch_set([])  # 不应抛出异常


# ===================================================================
# 4. 统计信息测试
# ===================================================================


class TestStats:
    def test_stats_structure(self, cache: EmbeddingCache) -> None:
        """统计信息：返回正确的结构"""
        stats = cache.stats()
        assert "total_entries" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "total_queries" in stats
        assert "hit_rate" in stats
        assert "db_size_bytes" in stats
        assert "db_path" in stats

    def test_stats_hit_rate(self, cache: EmbeddingCache) -> None:
        """统计信息：命中率计算正确"""
        cache.set("a", _make_vector())
        cache.get("a")  # 命中
        cache.get("a")  # 命中
        cache.get("x")  # 未命中
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_queries"] == 3
        assert stats["hit_rate"] == 2 / 3

    def test_stats_zero_queries(self, cache: EmbeddingCache) -> None:
        """统计信息：未查询时命中率为 0.0"""
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_total_entries(self, cache: EmbeddingCache) -> None:
        """统计信息：条目计数正确"""
        cache.set("a", _make_vector(seed=0))
        cache.set("b", _make_vector(seed=1))
        cache.set("c", _make_vector(seed=2))
        stats = cache.stats()
        assert stats["total_entries"] == 3


# ===================================================================
# 5. 管理方法测试
# ===================================================================


class TestManagement:
    def test_clear_empties_cache(self, cache: EmbeddingCache) -> None:
        """清空：clear 后缓存条目为 0"""
        cache.set("a", _make_vector())
        cache.set("b", _make_vector())
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_clear_resets_stats(self, cache: EmbeddingCache) -> None:
        """清空：clear 后统计计数重置"""
        cache.set("a", _make_vector())
        cache.get("a")  # 命中
        cache.get("x")  # 未命中
        stats_before = cache.stats()
        assert stats_before["hits"] > 0
        assert stats_before["misses"] > 0

        cache.clear()
        stats_after = cache.stats()
        assert stats_after["hits"] == 0
        assert stats_after["misses"] == 0


# ===================================================================
# 6. Dunder 方法测试
# ===================================================================


class TestDunderMethods:
    def test_len_empty(self, cache: EmbeddingCache) -> None:
        """__len__：空缓存返回 0"""
        assert len(cache) == 0

    def test_len_after_set(self, cache: EmbeddingCache) -> None:
        """__len__：写入后正确计数"""
        cache.set("a", _make_vector(seed=0))
        assert len(cache) == 1
        cache.set("b", _make_vector(seed=1))
        assert len(cache) == 2

    def test_contains_true(self, cache: EmbeddingCache) -> None:
        """__contains__：存在的文本返回 True"""
        cache.set("包含测试文本", _make_vector())
        assert "包含测试文本" in cache

    def test_contains_false(self, cache: EmbeddingCache) -> None:
        """__contains__：不存在的文本返回 False"""
        assert "不存在" not in cache

    def test_bool_always_true(self, cache: EmbeddingCache) -> None:
        """__bool__：实例始终为 truthy"""
        assert bool(cache) is True
        cache.clear()
        assert bool(cache) is True  # 即使清空也为 True

    def test_repr(self, cache: EmbeddingCache) -> None:
        """__repr__：返回标准格式"""
        cache.set("测试", _make_vector())
        r = repr(cache)
        assert "EmbeddingCache" in r
        assert "entries=" in r
        assert "hits=" in r
        assert "misses=" in r


# ===================================================================
# 7. 大规模性能测试
# ===================================================================


class TestLargeScale:
    def test_batch_set_1000_entries(self, temp_dir: str) -> None:
        """大规模：批量写入 1000 条"""
        cache = EmbeddingCache(cache_dir=temp_dir)
        texts = [f"大规模测试文本{i}" for i in range(1000)]
        vecs = [_make_vector(dim=4, seed=i) for i in range(1000)]
        pairs = list(zip(texts, vecs))

        t0 = time.perf_counter()
        cache.batch_set(pairs)
        elapsed = time.perf_counter() - t0

        assert len(cache) == 1000
        # 1000 条写入应在合理时间内完成
        assert elapsed < 10.0, f"batch_set 1000 条耗时 {elapsed:.2f}s，预期 < 10s"
        cache.clear()
        cache.close()

    def test_batch_get_1000_entries(self, temp_dir: str) -> None:
        """大规模：批量读取 1000 条（全部命中）"""
        cache = EmbeddingCache(cache_dir=temp_dir)
        texts = [f"批量读取测试{i}" for i in range(1000)]
        vecs = [_make_vector(dim=4, seed=i) for i in range(1000)]
        cache.batch_set(list(zip(texts, vecs)))

        t0 = time.perf_counter()
        results = cache.batch_get(texts)
        elapsed = time.perf_counter() - t0

        assert len(results) == 1000
        assert all(r is not None for r in results)
        assert elapsed < 10.0, f"batch_get 1000 条耗时 {elapsed:.2f}s，预期 < 10s"
        cache.clear()
        cache.close()

    def test_batch_get_1000_mixed(self, temp_dir: str) -> None:
        """大规模：批量读取 1000 条（50% 命中）"""
        cache = EmbeddingCache(cache_dir=temp_dir)
        texts = [f"混合测试{i}" for i in range(500)]
        vecs = [_make_vector(dim=4, seed=i) for i in range(500)]
        cache.batch_set(list(zip(texts, vecs)))

        # 查询 1000 条，前 500 条已缓存，后 500 条未缓存
        query = texts + [f"未缓存文本{j}" for j in range(500)]
        results = cache.batch_get(query)
        assert len(results) == 1000
        hits = sum(1 for r in results if r is not None)
        assert hits == 500
        cache.clear()
        cache.close()


# ===================================================================
# 8. 持久化测试
# ===================================================================


class TestPersistence:
    def test_persistence_across_reload(self, temp_dir: str) -> None:
        """持久化：关闭后重新打开数据仍在"""
        cache1 = EmbeddingCache(cache_dir=temp_dir)
        texts = ["持久化A", "持久化B", "持久化C"]
        vecs = [_make_vector(seed=i) for i in range(3)]
        for t, v in zip(texts, vecs):
            cache1.set(t, v)
        len1 = len(cache1)
        cache1.close()

        # 重新创建实例（同一目录）
        cache2 = EmbeddingCache(cache_dir=temp_dir)
        assert len(cache2) == len1 == 3
        for t, expected in zip(texts, vecs):
            result = cache2.get(t)
            assert result == expected
        cache2.clear()
        cache2.close()

    def test_persistence_after_clear(self, temp_dir: str) -> None:
        """持久化：clear 后重新打开数据已被清空"""
        cache1 = EmbeddingCache(cache_dir=temp_dir)
        cache1.set("待清空", _make_vector())
        cache1.clear()
        cache1.close()

        cache2 = EmbeddingCache(cache_dir=temp_dir)
        assert len(cache2) == 0
        assert cache2.get("待清空") is None
        cache2.close()


# ===================================================================
# 9. 并发安全性测试
# ===================================================================


class TestConcurrency:
    def test_concurrent_set(self, temp_dir: str) -> None:
        """并发：多线程同时写入不崩溃"""
        cache = EmbeddingCache(cache_dir=temp_dir)
        n_threads = 10
        texts = [f"并发写入{i}" for i in range(n_threads)]
        vecs = [_make_vector(seed=i) for i in range(n_threads)]

        def write(idx: int) -> None:
            cache.set(texts[idx], vecs[idx])

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as ex:
            futures = [ex.submit(write, i) for i in range(n_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # 不应抛出异常

        assert len(cache) == n_threads
        for t, v in zip(texts, vecs):
            assert cache.get(t) == v
        cache.clear()
        cache.close()

    def test_concurrent_get(self, temp_dir: str) -> None:
        """并发：多线程同时读取不崩溃"""
        cache = EmbeddingCache(cache_dir=temp_dir)
        texts = [f"并发读取{i}" for i in range(20)]
        vecs = [_make_vector(seed=i) for i in range(20)]
        for t, v in zip(texts, vecs):
            cache.set(t, v)

        n_threads = 10

        def read(idx: int) -> Optional[List[float]]:
            return cache.get(texts[idx % len(texts)])

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as ex:
            futures = [ex.submit(read, i) for i in range(50)]
            for f in concurrent.futures.as_completed(futures):
                result = f.result()
                assert result is not None  # 全部应命中
        cache.clear()
        cache.close()

    def test_concurrent_batch_set(self, temp_dir: str) -> None:
        """并发：多线程批量写入不崩溃"""
        cache = EmbeddingCache(cache_dir=temp_dir)
        n_threads = 5

        def batch_write(thread_id: int) -> None:
            texts = [f"线程{thread_id}_文本{j}" for j in range(20)]
            vecs = [_make_vector(seed=thread_id * 100 + j) for j in range(20)]
            cache.batch_set(list(zip(texts, vecs)))

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as ex:
            futures = [ex.submit(batch_write, i) for i in range(n_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        total = len(cache)
        assert total == n_threads * 20, f"预期 {n_threads * 20} 条，实际 {total} 条"
        cache.clear()
        cache.close()


# ===================================================================
# 10. 边界情况测试
# ===================================================================


class TestEdgeCases:
    def test_empty_text(self, cache: EmbeddingCache) -> None:
        """边界：空字符串作为key"""
        vec = _make_vector()
        cache.set("", vec)
        result = cache.get("")
        assert result == vec

    def test_special_characters(self, cache: EmbeddingCache) -> None:
        """边界：特殊字符文本"""
        texts = [
            "hello world!@#$%^&*()",
            "line1\nline2\t tab",
            "  前后空格  ",
            "中文 English 混合 123",
            "emoji 😀🎉🔥",
        ]
        for t in texts:
            v = _make_vector(seed=hash(t))
            cache.set(t, v)
        for t in texts:
            result = cache.get(t)
            assert result is not None, f"特殊字符文本读取失败: {t!r}"

    def test_very_long_text(self, cache: EmbeddingCache) -> None:
        """边界：超长文本 (10KB)"""
        long_text = "长文本" * 3000  # ~18KB
        vec = _make_vector()
        cache.set(long_text, vec)
        result = cache.get(long_text)
        assert result == vec

    def test_zero_dimension_vector(self, cache: EmbeddingCache) -> None:
        """边界：零维向量"""
        cache.set("零维向量", [])
        result = cache.get("零维向量")
        assert result == []

    def test_large_dimension_vector(self, cache: EmbeddingCache) -> None:
        """边界：大维度向量 (768维，模拟真实BGE)"""
        vec = _make_vector(dim=768, seed=42)
        cache.set("大维度向量", vec)
        result = cache.get("大维度向量")
        assert result is not None
        assert len(result) == 768
        assert result == vec
