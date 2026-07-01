"""
模型注册 — ModelRegistry
- 版本管理 + stage 提升 (staging / production)
- 字典 + SQLite 持久化
- 生产模型获取
"""

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = "model_registry.db"


@dataclass
class ModelRecord:
    """模型记录。"""
    name: str
    version: str
    path: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    stage: str = "none"          # none / staging / production
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ModelRegistry:
    """模型注册中心 (线程安全, SQLite 持久化)。

    说明: 使用文件路径时数据持久化到磁盘；使用 ':memory:' 仅在当前连接有效。
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    # ── SQLite 初始化 ─────────────────────────────────────────

    def _init_db(self):
        # 使用持久连接避免 :memory: 模式丢失表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS models (
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                path TEXT NOT NULL,
                metrics TEXT DEFAULT '{}',
                stage TEXT DEFAULT 'none',
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (name, version)
            )
        """)
        self._conn.commit()

    def _row_to_record(self, row: tuple) -> ModelRecord:
        return ModelRecord(
            name=row[0],
            version=row[1],
            path=row[2],
            metrics=json.loads(row[3]) if row[3] else {},
            stage=row[4],
            created_at=row[5],
        )

    # ── CRUD ──────────────────────────────────────────────────

    def register_model(
        self,
        name: str,
        version: str,
        path: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> ModelRecord:
        """注册一个新模型版本。"""
        record = ModelRecord(
            name=name,
            version=version,
            path=path,
            metrics=metrics or {},
        )
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO models (name, version, path, metrics, stage, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (record.name, record.version, record.path,
                 json.dumps(record.metrics), record.stage, record.created_at),
            )
            self._conn.commit()
        logger.info("注册模型: %s v%s (path=%s)", name, version, path)
        return record

    def get_model(self, name: str, version: str) -> Optional[ModelRecord]:
        """获取指定版本模型。"""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT name, version, path, metrics, stage, created_at FROM models "
                "WHERE name=? AND version=?",
                (name, version),
            )
            row = cursor.fetchone()
        if row is None:
            logger.warning("模型未找到: %s v%s", name, version)
            return None
        return self._row_to_record(row)

    def list_models(self) -> List[ModelRecord]:
        """列出所有已注册模型。"""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT name, version, path, metrics, stage, created_at FROM models "
                "ORDER BY name, created_at DESC"
            )
            rows = cursor.fetchall()
        return [self._row_to_record(r) for r in rows]

    # ── Stage 提升 ────────────────────────────────────────────

    def promote_model(self, name: str, version: str, stage: str) -> Optional[ModelRecord]:
        """提升模型到指定 stage (staging / production)。

        提升到 production 时会自动将同一 name 下其他 production 模型降级为 staging。
        """
        if stage not in ("staging", "production"):
            raise ValueError("stage 必须是 staging 或 production")

        with self._lock:
            # 检查模型是否存在
            cursor = self._conn.execute(
                "SELECT name, version, path, metrics, stage, created_at FROM models "
                "WHERE name=? AND version=?",
                (name, version),
            )
            row = cursor.fetchone()
            if row is None:
                logger.warning("提升失败: 模型 %s v%s 不存在", name, version)
                return None

            if stage == "production":
                # 降级当前 production
                self._conn.execute(
                    "UPDATE models SET stage='staging' WHERE name=? AND stage='production'",
                    (name,),
                )

            self._conn.execute(
                "UPDATE models SET stage=? WHERE name=? AND version=?",
                (stage, name, version),
            )
            self._conn.commit()

            # 返回更新后的记录
            cursor = self._conn.execute(
                "SELECT name, version, path, metrics, stage, created_at FROM models "
                "WHERE name=? AND version=?",
                (name, version),
            )
            updated = self._row_to_record(cursor.fetchone())
            logger.info("模型提升: %s v%s → %s", name, version, stage)
            return updated

    def get_production_model(self, name: str) -> Optional[ModelRecord]:
        """获取生产环境模型。"""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT name, version, path, metrics, stage, created_at FROM models "
                "WHERE name=? AND stage='production' ORDER BY created_at DESC LIMIT 1",
                (name,),
            )
            row = cursor.fetchone()
        if row is None:
            logger.info("模型 %s 没有 production 版本", name)
            return None
        return self._row_to_record(row)
