"""
交易保障服务 (Escrow Service)
=============================
对标 Alibaba Trade Assurance 的核心业务逻辑:
  - 创建交易与里程碑
  - 状态机流转
  - 付款释放（模拟）
  - 争议处理
  - 信任评分计算
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.escrow import (
    DEAL_STATUS_CANCELLED,
    DEAL_STATUS_COMPLETED,
    DEAL_STATUS_DISPUTED,
    DEAL_STATUS_FULFILLED,
    DEAL_STATUS_PAID,
    DEAL_STATUS_PENDING,
    DEAL_STATUS_REFUNDED,
    DEAL_STATUS_RESOLVED,
    DISPUTE_STATUS_INVESTIGATING,
    DISPUTE_STATUS_OPEN,
    DISPUTE_STATUS_REJECTED,
    DISPUTE_STATUS_RESOLVED,
    MILESTONE_STATUS_COMPLETED,
    MILESTONE_STATUS_FAILED,
    MILESTONE_STATUS_PENDING,
    Deal,
    Dispute,
    Milestone,
    validate_deal_transition,
)

logger = logging.getLogger(__name__)


# ============================================================
# 交易创建
# ============================================================


def create_deal(
    db: Session,
    buyer_id: int,
    seller_id: int,
    amount: float,
    title: str = "",
    description: str = "",
    milestones: list[dict[str, Any]] | None = None,
) -> Deal:
    """
    创建交易保障订单

    Args:
        db: 数据库会话
        buyer_id: 买方用户ID
        seller_id: 卖方用户ID
        amount: 交易金额
        title: 交易标题
        description: 交易描述
        milestones: 里程碑列表, 每项含 name, due_date(可选), description(可选)

    Returns:
        创建的 Deal 对象
    """
    if buyer_id == seller_id:
        raise ValueError("买方和卖方不能是同一用户")
    if amount <= 0:
        raise ValueError("交易金额必须大于0")

    deal = Deal(
        buyer_id=buyer_id,
        seller_id=seller_id,
        amount=amount,
        status=DEAL_STATUS_PENDING,
        title=title or f"交易 #{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        description=description,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(deal)
    db.flush()  # 获取 deal.id

    # 创建里程碑
    if milestones:
        for idx, ms in enumerate(milestones):
            due = None
            if ms.get("due_date"):
                if isinstance(ms["due_date"], str):
                    due = datetime.fromisoformat(ms["due_date"])
                else:
                    due = ms["due_date"]
            milestone = Milestone(
                deal_id=deal.id,
                name=ms.get("name", f"里程碑 {idx + 1}"),
                description=ms.get("description"),
                status=MILESTONE_STATUS_PENDING,
                due_date=due,
            )
            db.add(milestone)
    else:
        # 默认创建三个里程碑
        default_milestones = [
            {"name": "买方付款", "description": "买方支付交易款项"},
            {"name": "卖家履约", "description": "卖家完成交付义务"},
            {"name": "买方确认", "description": "买方确认收货并完成交易"},
        ]
        for ms in default_milestones:
            milestone = Milestone(
                deal_id=deal.id,
                name=ms["name"],
                description=ms["description"],
                status=MILESTONE_STATUS_PENDING,
            )
            db.add(milestone)

    db.commit()
    db.refresh(deal)
    logger.info(f"交易已创建: deal_id={deal.id}, buyer={buyer_id}, seller={seller_id}, amount={amount}")
    return deal


# ============================================================
# 交易状态管理
# ============================================================


def update_deal_status(db: Session, deal_id: int, new_status: str) -> Deal:
    """
    更新交易状态（含状态机校验）

    Args:
        db: 数据库会话
        deal_id: 交易ID
        new_status: 目标状态

    Returns:
        更新后的 Deal 对象
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise ValueError(f"交易不存在: deal_id={deal_id}")

    validate_deal_transition(deal.status, new_status)
    deal.status = new_status
    deal.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(deal)
    logger.info(f"交易状态已更新: deal_id={deal_id}, {deal.status} → {new_status}")
    return deal


# ============================================================
# 里程碑管理
# ============================================================


def update_milestone(
    db: Session,
    deal_id: int,
    milestone_id: int,
    status: str,
) -> Milestone:
    """
    更新里程碑状态

    Args:
        db: 数据库会话
        deal_id: 交易ID
        milestone_id: 里程碑ID
        status: 目标状态 (pending / in_progress / completed / failed)

    Returns:
        更新后的 Milestone 对象
    """
    milestone = db.query(Milestone).filter(Milestone.id == milestone_id, Milestone.deal_id == deal_id).first()
    if not milestone:
        raise ValueError(f"里程碑不存在: milestone_id={milestone_id}, deal_id={deal_id}")

    if status == MILESTONE_STATUS_COMPLETED:
        milestone.completed_at = datetime.utcnow()

    milestone.status = status
    db.commit()
    db.refresh(milestone)
    logger.info(f"里程碑已更新: deal_id={deal_id}, milestone_id={milestone_id}, status={status}")
    return milestone


def get_milestones(db: Session, deal_id: int) -> list[Milestone]:
    """获取交易的所有里程碑"""
    return db.query(Milestone).filter(Milestone.deal_id == deal_id).order_by(Milestone.id).all()


# ============================================================
# 付款释放（模拟）
# ============================================================


def release_payment(db: Session, deal_id: int, actor_id: int) -> Deal:
    """
    释放付款到卖家（模拟）
    状态机: fulfilled → completed

    Args:
        db: 数据库会话
        deal_id: 交易ID
        actor_id: 操作人ID（买方确认）

    Returns:
        更新后的 Deal 对象
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise ValueError(f"交易不存在: deal_id={deal_id}")

    if deal.status != DEAL_STATUS_FULFILLED:
        raise ValueError(f"当前状态非法: {deal.status}, 需要 fulfilled 才能释放付款")

    if deal.buyer_id != actor_id:
        raise ValueError("只有买方才能确认释放付款")

    deal.status = DEAL_STATUS_COMPLETED
    deal.updated_at = datetime.utcnow()

    # 自动完成所有未完成的里程碑
    db.query(Milestone).filter(
        Milestone.deal_id == deal_id,
        Milestone.status != MILESTONE_STATUS_COMPLETED,
    ).update(
        {
            "status": MILESTONE_STATUS_COMPLETED,
            "completed_at": datetime.utcnow(),
        }
    )

    db.commit()
    db.refresh(deal)
    logger.info(f"付款已释放: deal_id={deal_id}, amount={deal.amount}")
    return deal


# ============================================================
# 争议处理
# ============================================================


def create_dispute(
    db: Session,
    deal_id: int,
    initiator_id: int,
    reason: str,
    description: str = "",
    evidence: list[str] | None = None,
) -> Dispute:
    """
    发起争议

    Args:
        db: 数据库会话
        deal_id: 交易ID
        initiator_id: 发起人ID
        reason: 争议原因
        description: 详细描述
        evidence: 证据列表（文件URL等）

    Returns:
        创建的 Dispute 对象
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise ValueError(f"交易不存在: deal_id={deal_id}")

    if deal.status in (DEAL_STATUS_COMPLETED, DEAL_STATUS_CANCELLED, DEAL_STATUS_REFUNDED):
        raise ValueError(f"交易已终态 ({deal.status}), 不可发起争议")

    if deal.buyer_id != initiator_id and deal.seller_id != initiator_id:
        raise ValueError("只有交易参与者才能发起争议")

    # 检查是否有未关闭的争议
    existing_open = (
        db.query(Dispute)
        .filter(
            Dispute.deal_id == deal_id,
            Dispute.status.in_([DISPUTE_STATUS_OPEN, DISPUTE_STATUS_INVESTIGATING]),
        )
        .first()
    )
    if existing_open:
        raise ValueError(f"该交易已有未关闭的争议 (dispute_id={existing_open.id})")

    dispute = Dispute(
        deal_id=deal_id,
        initiator_id=initiator_id,
        reason=reason,
        description=description,
        status=DISPUTE_STATUS_OPEN,
        evidence=json.dumps(evidence or [], ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.add(dispute)

    # 更新交易状态为争议中
    if deal.status != DEAL_STATUS_DISPUTED:
        deal.status = DEAL_STATUS_DISPUTED
        deal.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(dispute)
    logger.info(f"争议已创建: dispute_id={dispute.id}, deal_id={deal_id}, initiator={initiator_id}")
    return dispute


def resolve_dispute(
    db: Session,
    dispute_id: int,
    resolution: str,
    status: str = DISPUTE_STATUS_RESOLVED,
) -> Dispute:
    """
    解决争议

    Args:
        db: 数据库会话
        dispute_id: 争议ID
        resolution: 解决说明
        status: 解决状态 (resolved / rejected)

    Returns:
        更新后的 Dispute 对象
    """
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute:
        raise ValueError(f"争议不存在: dispute_id={dispute_id}")

    dispute.status = status
    dispute.resolution = resolution
    dispute.resolved_at = datetime.utcnow()

    # 恢复交易状态
    deal = db.query(Deal).filter(Deal.id == dispute.deal_id).first()
    if deal and deal.status == DEAL_STATUS_DISPUTED:
        if status == DISPUTE_STATUS_RESOLVED:
            deal.status = DEAL_STATUS_RESOLVED
        elif status == DISPUTE_STATUS_REJECTED:
            deal.status = DEAL_STATUS_PAID  # 驳回争议，回到已付款
        deal.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(dispute)
    logger.info(f"争议已解决: dispute_id={dispute_id}, status={status}")
    return dispute


# ============================================================
# 交易取消
# ============================================================


def cancel_deal(db: Session, deal_id: int, actor_id: int) -> Deal:
    """
    取消交易

    Args:
        db: 数据库会话
        deal_id: 交易ID
        actor_id: 操作人ID

    Returns:
        更新后的 Deal 对象
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise ValueError(f"交易不存在: deal_id={deal_id}")

    if deal.status not in (DEAL_STATUS_PENDING, DEAL_STATUS_PAID):
        raise ValueError(f"当前状态 {deal.status} 不允许取消交易")

    if deal.buyer_id != actor_id and deal.seller_id != actor_id:
        raise ValueError("只有交易参与者才能取消交易")

    deal.status = DEAL_STATUS_CANCELLED
    deal.updated_at = datetime.utcnow()

    # 取消所有未完成的里程碑
    db.query(Milestone).filter(
        Milestone.deal_id == deal_id,
        Milestone.status == MILESTONE_STATUS_PENDING,
    ).update({"status": MILESTONE_STATUS_FAILED})

    db.commit()
    db.refresh(deal)
    logger.info(f"交易已取消: deal_id={deal_id}, actor={actor_id}")
    return deal


# ============================================================
# 查询
# ============================================================


def get_deal(db: Session, deal_id: int) -> Deal | None:
    """获取交易详情"""
    return db.query(Deal).filter(Deal.id == deal_id).first()


def get_deal_status(db: Session, deal_id: int) -> str | None:
    """获取交易状态"""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    return deal.status if deal else None


def list_deals(db: Session, user_id: int, status: str | None = None) -> list[Deal]:
    """
    获取用户的所有交易（作为买方或卖方）

    Args:
        db: 数据库会话
        user_id: 用户ID
        status: 可选的状态过滤

    Returns:
        交易列表
    """
    query = db.query(Deal).filter((Deal.buyer_id == user_id) | (Deal.seller_id == user_id))
    if status:
        query = query.filter(Deal.status == status)
    return query.order_by(Deal.updated_at.desc()).all()


def list_disputes(db: Session, deal_id: int | None = None) -> list[Dispute]:
    """获取争议列表，可按交易ID过滤"""
    query = db.query(Dispute)
    if deal_id is not None:
        query = query.filter(Dispute.deal_id == deal_id)
    return query.order_by(Dispute.created_at.desc()).all()


# ============================================================
# 信任评分
# ============================================================


def calculate_trust_score(db: Session, user_id: int) -> dict[str, Any]:
    """
    计算用户信任分

    评分维度 (满分100):
      - 交易完成率 (40分): completed / (completed + cancelled + refunded + disputed)
      - 纠纷率 (30分): 无纠纷=满分，纠纷越多扣分越多
      - 完成速度 (20分): 平均完成天数，越快越高
      - 交易量 (10分): 交易笔数越多越高

    Args:
        db: 数据库会话
        user_id: 用户ID

    Returns:
        dict: {score, total_deals, completed_deals, disputed_deals, ...}
    """
    # 统计用户参与的所有交易
    total_deals_count = (
        db.query(func.count(Deal.id)).filter((Deal.buyer_id == user_id) | (Deal.seller_id == user_id)).scalar() or 0
    )

    completed_count = (
        db.query(func.count(Deal.id))
        .filter(
            (Deal.buyer_id == user_id) | (Deal.seller_id == user_id),
            Deal.status == DEAL_STATUS_COMPLETED,
        )
        .scalar()
        or 0
    )

    disputed_count = (
        db.query(func.count(Deal.id))
        .filter(
            (Deal.buyer_id == user_id) | (Deal.seller_id == user_id),
            Deal.status == DEAL_STATUS_DISPUTED,
        )
        .scalar()
        or 0
    )

    # 交易已解决争议的数量
    resolved_dispute_count = (
        db.query(func.count(Dispute.id))
        .join(Deal, Dispute.deal_id == Deal.id)
        .filter(
            (Deal.buyer_id == user_id) | (Deal.seller_id == user_id),
            Dispute.status == DISPUTE_STATUS_RESOLVED,
        )
        .scalar()
        or 0
    )

    cancelled_count = (
        db.query(func.count(Deal.id))
        .filter(
            (Deal.buyer_id == user_id) | (Deal.seller_id == user_id),
            Deal.status == DEAL_STATUS_CANCELLED,
        )
        .scalar()
        or 0
    )

    refunded_count = (
        db.query(func.count(Deal.id))
        .filter(
            (Deal.buyer_id == user_id) | (Deal.seller_id == user_id),
            Deal.status == DEAL_STATUS_REFUNDED,
        )
        .scalar()
        or 0
    )

    # --- 1. 交易完成率 (40分) ---
    completed_ratio = 0.0
    performance_deals = total_deals_count  # 所有非pending的交易
    if performance_deals > 0:
        completed_ratio = completed_count / performance_deals
    completion_score = round(completed_ratio * 40, 1)

    # --- 2. 纠纷率 (30分) ---
    dispute_ratio = 0.0
    if total_deals_count > 0:
        dispute_ratio = (disputed_count + resolved_dispute_count) / total_deals_count
    # 无纠纷 = 30分, 全纠纷 = 0分
    dispute_score = round(max(0, 30 * (1 - dispute_ratio)), 1)

    # --- 3. 完成速度 (20分) ---
    speed_score = 15.0  # 默认中间值
    completed_deals = (
        db.query(Deal)
        .filter(
            (Deal.buyer_id == user_id) | (Deal.seller_id == user_id),
            Deal.status == DEAL_STATUS_COMPLETED,
            Deal.created_at.isnot(None),
            Deal.updated_at.isnot(None),
        )
        .all()
    )
    if completed_deals:
        durations = []
        for d in completed_deals:
            if d.created_at and d.updated_at:
                diff = (d.updated_at - d.created_at).days
                if diff >= 0:
                    durations.append(diff)
        if durations:
            avg_days = sum(durations) / len(durations)
            # 1天内完成=20分, 30天以上=5分, 线性插值
            if avg_days <= 1:
                speed_score = 20.0
            elif avg_days >= 30:
                speed_score = 5.0
            else:
                speed_score = round(20 - (avg_days - 1) * (15 / 29), 1)

    # --- 4. 交易量 (10分) ---
    volume_score = 0.0
    if total_deals_count >= 50:
        volume_score = 10.0
    elif total_deals_count >= 20:
        volume_score = 8.0
    elif total_deals_count >= 10:
        volume_score = 6.0
    elif total_deals_count >= 5:
        volume_score = 4.0
    elif total_deals_count >= 1:
        volume_score = 2.0

    total_score = round(completion_score + dispute_score + speed_score + volume_score, 1)

    result: dict[str, Any] = {
        "user_id": user_id,
        "trust_score": min(100.0, total_score),
        "completion_score": completion_score,
        "dispute_score": dispute_score,
        "speed_score": speed_score,
        "volume_score": volume_score,
        "total_deals": total_deals_count,
        "completed_deals": completed_count,
        "disputed_deals": disputed_count,
        "cancelled_deals": cancelled_count,
        "refunded_deals": refunded_count,
    }

    logger.info(f"信任评分已计算: user_id={user_id}, score={result['trust_score']}")
    return result


def get_trust_score(db: Session, user_id: int) -> dict[str, Any]:
    """
    获取用户信任分（对外暴露接口，简化返回）

    Args:
        db: 数据库会话
        user_id: 用户ID

    Returns:
        dict: {user_id, trust_score, total_deals, level}
    """
    detail = calculate_trust_score(db, user_id)
    score = detail["trust_score"]

    # 等级划分
    if score >= 90:
        level = "AAA"  # 卓越
    elif score >= 75:
        level = "AA"  # 优秀
    elif score >= 60:
        level = "A"  # 良好
    elif score >= 40:
        level = "B"  # 一般
    else:
        level = "C"  # 待提升

    return {
        "user_id": user_id,
        "trust_score": score,
        "level": level,
        "total_deals": detail["total_deals"],
        "completed_deals": detail["completed_deals"],
    }
