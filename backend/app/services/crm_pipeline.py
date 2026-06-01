"""
CRM管道工作流 - 服务层
用户粘性机制实现：Pipeline阶段管理 + 跟进提醒 + 活动记录

Pipeline阶段: 新线索→已联系→洽谈中→报价中→已成交→已流失
数据存储: 独立 SQLite 数据库 (backend/data/crm.db)
"""

import logging
import os
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

PIPELINE_STAGES = [
    "new_lead",  # 新线索
    "contacted",  # 已联系
    "negotiating",  # 洽谈中
    "quotation",  # 报价中
    "closed_won",  # 已成交
    "closed_lost",  # 已流失
]

STAGE_LABELS = {
    "new_lead": "新线索",
    "contacted": "已联系",
    "negotiating": "洽谈中",
    "quotation": "报价中",
    "closed_won": "已成交",
    "closed_lost": "已流失",
}

# 数据库路径
_DATA_DIR = os.environ.get(
    "CRM_PIPELINE_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)
DB_PATH = os.path.join(_DATA_DIR, "crm.db")

# 线程锁（SQLite 写操作串行化）
_local = threading.local()


# ============================================================
# 数据库连接管理
# ============================================================


def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接（自动创建+初始化）"""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
        _init_db(conn)
    return _local.conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """上下文管理器：获取数据库连接，自动提交/回滚"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _init_db(conn: sqlite3.Connection) -> None:
    """初始化表结构"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            company         TEXT NOT NULL DEFAULT '',
            phone           TEXT DEFAULT '',
            source          TEXT DEFAULT 'manual',
            stage           TEXT NOT NULL DEFAULT 'new_lead',
            assigned_to     INTEGER DEFAULT NULL,
            assigned_name   TEXT DEFAULT '',
            next_action     TEXT DEFAULT '',
            next_action_date TEXT DEFAULT NULL,
            value           REAL DEFAULT 0.0,
            notes           TEXT DEFAULT '',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lead_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER NOT NULL,
            user_id     INTEGER DEFAULT NULL,
            user_name   TEXT DEFAULT '',
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
        CREATE INDEX IF NOT EXISTS idx_leads_assigned ON leads(assigned_to);
        CREATE INDEX IF NOT EXISTS idx_lead_notes_lead ON lead_notes(lead_id);
    """)


# ============================================================
# CRUD 操作
# ============================================================


def _now() -> str:
    return datetime.utcnow().isoformat()


def create_lead(
    name: str,
    company: str = "",
    phone: str = "",
    source: str = "manual",
    assigned_to: int | None = None,
    assigned_name: str = "",
    next_action: str = "",
    value: float = 0.0,
    notes: str = "",
) -> dict[str, Any]:
    """创建新线索（含 LLM 智能摘要）"""
    now = _now()
    with get_db() as db:
        cursor = db.execute(
            """INSERT INTO leads
               (name, company, phone, source, stage, assigned_to, assigned_name,
                next_action, value, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'new_lead', ?, ?, ?, ?, ?, ?, ?)""",
            (name, company, phone, source, assigned_to, assigned_name, next_action, value, notes, now, now),
        )
        lead_id = cursor.lastrowid

    lead = get_lead(lead_id)
    if lead:
        # 异步生成 LLM 智能摘要并追加到备注
        _enrich_lead_with_ai_summary(lead, name, company, phone, source)

    return lead if lead else get_lead(lead_id)


def get_lead(lead_id: int) -> dict[str, Any] | None:
    """获取单个线索详情（含跟进记录 + AI 摘要）"""
    with get_db() as db:
        row = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            return None
        notes = db.execute(
            "SELECT * FROM lead_notes WHERE lead_id = ? ORDER BY created_at DESC",
            (lead_id,),
        ).fetchall()
    lead = dict(row)
    lead["stage_label"] = STAGE_LABELS.get(lead["stage"], lead["stage"])
    lead["notes_list"] = [dict(n) for n in notes]

    # 提取 AI 摘要（首条带 🤖 标记的笔记）
    ai_summary = ""
    for n in lead["notes_list"]:
        content = n.get("content", "")
        if content.startswith("🤖"):
            ai_summary = content
            break
    lead["ai_summary"] = ai_summary

    return lead


def update_lead(
    lead_id: int,
    name: str | None = None,
    company: str | None = None,
    phone: str | None = None,
    source: str | None = None,
    assigned_to: int | None = None,
    assigned_name: str | None = None,
    next_action: str | None = None,
    value: float | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """更新线索字段"""
    fields = []
    values = []
    for key, val in [
        ("name", name),
        ("company", company),
        ("phone", phone),
        ("source", source),
        ("assigned_to", assigned_to),
        ("assigned_name", assigned_name),
        ("next_action", next_action),
        ("value", value),
        ("notes", notes),
    ]:
        if val is not None:
            fields.append(f"{key} = ?")
            values.append(val)

    if not fields:
        return get_lead(lead_id)

    values.append(_now())
    values.append(lead_id)
    with get_db() as db:
        db.execute(
            f"UPDATE leads SET {', '.join(fields)}, updated_at = ? WHERE id = ?",
            values,
        )
    return get_lead(lead_id)


def update_stage(lead_id: int, stage: str, user_id: int = 0, user_name: str = "") -> dict[str, Any] | None:
    """更新线索阶段（核心管道推进操作）"""
    stage = stage.lower().strip()
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"无效阶段: {stage}，有效值: {', '.join(PIPELINE_STAGES)}")

    lead = get_lead(lead_id)
    if not lead:
        return None

    old_stage = lead["stage"]
    if old_stage == stage:
        return lead

    now = _now()
    with get_db() as db:
        db.execute(
            "UPDATE leads SET stage = ?, updated_at = ? WHERE id = ?",
            (stage, now, lead_id),
        )
        # 自动记录阶段变更笔记
        from_label = STAGE_LABELS.get(old_stage, old_stage)
        to_label = STAGE_LABELS.get(stage, stage)
        db.execute(
            """INSERT INTO lead_notes (lead_id, user_id, user_name, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (lead_id, user_id, user_name, f"🔄 阶段变更: {from_label} → {to_label}", now),
        )
    return get_lead(lead_id)


def add_note(lead_id: int, content: str, user_id: int = 0, user_name: str = "") -> dict[str, Any] | None:
    """添加跟进记录"""
    lead = get_lead(lead_id)
    if not lead:
        return None

    now = _now()
    with get_db() as db:
        db.execute(
            """INSERT INTO lead_notes (lead_id, user_id, user_name, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (lead_id, user_id, user_name, content, now),
        )
        db.execute(
            "UPDATE leads SET updated_at = ? WHERE id = ?",
            (now, lead_id),
        )
    return get_lead(lead_id)


def get_pipeline() -> dict[str, Any]:
    """获取管道概览（各阶段数量 + 总额）"""
    with get_db() as db:
        rows = db.execute(
            "SELECT stage, COUNT(*) as count, COALESCE(SUM(value), 0) as total_value FROM leads GROUP BY stage"
        ).fetchall()

    stage_counts = {s: {"count": 0, "value": 0.0, "label": STAGE_LABELS.get(s, s)} for s in PIPELINE_STAGES}
    total_count = 0
    total_value = 0.0

    for row in rows:
        r = dict(row)
        s = r["stage"]
        if s in stage_counts:
            stage_counts[s]["count"] = r["count"]
            stage_counts[s]["value"] = float(r["total_value"])
            total_count += r["count"]
            total_value += float(r["total_value"])

    stages_list = [
        {
            "stage": s,
            "label": stage_counts[s]["label"],
            "count": stage_counts[s]["count"],
            "value": stage_counts[s]["value"],
        }
        for s in PIPELINE_STAGES
    ]
    return {"stages": stages_list, "total_count": total_count, "total_value": total_value}


def get_leads(
    stage: str | None = None,
    assigned_to: int | None = None,
    search: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """获取线索列表（支持筛选、搜索、分页）"""
    where_clauses = []
    params = []

    if stage:
        stage_norm = stage.lower().strip()
        if stage_norm in PIPELINE_STAGES:
            where_clauses.append("stage = ?")
            params.append(stage_norm)

    if assigned_to is not None:
        where_clauses.append("assigned_to = ?")
        params.append(assigned_to)

    if search:
        where_clauses.append("(name LIKE ? OR company LIKE ? OR phone LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with get_db() as db:
        # 总数
        count_row = db.execute(f"SELECT COUNT(*) as cnt FROM leads {where_sql}", params).fetchone()
        total = count_row["cnt"] if count_row else 0

        # 分页数据
        offset = (page - 1) * page_size
        rows = db.execute(
            f"SELECT * FROM leads {where_sql} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()

    leads = []
    for row in rows:
        lead = dict(row)
        lead["stage_label"] = STAGE_LABELS.get(lead["stage"], lead["stage"])
        leads.append(lead)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": leads,
    }


def get_my_leads(user_id: int, stage: str | None = None) -> dict[str, Any]:
    """获取分配给指定用户的线索"""
    return get_leads(stage=stage, assigned_to=user_id)


# ============================================================
# 粘性机制辅助函数
# ============================================================


def get_stale_leads(days_threshold: int = 7) -> list[dict[str, Any]]:
    """获取超过 N 天未更新的线索（用于提醒跟进）"""
    from datetime import timedelta

    cutoff = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM leads WHERE updated_at < ? AND stage NOT IN ('closed_won', 'closed_lost') ORDER BY updated_at ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_pipeline_summary_for_user(user_id: int) -> dict[str, Any]:
    """获取用户的管道摘要（首页卡片用）"""
    my = get_my_leads(user_id)
    all_pipeline = get_pipeline()

    my_stage_counts = {}
    for lead in my.get("items", []):
        s = lead["stage"]
        my_stage_counts[s] = my_stage_counts.get(s, 0) + 1

    return {
        "my_total": len(my.get("items", [])),
        "my_stages": my_stage_counts,
        "pipeline": all_pipeline,
    }


# ============================================================
# LLM 智能摘要
# ============================================================


def _enrich_lead_with_ai_summary(
    lead: dict[str, Any],
    name: str,
    company: str = "",
    phone: str = "",
    source: str = "manual",
) -> None:
    """尝试用 LLM 生成线索智能摘要并写入 lead_notes

    异常安全：任何失败只记录日志，不抛向调用方
    """
    try:
        from app.services.llm_service import summarize_lead

        lead_data = {
            "name": name,
            "company": company,
            "phone": phone,
            "source": source,
            "stage": lead.get("stage", "new_lead"),
            "notes": lead.get("notes", ""),
        }
        summary = summarize_lead(lead_data)
        if summary:
            lead_id = lead["id"]
            now = _now()
            with get_db() as db:
                db.execute(
                    """INSERT INTO lead_notes (lead_id, user_id, user_name, content, created_at)
                       VALUES (?, 0, 'AI智能助手', ?, ?)""",
                    (lead_id, f"🤖 {summary}", now),
                )
            logger.info("llm_summary_generated", extra={"lead_id": lead_id, "summary": summary[:50]})
    except Exception as e:
        logger.debug(f"LLM 智能摘要生成失败（降级）: {e}")
