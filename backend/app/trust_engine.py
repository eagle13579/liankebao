"""
链客宝三层信任体系 — 信任评分引擎 (Trust Engine)
=================================================
对标 Airbnb/Salesforce Einstein 信任评分系统

评分构成:
  - verification_points (40%): 身份认证得分
  - review_avg (35%): 互评均分
  - behavior_signals (25%): 行为信号(响应率+响应速度)

信任等级:
  - bronze   (0-300)
  - silver   (301-500)
  - gold     (501-700)
  - platinum (701-1000)
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Review, TrustScore, User

logger = logging.getLogger(__name__)

# ============================================================
# 认证得分映射
# ============================================================
VERIFICATION_POINTS = {
    "email": 10,
    "phone": 20,
    "enterprise": 50,
    "wechat": 10,
}
MAX_VERIFICATION_POINTS = sum(VERIFICATION_POINTS.values())  # 90

# ============================================================
# 响应时间阈值（小时）
# ============================================================
MAX_EXPECTED_RESPONSE_HOURS = 72.0  # 超过此值视为响应极慢，得分为0


def calculate_verification_points(user: User) -> int:
    """计算身份认证得分 (满分90)"""
    points = 0
    if user.email_verified:
        points += VERIFICATION_POINTS["email"]
    if user.phone_verified:
        points += VERIFICATION_POINTS["phone"]
    if user.enterprise_verified:
        points += VERIFICATION_POINTS["enterprise"]
    if user.wechat_verified:
        points += VERIFICATION_POINTS["wechat"]
    return min(points, MAX_VERIFICATION_POINTS)


def calculate_review_score(db: Session, user_id: int) -> float:
    """
    计算互评均分 (最近20条)
    返回 0-500 范围的分数 (均分 * 100)
    """
    reviews = db.query(Review).filter(Review.reviewee_id == user_id).order_by(Review.created_at.desc()).limit(20).all()

    if not reviews:
        return 0.0

    avg_rating = sum(r.overall_rating for r in reviews) / len(reviews)
    # overall_rating 是 1-5 分，乘以100得 100-500
    return round(avg_rating * 100, 2)


def calculate_behavior_signals(
    response_rate: float,
    avg_response_time: float,
) -> float:
    """
    计算行为信号得分 (加权25%前的原始分数, 满分100)
    - response_rate: 直接映射 0-100
    - response_time: (1 - avg_time/MAX_EXPECTED) * 100, 最低0
    - 两者均值
    """
    rate_score = max(0.0, min(100.0, response_rate))

    if avg_response_time <= 0:
        time_score = 100.0
    else:
        time_score = max(0.0, 100.0 - (avg_response_time / MAX_EXPECTED_RESPONSE_HOURS) * 100)

    return round((rate_score + time_score) / 2, 2)


def calculate_total_score(
    verification_points: int,
    review_score: float,
    behavior_score: float,
) -> int:
    """
    计算信任总分 (0-1000)
      = verification_points(满分90 → 归一化到400分) * 40%
      + review_score(满分500) * 35%
      + behavior_score(满分100 → 归一化到250分) * 25%
    """
    # verification: 90点 → 最大贡献400分中的40%
    v_part = (verification_points / MAX_VERIFICATION_POINTS) * 400

    # review: 500分 → 最大贡献350分中的35%
    r_part = (review_score / 500.0) * 350

    # behavior: 100分 → 最大贡献250分中的25%
    b_part = (behavior_score / 100.0) * 250

    total = round(v_part + r_part + b_part)
    return min(1000, max(0, total))


def get_trust_tier(total_score: int) -> str:
    """根据总分返回信任等级"""
    if total_score >= 701:
        return "platinum"
    elif total_score >= 501:
        return "gold"
    elif total_score >= 301:
        return "silver"
    else:
        return "bronze"


def get_match_level(trust_tier: str) -> str:
    """
    根据信任等级决定匹配模式
    - platinum/gold → Instant Match (自动推荐+直连)
    - silver → Assisted Match (需双方确认)
    - bronze/none → Manual Match (仅展示不推荐)
    """
    tier_map = {
        "platinum": "instant",
        "gold": "instant",
        "silver": "assisted",
        "bronze": "manual",
        "none": "manual",
    }
    return tier_map.get(trust_tier, "manual")


def calculate_trust_score(db: Session, user_id: int) -> TrustScore:
    """完整计算用户信任评分并持久化"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"用户不存在: user_id={user_id}")

    # L1: 验证得分
    v_points = calculate_verification_points(user)

    # L2: 互评均分
    r_score = calculate_review_score(db, user_id)

    # 从已有的 TrustScore 中读取行为数据（如果没有则使用默认值）
    existing = db.query(TrustScore).filter(TrustScore.user_id == user_id).first()
    completed_matches = existing.completed_matches if existing else 0
    response_rate = existing.response_rate if existing else 0.0
    avg_response_time = existing.avg_response_time if existing else 0.0

    # L3: 行为信号
    b_score = calculate_behavior_signals(response_rate, avg_response_time)

    # 总分
    total = calculate_total_score(v_points, r_score, b_score)
    tier = get_trust_tier(total)

    # 更新或创建
    if existing:
        existing.total_score = total
        existing.trust_tier = tier
        existing.last_calculated_at = datetime.utcnow()
        ts = existing
    else:
        ts = TrustScore(
            user_id=user_id,
            total_score=total,
            completed_matches=completed_matches,
            response_rate=response_rate,
            avg_response_time=avg_response_time,
            trust_tier=tier,
            last_calculated_at=datetime.utcnow(),
        )
        db.add(ts)

    db.commit()
    db.refresh(ts)

    logger.info(
        "信任评分已计算",
        extra={
            "user_id": user_id,
            "total_score": total,
            "trust_tier": tier,
            "verification_points": v_points,
            "review_score": r_score,
            "behavior_score": b_score,
        },
    )

    return ts


def update_behavior_signals(
    db: Session,
    user_id: int,
    completed_matches_delta: int = 0,
    response_time_hours: float | None = None,
    responded: bool | None = None,
):
    """
    更新用户行为信号（匹配完成数、响应率、响应时间）
    在每次匹配事件中调用
    """
    ts = db.query(TrustScore).filter(TrustScore.user_id == user_id).first()
    if not ts:
        ts = TrustScore(user_id=user_id)
        db.add(ts)

    if completed_matches_delta:
        ts.completed_matches = (ts.completed_matches or 0) + completed_matches_delta

    if responded is not None and completed_matches_delta:
        # 简化的响应率计算：新响应率 = (旧完成数*旧响应率 + 响应) / 新完成数
        old_completed = (ts.completed_matches or 1) - completed_matches_delta
        if old_completed < 0:
            old_completed = 0
        old_responses = old_completed * (ts.response_rate or 0) / 100.0
        new_responses = old_responses + (1 if responded else 0)
        new_completed = ts.completed_matches or 1
        ts.response_rate = round((new_responses / new_completed) * 100, 2)

    if response_time_hours is not None:
        old_count = max(ts.completed_matches or 1, 1)
        ts.avg_response_time = round(
            ((ts.avg_response_time or 0) * (old_count - 1) + response_time_hours) / old_count,
            2,
        )

    db.commit()
