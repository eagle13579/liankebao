"""
链客宝 - 预计算嵌入调度器 + 断点续传 + 版本管理
=================================================

核心功能:
1. EmbedScheduler — 离线嵌入批处理调度器
   - 全量刷新 (schedule_full_refresh)
   - 增量更新 (schedule_incremental)
   - 断点续传 (resume)
   - 进度查询 (status)

2. 三种数据源:
   a. SQLite 表 (business_cards)
   b. JSONL 文件
   c. CSV 文件

3. 版本管理:
   - 每次全量刷新生成 v1, v2, ...
   - 元数据: version/date/embedding_model/record_count/md5
   - 查询时使用最新版本

Author: 银珠 (P6, 情报部, 缓存策略/检索)
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Sequence, Tuple, Type, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_CHECKPOINT_DIR = os.path.join(str(Path.home()), ".cache", "chainke", "scheduler_checkpoints")
DEFAULT_VERSION_DB = os.path.join(str(Path.home()), ".cache", "chainke", "version_metadata.db")
DEFAULT_BATCH_SIZE = 32
DEFAULT_STREAM_BATCH_SIZE = 100

# 版本表结构
VERSION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS embedding_versions (
    version      TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    data_source  TEXT NOT NULL,
    text_field   TEXT NOT NULL,
    md5_checksum TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'completed',
    metadata     TEXT NOT NULL DEFAULT '{}'
)
"""


# ---------------------------------------------------------------------------
# 版本管理器
# ---------------------------------------------------------------------------

class VersionManager:
    """
    嵌入版本管理器。

    每次全量刷新生成一个新版本号 (v1, v2, ...)，
    记录版本元数据到 SQLite 数据库，
    查询时使用最新版本。

    线程安全。
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Args:
            db_path: 版本元数据库路径，默认 ~/.cache/chainke/version_metadata.db
        """
        self._db_path = db_path or DEFAULT_VERSION_DB
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """初始化版本表"""
        with self._get_conn() as conn:
            conn.execute(VERSION_TABLE_DDL)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # 版本生成
    # ------------------------------------------------------------------

    def next_version(self) -> str:
        """
        生成下一个版本号。

        Returns:
            "v1", "v2", ... 格式的版本号
        """
        with self._lock:
            existing = self.list_versions()
            if not existing:
                return "v1"
            # 提取最大数字
            nums = []
            for v in existing:
                try:
                    nums.append(int(v.lstrip("v")))
                except ValueError:
                    continue
            next_num = max(nums) + 1 if nums else 1
            return f"v{next_num}"

    def register_version(
        self,
        version: str,
        embedding_model: str,
        record_count: int,
        data_source: str,
        text_field: str,
        md5_checksum: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        注册一个新版本。

        Args:
            version: 版本号 (如 "v1")
            embedding_model: 嵌入模型名称
            record_count: 记录数
            data_source: 数据源描述
            text_field: 文本字段名
            md5_checksum: 数据 MD5 校验
            metadata: 额外元数据
        """
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO embedding_versions
                       (version, created_at, embedding_model, record_count,
                        data_source, text_field, md5_checksum, status, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)""",
                    (version, now, embedding_model, record_count,
                     data_source, text_field, md5_checksum, meta_json),
                )
                conn.commit()

    def mark_version_failed(self, version: str, error_info: str = "") -> None:
        """标记版本为失败状态"""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE embedding_versions SET status='failed', metadata=? WHERE version=?",
                    (json.dumps({"error": error_info}, ensure_ascii=False), version),
                )
                conn.commit()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_latest_version(self) -> Optional[Dict[str, Any]]:
        """
        获取最新（按创建时间）的已完成版本。

        Returns:
            版本元数据字典，无可用版本返回 None
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM embedding_versions WHERE status='completed' "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def get_version(self, version: str) -> Optional[Dict[str, Any]]:
        """获取指定版本的元数据"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM embedding_versions WHERE version=?",
                (version,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def list_versions(self) -> List[str]:
        """列出所有版本号（按创建时间降序）"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT version FROM embedding_versions ORDER BY created_at DESC"
            ).fetchall()
            return [r["version"] for r in rows]

    def list_version_metadata(self) -> List[Dict[str, Any]]:
        """列出所有版本的完整元数据"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM embedding_versions ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_version(self, version: str) -> bool:
        """删除指定版本"""
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute("DELETE FROM embedding_versions WHERE version=?", (version,))
                conn.commit()
                return cur.rowcount > 0

    def stats(self) -> Dict[str, Any]:
        """版本统计"""
        versions = self.list_version_metadata()
        return {
            "total_versions": len(versions),
            "latest_version": versions[0] if versions else None,
            "versions": versions,
        }


# ---------------------------------------------------------------------------
# 检查点管理器 (断点续传)
# ---------------------------------------------------------------------------

class CheckpointManager:
    """
    检查点管理器，记录已处理的数据 ID 以支持断点续传。

    每个调度任务一个 JSON 检查点文件，包含:
    - processed_ids: 已成功处理的 ID 集合
    - failed_ids: 处理失败的 ID 集合
    - last_updated: 最后更新时间
    - total_count: 总记录数
    - processed_count: 已处理数
    """

    def __init__(self, checkpoint_dir: Optional[str] = None) -> None:
        """
        Args:
            checkpoint_dir: 检查点文件目录
        """
        self._checkpoint_dir = checkpoint_dir or DEFAULT_CHECKPOINT_DIR
        os.makedirs(self._checkpoint_dir, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 路径管理
    # ------------------------------------------------------------------

    def _checkpoint_path(self, task_id: str) -> str:
        """检查点文件路径"""
        safe_name = task_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
        return os.path.join(self._checkpoint_dir, f"{safe_name}.checkpoint.json")

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------

    def load(self, task_id: str) -> Dict[str, Any]:
        """
        加载检查点。

        Args:
            task_id: 任务唯一标识

        Returns:
            检查点字典:
            - processed_ids: List[str] 已处理的 ID
            - failed_ids: List[str] 失败的 ID
            - total_count: int 总记录数
            - processed_count: int 已处理数
            - last_updated: str ISO 时间
        """
        path = self._checkpoint_path(task_id)
        if not os.path.exists(path):
            return {
                "processed_ids": [],
                "failed_ids": [],
                "total_count": 0,
                "processed_count": 0,
                "last_updated": "",
            }
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 确保所有字段存在
            data.setdefault("processed_ids", [])
            data.setdefault("failed_ids", [])
            data.setdefault("total_count", 0)
            data.setdefault("processed_count", 0)
            data.setdefault("last_updated", "")
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("[Checkpoint] 加载检查点失败: %s, 重置", e)
            return {
                "processed_ids": [],
                "failed_ids": [],
                "total_count": 0,
                "processed_count": 0,
                "last_updated": "",
            }

    def save(self, task_id: str, checkpoint: Dict[str, Any]) -> None:
        """
        保存检查点。

        Args:
            task_id: 任务唯一标识
            checkpoint: 检查点字典
        """
        checkpoint["last_updated"] = datetime.now(timezone.utc).isoformat()
        checkpoint["processed_count"] = len(checkpoint.get("processed_ids", []))
        path = self._checkpoint_path(task_id)
        with self._lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False, indent=2)
            except OSError as e:
                logger.error("[Checkpoint] 保存检查点失败: %s", e)

    def mark_processed(self, task_id: str, ids: List[str]) -> None:
        """标记一批 ID 为已处理"""
        checkpoint = self.load(task_id)
        processed_set = set(checkpoint.get("processed_ids", []))
        for pid in ids:
            processed_set.add(str(pid))
        checkpoint["processed_ids"] = sorted(processed_set)
        self.save(task_id, checkpoint)

    def mark_failed(self, task_id: str, ids: List[str]) -> None:
        """标记一批 ID 为处理失败"""
        checkpoint = self.load(task_id)
        failed_set = set(checkpoint.get("failed_ids", []))
        failed_set.update(str(pid) for pid in ids)
        checkpoint["failed_ids"] = sorted(failed_set)
        self.save(task_id, checkpoint)

    def get_unprocessed_ids(self, task_id: str, all_ids: List[str]) -> List[str]:
        """
        获取尚未处理的 ID 列表（用于断点续传）。

        Args:
            task_id: 任务唯一标识
            all_ids: 所有 ID 列表

        Returns:
            未处理的 ID 列表
        """
        checkpoint = self.load(task_id)
        processed_set = set(checkpoint.get("processed_ids", []))
        failed_set = set(checkpoint.get("failed_ids", []))
        # 已处理或已失败的都跳过
        skipped = processed_set | failed_set
        return [pid for pid in all_ids if str(pid) not in skipped]

    def reset(self, task_id: str) -> None:
        """重置检查点"""
        path = self._checkpoint_path(task_id)
        with self._lock:
            try:
                if os.path.exists(path):
                    os.remove(path)
                logger.info("[Checkpoint] 已重置: %s", task_id)
            except OSError as e:
                logger.warning("[Checkpoint] 重置失败: %s", e)

    def list_checkpoints(self) -> List[str]:
        """列出所有检查点任务 ID"""
        checkpoints = []
        if not os.path.isdir(self._checkpoint_dir):
            return []
        for fname in os.listdir(self._checkpoint_dir):
            if fname.endswith(".checkpoint.json"):
                task_id = fname.replace(".checkpoint.json", "")
                checkpoints.append(task_id)
        return sorted(checkpoints)


# ---------------------------------------------------------------------------
# 数据源抽象
# ---------------------------------------------------------------------------

class DataSource:
    """数据源基类"""

    def __init__(self, text_field: str, id_field: str = "id", **kwargs: Any) -> None:
        self.text_field = text_field
        self.id_field = id_field

    def get_total_count(self) -> int:
        """获取数据总量"""
        raise NotImplementedError

    def iter_records(self, batch_size: int = DEFAULT_STREAM_BATCH_SIZE) -> Generator[List[Tuple[str, str]], None, None]:
        """
        分批迭代 (id, text) 元组。

        Args:
            batch_size: 每批大小

        Yields:
            List[(id, text)] 批次
        """
        raise NotImplementedError

    def get_all_ids(self) -> List[str]:
        """获取所有数据 ID"""
        raise NotImplementedError

    def get_description(self) -> str:
        """获取数据源描述"""
        raise NotImplementedError

    def compute_md5(self) -> str:
        """计算数据 MD5 校验和"""
        raise NotImplementedError


class SQliteDataSource(DataSource):
    """
    SQLite 表数据源。

    从 business_cards 表（或自定义表）中提取文本字段进行嵌入。
    fields 是 JSON 字段，从中提取用户配置的描述文本。
    """

    def __init__(
        self,
        db_path: str,
        table: str = "business_cards",
        text_field: str = "fields",
        id_field: str = "id",
        where_clause: str = "",
        text_extractor: Optional[Callable[[Dict[str, Any]], str]] = None,
    ) -> None:
        """
        Args:
            db_path: SQLite 数据库路径
            table: 表名
            text_field: 文本字段名（对于 JSON 字段，用 text_extractor 提取）
            id_field: ID 字段名
            where_clause: 可选的 WHERE 条件（不含 WHERE 关键字）
            text_extractor: 从字段值提取文本的函数。
                           默认将 fields JSON 转为字符串描述。
        """
        super().__init__(text_field=text_field, id_field=id_field)
        self._db_path = db_path
        self._table = table
        self._where_clause = where_clause.strip()
        self._text_extractor = text_extractor or self._default_extractor

    @staticmethod
    def _default_extractor(fields_value: Any) -> str:
        """从 business_cards.fields JSON 提取文本描述"""
        if isinstance(fields_value, dict):
            # 拼接所有字符串字段值
            parts = []
            for k, v in fields_value.items():
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())
                elif isinstance(v, (int, float)):
                    parts.append(str(v))
            return "，".join(parts) if parts else json.dumps(fields_value, ensure_ascii=False)
        if isinstance(fields_value, str):
            return fields_value
        return str(fields_value) if fields_value is not None else ""

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.row_factory = sqlite3.Row
        return conn

    def get_total_count(self) -> int:
        sql = f"SELECT COUNT(*) as cnt FROM {self._table}"
        if self._where_clause:
            sql += f" WHERE {self._where_clause}"
        with self._get_conn() as conn:
            row = conn.execute(sql).fetchone()
            return row["cnt"] if row else 0

    def iter_records(
        self, batch_size: int = DEFAULT_STREAM_BATCH_SIZE
    ) -> Generator[List[Tuple[str, str]], None, None]:
        sql = f"SELECT {self.id_field}, {self.text_field} FROM {self._table}"
        if self._where_clause:
            sql += f" WHERE {self._where_clause}"
        sql += " ORDER BY rowid"
        offset = 0
        with self._get_conn() as conn:
            while True:
                batch_sql = f"{sql} LIMIT {batch_size} OFFSET {offset}"
                rows = conn.execute(batch_sql).fetchall()
                if not rows:
                    break
                batch: List[Tuple[str, str]] = []
                for row in rows:
                    rid = str(row[self.id_field])
                    raw = row[self.text_field]
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    text = self._text_extractor(raw)
                    if text and text.strip():
                        batch.append((rid, text.strip()))
                if batch:
                    yield batch
                offset += batch_size

    def get_all_ids(self) -> List[str]:
        sql = f"SELECT {self.id_field} FROM {self._table}"
        if self._where_clause:
            sql += f" WHERE {self._where_clause}"
        sql += " ORDER BY rowid"
        with self._get_conn() as conn:
            rows = conn.execute(sql).fetchall()
            return [str(r[self.id_field]) for r in rows]

    def get_description(self) -> str:
        desc = f"SQLite({self._table}.{self.text_field})"
        if self._where_clause:
            desc += f" WHERE {self._where_clause}"
        return desc

    def compute_md5(self) -> str:
        """计算所有文本数据的 MD5（不依赖 ID）"""
        md5 = hashlib.md5()
        for batch in self.iter_records(batch_size=500):
            for rid, text in batch:
                md5.update(text.encode("utf-8"))
        return md5.hexdigest()


class JsonlDataSource(DataSource):
    """
    JSONL 文件数据源。

    每行一个 JSON 对象，从指定字段提取文本。
    """

    def __init__(
        self,
        file_path: str,
        text_field: str = "text",
        id_field: str = "id",
    ) -> None:
        """
        Args:
            file_path: JSONL 文件路径
            text_field: 文本字段名
            id_field: ID 字段名
        """
        super().__init__(text_field=text_field, id_field=id_field)
        self._file_path = file_path
        self._records: Optional[List[Dict[str, Any]]] = None

    def _load_all(self) -> List[Dict[str, Any]]:
        if self._records is not None:
            return self._records
        self._records = []
        with open(self._file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._records.append(json.loads(line))
        return self._records

    def get_total_count(self) -> int:
        return len(self._load_all())

    def iter_records(
        self, batch_size: int = DEFAULT_STREAM_BATCH_SIZE
    ) -> Generator[List[Tuple[str, str]], None, None]:
        records = self._load_all()
        for i in range(0, len(records), batch_size):
            batch_records = records[i : i + batch_size]
            batch: List[Tuple[str, str]] = []
            for rec in batch_records:
                rid = str(rec.get(self.id_field, ""))
                text = rec.get(self.text_field, "")
                if isinstance(text, str) and text.strip():
                    batch.append((rid, text.strip()))
                elif isinstance(text, (dict, list)):
                    batch.append((rid, json.dumps(text, ensure_ascii=False)))
            if batch:
                yield batch

    def get_all_ids(self) -> List[str]:
        records = self._load_all()
        return [str(r.get(self.id_field, f"idx_{i}")) for i, r in enumerate(records)]

    def get_description(self) -> str:
        return f"JSONL({os.path.basename(self._file_path)}.{self.text_field})"

    def compute_md5(self) -> str:
        md5 = hashlib.md5()
        for batch in self.iter_records(batch_size=500):
            for rid, text in batch:
                md5.update(text.encode("utf-8"))
        return md5.hexdigest()


class CsvDataSource(DataSource):
    """
    CSV 文件数据源。

    从指定列名读取文本数据。
    """

    def __init__(
        self,
        file_path: str,
        text_field: str = "text",
        id_field: str = "id",
        delimiter: str = ",",
        encoding: str = "utf-8",
    ) -> None:
        """
        Args:
            file_path: CSV 文件路径
            text_field: 文本列名
            id_field: ID 列名
            delimiter: CSV 分隔符
            encoding: 文件编码
        """
        super().__init__(text_field=text_field, id_field=id_field)
        self._file_path = file_path
        self._delimiter = delimiter
        self._encoding = encoding
        self._rows: Optional[List[Dict[str, str]]] = None

    def _load_all(self) -> List[Dict[str, str]]:
        if self._rows is not None:
            return self._rows
        self._rows = []
        with open(self._file_path, "r", encoding=self._encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=self._delimiter)
            for row in reader:
                self._rows.append(row)
        return self._rows

    def get_total_count(self) -> int:
        return len(self._load_all())

    def iter_records(
        self, batch_size: int = DEFAULT_STREAM_BATCH_SIZE
    ) -> Generator[List[Tuple[str, str]], None, None]:
        rows = self._load_all()
        for i in range(0, len(rows), batch_size):
            batch_rows = rows[i : i + batch_size]
            batch: List[Tuple[str, str]] = []
            for row in batch_rows:
                rid = str(row.get(self.id_field, ""))
                text = row.get(self.text_field, "")
                if text and text.strip():
                    batch.append((rid, text.strip()))
            if batch:
                yield batch

    def get_all_ids(self) -> List[str]:
        rows = self._load_all()
        return [str(r.get(self.id_field, f"row_{i}")) for i, r in enumerate(rows)]

    def get_description(self) -> str:
        return f"CSV({os.path.basename(self._file_path)}.{self.text_field})"

    def compute_md5(self) -> str:
        md5 = hashlib.md5()
        for batch in self.iter_records(batch_size=500):
            for rid, text in batch:
                md5.update(text.encode("utf-8"))
        return md5.hexdigest()


# ---------------------------------------------------------------------------
# 嵌入调度器
# ---------------------------------------------------------------------------

class EmbedScheduler:
    """
    预计算嵌入批处理调度器。

    支持:
    - 全量刷新: 编码所有数据并生成新版本
    - 增量更新: 仅处理指定时间戳之后的数据
    - 断点续传: 从中断位置恢复
    - 进度查询: status() 返回当前进度

    用法:
        scheduler = EmbedScheduler()
        source = SQliteDataSource(db_path="chainke.db")
        scheduler.schedule_full_refresh(source, text_field="fields")
        print(scheduler.status())
    """

    def __init__(
        self,
        embedder_class: Type = None,
        cache_class: Type = None,
        checkpoint_dir: Optional[str] = None,
        version_db_path: Optional[str] = None,
        embedder_kwargs: Optional[Dict[str, Any]] = None,
        cache_dir: Optional[str] = None,
    ) -> None:
        """
        Args:
            embedder_class: BgeM3Embedding 类（或兼容类），None 则延迟导入默认
            cache_class: EmbeddingCache 类（或兼容类），None 则延迟导入默认
            checkpoint_dir: 检查点目录
            version_db_path: 版本数据库路径
            embedder_kwargs: 传递给嵌入器类的额外参数
            cache_dir: 嵌入缓存目录，None 则使用 EmbeddingCache 默认路径
        """
        self._embedder_class = embedder_class
        self._cache_class = cache_class
        self._embedder_kwargs = embedder_kwargs or {}
        self._cache_dir = cache_dir

        # 延迟导入，避免启动时强制依赖
        self._embedder: Any = None
        self._cache: Any = None
        self._initialized: bool = False

        # 管理器
        self._version_manager = VersionManager(
            db_path=version_db_path or DEFAULT_VERSION_DB
        )
        self._checkpoint_manager = CheckpointManager(
            checkpoint_dir=checkpoint_dir or DEFAULT_CHECKPOINT_DIR
        )

        # 运行状态
        self._lock = threading.Lock()
        self._running: bool = False
        self._current_task_id: str = ""
        self._current_source: Optional[DataSource] = None

        # 进度跟踪
        self._total: int = 0
        self._processed: int = 0
        self._failed: int = 0
        self._cache_hits: int = 0
        self._start_time: float = 0.0
        self._current_version: str = ""

    # ------------------------------------------------------------------
    # 延迟初始化
    # ------------------------------------------------------------------

    def _lazy_init(self) -> None:
        """延迟导入并初始化嵌入器和缓存"""
        if self._initialized:
            return

        if self._embedder_class is None:
            from features.embedding_service import BgeM3Embedding
            self._embedder_class = BgeM3Embedding

        if self._cache_class is None:
            from features.embedding_cache import EmbeddingCache
            self._cache_class = EmbeddingCache

        # 创建 force_fallback 嵌入器（避免下载模型）
        kwargs = dict(self._embedder_kwargs)
        kwargs.setdefault("force_fallback", True)
        self._embedder = self._embedder_class(**kwargs)

        # 创建缓存（使用指定缓存目录或默认）
        cache_init_kwargs = {}
        if self._cache_dir is not None:
            cache_init_kwargs["cache_dir"] = self._cache_dir
        self._cache = self._cache_class(**cache_init_kwargs)

        # 确保嵌入器已加载
        if hasattr(self._embedder, "load_model"):
            self._embedder.load_model()
        if hasattr(self._embedder, "warmup"):
            self._embedder.warmup()

        self._initialized = True

    # ------------------------------------------------------------------
    # 模型/缓存属性（便捷访问）
    # ------------------------------------------------------------------

    @property
    def embedder(self) -> Any:
        self._lazy_init()
        return self._embedder

    @property
    def cache(self) -> Any:
        self._lazy_init()
        return self._cache

    @property
    def version_manager(self) -> VersionManager:
        return self._version_manager

    @property
    def checkpoint_manager(self) -> CheckpointManager:
        return self._checkpoint_manager

    # ------------------------------------------------------------------
    # 全量刷新
    # ------------------------------------------------------------------

    def schedule_full_refresh(
        self,
        data_source: DataSource,
        text_field: str = "text",
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
        task_id: Optional[str] = None,
    ) -> str:
        """
        执行全量刷新。

        流程:
        1. 生成新版本号
        2. 获取所有数据 ID
        3. 分批编码并缓存
        4. 检查点记录
        5. 注册版本元数据

        Args:
            data_source: 数据源实例
            text_field: 文本字段（数据源已配置，此处为兼容参数）
            batch_size: 每批编码数量
            task_id: 任务 ID（默认自动生成）

        Returns:
            生成的版本号
        """
        self._lazy_init()

        # 生成版本号
        version = self._version_manager.next_version()

        # 生成任务 ID
        task_id = task_id or f"full_refresh_{version}_{data_source.get_description()}"

        # 设置运行状态
        with self._lock:
            self._running = True
            self._current_task_id = task_id
            self._current_source = data_source
            self._total = data_source.get_total_count()
            self._processed = 0
            self._failed = 0
            self._cache_hits = 0
            self._start_time = time.perf_counter()
            self._current_version = version

        logger.info(
            "[EmbedScheduler] 全量刷新开始: version=%s, data=%s, total=%d",
            version, data_source.get_description(), self._total,
        )

        # 重置检查点（全新开始）
        self._checkpoint_manager.reset(task_id)

        processed_count = 0
        failed_count = 0

        try:
            for batch in data_source.iter_records(batch_size=batch_size):
                if not batch:
                    continue

                ids = [rid for rid, _ in batch]
                texts = [text for _, text in batch]

                # 检查缓存
                cached_vectors = self._cache.batch_get(texts)
                uncached_texts: List[str] = []
                uncached_indices: List[int] = []

                for i, (txt, vec) in enumerate(zip(texts, cached_vectors)):
                    if vec is not None:
                        self._cache_hits += 1
                    else:
                        uncached_texts.append(txt)
                        uncached_indices.append(i)

                # 编码未缓存的部分
                if uncached_texts:
                    encoded = self.embedder.encode(uncached_texts)
                    if encoded is not None:
                        # 写入缓存
                        pairs = list(zip(uncached_texts, encoded))
                        self._cache.batch_set(pairs)
                    else:
                        logger.warning(
                            "[EmbedScheduler] 批次编码失败，跳过 %d 条",
                            len(uncached_texts),
                        )
                        failed_count += len(uncached_texts)
                        self._checkpoint_manager.mark_failed(
                            task_id,
                            [ids[uncached_indices[i]] for i in range(len(uncached_texts))],
                        )
                        # 处理成功的部分
                        success_ids = [ids[i] for i in range(len(ids))
                                       if i not in uncached_indices]
                        if success_ids:
                            self._checkpoint_manager.mark_processed(task_id, success_ids)
                        continue

                # 标记已处理
                self._checkpoint_manager.mark_processed(task_id, ids)
                processed_count += len(ids)

                # 更新进度
                with self._lock:
                    self._processed = processed_count
                    self._failed = failed_count

            # 计算 MD5
            md5 = data_source.compute_md5()

            # 注册版本
            self._version_manager.register_version(
                version=version,
                embedding_model=self._get_model_name(),
                record_count=processed_count,
                data_source=data_source.get_description(),
                text_field=text_field,
                md5_checksum=md5,
                metadata={
                    "task_id": task_id,
                    "total_records": self._total,
                    "failed_records": failed_count,
                    "cache_hits": self._cache_hits,
                    "batch_size": batch_size,
                },
            )

            elapsed = time.perf_counter() - self._start_time
            logger.info(
                "[EmbedScheduler] 全量刷新完成: version=%s, processed=%d, "
                "failed=%d, elapsed=%.2fs",
                version, processed_count, failed_count, elapsed,
            )

        except Exception as e:
            logger.error("[EmbedScheduler] 全量刷新异常: %s", e)
            self._version_manager.mark_version_failed(version, str(e))
            raise
        finally:
            with self._lock:
                self._running = False

        return version

    # ------------------------------------------------------------------
    # 增量更新
    # ------------------------------------------------------------------

    def schedule_incremental(
        self,
        data_source: DataSource,
        text_field: str = "text",
        since_timestamp: Optional[str] = None,
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
        task_id: Optional[str] = None,
    ) -> int:
        """
        执行增量更新。

        增量更新不生成新版本，仅将新数据的嵌入写入缓存。
        可在之后通过全量刷新生成新版。

        Args:
            data_source: 数据源实例
            text_field: 文本字段名
            since_timestamp: 起始时间戳（ISO 格式），None 则处理全部
            batch_size: 每批编码数量
            task_id: 任务 ID（默认自动生成）

        Returns:
            处理的数据条数
        """
        self._lazy_init()

        task_id = task_id or f"incremental_{data_source.get_description()}_{int(time.time())}"

        with self._lock:
            self._running = True
            self._current_task_id = task_id
            self._current_source = data_source
            self._total = data_source.get_total_count()
            self._processed = 0
            self._failed = 0
            self._cache_hits = 0
            self._start_time = time.perf_counter()
            self._current_version = ""

        logger.info(
            "[EmbedScheduler] 增量更新开始: task=%s, since=%s",
            task_id, since_timestamp or "全部",
        )

        processed_count = 0

        try:
            # 对于增量，先加载检查点（如果有）
            all_ids = data_source.get_all_ids()
            unprocessed_ids = set(self._checkpoint_manager.get_unprocessed_ids(task_id, all_ids))

            for batch in data_source.iter_records(batch_size=batch_size):
                # 过滤已处理的 ID
                fresh_batch = [(rid, txt) for rid, txt in batch if rid in unprocessed_ids]
                if not fresh_batch:
                    continue

                ids = [rid for rid, _ in fresh_batch]
                texts = [txt for _, txt in fresh_batch]

                # 先查缓存
                cached_vectors = self._cache.batch_get(texts)
                need_encode: List[Tuple[str, str]] = []
                for i, (rid, txt) in enumerate(fresh_batch):
                    if cached_vectors[i] is not None:
                        self._cache_hits += 1
                    else:
                        need_encode.append((rid, txt))

                # 编码未缓存的部分
                if need_encode:
                    need_texts = [txt for _, txt in need_encode]
                    encoded = self.embedder.encode(need_texts)
                    if encoded is not None:
                        self._cache.batch_set(list(zip(need_texts, encoded)))
                    else:
                        logger.warning(
                            "[EmbedScheduler] 增量编码失败，跳过 %d 条",
                            len(need_texts),
                        )

                # 标记已处理
                self._checkpoint_manager.mark_processed(task_id, ids)
                processed_count += len(ids)

                with self._lock:
                    self._processed = processed_count

            elapsed = time.perf_counter() - self._start_time
            logger.info(
                "[EmbedScheduler] 增量更新完成: processed=%d, elapsed=%.2fs",
                processed_count, elapsed,
            )

        except Exception as e:
            logger.error("[EmbedScheduler] 增量更新异常: %s", e)
            raise
        finally:
            with self._lock:
                self._running = False

        return processed_count

    # ------------------------------------------------------------------
    # 批处理编码
    # ------------------------------------------------------------------

    def process_batch(
        self,
        texts: Sequence[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Optional[List[List[float]]]:
        """
        编码一批文本并写入缓存。

        Args:
            texts: 待编码的文本列表
            batch_size: 批处理大小

        Returns:
            嵌入向量列表，失败返回 None
        """
        self._lazy_init()

        if not texts:
            return []

        text_list = list(texts)
        vectors: List[Optional[List[float]]] = [None] * len(text_list)

        # 查缓存
        cached = self._cache.batch_get(text_list)
        for i, v in enumerate(cached):
            if v is not None:
                vectors[i] = v
                self._cache_hits += 1

        # 未命中的需要编码
        uncached_indices = [i for i, v in enumerate(vectors) if v is None]
        if uncached_indices:
            uncached_texts = [text_list[i] for i in uncached_indices]
            encoded = self.embedder.encode(uncached_texts, batch_size=batch_size)
            if encoded is not None:
                # 写入缓存
                pairs = list(zip(uncached_texts, encoded))
                self._cache.batch_set(pairs)
                for idx, vec in zip(uncached_indices, encoded):
                    vectors[idx] = vec
                with self._lock:
                    self._processed += len(encoded)
            else:
                logger.error("[EmbedScheduler] process_batch 编码失败")
                return None

        return [v for v in vectors if v is not None]

    # ------------------------------------------------------------------
    # 断点续传
    # ------------------------------------------------------------------

    def resume(
        self,
        task_id: Optional[str] = None,
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    ) -> Dict[str, Any]:
        """
        从检查点恢复未完成的调度任务。

        如果 task_id 未指定，尝试恢复最近的未完成任务。

        Args:
            task_id: 要恢复的任务 ID
            batch_size: 批处理大小

        Returns:
            结果字典 { "version", "processed", "failed", "status" }
        """
        self._lazy_init()

        if task_id is None:
            # 尝试找到最近的检查点
            checkpoints = self._checkpoint_manager.list_checkpoints()
            if not checkpoints:
                return {
                    "version": "",
                    "processed": 0,
                    "failed": 0,
                    "status": "no_checkpoint",
                    "message": "没有可恢复的检查点",
                }
            task_id = checkpoints[-1]  # 最新

        checkpoint = self._checkpoint_manager.load(task_id)
        if not checkpoint or not checkpoint.get("total_count"):
            return {
                "version": "",
                "processed": 0,
                "failed": 0,
                "status": "empty_checkpoint",
                "message": f"检查点 {task_id} 为空或无效",
            }

        # 解析任务信息
        # task_id 格式: full_refresh_v1_SQLite(...) 或 incremental_...
        is_full = task_id.startswith("full_refresh_")
        parts = task_id.split("_")
        version = ""
        if is_full and len(parts) >= 3:
            version = parts[2]  # v1, v2, ...

        logger.info(
            "[EmbedScheduler] 恢复任务: %s (version=%s, processed=%d/%d)",
            task_id, version,
            checkpoint.get("processed_count", 0),
            checkpoint.get("total_count", 0),
        )

        # 这需要外部提供数据源——这里我们没法恢复数据源引用
        # 所以返回检查点信息，让调用者提供数据源重新运行
        return {
            "version": version,
            "task_id": task_id,
            "processed": checkpoint.get("processed_count", 0),
            "failed": len(checkpoint.get("failed_ids", [])),
            "total": checkpoint.get("total_count", 0),
            "status": "partial" if checkpoint.get("processed_count", 0) < checkpoint.get("total_count", 0) else "completed",
            "checkpoint": checkpoint,
            "message": (
                "检查点加载成功。请调用 schedule_full_refresh 并传入相同的 task_id 以续传，"
                "或调用 checkpoint_manager.get_unprocessed_ids 获取未处理 ID 后手动处理"
            ),
        }

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """
        获取当前调度状态。

        Returns:
            - running: bool 是否正在运行
            - task_id: str 当前任务 ID
            - version: str 当前版本号
            - total: int 总记录数
            - processed: int 已处理数
            - failed: int 失败数
            - cache_hits: int 缓存命中数
            - progress_pct: float 进度百分比
            - eta: str 预估剩余时间
            - elapsed: float 已用时间(秒)
            - data_source: str 数据源描述
        """
        with self._lock:
            elapsed = time.perf_counter() - self._start_time if self._start_time > 0 else 0.0
            progress = (self._processed / self._total * 100) if self._total > 0 else 0.0

            # ETA 估算
            eta = "N/A"
            if self._processed > 0 and elapsed > 0 and self._total > 0:
                rate = self._processed / elapsed
                remaining = self._total - self._processed
                if rate > 0:
                    eta_secs = remaining / rate
                    if eta_secs < 60:
                        eta = f"{eta_secs:.0f}s"
                    elif eta_secs < 3600:
                        eta = f"{eta_secs / 60:.1f}m"
                    else:
                        eta = f"{eta_secs / 3600:.1f}h"

            return {
                "running": self._running,
                "task_id": self._current_task_id,
                "version": self._current_version,
                "total": self._total,
                "processed": self._processed,
                "failed": self._failed,
                "cache_hits": self._cache_hits,
                "progress_pct": round(progress, 2),
                "eta": eta,
                "elapsed_seconds": round(elapsed, 2),
                "data_source": self._current_source.get_description() if self._current_source else "",
            }

    # ------------------------------------------------------------------
    # 版本查询
    # ------------------------------------------------------------------

    def get_latest_version(self) -> Optional[Dict[str, Any]]:
        """获取最新版本元数据"""
        return self._version_manager.get_latest_version()

    def get_version(self, version: str) -> Optional[Dict[str, Any]]:
        """获取指定版本元数据"""
        return self._version_manager.get_version(version)

    def list_versions(self) -> List[str]:
        """列出所有版本"""
        return self._version_manager.list_versions()

    def list_version_metadata(self) -> List[Dict[str, Any]]:
        """列出所有版本的完整元数据"""
        return self._version_manager.list_version_metadata()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _get_model_name(self) -> str:
        """获取嵌入模型名称"""
        try:
            if hasattr(self._embedder, "model_name"):
                return self._embedder.model_name
        except Exception:
            pass
        return "BgeM3Embedding(fallback)" if hasattr(self._embedder, "is_fallback") and self._embedder.is_fallback else "BgeM3Embedding"

    def __repr__(self) -> str:
        status_info = self.status()
        return (
            f"EmbedScheduler(running={status_info['running']}, "
            f"version={status_info['version']}, "
            f"progress={status_info['progress_pct']}%, "
            f"task={status_info['task_id']})"
        )
