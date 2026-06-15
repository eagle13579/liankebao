# =============================================================================
# 链客宝信任体系 — REST API 端点
# =============================================================================
# 依据 PRD §5.2 共11个端点:
#   信任评分 (3):  GET 获取/历史/明细
#   资质管理 (5):  POST/GET/GET/PUT/DELETE
#   审计报告 (3):  POST/GET/GET
#   评价系统 (2):  POST/GET
#   合规中心 (2):  GET 平台资质/评分公式
#
# 框架: FastAPI (适配链客宝现有架构)
# 设计哲学: H08 阳光下行走 — 评分公式完全公开
# =============================================================================

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from trust_engine.scoring import (
    TrustScorer,
    QualificationSubscores,
    TransactionSubscores,
    ComplianceSubscores,
)
from trust_engine.tier import (
    TrustTier,
    TrustLevel,
    TIER_DEFINITIONS,
    validate_score,
    is_diamond_eligible,
    is_board_eligible,
)
from trust_models import (
    TrustQualification,
    TrustScoreSnapshot,
    TrustAuditReport,
    TrustReview,
    TrustScoreLog,
    QualificationStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trust", tags=["信任体系"])

# ── 核心评分器实例 ─────────────────────────────────────────────────────────
_scorer = TrustScorer()


# =============================================================================
# Pydantic 请求/响应模型
# =============================================================================

# ── 信任评分响应 ───────────────────────────────────────────────────────────

class ScoreResponse(BaseModel):
    """信任评分响应 (公开)"""
    user_id: str
    total_score: float = Field(..., ge=0, le=100)
    breakdown: dict[str, Any]
    tier: dict[str, object]
    snapshot_date: str

    model_config = {"json_schema_extra": {
        "example": {
            "user_id": "uuid-xxx",
            "total_score": 86.5,
            "breakdown": {
                "qualification": {"raw_total": 85.0, "weighted": 34.0},
                "transaction": {"raw_total": 92.0, "weighted": 32.2},
                "compliance": {"raw_total": 78.0, "weighted": 19.5},
            },
            "tier": {"level": "excellent", "label_cn": "优秀级", "icon": "⭐"},
            "snapshot_date": "2026-06-07",
        }
    }}


class ScoreHistoryItem(BaseModel):
    """评分历史单项"""
    snapshot_date: str
    total_score: float
    trust_level: str


class ScoreHistoryResponse(BaseModel):
    """评分历史响应"""
    user_id: str
    history: list[ScoreHistoryItem]


# ── 资质管理请求 ───────────────────────────────────────────────────────────

class QualificationCreate(BaseModel):
    """上传资质请求"""
    qualification_type: str = Field(
        ..., min_length=1, max_length=64,
        description="资质类型: business_license / iso_cert / icp / patent / ..."
    )
    qualification_name: str = Field(..., min_length=1, max_length=256)
    cert_number: Optional[str] = Field(None, max_length=128)
    issuing_authority: Optional[str] = Field(None, max_length=256)
    issue_date: str = Field(..., description="发证日期 YYYY-MM-DD")
    expiry_date: Optional[str] = Field(None, description="有效期 YYYY-MM-DD 或无期传 null")
    file_url: str = Field(..., min_length=1, max_length=1024)
    file_hash: Optional[str] = Field(None, max_length=64, description="SHA-256, 不传则自动计算")

    @field_validator("issue_date", "expiry_date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError(f"日期格式必须为 YYYY-MM-DD, got {v}") from exc
        return v


class QualificationUpdate(BaseModel):
    """更新资质请求"""
    qualification_name: Optional[str] = Field(None, max_length=256)
    cert_number: Optional[str] = Field(None, max_length=128)
    issuing_authority: Optional[str] = Field(None, max_length=256)
    expiry_date: Optional[str] = None
    file_url: Optional[str] = Field(None, max_length=1024)
    file_hash: Optional[str] = Field(None, max_length=64)

    @field_validator("expiry_date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError(f"日期格式必须为 YYYY-MM-DD, got {v}") from exc
        return v


# ── 审计报告请求 ───────────────────────────────────────────────────────────

class AuditReportCreate(BaseModel):
    """上传审计报告请求"""
    report_type: str = Field(..., pattern="^(financial|security|compliance)$")
    audit_firm: str = Field(..., min_length=1, max_length=256)
    audit_conclusion: str = Field(..., min_length=1, max_length=512)
    report_url: str = Field(..., min_length=1, max_length=1024)
    report_hash: str = Field(..., min_length=1, max_length=64)
    audit_period_start: str = Field(..., description="YYYY-MM-DD")
    audit_period_end: str = Field(..., description="YYYY-MM-DD")
    is_public: bool = False
    view_permission: str = Field("diamond", pattern="^(public|gold|diamond|board)$")


# ── 评价请求 ───────────────────────────────────────────────────────────────

class ReviewCreate(BaseModel):
    """提交评价请求"""
    to_user_id: str = Field(..., min_length=1, max_length=36)
    order_id: Optional[str] = Field(None, max_length=36)
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = Field(None, max_length=2000)
    tags: Optional[list[str]] = Field(None, max_length=10)
    is_anonymous: bool = False


# ── 合规中心响应 ───────────────────────────────────────────────────────────

class PlatformQualificationItem(BaseModel):
    """平台资质单项"""
    name: str
    cert_number: Optional[str] = None
    status: str
    description: str


class TrustFormulaResponse(BaseModel):
    """信任评分公式公开 (H08 阳光下行走)"""
    version: str = "1.0"
    dimensions: list[dict[str, object]]
    tiers: list[dict[str, object]]
    decay_function: str
    formula_summary: str


# =============================================================================
# 辅助函数
# =============================================================================

def _get_current_user_id(authorization: Optional[str] = None) -> str:
    """从请求头中提取当前用户ID（简版，实际应使用JWT验证）

    生产环境应替换为 app.auth.get_current_user 注入
    """
    # TODO: 集成现有 JWT 认证中间件
    # 当前返回模拟用户ID，生产环境通过依赖注入替换
    return "current-user-id-placeholder"


def _compute_file_hash(content: bytes) -> str:
    """计算SHA-256文件哈希"""
    return hashlib.sha256(content).hexdigest()


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return date.today().isoformat()


# =============================================================================
# 信任评分 API (3个端点)
# =============================================================================

@router.get(
    "/score/{user_id}",
    response_model=ScoreResponse,
    summary="获取用户信任评分（公开）",
    description="PRD §5.2: 返回用户的综合信任评分、三维明细、等级。该端点公开可访问。",
)
def get_trust_score(
    user_id: str = Path(..., description="用户UUID"),
    db: Session = Depends(lambda: None),  # TODO: inject get_db
):
    """获取用户信任评分（公开）

    H08 阳光下行走: 评分完全公开透明
    """
    try:
        # 实际应从数据库查询数据，这里用模拟数据演示
        # TODO: 替换为真实数据库查询 + TrustScorer.calculate_from_raw_data()
        snapshot = _get_latest_snapshot(db, user_id)
        if snapshot:
            tier = TrustTier(snapshot.score_total)
            return ScoreResponse(
                user_id=user_id,
                total_score=snapshot.score_total,
                breakdown=snapshot.calc_metadata or {},
                tier=tier.to_dict(),
                snapshot_date=snapshot.snapshot_date.isoformat(),
            )

        # 无快照时返回默认值（冷启动）
        tier = TrustTier(0)
        return ScoreResponse(
            user_id=user_id,
            total_score=0.0,
            breakdown={
                "qualification": {"raw_total": 0, "weighted": 0},
                "transaction": {"raw_total": 0, "weighted": 0},
                "compliance": {"raw_total": 0, "weighted": 0},
            },
            tier=tier.to_dict(),
            snapshot_date=_today_str(),
        )
    except Exception as exc:
        logger.error("获取信任评分失败 user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="信任评分计算失败",
        ) from exc


@router.get(
    "/score/history/{user_id}",
    response_model=ScoreHistoryResponse,
    summary="评分历史走势（公开-近12月）",
    description="PRD §5.2: 返回用户近12个月的评分走势数据。",
)
def get_trust_score_history(
    user_id: str = Path(..., description="用户UUID"),
    months: int = Query(12, ge=1, le=24, description="查询月数"),
    db: Session = Depends(lambda: None),
):
    """获取评分历史走势（公开-近12月）"""
    try:
        # TODO: 替换为实际数据库查询
        history = _query_score_history(db, user_id, months)
        return ScoreHistoryResponse(
            user_id=user_id,
            history=[
                ScoreHistoryItem(
                    snapshot_date=h.snapshot_date.isoformat(),
                    total_score=h.score_total,
                    trust_level=h.trust_level,
                )
                for h in history
            ],
        )
    except Exception as exc:
        logger.error("获取评分历史失败 user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取评分历史失败",
        ) from exc


@router.get(
    "/score/breakdown/{user_id}",
    summary="评分维度明细（公开）",
    description="PRD §5.2: 返回三维评分各子指标的详细分值。",
)
def get_trust_score_breakdown(
    user_id: str = Path(..., description="用户UUID"),
    db: Session = Depends(lambda: None),
):
    """获取评分维度明细（公开）

    返回完整的三维评分明细，包括每个子指标的具体分值。
    完全透明（H08 阳光下行走）。
    """
    try:
        snapshot = _get_latest_snapshot(db, user_id)
        if not snapshot:
            return {"user_id": user_id, "breakdown": None, "message": "暂无评分数据"}

        result = snapshot.calc_metadata or {}
        tier = TrustTier(snapshot.score_total)
        return {
            "user_id": user_id,
            "total_score": snapshot.score_total,
            "tier": tier.to_dict(),
            "breakdown": result,
            "snapshot_date": snapshot.snapshot_date.isoformat(),
        }
    except Exception as exc:
        logger.error("获取评分明细失败 user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取评分明细失败",
        ) from exc


# =============================================================================
# 资质管理 API (5个端点)
# =============================================================================

@router.post(
    "/qualifications",
    status_code=status.HTTP_201_CREATED,
    summary="上传资质证书（需认证）",
    description="PRD §5.2: 上传企业资质证书，自动触发AI OCR验证。",
)
def create_qualification(
    body: QualificationCreate,
    authorization: Optional[str] = None,
    db: Session = Depends(lambda: None),
):
    """上传资质证书"""
    current_user = _get_current_user_id(authorization)

    try:
        # 自动计算文件哈希（如果未提供）
        file_hash = body.file_hash
        if not file_hash and body.file_url:
            file_hash = _compute_file_hash(body.file_url.encode("utf-8"))

        qual = TrustQualification(
            user_id=current_user,
            qualification_type=body.qualification_type,
            qualification_name=body.qualification_name,
            cert_number=body.cert_number,
            issuing_authority=body.issuing_authority,
            issue_date=datetime.strptime(body.issue_date, "%Y-%m-%d").date(),
            expiry_date=(
                datetime.strptime(body.expiry_date, "%Y-%m-%d").date()
                if body.expiry_date else None
            ),
            file_url=body.file_url,
            file_hash=file_hash,
            status=QualificationStatus.PENDING.value,
        )

        # TODO: db.add(qual); db.commit(); db.refresh(qual)
        logger.info("资质上传: user=%s type=%s", current_user, body.qualification_type)

        return {
            "code": 201,
            "message": "资质上传成功，等待审核",
            "data": qual.to_dict() if hasattr(qual, 'to_dict') else {"id": qual.id},
        }
    except Exception as exc:
        logger.error("资质上传失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"资质上传失败: {exc}",
        ) from exc


@router.get(
    "/qualifications",
    summary="获取资质列表（需认证）",
    description="PRD §5.2: 返回当前用户的所有资质证书。",
)
def list_qualifications(
    status_filter: Optional[str] = Query(None, description="筛选状态: active/pending/expired/rejected"),
    authorization: Optional[str] = None,
    db: Session = Depends(lambda: None),
):
    """获取资质列表"""
    current_user = _get_current_user_id(authorization)

    try:
        # TODO: 替换为实际数据库查询
        query = db.query(TrustQualification).filter(
            TrustQualification.user_id == current_user
        )
        if status_filter:
            query = query.filter(TrustQualification.status == status_filter)

        qualifications = query.order_by(TrustQualification.created_at.desc()).all()

        return {
            "code": 200,
            "message": "success",
            "data": [q.to_dict() for q in qualifications],
            "total": len(qualifications),
        }
    except Exception as exc:
        logger.error("查询资质列表失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查询资质列表失败",
        ) from exc


@router.get(
    "/qualifications/{qual_id}",
    summary="获取资质详情（需认证）",
    description="PRD §5.2: 返回指定资质的详细信息。",
)
def get_qualification(
    qual_id: str = Path(..., description="资质ID"),
    db: Session = Depends(lambda: None),
):
    """获取资质详情"""
    try:
        # TODO: 替换为实际数据库查询
        qual = db.query(TrustQualification).filter(
            TrustQualification.id == qual_id
        ).first()

        if not qual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="资质记录不存在",
            )

        return {
            "code": 200,
            "message": "success",
            "data": qual.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("查询资质详情失败 id=%s: %s", qual_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查询资质详情失败",
        ) from exc


@router.put(
    "/qualifications/{qual_id}",
    summary="更新资质（需认证）",
    description="PRD §5.2: 更新指定资质的信息。",
)
def update_qualification(
    qual_id: str = Path(...),
    body: QualificationUpdate = ...,
    authorization: Optional[str] = None,
    db: Session = Depends(lambda: None),
):
    """更新资质"""
    current_user = _get_current_user_id(authorization)

    try:
        # TODO: 替换为实际数据库查询
        qual = db.query(TrustQualification).filter(
            TrustQualification.id == qual_id,
            TrustQualification.user_id == current_user,
        ).first()

        if not qual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="资质不存在或无权修改",
            )

        # 更新字段
        update_data = body.model_dump(exclude_unset=True)
        if "expiry_date" in update_data and update_data["expiry_date"]:
            update_data["expiry_date"] = datetime.strptime(
                update_data["expiry_date"], "%Y-%m-%d"
            ).date()

        for key, value in update_data.items():
            setattr(qual, key, value)

        # TODO: db.commit(); db.refresh(qual)

        logger.info("资质更新: id=%s user=%s", qual_id, current_user)
        return {
            "code": 200,
            "message": "资质更新成功",
            "data": qual.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("更新资质失败 id=%s: %s", qual_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"更新资质失败: {exc}",
        ) from exc


@router.delete(
    "/qualifications/{qual_id}",
    status_code=status.HTTP_200_OK,
    summary="删除资质（需认证）",
    description="PRD §5.2: 删除指定资质记录。",
)
def delete_qualification(
    qual_id: str = Path(...),
    authorization: Optional[str] = None,
    db: Session = Depends(lambda: None),
):
    """删除资质"""
    current_user = _get_current_user_id(authorization)

    try:
        # TODO: 替换为实际数据库查询
        qual = db.query(TrustQualification).filter(
            TrustQualification.id == qual_id,
            TrustQualification.user_id == current_user,
        ).first()

        if not qual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="资质不存在或无权删除",
            )

        # TODO: db.delete(qual); db.commit()

        logger.info("资质删除: id=%s user=%s", qual_id, current_user)
        return {
            "code": 200,
            "message": "资质删除成功",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("删除资质失败 id=%s: %s", qual_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除资质失败",
        ) from exc


# =============================================================================
# 审计报告 API (3个端点)
# =============================================================================

@router.post(
    "/audit-reports",
    status_code=status.HTTP_201_CREATED,
    summary="上传审计报告（需认证+钻石及以上）",
    description="PRD §5.2: 上传第三方审计报告（财务/安全/合规）。",
)
def create_audit_report(
    body: AuditReportCreate,
    authorization: Optional[str] = None,
    db: Session = Depends(lambda: None),
):
    """上传审计报告"""
    current_user = _get_current_user_id(authorization)

    try:
        # TODO: 检查用户会员等级（需钻石及以上）
        report = TrustAuditReport(
            user_id=current_user,
            report_type=body.report_type,
            audit_firm=body.audit_firm,
            audit_conclusion=body.audit_conclusion,
            report_url=body.report_url,
            report_hash=body.report_hash,
            audit_period_start=datetime.strptime(body.audit_period_start, "%Y-%m-%d").date(),
            audit_period_end=datetime.strptime(body.audit_period_end, "%Y-%m-%d").date(),
            is_public=body.is_public,
            view_permission=body.view_permission,
            status="pending",
        )

        # TODO: db.add(report); db.commit(); db.refresh(report)

        logger.info("审计报告上传: user=%s type=%s", current_user, body.report_type)
        return {
            "code": 201,
            "message": "审计报告上传成功，等待审核",
            "data": report.to_dict(),
        }
    except Exception as exc:
        logger.error("审计报告上传失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"审计报告上传失败: {exc}",
        ) from exc


@router.get(
    "/audit-reports",
    summary="获取审计报告列表",
    description="PRD §5.2: 返回当前用户的审计报告列表。",
)
def list_audit_reports(
    report_type: Optional[str] = Query(None, description="筛选类型"),
    authorization: Optional[str] = None,
    db: Session = Depends(lambda: None),
):
    """获取审计报告列表"""
    current_user = _get_current_user_id(authorization)

    try:
        # TODO: 替换为实际数据库查询
        query = db.query(TrustAuditReport).filter(
            TrustAuditReport.user_id == current_user
        )
        if report_type:
            query = query.filter(TrustAuditReport.report_type == report_type)

        reports = query.order_by(TrustAuditReport.created_at.desc()).all()

        return {
            "code": 200,
            "message": "success",
            "data": [r.to_dict() for r in reports],
            "total": len(reports),
        }
    except Exception as exc:
        logger.error("查询审计报告列表失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查询审计报告列表失败",
        ) from exc


@router.get(
    "/audit-reports/{report_id}",
    summary="获取审计报告详情",
    description="PRD §5.2: 返回指定审计报告的详细信息（带权限控制）。",
)
def get_audit_report(
    report_id: str = Path(...),
    db: Session = Depends(lambda: None),
):
    """获取审计报告详情"""
    try:
        # TODO: 替换为实际数据库查询
        report = db.query(TrustAuditReport).filter(
            TrustAuditReport.id == report_id
        ).first()

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="审计报告不存在",
            )

        # TODO: 检查查看权限
        return {
            "code": 200,
            "message": "success",
            "data": report.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("查询审计报告详情失败 id=%s: %s", report_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查询审计报告详情失败",
        ) from exc


# =============================================================================
# 评价系统 API (2个端点)
# =============================================================================

@router.post(
    "/reviews",
    status_code=status.HTTP_201_CREATED,
    summary="提交评价（订单完成后触发）",
    description="PRD §5.2: 成交后提交评价，一条订单一笔评价。",
)
def create_review(
    body: ReviewCreate,
    authorization: Optional[str] = None,
    db: Session = Depends(lambda: None),
):
    """提交评价"""
    current_user = _get_current_user_id(authorization)

    # 自评校验
    if current_user == body.to_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能给自己评分",
        )

    try:
        review = TrustReview(
            from_user_id=current_user,
            to_user_id=body.to_user_id,
            order_id=body.order_id,
            rating=body.rating,
            review_text=body.review_text,
            tags=body.tags,
            is_anonymous=body.is_anonymous,
        )

        # TODO: db.add(review); db.commit(); db.refresh(review)
        # TODO: 触发交易可信度重新计算

        logger.info(
            "评价提交: from=%s to=%s rating=%d order=%s",
            current_user, body.to_user_id, body.rating, body.order_id,
        )
        return {
            "code": 201,
            "message": "评价提交成功",
            "data": review.to_dict(),
        }
    except Exception as exc:
        logger.error("评价提交失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"评价提交失败: {exc}",
        ) from exc


@router.get(
    "/reviews/{user_id}",
    summary="查看用户评价列表",
    description="PRD §5.2: 返回指定用户收到的所有评价。",
)
def list_reviews(
    user_id: str = Path(..., description="被评价用户ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(lambda: None),
):
    """查看用户评价列表"""
    try:
        # TODO: 替换为实际数据库查询
        query = db.query(TrustReview).filter(
            TrustReview.to_user_id == user_id
        ).order_by(TrustReview.created_at.desc())

        total = query.count()
        reviews = query.offset((page - 1) * page_size).limit(page_size).all()

        # 聚合统计
        stats = _aggregate_review_stats(reviews, total)

        return {
            "code": 200,
            "message": "success",
            "data": {
                "reviews": [r.to_dict() for r in reviews],
                "stats": stats,
            },
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    except Exception as exc:
        logger.error("查询评价列表失败 user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查询评价列表失败",
        ) from exc


# =============================================================================
# 合规中心 API (2个端点)
# =============================================================================

@router.get(
    "/compliance/platform-qualifications",
    summary="平台资质展示（公开）",
    description="PRD §5.2 + §3.5: 公开展示链客宝平台自身的合规资质。",
)
def get_platform_qualifications():
    """平台资质展示（公开）

    H08 阳光下行走: 平台自身合规资质完全透明
    """
    # 平台资质数据（硬编码，实际从数据库读取）
    platform_quals = [
        PlatformQualificationItem(
            name="ICP备案",
            cert_number="沪ICP备2025XXXXXX号",
            status="✅ 有效",
            description="工业和信息化部ICP备案",
        ),
        PlatformQualificationItem(
            name="等保三级认证",
            cert_number="330106XXXXX",
            status="✅ 有效",
            description="国家信息安全等级保护三级认证",
        ),
        PlatformQualificationItem(
            name="企业营业执照",
            cert_number="91310000XXXXXXXX",
            status="✅ 有效",
            description="上海市市场监督管理局",
        ),
        PlatformQualificationItem(
            name="数据安全承诺",
            cert_number=None,
            status="✅ 已签署",
            description="链客宝数据安全与隐私保护承诺书",
        ),
        PlatformQualificationItem(
            name="区块链存证备案",
            cert_number="沪网信备XXXXXXXX号",
            status="✅ 有效",
            description="区块链信息服务备案",
        ),
    ]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "platform_name": "链客宝 LianKeBao",
            "qualifications": [q.model_dump() for q in platform_quals],
            "last_updated": "2026-06-07",
        },
    }


@router.get(
    "/compliance/trust-formula",
    summary="信任评分公式公开（H08阳光下行走）",
    description="PRD §5.2 + H08: 完全公开信任评分计算公式。",
)
def get_trust_formula():
    """信任评分公式公开（H08 阳光下行走）

    完全透明的评分公式，任何人都可查。
    越透明，越没人质疑。
    """
    dimensions = [
        {
            "name": "资质可信度",
            "weight": "40%",
            "sub_indicators": [
                {"name": "认证等级", "range": "0-30", "description": "基础认证=10, 企业认证=20, 高级认证=25, 钻石=30"},
                {"name": "资质种类数", "range": "0-25", "description": "每上传1项有效资质+5分，上限25分（5项满分）"},
                {"name": "资质时效性", "range": "0-20", "description": "全部有效=20, 1项过期-5, 2项过期-10, 3项+=0"},
                {"name": "实名深度", "range": "0-15", "description": "手机号=3, 身份证=8, 法定代表人视频认证=15"},
                {"name": "平台验证时长", "range": "0-10", "description": "<1年=3, 1-2年=5, 2-3年=8, 3年+=10"},
            ],
            "formula": "资质可信度 = (认证等级 + 资质种类数 + 资质时效性 + 实名深度 + 平台验证时长) × 0.40",
        },
        {
            "name": "交易可信度",
            "weight": "35%",
            "sub_indicators": [
                {"name": "成交笔数", "range": "0-30", "description": "0笔=0, 1-5笔=10, 6-20笔=20, 21笔+=30"},
                {"name": "成交金额", "range": "0-25", "description": "<10万=5, 10-100万=15, 100-500万=20, 500万+=25"},
                {"name": "好评率", "range": "0-20", "description": "<80%=0, 80-90%=10, 90-95%=15, 95%+=20"},
                {"name": "纠纷率", "range": "0-15", "description": "纠纷率>10%=0, 5-10%=5, 1-5%=10, 0%=15"},
                {"name": "复购率", "range": "0-10", "description": "首单=3, 2次=5, 3次=7, 5次+=10"},
            ],
            "formula": "交易可信度 = (成交笔数 + 成交金额 + 好评率 + (15 - 纠纷率惩罚) + 复购率) × 0.35",
            "decay": "时间衰减: score × exp(-0.1 × 距最近成交月数)",
        },
        {
            "name": "合规健康度",
            "weight": "25%",
            "sub_indicators": [
                {"name": "资质完整度", "range": "0-30", "description": "已上传资质数/建议资质数(7) × 30"},
                {"name": "证书过期风险", "range": "0-25", "description": "无过期=25, 1项即将过期=15, 1项已过期=5, 2项+=0"},
                {"name": "合规证书数", "range": "0-20", "description": "ISO/等保/ICP等，每项+5分，上限20"},
                {"name": "审计报告", "range": "0-15", "description": "有有效第三方审计报告=15, 有过期=5, 无=0"},
                {"name": "合规更新频率", "range": "0-10", "description": "近3月有更新=10, 近6月=7, 近1年=4, >1年=0"},
            ],
            "formula": "合规健康度 = (资质完整度 + 证书过期风险 + 合规证书数 + 审计报告 + 合规更新频率) × 0.25",
        },
    ]

    tiers = [t.to_dict() for t in [TrustTier(s * 10 + 5) for s in range(5)]]  # 示例值

    return TrustFormulaResponse(
        version="1.0",
        dimensions=dimensions,
        tiers=[
            {
                "level": t.level.value,
                "label_cn": t.label_cn,
                "icon": t.icon,
                "range": f"{t.min_score:.0f}-{t.max_score:.0f}",
                "match_weight": t.match_weight,
            }
            for t in TIER_DEFINITIONS
        ],
        decay_function="f(t) = exp(-0.1 × months_since_last_trade), λ=0.1",
        formula_summary=(
            "TRUST_SCORE = 资质可信度(40%) + 交易可信度(35%) + 合规健康度(25%)\n"
            "评分范围: [0, 100]\n"
            "分级: ❌待完善(0-39) ⚠️基础级(40-59) ✅良好级(60-79) ⭐优秀级(80-89) 👑顶级(90-100)\n"
            "H08 阳光下行走: 评分公式完全公开透明"
        ),
    )


# =============================================================================
# 会员体系 API — 会员等级、升级购买、状态查询
# =============================================================================

from datetime import datetime, timedelta
from typing import Optional

_membership_router = APIRouter(prefix="/api/v1/membership", tags=["会员体系"])

# ── 会员等级定义（与 会员体系设计方案.md 一致）─────────────────────────────
MEMBERSHIP_TIERS = {
    "free": {
        "id": "free",
        "label_cn": "免费会员",
        "label_en": "Free",
        "icon": "🆓",
        "price_monthly": 0,
        "price_annual": 0,
        "description": "零成本入门，探索商机",
        "features": [
            "浏览供需信息",
            "发布3次/月需求",
            "3次精准对接券",
        ],
        "color": "#9CA3AF",
        "recommended": False,
    },
    "gold": {
        "id": "gold",
        "label_cn": "金卡会员",
        "label_en": "Gold",
        "icon": "🥇",
        "price_monthly": 99,
        "price_annual": 999,
        "description": "精准高效对接，企业增长加速器",
        "features": [
            "无限发布需求",
            "查看对方联系方式",
            "AI匹配优先推荐",
            "每月5次定向对接机会",
            "企业身份认证标识",
        ],
        "color": "#F59E0B",
        "recommended": False,
    },
    "diamond": {
        "id": "diamond",
        "label_cn": "钻石会员",
        "label_en": "Diamond",
        "icon": "💎",
        "price_monthly": 499,
        "price_annual": 4999,
        "description": "专属增长引擎，全方位赋能",
        "features": [
            "全部金卡权益",
            "专属撮合经理",
            "需求优先推荐TOP 3",
            "企业深度认证+信用报告",
            "线上闭门对接会（每季1次）",
            "交易安全保障金¥10,000",
            "CRM对接工具+合作意向追踪",
        ],
        "color": "#0284c7",
        "recommended": True,
    },
    "board": {
        "id": "board",
        "label_cn": "私董会",
        "label_en": "Board",
        "icon": "👑",
        "price_monthly": None,
        "price_annual": 19999,
        "description": "顶级企业家圈层，深度商业赋能",
        "features": [
            "全部钻石权益",
            "线下闭门私董会（每季1次）",
            "一对一商业诊断（季度）",
            "专家导师库（行业TOP100企业家）",
            "优先投资对接+独家项目路演",
        ],
        "color": "#8B5CF6",
        "recommended": False,
        "quota": 50,  # 限额50席
    },
}

# ── 内存订单存储（TODO: 替换为数据库）────────────────────────────────────
_membership_orders: dict[str, dict] = {}
_order_counter = 0


def _generate_order_no() -> str:
    global _order_counter
    _order_counter += 1
    now = datetime.now()
    return f"MB{now.strftime('%Y%m%d%H%M%S')}{_order_counter:04d}"


# ── 会员等级列表 ──────────────────────────────────────────────────────────

@_membership_router.get(
    "/tiers",
    summary="会员等级列表",
    description="返回所有会员等级的详细信息和权益对比。",
)
def list_membership_tiers():
    """获取所有会员等级列表"""
    tiers_list = list(MEMBERSHIP_TIERS.values())
    return {
        "code": 200,
        "message": "success",
        "data": tiers_list,
        "total": len(tiers_list),
    }


# ── 当前会员状态 ──────────────────────────────────────────────────────────

@_membership_router.get(
    "/status",
    summary="当前会员状态",
    description="返回当前登录用户的会员等级、有效期、剩余对接券等信息。",
)
def get_membership_status(
    authorization: Optional[str] = None,
):
    """获取当前会员状态"""
    current_user = _get_current_user_id(authorization)

    # TODO: 从数据库获取用户真实会员信息
    # 模拟数据
    tier_id = "free"
    expires_at = None
    match_credits = 3

    # 尝试从内存订单中查找最近的已支付订单
    user_orders = [
        o for o in _membership_orders.values()
        if o.get("user_id") == current_user and o.get("status") == "paid"
    ]
    if user_orders:
        latest = sorted(user_orders, key=lambda o: o.get("paid_at", ""), reverse=True)[0]
        tier_id = latest.get("tier", "free")
        expires_at = latest.get("expires_at")
        match_credits = 999 if tier_id in ("gold", "diamond", "board") else 3

    tier_info = MEMBERSHIP_TIERS.get(tier_id, MEMBERSHIP_TIERS["free"])

    return {
        "code": 200,
        "message": "success",
        "data": {
            "user_id": current_user,
            "tier": tier_id,
            "tier_name": tier_info["label_cn"],
            "tier_icon": tier_info["icon"],
            "tier_label": tier_info["label_cn"],
            "expires_at": expires_at,
            "match_credits": match_credits,
            "features": tier_info["features"],
        },
    }


# ── 创建会员订单 ──────────────────────────────────────────────────────────

class MembershipOrderCreate(BaseModel):
    tier: str = Field(..., pattern="^(gold|diamond|board)$", description="会员等级")
    period: str = Field("annual", pattern="^(monthly|annual)$", description="付费周期")
    amount: float = Field(..., gt=0, description="支付金额")
    pay_method: str = Field("alipay", pattern="^(alipay|wxpay)$", description="支付方式")


class MembershipOrderResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict = {}


@_membership_router.post(
    "/orders",
    status_code=status.HTTP_201_CREATED,
    summary="创建会员订单",
    description="创建会员升级/购买订单，返回支付所需参数。",
)
def create_membership_order(
    body: MembershipOrderCreate,
    authorization: Optional[str] = None,
):
    """创建会员订单"""
    current_user = _get_current_user_id(authorization)

    if body.tier not in MEMBERSHIP_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的会员等级: {body.tier}",
        )

    tier_info = MEMBERSHIP_TIERS[body.tier]

    # 校验金额
    expected_amount = (
        tier_info["price_annual"] if body.period == "annual"
        else tier_info["price_monthly"]
    )
    if expected_amount is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{tier_info['label_cn']}不支持{body.period}付费",
        )

    order_no = _generate_order_no()
    order = {
        "order_no": order_no,
        "user_id": current_user,
        "tier": body.tier,
        "tier_name": tier_info["label_cn"],
        "period": body.period,
        "amount": body.amount,
        "expected_amount": expected_amount,
        "pay_method": body.pay_method,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "paid_at": None,
        "expires_at": None,
    }
    _membership_orders[order_no] = order

    logger.info("会员订单创建: user=%s tier=%s order=%s", current_user, body.tier, order_no)

    return {
        "code": 201,
        "message": "订单创建成功",
        "data": {
            "order_no": order_no,
            "amount": expected_amount,
            "tier": body.tier,
            "tier_name": tier_info["label_cn"],
            "status": "pending",
            "pay_params": {
                "prepay_id": f"PRE{order_no}",
                "qr_code_url": f"https://api.chainke.cn/pay/qr/{order_no}",
                "trade_no": order_no,
            },
        },
    }


# ── 查询订单 ──────────────────────────────────────────────────────────────

@_membership_router.get(
    "/orders/{order_no}",
    summary="查询会员订单",
    description="根据订单号查询会员订单状态。",
)
def get_membership_order(
    order_no: str = Path(..., description="订单号"),
):
    """查询会员订单"""
    order = _membership_orders.get(order_no)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在",
        )

    return {
        "code": 200,
        "message": "success",
        "data": order,
    }


# ── 订单列表 ──────────────────────────────────────────────────────────────

@_membership_router.get(
    "/orders",
    summary="会员订单列表",
    description="返回当前用户的所有会员订单。",
)
def list_membership_orders(
    authorization: Optional[str] = None,
):
    """获取会员订单列表"""
    current_user = _get_current_user_id(authorization)

    user_orders = [
        o for o in _membership_orders.values()
        if o.get("user_id") == current_user
    ]
    user_orders.sort(key=lambda o: o.get("created_at", ""), reverse=True)

    return {
        "code": 200,
        "message": "success",
        "data": user_orders,
        "total": len(user_orders),
    }


# ── 支付回调（模拟） ───────────────────────────────────────────────────────

class PaymentCallback(BaseModel):
    order_no: str
    trade_no: str
    status: str = Field("paid", pattern="^(paid|failed)$")
    paid_amount: Optional[float] = None


@_membership_router.post(
    "/orders/callback",
    summary="支付回调",
    description="支付回调通知接口，更新订单状态。",
)
def payment_callback(
    body: PaymentCallback,
):
    """支付回调处理"""
    order = _membership_orders.get(body.order_no)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在",
        )

    if body.status == "paid":
        order["status"] = "paid"
        order["paid_at"] = datetime.utcnow().isoformat() + "Z"
        # 计算到期时间
        period_months = 12 if order.get("period") == "annual" else 1
        expires = datetime.utcnow() + timedelta(days=period_months * 30)
        order["expires_at"] = expires.isoformat() + "Z"
        logger.info("支付回调成功: order=%s tier=%s", body.order_no, order.get("tier"))
    else:
        order["status"] = "failed"
        logger.info("支付回调失败: order=%s", body.order_no)

    return {
        "code": 200,
        "message": "回调处理成功",
        "data": {
            "order_no": body.order_no,
            "status": order["status"],
        },
    }


# ── 注册会员路由到信任 API 路由器 ─────────────────────────────────────
# 将会员路由添加到主路由（通过 app 注册方式）
# 在 fastapi_payment.py 或统一入口中注册

# =============================================================================
# 内部辅助函数（TODO: 替换为真实数据库查询）
# =============================================================================

def _get_latest_snapshot(db, user_id: str) -> Optional[TrustScoreSnapshot]:
    """获取用户最新的评分快照"""
    # TODO: 替换为真实数据库查询
    # return (
    #     db.query(TrustScoreSnapshot)
    #     .filter(TrustScoreSnapshot.user_id == user_id)
    #     .order_by(TrustScoreSnapshot.snapshot_date.desc())
    #     .first()
    # )
    return None


def _query_score_history(
    db, user_id: str, months: int = 12
) -> list[TrustScoreSnapshot]:
    """查询评分历史"""
    # TODO: 替换为真实数据库查询
    return []


def _aggregate_review_stats(
    reviews: list[TrustReview], total: int
) -> dict[str, Any]:
    """聚合评价统计"""
    if total == 0:
        return {
            "total_reviews": 0,
            "average_rating": 0.0,
            "rating_distribution": {str(i): 0 for i in range(1, 6)},
        }

    ratings = [r.rating for r in reviews]
    avg = sum(ratings) / len(ratings) if ratings else 0.0
    dist = {str(i): sum(1 for r in reviews if r.rating == i) for i in range(1, 6)}

    return {
        "total_reviews": total,
        "average_rating": round(avg, 2),
        "rating_distribution": dist,
    }
