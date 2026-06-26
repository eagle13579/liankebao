"""
站内通知系统 (notifications.py)

零外部依赖，纯 Python + SQLite 实现。
提供创建通知、查询通知、标记已读等功能。
数据库文件默认存储在项目 data/ 目录下。
适配到 chainke-full 项目路径。
"""
import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any


class NotificationService:
    """站内通知服务"""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # workflow -> backend
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "notifications.db")
        self._db_path = db_path
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        """线程本地连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                notification_type TEXT DEFAULT 'info',
                reference_type TEXT,
                reference_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                read_at TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notifications_user
            ON notifications(user_id, is_read, created_at DESC)
        """)
        conn.commit()
        conn.close()

    # ── 创建通知 ────────────────────────────────────────────────

    def send(
        self,
        user_id: int,
        title: str,
        content: str | None = None,
        notification_type: str = "info",
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> int:
        """向指定用户发送站内通知

        Args:
            user_id:           接收用户ID
            title:             通知标题
            content:           通知内容 (可选)
            notification_type: 通知类型: info / warning / success / error
            reference_type:    关联实体类型 (可选)
            reference_id:      关联实体ID (可选)

        Returns:
            新创建的通知ID
        """
        cursor = self._conn.execute(
            """
            INSERT INTO notifications (user_id, title, content, notification_type,
                                       reference_type, reference_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, title, content, notification_type, reference_type, reference_id),
        )
        self._conn.commit()
        return cursor.lastrowid

    def send_broadcast(
        self,
        user_ids: list[int],
        title: str,
        content: str | None = None,
        notification_type: str = "info",
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> list[int]:
        """向多个用户发送通知

        Returns:
            创建的通知ID列表
        """
        ids = []
        for uid in user_ids:
            nid = self.send(uid, title, content, notification_type, reference_type, reference_id)
            ids.append(nid)
        return ids

    # ── 查询 ─────────────────────────────────────────────────────

    def get_user_notifications(
        self,
        user_id: int,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """获取用户的通知列表"""
        query = "SELECT * FROM notifications WHERE user_id = ?"
        params: list[Any] = [user_id]

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def count_unread(self, user_id: int) -> int:
        """统计用户未读通知数"""
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_by_id(self, notification_id: int) -> dict[str, Any] | None:
        """根据ID获取通知"""
        row = self._conn.execute(
            "SELECT * FROM notifications WHERE id = ?", (notification_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── 标记状态 ────────────────────────────────────────────────

    def mark_read(self, notification_id: int) -> bool:
        """标记单条通知为已读"""
        cursor = self._conn.execute(
            "UPDATE notifications SET is_read = 1, read_at = datetime('now', 'localtime') WHERE id = ?",
            (notification_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def mark_all_read(self, user_id: int) -> int:
        """标记用户所有通知为已读"""
        cursor = self._conn.execute(
            "UPDATE notifications SET is_read = 1, read_at = datetime('now', 'localtime') "
            "WHERE user_id = ? AND is_read = 0",
            (user_id,),
        )
        self._conn.commit()
        return cursor.rowcount

    def delete(self, notification_id: int) -> bool:
        """删除通知"""
        cursor = self._conn.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_old(self, days: int = 90) -> int:
        """清理指定天数之前的已读通知"""
        cursor = self._conn.execute(
            "DELETE FROM notifications WHERE is_read = 1 AND "
            "created_at < datetime('now', ? || ' days', 'localtime')",
            (f"-{days}",),
        )
        self._conn.commit()
        return cursor.rowcount

    def __repr__(self) -> str:
        return f"<NotificationService(db='{self._db_path}')>"
