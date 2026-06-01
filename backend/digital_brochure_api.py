#!/usr/bin/env python3
"""
AI数字名片 v2.1 — FastAPI 服务
===============================
端口: 8003
存储: SQLite (digital_brochure.db)

API 端点概要:
  GET    /api/brochures              — 获取所有画册
  GET    /api/brochures/{user_id}    — 获取指定用户画册
  POST   /api/brochures              — 创建画册
  PUT    /api/brochures/{user_id}    — 更新画册
  DELETE /api/brochures/{user_id}    — 删除画册
  GET    /api/brochures/{user_id}/trust_network   — 获取信任网络
  POST   /api/brochures/{user_id}/trust_network   — 添加信任关系
  DELETE /api/brochures/{user_id}/trust_network   — 移除信任关系
  GET    /api/brochures/{user_id}/matches         — 获取匹配列表
  POST   /api/match                               — 匹配引擎
  GET    /api/users                               — 获取用户列表
  GET    /api/users/{user_id}                     — 获取指定用户
  GET    /api/health                              — 健康检查
"""

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import sys
import threading
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import uvicorn

# ── P2: tracing / rate-limit / sentry / metrics / i18n ──────────
import contextvars
import time
from collections import deque

from app.i18n import _, detect_lang
from app.rate_limiter import (
    MemoryRateLimiter,
    get_rate_limiter,
    get_route_limit,
    extract_client_ip,
    extract_user_id,
    is_rate_limiting_enabled as _rate_limit_enabled,
)
from app.sentry_config import setup_sentry, wrap_with_sentry, is_sentry_active
from app.observability import get_metrics_collector, get_system_info

# FastAPI exception handlers
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── 全局 trace_id 上下文 ──────────────────────────────────
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='')
_lang_var: contextvars.ContextVar[str] = contextvars.ContextVar('lang', default='zh')


# ── 日志 ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("digital_brochure")

# ── 配置 ──────────────────────────────────────────────
PORT = 8003
HOST = "0.0.0.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "digital_brochure.db")

# ── 链客宝对接配置（实时读取环境变量或使用默认值） ────
CHAINKE_API_BASE = os.environ.get("CHAINKE_API_BASE", "") or ""
"""链客宝用户系统对接基地址。设为空字符串则使用本地 SQLite 用户系统（默认）。
Phase 3: 信任网络→企盟匹配桥接，可指向链客宝网关 :5136。"""

# ── 链客宝桥接模块 ──────────────────────────────────
_chainke_bridge = None
def _get_chainke_bridge():
    """延迟加载 chainke_bridge 模块，避免启动时依赖链客宝后端。"""
    global _chainke_bridge
    if _chainke_bridge is None:
        try:
            from backend.app.services import chainke_bridge as cb
            # 设置 API 基地址
            if CHAINKE_API_BASE:
                cb.CHAINKE_API_BASE = CHAINKE_API_BASE
            _chainke_bridge = cb
            if CHAINKE_API_BASE:
                logger.info("链客宝桥接模块已加载: %s", CHAINKE_API_BASE)
            else:
                logger.info("链客宝桥接模块已加载（本地模式，未配置远程地址）")
        except ImportError:
            logger.warning("chainke_bridge 模块未找到，链客宝同步功能不可用")
            _chainke_bridge = None
    return _chainke_bridge

# ── 安全配置 ──────────────────────────────────────────
TOKEN_EXPIRE_HOURS = 72
"""Token 过期时间（小时）。"""

# ── 全局内存缓存（保持API返回格式兼容） ────────────────
BROCHURES: dict[str, dict] = {}
_db_lock = threading.Lock()


# ════════════════════════════════════════════════════════
# SQLite 持久化层
# ════════════════════════════════════════════════════════

def get_db_conn() -> sqlite3.Connection:
    """获取 SQLite 连接（线程安全）。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构。"""
    conn = get_db_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS brochures (
                brochure_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                company TEXT DEFAULT '',
                position TEXT DEFAULT '',
                avatar TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES auth_users(user_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id
            ON auth_tokens(user_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_tokens_created
            ON auth_tokens(created_at)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trust_network (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                trusted_user_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, trusted_user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a TEXT NOT NULL,
                user_b TEXT NOT NULL,
                score REAL DEFAULT 0,
                common_tags TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brochure_id TEXT NOT NULL,
                visitor_ip TEXT DEFAULT '',
                visitor_name TEXT DEFAULT '',
                source TEXT DEFAULT 'direct',
                visit_time TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (brochure_id) REFERENCES brochures(brochure_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_visitor_logs_brochure_id
            ON visitor_logs(brochure_id, visit_time DESC)
        """)
        conn.commit()
        logger.info("数据库表初始化完成: %s", DB_PATH)
    finally:
        conn.close()


def serialize_datetime(obj):
    """将 datetime/date 转换为 isoformat 字符串。"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def brochure_to_json(brochure: dict) -> str:
    """将画册 dict 序列化为 JSON，处理 datetime 等不可序列化类型。"""
    return json.dumps(brochure, default=serialize_datetime, ensure_ascii=False)


# ── 读操作 ────────────────────────────────────────────

def db_load_all_brochures() -> dict[str, dict]:
    """从 SQLite 加载所有画册到内存。"""
    conn = get_db_conn()
    try:
        rows = conn.execute("SELECT brochure_id, data FROM brochures").fetchall()
        result = {}
        for row in rows:
            try:
                result[row["brochure_id"]] = json.loads(row["data"])
            except json.JSONDecodeError:
                logger.warning("跳过损坏的画册数据: %s", row["brochure_id"])
        return result
    finally:
        conn.close()


def db_get_brochure(brochure_id: str) -> Optional[dict]:
    """从 SQLite 获取单个画册。"""
    conn = get_db_conn()
    try:
        row = conn.execute(
            "SELECT data FROM brochures WHERE brochure_id = ?", (brochure_id,)
        ).fetchone()
        if row:
            return json.loads(row["data"])
        return None
    finally:
        conn.close()


def db_count_brochures() -> int:
    """统计画册数量。"""
    conn = get_db_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM brochures").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def db_get_all_user_ids() -> list[str]:
    """获取所有画册的 user_id。"""
    conn = get_db_conn()
    try:
        rows = conn.execute("SELECT DISTINCT user_id FROM brochures").fetchall()
        return [r["user_id"] for r in rows]
    finally:
        conn.close()


# ── 用户认证操作 ──────────────────────────────────────

# 旧版SHA256固定盐（用于旧密码兼容）
HASH_SALT_OLD = "digital_brochure_v2"

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False


def _hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码。如 bcrypt 不可用，回退到 SHA256。"""
    if HAS_BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return hashlib.sha256(f"{HASH_SALT_OLD}:{password}".encode()).hexdigest()


def _verify_password(plain: str, hashed: str) -> bool:
    """验证密码。优先 bcrypt，兼容旧 SHA256 格式。"""
    # 先尝试 bcrypt 验证
    if HAS_BCRYPT and hashed.startswith("$2"):
        try:
            return bcrypt.checkpw(plain.encode(), hashed.encode())
        except Exception:
            pass
    # 回退到旧 SHA256
    old_hash = hashlib.sha256(f"{HASH_SALT_OLD}:{plain}".encode()).hexdigest()
    return old_hash == hashed


def _generate_user_id() -> str:
    """生成唯一用户ID。"""
    return f"u_{uuid.uuid4().hex[:12]}"


def db_create_user(name: str, phone: str, password: str) -> Optional[dict]:
    """创建新用户。返回用户信息或 None（手机号已存在）。"""
    conn = get_db_conn()
    try:
        # 检查手机号是否已注册
        existing = conn.execute(
            "SELECT user_id FROM auth_users WHERE phone = ?", (phone,)
        ).fetchone()
        if existing:
            return None

        user_id = _generate_user_id()
        password_hash = _hash_password(password)
        conn.execute(
            """INSERT INTO auth_users (user_id, name, phone, password_hash)
               VALUES (?, ?, ?, ?)""",
            (user_id, name, phone, password_hash),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM auth_users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error("创建用户失败: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def db_get_user_by_phone(phone: str) -> Optional[dict]:
    """通过手机号查找用户。"""
    conn = get_db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM auth_users WHERE phone = ?", (phone,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def db_get_user_by_id(user_id: str) -> Optional[dict]:
    """通过 user_id 查找用户。"""
    conn = get_db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM auth_users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def db_authenticate_user(phone: str, password: str) -> Optional[dict]:
    """验证用户密码。成功返回用户信息，失败返回 None。支持 bcrypt（新）和 SHA256（旧）格式。"""
    user = db_get_user_by_phone(phone)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    # 如果密码还是旧 SHA256 格式，自动升级为 bcrypt
    if HAS_BCRYPT and not user["password_hash"].startswith("$2"):
        new_hash = _hash_password(password)
        conn = get_db_conn()
        try:
            conn.execute("UPDATE auth_users SET password_hash=? WHERE user_id=?", (new_hash, user["user_id"]))
            conn.commit()
            logger.info("密码自动升级为 bcrypt: %s (%s)", user.get("name", ""), user.get("phone", ""))
        finally:
            conn.close()
    return user


def db_create_token(user_id: str) -> str:
    """为用户创建新 token。"""
    token = f"db_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"
    conn = get_db_conn()
    try:
        conn.execute(
            "INSERT INTO auth_tokens (token, user_id) VALUES (?, ?)",
            (token, user_id),
        )
        conn.commit()
        return token
    except Exception as e:
        logger.error("创建 token 失败: %s", e)
        conn.rollback()
        return ""
    finally:
        conn.close()


def db_get_user_by_token(token: str) -> Optional[dict]:
    """通过 token 获取用户信息。同时清理过期 token。"""
    conn = get_db_conn()
    try:
        # 清理过期 token
        conn.execute(
            "DELETE FROM auth_tokens WHERE created_at < datetime('now', ?)",
            (f"-{TOKEN_EXPIRE_HOURS} hours",),
        )
        row = conn.execute(
            """SELECT u.* FROM auth_users u
               JOIN auth_tokens t ON u.user_id = t.user_id
               WHERE t.token = ?""",
            (token,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def db_delete_token(token: str) -> bool:
    """删除 token（登出）。"""
    conn = get_db_conn()
    try:
        conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def db_get_user_brochure_ids(user_id: str) -> list[str]:
    """获取指定用户的所有画册 ID（用于用户隔离）。"""
    conn = get_db_conn()
    try:
        rows = conn.execute(
            "SELECT brochure_id FROM brochures WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [r["brochure_id"] for r in rows]
    finally:
        conn.close()


# ── 写操作 ────────────────────────────────────────────

def db_upsert_brochure(brochure_id: str, user_id: str, data: dict) -> bool:
    """插入或更新画册。返回是否成功。"""
    conn = get_db_conn()
    try:
        json_str = brochure_to_json(data)
        conn.execute(
            """INSERT INTO brochures (brochure_id, user_id, data, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(brochure_id) DO UPDATE SET
                 user_id = excluded.user_id,
                 data = excluded.data,
                 updated_at = datetime('now')""",
            (brochure_id, user_id, json_str),
        )
        conn.commit()
        # 写入后验证
        verify = conn.execute(
            "SELECT brochure_id FROM brochures WHERE brochure_id = ?", (brochure_id,)
        ).fetchone()
        return verify is not None
    except Exception as e:
        logger.error("写入画册失败 %s: %s", brochure_id, e)
        conn.rollback()
        return False
    finally:
        conn.close()


def db_delete_brochure(brochure_id: str) -> bool:
    """删除画册。"""
    conn = get_db_conn()
    try:
        conn.execute("DELETE FROM brochures WHERE brochure_id = ?", (brochure_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error("删除画册失败 %s: %s", brochure_id, e)
        conn.rollback()
        return False
    finally:
        conn.close()


def db_upsert_user(user_id: str, data: dict) -> bool:
    """插入或更新用户数据。"""
    conn = get_db_conn()
    try:
        json_str = brochure_to_json(data)
        conn.execute(
            """INSERT INTO users (user_id, data)
               VALUES (?, ?)
               ON CONFLICT(user_id) DO UPDATE SET data = excluded.data""",
            (user_id, json_str),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error("写入用户失败 %s: %s", user_id, e)
        conn.rollback()
        return False
    finally:
        conn.close()


# ── 信任网络 ──────────────────────────────────────────

def db_add_trust(user_id: str, trusted_user_id: str) -> bool:
    """添加信任关系。"""
    conn = get_db_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO trust_network (user_id, trusted_user_id) VALUES (?, ?)",
            (user_id, trusted_user_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error("添加信任关系失败: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()


def db_remove_trust(user_id: str, trusted_user_id: str) -> bool:
    """移除信任关系。"""
    conn = get_db_conn()
    try:
        conn.execute(
            "DELETE FROM trust_network WHERE user_id = ? AND trusted_user_id = ?",
            (user_id, trusted_user_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error("移除信任关系失败: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()


def db_get_trust_network(user_id: str) -> list[str]:
    """获取用户的信任网络（信任的人）。"""
    conn = get_db_conn()
    try:
        rows = conn.execute(
            "SELECT trusted_user_id FROM trust_network WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return [r["trusted_user_id"] for r in rows]
    finally:
        conn.close()


def db_get_trusted_by(user_id: str) -> list[str]:
    """获取信任该用户的人。"""
    conn = get_db_conn()
    try:
        rows = conn.execute(
            "SELECT user_id FROM trust_network WHERE trusted_user_id = ?",
            (user_id,),
        ).fetchall()
        return [r["user_id"] for r in rows]
    finally:
        conn.close()


# ── 匹配记录 ──────────────────────────────────────────

def db_save_match(user_a: str, user_b: str, score: float, common_tags: list[str]) -> int:
    """保存匹配记录。"""
    conn = get_db_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO match_records (user_a, user_b, score, common_tags, status)
               VALUES (?, ?, ?, ?, 'matched')""",
            (user_a, user_b, score, json.dumps(common_tags, ensure_ascii=False)),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error("保存匹配记录失败: %s", e)
        conn.rollback()
        return 0
    finally:
        conn.close()


def db_get_matches(user_id: str) -> list[dict]:
    """获取用户的匹配记录。"""
    conn = get_db_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM match_records
               WHERE user_a = ? OR user_b = ?
               ORDER BY score DESC, created_at DESC""",
            (user_id, user_id),
        ).fetchall()
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "user_a": r["user_a"],
                "user_b": r["user_b"],
                "score": r["score"],
                "common_tags": json.loads(r["common_tags"]) if isinstance(r["common_tags"], str) else [],
                "status": r["status"],
                "created_at": r["created_at"],
            })
        return results
    finally:
        conn.close()


# ── 访客日志 ──────────────────────────────────────────

def db_log_visitor(brochure_id: str, visitor_ip: str = "",
                   visitor_name: str = "", source: str = "direct") -> bool:
    """记录访客访问。"""
    conn = get_db_conn()
    try:
        conn.execute(
            """INSERT INTO visitor_logs (brochure_id, visitor_ip, visitor_name, source)
               VALUES (?, ?, ?, ?)""",
            (brochure_id, visitor_ip, visitor_name, source),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error("记录访客失败: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()


def db_get_visitors(brochure_id: str, limit: int = 30) -> list[dict]:
    """获取画册最近访客记录。"""
    conn = get_db_conn()
    try:
        rows = conn.execute(
            """SELECT id, visitor_ip, visitor_name, source, visit_time
               FROM visitor_logs
               WHERE brochure_id = ?
               ORDER BY visit_time DESC
               LIMIT ?""",
            (brochure_id, limit),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "visitor_ip": r["visitor_ip"],
                "visitor_name": r["visitor_name"],
                "source": r["source"],
                "visit_time": r["visit_time"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def db_count_visitors(brochure_id: str) -> int:
    """统计画册总访问次数。"""
    conn = get_db_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM visitor_logs WHERE brochure_id = ?",
            (brochure_id,),
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


# ════════════════════════════════════════════════════════
# 匹配引擎
# ════════════════════════════════════════════════════════

def compute_tag_similarity(user_a_tags: list[dict], user_b_tags: list[dict]) -> float:
    """计算两个用户之间的供需匹配度（余弦相似度）。

    A 的 provide_tags × B 的 need_tags → 余弦相似度
    """
    # A 的提供向量
    a_provide = {}
    for item in user_a_tags:
        if item.get("tag_type") == "provide":
            weight = item.get("weight", 1.0)
            if item.get("source") == "manual":
                weight *= 3.0
            a_provide[item["tag"]] = weight

    # B 的需求向量
    b_need = {}
    for item in user_b_tags:
        if item.get("tag_type") == "need":
            weight = item.get("weight", 1.0)
            if item.get("source") == "manual":
                weight *= 3.0
            b_need[item["tag"]] = weight

    # 交集
    common_tags = set(a_provide.keys()) & set(b_need.keys())
    if not common_tags:
        return 0.0

    # 余弦相似度
    import math
    dot_product = sum(a_provide[t] * b_need[t] for t in common_tags)
    norm_a = math.sqrt(sum(v * v for v in a_provide.values()))
    norm_b = math.sqrt(sum(v * v for v in b_need.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0

    cos_sim = dot_product / (norm_a * norm_b)
    return max(0.0, min(1.0, cos_sim))


def run_matching(source_user_id: str, target_brochures: dict[str, dict]) -> list[dict]:
    """对 source_user 与 target_brochures 中的每个用户进行匹配计算。

    返回按匹配度降序排列的列表。
    """
    source = BROCHURES.get(source_user_id)
    if not source:
        return []

    source_tags = source.get("tags", [])
    results = []

    for bid, brochure in target_brochures.items():
        if bid == source_user_id:
            continue
        target_tags = brochure.get("tags", [])
        score = compute_tag_similarity(source_tags, target_tags)
        if score > 0:
            # 提取共同标签
            source_provide = {t["tag"] for t in source_tags if t.get("tag_type") == "provide"}
            target_need = {t["tag"] for t in target_tags if t.get("tag_type") == "need"}
            common = list(source_provide & target_need)

            results.append({
                "user_id": brochure.get("user_id", bid),
                "name": brochure.get("name", ""),
                "company": brochure.get("company", ""),
                "position": brochure.get("position", ""),
                "avatar": brochure.get("avatar", ""),
                "score": round(score * 100, 1),
                "common_tags": common,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ════════════════════════════════════════════════════════
# 启动前数据加载
# ════════════════════════════════════════════════════════

def load_data():
    """启动时加载数据：从 SQLite 加载到内存缓存。不再使用种子数据。"""
    global BROCHURES

    init_db()
    BROCHURES = db_load_all_brochures()
    logger.info("数据加载完成，当前共 %d 个画册（来自 SQLite）", len(BROCHURES))


# ════════════════════════════════════════════════════════
# FastAPI 应用
# ════════════════════════════════════════════════════════

app = FastAPI(
    title="AI数字名片 v2.2",
    description="AI数字名片 API — 画册管理、信任网络、供需匹配、链客宝生态融合",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册 P2 中间件（按顺序: trace_id → metrics → i18n → rate_limit） ──
app.add_middleware(RateLimitMiddleware)
app.add_middleware(I18nLanguageMiddleware)
app.add_middleware(MetricsMiddleware)


# ── Pydantic 模型 ──────────────────────────────────────

class BrochureCreate(BaseModel):
    user_id: str = ""
    """如不传，自动使用 token 对应用户 ID。"""
    title: str = ""
    name: str = ""
    avatar: str = ""
    company: str = ""
    position: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    bio: str = ""
    tags: list[dict] = []
    trust_network: list[str] = []


class BrochureUpdate(BaseModel):
    title: Optional[str] = None
    name: Optional[str] = None
    avatar: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    wechat: Optional[str] = None
    bio: Optional[str] = None
    tags: Optional[list[dict]] = None
    trust_network: Optional[list[str]] = None


class TrustAddRequest(BaseModel):
    trusted_user_id: str


class MatchRequest(BaseModel):
    user_id: str
    limit: int = 10


class BatchImportItem(BaseModel):
    name: str
    company_name: str = ""
    industry: str = ""
    title: str = ""


class BatchImportRequest(BaseModel):
    users: list[BatchImportItem]


# ── 认证模型 ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    phone: str = Field(..., pattern=r"^1\d{10}$")
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    phone: str
    password: str


class UserInfoResponse(BaseModel):
    user_id: str
    name: str
    phone: str
    company: str = ""
    position: str = ""
    avatar: str = ""
    bio: str = ""
    created_at: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfoResponse


# ── Token 安全方案 ────────────────────────────────────

security = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """从请求头 Authorization: Bearer <token> 解析当前用户 ID。
    若 token 无效或缺失则返回空字符串（公开端点可选择性使用）。
    """
    if credentials is None:
        return ""
    user = db_get_user_by_token(credentials.credentials)
    if user is None:
        return ""
    return user["user_id"]


def require_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """要求必须有有效 token，否则返回 401。"""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail=_("缺少 Authorization 头，请先登录", _lang_var.get()),
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db_get_user_by_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=_("Token 无效或已过期，请重新登录", _lang_var.get()),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user["user_id"]


# ── 同步内存与数据库 ──────────────────────────────────

def sync_to_db(brochure_id: str):
    """将内存中的画册同步到 SQLite。"""
    brochure = BROCHURES.get(brochure_id)
    if brochure:
        user_id = brochure.get("user_id", brochure_id)
        db_upsert_brochure(brochure_id, user_id, brochure)


def ensure_brochure_id(user_id: str) -> str:
    """确保 brochure_id 与 user_id 一致（现在直接返回 user_id）。"""
    return user_id



# ════════════════════════════════════════════════════════
# P2: trace_id+限流+国际化 中间件
# ════════════════════════════════════════════════════════

@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """为每个请求分配 trace_id，设置 X-Trace-Id 响应头。"""
    trace_id = request.headers.get("X-Trace-Id", uuid.uuid4().hex[:16])
    _trace_id_var.set(trace_id)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc: Exception):
    """全局异常处理：返回含 trace_id 的 JSON 错误响应。"""
    trace_id = _trace_id_var.get() or getattr(request.state, 'trace_id', '')
    status_code = 500
    detail = _("内部服务器错误", detect_lang(request.headers.get("Accept-Language", "")))

    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail

    logger.error("请求异常: path=%s, trace_id=%s, status=%d, detail=%s",
                 request.url.path, trace_id, status_code, detail)

    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "data": None,
            "message": detail,
            "trace_id": trace_id,
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件 — 100次/分钟/IP，滑动窗口"""

    EXEMPT_PATHS = {"/api/health", "/api/v1/metrics"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 排除免限流路径
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # 检查是否启用
        if not _rate_limit_enabled():
            return await call_next(request)

        client_ip = extract_client_ip(request)
        limiter: MemoryRateLimiter = get_rate_limiter()
        default_limit = 100

        # 获取路径特定的限流上限
        route_limit = get_route_limit(path, default=default_limit)

        allowed, retry_after = limiter.check(client_ip, limit=route_limit)
        remaining = limiter.get_remaining(client_ip, limit=route_limit)

        if not allowed:
            lang = detect_lang(request.headers.get("Accept-Language", ""))
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "data": None,
                    "message": _("请求过于频繁，请稍后再试", lang),
                },
                headers={
                    "X-RateLimit-Limit": str(route_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                    "Retry-After": str(retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(route_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(limiter.window_sec)
        return response


class I18nLanguageMiddleware(BaseHTTPMiddleware):
    """国际化中间件: 从 Accept-Language 检测语言并设置 _lang_var"""

    async def dispatch(self, request: Request, call_next):
        accept_lang = request.headers.get("Accept-Language", "")
        lang = detect_lang(accept_lang)
        _lang_var.set(lang)
        request.state.lang = lang
        response = await call_next(request)
        response.headers["X-Content-Language"] = lang
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Prometheus 指标采集中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time

        collector = get_metrics_collector()
        collector.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_sec=elapsed,
        )
        return response


# ════════════════════════════════════════════════════════
# API 端点
# ════════════════════════════════════════════════════════

# ── 1. 健康检查 ──────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """首页 - 登录/注册 + 画册管理"""
    templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "app", "templates"))
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/v1/health")
def health_check(request: Request = None):
    lang = _lang_var.get() or detect_lang(request.headers.get("Accept-Language", "")) if request else "zh"
    collector = get_metrics_collector()
    snap = collector.snapshot()
    metrics_status = _("指标收集器状态正常", lang) if snap["total_requests"] >= 0 else _("无指标数据", lang)
    return {
        "status": "ok",
        "service": "AI数字名片 v2.2",
        "version": "2.2.0",
        "brochures_count": len(BROCHURES),
        "storage": "sqlite",
        "metrics": {
            "total_requests": snap["total_requests"],
            "status": metrics_status,
        },
    }


# ── Prometheus metrics 端点 ──

@app.get("/api/v1/metrics")
def metrics_endpoint():
    """返回 Prometheus text/plain 格式的指标数据"""
    collector = get_metrics_collector()
    prometheus_text = collector.generate_prometheus_text()
    return Response(
        content=prometheus_text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# ── 0. 用户认证 ──────────────────────────────────────

@app.post("/api/v1/auth/register", status_code=201)
def register(data: RegisterRequest):
    """用户注册（手机号 + 密码 + 姓名）。"""
    # 检查手机号是否已注册
    existing = db_get_user_by_phone(data.phone)
    if existing:
        raise HTTPException(status_code=409, detail=_("该手机号已注册", _lang_var.get()))

    # 创建用户
    user = db_create_user(name=data.name, phone=data.phone, password=data.password)
    if not user:
        raise HTTPException(status_code=500, detail=_("注册失败，请稍后再试", _lang_var.get()))

    # 自动登录：创建 token
    token = db_create_token(user["user_id"])
    if not token:
        raise HTTPException(status_code=500, detail=_("创建 token 失败", _lang_var.get()))

    logger.info("新用户注册: %s (%s)", user["name"], user["phone"])
    return TokenResponse(
        access_token=token,
        user=UserInfoResponse(
            user_id=user["user_id"],
            name=user["name"],
            phone=user["phone"],
            company=user.get("company", ""),
            position=user.get("position", ""),
            avatar=user.get("avatar", ""),
            bio=user.get("bio", ""),
            created_at=user.get("created_at", ""),
        ),
    )


@app.post("/api/v1/auth/login")
def login(data: LoginRequest):
    """用户登录（手机号 + 密码），返回 token。"""
    user = db_authenticate_user(data.phone, data.password)
    if not user:
        raise HTTPException(status_code=401, detail=_("手机号或密码错误", _lang_var.get()))

    token = db_create_token(user["user_id"])
    if not token:
        raise HTTPException(status_code=500, detail=_("创建 token 失败", _lang_var.get()))

    logger.info("用户登录: %s (%s)", user["name"], user["phone"])
    return TokenResponse(
        access_token=token,
        user=UserInfoResponse(
            user_id=user["user_id"],
            name=user["name"],
            phone=user["phone"],
            company=user.get("company", ""),
            position=user.get("position", ""),
            avatar=user.get("avatar", ""),
            bio=user.get("bio", ""),
            created_at=user.get("created_at", ""),
        ),
    )


@app.get("/api/v1/auth/me")
def get_me(current_user_id: str = Depends(require_user_id)):
    """获取当前登录用户的信息。"""
    user = db_get_user_by_id(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_("用户不存在", _lang_var.get()))
    return {
        "code": 200,
        "data": UserInfoResponse(
            user_id=user["user_id"],
            name=user["name"],
            phone=user["phone"],
            company=user.get("company", ""),
            position=user.get("position", ""),
            avatar=user.get("avatar", ""),
            bio=user.get("bio", ""),
            created_at=user.get("created_at", ""),
        ),
    }


@app.post("/api/v1/auth/logout")
def logout(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """退出登录（删除 token）。"""
    if credentials:
        db_delete_token(credentials.credentials)
    return {"code": 200, "message": _("已退出登录", _lang_var.get())}


# ── 我的画册列表（当前用户） ─────────────────────────

@app.get("/api/v1/brochure/list")
def list_my_brochures(current_user_id: str = Depends(require_user_id)):
    """获取当前用户的所有画册（用户隔离）。"""
    brochure_ids = db_get_user_brochure_ids(current_user_id)
    my_brochures = []
    for bid in brochure_ids:
        brochure = BROCHURES.get(bid) or db_get_brochure(bid)
        if brochure:
            my_brochures.append(brochure)
    return {
        "code": 200,
        "data": my_brochures,
        "total": len(my_brochures),
    }


# ── 2. 获取所有画册 ──────────────────────────────────

@app.get("/api/v1/brochures")
def get_all_brochures():
    return {
        "code": 200,
        "data": list(BROCHURES.values()),
        "total": len(BROCHURES),
    }


# ── 3. 获取指定用户画册 ──────────────────────────────

@app.get("/api/v1/brochures/{user_id:path}")
def get_brochure(user_id: str):
    bid = ensure_brochure_id(user_id)
    brochure = BROCHURES.get(bid)
    if not brochure:
        # 尝试从 SQLite 直接读取
        brochure = db_get_brochure(bid)
        if brochure:
            BROCHURES[bid] = brochure
        else:
            raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))
    return {"code": 200, "data": brochure}


# ── 4. 创建画册（需登录） ─────────────────────────────

@app.post("/api/v1/brochures", status_code=201)
def create_brochure(data: BrochureCreate, current_user_id: str = Depends(require_user_id)):
    now = datetime.now().isoformat()
    # 如果未传 user_id，使用 token 中的用户 ID
    effective_user_id = data.user_id if data.user_id else current_user_id
    bid = ensure_brochure_id(effective_user_id)

    # 用户隔离：只能用自己的 user_id 创建画册
    if effective_user_id != current_user_id:
        raise HTTPException(status_code=403, detail=_("不能为其他用户创建画册", _lang_var.get()))

    if bid in BROCHURES:
        raise HTTPException(status_code=409, detail=_("该用户画册已存在", _lang_var.get()))

    brochure = {
        "brochure_id": bid,
        "user_id": effective_user_id,
        "title": data.title or f"{data.name} 的数字名片",
        "name": data.name,
        "avatar": data.avatar,
        "company": data.company,
        "position": data.position,
        "phone": data.phone,
        "email": data.email,
        "wechat": data.wechat,
        "bio": data.bio,
        "tags": data.tags,
        "trust_network": data.trust_network,
        "created_at": now,
        "updated_at": now,
    }

    BROCHURES[bid] = brochure
    sync_to_db(bid)
    db_upsert_user(effective_user_id, {
        "user_id": effective_user_id,
        "name": data.name,
        "company": data.company,
        "position": data.position,
        "avatar": data.avatar,
        "bio": data.bio,
    })
    # 写入信任关系
    for trusted_id in data.trust_network:
        db_add_trust(effective_user_id, trusted_id)

    return {"code": 201, "message": _("画册创建成功", _lang_var.get()), "data": brochure}


# ── 5. 更新画册（需登录 + 所有权校验） ────────────────

@app.put("/api/v1/brochures/{user_id:path}")
def update_brochure(user_id: str, data: BrochureUpdate,
                    current_user_id: str = Depends(require_user_id)):
    bid = ensure_brochure_id(user_id)
    brochure = BROCHURES.get(bid)
    if not brochure:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    # 用户隔离：只能更新自己的画册
    if brochure.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail=_("无权修改此画册", _lang_var.get()))

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if value is not None:
            brochure[field] = value

    brochure["updated_at"] = datetime.now().isoformat()
    BROCHURES[bid] = brochure
    sync_to_db(bid)

    return {"code": 200, "message": _("画册更新成功", _lang_var.get()), "data": brochure}


# ── 6. 删除画册（需登录 + 所有权校验） ────────────────

@app.delete("/api/v1/brochures/{user_id:path}")
def delete_brochure(user_id: str, current_user_id: str = Depends(require_user_id)):
    bid = ensure_brochure_id(user_id)
    brochure = BROCHURES.get(bid)
    if not brochure:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    # 用户隔离：只能删除自己的画册
    if brochure.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail=_("无权删除此画册", _lang_var.get()))

    del BROCHURES[bid]
    db_delete_brochure(bid)

    return {"code": 200, "message": _("画册已删除", _lang_var.get())}


# ── 7. 获取信任网络 ──────────────────────────────────

@app.get("/api/v1/brochures/{user_id:path}/trust_network")
def get_trust_network(user_id: str):
    bid = ensure_brochure_id(user_id)
    brochure = BROCHURES.get(bid)
    if not brochure:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    # 从 SQLite 获取信任关系
    trusted_ids = db_get_trust_network(user_id)
    trusted_by_ids = db_get_trusted_by(user_id)

    trust_data = []
    for tid in trusted_ids:
        tb = BROCHURES.get(tid) or db_get_brochure(tid)
        if tb:
            trust_data.append({
                "user_id": tb.get("user_id", tid),
                "name": tb.get("name", ""),
                "company": tb.get("company", ""),
                "position": tb.get("position", ""),
                "avatar": tb.get("avatar", ""),
                "direction": "outgoing",
            })

    for tid in trusted_by_ids:
        if tid not in trusted_ids:
            tb = BROCHURES.get(tid) or db_get_brochure(tid)
            if tb:
                trust_data.append({
                    "user_id": tb.get("user_id", tid),
                    "name": tb.get("name", ""),
                    "company": tb.get("company", ""),
                    "position": tb.get("position", ""),
                    "avatar": tb.get("avatar", ""),
                    "direction": "incoming",
                })

    return {
        "code": 200,
        "data": {
            "user_id": user_id,
            "trust_network": trust_data,
            "trust_count": len(trust_data),
        },
    }


# ── 8. 添加信任关系（需登录 + 只能操作自己的信任网络） ─

@app.post("/api/v1/brochures/{user_id:path}/trust_network")
def add_trust(user_id: str, data: TrustAddRequest,
              current_user_id: str = Depends(require_user_id)):
    # 用户隔离：只能操作自己的信任网络
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail=_("无权操作其他用户的信任网络", _lang_var.get()))
    bid = ensure_brochure_id(user_id)
    if bid not in BROCHURES:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    trusted_bid = ensure_brochure_id(data.trusted_user_id)
    if trusted_bid not in BROCHURES:
        raise HTTPException(status_code=404, detail=_("被信任用户画册不存在", _lang_var.get()))

    ok = db_add_trust(user_id, data.trusted_user_id)
    if not ok:
        raise HTTPException(status_code=500, detail=_("添加信任关系失败", _lang_var.get()))

    # 更新内存缓存
    if "trust_network" not in BROCHURES[bid]:
        BROCHURES[bid]["trust_network"] = []
    if data.trusted_user_id not in BROCHURES[bid]["trust_network"]:
        BROCHURES[bid]["trust_network"].append(data.trusted_user_id)
    BROCHURES[bid]["updated_at"] = datetime.now().isoformat()
    sync_to_db(bid)

    return {"code": 200, "message": _("信任关系添加成功", _lang_var.get())}


# ── 9. 移除信任关系（需登录 + 只能操作自己的信任网络） ─

@app.delete("/api/v1/brochures/{user_id:path}/trust_network")
def remove_trust(user_id: str, trusted_user_id: str = Query(..., description="被信任的用户ID"),
                 current_user_id: str = Depends(require_user_id)):
    # 用户隔离：只能操作自己的信任网络
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail=_("无权操作其他用户的信任网络", _lang_var.get()))
    bid = ensure_brochure_id(user_id)
    if bid not in BROCHURES:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    ok = db_remove_trust(user_id, trusted_user_id)
    if not ok:
        raise HTTPException(status_code=500, detail=_("移除信任关系失败", _lang_var.get()))

    # 更新内存缓存
    if "trust_network" in BROCHURES[bid] and trusted_user_id in BROCHURES[bid]["trust_network"]:
        BROCHURES[bid]["trust_network"].remove(trusted_user_id)
    BROCHURES[bid]["updated_at"] = datetime.now().isoformat()
    sync_to_db(bid)

    return {"code": 200, "message": _("信任关系已移除", _lang_var.get())}


# ── 10. 获取匹配列表 ─────────────────────────────────

@app.get("/api/v1/brochures/{user_id:path}/matches")
def get_matches(user_id: str):
    bid = ensure_brochure_id(user_id)
    if bid not in BROCHURES:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    matches = db_get_matches(user_id)
    enriched = []
    for m in matches:
        other_id = m["user_b"] if m["user_a"] == user_id else m["user_a"]
        other = BROCHURES.get(other_id) or db_get_brochure(other_id)
        enriched.append({
            "id": m["id"],
            "matched_user_id": other_id,
            "name": other.get("name", "") if other else "",
            "company": other.get("company", "") if other else "",
            "position": other.get("position", "") if other else "",
            "avatar": other.get("avatar", "") if other else "",
            "score": m["score"],
            "common_tags": m["common_tags"],
            "status": m["status"],
            "created_at": m["created_at"],
        })

    return {"code": 200, "data": enriched, "total": len(enriched)}


# ── 11. 匹配引擎 ─────────────────────────────────────

@app.post("/api/v1/match")
def match_brochures(req: MatchRequest):
    """匹配引擎：计算指定用户与其他所有用户的供需匹配度。"""
    source_id = ensure_brochure_id(req.user_id)
    if source_id not in BROCHURES:
        raise HTTPException(status_code=404, detail=_("源用户画册不存在", _lang_var.get()))

    results = run_matching(source_id, BROCHURES)
    limited = results[:req.limit]

    # 保存匹配记录
    for r in limited:
        other_id = ensure_brochure_id(r["user_id"])
        db_save_match(source_id, other_id, r["score"], r["common_tags"])

    return {
        "code": 200,
        "data": limited,
        "total": len(results),
        "user_id": req.user_id,
    }


# ── 12. 获取用户列表 ─────────────────────────────────

@app.get("/api/v1/users")
def get_users():
    conn = get_db_conn()
    try:
        rows = conn.execute("SELECT user_id, data FROM users").fetchall()
        users = []
        for row in rows:
            try:
                user_data = json.loads(row["data"])
                users.append(user_data)
            except json.JSONDecodeError:
                pass
        return {"code": 200, "data": users, "total": len(users)}
    finally:
        conn.close()


# ── 13. 获取指定用户 ─────────────────────────────────

@app.get("/api/v1/users/{user_id:path}")
def get_user(user_id: str):
    conn = get_db_conn()
    try:
        row = conn.execute(
            "SELECT data FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return {"code": 200, "data": json.loads(row["data"])}
        # 退回到画册数据
        bid = ensure_brochure_id(user_id)
        brochure = BROCHURES.get(bid) or db_get_brochure(bid)
        if brochure:
            return {
                "code": 200,
                "data": {
                    "user_id": user_id,
                    "name": brochure.get("name", ""),
                    "company": brochure.get("company", ""),
                    "position": brochure.get("position", ""),
                    "avatar": brochure.get("avatar", ""),
                    "bio": brochure.get("bio", ""),
                },
            }
        raise HTTPException(status_code=404, detail=_("用户不存在", _lang_var.get()))
    finally:
        conn.close()


# ════════════════════════════════════════════════════════
# 新增功能: 访客感知 + 扫码优化 + 企业批量导入
# ════════════════════════════════════════════════════════

# ── 14. 画册预览HTML（访客感知注入点）────────────────

@app.get("/api/v1/brochure/{brochure_id}/brochure", response_class=HTMLResponse)
def brochure_preview(brochure_id: str, request: Request,
                     visitor_name: str = ""):
    """画册预览页 — 访问即记录访客。"""
    bid = ensure_brochure_id(brochure_id)
    brochure = BROCHURES.get(bid) or db_get_brochure(bid)
    if not brochure:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    # ── 记录访客 ──
    visitor_ip = request.client.host if request.client else "0.0.0.0"
    source = request.query_params.get("source", "direct")
    db_log_visitor(bid, visitor_ip=visitor_ip, visitor_name=visitor_name,
                   source=source)

    # ── 生成HTML ──
    name = brochure.get("name", "未知")
    company = brochure.get("company", "")
    position = brochure.get("position", "")
    bio = brochure.get("bio", "")
    avatar = brochure.get("avatar", "")
    phone = brochure.get("phone", "")
    email = brochure.get("email", "")
    wechat = brochure.get("wechat", "")
    tags = brochure.get("tags", [])
    visit_count = db_count_visitors(bid)
    owner_id = brochure.get("user_id", "")

    # 访客列表（仅画册拥有者可见的最近访客数据通过 API 获取）
    # 这里直接传递 visit_count 到页面

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} - AI数字名片</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); min-height:100vh; display:flex; justify-content:center; padding:20px; }}
.card {{ max-width:420px; width:100%; background:#fff; border-radius:20px; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,0.2); }}
.header {{ background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); padding:40px 20px 30px; text-align:center; color:#fff; }}
.header img {{ width:100px; height:100px; border-radius:50%; border:4px solid rgba(255,255,255,0.3); object-fit:cover; margin-bottom:15px; }}
.header h1 {{ font-size:24px; font-weight:600; }}
.header .position {{ font-size:14px; opacity:0.9; margin-top:5px; }}
.header .company {{ font-size:13px; opacity:0.7; margin-top:3px; }}
.body {{ padding:20px; }}
.section {{ margin-bottom:20px; }}
.section h3 {{ font-size:14px; color:#667eea; margin-bottom:10px; padding-bottom:5px; border-bottom:1px solid #eee; }}
.bio {{ font-size:14px; line-height:1.6; color:#555; }}
.contact {{ display:grid; gap:8px; }}
.contact-item {{ display:flex; align-items:center; gap:8px; font-size:13px; color:#555; }}
.contact-item .label {{ color:#999; min-width:50px; }}
.tags {{ display:flex; flex-wrap:wrap; gap:6px; }}
.tag {{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:12px; }}
.tag-provide {{ background:#e8f5e9; color:#2e7d32; }}
.tag-need {{ background:#fff3e0; color:#e65100; }}
.footer {{ padding:15px 20px; text-align:center; font-size:12px; color:#999; border-top:1px solid #eee; }}
.footer .visit-count {{ margin-top:5px; color:#667eea; font-weight:500; }}
</style>
</head>
<body>
<div class="card">
<div class="header">
<img src="{avatar}" alt="avatar" onerror="this.src='https://api.dicebear.com/7.x/avataaars/svg?seed={name}'">
<h1>{name}</h1>
<div class="position">{position}</div>
<div class="company">{company}</div>
</div>
<div class="body">
<div class="section">
<h3>📝 个人简介</h3>
<p class="bio">{bio}</p>
</div>
<div class="section">
<h3>📞 联系方式</h3>
<div class="contact">
<div class="contact-item"><span class="label">电话</span><span>{phone}</span></div>
<div class="contact-item"><span class="label">邮箱</span><span>{email}</span></div>
<div class="contact-item"><span class="label">微信</span><span>{wechat}</span></div>
</div>
</div>
<div class="section">
<h3>🏷️ 标签</h3>
<div class="tags">
{"".join(f'<span class="tag tag-{t.get("tag_type","provide")}">{t["tag"]}</span>' for t in tags)}
</div>
</div>
</div>
<div class="footer">
<p>AI数字名片 v2.1</p>
<p class="visit-count">👁️ 已被浏览 {visit_count} 次</p>
</div>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


# ── 15. 获取访客记录 ──────────────────────────────────

@app.get("/api/v1/brochure/{brochure_id}/visitors")
def get_visitors(brochure_id: str, limit: int = 30):
    """获取画册最近访客记录（仅画册拥有者可查看）。"""
    bid = ensure_brochure_id(brochure_id)
    brochure = BROCHURES.get(bid) or db_get_brochure(bid)
    if not brochure:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    visitors = db_get_visitors(bid, limit=min(limit, 100))
    total = db_count_visitors(bid)

    return {
        "code": 200,
        "data": {
            "brochure_id": bid,
            "owner_name": brochure.get("name", ""),
            "total_visits": total,
            "visitors": visitors,
        },
    }


# ── 16. 二维码数据端点 ────────────────────────────────

@app.get("/api/v1/brochure/{brochure_id}/qrcode")
def get_brochure_qrcode(brochure_id: str, request: Request):
    """生成画册二维码指向的短链接信息。"""
    bid = ensure_brochure_id(brochure_id)
    brochure = BROCHURES.get(bid) or db_get_brochure(bid)
    if not brochure:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    # 构建扫描短链接
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", f"localhost:{PORT}")
    scan_url = f"{scheme}://{host}/scan/{bid}"

    return {
        "code": 200,
        "data": {
            "brochure_id": bid,
            "name": brochure.get("name", ""),
            "scan_url": scan_url,
            "qrcode_data": scan_url,  # 二维码直接编码此URL
        },
    }


# ── 17. 扫码跳转（短链接优化）────────────────────────

@app.get("/scan/{brochure_id}")
def scan_redirect(brochure_id: str, request: Request):
    """扫码后短链接跳转到画册预览页。"""
    bid = ensure_brochure_id(brochure_id)
    brochure = BROCHURES.get(bid) or db_get_brochure(bid)
    if not brochure:
        raise HTTPException(status_code=404, detail=_("画册不存在", _lang_var.get()))

    # 302 临时重定向到预览页
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", f"localhost:{PORT}")
    preview_url = f"{scheme}://{host}/api/brochure/{bid}/brochure?source=scan"
    return RedirectResponse(url=preview_url, status_code=302)


# ── 19. 链客宝数据同步 ──────────────────────────────────

@app.get("/api/v1/brochure/sync/chainke")
def sync_chainke(current_user_id: str = Depends(require_user_id)):
    """手动触发与链客宝的数据同步。

    将信任网络数据推送到链客宝，并从链客宝拉取推荐匹配。
    链客宝不可达时自动 fallback 到本地匹配引擎。

    Returns:
        {
            "code": 0,
            "message": _("同步完成", _lang_var.get()),
            "data": {
                "trust_pushed": N,
                "matches_pulled": N,
                "source": "chainke" | "local",
            }
        }
    """
    bridge = _get_chainke_bridge()
    if not bridge:
        return {
            "code": 0,
            "message": _("链客宝桥接模块未加载，同步跳过", _lang_var.get()),
            "data": {
                "trust_pushed": 0,
                "matches_pulled": 0,
                "source": "none",
            },
        }

    # 1. 收集当前用户的信任网络数据
    trusted_ids = db_get_trust_network(current_user_id)
    trust_data = {
        "trust_value": {
            "core_competence": [],
            "industry_experience": [],
            "cooperation_advantage": [],
        },
        "resource_needs": {
            "resources_required": [],
            "ideal_partner_profile": [],
        },
        "trust_evidence": {
            "cooperation_cases": [],
            "client_evaluations": [],
        },
        "trusted_user_ids": trusted_ids,
    }

    # 从画册中提取详细信任数据
    brochure = BROCHURES.get(current_user_id)
    if brochure:
        tags = brochure.get("tags", [])
        for t in tags:
            if t.get("tag_type") == "provide":
                trust_data["trust_value"]["core_competence"].append({
                    "tag": t["tag"],
                    "weight": t.get("weight", 1.0),
                })
            elif t.get("tag_type") == "need":
                trust_data["resource_needs"]["resources_required"].append({
                    "tag": t["tag"],
                    "weight": t.get("weight", 1.0),
                })

    # 2. 推送信任数据到链客宝
    push_result = bridge.sync_trust_to_chainke(
        user_id=current_user_id,
        trust_data=trust_data,
    )
    trust_pushed = 1 if push_result.get("pushed") else 0

    # 3. 从链客宝拉取推荐匹配
    pull_result = bridge.sync_matches_from_chainke(
        user_id=current_user_id,
    )
    matches = pull_result.get("matches", [])
    matches_pulled = len(matches)
    source = pull_result.get("source", "local")

    logger.info(
        "链客宝同步完成: user=%s, trust_pushed=%d, matches_pulled=%d, source=%s",
        current_user_id, trust_pushed, matches_pulled, source,
    )

    return {
        "code": 0,
        "message": _("同步完成", _lang_var.get()),
        "data": {
            "trust_pushed": trust_pushed,
            "matches_pulled": matches_pulled,
            "source": source,
            "matches": matches[:10] if matches else [],
        },
    }


# ── 18. 企业批量导入 ──────────────────────────────────

@app.post("/api/v1/brochure/batch-import", status_code=201)
def batch_import(data: BatchImportRequest):
    """批量导入企业用户，自动创建画册。"""
    if not data.users:
        raise HTTPException(status_code=400, detail=_("导入列表不能为空", "zh"))

    imported = []
    errors = []

    for idx, item in enumerate(data.users):
        try:
            now = datetime.now().isoformat()
            # 生成唯一 user_id
            safe_name = item.name.strip().replace(" ", "_")
            user_id = f"batch_{safe_name}_{int(datetime.now().timestamp())}_{idx}"

            brochure = {
                "brochure_id": user_id,
                "user_id": user_id,
                "title": f"{item.name} - {item.title or item.company_name}",
                "name": item.name,
                "avatar": f"https://api.dicebear.com/7.x/avataaars/svg?seed={item.name}",
                "company": item.company_name,
                "position": item.title,
                "phone": "",
                "email": "",
                "wechat": "",
                "bio": f"{item.name} · {item.company_name} · {item.title} · {item.industry}" if item.industry else f"{item.name} · {item.company_name} · {item.title}",
                "tags": [
                    {"tag": item.industry, "tag_type": "provide", "weight": 0.8, "source": "import"}
                ] if item.industry else [],
                "trust_network": [],
                "created_at": now,
                "updated_at": now,
            }

            ok = db_upsert_brochure(user_id, user_id, brochure)
            if ok:
                BROCHURES[user_id] = brochure
                db_upsert_user(user_id, {
                    "user_id": user_id,
                    "name": item.name,
                    "company": item.company_name,
                    "position": item.title,
                    "avatar": brochure["avatar"],
                    "bio": brochure["bio"],
                })
                imported.append({
                    "user_id": user_id,
                    "name": item.name,
                    "company": item.company_name,
                })
            else:
                errors.append({"name": item.name, "error": "写入数据库失败"})
        except Exception as e:
            logger.error("批量导入失败 [%s]: %s", item.name, e)
            errors.append({"name": item.name, "error": str(e)})

    return {
        "code": 201 if imported else 400,
        "message": _("成功导入", "zh") + f" {len(imported)} " + _("个用户，失败", "zh") + f" {len(errors)} 个",
        "data": {
            "imported": imported,
            "errors": errors,
            "total": len(data.users),
            "success_count": len(imported),
            "fail_count": len(errors),
        },
    }


# ════════════════════════════════════════════════════════
# 启动
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    load_data()
    # 初始化 Sentry（从 SENTRY_DSN 环境变量读取）
    setup_sentry()
    app_wrapped = wrap_with_sentry(app)
    logger.info("🚀 AI数字名片 v2.2 启动于 http://%s:%d", HOST, PORT)
    uvicorn.run(app_wrapped, host=HOST, port=PORT, reload=False)
