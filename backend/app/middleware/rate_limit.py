"""API RateLimit 中间件 — 滑动窗口限流

基于 app.rate_limiter 模块实现：
- 默认每 IP 每分钟 100 次
- /api/v1/auth/* 路由更严格：30 次/分钟
- 超限返回 429 + Retry-After header
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.rate_limiter import (
    MemoryRateLimiter,
    extract_client_ip,
    extract_user_id,
    get_rate_limiter,
    is_rate_limiting_enabled,
)

logger = logging.getLogger(__name__)

# 路由级别速率配置（按最长前缀匹配）
# 格式: (路径前缀, 速率上限, 窗口秒数)
ROUTE_RATE_LIMITS: list[tuple[str, int, int]] = [
    ("/api/v1/auth/", 30, 60),  # 认证接口更严格：30次/分钟
    ("/api/auth/", 10, 60),  # 旧版认证接口：10次/分钟
    ("/api/v1/search/vector/rebuild", 6, 60),  # 索引重建：6次/分钟
]

# 默认速率
DEFAULT_LIMIT = 100
DEFAULT_WINDOW = 60


def _get_matching_rate(path: str) -> tuple[int, int]:
    """获取请求路径匹配的速率配置（最长前缀匹配）

    Returns:
        (limit, window_sec)
    """
    best_limit = DEFAULT_LIMIT
    best_window = DEFAULT_WINDOW
    best_len = 0
    for prefix, limit, window in ROUTE_RATE_LIMITS:
        if path.startswith(prefix) and len(prefix) > best_len:
            best_limit = limit
            best_window = window
            best_len = len(prefix)
    return best_limit, best_window


class RateLimitMiddleware:
    """FastAPI 速率限制中间件（ASGI 接口）

    使用 MemoryRateLimiter 滑动窗口算法，
    支持 per-IP 和 per-user 限流。
    """

    def __init__(self, app):
        self.app = app
        self.limiter: MemoryRateLimiter = get_rate_limiter()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not is_rate_limiting_enabled():
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # 仅限 API 路径
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        # 提取客户端标识
        client_ip = extract_client_ip(request)
        user_id = extract_user_id(request)
        rate_key = user_id if user_id else f"ip:{client_ip}"

        # 获取匹配的速率
        limit, window = _get_matching_rate(path)

        # 使用窗口秒数作为自定义限制的 key 后缀
        custom_key = f"{rate_key}:w{window}"

        allowed, retry_after = self.limiter.check(custom_key, limit=limit)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "path": path,
                    "client_ip": client_ip,
                    "user_id": user_id or "",
                    "rate_key": rate_key,
                    "limit": limit,
                    "retry_after": retry_after,
                },
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "message": "请求过于频繁，请稍后再试",
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
