"""
链客宝 — 信任评分服务层
=========================
TrustScoreService: 信任评分系统的业务逻辑层。

增强内容（迁移自旧版 trust_engine）:
  1. calculate_trust_score(user_id) — 使用三维评分算法计算总分
  2. get_trust_tier(score) — 根据分数返回等级
  3. add_behavior_points(user_id, source, points, description) — 记录行为积分
  4. create_guarantee(guarantor_id, guarantee_id) — 创建担保
  5. get_trust_network(user_id) — 获取担保网络

Usage:
  from app.services.trust_score_service import TrustScoreService
  service = TrustScoreService(db)
  score = service.calculate_trust_score("user_xxx")
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.trust_score_models import (
    BehaviorPoint,
    GUARANTEE_STATUS_ACTIVE,
    GUARANTEE_STATUS_PENDING,
    TIER_BRONZE,
    TrustGuarantee,
    TrustScore,
    GUARANTEE_STATUS_REVOKED,
    GUARANTEE_STATUS_EXPIRED,
    get_trust_tier as model_get_trust_tier,
)

# 导入新 trust_engine 特性模块
from features.trust_engine.scoring import TrustScorer, ScoreBreakdown
from features.trust_engine.tier import TrustTier

logger = logging.getLogger(__name__)

# 权重配置（与 TrustScorer 内部权重一致，供模型字段映射用）
VERIFICATION_WEIGHT = 0.3   # 认证维度权重
BEHAVIOR_WEIGHT = 0.4       # 行为维度权重
GUARANTEE_WEIGHT = 0.3      # 担保维度权重

# 单次行为积分上限
MAX_BEHAVIOR_POINTS_PER_EVENT = 100
MIN_BEHAVIOR_POINTS_PER_EVENT = -100


class TrustScoreService:
    """信任评分服务（增强版）"""

    def __init__(self, db: Session):
        self.db = db
        self.scorer = TrustScorer()

    # ------------------------------------------------------------------
    # calculate_trust_score — 从三个维度计算用户信任总分
    # ------------------------------------------------------------------

    def calculate_trust_score(self, user_id: str) -> TrustScore:
        """计算用户的综合信任评分

        使用 trust_engine.scoring 的三维评分算法:
          1. verification_points — 认证积分（资质可信度映射）
          2. behavior_points     — 行为积分（交易可信度映射）
          3. guarantee_points    — 担保积分（合规可信度映射）

        Args:
            user_id: 用户 ID

        Returns:
            TrustScore ORM 实例（已持久化）
        """
        # ── 查询或创建 TrustScore 记录 ──
        trust_score = (
            self.db.query(TrustScore)
            .filter(TrustScore.user_id == user_id)
            .first()
        )
        if trust_score is None:
            trust_score = TrustScore(
                user_id=user_id,
                total_score=0.0,
                tier=TIER_BRONZE,
                verification_points=0.0,
                behavior_points=0.0,
                guarantee_points=0.0,
            )
            self.db.add(trust_score)

        # ── 1. 认证积分 (verification_points) — 使用现有值，保持外部更新 ──
        verification = trust_score.verification_points

        # ── 2. 行为积分 (behavior_points) — 从流水表累加 ──
        behavior_row = (
            self.db.query(sa_func.coalesce(sa_func.sum(BehaviorPoint.points), 0.0))
            .filter(BehaviorPoint.user_id == user_id)
            .scalar()
        )
        behavior = float(behavior_row or 0.0)

        # ── 3. 担保积分 (guarantee_points) — 从活跃担保关系计算 ──
        now = datetime.utcnow()
        active_guarantees = (
            self.db.query(TrustGuarantee)
            .filter(
                TrustGuarantee.guarantee_id == user_id,
                TrustGuarantee.status == GUARANTEE_STATUS_ACTIVE,
                (TrustGuarantee.expired_at.is_(None))
                | (TrustGuarantee.expired_at > now),
            )
            .all()
        )
        guarantee = sum(g.weight * 50.0 for g in active_guarantees)

        # ── 使用 TrustScorer 计算综合评分 ──
        # 将三个维度分映射到 trust_engine 的评分维度
        # 使用 TrustScorer.breakdown_to_model_fields 进行双范围转换
        breakdown = self._compute_from_points(
            verification=verification,
            behavior=behavior,
            guarantee=guarantee,
        )

        total_score = breakdown.total_scaled
        tier = TrustTier(total_score).level.value

        # ── 更新 TrustScore 记录 ──
        trust_score.total_score = total_score
        trust_score.tier = tier
        trust_score.verification_points = round(verification, 2)
        trust_score.behavior_points = round(behavior, 2)
        trust_score.guarantee_points = round(guarantee, 2)
        trust_score.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(trust_score)
        return trust_score

    def _compute_from_points(
        self,
        verification: float,
        behavior: float,
        guarantee: float,
    ) -> ScoreBreakdown:
        """将三个维度的积分映射到 TrustScorer 的评分维度

        Args:
            verification: 认证积分 [0, 1000]
            behavior: 行为积分 [0, 1000]
            guarantee: 担保积分 [0, 1000]

        Returns:
            ScoreBreakdown 包含完整评分明细
        """
        # 将 0-1000 映射到 0-100 范围供 TrustScorer 内部使用
        v = TrustScorer.scale_to_100(verification)
        b = TrustScorer.scale_to_100(behavior)
        g = TrustScorer.scale_to_100(guarantee)

        # 构建子分（按权重比例将总分分配到各子指标）
        from features.trust_engine.scoring import (
            QualificationSubscores,
            TransactionSubscores,
            ComplianceSubscores,
        )

        # 认证维度映射到 QualificationSubscores
        qual = QualificationSubscores(
            cert_level=v * 0.3,        # 30% of verification
            cert_variety=v * 0.25,     # 25%
            cert_timeliness=v * 0.2,   # 20%
            id_depth=v * 0.15,         # 15%
            platform_tenure=v * 0.1,   # 10%
        )

        # 行为维度映射到 TransactionSubscores
        txn = TransactionSubscores(
            trade_count=b * 0.3,
            trade_amount=b * 0.25,
            positive_rate=b * 0.2,
            dispute_rate=b * 0.15,
            repurchase_rate=b * 0.1,
        )

        # 担保维度映射到 ComplianceSubscores
        comp = ComplianceSubscores(
            qual_completeness=g * 0.3,
            expiry_risk=g * 0.25,
            compliance_certs=g * 0.2,
            audit_report=g * 0.15,
            update_frequency=g * 0.1,
        )

        return self.scorer.calculate_breakdown(qual, txn, comp)

    # ------------------------------------------------------------------
    # calculate_trust_score_with_details — 返回详细评分明细
    # ------------------------------------------------------------------

    def calculate_trust_score_with_details(self, user_id: str) -> dict:
        """计算评分并返回详细明细（API 用）

        Returns:
            dict 包含 trust_score 记录和 breakdown 明细
        """
        trust_score = self.calculate_trust_score(user_id)
        breakdown = self._compute_from_points(
            verification=trust_score.verification_points,
            behavior=trust_score.behavior_points,
            guarantee=trust_score.guarantee_points,
        )
        tier = TrustTier(trust_score.total_score)

        return {
            "trust_score": trust_score.to_dict(),
            "breakdown": breakdown.to_dict(),
            "tier_detail": tier.to_dict(),
        }

    # ------------------------------------------------------------------
    # get_trust_tier — 根据分数返回等级
    # ------------------------------------------------------------------

    @staticmethod
    def get_trust_tier(score: float) -> str:
        """根据信任分数返回对应的信任等级

        Args:
            score: 信任分数 (0~1000)

        Returns:
            等级字符串: bronze / silver / gold / platinum
        """
        return model_get_trust_tier(score)

    # ------------------------------------------------------------------
    # add_behavior_points — 记录行为积分
    # ------------------------------------------------------------------

    def add_behavior_points(
        self,
        user_id: str,
        source: str,
        points: float,
        description: Optional[str] = None,
    ) -> BehaviorPoint:
        """记录一条行为积分流水

        Args:
            user_id:      用户 ID
            source:       积分来源 (如 trade/review/referral)
            points:       积分变动值 (正为加分，负为扣分)
            description:  变动描述（可选）

        Returns:
            BehaviorPoint ORM 实例

        Raises:
            ValueError: 积分值超出允许范围
        """
        if not (MIN_BEHAVIOR_POINTS_PER_EVENT <= points <= MAX_BEHAVIOR_POINTS_PER_EVENT):
            raise ValueError(
                f"单次积分变动必须在 {MIN_BEHAVIOR_POINTS_PER_EVENT} ~ "
                f"{MAX_BEHAVIOR_POINTS_PER_EVENT} 之间，收到: {points}"
            )

        record = BehaviorPoint(
            user_id=user_id,
            source=source,
            points=points,
            description=description,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info(
            "行为积分记录: user=%s source=%s points=%+.1f desc=%s",
            user_id, source, points, description,
        )
        return record

    # ------------------------------------------------------------------
    # update_verification_points — 更新认证积分
    # ------------------------------------------------------------------

    def update_verification_points(
        self, user_id: str, points: float
    ) -> TrustScore:
        """更新用户的认证积分

        Args:
            user_id: 用户 ID
            points:  新的认证积分值

        Returns:
            TrustScore ORM 实例
        """
        trust_score = (
            self.db.query(TrustScore)
            .filter(TrustScore.user_id == user_id)
            .first()
        )
        if trust_score is None:
            trust_score = TrustScore(
                user_id=user_id,
                total_score=0.0,
                tier=TIER_BRONZE,
                verification_points=points,
                behavior_points=0.0,
                guarantee_points=0.0,
            )
            self.db.add(trust_score)
        else:
            trust_score.verification_points = points

        self.db.commit()
        self.db.refresh(trust_score)
        return trust_score

    # ------------------------------------------------------------------
    # create_guarantee — 创建担保关系
    # ------------------------------------------------------------------

    def create_guarantee(
        self,
        guarantor_id: str,
        guarantee_id: str,
        weight: float = 1.0,
        expired_at: Optional[datetime] = None,
    ) -> TrustGuarantee:
        """创建一条担保关系

        Args:
            guarantor_id:  担保人用户 ID
            guarantee_id:  被担保人用户 ID
            weight:        担保权重 (0.0~1.0)，默认 1.0
            expired_at:    过期时间（可选，None 表示永不过期）

        Returns:
            TrustGuarantee ORM 实例

        Raises:
            ValueError: 参数校验失败
        """
        if guarantor_id == guarantee_id:
            raise ValueError("不能自己担保自己")
        if not (0.0 <= weight <= 1.0):
            raise ValueError(f"担保权重必须介于 0.0~1.0 之间，收到: {weight}")

        existing = (
            self.db.query(TrustGuarantee)
            .filter(
                TrustGuarantee.guarantor_id == guarantor_id,
                TrustGuarantee.guarantee_id == guarantee_id,
                TrustGuarantee.status.in_(
                    [GUARANTEE_STATUS_PENDING, GUARANTEE_STATUS_ACTIVE]
                ),
            )
            .first()
        )
        if existing is not None:
            raise ValueError(
                f"担保人 {guarantor_id} 与 {guarantee_id} 之间已存在活跃担保关系 (status={existing.status})"
            )

        guarantee = TrustGuarantee(
            guarantor_id=guarantor_id,
            guarantee_id=guarantee_id,
            status=GUARANTEE_STATUS_PENDING,
            weight=weight,
            expired_at=expired_at,
        )
        self.db.add(guarantee)
        self.db.commit()
        self.db.refresh(guarantee)
        logger.info(
            "担保关系创建: guarantor=%s guarantee=%s weight=%.1f",
            guarantor_id, guarantee_id, weight,
        )
        return guarantee

    # ------------------------------------------------------------------
    # confirm_guarantee — 确认担保（将 pending → active）
    # ------------------------------------------------------------------

    def confirm_guarantee(self, guarantee_id: int) -> TrustGuarantee:
        """确认担保关系，将状态从 pending 变为 active

        Args:
            guarantee_id: 担保记录 ID

        Returns:
            TrustGuarantee ORM 实例

        Raises:
            ValueError: 担保不存在或状态不是 pending
        """
        guarantee = (
            self.db.query(TrustGuarantee)
            .filter(TrustGuarantee.id == guarantee_id)
            .first()
        )
        if guarantee is None:
            raise ValueError(f"担保记录不存在: id={guarantee_id}")
        if guarantee.status != GUARANTEE_STATUS_PENDING:
            raise ValueError(
                f"担保状态不是 pending，无法确认: {guarantee.status}"
            )

        guarantee.status = GUARANTEE_STATUS_ACTIVE
        self.db.commit()
        self.db.refresh(guarantee)
        return guarantee

    # ------------------------------------------------------------------
    # revoke_guarantee — 撤销担保
    # ------------------------------------------------------------------

    def revoke_guarantee(self, guarantee_id: int) -> TrustGuarantee:
        """撤销担保关系

        Args:
            guarantee_id: 担保记录 ID

        Returns:
            TrustGuarantee ORM 实例

        Raises:
            ValueError: 担保不存在或已过期/已撤销
        """
        guarantee = (
            self.db.query(TrustGuarantee)
            .filter(TrustGuarantee.id == guarantee_id)
            .first()
        )
        if guarantee is None:
            raise ValueError(f"担保记录不存在: id={guarantee_id}")
        if guarantee.status in (GUARANTEE_STATUS_EXPIRED, GUARANTEE_STATUS_REVOKED):
            raise ValueError(f"担保已 {guarantee.status}，无法重复撤销")

        guarantee.status = GUARANTEE_STATUS_REVOKED
        self.db.commit()
        self.db.refresh(guarantee)
        return guarantee

    # ------------------------------------------------------------------
    # get_trust_network — 获取用户的担保网络
    # ------------------------------------------------------------------

    def get_trust_network(self, user_id: str) -> dict:
        """获取用户的担保网络

        Args:
            user_id: 用户 ID

        Returns:
            dict 包含:
              - as_guarantor: 作为担保人（该用户担保了谁）
              - as_guarantee: 作为被担保人（谁为该用户担保）
              - total_score:  用户的信任总分
              - tier:         信任等级
        """
        now = datetime.utcnow()

        as_guarantor = (
            self.db.query(TrustGuarantee)
            .filter(
                TrustGuarantee.guarantor_id == user_id,
                TrustGuarantee.status == GUARANTEE_STATUS_ACTIVE,
                (TrustGuarantee.expired_at.is_(None))
                | (TrustGuarantee.expired_at > now),
            )
            .all()
        )

        as_guarantee = (
            self.db.query(TrustGuarantee)
            .filter(
                TrustGuarantee.guarantee_id == user_id,
                TrustGuarantee.status == GUARANTEE_STATUS_ACTIVE,
                (TrustGuarantee.expired_at.is_(None))
                | (TrustGuarantee.expired_at > now),
            )
            .all()
        )

        trust_score = (
            self.db.query(TrustScore)
            .filter(TrustScore.user_id == user_id)
            .first()
        )

        return {
            "user_id": user_id,
            "as_guarantor": [g.to_dict() for g in as_guarantor],
            "as_guarantee": [g.to_dict() for g in as_guarantee],
            "total_score": trust_score.total_score if trust_score else 0.0,
            "tier": trust_score.tier if trust_score else TIER_BRONZE,
        }
