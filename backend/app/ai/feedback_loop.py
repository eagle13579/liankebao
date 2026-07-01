"""
AI数字名片 推荐反馈闭环
======================
实现用户对推荐结果的反馈收集与模型微调。

功能:
  1. POST /api/recommend/{item_id}/feedback — 用户给推荐结果打分(👍/👎/⭐1-5)
  2. feedback 记录存储到 SQLite
  3. 定期(每 N 次反馈)触发推荐模型微调: 用户打 👍 的推荐加权, 👎 的降权
  4. 反馈数据影响后续推荐结果（通过权重调整）

架构:
  ┌─────────┐   POST  ┌──────────────┐  SQLite  ┌──────────┐
  │  前端   │ ──────→ │ feedback_loop │ ───────→ │ feedback │
  └─────────┘         │  .record()    │          │   .db    │
                      └──────┬───────┘          └──────────┘
                             │ 每 N 次触发
                             ▼
                      ┌───────────────┐
                      │ _adjust_weights │ → 更新 weight_cache
                      └───────────────┘
                             │
                             ▼
                      ┌───────────────────┐
                      │ RecommendEngine   │ → 调用 get_feedback_boost()
                      │ .personalize()    │    影响最终 score
                      └───────────────────┘
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# 数据模型
# ======================================================================


@dataclass
class FeedbackRecord:
    """单条反馈记录"""
    id: int = 0
    user_id: int = 0
    item_id: int = 0           # 被推荐用户 ID
    rating: int = 0            # 评分: 1-5 (5=最喜欢), 或 -1/0/1 映射
    source: str = ""           # 反馈来源: "recommend" | "discover" | "similar"
    feedback_type: str = ""    # "like" | "dislike" | "rating"
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class RatingStats:
    """用户对某一目标的评分统计"""
    total_feedback: int = 0
    positive_count: int = 0
    negative_count: int = 0
    avg_rating: float = 0.0
    boost_factor: float = 1.0  # 最终推荐权重乘数


# ======================================================================
# 反馈闭环引擎
# ======================================================================


class FeedbackLoop:
    """推荐反馈闭环引擎

    使用 SQLite 持久化存储反馈数据，定期触发权重调整，
    让反馈数据影响后续推荐结果。
    """

    # 微调触发阈值：每收集 N 条反馈触发一次权重更新
    ADJUST_THRESHOLD = 10

    # 权重调整幅度
    BOOST_POSITIVE = 0.15   # 👍 加权 +15%
    BOOST_NEGATIVE = -0.20  # 👎 降权 -20%
    BOOST_RATING_BASE = 0.05  # ⭐ 每 1 分 +/- 5%

    DB_DIR = "data"

    # ── 类级单例缓存 ──────────────────────────────────────────
    _instance: Optional["FeedbackLoop"] = None
    _weight_cache: dict[str, float] = {}      # "user_id:item_id" -> boost_factor
    _feedback_count: int = 0                  # 累计反馈数(用于阈值判定)

    def __new__(cls, db_path: str | None = None):
        """单例模式，确保全局共享同一个 feedback loop 状态"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str | None = None):
        if self._initialized:
            return
        self._initialized = True

        if db_path is None:
            db_path = os.path.join(self.DB_DIR, "feedback.db")
        self.db_path = db_path
        self._init_db()
        self._load_feedback_count()
        self._load_weight_cache()
        logger.info("FeedbackLoop 初始化完成: db_path=%s, total_feedback=%d",
                     self.db_path, self._feedback_count)

    # ── 数据库操作 ────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """获取 SQLite 连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    feedback_type TEXT NOT NULL DEFAULT 'rating',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_user
                    ON feedback(user_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_item
                    ON feedback(item_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_user_item
                    ON feedback(user_id, item_id);

                CREATE TABLE IF NOT EXISTS weight_cache (
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    boost_factor REAL NOT NULL DEFAULT 1.0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (user_id, item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_weight_user
                    ON weight_cache(user_id);

                CREATE TABLE IF NOT EXISTS feedback_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def _load_feedback_count(self):
        """加载累计反馈数"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM feedback_meta WHERE key = 'total_feedback'"
            ).fetchone()
            if row:
                self._feedback_count = int(row["value"])
        finally:
            conn.close()

    def _save_feedback_count(self):
        """持久化累计反馈数"""
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO feedback_meta (key, value) VALUES (?, ?)",
                ("total_feedback", str(self._feedback_count)),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_weight_cache(self):
        """从 SQLite 加载权重缓存到内存"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT user_id, item_id, boost_factor FROM weight_cache"
            ).fetchall()
            self._weight_cache = {}
            for row in rows:
                key = f"{row['user_id']}:{row['item_id']}"
                self._weight_cache[key] = row["boost_factor"]
        finally:
            conn.close()

    # ── 反馈记录 ──────────────────────────────────────────────

    def record_feedback(
        self,
        user_id: int,
        item_id: int,
        rating: int,
        source: str = "recommend",
    ) -> FeedbackRecord:
        """记录用户对推荐结果的反馈

        Args:
            user_id: 当前用户 ID
            item_id: 被推荐/被评价的用户 ID
            rating: 评分值
                1-5: 👍 星级评分 (5=非常喜欢)
                1:   👍 点赞
                -1:  👎 不喜欢
                0:   中性/跳过
            source: 来源 (recommend/discover/similar)

        Returns:
            FeedbackRecord

        Raises:
            ValueError: rating 值不合法
        """
        if rating not in (-1, 0, 1, 2, 3, 4, 5):
            raise ValueError(
                f"rating 必须为 -1, 0, 1, 2, 3, 4, 5, 收到: {rating}"
            )

        # 确定反馈类型
        if rating == 1:
            feedback_type = "like"
        elif rating == -1:
            feedback_type = "dislike"
        else:
            feedback_type = "rating"

        now = time.time()

        conn = self._get_conn()
        try:
            # UPSERT: 同一用户对同一目标的反馈覆盖更新
            existing = conn.execute(
                "SELECT id FROM feedback WHERE user_id = ? AND item_id = ?",
                (user_id, item_id),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE feedback
                       SET rating = ?, source = ?, feedback_type = ?, updated_at = ?
                       WHERE id = ?""",
                    (rating, source, feedback_type, now, existing["id"]),
                )
                record_id = existing["id"]
                logger.debug("更新反馈: user=%d item=%d rating=%d id=%d",
                             user_id, item_id, rating, record_id)
            else:
                conn.execute(
                    """INSERT INTO feedback
                       (user_id, item_id, rating, source, feedback_type, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, item_id, rating, source, feedback_type, now, now),
                )
                record_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                logger.debug("新增反馈: user=%d item=%d rating=%d id=%d",
                             user_id, item_id, rating, record_id)

            conn.commit()

            # 更新累计反馈计数器
            self._feedback_count += 1
            self._save_feedback_count()

            # 检查是否需要触发微调
            if self._feedback_count % self.ADJUST_THRESHOLD == 0:
                logger.info("累计反馈达 %d 条，触发权重调整",
                            self._feedback_count)
                self._adjust_weights()

            # ── 盖娅进化大脑：极端反馈自动摄入 ──
            if rating in (-1, 5):
                try:
                    from app.ai.gaia_evolution_brain import get_gaia_brain
                    brain = get_gaia_brain()
                    brain.ingest_feedback(
                        user_id=user_id,
                        item_id=item_id,
                        rating=rating,
                        source=source,
                        comment=f"feedback_loop:{feedback_type}:rating={rating}",
                    )
                except Exception:
                    logger.debug("[Gaia] 反馈摄入跳过（盖娅不可用）")

            return FeedbackRecord(
                id=record_id,
                user_id=user_id,
                item_id=item_id,
                rating=rating,
                source=source,
                feedback_type=feedback_type,
                created_at=now,
                updated_at=now,
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_user_feedback(self, user_id: int, limit: int = 100) -> list[FeedbackRecord]:
        """获取用户的所有反馈记录

        Args:
            user_id: 用户 ID
            limit: 最大返回数

        Returns:
            list[FeedbackRecord]
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM feedback
                   WHERE user_id = ?
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def get_item_feedback(self, item_id: int, limit: int = 100) -> list[FeedbackRecord]:
        """获取某个推荐目标的反馈

        Args:
            item_id: 被推荐用户 ID
            limit: 最大返回数

        Returns:
            list[FeedbackRecord]
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM feedback
                   WHERE item_id = ?
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (item_id, limit),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def get_user_item_stats(self, user_id: int, item_id: int) -> RatingStats:
        """获取用户对某个推荐目标的评分统计

        Args:
            user_id: 用户 ID
            item_id: 被推荐用户 ID

        Returns:
            RatingStats
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT
                      COUNT(*) as total,
                      SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) as positive,
                      SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) as negative,
                      AVG(ABS(rating)) as avg_rating
                   FROM feedback
                   WHERE user_id = ? AND item_id = ?""",
                (user_id, item_id),
            ).fetchone()

            if not row or row["total"] == 0:
                return RatingStats()

            boost = self.get_feedback_boost(user_id, item_id)
            return RatingStats(
                total_feedback=row["total"],
                positive_count=row["positive"] or 0,
                negative_count=row["negative"] or 0,
                avg_rating=round(row["avg_rating"] or 0.0, 2),
                boost_factor=boost,
            )
        finally:
            conn.close()

    # ── 权重计算（反馈 → 推荐权重）───────────────────────────

    def get_feedback_boost(self, user_id: int, item_id: int) -> float:
        """获取反馈权重提升系数

        从内存缓存中读取，避免每次查询 SQLite。
        返回 [0.6, 1.5] 范围的值，用于调整推荐分数。

        Args:
            user_id: 当前用户 ID
            item_id: 被推荐用户 ID

        Returns:
            float: 权重乘数
        """
        key = f"{user_id}:{item_id}"
        return self._weight_cache.get(key, 1.0)

    def _adjust_weights(self):
        """反馈驱动权重微调

        遍历所有反馈记录，为每个 user-item 对计算 boost_factor：
          - 正面反馈 (rating > 0): 加权
          - 负面反馈 (rating < 0): 降权
          - ⭐ 评分: 按分数线性调整

        公式:
          boost = 1.0
            + (positive_count × BOOST_POSITIVE)
            + (negative_count × BOOST_NEGATIVE)
            + (avg_rating - 3) × BOOST_RATING_BASE
          clamp to [0.6, 1.5]
        """
        conn = self._get_conn()
        try:
            # 读取所有用户-条目级别的反馈统计
            rows = conn.execute(
                """SELECT
                      user_id,
                      item_id,
                      COUNT(*) as total,
                      SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) as positive,
                      SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) as negative,
                      AVG(ABS(rating)) as avg_rating
                   FROM feedback
                   GROUP BY user_id, item_id"""
            ).fetchall()

            now = time.time()
            updated_count = 0

            for row in rows:
                uid = row["user_id"]
                iid = row["item_id"]
                pos = row["positive"] or 0
                neg = row["negative"] or 0
                avg_r = row["avg_rating"] or 0.0

                # 计算 boost factor
                boost = 1.0
                boost += pos * self.BOOST_POSITIVE
                boost += neg * self.BOOST_NEGATIVE
                boost += (avg_r - 3.0) * self.BOOST_RATING_BASE

                # 限制范围 [0.6, 1.5]
                boost = max(0.6, min(1.5, boost))

                # 更新数据库
                conn.execute(
                    """INSERT OR REPLACE INTO weight_cache
                       (user_id, item_id, boost_factor, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (uid, iid, boost, now),
                )

                # 更新内存缓存
                key = f"{uid}:{iid}"
                self._weight_cache[key] = boost
                updated_count += 1

            conn.commit()
            logger.info("权重微调完成: 更新 %d 条记录", updated_count)

        except Exception as e:
            conn.rollback()
            logger.error("权重微调失败: %s", e, exc_info=True)
        finally:
            conn.close()

    def trigger_adjustment(self) -> int:
        """手动触发权重调整

        Returns:
            int: 更新的权重记录数
        """
        old_count = len(self._weight_cache)
        self._adjust_weights()
        new_count = len(self._weight_cache)
        logger.info("手动触发权重调整: 缓存 %d → %d 条", old_count, new_count)
        return new_count - old_count

    # ── 统计信息 ──────────────────────────────────────────────

    def get_global_stats(self) -> dict[str, Any]:
        """获取全局反馈统计"""
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM feedback").fetchone()["c"]
            positive = conn.execute(
                "SELECT COUNT(*) as c FROM feedback WHERE rating > 0"
            ).fetchone()["c"]
            negative = conn.execute(
                "SELECT COUNT(*) as c FROM feedback WHERE rating < 0"
            ).fetchone()["c"]
            weight_count = conn.execute(
                "SELECT COUNT(*) as c FROM weight_cache"
            ).fetchone()["c"]
            user_count = conn.execute(
                "SELECT COUNT(DISTINCT user_id) as c FROM feedback"
            ).fetchone()["c"]

            return {
                "total_feedback": total,
                "positive_feedback": positive,
                "negative_feedback": negative,
                "unique_users": user_count,
                "weight_cache_entries": weight_count,
                "adjust_threshold": self.ADJUST_THRESHOLD,
            }
        finally:
            conn.close()

    # ── 工具方法 ──────────────────────────────────────────────

    def _row_to_record(self, row: sqlite3.Row) -> FeedbackRecord:
        return FeedbackRecord(
            id=row["id"],
            user_id=row["user_id"],
            item_id=row["item_id"],
            rating=row["rating"],
            source=row["source"],
            feedback_type=row["feedback_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ======================================================================
# 快捷函数：用于 RecommendEngine 集成
# ======================================================================

_engine: FeedbackLoop | None = None


def get_feedback_loop(db_path: str | None = None) -> FeedbackLoop:
    """获取全局 FeedbackLoop 单例"""
    global _engine
    if _engine is None:
        _engine = FeedbackLoop(db_path)
    return _engine


def apply_feedback_boost(
    user_id: int,
    candidate_id: int,
    base_score: float,
) -> float:
    """应用反馈权重提升到推荐分数

    被 RecommendEngine 调用的快捷集成函数。

    Args:
        user_id: 当前用户 ID
        candidate_id: 候选推荐用户 ID
        base_score: 原始推荐分数

    Returns:
        float: 调整后的分数
    """
    loop = get_feedback_loop()
    boost = loop.get_feedback_boost(user_id, candidate_id)
    return base_score * boost
