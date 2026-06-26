"""
AuthMiddleware — JWT 认证中间件
=================================
验证所有 /api/* 路由的 Authorization header（除白名单路径外），
保护后端 API 免受未经授权的访问。

白名单路径（免认证）:
  精确匹配:
  - GET  /api/health
  - GET  /health
  - GET  /docs
  - GET  /openapi.json
  - GET  /redoc

  前缀匹配（整段放行，由路由层的 Depends 做细粒度控制）:
  - /api/auth/*  — 登录/注册/微信登录/忘记密码等

Token 格式（支持两种）:
  1. 真实 JWT（推荐） — HS256 签名，带 exp 过期时间
  2. dev-token-{uuid4} — 开发环境兼容 token（仅开发/测试使用）

JWT 配置:
  JWT_SECRET     — 从环境变量读取（默认 chainke-dev-secret-key）
  JWT_ALGORITHM  — HS256

用法:
    app.add_middleware(AuthMiddleware)
"""

import logging
import os
import re

import jwt as pyjwt

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger("chainke.auth")

# ===================================================================
# JWT 配置
# ===================================================================
JWT_SECRET = os.getenv("JWT_SECRET", "chainke-dev-secret-key")
JWT_ALGORITHM = "HS256"

# ===================================================================
# 白名单路径（不要求认证）
# ===================================================================
# 精确匹配白名单
WHITELIST_PATHS = frozenset({
    "/api/health",
    "/api/health/error-report",
    "/api/seo/schema",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
})

# 前缀匹配白名单（以这些前缀开头的路径一律放行）
# 路由层通过 Depends(get_current_user) 做细粒度控制
WHITELIST_PREFIXES = frozenset({
    "/api/auth/",       # 登录/注册/微信登录/忘记密码等公共认证端点
})


class AuthMiddleware(BaseHTTPMiddleware):
    """
    JWT 认证中间件 — 保护除白名单外的所有 /api/* 路由

    支持两种 token 格式:
      1. 真实 JWT (HS256, 带 exp)
      2. dev-token-{uuid4} (开发环境兼容)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # ── 白名单路径 — 直接放行 ────────────────────────────────
        path = request.url.path
        if path in WHITELIST_PATHS:
            return await call_next(request)

        # ── 白名单前缀 — 直接放行 ────────────────────────────────
        for prefix in WHITELIST_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # ── 非 API 路径 — 直接放行 ────────────────────────────────
        if not path.startswith("/api/"):
            return await call_next(request)

        # ── 验证 Authorization header ─────────────────────────────
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning(
                "[Auth] 缺失或无效的 Authorization header: path=%s",
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "未提供认证令牌，请在请求头中添加 Authorization: Bearer ***"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[len("Bearer "):]

        # ── 验证 token ────────────────────────────────────────────
        is_valid, payload_or_reason = self._validate_token(token)
        if not is_valid:
            logger.warning(
                "[Auth] 无效的 token: path=%s, reason=%s",
                request.url.path,
                payload_or_reason,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "认证令牌无效或已过期"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # ── 将 payload 注入 request.state 供下游使用 ──────────────
        request.state.user = payload_or_reason
        return await call_next(request)

    @staticmethod
    def _validate_token(token: str) -> tuple[bool, dict | str]:
        """
        验证 token，返回 (is_valid, payload_or_reason)

        支持两种格式:
          1. 真实 JWT (HS256)
          2. dev-token-{uuid4} (开发兼容)
        """
        # ── 方式一: 真实 JWT 验证 ─────────────────────────────────
        try:
            payload = pyjwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGORITHM],
                options={"verify_exp": True},
            )
            return True, payload
        except pyjwt.ExpiredSignatureError:
            return False, "JWT token 已过期"
        except pyjwt.InvalidTokenError:
            pass  # 不是 JWT 格式，继续尝试 dev-token

        # ── 方式二: dev-token-{uuid4} 兼容格式 ────────────────────
        if re.match(
            r"^dev-token-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            token,
        ):
            return True, {"type": "dev-token", "token": token[:20] + "..."}

        return False, "不支持的 token 格式"
