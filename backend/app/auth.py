"""
链客宝 — 认证适配层
======================
为开发者门户等模块提供 get_current_user 依赖注入。

在 chainke-full 中，JWT 认证由 AuthMiddleware 中间件统一处理（验证
Authorization header 并将 JWT payload 注入 request.state.user）。

与源项目 backend/app/auth.py 兼容的
get_current_user 函数签名，从中提取用户信息。

使用方式（FastAPI 依赖注入）:
    @router.get("/example")
    def example(current_user = Depends(get_current_user)):
        return {"user_id": current_user.id}
"""

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)


class CurrentUser:
    """当前用户信息对象 (轻量适配层)

    替代源项目的 User ORM 模型。在 chainke-full 中用户由 JWT sub 标识
    (字符串)，而非数据库自增 ID。
    """

    def __init__(self, sub: str, payload: dict[str, Any]):
        self._payload = payload
        self.id: str = sub  # JWT sub = 用户名/用户标识符
        self.username: str = sub
        self.role: str = payload.get("role", "viewer")

    def __repr__(self) -> str:
        return f"<CurrentUser(id={self.id}, role={self.role})>"


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),  # 保留 db 参数，兼容调用方签名
) -> CurrentUser:
    """从请求上下文中提取当前用户。

    适配源项目 auth.get_current_user 签名:
      - source: (credentials=Depends(security), db=Depends(get_db)) -> User
      - adapter: (request: Request, db=Depends(get_db)) -> CurrentUser

    在 chainke-full 中，AuthMiddleware 已将 JWT payload 注入
    request.state.user。本函数直接读取此值。

    Raises:
      HTTPException 401 — 未认证或令牌无效
    """
    payload: dict[str, Any] | None = getattr(request.state, "user", None)
    if payload is None:
        logger.warning("[Auth] request.state.user 为空 — 请求未通过 AuthMiddleware")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌或令牌无效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub: str | None = payload.get("sub")
    if not sub:
        logger.warning("[Auth] JWT payload 缺少 sub 字段: %s", payload)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌 (缺少用户标识)",
        )

    logger.debug("[Auth] 用户已认证: sub=%s, role=%s", sub, payload.get("role"))
    return CurrentUser(sub=sub, payload=payload)
