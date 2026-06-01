"""
觅迹 Mijü·翻页图册 (Digital Brochure) API
使用原生 sqlite3（非 SQLAlchemy），独立数据库文件 digital_brochure.db

7 张表:
  auth_users     - 认证用户
  auth_tokens    - 认证令牌
  users          - 用户信息
  brochures      - 翻页图册
  trust_network  - 信任网络
  match_records  - 匹配记录
  visitor_logs   - 访客日志

版本: 1.0.0
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 数据库路径（当前目录下的 digital_brochure.db）
# ============================================================
DB_DIR = os.environ.get(
    "BROCHURE_DB_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)
DB_NAME = "digital_brochure.db"
DB_PATH = os.path.join(DB_DIR, DB_NAME)

# 线程本地存储，确保每个线程有自己的连接
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接"""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def close_connection():
    """关闭当前线程的数据库连接"""
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None


# ============================================================
# 建表 DDL (版本 v1.0.0)
# ============================================================
SCHEMA_VERSION = "v1.0.0"

CREATE_TABLES_SQL = [
    # --- 1. auth_users: 认证用户 ---
    """
    CREATE TABLE IF NOT EXISTS auth_users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT    NOT NULL UNIQUE,
        password_hash   TEXT    NOT NULL,
        email           TEXT,
        phone           TEXT,
        is_active       INTEGER NOT NULL DEFAULT 1,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # --- 2. auth_tokens: 认证令牌 ---
    """
    CREATE TABLE IF NOT EXISTS auth_tokens (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL REFERENCES auth_users(id),
        token           TEXT    NOT NULL UNIQUE,
        token_type      TEXT    NOT NULL DEFAULT 'access',
        expires_at      TEXT    NOT NULL,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        revoked         INTEGER NOT NULL DEFAULT 0
    )
    """,
    # --- 3. users: 用户信息 ---
    """
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        auth_user_id    INTEGER REFERENCES auth_users(id),
        name            TEXT    NOT NULL,
        company         TEXT,
        position        TEXT,
        avatar          TEXT,
        phone           TEXT,
        email           TEXT,
        wechat_id       TEXT,
        bio             TEXT,
        tags            TEXT    DEFAULT '[]',
        settings        TEXT    DEFAULT '{}',
        is_public       INTEGER NOT NULL DEFAULT 1,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # --- 4. brochures: 翻页图册 ---
    """
    CREATE TABLE IF NOT EXISTS brochures (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL REFERENCES users(id),
        title           TEXT    NOT NULL,
        cover           TEXT,
        pages_count     INTEGER NOT NULL DEFAULT 0,
        description     TEXT,
        status          TEXT    NOT NULL DEFAULT 'draft',
        is_public       INTEGER NOT NULL DEFAULT 1,
        view_count      INTEGER NOT NULL DEFAULT 0,
        share_count     INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # --- 5. trust_network: 信任网络 ---
    """
    CREATE TABLE IF NOT EXISTS trust_network (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL REFERENCES users(id),
        target_user_id  INTEGER NOT NULL REFERENCES users(id),
        trust_level     INTEGER NOT NULL DEFAULT 1,
        tags            TEXT    DEFAULT '[]',
        notes           TEXT,
        is_mutual       INTEGER NOT NULL DEFAULT 0,
        source          TEXT    DEFAULT 'manual',
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        UNIQUE(user_id, target_user_id)
    )
    """,
    # --- 6. match_records: 匹配记录 ---
    """
    CREATE TABLE IF NOT EXISTS match_records (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL REFERENCES users(id),
        matched_user_id INTEGER NOT NULL REFERENCES users(id),
        match_type      TEXT    NOT NULL DEFAULT 'supply_demand',
        match_score     REAL,
        match_reason    TEXT,
        status          TEXT    NOT NULL DEFAULT 'pending',
        contact_made    INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # --- 7. visitor_logs: 访客日志 ---
    """
    CREATE TABLE IF NOT EXISTS visitor_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        brochure_id     INTEGER NOT NULL REFERENCES brochures(id),
        visitor_id      INTEGER REFERENCES users(id),
        visitor_ip      TEXT,
        visitor_agent   TEXT,
        visit_type      TEXT    NOT NULL DEFAULT 'view',
        duration_sec    INTEGER DEFAULT 0,
        extra_data      TEXT    DEFAULT '{}',
        created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # --- 索引 ---
    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_auth_tokens_token ON auth_tokens(token)",
    "CREATE INDEX IF NOT EXISTS idx_users_auth ON users(auth_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_brochures_user ON brochures(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_brochures_status ON brochures(status)",
    "CREATE INDEX IF NOT EXISTS idx_trust_network_user ON trust_network(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_trust_network_target ON trust_network(target_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_match_records_user ON match_records(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_match_records_match ON match_records(matched_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_visitor_logs_brochure ON visitor_logs(brochure_id)",
    "CREATE INDEX IF NOT EXISTS idx_visitor_logs_visitor ON visitor_logs(visitor_id)",
    "CREATE INDEX IF NOT EXISTS idx_visitor_logs_time ON visitor_logs(created_at)",
]

# ============================================================
# Schema 版本记录表
# ============================================================
CREATE_SCHEMA_META = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
)
"""


def init_db():
    """
    初始化数据库：创建所有表（如果不存在）
    版本注释: digital_brochure_db v1.0.0 - 7张表
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 创建 schema 版本表
    cursor.execute(CREATE_SCHEMA_META)

    # 检查是否已初始化
    cursor.execute("SELECT version FROM _schema_version WHERE version = ?", (SCHEMA_VERSION,))
    if cursor.fetchone():
        logger.info(f"digital_brochure_db 已初始化 (version={SCHEMA_VERSION})")
        return

    # 创建所有表
    for sql in CREATE_TABLES_SQL:
        cursor.execute(sql)

    # 记录版本
    cursor.execute(
        "INSERT OR REPLACE INTO _schema_version (version, description) VALUES (?, ?)",
        (SCHEMA_VERSION, "digital_brochure_db v1.0.0 - 7张初始表 (auth_users, auth_tokens, users, brochures, trust_network, match_records, visitor_logs)"),
    )

    conn.commit()
    logger.info(f"digital_brochure_db 初始化完成 (version={SCHEMA_VERSION})")


# ============================================================
# CRUD 辅助函数
# ============================================================

def dict_from_row(row) -> dict:
    """将 sqlite3.Row 转换为 dict"""
    if row is None:
        return None
    return dict(row)


def get_brochure(brochure_id: int) -> Optional[dict]:
    """获取单个图册"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM brochures WHERE id = ?", (brochure_id,))
    return dict_from_row(cursor.fetchone())


def get_user_brochures(user_id: int) -> list:
    """获取用户的所有图册"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM brochures WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    )
    return [dict_from_row(row) for row in cursor.fetchall()]


def record_visit(brochure_id: int, visitor_id: Optional[int] = None,
                 visitor_ip: Optional[str] = None,
                 visitor_agent: Optional[str] = None) -> int:
    """记录访客并返回日志ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO visitor_logs
           (brochure_id, visitor_id, visitor_ip, visitor_agent, visit_type)
           VALUES (?, ?, ?, ?, 'view')""",
        (brochure_id, visitor_id, visitor_ip, visitor_agent),
    )
    # 更新浏览计数
    cursor.execute(
        "UPDATE brochures SET view_count = view_count + 1, updated_at = datetime('now') WHERE id = ?",
        (brochure_id,),
    )
    conn.commit()
    return cursor.lastrowid


def get_visitor_logs(brochure_id: int, limit: int = 50) -> list:
    """获取图册的访客记录"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT vl.*, u.name as visitor_name, u.avatar as visitor_avatar
           FROM visitor_logs vl
           LEFT JOIN users u ON vl.visitor_id = u.id
           WHERE vl.brochure_id = ?
           ORDER BY vl.created_at DESC
           LIMIT ?""",
        (brochure_id, limit),
    )
    return [dict_from_row(row) for row in cursor.fetchall()]


# ============================================================
# FastAPI 集成（可选）
# ============================================================

try:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/api/v1/digital-brochure", tags=["觅迹·数字图册"])

    @router.get("/{brochure_id}")
    def api_get_brochure(brochure_id: int):
        """获取翻页图册"""
        init_db()  # 确保数据库已初始化
        brochure = get_brochure(brochure_id)
        if not brochure:
            raise HTTPException(status_code=404, detail="图册不存在")
        return {"code": 200, "data": brochure}

    @router.post("/{brochure_id}/visit")
    def api_record_visit(brochure_id: int, visitor_id: int = None):
        """记录访客"""
        init_db()
        brochure = get_brochure(brochure_id)
        if not brochure:
            raise HTTPException(status_code=404, detail="图册不存在")
        record_visit(brochure_id, visitor_id)
        return {"code": 200, "message": "已记录"}

    @router.get("/{brochure_id}/visitors")
    def api_get_visitors(brochure_id: int, limit: int = 50):
        """获取访客记录"""
        init_db()
        logs = get_visitor_logs(brochure_id, limit)
        return {"code": 200, "data": logs}

except ImportError:
    # 无 FastAPI 环境，仅提供原生函数
    router = None
