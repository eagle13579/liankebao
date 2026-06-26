"""链客宝 — 反馈服务层
========================
FeedbackService: 反馈采集管道的业务逻辑层。

职责:
  1. 提交反馈 (submit_feedback)
  2. 查询目标统计 (get_stats)
  3. 查询用户历史 (get_user_feedback)
  4. 获取最近反馈 (get_recent_feedback) — 供在线学习管道使用

使用方式:
  from app.services.feedback_service import FeedbackService
  service = FeedbackService(db)
  feedback = service.submit_feedback(...)
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, func as sa_func
from sqlalchemy.orm import Session

from app.models.feedback import Feedback, FeedbackStats


class FeedbackService:
    """用户反馈采集服务"""

    VALID_TARGET_TYPES = {"enterprise", "card", "match"}
    VALID_FEEDBACK_TYPES = {"like", "dislike", "rating", "report"}

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # submit_feedback — 提交一条反馈
    # ------------------------------------------------------------------
    def submit_feedback(
        self,
        user_id: str,
        target_type: str,
        target_id: str,
        feedback_type: str,
        score: Optional[int] = None,
        comment: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> Feedback:
        """提交用户反馈

        Args:
            user_id:      反馈用户 ID
            target_type:  目标类型 (enterprise/card/match)
            target_id:    目标 ID
            feedback_type:反馈类型 (like/dislike/rating/report)
            score:        评分 (1-5)，仅 rating 类型必填
            comment:      文本评论（可选）
            context:      上下文 JSON（可选）

        Returns:
            Feedback ORM 实例

        Raises:
            ValueError: 参数校验失败
        """
        # ── 参数校验 ──
        target_type = target_type.strip().lower()
        feedback_type = feedback_type.strip().lower()

        if target_type not in self.VALID_TARGET_TYPES:
            raise ValueError(
                f"无效 target_type: '{target_type}'. "
                f"可选: {', '.join(sorted(self.VALID_TARGET_TYPES))}"
            )
        if feedback_type not in self.VALID_FEEDBACK_TYPES:
            raise ValueError(
                f"无效 feedback_type: '{feedback_type}'. "
                f"可选: {', '.join(sorted(self.VALID_FEEDBACK_TYPES))}"
            )
        if feedback_type == "rating":
            if score is None:
                raise ValueError("rating 类型必须提供 score 参数")
            if not (1 <= score <= 5):
                raise ValueError(f"score 必须在 1-5 之间，收到: {score}")
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        if not target_id or not target_id.strip():
            raise ValueError("target_id 不能为空")

        # ── 创建记录 ──
        feedback = Feedback(
            user_id=user_id.strip(),
            target_type=target_type,
            target_id=target_id.strip(),
            feedback_type=feedback_type,
            score=score,
            comment=comment,
            context=context or {},
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    # ------------------------------------------------------------------
    # get_stats — 查询目标的反馈统计
    # ------------------------------------------------------------------
    def get_stats(self, target_type: str, target_id: str) -> FeedbackStats:
        """获取指定目标的聚合统计

        Args:
            target_type: 目标类型 (enterprise/card/match)
            target_id:   目标 ID

        Returns:
            FeedbackStats 值对象
        """
        target_type = target_type.strip().lower()

        # 聚合查询: like 计数 / dislike 计数 / rating 平均分 / 总数
        row = (
            self.db.query(
                sa_func.sum(
                    case((Feedback.feedback_type == "like", 1), else_=0)
                ).label("like_count"),
                sa_func.sum(
                    case((Feedback.feedback_type == "dislike", 1), else_=0)
                ).label("dislike_count"),
                sa_func.avg(
                    case(
                        (Feedback.feedback_type == "rating", Feedback.score),
                        else_=None,
                    )
                ).label("avg_rating"),
                sa_func.count(Feedback.id).label("total_count"),
            )
            .filter(
                Feedback.target_type == target_type,
                Feedback.target_id == target_id,
            )
            .first()
        )

        return FeedbackStats.from_query_result(target_id, row)

    # ------------------------------------------------------------------
    # get_user_feedback — 查询用户的反馈历史
    # ------------------------------------------------------------------
    def get_user_feedback(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Feedback]:
        """获取某用户的所有反馈历史（最近优先）

        Args:
            user_id: 用户 ID
            limit:   返回条数上限 (默认 50)
            offset:  分页偏移 (默认 0)

        Returns:
            Feedback 实例列表
        """
        return (
            self.db.query(Feedback)
            .filter(Feedback.user_id == user_id)
            .order_by(Feedback.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    # ------------------------------------------------------------------
    # get_recent_feedback — 获取最近 N 小时的反馈（供在线学习管道）
    # ------------------------------------------------------------------
    def get_recent_feedback(self, hours: int = 24) -> list[Feedback]:
        """获取最近指定小时内的所有反馈

        用于在线学习管道 (online learning pipeline) 定期拉取最近的
        用户反馈信号，更新推荐模型。

        Args:
            hours: 回溯小时数 (默认 24)

        Returns:
            Feedback 实例列表（按创建时间倒序）
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        return (
            self.db.query(Feedback)
            .filter(Feedback.created_at >= since)
            .order_by(Feedback.created_at.desc())
            .all()
        )
