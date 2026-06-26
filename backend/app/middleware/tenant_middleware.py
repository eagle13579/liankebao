"""
TenantMiddleware — 多租户 SQLite 兼容层
=========================================
为链客宝提供行级租户隔离中间件，兼容 SQLite 和 PostgreSQL。

功能：
1. 从请求头 `X-Org-ID` 提取组织 ID（最高优先级）
2. 若 X-Org-ID 缺失，从 JWT payload（request.state.user）中的 org_id 声明提取
3. 将解析后的 org_id 注入 request.state.org_id
4. 提供快捷函数 `get_current_org_id()` 供路由层和查询层使用

设计原则：
- SQLite 开发模式下，DB_TYPE != "postgres"，six_degrees.py 中的多租户
  FK 约束默认关闭。此中间件作为兼容层，使 SQLite 也支持行级租户隔离，
  通过 application-level 的 org_id 过滤实现。
- 不修改现有 main.py 注册 —— 由使用者自行注册。

用法:
    from app.middleware.tenant_middleware import TenantMiddleware
    app.add_middleware(TenantMiddleware)

依赖:
    - AuthMiddleware 需要在 TenantMiddleware 之前注册（如果希望从 JWT 提取 org_id）
    - 如果仅使用 X-Org-ID 请求头，不依赖 AuthMiddleware
"""

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("chainke.tenant")

# ===================================================================
# 请求头配置
# ===================================================================
ORG_ID_HEADER = "X-Org-ID"  # 请求头名称

# ===================================================================
# JWT 声明中的 org_id 字段名
# ===================================================================
JWT_ORG_ID_CLAIM = "org_id"  # JWT payload 中携带组织 ID 的字段

# ===================================================================
# 白名单路径（不注入租户上下文）
# ===================================================================
# 精确匹配白名单
TENANT_WHITELIST_PATHS: frozenset[str] = frozenset({
    "/api/health",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
})

# 前缀匹配白名单
TENANT_WHITELIST_PREFIXES: frozenset[str] = frozenset({
    "/api/auth/",       # 登录/注册等匿名端点
})


class TenantMiddleware(BaseHTTPMiddleware):
    """
    多租户 SQLite 兼容层中间件

    从请求头 X-Org-ID 或 JWT 声明中提取组织 ID，注入 request.state，
    供下游路由和查询层做行级租户隔离过滤。

    中间件执行顺序建议（main.py）:
        app.add_middleware(CORSMiddleware)
        app.add_middleware(TenantMiddleware)   # 在 AuthMiddleware 之前或之后均可
        app.add_middleware(AuthMiddleware)     # 如果要从 JWT 提取 org_id，TenantMiddleware 应在 AuthMiddleware 之后
        ...

    注意: TenantMiddleware 本身不验证权限，仅负责提取和注入 org_id。
    实际的行级过滤由各路由/service 层通过 request.state.org_id 实现。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── 白名单路径 — 直接放行，不注入租户上下文 ──────────
        path = request.url.path
        if path in TENANT_WHITELIST_PATHS:
            return await call_next(request)

        for prefix in TENANT_WHITELIST_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # ── 解析 org_id ─────────────────────────────────────
        org_id = self._resolve_org_id(request)

        # ── 注入 request.state ──────────────────────────────
        request.state.org_id = org_id

        # 为兼容性，同时设置 tenant_id 别名
        request.state.tenant_id = org_id

        if org_id is not None:
            logger.debug(
                "[Tenant] 注入 org_id=%s, path=%s, method=%s",
                org_id, path, request.method,
            )
        else:
            logger.debug(
                "[Tenant] 未找到 org_id（无租户上下文）, path=%s, method=%s",
                path, request.method,
            )

        return await call_next(request)

    @staticmethod
    def _resolve_org_id(request: Request) -> int | str | None:
        """
        解析组织 ID，优先级：

        1. X-Org-ID 请求头（最高优先级，显式指定）
        2. JWT payload 中的 org_id 声明（需 AuthMiddleware 已注入 request.state.user）
        3. 均不存在时返回 None
        """
        # ── 方式一：从请求头 X-Org-ID 提取 ─────────────────
        header_org_id = request.headers.get(ORG_ID_HEADER)
        if header_org_id is not None and header_org_id.strip():
            return _normalize_org_id(header_org_id.strip())

        # ── 方式二：从 JWT payload 提取 ────────────────────
        user_payload: dict[str, Any] | None = getattr(request.state, "user", None)
        if user_payload is not None and isinstance(user_payload, dict):
            jwt_org_id = user_payload.get(JWT_ORG_ID_CLAIM)
            if jwt_org_id is not None:
                return _normalize_org_id(jwt_org_id)

        return None


def _normalize_org_id(value: Any) -> int | str | None:
    """
    归一化组织 ID 值：如果是纯数字字符串转为 int，否则保持原样。

    SQLite 中 org_id 通常为整数，但兼容字符串形式的组织标识符。
    """
    if value is None:
        return None

    # 如果是整数，直接返回
    if isinstance(value, int):
        return value

    # 如果是纯数字字符串，转为 int
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())

    # 其他情况（UUID、slug 等）保持字符串
    return str(value)


# ===================================================================
# 快捷函数
# ===================================================================

def get_current_org_id(request: Request) -> int | str | None:
    """
    从请求上下文中获取当前组织 ID。

    用法（路由层）:
        @router.get("/api/contacts")
        async def list_contacts(
            request: Request,
            db: Session = Depends(get_db),
        ):
            org_id = get_current_org_id(request)
            if org_id is None:
                # 多租户模式下，没有 org_id 应拒绝请求
                raise HTTPException(status_code=400, detail="缺少组织ID")
            contacts = db.query(Contact).filter(
                Contact.org_id == org_id
            ).all()
            ...
    """
    org_id: int | str | None = getattr(request.state, "org_id", None)
    return org_id


def is_multi_tenant_active(request: Request) -> bool:
    """
    检查当前请求是否处于多租户模式（即是否有有效的 org_id）。

    可用于条件性跳过租户过滤（如超级管理员/跨租户查询）。
    """
    return get_current_org_id(request) is not None
