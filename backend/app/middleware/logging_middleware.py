"""
LoggingMiddleware — 结构化请求日志中间件
==========================================
记录每个 HTTP 请求的方法、路径、状态码、耗时和请求 ID。

请求 ID 通过 contextvars 传递，确保在同一请求的全链路中
所有日志条目都包含相同的 request_id。

用法:
    app.add_middleware(LoggingMiddleware)
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.logging_config import get_logger, set_request_id

logger = get_logger("chainke.api")


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件 — 记录方法/路径/状态码/耗时/请求ID"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── 生成或复用请求 ID ────────────────────────────────────
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(request_id)

        start_time = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # 将请求 ID 写入响应头，方便客户端追踪
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "%s %s → %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": round(elapsed_ms, 1),
                "query_params": dict(request.query_params),
            },
        )

        # 清理上下文 (避免请求间泄漏)
        set_request_id(None)

        return response
