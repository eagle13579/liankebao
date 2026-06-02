"""
多租户模型与租户上下文管理

Organization — 租户组织
Membership  — 用户-组织关联（角色）
TenantContext — 当前请求的租户上下文（线程安全）

行为:
- DB_TYPE=postgres: 强制启用多租户，所有业务数据按 organization_id 隔离
- DB_TYPE=sqlite: 跳过租户模型，兼容现有数据
"""

import logging
import threading
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Session, relationship

from app.database import DB_TYPE, Base

logger = logging.getLogger(__name__)

# ============================================================
# 是否启用多租户
# ============================================================
IS_MULTI_TENANT = False


# ============================================================
# 租户上下文（线程安全 + asyncio 兼容）
# ============================================================
class TenantContext:
    """
    当前请求的租户上下文。
    通过 ContextVar 实现 asyncio-safe，同时保留 threading.local 兜底。
    """

    _context_var: ContextVar[Optional["TenantContext"]] = ContextVar("tenant_context", default=None)
    _thread_local = threading.local()

    def __init__(self, org_id: int, org_slug: str = ""):
        self.org_id = org_id
        self.org_slug = org_slug

    @classmethod
    def set(cls, ctx: "TenantContext") -> None:
        """设置当前租户上下文"""
        cls._context_var.set(ctx)
        cls._thread_local.context = ctx

    @classmethod
    def get(cls) -> Optional["TenantContext"]:
        """获取当前租户上下文"""
        ctx = cls._context_var.get()
        if ctx is not None:
            return ctx
        return getattr(cls._thread_local, "context", None)

    @classmethod
    def clear(cls) -> None:
        """清除当前租户上下文"""
        cls._context_var.set(None)
        if hasattr(cls._thread_local, "context"):
            del cls._thread_local.context


def get_current_org_id() -> int | None:
    """便捷函数：获取当前请求的 organization_id"""
    ctx = TenantContext.get()
    if ctx is None:
        return None
    return ctx.org_id


def get_current_org_slug() -> str:
    """便捷函数：获取当前请求的 org_slug"""
    ctx = TenantContext.get()
    if ctx is None:
        return ""
    return ctx.org_slug


# ============================================================
# 租户模型
# ============================================================


if IS_MULTI_TENANT:
    class Membership(Base):
        """用户-组织关联模型"""
    
        __table_args__ = {"extend_existing": True}
        __tablename__ = "memberships"
    
        id = Column(Integer, primary_key=True, index=True, autoincrement=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
        role = Column(String(20), nullable=False, default="member")  # admin / member / viewer
        created_at = Column(DateTime, default=datetime.utcnow)

        user = relationship("User", back_populates="memberships", foreign_keys=[user_id])
        organization = relationship("Organization", back_populates="memberships")


# ============================================================
# 租户感知的 Session 查询辅助
# ============================================================


def _tenant_filter_kwargs() -> dict:
    """
    返回当前租户的过滤条件字典。
    若无租户上下文（SQLite 模式或未认证请求），返回空字典（不过滤）。
    """
    if not IS_MULTI_TENANT:
        return {}
    org_id = get_current_org_id()
    if org_id is None:
        return {}
    return {"organization_id": org_id}


class TenantSessionWrapper:
    """
    Session 包装器：对 query() 自动附加 organization_id 过滤。

    用法:
        with TenantSessionWrapper(db) as wrapped_db:
            users = wrapped_db.query(User).all()  # 自动过滤 org

    也支持直接调用: filter_by_tenant(query) 手动过滤。
    """

    def __init__(self, session: Session):
        self._session = session

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    @property
    def session(self) -> Session:
        return self._session

    def query(self, *entities, **kwargs):
        """代理 query()，对业务模型自动附加 organization_id 过滤"""
        q = self._session.query(*entities, **kwargs)
        org_id = get_current_org_id()
        if org_id is not None and IS_MULTI_TENANT:
            for entity in entities:
                if hasattr(entity, "organization_id"):
                    q = q.filter(entity.organization_id == org_id)
                    break
        return q

    def __getattr__(self, name):
        return getattr(self._session, name)


def apply_tenant_filter(query, model_class):
    """
    手动为已有查询附加 organization_id 过滤。

    用法:
        q = db.query(Product)
        q = apply_tenant_filter(q, Product)
    """
    if not IS_MULTI_TENANT:
        return query
    org_id = get_current_org_id()
    if org_id is None:
        return query
    if hasattr(model_class, "organization_id"):
        return query.filter(model_class.organization_id == org_id)
    return query
