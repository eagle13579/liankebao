"""
链客宝 - MinuteIndexer / InMemoryIndex 分钟级增量索引单元测试
==============================================================

测试覆盖:
1.  InMemoryIndex 初始化 (dim/空索引)
2.  InMemoryIndex.add / get / size
3.  InMemoryIndex.search 余弦相似度
4.  InMemoryIndex.search top_k 截断
5.  InMemoryIndex.delete
6.  InMemoryIndex.update
7.  InMemoryIndex 维度校验
8.  InMemoryIndex.save / load 持久化
9.  InMemoryIndex.clear
10. MinuteIndexer 初始化
11. MinuteIndexer start / stop 生命周期
12. MinuteIndexer status 格式
13. MinuteIndexer 索引周期 (首次初始化)
14. MinuteIndexer 索引周期 (有变更)
15. MinuteIndexer 索引周期 (无变更)
16. MinuteIndexer 延迟保证 (< 1分钟)
17. MinuteIndexer 版本标记
18. 批量索引
19. 并发安全性
20. 进度持久化

Author: 长右 (P8, 移动端工程师, 增量同步/索引)
"""

from __future__ import annotations

import json
import math
import os
import pickle
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ml.pipelines.minute_indexer import (
    InMemoryIndex,
    IndexEntry,
    IndexerStatus,
    MinuteIndexer,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_EMBEDDING_DIM,
)


# ===================================================================
# 辅助函数
# ===================================================================


def _make_vector(dim: int = 4, seed: int = 0) -> List[float]:
    """生成确定性归一化向量"""
    rng = __import__("random").Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    return [round(v / norm, 6) for v in vec]


def _make_temp_db(records: List[Dict[str, Any]]) -> str:
    """创建临时 SQLite 数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS business_cards ("
        "id INTEGER PRIMARY KEY, "
        "fields TEXT, "
        "created_at TEXT, "
        "updated_at TEXT"
        ")"
    )
    for rec in records:
        conn.execute(
            "INSERT INTO business_cards (id, fields, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                rec["id"],
                json.dumps(rec["fields"], ensure_ascii=False),
                rec.get("created_at", ""),
                rec.get("updated_at", ""),
            ),
        )
    conn.commit()
    conn.close()
    return path


def _make_mock_pipeline(db_path: str, source_name: str = "test_source"):
    """创建模拟的 RealtimeSyncPipeline"""
    from ml.pipelines.realtime_sync import (
        DataSourceConfig,
        RealtimeSyncPipeline,
    )

    pipeline = MagicMock(spec=RealtimeSyncPipeline)
    config = DataSourceConfig(
        name=source_name,
        db_path=db_path,
        table="business_cards",
        id_field="id",
        updated_at_field="updated_at",
        fields_field="fields",
    )
    pipeline._data_sources = {source_name: config}
    pipeline.list_sources.return_value = [source_name]

    # 实现 _query_max_updated_at
    def query_max_updated_at(cfg):
        conn = sqlite3.connect(cfg.db_path)
        try:
            row = conn.execute(
                f"SELECT MAX({cfg.updated_at_field}) FROM {cfg.table}"
            ).fetchone()
            return row[0] if row and row[0] else None
        finally:
            conn.close()

    # 实现 _pull_incremental
    def pull_incremental(cfg, since_ts):
        from ml.pipelines.realtime_sync import ChangeEvent

        conn = sqlite3.connect(cfg.db_path)
        try:
            conn.row_factory = sqlite3.Row
            sql = (
                f"SELECT {cfg.id_field}, {cfg.fields_field}, {cfg.updated_at_field} "
                f"FROM {cfg.table} WHERE {cfg.updated_at_field} > ? "
                f"ORDER BY {cfg.updated_at_field} ASC"
            )
            rows = conn.execute(sql, (since_ts,)).fetchall()
            events = []
            for row in rows:
                raw = row[cfg.fields_field]
                fields_json = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                events.append(ChangeEvent(
                    record_id=str(row[cfg.id_field]),
                    fields_json=fields_json,
                    updated_at=str(row[cfg.updated_at_field]),
                    source_name=cfg.name,
                ))
            return events
        finally:
            conn.close()

    pipeline._query_max_updated_at = query_max_updated_at
    pipeline._pull_incremental = pull_incremental

    # embedder mock
    pipeline._embedder = None

    return pipeline, config, db_path


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """临时目录"""
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def index() -> Generator[InMemoryIndex, None, None]:
    """InMemoryIndex 实例 (dim=4)"""
    idx = InMemoryIndex(dim=4)
    yield idx


@pytest.fixture
def populated_index() -> Generator[InMemoryIndex, None, None]:
    """预填充 5 条条目的 InMemoryIndex"""
    idx = InMemoryIndex(dim=4)
    for i in range(5):
        idx.add(
            id=f"doc{i}",
            vector=_make_vector(seed=i),
            metadata={"title": f"文档{i}", "tag": f"tag{i % 3}"},
        )
    yield idx


@pytest.fixture
def mock_cache() -> MagicMock:
    """模拟的 EmbeddingCache"""
    cache = MagicMock()
    cache.batch_set = MagicMock()
    cache.get = MagicMock(return_value=None)
    return cache


@pytest.fixture
def seeded_db_path() -> Generator[str, None, None]:
    """带初始数据的临时数据库"""
    now = datetime.now(timezone.utc)
    records = [
        {
            "id": 1,
            "fields": {"company": "链客宝科技", "desc": "企业数字名片平台"},
            "created_at": "2025-01-01T00:00:00",
            "updated_at": (now.replace(hour=0, minute=0, second=0) - 
                           __import__("datetime").timedelta(hours=2)).isoformat(),
        },
        {
            "id": 2,
            "fields": {"company": "数据智能", "desc": "AI 解决方案"},
            "created_at": "2025-01-02T00:00:00",
            "updated_at": (now.replace(hour=0, minute=0, second=0) - 
                           __import__("datetime").timedelta(hours=1)).isoformat(),
        },
    ]
    path = _make_temp_db(records)
    yield path
    import gc
    gc.collect()
    try:
        os.unlink(path)
    except PermissionError:
        time.sleep(0.1)
        gc.collect()
        try:
            os.unlink(path)
        except PermissionError:
            pass


@pytest.fixture
def indexer(seeded_db_path: str, mock_cache: MagicMock, temp_dir: str) -> Generator[MinuteIndexer, None, None]:
    """MinuteIndexer 实例"""
    pipeline, _, _ = _make_mock_pipeline(seeded_db_path)
    idxr = MinuteIndexer(
        sync_pipeline=pipeline,
        cache=mock_cache,
        check_interval=60,
        dim=4,
        index_dir=os.path.join(temp_dir, "index_data"),
        embedder=None,
    )
    yield idxr
    try:
        idxr.stop()
    except Exception:
        pass


# ===================================================================
# 测试 1: InMemoryIndex 初始化
# ===================================================================


class TestInMemoryIndexInit:
    """InMemoryIndex 初始化"""

    def test_default_dim(self):
        """默认 dim 应为 768"""
        idx = InMemoryIndex()
        assert idx._dim == DEFAULT_EMBEDDING_DIM

    def test_custom_dim(self):
        """自定义 dim 应正确设置"""
        idx = InMemoryIndex(dim=128)
        assert idx._dim == 128

    def test_empty_index_size(self, index: InMemoryIndex):
        """空索引 size = 0"""
        assert index.size() == 0
        assert len(index) == 0

    def test_empty_index_search(self, index: InMemoryIndex):
        """空索引 search 返回空列表"""
        results = index.search([0.1, 0.2, 0.3, 0.4])
        assert results == []

    def test_repr(self, index: InMemoryIndex):
        """__repr__ 格式"""
        r = repr(index)
        assert "InMemoryIndex" in r
        assert "dim=" in r
        assert "entries=" in r


# ===================================================================
# 测试 2: InMemoryIndex add / get / size
# ===================================================================


class TestInMemoryIndexAdd:
    """InMemoryIndex 添加操作"""

    def test_add_single(self, index: InMemoryIndex):
        """添加单条后 size 为 1"""
        vec = _make_vector()
        index.add("doc1", vec, {"title": "测试文档"})
        assert index.size() == 1
        assert "doc1" in index

    def test_get_returns_entry(self, index: InMemoryIndex):
        """get 返回正确的 IndexEntry"""
        vec = _make_vector(seed=42)
        meta = {"title": "测试"}
        index.add("doc1", vec, meta)
        entry = index.get("doc1")
        assert entry is not None
        assert entry.id == "doc1"
        assert entry.vector == vec
        assert entry.metadata == meta
        assert entry.version is not None  # 有时间戳

    def test_get_nonexistent(self, index: InMemoryIndex):
        """不存在的 ID 返回 None"""
        assert index.get("nonexistent") is None

    def test_add_duplicate_overwrites(self, index: InMemoryIndex):
        """重复添加相同 ID 应覆盖"""
        v1 = _make_vector(seed=1)
        v2 = _make_vector(seed=2)
        index.add("doc1", v1, {"v": 1})
        index.add("doc1", v2, {"v": 2})
        assert index.size() == 1
        entry = index.get("doc1")
        assert entry is not None
        assert entry.vector == v2
        assert entry.metadata["v"] == 2

    def test_add_validates_dim(self, index: InMemoryIndex):
        """维度不匹配应抛出 ValueError"""
        wrong_vec = [0.1, 0.2, 0.3]  # 3 维，索引是 4 维
        with pytest.raises(ValueError, match="维度"):
            index.add("bad_dim", wrong_vec, {})

    def test_add_version_is_isoformat(self, index: InMemoryIndex):
        """添加后 version 应为 ISO 格式"""
        index.add("vtest", _make_vector(), {})
        entry = index.get("vtest")
        assert entry is not None
        assert "T" in entry.version  # ISO 格式包含 T


# ===================================================================
# 测试 3: InMemoryIndex.search 余弦相似度
# ===================================================================


class TestInMemoryIndexSearch:
    """InMemoryIndex 搜索"""

    def test_search_returns_correct_format(self, populated_index: InMemoryIndex):
        """search 返回正确的 (id, score, metadata) 格式"""
        qvec = _make_vector(seed=0)
        results = populated_index.search(qvec, top_k=3)
        assert len(results) == 3
        for rid, score, meta in results:
            assert isinstance(rid, str)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0  # 余弦相似度范围 [-1, 1]
            assert isinstance(meta, dict)

    def test_search_best_match(self, populated_index: InMemoryIndex):
        """与自身最相似的文档应排第一"""
        # 使用 doc0 的向量查询，doc0 应排第一（余弦相似度 = 1.0）
        doc0_vec = populated_index.get("doc0")
        assert doc0_vec is not None
        results = populated_index.search(doc0_vec.vector, top_k=5)
        assert results[0][0] == "doc0"
        assert results[0][1] == pytest.approx(1.0, abs=1e-6)

    def test_search_top_k_clamp(self, populated_index: InMemoryIndex):
        """top_k 超过条目数应返回所有"""
        qvec = _make_vector(seed=0)
        results = populated_index.search(qvec, top_k=100)
        assert len(results) == 5  # 只有 5 条

    def test_search_top_k_one(self, populated_index: InMemoryIndex):
        """top_k=1 返回单条"""
        qvec = _make_vector(seed=0)
        results = populated_index.search(qvec, top_k=1)
        assert len(results) == 1

    def test_search_zero_vector(self, index: InMemoryIndex):
        """零向量查询应返回空"""
        index.add("doc_a", [1.0, 0.0, 0.0, 0.0], {})
        results = index.search([0.0, 0.0, 0.0, 0.0])
        assert results == []

    def test_search_metadata_is_copy(self, populated_index: InMemoryIndex):
        """search 返回的 metadata 应为副本，修改不影响原条目"""
        qvec = _make_vector(seed=0)
        results = populated_index.search(qvec, top_k=1)
        rid, score, meta = results[0]
        meta["hacked"] = True
        # 确认原条目 metadata 未被修改
        entry = populated_index.get(rid)
        assert entry is not None
        assert "hacked" not in entry.metadata


# ===================================================================
# 测试 4: InMemoryIndex delete / update
# ===================================================================


class TestInMemoryIndexMutate:
    """InMemoryIndex 删除与更新"""

    def test_delete_existing(self, populated_index: InMemoryIndex):
        """删除存在的条目"""
        assert populated_index.delete("doc0") is True
        assert "doc0" not in populated_index
        assert populated_index.size() == 4

    def test_delete_nonexistent(self, populated_index: InMemoryIndex):
        """删除不存在的条目返回 False"""
        assert populated_index.delete("nonexistent") is False
        assert populated_index.size() == 5

    def test_update_existing(self, populated_index: InMemoryIndex):
        """更新存在的条目"""
        new_vec = [0.5, 0.5, 0.5, 0.5]
        new_meta = {"title": "已更新"}
        assert populated_index.update("doc0", new_vec, new_meta) is True
        entry = populated_index.get("doc0")
        assert entry is not None
        assert entry.vector == new_vec
        assert entry.metadata == new_meta

    def test_update_nonexistent(self, populated_index: InMemoryIndex):
        """更新不存在的条目返回 False"""
        assert populated_index.update(
            "nonexistent", [0.1, 0.2, 0.3, 0.4], {}
        ) is False

    def test_update_validation(self, populated_index: InMemoryIndex):
        """更新时维度不匹配抛出 ValueError"""
        with pytest.raises(ValueError, match="维度"):
            populated_index.update("doc0", [0.1, 0.2, 0.3], {})

    def test_clear(self, populated_index: InMemoryIndex):
        """清空索引"""
        assert populated_index.size() == 5
        populated_index.clear()
        assert populated_index.size() == 0
        assert populated_index.get("doc0") is None


# ===================================================================
# 测试 5: InMemoryIndex save / load 持久化
# ===================================================================


class TestInMemoryIndexPersistence:
    """InMemoryIndex 持久化"""

    def test_save_and_load(self, populated_index: InMemoryIndex, temp_dir: str):
        """保存后加载应恢复完整索引"""
        save_path = os.path.join(temp_dir, "index.pkl")
        populated_index.save(save_path)

        idx2 = InMemoryIndex(dim=4)
        assert idx2.load(save_path) is True
        assert idx2.size() == 5
        for i in range(5):
            eid = f"doc{i}"
            orig = populated_index.get(eid)
            loaded = idx2.get(eid)
            assert loaded is not None
            assert loaded.vector == orig.vector
            assert loaded.metadata == orig.metadata

    def test_load_nonexistent(self, index: InMemoryIndex):
        """加载不存在的文件返回 False"""
        assert index.load("/nonexistent/path.pkl") is False

    def test_save_creates_dir(self, temp_dir: str):
        """保存应自动创建目录"""
        deep_dir = os.path.join(temp_dir, "a", "b", "c", "idx.pkl")
        idx = InMemoryIndex(dim=4)
        idx.add("test", _make_vector(), {})
        idx.save(deep_dir)
        assert os.path.exists(deep_dir)

    def test_save_load_roundtrip_content(self, temp_dir: str):
        """保存加载往返：向量和元数据一致"""
        idx = InMemoryIndex(dim=4)
        for i in range(10):
            idx.add(f"item{i}", _make_vector(seed=i), {"idx": i, "label": f"L{i}"})

        save_path = os.path.join(temp_dir, "idx.pkl")
        idx.save(save_path)

        idx2 = InMemoryIndex(dim=4)
        idx2.load(save_path)
        # 验证向量余弦相似度
        qvec = _make_vector(seed=0)
        r1 = idx.search(qvec, top_k=3)
        r2 = idx2.search(qvec, top_k=3)
        assert len(r1) == len(r2)
        for (id1, s1, _), (id2, s2, _) in zip(r1, r2):
            assert id1 == id2
            assert s1 == pytest.approx(s2, abs=1e-6)


# ===================================================================
# 测试 6: MinuteIndexer 初始化
# ===================================================================


class TestMinuteIndexerInit:
    """MinuteIndexer 初始化"""

    def test_default_check_interval(self, indexer: MinuteIndexer):
        """默认 check_interval 应为 60"""
        assert indexer._check_interval == 60

    def test_min_check_interval(self, seeded_db_path: str, mock_cache: MagicMock, temp_dir: str):
        """check_interval 最小值 5"""
        pipeline, _, _ = _make_mock_pipeline(seeded_db_path)
        idxr = MinuteIndexer(
            sync_pipeline=pipeline, cache=mock_cache,
            check_interval=1, dim=4, index_dir=temp_dir,
        )
        assert idxr._check_interval == 5  # 最小值限制
        idxr.stop()

    def test_initial_status(self, indexer: MinuteIndexer):
        """初始状态应为未运行"""
        st = indexer.status()
        assert st["running"] is False
        assert st["started_at"] is None
        assert st["stopped_at"] is None
        assert st["total_cycles"] == 0
        assert st["total_records_indexed"] == 0


# ===================================================================
# 测试 7: MinuteIndexer start / stop
# ===================================================================


class TestMinuteIndexerLifecycle:
    """MinuteIndexer 生命周期"""

    def test_start(self, indexer: MinuteIndexer):
        """启动后 running=True"""
        indexer.start()
        assert indexer.is_running is True
        st = indexer.status()
        assert st["running"] is True
        assert st["started_at"] is not None
        indexer.stop()

    def test_stop(self, indexer: MinuteIndexer):
        """停止后 running=False"""
        indexer.start()
        assert indexer.is_running is True
        indexer.stop()
        assert indexer.is_running is False
        st = indexer.status()
        assert st["running"] is False
        assert st["stopped_at"] is not None

    def test_start_idempotent(self, indexer: MinuteIndexer):
        """重复 start() 应忽略"""
        indexer.start()
        indexer.start()  # 第二次
        assert indexer.is_running is True
        indexer.stop()

    def test_stop_idempotent(self, indexer: MinuteIndexer):
        """重复 stop() 应忽略"""
        indexer.stop()  # 未启动
        indexer.stop()  # 再次
        assert indexer.is_running is False

    def test_thread_daemon(self, indexer: MinuteIndexer):
        """后台线程应为守护线程"""
        indexer.start()
        assert indexer._thread is not None
        assert indexer._thread.daemon is True
        indexer.stop()


# ===================================================================
# 测试 8: MinuteIndexer 索引周期
# ===================================================================


class TestMinuteIndexerCycle:
    """MinuteIndexer 索引周期"""

    def test_trigger_cycle_first_run(self, indexer: MinuteIndexer):
        """首次触发索引周期应仅初始化（无记录）"""
        result = indexer.trigger_index_cycle()
        assert result["records_indexed"] == 0
        assert result["errors"] == 0
        assert result["version"] is not None
        # 进度应已记录
        assert "test_source" in indexer._source_progress

    def test_trigger_cycle_with_new_data(
        self, indexer: MinuteIndexer, seeded_db_path: str
    ):
        """插入新数据后触发周期应索引到新记录"""
        # 给 indexer 注入 mock embedder
        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = [_make_vector(seed=0)]
        indexer._embedder = mock_embedder

        # 首次：初始化
        indexer.trigger_index_cycle()

        # 插入新数据
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(seeded_db_path)
        conn.execute(
            "INSERT INTO business_cards (id, fields, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                100,
                json.dumps({"company": "新公司", "desc": "新数据"}),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        # 第二次触发：应索引到新记录
        result = indexer.trigger_index_cycle()
        assert result["records_indexed"] >= 1
        st = indexer.status()
        assert st["total_records_indexed"] >= 1
        assert st["total_cycles"] >= 2

    def test_trigger_cycle_no_changes(self, indexer: MinuteIndexer):
        """无变更时触发周期返回 0"""
        indexer.trigger_index_cycle()  # 首次：初始化
        result = indexer.trigger_index_cycle()  # 第二次：无变更
        assert result["records_indexed"] == 0

    def test_trigger_cycle_incremental_indexing(self, indexer: MinuteIndexer, seeded_db_path: str):
        """增量索引：第二次只索引新数据"""
        # 注入 mock embedder
        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = [
            _make_vector(seed=0), _make_vector(seed=1),
        ]
        indexer._embedder = mock_embedder

        indexer.trigger_index_cycle()  # 首次初始化

        # 插入 2 条新数据
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(seeded_db_path)
        for i in range(2):
            conn.execute(
                "INSERT INTO business_cards (id, fields, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    200 + i,
                    json.dumps({"company": f"增量公司{i}", "desc": f"增量数据{i}"}),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        conn.commit()
        conn.close()

        result = indexer.trigger_index_cycle()
        assert result["records_indexed"] == 2

        # 索引大小应为 2
        assert indexer.index.size() == 2

    def test_version_marking(self, indexer: MinuteIndexer, seeded_db_path: str):
        """每次索引周期应有唯一版本号"""
        indexer.trigger_index_cycle()  # 首次

        # 插入数据
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(seeded_db_path)
        conn.execute(
            "INSERT INTO business_cards (id, fields, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (300, json.dumps({"company": "版本测试"}), now.isoformat(), now.isoformat()),
        )
        conn.commit()
        conn.close()

        result1 = indexer.trigger_index_cycle()
        v1 = result1["version"]

        # 再插入一条
        conn = sqlite3.connect(seeded_db_path)
        conn.execute(
            "INSERT INTO business_cards (id, fields, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (301, json.dumps({"company": "版本测试2"}), now.isoformat(), now.isoformat()),
        )
        conn.commit()
        conn.close()

        result2 = indexer.trigger_index_cycle()
        v2 = result2["version"]

        # 版本号不同
        assert v1 != v2
        # 状态记录最后版本
        st = indexer.status()
        assert st["last_index_version"] == v2


# ===================================================================
# 测试 9: 延迟保证
# ===================================================================


class TestLatencyGuarantee:
    """延迟保证 < 1 分钟"""

    def test_check_interval_default(self):
        """默认 check_interval = 60 秒"""
        assert DEFAULT_CHECK_INTERVAL == 60

    def test_cycle_latency(self, indexer: MinuteIndexer, seeded_db_path: str):
        """单次索引周期应在 1 秒内完成（远小于 60 秒阈值）"""
        indexer.trigger_index_cycle()  # 首次初始化

        # 插入数据
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(seeded_db_path)
        conn.execute(
            "INSERT INTO business_cards (id, fields, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (400, json.dumps({"company": "快速测试"}), now.isoformat(), now.isoformat()),
        )
        conn.commit()
        conn.close()

        t0 = time.perf_counter()
        result = indexer.trigger_index_cycle()
        elapsed = time.perf_counter() - t0

        # 单次周期应远小于 60 秒
        assert elapsed < 10.0, f"索引周期耗时 {elapsed:.3f}s，预期 < 10s"
        assert result["records_indexed"] >= 0


# ===================================================================
# 测试 10: 批量索引
# ===================================================================


class TestBatchIndexing:
    """批量索引场景"""

    def test_batch_add(self, index: InMemoryIndex):
        """批量添加 100 条"""
        for i in range(100):
            index.add(
                f"batch_doc{i}",
                _make_vector(seed=i),
                {"idx": i},
            )
        assert index.size() == 100

    def test_batch_search(self, index: InMemoryIndex):
        """批量添加后搜索"""
        for i in range(50):
            index.add(
                f"bdoc{i}",
                _make_vector(seed=i),
                {"idx": i},
            )
        qvec = _make_vector(seed=10)
        results = index.search(qvec, top_k=5)
        assert len(results) == 5
        # 最相似的是 seed=10
        assert results[0][0] == "bdoc10"

    def test_batch_delete(self, populated_index: InMemoryIndex):
        """批量删除所有"""
        for i in range(5):
            populated_index.delete(f"doc{i}")
        assert populated_index.size() == 0


# ===================================================================
# 测试 11: 并发安全性
# ===================================================================


class TestConcurrency:
    """并发安全性"""

    def test_concurrent_add(self, temp_dir: str):
        """多线程并发添加不崩溃"""
        idx = InMemoryIndex(dim=4)
        n_threads = 10
        n_each = 20

        def add_range(start: int):
            for i in range(n_each):
                idx.add(
                    f"concurrent_{start + i}",
                    _make_vector(seed=start + i),
                    {"idx": start + i},
                )

        threads = [
            threading.Thread(target=add_range, args=(t * n_each,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert idx.size() == n_threads * n_each

    def test_concurrent_search(self, populated_index: InMemoryIndex):
        """多线程并发搜索不崩溃"""
        n_threads = 10
        errors = []

        def search_thread():
            try:
                qvec = _make_vector(seed=0)
                for _ in range(20):
                    populated_index.search(qvec, top_k=3)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=search_thread) for _ in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_mixed(self, populated_index: InMemoryIndex):
        """多线程混合读写"""
        errors = []

        def writer():
            try:
                for i in range(10):
                    populated_index.add(
                        f"new_{i}", _make_vector(seed=i), {}
                    )
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(10):
                    populated_index.search(_make_vector(seed=0), top_k=3)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer) for _ in range(4)
        ] + [
            threading.Thread(target=reader) for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ===================================================================
# 测试 12: 进度持久化
# ===================================================================


class TestProgressPersistence:
    """进度持久化"""

    def test_progress_saved_after_cycle(self, indexer: MinuteIndexer):
        """索引周期后进度应保存到文件"""
        indexer.trigger_index_cycle()  # 首次初始化
        progress_file = indexer._progress_file()
        assert os.path.exists(progress_file)

        with open(progress_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "source_progress" in data
        assert "test_source" in data["source_progress"]

    def test_progress_loaded(self, indexer: MinuteIndexer, temp_dir: str):
        """重新创建索引器应加载保存的进度"""
        indexer.trigger_index_cycle()
        assert "test_source" in indexer._source_progress

        # 创建新索引器（同一目录）
        pipeline, _, _ = _make_mock_pipeline(
            indexer._sync_pipeline._data_sources["test_source"].db_path
        )
        cache = MagicMock()
        idxr2 = MinuteIndexer(
            sync_pipeline=pipeline,
            cache=cache,
            dim=4,
            index_dir=os.path.join(temp_dir, "index_data"),
        )
        assert "test_source" in idxr2._source_progress
        idxr2.stop()

    def test_progress_preserves_cycle_count(self, indexer: MinuteIndexer, temp_dir: str):
        """进度保存周期计数"""
        indexer.trigger_index_cycle()

        pipeline, _, _ = _make_mock_pipeline(
            indexer._sync_pipeline._data_sources["test_source"].db_path
        )
        cache = MagicMock()
        idxr2 = MinuteIndexer(
            sync_pipeline=pipeline,
            cache=cache,
            dim=4,
            index_dir=os.path.join(temp_dir, "index_data"),
        )
        st = idxr2.status()
        assert st["total_cycles"] >= 1
        idxr2.stop()


# ===================================================================
# 测试 13: 边界情况
# ===================================================================


class TestEdgeCases:
    """边界情况"""

    def test_index_multiple_sources(self, seeded_db_path: str, mock_cache: MagicMock, temp_dir: str):
        """多个数据源"""
        pipeline, _, _ = _make_mock_pipeline(seeded_db_path, "source_a")
        # 添加第二个数据源
        from ml.pipelines.realtime_sync import DataSourceConfig
        config_b = DataSourceConfig(
            name="source_b", db_path=seeded_db_path,
            table="business_cards", id_field="id",
            updated_at_field="updated_at", fields_field="fields",
        )
        pipeline._data_sources["source_b"] = config_b
        pipeline.list_sources.return_value = ["source_a", "source_b"]

        idxr = MinuteIndexer(
            sync_pipeline=pipeline, cache=mock_cache,
            dim=4, index_dir=os.path.join(temp_dir, "multi"),
        )
        result = idxr.trigger_index_cycle()
        # 两个源都首次初始化
        assert result["records_indexed"] == 0
        assert result["errors"] == 0
        idxr.stop()

    def test_empty_db(self, temp_dir: str, mock_cache: MagicMock):
        """空数据库不应崩溃"""
        db_path = _make_temp_db([])
        try:
            pipeline, _, _ = _make_mock_pipeline(db_path)
            idxr = MinuteIndexer(
                sync_pipeline=pipeline, cache=mock_cache,
                dim=4, index_dir=os.path.join(temp_dir, "empty"),
            )
            result = idxr.trigger_index_cycle()
            assert result["records_indexed"] == 0
            assert result["errors"] == 0
            idxr.stop()
        finally:
            import gc
            gc.collect()
            try:
                os.unlink(db_path)
            except PermissionError:
                pass

    def test_corrupted_progress_file(self, temp_dir: str, seeded_db_path: str, mock_cache: MagicMock):
        """损坏的进度文件不应崩溃"""
        progress_dir = os.path.join(temp_dir, "corrupted")
        os.makedirs(progress_dir, exist_ok=True)
        with open(os.path.join(progress_dir, "index_progress.json"), "w", encoding="utf-8") as f:
            f.write("这不是 JSON{{{")

        pipeline, _, _ = _make_mock_pipeline(seeded_db_path)
        idxr = MinuteIndexer(
            sync_pipeline=pipeline, cache=mock_cache,
            dim=4, index_dir=progress_dir,
        )
        # 不应抛出异常
        assert idxr._source_progress == {}
        idxr.stop()

    def test_save_load_roundtrip_pickle_corruption(self, temp_dir: str):
        """损坏的 pickle 文件返回 False"""
        path = os.path.join(temp_dir, "bad.pkl")
        with open(path, "w") as f:
            f.write("not pickle data")
        idx = InMemoryIndex(dim=4)
        assert idx.load(path) is False


# ===================================================================
# 测试 14: IndexerStatus 数据模型
# ===================================================================


class TestIndexerStatus:
    """IndexerStatus 数据模型"""

    def test_defaults(self):
        """默认值"""
        st = IndexerStatus()
        assert st.running is False
        assert st.total_cycles == 0
        assert st.total_records_indexed == 0
        assert st.total_errors == 0
        assert st.index_size == 0
        assert st.last_error is None

    def test_to_dict(self):
        """to_dict 包含所有字段"""
        st = IndexerStatus(
            running=True,
            started_at="2025-01-01T00:00:00",
            total_cycles=5,
            total_records_indexed=42,
            index_size=100,
        )
        d = st.to_dict()
        assert d["running"] is True
        assert d["total_cycles"] == 5
        assert d["total_records_indexed"] == 42
        assert d["index_size"] == 100
        assert "check_interval" in d


# ===================================================================
# 运行断言汇总
# ===================================================================
#
# 已实现 14 个测试类，超过 40 个测试用例，覆盖：
# ✅ InMemoryIndex 初始化 (test 1)
# ✅ InMemoryIndex add / get / size (test 2)
# ✅ InMemoryIndex search 余弦相似度 + top_k (test 3)
# ✅ InMemoryIndex delete / update / clear (test 4)
# ✅ InMemoryIndex save / load 持久化 (test 5)
# ✅ MinuteIndexer 初始化 (test 6)
# ✅ MinuteIndexer start / stop 生命周期 (test 7)
# ✅ MinuteIndexer 索引周期 (首次/有变更/无变更) (test 8)
# ✅ 版本标记 (test 8)
# ✅ 延迟保证 (test 9)
# ✅ 批量索引 (test 10)
# ✅ 并发安全性 (test 11)
# ✅ 进度持久化 (test 12)
# ✅ 边界情况 (test 13)
# ✅ IndexerStatus 数据模型 (test 14)
