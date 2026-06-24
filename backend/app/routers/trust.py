"""
链客宝三层信任体系 — API 路由
================================
L1: 身份认证层 - POST /api/trust/verify, PUT /api/trust/verify/{id}, GET /api/trust/score/{user_id}
L2: 交互信誉层 - POST /api/trust/review, GET /api/trust/reviews/{user_id}
L3: 行为信号层 - GET /api/trust/score/{user_id}, GET /api/trust/match-level/{user_id}
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_admin, get_current_user
from app.database import get_db
from app.models import Review, TrustScore, User, VerificationRequest
from app.trust_engine import (
    calculate_trust_score,
    get_match_level,
    get_trust_tier,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trust", tags=["信任体系"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================


class ReviewCreate(BaseModel):
    reviewee_id: int = Field(..., description="被评价用户ID")
    match_id: int | None = Field(None, description="关联匹配事件ID")
    response_speed: int = Field(5, ge=1, le=5, description="响应速度 1-5")
    cooperation_willingness: int = Field(5, ge=1, le=5, description="合作意愿 1-5")
    info_accuracy: int = Field(5, ge=1, le=5, description="信息准确度 1-5")
    comment: str | None = Field(None, max_length=500, description="评价内容")


class VerificationCreate(BaseModel):
    type: str = Field(..., pattern=r"^(email|phone|enterprise)$", description="认证类型: email/phone/enterprise")
    evidence: str | None = Field(None, description="认证证明材料(JSON)")


class VerificationReview(BaseModel):
    status: str = Field(..., pattern=r"^(verified|rejected)$", description="审核结果: verified/rejected")


# ============================================================
# L2 — 交互信誉层 API
# ============================================================


@router.post("/review", summary="提交互评", description="用户对匹配对象进行评价（L2交互信誉层）")
def create_review(
    data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 不能自我评价
    if data.reviewee_id == current_user.id:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "不能给自己评价"},
        )

    # 验证被评价用户存在
    reviewee = db.query(User).filter(User.id == data.reviewee_id).first()
    if not reviewee:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "被评价用户不存在"},
        )

    # 检查是否已评价过同一 match（防止刷评）
    existing = (
        db.query(Review)
        .filter(
            Review.reviewer_id == current_user.id,
            Review.reviewee_id == data.reviewee_id,
            Review.match_id == data.match_id,
        )
        .first()
    )
    if existing:
        return JSONResponse(
            status_code=409,
            content={"code": 409, "message": "您已评价过本次匹配"},
        )

    # 计算综合评分
    overall = round(
        (data.response_speed + data.cooperation_willingness + data.info_accuracy) / 3.0,
        2,
    )

    review = Review(
        reviewer_id=current_user.id,
        reviewee_id=data.reviewee_id,
        match_id=data.match_id,
        response_speed=data.response_speed,
        cooperation_willingness=data.cooperation_willingness,
        info_accuracy=data.info_accuracy,
        overall_rating=overall,
        comment=data.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # 触发信任评分重新计算
    try:
        calculate_trust_score(db, data.reviewee_id)
    except Exception as e:
        logger.warning(f"信任评分重算失败: {e}")

    return {
        "code": 200,
        "message": "评价提交成功",
        "data": {
            "id": review.id,
            "overall_rating": overall,
        },
    }


@router.get(
    "/reviews/{user_id}", summary="获取用户评价列表", description="获取某用户收到的所有评价（支持分页和评分筛选）"
)
def list_reviews(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_rating: float | None = Query(None, ge=1.0, le=5.0, description="最低评分筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 验证用户存在
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "用户不存在"},
        )

    query = db.query(Review).filter(Review.reviewee_id == user_id)

    if min_rating is not None:
        query = query.filter(Review.overall_rating >= min_rating)

    total = query.count()
    reviews = query.order_by(Review.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # 构建结果（附带评价人名称信息）
    items = []
    for r in reviews:
        reviewer = db.query(User).filter(User.id == r.reviewer_id).first()
        items.append(
            {
                "id": r.id,
                "reviewer_id": r.reviewer_id,
                "reviewer_name": reviewer.name if reviewer else "未知用户",
                "reviewer_avatar": reviewer.avatar if reviewer else None,
                "match_id": r.match_id,
                "response_speed": r.response_speed,
                "cooperation_willingness": r.cooperation_willingness,
                "info_accuracy": r.info_accuracy,
                "overall_rating": r.overall_rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
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


# ============================================================
# L1 — 身份认证 API
# ============================================================


@router.post("/verify", summary="提交认证申请", description="用户提交身份认证申请（L1身份认证层）")
def submit_verification(
    data: VerificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 检查是否有待审核的同类型申请
    existing_pending = (
        db.query(VerificationRequest)
        .filter(
            VerificationRequest.user_id == current_user.id,
            VerificationRequest.type == data.type,
            VerificationRequest.status == "pending",
        )
        .first()
    )
    if existing_pending:
        return JSONResponse(
            status_code=409,
            content={"code": 409, "message": f"您已有待审核的{data.type}认证申请"},
        )

    # 检查是否已认证通过
    already_verified = False
    if data.type == "email" and current_user.email_verified:
        already_verified = True
    elif data.type == "phone" and current_user.phone_verified:
        already_verified = True
    elif data.type == "enterprise" and current_user.enterprise_verified:
        already_verified = True

    if already_verified:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": f"您的{data.type}已认证通过"},
        )

    req = VerificationRequest(
        user_id=current_user.id,
        type=data.type,
        status="pending",
        evidence=data.evidence,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return {
        "code": 200,
        "message": "认证申请已提交，等待审核",
        "data": {
            "id": req.id,
            "type": req.type,
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        },
    }


@router.put("/verify/{id}", summary="管理员审核认证", description="管理员审核用户认证申请（需要admin权限）")
def review_verification(
    id: int,
    data: VerificationReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    req = db.query(VerificationRequest).filter(VerificationRequest.id == id).first()
    if not req:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "认证申请不存在"},
        )

    if req.status != "pending":
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": f"该申请已处理，当前状态: {req.status}"},
        )

    req.status = data.status
    if data.status == "verified":
        req.verified_at = datetime.utcnow()
        # 更新用户认证状态
        user = db.query(User).filter(User.id == req.user_id).first()
        if user:
            if req.type == "email":
                user.email_verified = True
            elif req.type == "phone":
                user.phone_verified = True
            elif req.type == "enterprise":
                user.enterprise_verified = True

            # 计算最新认证层级
            _update_verification_tier(user)

            db.flush()
            # 触发信任评分重算
            try:
                calculate_trust_score(db, req.user_id)
            except Exception as e:
                logger.warning(f"信任评分重算失败: {e}")

    db.commit()
    db.refresh(req)

    return {
        "code": 200,
        "message": "认证申请已审核",
        "data": {
            "id": req.id,
            "status": req.status,
            "verified_at": req.verified_at.isoformat() if req.verified_at else None,
        },
    }


def _update_verification_tier(user: User):
    """根据验证状态计算认证层级"""
    verified_count = sum(
        [
            bool(user.email_verified),
            bool(user.phone_verified),
            bool(user.enterprise_verified),
            bool(user.wechat_verified),
        ]
    )
    if user.enterprise_verified and verified_count >= 3:
        user.verification_tier = "verified"
    elif verified_count >= 2:
        user.verification_tier = "standard"
    elif verified_count >= 1:
        user.verification_tier = "basic"
    else:
        user.verification_tier = "none"


# ============================================================
# L3 — 信任评分 & 匹配级别 API
# ============================================================


@router.get("/score/{user_id}", summary="获取信任评分详情", description="获取用户信任评分详情（L3行为信号层）")
def get_trust_score(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "用户不存在"},
        )

    ts = db.query(TrustScore).filter(TrustScore.user_id == user_id).first()

    if not ts:
        # 首次查询，计算评分
        try:
            ts = calculate_trust_score(db, user_id)
        except Exception as e:
            logger.error(f"信任评分计算失败: {e}")
            return JSONResponse(
                status_code=500,
                content={"code": 500, "message": "信任评分计算失败"},
            )

    # 查询最近评价统计
    review_stats = _get_review_stats(db, user_id)

    # 计算各维度得分明细
    from app.trust_engine import (
        MAX_VERIFICATION_POINTS,
        calculate_behavior_signals,
        calculate_review_score,
        calculate_verification_points,
    )

    v_points = calculate_verification_points(user)
    r_score = calculate_review_score(db, user_id)
    b_score = calculate_behavior_signals(ts.response_rate, ts.avg_response_time)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "user_id": user_id,
            "user_name": user.name,
            "total_score": ts.total_score,
            "trust_tier": ts.trust_tier,
            "verification_tier": user.verification_tier,
            "verification": {
                "points": v_points,
                "max_points": MAX_VERIFICATION_POINTS,
                "weight": "40%",
                "email_verified": user.email_verified,
                "phone_verified": user.phone_verified,
                "enterprise_verified": user.enterprise_verified,
                "wechat_verified": user.wechat_verified,
            },
            "review": {
                "score": r_score,
                "max_score": 500,
                "weight": "35%",
                "total_reviews": review_stats["total_reviews"],
                "avg_rating": review_stats["avg_rating"],
            },
            "behavior": {
                "score": b_score,
                "max_score": 100,
                "weight": "25%",
                "completed_matches": ts.completed_matches,
                "response_rate": ts.response_rate,
                "avg_response_time_hours": ts.avg_response_time,
            },
            "match_level": get_match_level(ts.trust_tier),
            "last_calculated_at": ts.last_calculated_at.isoformat() if ts.last_calculated_at else None,
        },
    }


@router.get(
    "/match-level/{user_id}", summary="获取匹配级别", description="获取用户的匹配级别（基于信任等级决定匹配模式）"
)
def get_match_level_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "用户不存在"},
        )

    # 获取或计算信任评分
    ts = db.query(TrustScore).filter(TrustScore.user_id == user_id).first()
    if not ts:
        try:
            ts = calculate_trust_score(db, user_id)
        except Exception:
            # 如果计算失败，用默认值
            tier = get_trust_tier(0)
            level = get_match_level(tier)
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "user_id": user_id,
                    "trust_tier": tier,
                    "total_score": 0,
                    "match_level": level,
                    "match_level_label": _match_level_label(level),
                },
            }

    level = get_match_level(ts.trust_tier)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "user_id": user_id,
            "trust_tier": ts.trust_tier,
            "total_score": ts.total_score,
            "match_level": level,
            "match_level_label": _match_level_label(level),
        },
    }


# ============================================================
# 管理员工具: 批量重算信任评分
# ============================================================


@router.post("/recalculate", summary="批量重算信任评分", description="管理员手动触发所有用户信任评分的批量重算")
def recalculate_all_scores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    users = db.query(User).filter(User.is_deleted == False).all()
    count = 0
    errors = []
    for user in users:
        try:
            calculate_trust_score(db, user.id)
            count += 1
        except Exception as e:
            errors.append({"user_id": user.id, "error": str(e)})

    return {
        "code": 200,
        "message": f"成功重算 {count}/{len(users)} 个用户的信任评分",
        "data": {
            "total": len(users),
            "success": count,
            "errors": errors,
        },
    }


# ============================================================
# 内部辅助函数
# ============================================================


def _get_review_stats(db: Session, user_id: int) -> dict:
    """获取用户评价统计"""
    reviews = db.query(Review).filter(Review.reviewee_id == user_id).all()
    total = len(reviews)
    avg = round(sum(r.overall_rating for r in reviews) / total, 2) if total > 0 else 0.0
    return {
        "total_reviews": total,
        "avg_rating": avg,
    }


def _match_level_label(level: str) -> str:
    labels = {
        "instant": "即时匹配 — 自动推荐+直连",
        "assisted": "辅助匹配 — 需双方确认",
        "manual": "手动匹配 — 仅展示不推荐",
    }
    return labels.get(level, "未知")
