"""
链客宝 - 实时增量同步管道（轮询+变更检测+自动重编码）
========================================================

核心职责：
1. 轮询 business_cards 表的 updated_at 字段，检测增量变更
2. 拉取变更记录 → BGE-M3 重新编码 → 更新向量缓存 → 更新检索索引
3. 延迟监控与阈值告警

设计原则：
- 单步独立 try/except，单步失败不影响后续
- 状态持久化到 sync_status.json
- 守护线程模式，不阻塞主进程退出

Usage:
    from ml.pipelines import RealtimeSyncPipeline

    pipeline = RealtimeSyncPipeline(check_interval=60)
    pipeline.add_source("business_cards", db_path="chainke.db")
    pipeline.start()
    # ... 运行中 ...
    print(pipeline.status())
    pipeline.stop()

Author: 胜遇 (P6, 运营部, 管道编排/消息队列)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 默认轮询间隔（秒）
DEFAULT_CHECK_INTERVAL = 60

# 默认延迟告警阈值（秒）
DEFAULT_LATENCY_THRESHOLD = 300

# 状态文件路径
DEFAULT_STATUS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "sync_status.json",
)

# business_cards 默认字段
DEFAULT_TABLE = "business_cards"
DEFAULT_ID_FIELD = "id"
DEFAULT_UPDATED_AT_FIELD = "updated_at"
DEFAULT_FIELDS_FIELD = "fields"
DEFAULT_BATCH_SIZE = 32


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class DataSourceConfig:
    """数据源配置"""

    name: str
    db_path: str
    table: str = DEFAULT_TABLE
    id_field: str = DEFAULT_ID_FIELD
    updated_at_field: str = DEFAULT_UPDATED_AT_FIELD
    fields_field: str = DEFAULT_FIELDS_FIELD
    where_clause: str = ""


@dataclass
class SourceSyncStatus:
    """单个数据源的同步状态"""

    name: str
    last_check_time: Optional[str] = None      # ISO 格式
    last_max_updated_at: Optional[str] = None   # 上次检查到的最大 updated_at
    last_sync_time: Optional[str] = None        # 最近一次实际同步时间
    last_latency_seconds: float = 0.0           # 最近一次同步延迟（秒）
    max_latency_seconds: float = 0.0            # 历史最大延迟
    total_syncs: int = 0
    total_records_synced: int = 0
    total_errors: int = 0
    last_error: Optional[str] = None
    is_running: bool = False
    last_alert_time: Optional[str] = None       # 最近一次告警时间


@dataclass
class SyncStatus:
    """管道整体同步状态"""

    sources: Dict[str, SourceSyncStatus] = field(default_factory=dict)
    pipeline_running: bool = False
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    check_interval: int = DEFAULT_CHECK_INTERVAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_running": self.pipeline_running,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "check_interval": self.check_interval,
            "sources": {
                name: asdict(status)
                for name, status in self.sources.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SyncStatus:
        status = cls(
            pipeline_running=data.get("pipeline_running", False),
            started_at=data.get("started_at"),
            stopped_at=data.get("stopped_at"),
            check_interval=data.get("check_interval", DEFAULT_CHECK_INTERVAL),
        )
        for name, src_data in data.get("sources", {}).items():
            status.sources[name] = SourceSyncStatus(
                name=name,
                last_check_time=src_data.get("last_check_time"),
                last_max_updated_at=src_data.get("last_max_updated_at"),
                last_sync_time=src_data.get("last_sync_time"),
                last_latency_seconds=src_data.get("last_latency_seconds", 0.0),
                max_latency_seconds=src_data.get("max_latency_seconds", 0.0),
                total_syncs=src_data.get("total_syncs", 0),
                total_records_synced=src_data.get("total_records_synced", 0),
                total_errors=src_data.get("total_errors", 0),
                last_error=src_data.get("last_error"),
                is_running=src_data.get("is_running", False),
                last_alert_time=src_data.get("last_alert_time"),
            )
        return status


# ---------------------------------------------------------------------------
# 变更事件
# ---------------------------------------------------------------------------


@dataclass
class ChangeEvent:
    """单条变更记录"""

    record_id: str
    fields_json: str           # fields 字段的原始 JSON 字符串
    updated_at: str            # ISO 格式时间戳
    source_name: str = ""


# ---------------------------------------------------------------------------
# 实时增量同步管道
# ---------------------------------------------------------------------------


class RealtimeSyncPipeline:
    """实时增量同步管道

    通过轮询 business_cards 表的 updated_at 字段检测增量变更，
    拉取变更记录后依次执行：BGE-M3 重新编码 → 更新向量缓存 → 更新检索索引。

    每步独立 try/except，单步失败不影响后续。

    Usage:
        pipeline = RealtimeSyncPipeline(check_interval=60)
        pipeline.add_source("business_cards", db_path="chainke.db")
        pipeline.start()
        print(pipeline.status())
        pipeline.stop()
    """

    def __init__(
        self,
        data_sources: Optional[List[DataSourceConfig]] = None,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
        latency_threshold: int = DEFAULT_LATENCY_THRESHOLD,
        status_file: Optional[str] = None,
        embedder_class: Any = None,
        cache_class: Any = None,
        on_alert: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        """初始化实时增量同步管道

        Args:
            data_sources: 初始数据源列表
            check_interval: 轮询间隔（秒），默认 60
            latency_threshold: 延迟告警阈值（秒），默认 300
            status_file: 状态持久化文件路径
            embedder_class: BGE-M3 嵌入器类（延迟导入）
            cache_class: 向量缓存类（延迟导入）
            on_alert: 告警回调函数，接收 (source_name, latency_seconds)
        """
        self._check_interval = max(5, check_interval)
        self._latency_threshold = max(10, latency_threshold)
        self._status_file = status_file or DEFAULT_STATUS_FILE
        self._on_alert = on_alert

        # 数据源配置
        self._data_sources: Dict[str, DataSourceConfig] = {}
        if data_sources:
            for ds in data_sources:
                self._data_sources[ds.name] = ds

        # 嵌入器和缓存（延迟导入）
        self._embedder_class = embedder_class
        self._cache_class = cache_class
        self._embedder: Any = None
        self._cache: Any = None
        self._initialized_ml: bool = False

        # 线程控制
        self._running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 状态管理
        self._status = SyncStatus(
            check_interval=self._check_interval,
        )
        self._load_status()

        logger.info(
            "RealtimeSyncPipeline: 初始化完成 (check_interval=%ss, "
            "latency_threshold=%ss, sources=%d)",
            self._check_interval,
            self._latency_threshold,
            len(self._data_sources),
        )

    # ------------------------------------------------------------------
    # 数据源管理
    # ------------------------------------------------------------------

    def add_source(
        self,
        name: str,
        db_path: str,
        table: str = DEFAULT_TABLE,
        id_field: str = DEFAULT_ID_FIELD,
        updated_at_field: str = DEFAULT_UPDATED_AT_FIELD,
        fields_field: str = DEFAULT_FIELDS_FIELD,
        where_clause: str = "",
    ) -> None:
        """添加数据源

        Args:
            name: 数据源唯一名称
            db_path: SQLite 数据库路径
            table: 表名，默认 business_cards
            id_field: ID 字段名
            updated_at_field: 更新时间字段名
            fields_field: 字段 JSON 字段名
            where_clause: 额外的 WHERE 条件（不包含 WHERE 关键字）
        """
        config = DataSourceConfig(
            name=name,
            db_path=db_path,
            table=table,
            id_field=id_field,
            updated_at_field=updated_at_field,
            fields_field=fields_field,
            where_clause=where_clause,
        )
        with self._lock:
            self._data_sources[name] = config
            if name not in self._status.sources:
                self._status.sources[name] = SourceSyncStatus(name=name)
            self._save_status()

        logger.info("RealtimeSyncPipeline: 添加数据源 %r (db=%s, table=%s)", name, db_path, table)

    def remove_source(self, name: str) -> bool:
        """移除数据源

        Returns:
            True 如果存在并移除
        """
        with self._lock:
            if name not in self._data_sources:
                return False
            del self._data_sources[name]
            self._status.sources.pop(name, None)
            self._save_status()
        logger.info("RealtimeSyncPipeline: 移除数据源 %r", name)
        return True

    def list_sources(self) -> List[str]:
        """列出所有数据源名称"""
        with self._lock:
            return list(self._data_sources.keys())

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台同步线程

        如果管道已在运行，则忽略此调用。
        """
        if self._running:
            logger.warning("RealtimeSyncPipeline: 已在运行中，忽略重复 start()")
            return

        if not self._data_sources:
            logger.warning("RealtimeSyncPipeline: 无数据源，无法启动")
            return

        self._running = True
        self._stop_event.clear()

        # 延迟初始化 ML 组件
        self._lazy_init_ml()

        # 启动后台线程
        self._thread = threading.Thread(
            target=self._run_loop,
            name="RealtimeSyncPipeline",
            daemon=True,
        )
        self._thread.start()

        with self._lock:
            self._status.pipeline_running = True
            self._status.started_at = datetime.now(timezone.utc).isoformat()
            self._save_status()

        logger.info(
            "RealtimeSyncPipeline: 已启动 (check_interval=%ss, sources=%d)",
            self._check_interval,
            len(self._data_sources),
        )

    def stop(self, timeout: float = 10.0) -> None:
        """停止后台同步线程

        Args:
            timeout: 等待线程结束的超时秒数
        """
        if not self._running:
            logger.warning("RealtimeSyncPipeline: 未在运行，忽略 stop()")
            return

        self._stop_event.set()
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "RealtimeSyncPipeline: 线程未在 %ss 内结束", timeout
                )

        self._thread = None

        with self._lock:
            self._status.pipeline_running = False
            self._status.stopped_at = datetime.now(timezone.utc).isoformat()
            for src_status in self._status.sources.values():
                src_status.is_running = False
            self._save_status()

        logger.info("RealtimeSyncPipeline: 已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """返回管道当前状态字典

        Returns:
            {
                "pipeline_running": bool,
                "started_at": str | None,
                "stopped_at": str | None,
                "check_interval": int,
                "sources": {
                    "<source_name>": {
                        "name": str,
                        "last_check_time": str | None,
                        "last_max_updated_at": str | None,
                        "last_sync_time": str | None,
                        "last_latency_seconds": float,
                        "max_latency_seconds": float,
                        "total_syncs": int,
                        "total_records_synced": int,
                        "total_errors": int,
                        "last_error": str | None,
                        "is_running": bool,
                        "last_alert_time": str | None,
                    },
                    ...
                }
            }
        """
        with self._lock:
            return self._status.to_dict()

    def get_source_status(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定数据源的状态"""
        with self._lock:
            src_status = self._status.sources.get(name)
            if src_status is None:
                return None
            return asdict(src_status)

    # ------------------------------------------------------------------
    # 延迟初始化
    # ------------------------------------------------------------------

    def _lazy_init_ml(self) -> None:
        """延迟导入并初始化 BGE-M3 嵌入器和向量缓存"""
        if self._initialized_ml:
            return

        try:
            if self._embedder_class is None:
                from features.embedding_service import BgeM3Embedding
                self._embedder_class = BgeM3Embedding

            if self._cache_class is None:
                from features.embedding_cache import EmbeddingCache
                self._cache_class = EmbeddingCache

            # 创建嵌入器（force_fallback 避免下载模型）
            self._embedder = self._embedder_class(force_fallback=True)

            # 创建缓存
            self._cache = self._cache_class()

            # 预热
            if hasattr(self._embedder, "load_model"):
                self._embedder.load_model()
            if hasattr(self._embedder, "warmup"):
                self._embedder.warmup()

            self._initialized_ml = True
            logger.info("RealtimeSyncPipeline: ML 组件初始化完成")

        except Exception as exc:
            logger.warning(
                "RealtimeSyncPipeline: ML 组件初始化失败 - %s（将使用降级模式）",
                exc,
            )
            self._initialized_ml = False

    # ------------------------------------------------------------------
    # 状态持久化
    # ------------------------------------------------------------------

    def _load_status(self) -> None:
        """从 JSON 文件加载持久化状态"""
        if not os.path.exists(self._status_file):
            logger.debug("RealtimeSyncPipeline: 无持久化状态文件，使用默认状态")
            return

        try:
            with open(self._status_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._status = SyncStatus.from_dict(data)
            logger.info("RealtimeSyncPipeline: 已加载持久化状态")
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("RealtimeSyncPipeline: 加载状态文件失败 - %s", exc)

    def _save_status(self) -> None:
        """保存状态到 JSON 文件"""
        try:
            os.makedirs(os.path.dirname(self._status_file), exist_ok=True)
            with open(self._status_file, "w", encoding="utf-8") as f:
                json.dump(self._status.to_dict(), f, ensure_ascii=False, indent=2)
        except IOError as exc:
            logger.error("RealtimeSyncPipeline: 保存状态失败 - %s", exc)

    # ------------------------------------------------------------------
    # 主同步循环
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """主同步循环（在后台线程中运行）"""
        logger.debug("RealtimeSyncPipeline: 同步循环已启动")

        while not self._stop_event.is_set():
            # 获取当前数据源快照
            sources_snapshot: List[DataSourceConfig] = []
            with self._lock:
                sources_snapshot = list(self._data_sources.values())

            # 逐个检查数据源
            for config in sources_snapshot:
                if self._stop_event.is_set():
                    break

                try:
                    self._check_and_sync(config)
                except Exception as exc:
                    logger.error(
                        "RealtimeSyncPipeline: 数据源 %r 检查异常 - %s",
                        config.name, exc,
                    )
                    with self._lock:
                        src_status = self._status.sources.get(config.name)
                        if src_status:
                            src_status.total_errors += 1
                            src_status.last_error = f"{type(exc).__name__}: {exc}"
                            self._save_status()

            # 等待下一次轮询
            self._stop_event.wait(timeout=self._check_interval)

        logger.debug("RealtimeSyncPipeline: 同步循环已退出")

    def _check_and_sync(self, config: DataSourceConfig) -> None:
        """检查数据源变更并执行同步

        流程：
        1. 查询 max(updated_at) 检测是否有新变更
        2. 如果 last_max_updated_at 为 None（首次），初始化并跳过
        3. 如果 updated_at > last_max_updated_at，增量拉取
        4. 提取变更记录 → BGE-M3 重新编码 → 更新向量缓存 → 更新检索索引
        5. 每步独立 try/except
        """
        source_name = config.name

        # --- 第一步：检测变更 ---
        try:
            max_updated_at = self._query_max_updated_at(config)
        except Exception as exc:
            logger.error(
                "RealtimeSyncPipeline [%s]: 查询 max(updated_at) 失败 - %s",
                source_name, exc,
            )
            self._record_error(source_name, f"query_max_updated_at: {exc}")
            return

        if max_updated_at is None:
            # 表无数据，跳过
            return

        # 获取上次检查的最大 updated_at
        with self._lock:
            src_status = self._status.sources.get(source_name)
            if src_status is None:
                src_status = SourceSyncStatus(name=source_name)
                self._status.sources[source_name] = src_status

            last_max = src_status.last_max_updated_at

            # 更新检查时间
            src_status.last_check_time = datetime.now(timezone.utc).isoformat()
            self._save_status()

        # 首次检查：记录当前最大值，不触发同步
        if last_max is None:
            with self._lock:
                src_status = self._status.sources.get(source_name)
                if src_status:
                    src_status.last_max_updated_at = max_updated_at
                    self._save_status()
            logger.info(
                "RealtimeSyncPipeline [%s]: 首次检查初始化 (max_updated_at=%s)",
                source_name, max_updated_at,
            )
            return

        # 无新变更
        if max_updated_at <= last_max:
            logger.debug(
                "RealtimeSyncPipeline [%s]: 无新变更 (last=%s, current=%s)",
                source_name, last_max, max_updated_at,
            )
            return

        # --- 第二步：增量拉取 ---
        logger.info(
            "RealtimeSyncPipeline [%s]: 检测到新变更 (last=%s, current=%s)",
            source_name, last_max, max_updated_at,
        )

        try:
            changed_records = self._pull_incremental(config, last_max)
        except Exception as exc:
            logger.error(
                "RealtimeSyncPipeline [%s]: 增量拉取失败 - %s",
                source_name, exc,
            )
            self._record_error(source_name, f"pull_incremental: {exc}")
            return

        if not changed_records:
            # 有 updated_at 变更但无记录匹配（边界情况），仍更新标记
            with self._lock:
                src_status = self._status.sources.get(source_name)
                if src_status:
                    src_status.last_max_updated_at = max_updated_at
                    self._save_status()
            return

        sync_start = time.perf_counter()
        records_processed = 0
        records_failed = 0

        # 标记同步进行中
        with self._lock:
            src_status = self._status.sources.get(source_name)
            if src_status:
                src_status.is_running = True
                self._save_status()

        # --- 第三步：BGE-M3 重新编码 ---
        encoded_vectors: List[Optional[List[float]]] = []
        if self._initialized_ml and self._embedder is not None:
            try:
                texts = [rec.fields_json for rec in changed_records]
                vectors = self._embedder.encode(texts)
                if vectors is not None and len(vectors) == len(texts):
                    encoded_vectors = vectors
                else:
                    logger.warning(
                        "RealtimeSyncPipeline [%s]: 编码结果长度不匹配",
                        source_name,
                    )
                    encoded_vectors = [None] * len(changed_records)
            except Exception as exc:
                logger.error(
                    "RealtimeSyncPipeline [%s]: BGE-M3 编码失败 - %s",
                    source_name, exc,
                )
                encoded_vectors = [None] * len(changed_records)
                self._record_error(source_name, f"encode: {exc}")
        else:
            # ML 组件未初始化，跳过编码
            encoded_vectors = [None] * len(changed_records)
            logger.warning(
                "RealtimeSyncPipeline [%s]: ML 组件未就绪，跳过编码",
                source_name,
            )

        # --- 第四步：更新向量缓存 ---
        if self._initialized_ml and self._cache is not None and encoded_vectors:
            try:
                cache_updates = []
                for record, vec in zip(changed_records, encoded_vectors):
                    if vec is not None:
                        cache_updates.append((record.fields_json, vec))

                if cache_updates:
                    self._cache.batch_set(cache_updates)
                    records_processed += len(cache_updates)
                    logger.info(
                        "RealtimeSyncPipeline [%s]: 向量缓存更新 %d 条",
                        source_name, len(cache_updates),
                    )
            except Exception as exc:
                logger.error(
                    "RealtimeSyncPipeline [%s]: 更新向量缓存失败 - %s",
                    source_name, exc,
                )
                self._record_error(source_name, f"cache_update: {exc}")

        # --- 第五步：更新检索索引 ---
        try:
            self._update_retrieval_index(source_name, changed_records, encoded_vectors)
        except Exception as exc:
            logger.error(
                "RealtimeSyncPipeline [%s]: 更新检索索引失败 - %s",
                source_name, exc,
            )
            self._record_error(source_name, f"index_update: {exc}")

        # 计算延迟
        sync_elapsed = time.perf_counter() - sync_start
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            src_status = self._status.sources.get(source_name)
            if src_status:
                src_status.last_max_updated_at = max_updated_at
                src_status.last_sync_time = now_iso
                src_status.last_latency_seconds = round(sync_elapsed, 3)
                if sync_elapsed > src_status.max_latency_seconds:
                    src_status.max_latency_seconds = round(sync_elapsed, 3)
                src_status.total_syncs += 1
                src_status.total_records_synced += records_processed
                src_status.is_running = False
                self._save_status()

        logger.info(
            "RealtimeSyncPipeline [%s]: 同步完成 (records=%d, processed=%d, "
            "latency=%.2fs)",
            source_name, len(changed_records), records_processed, sync_elapsed,
        )

        # --- 延迟监控告警 ---
        if sync_elapsed > self._latency_threshold:
            self._trigger_alert(source_name, sync_elapsed)

    # ------------------------------------------------------------------
    # 数据访问
    # ------------------------------------------------------------------

    def _query_max_updated_at(self, config: DataSourceConfig) -> Optional[str]:
        """查询数据源的最大 updated_at 值

        Returns:
            ISO 格式时间戳字符串，无数据返回 None
        """
        import sqlite3

        sql = f"SELECT MAX({config.updated_at_field}) as max_ts FROM {config.table}"
        if config.where_clause:
            sql += f" WHERE {config.where_clause}"

        conn = sqlite3.connect(config.db_path, timeout=10)
        try:
            row = conn.execute(sql).fetchone()
            return row[0] if row and row[0] else None
        finally:
            conn.close()

    def _pull_incremental(
        self,
        config: DataSourceConfig,
        since_updated_at: str,
    ) -> List[ChangeEvent]:
        """增量拉取变更记录

        Args:
            config: 数据源配置
            since_updated_at: 起始时间戳

        Returns:
            变更事件列表
        """
        import sqlite3

        sql = (
            f"SELECT {config.id_field}, {config.fields_field}, {config.updated_at_field} "
            f"FROM {config.table} "
            f"WHERE {config.updated_at_field} > ?"
        )
        if config.where_clause:
            sql += f" AND {config.where_clause}"
        sql += f" ORDER BY {config.updated_at_field} ASC"

        conn = sqlite3.connect(config.db_path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (since_updated_at,)).fetchall()

            events: List[ChangeEvent] = []
            for row in rows:
                raw_fields = row[config.fields_field]
                if isinstance(raw_fields, str):
                    fields_json = raw_fields
                else:
                    fields_json = json.dumps(raw_fields, ensure_ascii=False)

                events.append(ChangeEvent(
                    record_id=str(row[config.id_field]),
                    fields_json=fields_json,
                    updated_at=str(row[config.updated_at_field]),
                    source_name=config.name,
                ))

            return events
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 检索索引更新
    # ------------------------------------------------------------------

    def _update_retrieval_index(
        self,
        source_name: str,
        records: List[ChangeEvent],
        vectors: List[Optional[List[float]]],
    ) -> None:
        """更新检索索引

        目前是桩实现，子类或外部可覆盖此方法实现自定义索引更新逻辑。
        默认仅记录日志。

        Args:
            source_name: 数据源名称
            records: 变更记录列表
            vectors: 对应的向量列表（None 表示编码失败）
        """
        # 默认实现：记录日志 + 统计成功/失败
        valid_count = sum(1 for v in vectors if v is not None)
        failed_count = len(vectors) - valid_count

        if valid_count > 0:
            logger.debug(
                "RealtimeSyncPipeline [%s]: 检索索引更新 %d 条 (成功=%d, 失败=%d)",
                source_name, len(records), valid_count, failed_count,
            )
        else:
            logger.debug(
                "RealtimeSyncPipeline [%s]: 检索索引无有效向量更新",
                source_name,
            )

    # ------------------------------------------------------------------
    # 错误记录与告警
    # ------------------------------------------------------------------

    def _record_error(self, source_name: str, error_msg: str) -> None:
        """记录错误到状态"""
        with self._lock:
            src_status = self._status.sources.get(source_name)
            if src_status:
                src_status.total_errors += 1
                src_status.last_error = error_msg
                src_status.is_running = False
                self._save_status()

    def _trigger_alert(self, source_name: str, latency_seconds: float) -> None:
        """触发延迟告警

        Args:
            source_name: 数据源名称
            latency_seconds: 实际延迟秒数
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            src_status = self._status.sources.get(source_name)
            if src_status:
                src_status.last_alert_time = now_iso
                self._save_status()

        logger.warning(
            "RealtimeSyncPipeline [%s]: 延迟告警 - %.2fs (阈值=%ss)",
            source_name, latency_seconds, self._latency_threshold,
        )

        # 调用外部告警回调
        if self._on_alert is not None:
            try:
                self._on_alert(source_name, latency_seconds)
            except Exception as exc:
                logger.warning(
                    "RealtimeSyncPipeline: 告警回调异常 - %s", exc,
                )

    # ------------------------------------------------------------------
    # 手动触发同步
    # ------------------------------------------------------------------

    def trigger_sync(self, source_name: Optional[str] = None) -> Dict[str, Any]:
        """手动触发立即同步

        Args:
            source_name: 指定数据源名称，None 表示所有数据源

        Returns:
            同步结果字典 {"sources": {name: "triggered" | "not_found" | "skipped"}}
        """
        if not self._running:
            return {"error": "管道未运行", "sources": {}}

        result: Dict[str, str] = {}
        sources_to_sync: List[DataSourceConfig] = []

        with self._lock:
            if source_name:
                config = self._data_sources.get(source_name)
                if config:
                    sources_to_sync.append(config)
                    result[source_name] = "triggered"
                else:
                    result[source_name] = "not_found"
            else:
                for config in self._data_sources.values():
                    sources_to_sync.append(config)
                    result[config.name] = "triggered"

        # 在线程中执行同步（不阻塞调用者）
        for config in sources_to_sync:
            thread = threading.Thread(
                target=self._check_and_sync,
                args=(config,),
                daemon=True,
            )
            thread.start()

        return {"sources": result}


__all__ = [
    "RealtimeSyncPipeline",
    "SyncStatus",
    "SourceSyncStatus",
    "DataSourceConfig",
    "ChangeEvent",
    "DEFAULT_CHECK_INTERVAL",
    "DEFAULT_LATENCY_THRESHOLD",
]
