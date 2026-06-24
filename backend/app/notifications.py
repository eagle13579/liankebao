"""
站内消息通知系统
使用独立 SQLite 存储通知记录
"""

import logging
import os
import sqlite3
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# 通知数据库路径
_NOTIFY_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_NOTIFY_DB_PATH = os.path.join(_NOTIFY_DB_DIR, "notifications.db")

# 有效通知类型
VALID_TYPES = frozenset(
    {
        "order_status",
        "payment",
        "withdrawal",
        "review_result",
        "system",
        "match_alert",
    }
)


def _get_connection() -> sqlite3.Connection:
    """获取通知数据库连接（每次调用创建新连接，线程安全）"""
    os.makedirs(_NOTIFY_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_NOTIFY_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_notify_db():
    """初始化通知表（幂等）"""
    conn = _get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                type        TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                content     TEXT    NOT NULL DEFAULT '',
                related_id  INTEGER DEFAULT NULL,
                is_read     INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notify_user
            ON notifications(user_id, is_read, created_at)
        """)
        conn.commit()
    finally:
        conn.close()


# 模块导入时自动建表
_init_notify_db()


class NotificationManager:
    """站内消息管理器"""

    @staticmethod
    def create_notification(
        user_id: int,
        type_: str,
        title: str,
        content: str = "",
        related_id: int | None = None,
    ) -> dict:
        """
        创建通知

        Args:
            user_id:    接收通知的用户ID
            type_:      通知类型，可选：order_status / payment / withdrawal / review_result / system
            title:      通知标题
            content:    通知内容（可选）
            related_id: 关联的业务ID（订单ID/提现ID等，可选）

        Returns:
            创建的通知字典

        Raises:
            ValueError: 通知类型不合法
        """
        if type_ not in VALID_TYPES:
            raise ValueError(f"无效的通知类型 '{type_}'，有效值：{', '.join(sorted(VALID_TYPES))}")

        now = datetime.now(UTC).isoformat()
        conn = _get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO notifications (user_id, type, title, content, related_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, type_, title, content, related_id, now),
            )
            notification_id = cursor.lastrowid
            conn.commit()

            notification = {
                "id": notification_id,
                "user_id": user_id,
                "type": type_,
                "title": title,
                "content": content,
                "related_id": related_id,
                "is_read": False,
                "created_at": now,
            }

            logger.info(
                "通知已创建",
                extra={
                    "notification_id": notification_id,
                    "target_user": user_id,
                    "notify_type": type_,
                },
            )
            return notification
        finally:
            conn.close()

    @staticmethod
    def get_user_notifications(
        user_id: int,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        获取用户通知列表（按时间倒序）

        Args:
            user_id:     用户ID
            unread_only: 是否仅未读
            page:        页码（从1开始）
            page_size:   每页条数

        Returns:
            {
                "total": int,
                "page": int,
                "page_size": int,
                "total_pages": int,
                "unread_count": int,
                "notifications": [dict, ...]
            }
        """
        page = max(page, 1)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        conn = _get_connection()
        try:
            # 总条数
            if unread_only:
                count_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=? AND is_read=0",
                    (user_id,),
                ).fetchone()
            else:
                count_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=?",
                    (user_id,),
                ).fetchone()

            total = count_row["cnt"] if count_row else 0

            # 未读数
            unread_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=? AND is_read=0",
                (user_id,),
            ).fetchone()
            unread_count = unread_row["cnt"] if unread_row else 0

            # 查询列表
            if unread_only:
                rows = conn.execute(
                    """
                    SELECT id, user_id, type, title, content, related_id, is_read, created_at
                    FROM notifications
                    WHERE user_id=? AND is_read=0
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, page_size, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, user_id, type, title, content, related_id, is_read, created_at
                    FROM notifications
                    WHERE user_id=?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, page_size, offset),
                ).fetchall()

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            notifications = []
            for r in rows:
                notifications.append(
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "type": r["type"],
                        "title": r["title"],
                        "content": r["content"],
                        "related_id": r["related_id"],
                        "is_read": bool(r["is_read"]),
                        "created_at": r["created_at"],
                    }
                )

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "unread_count": unread_count,
                "notifications": notifications,
            }
        finally:
            conn.close()

    @staticmethod
    def mark_as_read(notification_id: int) -> bool:
        """
        标记单条通知为已读

        Returns:
            True 如果通知存在且被更新
        """
        conn = _get_connection()
        try:
            cursor = conn.execute(
                "UPDATE notifications SET is_read=1 WHERE id=?",
                (notification_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def mark_all_as_read(user_id: int) -> int:
        """
        标记用户所有通知为已读

        Returns:
            被更新的通知条数
        """
        conn = _get_connection()
        try:
            cursor = conn.execute(
                "UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0",
                (user_id,),
            )
            conn.commit()
            updated = cursor.rowcount
            logger.info(
                "全部标记已读",
                extra={"user_id": user_id, "count": updated},
            )
            return updated
        finally:
            conn.close()

    @staticmethod
    def delete_notification(notification_id: int) -> bool:
        """删除单条通知"""
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM notifications WHERE id=?", (notification_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        """获取用户未读通知数"""
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=? AND is_read=0",
                (user_id,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
