"""链客宝 — 审计日志 API
=========================
审计日志的 HTTP 接口层。

端点:
  GET  /api/v1/audit/logs                — 日志查询(分页+筛选)
  GET  /api/v1/audit/logs/user/{user_id} — 用户操作历史
  GET  /api/v1/audit/logs/recent         — 最近24h操作
  GET  /api/v1/audit/logs/export         — 导出为 CSV
  DELETE /api/v1/audit/logs/cleanup      — 清理过期日志
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.audit_service import AuditService

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/v1/audit", tags=["审计日志"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================

class AuditLogResponse(BaseModel):
    """审计日志记录响应"""
    id: int
    user_id: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    detail: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    result: str
    created_at: Optional[str] = None

    @classmethod
    def from_orm(cls, log) -> "AuditLogResponse":
        d = log.to_dict() if hasattr(log, "to_dict") else log
        if isinstance(d, dict):
            return cls(**d)
        return cls(**log)


class PaginatedResponse(BaseModel):
    """分页查询响应"""
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CleanupResponse(BaseModel):
    """清理操作响应"""
    archived_count: int
    deleted_count: int
    archive_file: str


# ===================================================================
# GET /api/v1/audit/logs — 日志查询(分页+筛选)
# ===================================================================

@router.get("/logs", response_model=PaginatedResponse)
async def query_logs(
    user_id: Optional[str] = Query(None, description="按用户ID筛选"),
    action: Optional[str] = Query(None, description="按操作类型筛选"),
    resource_type: Optional[str] = Query(None, description="按资源类型筛选"),
    resource_id: Optional[str] = Query(None, description="按资源ID筛选"),
    result: Optional[str] = Query(None, description="按结果筛选 (success/failure)"),
    date_from: Optional[str] = Query(None, description="起始时间 (ISO 格式)"),
    date_to: Optional[str] = Query(None, description="截止时间 (ISO 格式)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """分页查询审计日志，支持多条件筛选"""
    filters = {}
    if user_id:
        filters["user_id"] = user_id
    if action:
        filters["action"] = action
    if resource_type:
        filters["resource_type"] = resource_type
    if resource_id:
        filters["resource_id"] = resource_id
    if result:
        filters["result"] = result
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    service = AuditService(db)
    return service.query(filters=filters, page=page, page_size=page_size)


# ===================================================================
# GET /api/v1/audit/logs/user/{user_id} — 用户操作历史
# ===================================================================

@router.get("/logs/user/{user_id}", response_model=list[AuditLogResponse])
async def get_user_logs(
    user_id: str,
    limit: int = Query(50, ge=1, le=500, description="返回条数上限"),
    db: Session = Depends(get_db),
):
    """获取指定用户的操作历史（最近优先）"""
    service = AuditService(db)
    logs = service.get_by_user(user_id, limit=limit)
    return [AuditLogResponse.from_orm(log) for log in logs]


# ===================================================================
# GET /api/v1/audit/logs/recent — 最近操作
# ===================================================================

@router.get("/logs/recent", response_model=list[AuditLogResponse])
async def get_recent_logs(
    hours: int = Query(24, ge=1, le=720, description="回溯小时数"),
    db: Session = Depends(get_db),
):
    """获取最近指定小时内的所有操作"""
    service = AuditService(db)
    logs = service.get_recent(hours=hours)
    return [AuditLogResponse.from_orm(log) for log in logs]


# ===================================================================
# GET /api/v1/audit/logs/export — 导出 CSV
# ===================================================================

@router.get("/logs/export", response_class=PlainTextResponse)
async def export_logs_csv(
    user_id: Optional[str] = Query(None, description="按用户ID筛选"),
    action: Optional[str] = Query(None, description="按操作类型筛选"),
    resource_type: Optional[str] = Query(None, description="按资源类型筛选"),
    result: Optional[str] = Query(None, description="按结果筛选"),
    date_from: Optional[str] = Query(None, description="起始时间"),
    date_to: Optional[str] = Query(None, description="截止时间"),
    db: Session = Depends(get_db),
):
    """导出审计日志为 CSV 文件"""
    filters = {}
    if user_id:
        filters["user_id"] = user_id
    if action:
        filters["action"] = action
    if resource_type:
        filters["resource_type"] = resource_type
    if result:
        filters["result"] = result
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    service = AuditService(db)
    csv_content = service.export_csv(filters=filters)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


# ===================================================================
# DELETE /api/v1/audit/logs/cleanup — 清理过期日志
# ===================================================================

@router.delete("/logs/cleanup", response_model=CleanupResponse)
async def cleanup_logs(
    keep_days: int = Query(90, ge=1, le=365, description="保留天数"),
    db: Session = Depends(get_db),
):
    """清理超过指定保留天数的审计日志（归档后删除）"""
    service = AuditService(db)
    result = service.cleanup(keep_days=keep_days)
    return CleanupResponse(**result)


# ===================================================================
# GET /api/v1/audit/logs/stats — 操作统计
# ===================================================================

@router.get("/logs/stats")
async def get_log_stats(
    date_from: Optional[str] = Query(None, description="起始时间"),
    date_to: Optional[str] = Query(None, description="截止时间"),
    db: Session = Depends(get_db),
):
    """按操作类型分组统计审计日志"""
    service = AuditService(db)
    since = None
    until = None
    if date_from:
        try:
            since = datetime.fromisoformat(date_from)
        except (ValueError, TypeError):
            pass
    if date_to:
        try:
            until = datetime.fromisoformat(date_to)
        except (ValueError, TypeError):
            pass
    stats = service.count_by_action(since=since, until=until)
    return {"stats": stats}
