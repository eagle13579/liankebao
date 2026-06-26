"""
链客宝 - 分钟级增量索引服务 (InMemoryIndex + 自动更新)
=======================================================

核心职责：
1. 每 60 秒从 sync_pipeline 获取增量变更
2. 批量聚合 → BGE-M3 向量化 → 更新 InMemoryIndex + embedding_cache
3. 延迟保证 < 1 分钟（从数据变更到索引更新）
4. 版本标记：每次更新加时间戳版本号

组件：
- InMemoryIndex: 内存向量索引（支持 add/search/delete/update/save/load）
- MinuteIndexer: 分钟级增量索引服务（自动轮询+批处理）

Author: 长右 (P8, 移动端工程师, 增量同步/索引)
"""

from __future__ import annotations

import json
import logging
import math
import os
import pickle
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_CHECK_INTERVAL = 60  # 默认轮询间隔（秒）
DEFAULT_EMBEDDING_DIM = 768  # BGE-M3 默认维度
DEFAULT_INDEX_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".minute_index",
)
DEFAULT_PROGRESS_FILE = os.path.join(DEFAULT_INDEX_DIR, "index_progress.json")


# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

Vector = List[float]
Metadata = Dict[str, Any]
SearchResult = Tuple[str, float, Metadata]  # (id, score, metadata)


# ---------------------------------------------------------------------------
# InMemoryIndex — 内存向量索引
# ---------------------------------------------------------------------------


@dataclass
class IndexEntry:
    """索引单条条目"""
    id: str
    vector: Vector
    metadata: Metadata
    version: str  # ISO 格式时间戳
    added_at: float  # time.time()


class InMemoryIndex:
    """内存向量索引

    纯 Python 实现（无 FAISS 依赖），使用余弦相似度进行向量检索。
    支持线程安全的增删改查和持久化。

    Usage:
        index = InMemoryIndex(dim=768)
        index.add("doc1", [0.1, 0.2, ...], {"title": "文档1"})
        results = index.search(query_vector, top_k=5)
        index.save("/path/to/index.pkl")
        index.load("/path/to/index.pkl")
    """

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self._dim = dim
        self._entries: Dict[str, IndexEntry] = {}
        self._lock = threading.RLock()
        self._version_counter: int = 0

    # ------------------------------------------------------------------
    # 核心操作
    # ------------------------------------------------------------------

    def add(self, id: str, vector: Vector, metadata: Metadata) -> None:
        """添加条目到索引

        Args:
            id: 唯一标识
            vector: 向量（长度必须与 dim 一致）
            metadata: 元数据字典
        """
        if len(vector) != self._dim:
            raise ValueError(
                f"向量维度 {len(vector)} 不匹配索引维度 {self._dim}"
            )

        version = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._version_counter += 1
            self._entries[id] = IndexEntry(
                id=id,
                vector=vector,
                metadata=metadata,
                version=version,
                added_at=time.time(),
            )

    def search(
        self,
        query_vector: Vector,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """余弦相似度搜索

        Args:
            query_vector: 查询向量
            top_k: 返回 top-K 结果

        Returns:
            [(id, score, metadata), ...] 按相似度降序排列
        """
        if not self._entries:
            return []

        query_norm = self._norm(query_vector)
        if query_norm == 0:
            return []

        scored: List[Tuple[float, str]] = []

        with self._lock:
            for eid, entry in self._entries.items():
                sim = self._cosine_sim(query_vector, entry.vector, query_norm)
                scored.append((sim, eid))

        # 按相似度降序
        scored.sort(key=lambda x: x[0], reverse=True)

        results: List[SearchResult] = []
        with self._lock:
            for sim, eid in scored[:top_k]:
                entry = self._entries.get(eid)
                if entry is not None:
                    results.append((eid, round(sim, 6), dict(entry.metadata)))

        return results

    def delete(self, id: str) -> bool:
        """删除条目

        Returns:
            True 如果条目存在并删除
        """
        with self._lock:
            if id in self._entries:
                del self._entries[id]
                return True
            return False

    def update(self, id: str, vector: Vector, metadata: Metadata) -> bool:
        """更新条目

        Args:
            id: 条目 ID
            vector: 新向量
            metadata: 新元数据

        Returns:
            True 如果条目存在并更新
        """
        if len(vector) != self._dim:
            raise ValueError(
                f"向量维度 {len(vector)} 不匹配索引维度 {self._dim}"
            )

        version = datetime.now(timezone.utc).isoformat()

        with self._lock:
            if id not in self._entries:
                return False
            self._version_counter += 1
            self._entries[id] = IndexEntry(
                id=id,
                vector=vector,
                metadata=metadata,
                version=version,
                added_at=time.time(),
            )
            return True

    def get(self, id: str) -> Optional[IndexEntry]:
        """获取条目（不用于搜索，仅用于检查）"""
        with self._lock:
            entry = self._entries.get(id)
            if entry is None:
                return None
            return IndexEntry(
                id=entry.id,
                vector=list(entry.vector),
                metadata=dict(entry.metadata),
                version=entry.version,
                added_at=entry.added_at,
            )

    def size(self) -> int:
        """索引条目数"""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """清空索引"""
        with self._lock:
            self._entries.clear()
            self._version_counter = 0

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """持久化索引到文件

        Format: pickle 序列化 (确保 vector 和 metadata 可序列化)
        """
        with self._lock:
            data = {
                "dim": self._dim,
                "version_counter": self._version_counter,
                "entries": {
                    eid: {
                        "id": entry.id,
                        "vector": entry.vector,
                        "metadata": entry.metadata,
                        "version": entry.version,
                        "added_at": entry.added_at,
                    }
                    for eid, entry in self._entries.items()
                },
            }

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

        logger.info("InMemoryIndex: 已保存 %d 条目到 %s", len(data["entries"]), path)

    def load(self, path: str) -> bool:
        """从文件加载索引

        Returns:
            True 如果成功加载
        """
        if not os.path.exists(path):
            logger.warning("InMemoryIndex: 索引文件不存在 %s", path)
            return False

        try:
            with open(path, "rb") as f:
                data = pickle.load(f)

            with self._lock:
                self._dim = data.get("dim", DEFAULT_EMBEDDING_DIM)
                self._version_counter = data.get("version_counter", 0)
                self._entries.clear()
                for eid, entry_data in data.get("entries", {}).items():
                    self._entries[eid] = IndexEntry(
                        id=entry_data["id"],
                        vector=entry_data["vector"],
                        metadata=entry_data["metadata"],
                        version=entry_data["version"],
                        added_at=entry_data["added_at"],
                    )

            logger.info(
                "InMemoryIndex: 已加载 %d 条目从 %s", len(self._entries), path
            )
            return True

        except (pickle.UnpicklingError, EOFError, KeyError) as exc:
            logger.error("InMemoryIndex: 加载索引失败 - %s", exc)
            return False

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _norm(vec: Vector) -> float:
        return math.sqrt(sum(v * v for v in vec))

    @staticmethod
    def _cosine_sim(a: Vector, b: Vector, a_norm: Optional[float] = None) -> float:
        b_norm = InMemoryIndex._norm(b)
        if a_norm is None:
            a_norm = InMemoryIndex._norm(a)
        if a_norm == 0 or b_norm == 0:
            return 0.0
        dot = sum(av * bv for av, bv in zip(a, b))
        return dot / (a_norm * b_norm)

    def __len__(self) -> int:
        return self.size()

    def __contains__(self, id: str) -> bool:
        with self._lock:
            return id in self._entries

    def __repr__(self) -> str:
        return (
            f"InMemoryIndex(dim={self._dim}, entries={self.size()}, "
            f"version={self._version_counter})"
        )


# ---------------------------------------------------------------------------
# MinuteIndexer — 分钟级增量索引服务
# ---------------------------------------------------------------------------


@dataclass
class IndexerStatus:
    """索引器状态"""
    running: bool = False
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    check_interval: int = DEFAULT_CHECK_INTERVAL
    total_cycles: int = 0
    total_records_indexed: int = 0
    total_errors: int = 0
    last_cycle_time: Optional[str] = None
    last_index_version: Optional[str] = None
    index_size: int = 0
    last_error: Optional[str] = None
    sources: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "check_interval": self.check_interval,
            "total_cycles": self.total_cycles,
            "total_records_indexed": self.total_records_indexed,
            "total_errors": self.total_errors,
            "last_cycle_time": self.last_cycle_time,
            "last_index_version": self.last_index_version,
            "index_size": self.index_size,
            "last_error": self.last_error,
            "sources": dict(self.sources),
        }


class MinuteIndexer:
    """分钟级增量索引服务

    每 check_interval 秒从 sync_pipeline 获取增量变更，经 BGE-M3 向量化后，
    同时更新 InMemoryIndex 和 embedding_cache。

    Args:
        sync_pipeline: RealtimeSyncPipeline 实例（用于获取增量变更）
        cache: EmbeddingCache 实例（用于缓存向量）
        check_interval: 轮询间隔（秒），默认 60
        dim: 向量维度，默认 768 (BGE-M3)
        index_dir: 索引持久化目录
        embedder: 可选的嵌入器实例（默认使用 sync_pipeline 的嵌入器）
    """

    def __init__(
        self,
        sync_pipeline: Any,
        cache: Any,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
        dim: int = DEFAULT_EMBEDDING_DIM,
        index_dir: Optional[str] = None,
        embedder: Any = None,
    ) -> None:
        self._sync_pipeline = sync_pipeline
        self._cache = cache
        self._check_interval = max(5, check_interval)
        self._dim = dim
        self._index_dir = index_dir or DEFAULT_INDEX_DIR
        self._embedder = embedder

        # 内存索引
        self._index = InMemoryIndex(dim=dim)

        # 每个数据源的追踪状态（记录已索引到的 max_updated_at）
        self._source_progress: Dict[str, str] = {}

        # 线程控制
        self._running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # 状态
        self._status = IndexerStatus(check_interval=self._check_interval)

        # 尝试加载持久化进度
        self._load_progress()

        logger.info(
            "MinuteIndexer: 初始化完成 (check_interval=%ss, dim=%d, index_dir=%s)",
            self._check_interval, self._dim, self._index_dir,
        )

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动索引后台线程"""
        if self._running:
            logger.warning("MinuteIndexer: 已在运行中，忽略重复 start()")
            return

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="MinuteIndexer",
            daemon=True,
        )
        self._thread.start()

        with self._lock:
            self._status.running = True
            self._status.started_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "MinuteIndexer: 已启动 (check_interval=%ss)",
            self._check_interval,
        )

    def stop(self, timeout: float = 10.0) -> None:
        """停止后台线程"""
        if not self._running:
            logger.warning("MinuteIndexer: 未在运行，忽略 stop()")
            return

        self._stop_event.set()
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "MinuteIndexer: 线程未在 %ss 内结束", timeout
                )

        self._thread = None

        with self._lock:
            self._status.running = False
            self._status.stopped_at = datetime.now(timezone.utc).isoformat()

        self._save_progress()

        logger.info("MinuteIndexer: 已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """返回当前索引状态"""
        with self._lock:
            self._status.index_size = self._index.size()
            return self._status.to_dict()

    # ------------------------------------------------------------------
    # 索引访问
    # ------------------------------------------------------------------

    @property
    def index(self) -> InMemoryIndex:
        """获取底层 InMemoryIndex（只读建议）"""
        return self._index

    # ------------------------------------------------------------------
    # 手动触发
    # ------------------------------------------------------------------

    def trigger_index_cycle(self) -> Dict[str, Any]:
        """手动触发一次索引周期

        Returns:
            结果字典 {"records_indexed": int, "errors": int, "version": str}
        """
        return self._run_index_cycle()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save_index(self, path: Optional[str] = None) -> str:
        """持久化索引到文件

        Args:
            path: 保存路径，默认 index_dir/index.pkl

        Returns:
            实际保存路径
        """
        save_path = path or os.path.join(self._index_dir, "index.pkl")
        self._index.save(save_path)
        self._save_progress()
        return save_path

    def load_index(self, path: Optional[str] = None) -> bool:
        """从文件加载索引

        Args:
            path: 加载路径，默认 index_dir/index.pkl
        """
        load_path = path or os.path.join(self._index_dir, "index.pkl")
        return self._index.load(load_path)

    # ------------------------------------------------------------------
    # 内部：进度持久化
    # ------------------------------------------------------------------

    def _progress_file(self) -> str:
        return os.path.join(self._index_dir, "index_progress.json")

    def _save_progress(self) -> None:
        """保存索引进度到 JSON"""
        with self._lock:
            data = {
                "source_progress": dict(self._source_progress),
                "status": {
                    "total_cycles": self._status.total_cycles,
                    "total_records_indexed": self._status.total_records_indexed,
                    "last_index_version": self._status.last_index_version,
                },
            }

        try:
            os.makedirs(self._index_dir, exist_ok=True)
            with open(self._progress_file(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as exc:
            logger.error("MinuteIndexer: 保存进度失败 - %s", exc)

    def _load_progress(self) -> None:
        """加载持久化的索引进度"""
        pf = self._progress_file()
        if not os.path.exists(pf):
            return

        try:
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                self._source_progress.update(
                    data.get("source_progress", {})
                )
                st = data.get("status", {})
                self._status.total_cycles = st.get("total_cycles", 0)
                self._status.total_records_indexed = st.get(
                    "total_records_indexed", 0
                )
                self._status.last_index_version = st.get(
                    "last_index_version"
                )

            logger.info(
                "MinuteIndexer: 已加载进度 (%d sources, %d cycles)",
                len(self._source_progress), self._status.total_cycles,
            )

        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("MinuteIndexer: 加载进度失败 - %s", exc)

    # ------------------------------------------------------------------
    # 内部：主循环
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """主循环（后台线程）"""
        logger.debug("MinuteIndexer: 索引循环已启动")

        while not self._stop_event.is_set():
            cycle_start = time.perf_counter()

            try:
                result = self._run_index_cycle()
                if result["records_indexed"] > 0:
                    logger.info(
                        "MinuteIndexer: 索引周期完成 (indexed=%d, errors=%d, "
                        "version=%s, elapsed=%.2fs)",
                        result["records_indexed"],
                        result["errors"],
                        result["version"],
                        time.perf_counter() - cycle_start,
                    )
            except Exception as exc:
                logger.error("MinuteIndexer: 索引周期异常 - %s", exc)
                with self._lock:
                    self._status.total_errors += 1
                    self._status.last_error = f"{type(exc).__name__}: {exc}"

            # 等待下一次轮询（可中断）
            self._stop_event.wait(timeout=self._check_interval)

        logger.debug("MinuteIndexer: 索引循环已退出")

    def _run_index_cycle(self) -> Dict[str, Any]:
        """执行一次索引周期

        流程:
        1. 从 sync_pipeline 获取各数据源的增量变更
        2. 批量聚合变更文本
        3. BGE-M3 向量化
        4. 更新 InMemoryIndex + embedding_cache
        5. 版本标记 + 记录进度

        Returns:
            {"records_indexed": int, "errors": int, "version": str}
        """
        total_indexed = 0
        total_errors = 0
        version = datetime.now(timezone.utc).isoformat()

        # 获取数据源列表
        source_names = self._sync_pipeline.list_sources()
        if not source_names:
            logger.debug("MinuteIndexer: 无数据源，跳过周期")
            return {
                "records_indexed": 0,
                "errors": 0,
                "version": version,
            }

        for source_name in source_names:
            try:
                indexed = self._index_source(source_name, version)
                total_indexed += indexed
            except Exception as exc:
                logger.error(
                    "MinuteIndexer: 数据源 %r 索引失败 - %s",
                    source_name, exc,
                )
                total_errors += 1
                with self._lock:
                    self._status.last_error = (
                        f"{source_name}: {type(exc).__name__}: {exc}"
                    )

        # 更新状态
        with self._lock:
            self._status.total_cycles += 1
            self._status.total_records_indexed += total_indexed
            self._status.total_errors += total_errors
            self._status.last_cycle_time = version
            self._status.last_index_version = version
            self._status.index_size = self._index.size()

        # 保存进度
        self._save_progress()

        return {
            "records_indexed": total_indexed,
            "errors": total_errors,
            "version": version,
        }

    def _index_source(
        self, source_name: str, version: str
    ) -> int:
        """索引单个数据源的增量变更

        Args:
            source_name: 数据源名称
            version: 当前索引版本时间戳

        Returns:
            本次索引的记录数
        """
        # 获取该数据源的最新 max_updated_at
        config = self._sync_pipeline._data_sources.get(source_name)
        if config is None:
            logger.warning("MinuteIndexer: 数据源 %r 不存在", source_name)
            return 0

        max_updated_at = self._sync_pipeline._query_max_updated_at(config)
        if max_updated_at is None:
            # 表无数据，跳过
            return 0

        # 获取已索引到的位置
        last_indexed_at = self._source_progress.get(source_name)

        # 首次：记录进度并跳过
        if last_indexed_at is None:
            with self._lock:
                self._source_progress[source_name] = max_updated_at
            logger.info(
                "MinuteIndexer [%s]: 首次初始化 (max_updated_at=%s)",
                source_name, max_updated_at,
            )
            return 0

        # 无新变更
        if max_updated_at <= last_indexed_at:
            return 0

        # 增量拉取变更
        changed_records = self._sync_pipeline._pull_incremental(
            config, last_indexed_at
        )
        if not changed_records:
            # 有 updated_at 变更但无匹配记录
            with self._lock:
                self._source_progress[source_name] = max_updated_at
            return 0

        # --- 向量化 ---
        texts = [rec.fields_json for rec in changed_records]
        vectors = self._encode_texts(texts)

        # --- 更新索引 ---
        indexed_count = 0
        cache_updates = []

        for record, vec in zip(changed_records, vectors):
            if vec is None:
                continue

            try:
                # 元数据
                try:
                    meta = json.loads(record.fields_json)
                except json.JSONDecodeError:
                    meta = {"raw": record.fields_json}

                meta["source"] = record.source_name
                meta["updated_at"] = record.updated_at
                meta["record_id"] = record.record_id

                # 更新 InMemoryIndex
                record_id = f"{source_name}:{record.record_id}"
                if record_id in self._index:
                    self._index.update(record_id, vec, meta)
                else:
                    self._index.add(record_id, vec, meta)

                # 准备缓存更新
                cache_updates.append((record.fields_json, vec))
                indexed_count += 1

            except Exception as exc:
                logger.warning(
                    "MinuteIndexer [%s]: 索引记录 %s 失败 - %s",
                    source_name, record.record_id, exc,
                )

        # --- 更新 embedding_cache ---
        if cache_updates and self._cache is not None:
            try:
                self._cache.batch_set(cache_updates)
                logger.debug(
                    "MinuteIndexer [%s]: 缓存更新 %d 条",
                    source_name, len(cache_updates),
                )
            except Exception as exc:
                logger.warning(
                    "MinuteIndexer [%s]: 缓存更新失败 - %s",
                    source_name, exc,
                )

        # --- 更新进度 ---
        with self._lock:
            self._source_progress[source_name] = max_updated_at

        logger.info(
            "MinuteIndexer [%s]: 索引完成 (records=%d, indexed=%d, "
            "version=%s)",
            source_name, len(changed_records), indexed_count, version,
        )

        return indexed_count

    # ------------------------------------------------------------------
    # 向量化
    # ------------------------------------------------------------------

    def _encode_texts(self, texts: List[str]) -> List[Optional[Vector]]:
        """向量化文本列表

        使用优先级：
        1. 自定义 embedder（如果提供）
        2. sync_pipeline 的 embedder（如果已初始化）
        3. 降级：返回 None（不编码）

        Args:
            texts: 文本列表

        Returns:
            向量列表，编码失败的为 None
        """
        if not texts:
            return []

        # 尝试使用自定义 embedder
        if self._embedder is not None:
            try:
                vectors = self._embedder.encode(texts)
                if vectors is not None and len(vectors) == len(texts):
                    return vectors
            except Exception as exc:
                logger.warning("MinuteIndexer: 自定义编码失败 - %s", exc)

        # 尝试使用 sync_pipeline 的 embedder
        if (
            hasattr(self._sync_pipeline, "_embedder")
            and self._sync_pipeline._embedder is not None
        ):
            try:
                vectors = self._sync_pipeline._embedder.encode(texts)
                if vectors is not None and len(vectors) == len(texts):
                    return vectors
            except Exception as exc:
                logger.warning(
                    "MinuteIndexer: sync_pipeline 编码失败 - %s", exc
                )

        # 降级：返回 None
        logger.warning(
            "MinuteIndexer: 无可用编码器，返回 None 向量"
        )
        return [None] * len(texts)


__all__ = [
    "InMemoryIndex",
    "MinuteIndexer",
    "IndexEntry",
    "IndexerStatus",
    "DEFAULT_CHECK_INTERVAL",
    "DEFAULT_EMBEDDING_DIM",
]
