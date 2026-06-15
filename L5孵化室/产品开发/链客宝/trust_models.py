# =============================================================================
# 链客宝信任体系 — 数据库模型 (SQLAlchemy ORM)
# =============================================================================
# 依据 PRD §5.1 数据库模型扩展，共5张表:
#   1. trust_qualifications     — 企业资质档案
#   2. trust_score_snapshots    — 信任评分记录（每日快照）
#   3. trust_audit_reports      — 企业审计报告
#   4. trust_reviews            — 企业评价
#   5. trust_score_logs         — 信任评分变更日志（审计追踪）
#
# 设计原则:
#   - 类型注解全覆盖
#   - UUID主键
#   - 校验约束 (CHECK)
#   - JSONB元数据
#   - 时间戳审计
#   - 哈希防篡改 (SHA-256)
# =============================================================================

import enum
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── 基础声明 ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """声明性基类"""
    pass


# ── 辅助函数 ──────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── 枚举 ──────────────────────────────────────────────────────────────────

class QualificationStatus(str, enum.Enum):
    """资质状态"""
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REJECTED = "rejected"


class VerificationLevel(str, enum.Enum):
    """验证等级"""
    AI = "ai"
    MANUAL = "manual"
    BOTH = "both"


class AuditReportType(str, enum.Enum):
    """审计报告类型"""
    FINANCIAL = "financial"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class ViewPermission(str, enum.Enum):
    """查看权限"""
    PUBLIC = "public"
    GOLD = "gold"
    DIAMOND = "diamond"
    BOARD = "board"


class TrustLevelEnum(str, enum.Enum):
    """信任等级 (PRD §4.2)"""
    PENDING = "pending"         # ❌ 0-39
    BASIC = "basic"             # ⚠️ 40-59
    GOOD = "good"               # ✅ 60-79
    EXCELLENT = "excellent"     # ⭐ 80-89
    TOP = "top"                 # 👑 90-100


# =============================================================================
# 表1: trust_qualifications — 企业资质档案
# =============================================================================
# PRD §3.3 + §5.1:
#   企业上传的各类资质证书，含OCR验证+哈希存证
# =============================================================================

class TrustQualification(Base):
    """企业资质档案

    存储企业上传的各类资质证书（营业执照/ISO/ICP/专利等）。
    """
    __tablename__ = "trust_qualifications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    qualification_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="资质类型: business_license / iso_cert / icp / patent / trademark / saas_record / industry_license / copyright"
    )
    qualification_name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="资质名称"
    )
    cert_number: Mapped[Optional[str]] = mapped_column(
        String(128), comment="证书编号"
    )
    issuing_authority: Mapped[Optional[str]] = mapped_column(
        String(256), comment="发证机构"
    )
    issue_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="发证日期"
    )
    expiry_date: Mapped[Optional[date]] = mapped_column(
        Date, comment="有效期（无期则为NULL）"
    )
    file_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="原件存储URL"
    )
    file_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA-256文件哈希"
    )
    status: Mapped[str] = mapped_column(
        String(16), default=QualificationStatus.PENDING.value,
        comment="pending / active / expired / rejected"
    )
    verification_level: Mapped[str] = mapped_column(
        String(16), default=VerificationLevel.AI.value,
        comment="ai / manual / both"
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text, comment="驳回原因"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 约束
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'rejected')",
            name="ck_qualification_status"
        ),
        CheckConstraint(
            "verification_level IN ('ai', 'manual', 'both')",
            name="ck_qualification_verification"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TrustQualification id={self.id} user_id={self.user_id} "
            f"type={self.qualification_type} status={self.status}>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "qualification_type": self.qualification_type,
            "qualification_name": self.qualification_name,
            "cert_number": self.cert_number,
            "issuing_authority": self.issuing_authority,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "file_url": self.file_url,
            "file_hash": self.file_hash,
            "status": self.status,
            "verification_level": self.verification_level,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# 表2: trust_score_snapshots — 信任评分记录（每日快照）
# =============================================================================
# PRD §4.4.1 + §5.1:
#   每日全量重算的信任评分快照，含三维明细+等级+元数据
# =============================================================================

class TrustScoreSnapshot(Base):
    """信任评分快照

    每日02:00全量重算，或实时事件触发后更新。
    UNIQUE(user_id, snapshot_date) 确保每天每用户一条记录。
    """
    __tablename__ = "trust_score_snapshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    score_total: Mapped[float] = mapped_column(
        Float, nullable=False, comment="综合评分 0.00-100.00"
    )
    score_qualification: Mapped[Optional[float]] = mapped_column(
        Float, comment="资质可信度得分"
    )
    score_transaction: Mapped[Optional[float]] = mapped_column(
        Float, comment="交易可信度得分"
    )
    score_compliance: Mapped[Optional[float]] = mapped_column(
        Float, comment="合规健康度得分"
    )
    trust_level: Mapped[str] = mapped_column(
        String(16), nullable=False,
        comment="pending / basic / good / excellent / top"
    )
    snapshot_date: Mapped[date] = mapped_column(
        Date, nullable=False, default=date.today
    )
    calc_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, comment="计算明细元数据（各子指标分值+衰减因子+事件来源）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 约束
    __table_args__ = (
        UniqueConstraint(
            "user_id", "snapshot_date",
            name="uq_user_snapshot_date"
        ),
        CheckConstraint(
            "score_total >= 0 AND score_total <= 100",
            name="ck_score_total_range"
        ),
        CheckConstraint(
            "trust_level IN ('pending', 'basic', 'good', 'excellent', 'top')",
            name="ck_trust_level"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TrustScoreSnapshot user={self.user_id} "
            f"date={self.snapshot_date} score={self.score_total}>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "score_total": self.score_total,
            "score_qualification": self.score_qualification,
            "score_transaction": self.score_transaction,
            "score_compliance": self.score_compliance,
            "trust_level": self.trust_level,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
            "calc_metadata": self.calc_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# 表3: trust_audit_reports — 企业审计报告
# =============================================================================
# PRD §3.4 + §5.1:
#   第三方审计报告（财务/安全/合规），带权限控制
# =============================================================================

class TrustAuditReport(Base):
    """企业审计报告

    钻石及以上会员可上传，含权限控制。
    """
    __tablename__ = "trust_audit_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    report_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="financial / security / compliance"
    )
    audit_firm: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="审计机构名称"
    )
    audit_conclusion: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="审计结论"
    )
    report_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="报告文件URL"
    )
    report_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA-256"
    )
    audit_period_start: Mapped[date] = mapped_column(
        Date, nullable=False, comment="审计期间开始"
    )
    audit_period_end: Mapped[date] = mapped_column(
        Date, nullable=False, comment="审计期间结束"
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否公开展示"
    )
    view_permission: Mapped[str] = mapped_column(
        String(16), default=ViewPermission.DIAMOND.value,
        comment="public / gold / diamond / board"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending",
        comment="pending / active / expired / rejected"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 约束
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('financial', 'security', 'compliance')",
            name="ck_audit_report_type"
        ),
        CheckConstraint(
            "view_permission IN ('public', 'gold', 'diamond', 'board')",
            name="ck_audit_view_permission"
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'rejected')",
            name="ck_audit_status"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TrustAuditReport id={self.id} user_id={self.user_id} "
            f"type={self.report_type} firm={self.audit_firm}>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "report_type": self.report_type,
            "audit_firm": self.audit_firm,
            "audit_conclusion": self.audit_conclusion,
            "report_url": self.report_url,
            "report_hash": self.report_hash,
            "audit_period_start": self.audit_period_start.isoformat() if self.audit_period_start else None,
            "audit_period_end": self.audit_period_end.isoformat() if self.audit_period_end else None,
            "is_public": self.is_public,
            "view_permission": self.view_permission,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# 表4: trust_reviews — 企业评价
# =============================================================================
# PRD §3.4.2 + §5.1:
#   成交后的互评系统，一笔一笔评价，防刷机制
# =============================================================================

class TrustReview(Base):
    """企业评价

    仅订单完成后可评价，一笔订单一条评价（UNIQUE约束防重复）。
    """
    __tablename__ = "trust_reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    from_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
        comment="评价方用户ID"
    )
    to_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
        comment="被评价方用户ID"
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("orders.id"), comment="关联订单ID"
    )
    rating: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="评分 1-5"
    )
    review_text: Mapped[Optional[str]] = mapped_column(
        Text, comment="评价内容"
    )
    tags: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String(32)),
        comment="评价标签: ['交付准时', '沟通顺畅', '质量可靠']"
    )
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否匿名"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 约束
    __table_args__ = (
        UniqueConstraint(
            "from_user_id", "to_user_id", "order_id",
            name="uq_review_order"
        ),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_review_rating"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TrustReview from={self.from_user_id} to={self.to_user_id} "
            f"rating={self.rating}>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "order_id": self.order_id,
            "rating": self.rating,
            "review_text": self.review_text,
            "tags": self.tags,
            "is_anonymous": self.is_anonymous,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# 表5: trust_score_logs — 信任评分变更日志（审计追踪）
# =============================================================================
# PRD §5.1:
#   评分变更的审计追踪，区块链式哈希链防篡改
# =============================================================================

class TrustScoreLog(Base):
    """信任评分变更日志

    每次评分变更记录一条日志，支持审计追踪。
    后续可扩展为区块链式哈希链（每条记录包含上一条哈希）。
    """
    __tablename__ = "trust_score_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    score_before: Mapped[Optional[float]] = mapped_column(
        Float, comment="变更前评分"
    )
    score_after: Mapped[Optional[float]] = mapped_column(
        Float, comment="变更后评分"
    )
    change_reason: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="变更原因: new_qualification / trade_completed / review_submitted / "
                "expiry / dispute_resolved / scheduled_recalc / manual_adjust"
    )
    change_detail: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, comment="变更明细（变更的子指标、衰减因子等）"
    )
    previous_log_hash: Mapped[Optional[str]] = mapped_column(
        String(64), comment="上一条日志的SHA-256哈希（区块链式链）"
    )
    this_log_hash: Mapped[Optional[str]] = mapped_column(
        String(64), comment="本条日志的SHA-256哈希"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<TrustScoreLog user={self.user_id} "
            f"reason={self.change_reason} "
            f"delta={self.score_after - self.score_before if self.score_after is not None and self.score_before is not None else None}>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "change_reason": self.change_reason,
            "change_detail": self.change_detail,
            "previous_log_hash": self.previous_log_hash,
            "this_log_hash": self.this_log_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 导出所有模型 ──────────────────────────────────────────────────────────

__all__ = [
    "Base",
    "TrustQualification",
    "TrustScoreSnapshot",
    "TrustAuditReport",
    "TrustReview",
    "TrustScoreLog",
    "QualificationStatus",
    "VerificationLevel",
    "AuditReportType",
    "ViewPermission",
    "TrustLevelEnum",
]
