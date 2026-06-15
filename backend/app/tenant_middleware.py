"""
租户中间件 — 从请求头或 JWT 中提取当前租户上下文

提取顺序:
  1. X-Org-ID 请求头（最高优先级）
  2. X-Org-Slug 请求头
  3. JWT payload 中的 org_id 字段

在多租户模式下（PostgreSQL），中间件会设置 TenantContext，
后续所有 get_db() 调用自动按租户过滤数据。

在 SQLite 模式下，中间件为 no-op，不干扰现有逻辑。
"""

import logging
import os

from fastapi import Request
from jose import JWTError, jwt

from app.database import is_multi_tenant
from app.tenant import TenantContext

logger = logging.getLogger(__name__)

# JWT SECRET（与 auth.py 保持一致）
SECRET_KEY = os.environ.get("SECRET_KEY", "liankebao-jwt-secret-key-2024-nous")
ALGORITHM = "HS256"


def _extract_org_id_from_jwt(request: Request) -> int | None:
    """从 JWT Authorization header 中提取 org_id"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        org_id = payload.get("org_id")
        if org_id is not None:
            return int(org_id)
    except (JWTError, ValueError, TypeError):
        pass
    return None


def _extract_org_id_from_header(request: Request) -> int | None:
    """从 X-Org-ID 请求头提取 org_id"""
    raw = request.headers.get("X-Org-ID", "")
    if raw:
        try:
            return int(raw)
        except (ValueError, TypeError):
            logger.warning(f"无效的 X-Org-ID 请求头值: {raw}")
    return None


def _extract_org_slug(request: Request) -> str | None:
    """从 X-Org-Slug 请求头提取 org_slug"""
    return request.headers.get("X-Org-Slug", "") or None


class TenantMiddleware:
    """
    FastAPI 中间件：提取当前请求的租户上下文。

    1. 优先使用 X-Org-ID 请求头
    2. 其次使用 X-Org-Slug 请求头
    3. 再次从 JWT payload 中读取 org_id

    SQLite 模式下跳过处理。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not is_multi_tenant():
            # SQLite 模式：跳过租户逻辑
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        org_id: int | None = None
        org_slug: str | None = None

        # 1. 从请求头提取
        org_id = _extract_org_id_from_header(request)
        org_slug = _extract_org_slug(request)

        # 2. 从 JWT 提取
        if org_id is None:
            org_id = _extract_org_id_from_jwt(request)

        # 3. 设置租户上下文
        if org_id is not None:
            TenantContext.set(TenantContext(org_id=org_id, org_slug=org_slug or ""))
        elif org_slug is not None:
            # 如果只有 slug，标记一个占位 slug，后续查询时可以解析
            TenantContext.set(TenantContext(org_id=0, org_slug=org_slug))
        else:
            logger.debug("未找到租户信息，请求将在无租户上下文中处理")
            TenantContext.clear()

        try:
            await self.app(scope, receive, send)
        finally:
            # 请求完成后清理租户上下文
            TenantContext.clear()
