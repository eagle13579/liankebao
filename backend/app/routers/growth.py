"""增长引擎：邀请/推荐/分享机制，独立 SQLite 数据库"""

import logging
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

# ===== 独立数据库配置 =====
_GROWTH_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
_GROWTH_DB_PATH = os.path.join(_GROWTH_DB_DIR, "growth.db")

os.makedirs(_GROWTH_DB_DIR, exist_ok=True)

# 邀请码有效期（天）
INVITE_CODE_EXPIRE_DAYS = 30
# 每个用户接受邀请获得的奖励积分
ACCEPT_REWARD_POINTS = 100
# 邀请人获得的奖励积分
INVITER_REWARD_POINTS = 50

router = APIRouter(prefix="/api/growth", tags=["增长引擎"])


# ===== 数据模型 =====


class InviteCreateRequest(BaseModel):
    """创建邀请链接请求"""

    message: str = ""


class InviteCreateResponse(BaseModel):
    code: int
    message: str
    data: dict


class InviteItem(BaseModel):
    code: str
    inviter_id: int
    inviter_name: str
    message: str
    invite_url: str
    accepted: bool
    accepted_by: int | None = None
    accepted_name: str | None = None
    accepted_at: str | None = None
    reward_earned: int
    created_at: str


class InviteListResponse(BaseModel):
    code: int
    message: str
    data: dict


class InviteDetailResponse(BaseModel):
    code: int
    message: str
    data: InviteItem | None = None


class AcceptInviteRequest(BaseModel):
    code: str


class StatsResponse(BaseModel):
    code: int
    message: str
    data: dict


# ===== 数据库初始化 =====


def get_growth_db():
    """获取增长引擎数据库连接（每次请求独立连接，自动关闭）"""
    conn = sqlite3.connect(_GROWTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_growth_db():
    """初始化增长引擎数据库表"""
    conn = sqlite3.connect(_GROWTH_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS invites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL UNIQUE,
            inviter_id  INTEGER NOT NULL,
            inviter_name TEXT NOT NULL DEFAULT '',
            message     TEXT NOT NULL DEFAULT '',
            accepted    INTEGER NOT NULL DEFAULT 0,
            accepted_by INTEGER,
            accepted_name TEXT DEFAULT '',
            accepted_at TEXT,
            reward_earned INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rewards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            points      INTEGER NOT NULL DEFAULT 0,
            source      TEXT NOT NULL DEFAULT 'invite',
            source_code TEXT DEFAULT '',
            created_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_invites_code ON invites(code);
        CREATE INDEX IF NOT EXISTS idx_invites_inviter ON invites(inviter_id);
        CREATE INDEX IF NOT EXISTS idx_invites_accepted_by ON invites(accepted_by);
        CREATE INDEX IF NOT EXISTS idx_rewards_user ON rewards(user_id);
    """)

    conn.commit()
    conn.close()
    logger.info(f"增长引擎数据库已初始化: {_GROWTH_DB_PATH}")


# ===== 工具函数 =====


def _generate_invite_code() -> str:
    """生成唯一邀请码（8位字母数字）"""
    return secrets.token_hex(4)  # 8个字符


def _build_invite_url(code: str) -> str:
    """构建邀请链接"""
    base_url = os.environ.get("FRONTEND_URL", "https://www.go-aiport.com")
    return f"{base_url}/invite/{code}"


# ===== API 路由 =====


@router.post("/invite", response_model=InviteCreateResponse)
def create_invite(
    req: InviteCreateRequest,
    db=Depends(get_growth_db),
    current_user: User = Depends(get_current_user),
):
    """创建邀请链接"""
    code = _generate_invite_code()
    now = datetime.now(UTC).isoformat()
    expires_at = (datetime.now(UTC) + timedelta(days=INVITE_CODE_EXPIRE_DAYS)).isoformat()
    invite_url = _build_invite_url(code)
    inviter_name = current_user.display_name or current_user.username or f"用户{current_user.id}"

    try:
        db.execute(
            """INSERT INTO invites (code, inviter_id, inviter_name, message, accepted, reward_earned, created_at, expires_at)
               VALUES (?, ?, ?, ?, 0, 0, ?, ?)""",
            (code, current_user.id, inviter_name, req.message, now, expires_at),
        )
        db.commit()
    except sqlite3.IntegrityError:
        # 极小概率冲突，重试一次
        code = _generate_invite_code()
        invite_url = _build_invite_url(code)
        db.execute(
            """INSERT INTO invites (code, inviter_id, inviter_name, message, accepted, reward_earned, created_at, expires_at)
               VALUES (?, ?, ?, ?, 0, 0, ?, ?)""",
            (code, current_user.id, inviter_name, req.message, now, expires_at),
        )
        db.commit()

    logger.info(f"用户 {current_user.id} 创建邀请链接: {code}")
    return {
        "code": 200,
        "message": "邀请链接创建成功",
        "data": {
            "code": code,
            "invite_url": invite_url,
            "expires_at": expires_at,
        },
    }


@router.get("/invites", response_model=InviteListResponse)
def list_invites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_growth_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的邀请列表"""
    offset = (page - 1) * page_size

    # 总数
    total_row = db.execute(
        "SELECT COUNT(*) as cnt FROM invites WHERE inviter_id = ?",
        (current_user.id,),
    ).fetchone()
    total = total_row["cnt"] if total_row else 0

    # 列表
    rows = db.execute(
        """SELECT code, inviter_id, inviter_name, message, accepted,
                  accepted_by, accepted_name, accepted_at, reward_earned, created_at
           FROM invites
           WHERE inviter_id = ?
           ORDER BY created_at DESC
           LIMIT ? OFFSET ?""",
        (current_user.id, page_size, offset),
    ).fetchall()

    items = []
    for r in rows:
        items.append(
            {
                "code": r["code"],
                "inviter_id": r["inviter_id"],
                "inviter_name": r["inviter_name"],
                "message": r["message"],
                "invite_url": _build_invite_url(r["code"]),
                "accepted": bool(r["accepted"]),
                "accepted_by": r["accepted_by"],
                "accepted_name": r["accepted_name"],
                "accepted_at": r["accepted_at"],
                "reward_earned": r["reward_earned"],
                "created_at": r["created_at"],
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        },
    }


@router.get("/invites/{code}", response_model=InviteDetailResponse)
def get_invite(
    code: str,
    db=Depends(get_growth_db),
):
    """查看邀请详情（无需登录，供落地页使用）"""
    row = db.execute(
        """SELECT code, inviter_id, inviter_name, message, accepted,
                  accepted_by, accepted_name, accepted_at, reward_earned, created_at
           FROM invites WHERE code = ?""",
        (code,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="邀请码不存在或已过期")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "code": row["code"],
            "inviter_id": row["inviter_id"],
            "inviter_name": row["inviter_name"],
            "message": row["message"],
            "invite_url": _build_invite_url(row["code"]),
            "accepted": bool(row["accepted"]),
            "accepted_by": row["accepted_by"],
            "accepted_name": row["accepted_name"],
            "accepted_at": row["accepted_at"],
            "reward_earned": row["reward_earned"],
            "created_at": row["created_at"],
        },
    }


@router.post("/invites/accept", response_model=InviteCreateResponse)
def accept_invite(
    req: AcceptInviteRequest,
    db=Depends(get_growth_db),
    current_user: User = Depends(get_current_user),
):
    """接受邀请（当前用户使用某个邀请码）"""
    code = req.code.strip()
    row = db.execute(
        "SELECT id, inviter_id, accepted FROM invites WHERE code = ?",
        (code,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    if row["accepted"]:
        raise HTTPException(status_code=400, detail="该邀请已被使用")

    # 不能接受自己的邀请
    if row["inviter_id"] == current_user.id:
        raise HTTPException(status_code=400, detail="不能接受自己的邀请")

    now = datetime.now(UTC).isoformat()
    accepted_name = current_user.display_name or current_user.username or f"用户{current_user.id}"

    # 更新邀请记录
    db.execute(
        """UPDATE invites SET accepted = 1, accepted_by = ?, accepted_name = ?, accepted_at = ?, reward_earned = ?
           WHERE code = ?""",
        (current_user.id, accepted_name, now, INVITER_REWARD_POINTS, code),
    )

    # 给邀请人增加奖励
    db.execute(
        "INSERT INTO rewards (user_id, points, source, source_code, created_at) VALUES (?, ?, 'invite_reward', ?, ?)",
        (row["inviter_id"], INVITER_REWARD_POINTS, code, now),
    )

    # 给接受者增加奖励
    db.execute(
        "INSERT INTO rewards (user_id, points, source, source_code, created_at) VALUES (?, ?, 'accept_reward', ?, ?)",
        (current_user.id, ACCEPT_REWARD_POINTS, code, now),
    )

    db.commit()

    logger.info(
        f"用户 {current_user.id} 接受了邀请 {code}，邀请人 {row['inviter_id']} 获得 {INVITER_REWARD_POINTS} 积分"
    )

    return {
        "code": 200,
        "message": "接受邀请成功",
        "data": {
            "reward": ACCEPT_REWARD_POINTS,
            "inviter_name": row["inviter_name"] if "inviter_name" in row.keys() else "",
        },
    }


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    db=Depends(get_growth_db),
    current_user: User = Depends(get_current_user),
):
    """邀请统计：已邀请人数、已注册人数、累计奖励"""
    # 已邀请（创建的邀请总数）
    invited_row = db.execute(
        "SELECT COUNT(*) as cnt FROM invites WHERE inviter_id = ?",
        (current_user.id,),
    ).fetchone()
    total_invited = invited_row["cnt"] if invited_row else 0

    # 已注册（已接受的邀请数）
    accepted_row = db.execute(
        "SELECT COUNT(*) as cnt FROM invites WHERE inviter_id = ? AND accepted = 1",
        (current_user.id,),
    ).fetchone()
    total_accepted = accepted_row["cnt"] if accepted_row else 0

    # 累计奖励
    reward_row = db.execute(
        "SELECT COALESCE(SUM(points), 0) as total FROM rewards WHERE user_id = ?",
        (current_user.id,),
    ).fetchone()
    total_reward = reward_row["total"] if reward_row else 0

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_invited": total_invited,
            "total_accepted": total_accepted,
            "total_reward": total_reward,
        },
    }
