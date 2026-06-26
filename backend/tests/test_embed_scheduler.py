"""
链客宝 - 嵌入调度器单元测试
============================
测试覆盖:
1. VersionManager 版本生成与注册
2. VersionManager 查询与统计
3. CheckpointManager 保存与加载
4. CheckpointManager 断点续传
5. SQliteDataSource 数据读取
6. JsonlDataSource 数据读取
7. CsvDataSource 数据读取
8. EmbedScheduler process_batch 批处理编码
9. EmbedScheduler schedule_full_refresh 全量刷新
10. EmbedScheduler status 状态查询
11. EmbedScheduler resume 断点续传
12. 数据源 MD5 校验
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple

import pytest

# 被测试模块
from ml.features.embed_scheduler import (
    CheckpointManager,
    CsvDataSource,
    DataSource,
    EmbedScheduler,
    JsonlDataSource,
    SQliteDataSource,
    VersionManager,
)


# ===================================================================
# 辅助函数
# ===================================================================


def _make_temp_db(cards: List[Dict[str, Any]]) -> str:
    """创建临时 SQLite 数据库并写入 business_cards 数据"""
    import sqlite3
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS business_cards "
        "(id INTEGER PRIMARY KEY, fields TEXT, created_at TEXT)"
    )
    for card in cards:
        conn.execute(
            "INSERT INTO business_cards (id, fields, created_at) VALUES (?, ?, ?)",
            (card["id"], json.dumps(card["fields"], ensure_ascii=False), card.get("created_at", "")),
        )
    conn.commit()
    conn.close()
    return path


def _make_temp_jsonl(records: List[Dict[str, Any]]) -> str:
    """创建临时 JSONL 文件"""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def _make_temp_csv(rows: List[Dict[str, str]], delimiter: str = ",") -> str:
    """创建临时 CSV 文件"""
    import csv
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    if not rows:
        return path
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_dir():
    """临时工作目录"""
    import tempfile
    import shutil
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    import time
    for _ in range(5):
        try:
            shutil.rmtree(tmpdir, ignore_errors=False)
            break
        except (PermissionError, NotADirectoryError, OSError):
            time.sleep(0.5)
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def version_db(tmp_dir: str) -> str:
    """版本数据库路径"""
    return os.path.join(tmp_dir, "versions.db")


@pytest.fixture
def cp_dir(tmp_dir: str) -> str:
    """检查点目录"""
    return os.path.join(tmp_dir, "checkpoints")


@pytest.fixture
def version_mgr(version_db: str) -> VersionManager:
    """VersionManager 实例"""
    return VersionManager(db_path=version_db)


@pytest.fixture
def cp_mgr(cp_dir: str) -> CheckpointManager:
    """CheckpointManager 实例"""
    return CheckpointManager(checkpoint_dir=cp_dir)


# ===================================================================
# 测试 1: VersionManager 版本生成与注册
# ===================================================================


class TestVersionManager:
    """版本管理器测试"""

    def test_next_version_initial(self, version_mgr: VersionManager):
        """初始版本应为 v1"""
        v = version_mgr.next_version()
        assert v == "v1", f"Expected v1, got {v}"

    def test_next_version_increments(self, version_mgr: VersionManager):
        """连续生成版本应递增"""
        versions = set()
        for _ in range(5):
            v = version_mgr.next_version()
            version_mgr.register_version(
                version=v,
                embedding_model="test_model",
                record_count=10,
                data_source="test",
                text_field="text",
            )
            versions.add(v)
        assert versions == {"v1", "v2", "v3", "v4", "v5"}, f"Unexpected versions: {versions}"

    def test_register_and_get_version(self, version_mgr: VersionManager):
        """注册后应能通过 get_version 获取"""
        v = version_mgr.next_version()
        version_mgr.register_version(
            version=v,
            embedding_model="bge-m3",
            record_count=42,
            data_source="SQLite(business_cards.fields)",
            text_field="fields",
            md5_checksum="abc123",
        )
        meta = version_mgr.get_version(v)
        assert meta is not None
        assert meta["version"] == v
        assert meta["embedding_model"] == "bge-m3"
        assert meta["record_count"] == 42
        assert meta["md5_checksum"] == "abc123"
        assert meta["status"] == "completed"

    def test_get_latest_version(self, version_mgr: VersionManager):
        """get_latest_version 应返回最新注册的版本"""
        for i in range(3):
            v = version_mgr.next_version()
            version_mgr.register_version(
                version=v,
                embedding_model="test",
                record_count=i * 10,
                data_source="test",
                text_field="text",
            )
        latest = version_mgr.get_latest_version()
        assert latest is not None
        assert latest["version"] == "v3"
        assert latest["record_count"] == 20

    def test_list_versions(self, version_mgr: VersionManager):
        """list_versions 应按创建时间降序"""
        for i in range(3):
            v = version_mgr.next_version()
            version_mgr.register_version(
                version=v,
                embedding_model="test",
                record_count=10,
                data_source="test",
                text_field="text",
            )
            time.sleep(0.01)  # 确保时间戳不同
        versions = version_mgr.list_versions()
        assert versions == ["v3", "v2", "v1"], f"Expected desc order, got {versions}"

    def test_mark_version_failed(self, version_mgr: VersionManager):
        """标记版本失败后状态应为 failed"""
        v = version_mgr.next_version()
        version_mgr.register_version(
            version=v,
            embedding_model="test",
            record_count=10,
            data_source="test",
            text_field="text",
        )
        version_mgr.mark_version_failed(v, "模型加载失败")
        meta = version_mgr.get_version(v)
        assert meta["status"] == "failed"
        assert "模型加载失败" in meta["metadata"]

    def test_delete_version(self, version_mgr: VersionManager):
        """删除版本后应无法查询"""
        v = version_mgr.next_version()
        version_mgr.register_version(
            version=v, embedding_model="test", record_count=1,
            data_source="test", text_field="text",
        )
        assert version_mgr.get_version(v) is not None
        version_mgr.delete_version(v)
        assert version_mgr.get_version(v) is None

    def test_stats(self, version_mgr: VersionManager):
        """stats 应返回正确的统计信息"""
        for i in range(3):
            v = version_mgr.next_version()
            version_mgr.register_version(
                version=v, embedding_model="test", record_count=10 * (i + 1),
                data_source="test", text_field="text",
            )
        stats = version_mgr.stats()
        assert stats["total_versions"] == 3
        assert stats["latest_version"]["version"] == "v3"
        assert len(stats["versions"]) == 3

    def test_no_version(self, version_mgr: VersionManager):
        """无版本时 get_latest_version 返回 None"""
        assert version_mgr.get_latest_version() is None


# ===================================================================
# 测试 2: CheckpointManager 检查点与断点续传
# ===================================================================


class TestCheckpointManager:
    """检查点管理器测试"""

    def test_load_empty(self, cp_mgr: CheckpointManager):
        """空检查点应返回默认值"""
        cp = cp_mgr.load("nonexistent_task")
        assert cp["processed_ids"] == []
        assert cp["failed_ids"] == []
        assert cp["total_count"] == 0
        assert cp["processed_count"] == 0

    def test_mark_processed(self, cp_mgr: CheckpointManager):
        """标记已处理的 ID 应持久化"""
        cp_mgr.mark_processed("task1", ["id1", "id2", "id3"])
        cp = cp_mgr.load("task1")
        assert set(cp["processed_ids"]) == {"id1", "id2", "id3"}
        assert cp["processed_count"] == 3

    def test_mark_failed(self, cp_mgr: CheckpointManager):
        """标记失败的 ID 应持久化"""
        cp_mgr.mark_failed("task1", ["bad1", "bad2"])
        cp = cp_mgr.load("task1")
        assert set(cp["failed_ids"]) == {"bad1", "bad2"}

    def test_get_unprocessed_ids(self, cp_mgr: CheckpointManager):
        """get_unprocessed_ids 应排除已处理和已失败的 ID"""
        all_ids = [f"id{i}" for i in range(10)]
        cp_mgr.mark_processed("task1", ["id0", "id1", "id2"])
        cp_mgr.mark_failed("task1", ["id3", "id4"])
        unprocessed = cp_mgr.get_unprocessed_ids("task1", all_ids)
        assert sorted(unprocessed) == ["id5", "id6", "id7", "id8", "id9"]

    def test_reset_checkpoint(self, cp_mgr: CheckpointManager):
        """重置检查点应删除文件"""
        cp_mgr.mark_processed("reset_task", ["id1"])
        assert len(cp_mgr.list_checkpoints()) == 1
        cp_mgr.reset("reset_task")
        assert len(cp_mgr.list_checkpoints()) == 0
        cp = cp_mgr.load("reset_task")
        assert cp["processed_count"] == 0

    def test_multiple_tasks(self, cp_mgr: CheckpointManager):
        """多个任务互不干扰"""
        cp_mgr.mark_processed("task_a", ["a1", "a2"])
        cp_mgr.mark_processed("task_b", ["b1"])
        cp_mgr.mark_failed("task_a", ["a3"])
        cp_a = cp_mgr.load("task_a")
        cp_b = cp_mgr.load("task_b")
        assert set(cp_a["processed_ids"]) == {"a1", "a2"}
        assert set(cp_a["failed_ids"]) == {"a3"}
        assert cp_b["processed_ids"] == ["b1"]

    def test_list_checkpoints(self, cp_mgr: CheckpointManager):
        """list_checkpoints 应返回所有任务 ID"""
        cp_mgr.mark_processed("task_x", ["x"])
        cp_mgr.mark_processed("task_y", ["y"])
        checkpoints = cp_mgr.list_checkpoints()
        assert "task_x" in checkpoints
        assert "task_y" in checkpoints

    def test_duplicate_ids(self, cp_mgr: CheckpointManager):
        """重复标记已处理 ID 不应累加"""
        cp_mgr.mark_processed("dedup", ["id1"])
        cp_mgr.mark_processed("dedup", ["id1"])
        cp = cp_mgr.load("dedup")
        assert cp["processed_ids"] == ["id1"]
        assert cp["processed_count"] == 1


# ===================================================================
# 测试 3: 数据源测试
# ===================================================================


class TestSQliteDataSource:
    """SQLite 数据源测试"""

    def _run_with_cleanup(self, cards, test_fn):
        """辅助方法：创建数据库，执行测试，确保清理"""
        import gc
        db_path = _make_temp_db(cards)
        try:
            test_fn(db_path)
        finally:
            # 强制清理所有对 db_path 的引用
            gc.collect()
            try:
                os.unlink(db_path)
            except PermissionError:
                # Windows 上偶尔延迟释放，再试一次
                import time
                time.sleep(0.1)
                gc.collect()
                os.unlink(db_path)

    def test_get_total_count(self):
        def _test(db_path):
            ds = SQliteDataSource(db_path=db_path, text_field="fields")
            assert ds.get_total_count() == 2
        cards = [
            {"id": 1, "fields": {"company": "链客宝科技", "desc": "企业数字名片平台"}, "created_at": "2025-01-01"},
            {"id": 2, "fields": {"company": "数据智能", "desc": "AI 解决方案"}, "created_at": "2025-01-02"},
        ]
        self._run_with_cleanup(cards, _test)

    def test_iter_records(self):
        def _test(db_path):
            ds = SQliteDataSource(db_path=db_path, text_field="fields")
            all_records = []
            for batch in ds.iter_records(batch_size=1):
                all_records.extend(batch)
            assert len(all_records) == 2
            ids = [rid for rid, _ in all_records]
            assert "10" in ids
            assert "20" in ids
            texts = [t for _, t in all_records]
            assert any("测试公司" in t for t in texts)
            assert any("另一家公司" in t for t in texts)
        cards = [
            {"id": 10, "fields": {"company": "测试公司", "desc": "测试描述"}, "created_at": ""},
            {"id": 20, "fields": {"company": "另一家公司"}, "created_at": ""},
        ]
        self._run_with_cleanup(cards, _test)

    def test_get_all_ids(self):
        def _test(db_path):
            ds = SQliteDataSource(db_path=db_path, text_field="fields")
            ids = ds.get_all_ids()
            assert ids == ["1", "2", "3"]
        cards = [
            {"id": 1, "fields": {"desc": "a"}, "created_at": ""},
            {"id": 2, "fields": {"desc": "b"}, "created_at": ""},
            {"id": 3, "fields": {"desc": "c"}, "created_at": ""},
        ]
        self._run_with_cleanup(cards, _test)

    def test_compute_md5(self):
        def _test(db_path):
            ds = SQliteDataSource(db_path=db_path, text_field="fields")
            md5_1 = ds.compute_md5()
            md5_2 = ds.compute_md5()
            assert md5_1 == md5_2
            assert len(md5_1) == 32
        cards = [
            {"id": 1, "fields": {"text": "hello"}, "created_at": ""},
            {"id": 2, "fields": {"text": "world"}, "created_at": ""},
        ]
        self._run_with_cleanup(cards, _test)

    def test_empty_table(self):
        def _test(db_path):
            ds = SQliteDataSource(db_path=db_path, text_field="fields")
            assert ds.get_total_count() == 0
            all_records = []
            for batch in ds.iter_records():
                all_records.extend(batch)
            assert all_records == []
        self._run_with_cleanup([], _test)

    def test_fields_json_extraction(self):
        def _test(db_path):
            ds = SQliteDataSource(db_path=db_path, text_field="fields")
            for batch in ds.iter_records():
                for rid, text in batch:
                    assert "链客宝" in text
                    assert "CTO" in text
                    assert "13800138000" in text
        cards = [
            {
                "id": 1,
                "fields": {
                    "company": "链客宝",
                    "position": "CTO",
                    "phone": "13800138000",
                    "email": "cto@liankebao.com",
                },
                "created_at": "",
            },
        ]
        self._run_with_cleanup(cards, _test)

    def test_where_clause(self):
        def _test(db_path):
            ds = SQliteDataSource(
                db_path=db_path,
                text_field="fields",
                where_clause="created_at >= '2025-01-01'",
            )
            assert ds.get_total_count() == 1
            ids = ds.get_all_ids()
            assert ids == ["1"]
        cards = [
            {"id": 1, "fields": {"desc": "active"}, "created_at": "2025-01-01"},
            {"id": 2, "fields": {"desc": "inactive"}, "created_at": "2024-01-01"},
        ]
        self._run_with_cleanup(cards, _test)


class TestJsonlDataSource:
    """JSONL 数据源测试"""

    def test_basic_read(self):
        """JSONL 应正确读取记录"""
        records = [
            {"id": "a1", "text": "第一条记录"},
            {"id": "a2", "text": "第二条记录"},
            {"id": "a3", "text": "第三条记录"},
        ]
        path = _make_temp_jsonl(records)
        try:
            ds = JsonlDataSource(file_path=path, text_field="text", id_field="id")
            assert ds.get_total_count() == 3
            all_records = []
            for batch in ds.iter_records(batch_size=2):
                all_records.extend(batch)
            assert len(all_records) == 3
            texts = [t for _, t in all_records]
            assert "第一条记录" in texts
        finally:
            os.unlink(path)

    def test_get_all_ids(self):
        """get_all_ids 应返回所有 ID"""
        records = [
            {"id": "x", "text": "hello"},
            {"id": "y", "text": "world"},
        ]
        path = _make_temp_jsonl(records)
        try:
            ds = JsonlDataSource(file_path=path, text_field="text", id_field="id")
            assert ds.get_all_ids() == ["x", "y"]
        finally:
            os.unlink(path)

    def test_md5_consistency(self):
        """MD5 校验应一致"""
        records = [
            {"id": "1", "text": "data"},
            {"id": "2", "text": "more data"},
        ]
        path = _make_temp_jsonl(records)
        try:
            ds = JsonlDataSource(file_path=path, text_field="text")
            md5_1 = ds.compute_md5()
            md5_2 = ds.compute_md5()
            assert md5_1 == md5_2
        finally:
            os.unlink(path)

    def test_empty_file(self):
        """空文件应返回 0 条记录"""
        path = _make_temp_jsonl([])
        try:
            ds = JsonlDataSource(file_path=path, text_field="text")
            assert ds.get_total_count() == 0
        finally:
            os.unlink(path)

    def test_missing_field(self):
        """缺少文本字段时应跳过"""
        records = [
            {"id": "1", "text": "valid"},
            {"id": "2", "other": "no text field"},
            {"id": "3", "text": ""},
        ]
        path = _make_temp_jsonl(records)
        try:
            ds = JsonlDataSource(file_path=path, text_field="text")
            all_records = []
            for batch in ds.iter_records():
                all_records.extend(batch)
            assert len(all_records) == 1
            assert all_records[0][0] == "1"
        finally:
            os.unlink(path)


class TestCsvDataSource:
    """CSV 数据源测试"""

    def test_basic_read(self):
        """CSV 应正确读取记录"""
        rows = [
            {"id": "r1", "text": "CSV 记录1", "extra": "x"},
            {"id": "r2", "text": "CSV 记录2", "extra": "y"},
        ]
        path = _make_temp_csv(rows)
        try:
            ds = CsvDataSource(file_path=path, text_field="text", id_field="id")
            assert ds.get_total_count() == 2
            all_records = []
            for batch in ds.iter_records(batch_size=1):
                all_records.extend(batch)
            assert len(all_records) == 2
            texts = [t for _, t in all_records]
            assert "CSV 记录1" in texts
        finally:
            os.unlink(path)

    def test_get_all_ids(self):
        """get_all_ids 应返回所有 ID"""
        rows = [
            {"id": "100", "text": "A"},
            {"id": "200", "text": "B"},
        ]
        path = _make_temp_csv(rows)
        try:
            ds = CsvDataSource(file_path=path, text_field="text", id_field="id")
            assert ds.get_all_ids() == ["100", "200"]
        finally:
            os.unlink(path)

    def test_tab_delimiter(self):
        """Tab 分隔符应正确解析"""
        rows = [
            {"id": "1", "text": "tab data"},
        ]
        path = _make_temp_csv(rows, delimiter="\t")
        try:
            ds = CsvDataSource(file_path=path, text_field="text", id_field="id", delimiter="\t")
            for batch in ds.iter_records():
                assert len(batch) == 1
                assert batch[0][1] == "tab data"
        finally:
            os.unlink(path)

    def test_missing_id_field(self):
        """缺少 ID 字段时应使用行号回退"""
        rows = [
            {"text": "no id col"},
            {"text": "still works"},
        ]
        path = _make_temp_csv(rows)
        try:
            ds = CsvDataSource(file_path=path, text_field="text", id_field="id")
            ids = ds.get_all_ids()
            # id 字段不存在，使用 row_N 回退
            assert ids == ["row_0", "row_1"]
        finally:
            os.unlink(path)

    def test_md5_consistency(self):
        """MD5 校验应一致"""
        rows = [
            {"id": "1", "text": "csv data"},
        ]
        path = _make_temp_csv(rows)
        try:
            ds = CsvDataSource(file_path=path, text_field="text")
            md5 = ds.compute_md5()
            assert len(md5) == 32
        finally:
            os.unlink(path)


# ===================================================================
# 测试 4: EmbedScheduler 集成测试
# ===================================================================


class TestEmbedScheduler:
    """嵌入调度器集成测试"""

    @pytest.fixture
    def scheduler(self, tmp_dir: str) -> EmbedScheduler:
        """EmbedScheduler 实例（使用临时目录）"""
        cp_dir = os.path.join(tmp_dir, "cp")
        vdb = os.path.join(tmp_dir, "vers.db")
        # 使用自定义缓存目录，避免干扰默认缓存
        cache_dir = os.path.join(tmp_dir, "emb_cache")
        return EmbedScheduler(
            checkpoint_dir=cp_dir,
            version_db_path=vdb,
            embedder_kwargs={
                "force_fallback": True,
                "cache_dir": cache_dir,
            },
        )

    def test_process_batch_empty(self, scheduler: EmbedScheduler):
        """空文本列表应返回空列表"""
        result = scheduler.process_batch([])
        assert result == []

    def test_process_batch_single(self, scheduler: EmbedScheduler):
        """单条文本应返回嵌入向量"""
        result = scheduler.process_batch(["测试文本"], batch_size=1)
        assert result is not None
        assert len(result) == 1
        # 降级模式维度 768
        assert len(result[0]) == 768

    def test_process_batch_multiple(self, scheduler: EmbedScheduler):
        """多条文本应全部编码"""
        texts = ["文本A", "文本B", "文本C"]
        result = scheduler.process_batch(texts, batch_size=2)
        assert result is not None
        assert len(result) == 3
        for vec in result:
            assert len(vec) == 768

    def test_process_batch_cache_hit(self, scheduler: EmbedScheduler):
        """重复调用应命中缓存"""
        texts = ["缓存测试文本"]
        # 第一次：编码并写入缓存
        result1 = scheduler.process_batch(texts)
        assert result1 is not None
        # 第二次：应命中缓存
        result2 = scheduler.process_batch(texts)
        assert result2 is not None
        # 向量应相同（降级模式是确定性的）
        assert result1[0] == result2[0]

    def test_status_initial(self, scheduler: EmbedScheduler):
        """初始状态应显示无运行任务"""
        status = scheduler.status()
        assert status["running"] is False
        assert status["task_id"] == ""
        assert status["total"] == 0

    def test_status_after_batch(self, scheduler: EmbedScheduler):
        """process_batch 后状态应更新"""
        scheduler.process_batch(["状态测试"], batch_size=1)
        status = scheduler.status()
        assert status["processed"] >= 1
        assert status["cache_hits"] >= 0

    def test_version_manager_integration(self, scheduler: EmbedScheduler):
        """调度器的版本管理器应正常工作"""
        vm = scheduler.version_manager
        v = vm.next_version()
        assert v == "v1"
        vm.register_version(
            version=v,
            embedding_model="test",
            record_count=5,
            data_source="test",
            text_field="text",
        )
        latest = scheduler.get_latest_version()
        assert latest is not None
        assert latest["version"] == "v1"

    def test_checkpoint_manager_integration(self, scheduler: EmbedScheduler):
        """调度器的检查点管理器应正常工作"""
        cm = scheduler.checkpoint_manager
        cm.mark_processed("integ_test", ["id1", "id2"])
        cp = cm.load("integ_test")
        assert cp["processed_count"] == 2

    def test_schedule_full_refresh_with_jsonl(self, scheduler: EmbedScheduler, tmp_dir: str):
        """使用 JSONL 数据源执行全量刷新"""
        records = [
            {"id": "1", "text": "企业数字名片服务"},
            {"id": "2", "text": "AI 智能匹配引擎"},
            {"id": "3", "text": "数据管道预处理"},
        ]
        path = _make_temp_jsonl(records)
        try:
            ds = JsonlDataSource(file_path=path, text_field="text", id_field="id")
            version = scheduler.schedule_full_refresh(
                data_source=ds,
                text_field="text",
                batch_size=2,
            )
            assert version == "v1"
            status = scheduler.status()
            assert status["processed"] == 3
            assert status["total"] == 3
            # 验证版本元数据
            meta = scheduler.get_version("v1")
            assert meta is not None
            assert meta["record_count"] == 3
        finally:
            os.unlink(path)

    def test_schedule_full_refresh_with_csv(self, scheduler: EmbedScheduler, tmp_dir: str):
        """使用 CSV 数据源执行全量刷新"""
        rows = [
            {"id": "c1", "text": "CSV 记录一"},
            {"id": "c2", "text": "CSV 记录二"},
        ]
        path = _make_temp_csv(rows)
        try:
            ds = CsvDataSource(file_path=path, text_field="text", id_field="id")
            version = scheduler.schedule_full_refresh(
                data_source=ds,
                text_field="text",
                batch_size=10,
            )
            assert version == "v1"
            meta = scheduler.get_latest_version()
            assert meta is not None
            assert meta["record_count"] == 2
        finally:
            os.unlink(path)

    def test_schedule_full_refresh_with_sqlite(self, scheduler: EmbedScheduler, tmp_dir: str):
        """使用 SQLite 数据源执行全量刷新"""
        cards = [
            {"id": 1, "fields": {"company": "链客宝科技", "desc": "名片平台"}, "created_at": ""},
            {"id": 2, "fields": {"company": "数据智能公司", "desc": "AI 平台"}, "created_at": ""},
        ]
        db_path = _make_temp_db(cards)
        try:
            ds = SQliteDataSource(db_path=db_path, text_field="fields")
            version = scheduler.schedule_full_refresh(
                data_source=ds,
                text_field="fields",
                batch_size=10,
            )
            assert version == "v1"
            meta = scheduler.get_latest_version()
            assert meta is not None
            assert meta["record_count"] == 2
            assert "SQLite" in meta["data_source"]
        finally:
            os.unlink(db_path)


# ===================================================================
# 测试 5: 边界情况
# ===================================================================


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_data_source(self, tmp_dir: str):
        """空数据源全量刷新应生成版本"""
        vdb = os.path.join(tmp_dir, "vers.db")
        cp_dir = os.path.join(tmp_dir, "cp")
        cache_dir = os.path.join(tmp_dir, "emb_cache")
        scheduler = EmbedScheduler(
            checkpoint_dir=cp_dir,
            version_db_path=vdb,
            embedder_kwargs={
                "force_fallback": True,
                "cache_dir": cache_dir,
            },
        )
        # 空 JSONL
        path = _make_temp_jsonl([])
        try:
            ds = JsonlDataSource(file_path=path, text_field="text")
            version = scheduler.schedule_full_refresh(ds, text_field="text")
            assert version == "v1"
            meta = scheduler.get_version("v1")
            assert meta is not None
            assert meta["record_count"] == 0  # 无数据
        finally:
            os.unlink(path)

    def test_resume_no_checkpoint(self, tmp_dir: str):
        """resume 无检查点时应返回提示"""
        vdb = os.path.join(tmp_dir, "vers.db")
        cp_dir = os.path.join(tmp_dir, "cp")
        cache_dir = os.path.join(tmp_dir, "emb_cache")
        scheduler = EmbedScheduler(
            checkpoint_dir=cp_dir,
            version_db_path=vdb,
            embedder_kwargs={
                "force_fallback": True,
                "cache_dir": cache_dir,
            },
        )
        result = scheduler.resume("nonexistent_task")
        assert result["status"] == "empty_checkpoint"

    def test_resume_with_checkpoint(self, tmp_dir: str):
        """resume 应能加载已有的检查点"""
        cp_dir = os.path.join(tmp_dir, "cp")
        vdb = os.path.join(tmp_dir, "vers.db")
        cache_dir = os.path.join(tmp_dir, "emb_cache")
        os.makedirs(cp_dir, exist_ok=True)

        # 先手动创建检查点（含 total_count）
        cm = CheckpointManager(checkpoint_dir=cp_dir)
        cm.save("full_refresh_v1_test", {
            "processed_ids": ["id1", "id2"],
            "failed_ids": ["id3"],
            "total_count": 5,
            "processed_count": 2,
        })

        scheduler = EmbedScheduler(
            checkpoint_dir=cp_dir,
            version_db_path=vdb,
            embedder_kwargs={
                "force_fallback": True,
                "cache_dir": cache_dir,
            },
        )
        result = scheduler.resume("full_refresh_v1_test")
        assert result["status"] == "partial"
        assert result["processed"] == 2
        assert result["failed"] == 1
        assert result["total"] == 5

    def test_list_versions_empty(self, tmp_dir: str):
        """无版本时 list_versions 返回空列表"""
        vdb = os.path.join(tmp_dir, "vers.db")
        vm = VersionManager(db_path=vdb)
        assert vm.list_versions() == []
        assert vm.list_version_metadata() == []

    def test_incremental_update(self, tmp_dir: str):
        """增量更新应正确处理"""
        vdb = os.path.join(tmp_dir, "vers.db")
        cp_dir = os.path.join(tmp_dir, "cp")
        cache_dir = os.path.join(tmp_dir, "emb_cache")
        scheduler = EmbedScheduler(
            checkpoint_dir=cp_dir,
            version_db_path=vdb,
            embedder_kwargs={
                "force_fallback": True,
                "cache_dir": cache_dir,
            },
        )
        records = [
            {"id": "1", "text": "记录一"},
            {"id": "2", "text": "记录二"},
        ]
        path = _make_temp_jsonl(records)
        try:
            ds = JsonlDataSource(file_path=path, text_field="text", id_field="id")
            count = scheduler.schedule_incremental(
                data_source=ds,
                text_field="text",
                batch_size=1,
            )
            assert count == 2
            # 再次增量（应全部命中缓存）
            count2 = scheduler.schedule_incremental(
                data_source=ds,
                text_field="text",
                batch_size=1,
            )
            # 虽然已缓存，但检查点会阻止重复处理
            assert count2 == 0
        finally:
            os.unlink(path)

    def test_multiple_versions(self, tmp_dir: str):
        """多次全量刷新应生成递增版本号"""
        vdb = os.path.join(tmp_dir, "vers.db")
        cp_dir = os.path.join(tmp_dir, "cp")
        cache_dir = os.path.join(tmp_dir, "emb_cache")
        scheduler = EmbedScheduler(
            checkpoint_dir=cp_dir,
            version_db_path=vdb,
            embedder_kwargs={
                "force_fallback": True,
                "cache_dir": cache_dir,
            },
        )

        for i in range(3):
            records = [{"id": str(i), "text": f"version_{i}_data"}]
            path = _make_temp_jsonl(records)
            try:
                ds = JsonlDataSource(file_path=path, text_field="text", id_field="id")
                v = scheduler.schedule_full_refresh(ds, text_field="text")
                assert v == f"v{i + 1}"
            finally:
                os.unlink(path)

        versions = scheduler.list_versions()
        assert versions == ["v3", "v2", "v1"]
