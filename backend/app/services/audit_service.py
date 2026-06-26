"""链客宝 — 审计日志服务层
=============================
AuditService: 审计日志的业务逻辑层。

职责:
  1. 记录审计日志 (log)
  2. 分页查询审计日志 (query)
  3. 查询用户操作历史 (get_by_user)
  4. 查询资源变更历史 (get_by_resource)
  5. 获取最近操作 (get_recent)
  6. 导出为 CSV (export_csv)
  7. 自动清理过期日志 (cleanup)

装饰器:
  @audit_log(action, resource_type) — 自动记录函数调用

使用方式:
  from app.services.audit_service import AuditService, audit_log
  service = AuditService(db)
  log_entry = service.log(...)
"""

import csv
import functools
import inspect
import io
import json
import logging
import os
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from sqlalchemy import func as sa_func, case as sa_case
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


# ===================================================================
# 操作/资源类型常量
# ===================================================================

class Actions:
    """预定义操作类型"""
    # 用户操作
    LOGIN = "login"
    REGISTER = "register"
    UPDATE_PROFILE = "update_profile"
    CREATE_CARD = "create_card"
    START_MATCH = "start_match"
    SUBMIT_FEEDBACK = "submit_feedback"
    # 管理操作
    ADMIN_SET_FLAG = "admin_set_flag"
    ADMIN_UPDATE_CONFIG = "admin_update_config"
    ADMIN_DELETE_DATA = "admin_delete_data"
    # 敏感操作
    PAYMENT = "payment"
    API_KEY_CHANGE = "api_key_change"
    PERMISSION_CHANGE = "permission_change"


class ResourceTypes:
    """预定义资源类型"""
    USER = "user"
    CARD = "card"
    MATCH = "match"
    FEEDBACK = "feedback"
    CONFIG = "config"
    PAYMENT = "payment"
    API_KEY = "api_key"
    PERMISSION = "permission"


# ===================================================================
# AuditService
# ===================================================================

class AuditService:
    """审计日志服务"""

    # 默认保留天数
    DEFAULT_RETENTION_DAYS = 90

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # log — 记录一条审计日志
    # ------------------------------------------------------------------
    def log(
        self,
        user_id: str,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        detail: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        result: str = "success",
    ) -> AuditLog:
        """记录一条审计日志

        Args:
            user_id:      操作用户 ID
            action:       操作类型 (如 login, create_card, payment)
            resource_type:资源类型 (可选，如 user, card, match)
            resource_id:  资源 ID (可选)
            detail:       详情 JSON (可选)
            ip_address:   客户端 IP 地址 (可选)
            user_agent:   客户端 User-Agent (可选)
            result:       操作结果: success/failure (默认 success)

        Returns:
            AuditLog ORM 实例
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        if not action or not action.strip():
            raise ValueError("action 不能为空")
        if result not in ("success", "failure"):
            raise ValueError(f"result 必须是 success 或 failure，收到: {result}")

        audit_log = AuditLog(
            user_id=user_id.strip(),
            action=action.strip(),
            resource_type=resource_type.strip() if resource_type else None,
            resource_id=resource_id.strip() if resource_id else None,
            detail=detail or {},
            ip_address=ip_address,
            user_agent=user_agent,
            result=result,
        )
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        return audit_log

    # ------------------------------------------------------------------
    # query — 分页查询审计日志
    # ------------------------------------------------------------------
    def query(
        self,
        filters: Optional[dict] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页查询审计日志

        Args:
            filters:  筛选条件字典，支持键:
                      user_id, action, resource_type, resource_id, result,
                      date_from, date_to (ISO 格式字符串)
            page:     页码 (从 1 开始)
            page_size:每页条数 (默认 20, 最大 100)

        Returns:
            dict: { "items": [...], "total": int, "page": int,
                    "page_size": int, "total_pages": int }
        """
        filters = filters or {}
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        q = self.db.query(AuditLog)

        # 应用筛选条件
        if "user_id" in filters and filters["user_id"]:
            q = q.filter(AuditLog.user_id == filters["user_id"])
        if "action" in filters and filters["action"]:
            q = q.filter(AuditLog.action == filters["action"])
        if "resource_type" in filters and filters["resource_type"]:
            q = q.filter(AuditLog.resource_type == filters["resource_type"])
        if "resource_id" in filters and filters["resource_id"]:
            q = q.filter(AuditLog.resource_id == filters["resource_id"])
        if "result" in filters and filters["result"]:
            q = q.filter(AuditLog.result == filters["result"])
        if "date_from" in filters and filters["date_from"]:
            try:
                dt_from = datetime.fromisoformat(filters["date_from"])
                q = q.filter(AuditLog.created_at >= dt_from)
            except (ValueError, TypeError):
                pass
        if "date_to" in filters and filters["date_to"]:
            try:
                dt_to = datetime.fromisoformat(filters["date_to"])
                q = q.filter(AuditLog.created_at <= dt_to)
            except (ValueError, TypeError):
                pass

        # 总数
        total = q.count()

        # 分页
        offset = (page - 1) * page_size
        items = (
            q.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }

    # ------------------------------------------------------------------
    # get_by_user — 查询用户操作历史
    # ------------------------------------------------------------------
    def get_by_user(self, user_id: str, limit: int = 50) -> list[AuditLog]:
        """获取指定用户的操作历史（最近优先）

        Args:
            user_id: 用户 ID
            limit:   返回条数上限 (默认 50)

        Returns:
            AuditLog 实例列表
        """
        return (
            self.db.query(AuditLog)
            .filter(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .all()
        )

    # ------------------------------------------------------------------
    # get_by_resource — 查询资源变更历史
    # ------------------------------------------------------------------
    def get_by_resource(
        self, resource_type: str, resource_id: str
    ) -> list[AuditLog]:
        """获取指定资源的所有变更历史

        Args:
            resource_type: 资源类型
            resource_id:   资源 ID

        Returns:
            AuditLog 实例列表（按时间倒序）
        """
        return (
            self.db.query(AuditLog)
            .filter(
                AuditLog.resource_type == resource_type,
                AuditLog.resource_id == resource_id,
            )
            .order_by(AuditLog.created_at.desc())
            .all()
        )

    # ------------------------------------------------------------------
    # get_recent — 获取最近 N 小时的操作
    # ------------------------------------------------------------------
    def get_recent(self, hours: int = 24) -> list[AuditLog]:
        """获取最近指定小时内的所有操作

        Args:
            hours: 回溯小时数 (默认 24)

        Returns:
            AuditLog 实例列表（按时间倒序）
        """
        since = datetime.now(dt_timezone.utc) - timedelta(hours=hours)
        return (
            self.db.query(AuditLog)
            .filter(AuditLog.created_at >= since)
            .order_by(AuditLog.created_at.desc())
            .all()
        )

    # ------------------------------------------------------------------
    # export_csv — 导出审计日志为 CSV
    # ------------------------------------------------------------------
    def export_csv(self, filters: Optional[dict] = None) -> str:
        """导出审计日志为 CSV 字符串

        Args:
            filters: 筛选条件（同 query 方法）

        Returns:
            CSV 格式字符串
        """
        filters = filters or {}
        q = self.db.query(AuditLog)

        # 应用筛选
        if "user_id" in filters and filters["user_id"]:
            q = q.filter(AuditLog.user_id == filters["user_id"])
        if "action" in filters and filters["action"]:
            q = q.filter(AuditLog.action == filters["action"])
        if "resource_type" in filters and filters["resource_type"]:
            q = q.filter(AuditLog.resource_type == filters["resource_type"])
        if "result" in filters and filters["result"]:
            q = q.filter(AuditLog.result == filters["result"])
        if "date_from" in filters and filters["date_from"]:
            try:
                dt_from = datetime.fromisoformat(filters["date_from"])
                q = q.filter(AuditLog.created_at >= dt_from)
            except (ValueError, TypeError):
                pass
        if "date_to" in filters and filters["date_to"]:
            try:
                dt_to = datetime.fromisoformat(filters["date_to"])
                q = q.filter(AuditLog.created_at <= dt_to)
            except (ValueError, TypeError):
                pass

        items = q.order_by(AuditLog.created_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "用户ID", "操作类型", "资源类型", "资源ID",
            "详情", "IP地址", "User-Agent", "结果", "创建时间",
        ])
        for item in items:
            writer.writerow([
                item.id,
                item.user_id,
                item.action,
                item.resource_type or "",
                item.resource_id or "",
                json.dumps(item.detail or {}, ensure_ascii=False),
                item.ip_address or "",
                item.user_agent or "",
                item.result,
                item.created_at.isoformat() if item.created_at else "",
            ])

        return output.getvalue()

    # ------------------------------------------------------------------
    # cleanup — 清理过期日志（归档 + 删除）
    # ------------------------------------------------------------------
    def cleanup(
        self,
        keep_days: int = DEFAULT_RETENTION_DAYS,
        archive_dir: Optional[str] = None,
    ) -> dict:
        """清理超过保留天数的审计日志

        将过期日志归档到 JSON 文件，然后从数据库中删除。

        Args:
            keep_days:   保留天数 (默认 90)
            archive_dir: 归档目录路径。为 None 时归档到当前工作目录的
                         audit_archive/ 子目录。

        Returns:
            dict: { "archived_count": int, "deleted_count": int,
                    "archive_file": str }
        """
        cutoff = datetime.now(dt_timezone.utc) - timedelta(days=keep_days)

        # 查询过期日志
        expired = (
            self.db.query(AuditLog)
            .filter(AuditLog.created_at < cutoff)
            .order_by(AuditLog.created_at.asc())
            .all()
        )

        if not expired:
            return {
                "archived_count": 0,
                "deleted_count": 0,
                "archive_file": "",
            }

        # 序列化为字典列表
        records = [item.to_dict() for item in expired]

        # 归档到 JSON 文件
        if archive_dir is None:
            archive_dir = os.path.join(os.getcwd(), "audit_archive")
        os.makedirs(archive_dir, exist_ok=True)

        archive_filename = f"audit_logs_{cutoff.strftime('%Y%m%d_%H%M%S')}.json"
        archive_path = os.path.join(archive_dir, archive_filename)

        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2, default=str)

        # 从数据库中删除过期记录
        deleted_count = len(expired)
        for record in expired:
            self.db.delete(record)
        self.db.commit()

        logger.info(
            f"审计日志清理完成: 归档 {deleted_count} 条到 {archive_path}"
        )

        return {
            "archived_count": deleted_count,
            "deleted_count": deleted_count,
            "archive_file": archive_path,
        }

    # ------------------------------------------------------------------
    # count_by_action — 按操作类型统计
    # ------------------------------------------------------------------
    def count_by_action(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[dict]:
        """按操作类型分组统计

        Args:
            since: 起始时间（可选）
            until: 截止时间（可选）

        Returns:
            list[dict]: [{"action": str, "count": int, "success_count": int,
                          "failure_count": int}, ...]
        """
        q = self.db.query(
            AuditLog.action,
            sa_func.count(AuditLog.id).label("total"),
            sa_func.sum(
                sa_case((AuditLog.result == "success", 1), else_=0)
            ).label("success_count"),
            sa_func.sum(
                sa_case((AuditLog.result == "failure", 1), else_=0)
            ).label("failure_count"),
        )

        if since:
            q = q.filter(AuditLog.created_at >= since)
        if until:
            q = q.filter(AuditLog.created_at <= until)

        rows = q.group_by(AuditLog.action).all()

        return [
            {
                "action": row.action,
                "count": row.total or 0,
                "success_count": row.success_count or 0,
                "failure_count": row.failure_count or 0,
            }
            for row in rows
        ]


# ===================================================================
# audit_log 装饰器 — 自动记录函数调用
# ===================================================================

def audit_log(action: str, resource_type: Optional[str] = None):
    """自动审计日志装饰器

    自动捕获被装饰函数的 user_id 和 resource_id 参数，
    并记录函数调用为审计日志。

    用法:
        @audit_log(action="create_card", resource_type="card")
        def create_card(user_id: str, ...):
            ...

    支持:
        - 位置参数和关键字参数中的 user_id
        - 关键字参数中的 resource_id
        - 自动检测 success/failure (通过异常)
        - 可选的 user_id_param / resource_id_param 定制参数名
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 提取 user_id: 优先从 kwargs，其次从 args 中按参数名匹配
            sig = inspect.signature(func)
            bound = None
            try:
                bound = sig.bind_partial(*args, **kwargs)
            except (TypeError, ValueError):
                pass

            user_id = None
            resource_id = None

            if bound is not None:
                if "user_id" in bound.arguments:
                    user_id = bound.arguments["user_id"]
                if "resource_id" in bound.arguments:
                    resource_id = bound.arguments["resource_id"]

            # 如果 bound 失败，从 kwargs 中尝试
            if user_id is None:
                user_id = kwargs.get("user_id")
            if resource_id is None:
                resource_id = kwargs.get("resource_id")

            # 执行函数
            try:
                result = func(*args, **kwargs)
                # 尝试获取 db 会话
                db = _extract_db(args, kwargs)
                if db is not None and user_id:
                    service = AuditService(db)
                    service.log(
                        user_id=str(user_id) if user_id else "unknown",
                        action=action,
                        resource_type=resource_type,
                        resource_id=str(resource_id) if resource_id else None,
                        result="success",
                    )
                return result
            except Exception as e:
                # 记录失败日志
                db = _extract_db(args, kwargs)
                if db is not None and user_id:
                    service = AuditService(db)
                    service.log(
                        user_id=str(user_id) if user_id else "unknown",
                        action=action,
                        resource_type=resource_type,
                        resource_id=str(resource_id) if resource_id else None,
                        detail={"error": str(e)},
                        result="failure",
                    )
                raise

        return wrapper

    return decorator


def _extract_db(args, kwargs) -> Optional[Session]:
    """从函数参数或 self 中提取 SQLAlchemy Session"""
    # 检查 kwargs 中是否有 db 参数
    db = kwargs.get("db")
    if db is not None and isinstance(db, Session):
        return db

    # 检查 args 中是否有 Session 实例
    for arg in args:
        if isinstance(arg, Session):
            return arg

    # 检查 args[0] 是否为 self 且具有 db 属性（绑定方法场景）
    if args and hasattr(args[0], "db") and isinstance(args[0].db, Session):
        return args[0].db

    return None
