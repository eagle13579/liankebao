"""
MetricsMiddleware — Prometheus 指标中间件
===========================================
使用 prometheus_client + prometheus_fastapi_instrumentator 提供:
  - /metrics 端点 (Prometheus 格式)
  - /health 端点 (健康检查)
  - 自动采集 HTTP 请求量、错误率、响应延迟等指标

用法:
    app.add_middleware(MetricsMiddleware)
    # /metrics 和 /health 端点自动注册

暴露的 Prometheus 指标:
    chainke_http_requests_total{method, path, status}     — 请求计数器
    chainke_http_request_duration_seconds{method, path}   — 耗时直方图
    chainke_active_users                                   — 活跃用户 Gauge
"""

import time
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse, JSONResponse
from starlette.types import ASGIApp

from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY, CONTENT_TYPE_LATEST

logger = logging.getLogger("chainke.metrics")

# ===================================================================
# Prometheus 指标定义
# ===================================================================

# HTTP 请求计数器 (按 method / path / status 分类)
HTTP_REQUESTS_TOTAL = Counter(
    name="chainke_http_requests_total",
    documentation="Total number of HTTP requests",
    labelnames=["method", "path", "status"],
)

# HTTP 请求耗时直方图 (单位: 秒)
HTTP_REQUEST_DURATION = Histogram(
    name="chainke_http_request_duration_seconds",
    documentation="HTTP request duration in seconds",
    labelnames=["method", "path"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, float("inf")),
)

# 活跃用户数 (Gauge，由业务逻辑设置)
ACTIVE_USERS = Gauge(
    name="chainke_active_users",
    documentation="Current number of active users",
)


# ===================================================================
# 中间件
# ===================================================================


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    请求指标中间件

    使用 prometheus_client 记录请求计数和耗时直方图，
    通过 /metrics 端点暴露 Prometheus 兼容格式，
    通过 /health 端点暴露健康检查状态。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── /metrics 端点 — 返回 Prometheus 指标 ─────────────────
        if request.url.path == "/metrics":
            return PlainTextResponse(
                content=generate_latest(REGISTRY).decode("utf-8"),
                media_type=CONTENT_TYPE_LATEST,
                headers={
                    "X-Content-Type-Options": "nosniff",
                },
            )

        # ── /health 端点 — 返回健康检查状态 ──────────────────────
        if request.url.path == "/health":
            return JSONResponse(
                content={
                    "status": "healthy",
                    "service": "chainke-backend",
                    "timestamp": int(time.time()),
                },
                status_code=200,
            )

        # ── 常规请求 — 记录指标 ──────────────────────────────────
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path=request.url.path,
                status="500",
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                path=request.url.path,
            ).observe(elapsed)
            raise exc

        elapsed = time.perf_counter() - start_time

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            path=request.url.path,
            status=str(response.status_code),
        ).inc()
        HTTP_REQUEST_DURATION.labels(
            method=request.method,
            path=request.url.path,
        ).observe(elapsed)

        return response


# ===================================================================
# 便捷工具函数 (供业务代码调用)
# ===================================================================


def set_active_users(count: int) -> None:
    """
    设置当前活跃用户数。
    可在登录/登出时调用更新。

    用法:
        from app.middleware.metrics_middleware import set_active_users
        set_active_users(42)
    """
    ACTIVE_USERS.set(count)
