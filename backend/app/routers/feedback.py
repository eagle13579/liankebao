"""链客宝 — 用户反馈 API（自进化闭环 P0）
=========================================
端点:
  POST   /api/feedback              — 提交反馈
  GET    /api/feedback              — 查询反馈列表（管理员）
  POST   /api/feedback/{id}/status  — 更新反馈处理状态
  GET    /api/feedback/stats        — 获取反馈统计
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.feedback import Feedback, FeedbackCategory, FeedbackStatus, FeedbackStats

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/feedback", tags=["用户反馈"])


# ===================================================================
# 依赖: 获取数据库会话
# ===================================================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================

class FeedbackSubmitRequest(BaseModel):
    """提交反馈请求体"""
    user_id: str = Field(..., min_length=1, description="用户 ID")
    category: FeedbackCategory = Field(..., description="反馈分类")
    message: str = Field(..., min_length=1, description="反馈内容")
    rating: Optional[int] = Field(None, ge=1, le=5, description="评分 (1-5)")
    page_url: Optional[str] = Field(None, max_length=1024, description="来源页面 URL")

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("反馈内容不能为空")
        return v.strip()

    @field_validator("page_url")
    @classmethod
    def clean_page_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class FeedbackSubmitResponse(BaseModel):
    """提交反馈响应"""
    id: int
    user_id: str
    category: str
    message: str
    rating: Optional[int] = None
    page_url: Optional[str] = None
    status: str
    created_at: str
    message_text: str = "反馈提交成功"


class FeedbackItem(BaseModel):
    """单条反馈记录"""
    id: int
    user_id: str
    category: str
    message: str
    rating: Optional[int] = None
    page_url: Optional[str] = None
    status: str
    created_at: str

    @classmethod
    def from_orm(cls, fb: Feedback) -> "FeedbackItem":
        return cls(
            id=fb.id,
            user_id=fb.user_id,
            category=fb.category.value if isinstance(fb.category, FeedbackCategory) else fb.category,
            message=fb.message,
            rating=fb.rating,
            page_url=fb.page_url,
            status=fb.status.value if isinstance(fb.status, FeedbackStatus) else fb.status,
            created_at=fb.created_at.isoformat() if fb.created_at else "",
        )


class FeedbackListResponse(BaseModel):
    """反馈列表响应"""
    total: int
    page: int
    limit: int
    items: list[FeedbackItem]


class FeedbackStatusUpdateRequest(BaseModel):
    """更新状态请求体"""
    status: FeedbackStatus = Field(..., description="新状态")


class FeedbackStatsResponse(BaseModel):
    """统计响应"""
    total_count: int
    category_distribution: dict[str, int]
    avg_rating: float
    rating_distribution: dict[int, int]
    status_distribution: dict[str, int]
    trend: dict[str, int]


# ===================================================================
# POST /api/feedback — 提交反馈
# ===================================================================
@router.post("", response_model=FeedbackSubmitResponse, status_code=201)
async def submit_feedback(req: FeedbackSubmitRequest, db: Session = Depends(get_db)):
    """提交一条用户反馈

    验证:
      - message 非空
      - rating 在 1-5 范围内（若提供）
    """
    feedback = Feedback(
        user_id=req.user_id,
        category=req.category,
        message=req.message,
        rating=req.rating,
        page_url=req.page_url,
        status=FeedbackStatus.PENDING,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return FeedbackSubmitResponse(
        id=feedback.id,
        user_id=feedback.user_id,
        category=feedback.category.value,
        message=feedback.message,
        rating=feedback.rating,
        page_url=feedback.page_url,
        status=feedback.status.value,
        created_at=feedback.created_at.isoformat() if feedback.created_at else "",
        message_text="反馈提交成功",
    )


# ===================================================================
# GET /api/feedback — 查询反馈列表（管理员）
# ===================================================================
@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    category: Optional[FeedbackCategory] = Query(None, description="按分类筛选"),
    status: Optional[FeedbackStatus] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=200, description="每页条数"),
    db: Session = Depends(get_db),
):
    """查询反馈列表（管理员用）

    支持按分类 (category) 和状态 (status) 筛选，分页返回。
    默认按创建时间倒序排列。
    """
    query = db.query(Feedback)

    if category is not None:
        query = query.filter(Feedback.category == category)
    if status is not None:
        query = query.filter(Feedback.status == status)

    total = query.count()
    items = (
        query
        .order_by(Feedback.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return FeedbackListResponse(
        total=total,
        page=page,
        limit=limit,
        items=[FeedbackItem.from_orm(fb) for fb in items],
    )


# ===================================================================
# POST /api/feedback/{id}/status — 更新反馈处理状态
# ===================================================================
@router.post("/{id}/status")
async def update_feedback_status(
    id: int,
    req: FeedbackStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """更新反馈处理状态

    状态流转: pending → acknowledged → resolved → closed
    """
    feedback = db.query(Feedback).filter(Feedback.id == id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail=f"反馈记录不存在 (id={id})")

    feedback.status = req.status
    db.commit()
    db.refresh(feedback)

    return {
        "id": feedback.id,
        "status": feedback.status.value,
        "message": f"反馈状态已更新为 {feedback.status.value}",
    }


# ===================================================================
# GET /api/feedback/stats — 获取反馈统计
# ===================================================================
@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(db: Session = Depends(get_db)):
    """获取反馈全局统计

    返回:
      - total_count:           反馈总数
      - category_distribution: 按分类分布
      - avg_rating:            平均评分
      - rating_distribution:   评分分布
      - status_distribution:   按状态分布
      - trend:                 按日期趋势（近 30 天）
    """
    # ── 总数 ──
    total_count = db.query(sa_func.count(Feedback.id)).scalar() or 0

    # ── 按分类分布 ──
    cat_rows = (
        db.query(Feedback.category, sa_func.count(Feedback.id).label("cnt"))
        .group_by(Feedback.category)
        .all()
    )
    category_distribution = {str(r.category): r.cnt for r in cat_rows}

    # ── 平均评分 ──
    avg_rating_row = (
        db.query(sa_func.avg(Feedback.rating))
        .filter(Feedback.rating.isnot(None))
        .scalar()
    )
    avg_rating = float(avg_rating_row) if avg_rating_row is not None else 0.0

    # ── 评分分布 ──
    rating_rows = (
        db.query(Feedback.rating, sa_func.count(Feedback.id).label("cnt"))
        .filter(Feedback.rating.isnot(None))
        .group_by(Feedback.rating)
        .all()
    )
    rating_distribution = {int(r.rating): r.cnt for r in rating_rows if r.rating is not None}
    # 补齐缺失的评分值
    for r in range(1, 6):
        if r not in rating_distribution:
            rating_distribution[r] = 0

    # ── 按状态分布 ──
    status_rows = (
        db.query(Feedback.status, sa_func.count(Feedback.id).label("cnt"))
        .group_by(Feedback.status)
        .all()
    )
    status_distribution = {str(r.status): r.cnt for r in status_rows}

    # ── 按日期趋势（近 30 天） ──
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    trend_rows = (
        db.query(
            sa_func.date(Feedback.created_at).label("date"),
            sa_func.count(Feedback.id).label("cnt"),
        )
        .filter(Feedback.created_at >= thirty_days_ago)
        .group_by(sa_func.date(Feedback.created_at))
        .order_by(sa_func.date(Feedback.created_at))
        .all()
    )
    trend = {str(r.date): r.cnt for r in trend_rows}

    return FeedbackStatsResponse(
        total_count=total_count,
        category_distribution=category_distribution,
        avg_rating=avg_rating,
        rating_distribution=rating_distribution,
        status_distribution=status_distribution,
        trend=trend,
    )
