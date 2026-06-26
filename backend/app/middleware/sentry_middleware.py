"""
SentryMiddleware — 统一异常处理中间件（Sentry 集成）
=====================================================
捕获所有未被处理的异常，记录到 Sentry（如已激活），
并返回统一的 JSON 错误响应。

如果 Sentry 未激活，中间件仍然会捕获异常并返回友好错误信息，
确保生产环境不泄露堆栈细节。

用法:
    from app.middleware.sentry_middleware import SentryMiddleware
    app.add_middleware(SentryMiddleware)
"""

import logging
import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.sentry import sentry_is_active

logger = logging.getLogger("chainke.sentry")


class SentryMiddleware(BaseHTTPMiddleware):
    """
    统一异常处理中间件。

    1. 所有未捕获的异常会被 Sentry SDK 捕获上报（如已初始化）。
    2. 返回统一的 JSON 错误响应，不暴露内部堆栈。
    3. 始终记录日志，便于本地调试。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            # ── 日志记录 ────────────────────────────────────────────
            logger.error(
                "未捕获异常: %s: %s\n%s",
                type(exc).__name__,
                str(exc),
                "".join(traceback.format_tb(exc.__traceback__)),
            )

            # ── Sentry 上报 ────────────────────────────────────────
            if sentry_is_active():
                try:
                    import sentry_sdk
                    with sentry_sdk.push_scope() as scope:
                        scope.set_tag("http.method", request.method)
                        scope.set_tag("http.url", str(request.url))
                        scope.set_extra("path_params", dict(request.path_params))
                        scope.set_extra("query_params", dict(request.query_params))
                        scope.set_extra("client_host", request.client.host if request.client else None)
                        sentry_sdk.capture_exception(exc)
                except Exception as sdk_err:
                    logger.warning("[Sentry] 上报异常时失败: %s", sdk_err)

            # ── 统一 JSON 响应 ─────────────────────────────────────
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "服务器内部错误，请稍后重试",
                    "error_type": type(exc).__name__,
                },
                headers={"X-Error-Reported": "true"},
            )
