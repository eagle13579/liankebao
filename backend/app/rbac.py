"""
RBAC 权限体系 — 基于现有多租户 Membership 角色模型

角色层次 (定义在 tenant.Membership.role):
  - admin  — 系统管理员，拥有全部权限
  - member — 正式成员，可读写核心业务数据
  - viewer — 只读成员，仅可查看

Permission 注册表:
  { permission_name: list[allowed_roles] }

基础设施权限:
  user.read, user.write, product.read, product.write,
  order.read, order.write, payment.read, payment.write,
  admin.access
"""

import logging
from functools import wraps
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

# ============================================================
# Permission 注册表
# ============================================================

PERMISSION_REGISTRY: dict[str, list[str]] = {
    # ── 用户管理 ──
    "user.read": ["admin", "member", "viewer"],
    "user.write": ["admin", "member"],
    # ── 产品 ──
    "product.read": ["admin", "member", "viewer"],
    "product.write": ["admin", "member"],
    # ── 订单 ──
    "order.read": ["admin", "member", "viewer"],
    "order.write": ["admin", "member"],
    # ── 支付 ──
    "payment.read": ["admin", "member"],
    "payment.write": ["admin", "member"],
    # ── 管理后台 ──
    "admin.access": ["admin"],
}

# ============================================================
# 角色层次（用于传播权限）
# ============================================================

ROLE_HIERARCHY: dict[str, set[str]] = {
    "admin": {"admin", "member", "viewer"},
    "member": {"member", "viewer"},
    "viewer": {"viewer"},
}


def get_effective_roles(user_role: str) -> set[str]:
    """根据角色层次，返回用户拥有的所有有效角色集合"""
    return ROLE_HIERARCHY.get(user_role, {user_role})


def user_has_permission(user_role: str, permission: str) -> bool:
    """检查用户角色是否拥有指定权限"""
    allowed_roles = PERMISSION_REGISTRY.get(permission)
    if allowed_roles is None:
        logger.warning(f"未注册的权限: {permission}")
        return False
    effective = get_effective_roles(user_role)
    return bool(set(allowed_roles) & effective)


# ============================================================
# 从 Membership 表获取角色（多租户感知）
# ============================================================


def get_tenant_role(
    user: User,
    org_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> Optional[str]:
    """
    从 Membership 表获取用户在指定组织中的角色。

    优先级:
      1. Membership 表中匹配 org_id 的 role
      2. 若 org_id 为 None 或未匹配，回退到 user.role 字段
    """
    # 如果没有传入 org_id，尝试从请求上下文获取
    if org_id is None:
        try:
            from app.tenant import get_current_org_id

            org_id = get_current_org_id()
        except Exception:
            pass

    # 如果有 db 且 org_id 存在，查 Membership
    if db is not None and org_id is not None:
        try:
            from app.tenant import Membership

            membership = (
                db.query(Membership)
                .filter(
                    Membership.user_id == user.id,
                    Membership.org_id == org_id,
                )
                .first()
            )
            if membership and membership.role:
                return membership.role
        except Exception:
            pass

    # 回退到 user.role 字段
    return user.role if user.role else "viewer"


# ============================================================
# 依赖注入: require_roles(["admin"])
# ============================================================


def require_roles(
    allowed_roles: list[str],
    *,
    permission: Optional[str] = None,
) -> Callable:
    """
    FastAPI 依赖注入工厂 — 检查当前用户的角色是否满足要求。

    用法:
        @router.get("/admin/dashboard")
        def dashboard(admin: User = Depends(require_roles(["admin"]))):
            ...

        @router.get("/orders")
        def orders(user: User = Depends(require_roles(["admin", "member", "viewer"]))):
            ...

    参数:
        allowed_roles: 允许的角色列表
        permission:    可选，当指定时还会额外检查该权限
    """

    def role_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
        request: Request = None,
    ) -> User:
        # 获取用户在组织中的角色
        role = get_tenant_role(current_user, db=db)

        # 角色层次展开
        effective = get_effective_roles(role)

        # 检查角色是否在允许列表内
        if not (set(allowed_roles) & effective):
            logger.warning(
                "rbac_access_denied",
                extra={
                    "user_id": current_user.id,
                    "username": current_user.username,
                    "role": role,
                    "allowed_roles": allowed_roles,
                    "permission": permission or "",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，需要 " + " / ".join(allowed_roles) + " 角色",
            )

        # 可选：额外检查具体权限
        if permission and not user_has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要 {permission} 权限",
            )

        # 注入角色信息到 request.state（供下游使用）
        if request is not None:
            try:
                request.state.user_role = role
                request.state.user_permissions = [
                    p for p, roles in PERMISSION_REGISTRY.items()
                    if set(roles) & effective
                ]
            except Exception:
                pass

        return current_user

    return role_checker


# ============================================================
# 装饰器: @require_permission("permission.name")
# ============================================================


def require_permission(permission: str):
    """
    装饰器 — 用于需要特定权限的路由处理函数。

    用法:
        @router.get("/admin/users")
        @require_permission("admin.access")
        def list_users(admin: User = Depends(require_roles(["admin"]))):
            ...

    注意: 这只是一个额外检查层，仍需要 require_roles 依赖注入。
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中提取 current_user
            current_user = kwargs.get("current_user") or kwargs.get("admin")
            if current_user is None:
                # 尝试从 request.state 获取
                request = kwargs.get("request")
                if request and hasattr(request.state, "user_role"):
                    role = request.state.user_role
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="未认证",
                    )
            else:
                role = current_user.role

            if not user_has_permission(role, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"权限不足，需要 {permission} 权限",
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# 中间件: inject_permissions — 从 JWT 解析角色并注入 request.state
# ============================================================


async def inject_permissions(request: Request, call_next):
    """
    FastAPI 中间件 — 从 JWT/当前用户提取角色，将权限列表注入 request.state。

    注册方式 (在 main.py 中):
        app.middleware("http")(inject_permissions)

    效果:
        request.state.user_role      -> str (admin/member/viewer)
        request.state.user_permissions -> list[str] (该角色拥有的所有权限)
    """
    # 初始化默认值
    request.state.user_role = "viewer"
    request.state.user_permissions = list(
        p for p, roles in PERMISSION_REGISTRY.items()
        if "viewer" in roles
    )

    # 尝试从认证头获取用户
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        response = await call_next(request)
        return response

    token = auth_header[7:]  # 去掉 "Bearer "

    # 解析 token
    from app.auth import verify_token

    payload = verify_token(token, expected_type="access")
    if payload is None:
        response = await call_next(request)
        return response

    # 从 payload 中提取角色
    role = payload.get("role", "viewer")

    # 注入 request.state
    request.state.user_role = role
    effective = get_effective_roles(role)
    request.state.user_permissions = [
        p for p, roles in PERMISSION_REGISTRY.items()
        if set(roles) & effective
    ]

    response = await call_next(request)
    return response


# ============================================================
# 工具函数 — 获取当前用户的角色和权限列表
# ============================================================


def get_current_user_role(request: Request) -> str:
    """从 request.state 获取当前用户角色"""
    return getattr(request.state, "user_role", "viewer")


def get_current_user_permissions(request: Request) -> list[str]:
    """从 request.state 获取当前用户权限列表"""
    return getattr(request.state, "user_permissions", [])
