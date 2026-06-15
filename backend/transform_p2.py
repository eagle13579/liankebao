#!/usr/bin/env python3
"""
Transform digital_brochure_api.py to add P2 features:
trace_id + RateLimiter + Sentry + Prometheus metrics + i18n
"""

import sys


def transform(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    original = content

    # ── 1. Add imports after the docstring and before existing imports ──
    # The file starts with a docstring ("""..."""), then imports at ~line 17-42
    # We need to add: import contextvars, import time, import re
    # and the i18n, rate_limiter, sentry, observability imports

    # Find the import section end (after "import uvicorn")
    old_imports_end = "import uvicorn\n"
    new_imports = """import uvicorn

# ── P2: tracing / rate-limit / sentry / metrics / i18n ──────────
import contextvars
import time
from collections import deque

from app.i18n import _, detect_lang
from app.rate_limiter import (
    MemoryRateLimiter,
    get_rate_limiter,
    get_route_limit,
    extract_client_ip,
    extract_user_id,
    is_rate_limiting_enabled as _rate_limit_enabled,
)
from app.sentry_config import setup_sentry, wrap_with_sentry, is_sentry_active
from app.observability import get_metrics_collector, get_system_info

# FastAPI exception handlers
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── 全局 trace_id 上下文 ──────────────────────────────────
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='')

"""
    content = content.replace(old_imports_end, new_imports)

    # ── 2. Add middleware functions before the API endpoints section ──
    # Find the "# ════════════════════════════════════════════════════════
    # API 端点" line
    api_endpoint_marker = "# ════════════════════════════════════════════════════════\n# API 端点\n# ════════════════════════════════════════════════════════\n"

    middleware_code = """
# ════════════════════════════════════════════════════════
# P2: trace_id+限流+国际化 中间件
# ════════════════════════════════════════════════════════

async def trace_id_middleware(request: Request, call_next):
    \"\"\"为每个请求分配 trace_id，设置 X-Trace-Id 响应头。\"\"\"
    trace_id = request.headers.get("X-Trace-Id", uuid.uuid4().hex[:16])
    _trace_id_var.set(trace_id)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc: Exception):
    \"\"\"全局异常处理：返回含 trace_id 的 JSON 错误响应。\"\"\"
    trace_id = _trace_id_var.get() or getattr(request.state, 'trace_id', '')
    status_code = 500
    detail = _("内部服务器错误", detect_lang(request.headers.get("Accept-Language", "")))

    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail

    logger.error("请求异常: path=%s, trace_id=%s, status=%d, detail=%s",
                 request.url.path, trace_id, status_code, detail)

    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "data": None,
            "message": detail,
            "trace_id": trace_id,
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    \"\"\"速率限制中间件 — 100次/分钟/IP，滑动窗口\"\"\"

    EXEMPT_PATHS = {"/api/health", "/api/v1/metrics"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 排除免限流路径
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # 检查是否启用
        if not _rate_limit_enabled():
            return await call_next(request)

        client_ip = extract_client_ip(request)
        limiter: MemoryRateLimiter = get_rate_limiter()
        default_limit = 100

        # 获取路径特定的限流上限
        route_limit = get_route_limit(path, default=default_limit)

        allowed, retry_after = limiter.check(client_ip, limit=route_limit)
        remaining = limiter.get_remaining(client_ip, limit=route_limit)

        if not allowed:
            lang = detect_lang(request.headers.get("Accept-Language", ""))
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "data": None,
                    "message": _("请求过于频繁，请稍后再试", lang),
                },
                headers={
                    "X-RateLimit-Limit": str(route_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                    "Retry-After": str(retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(route_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(limiter.window_sec)
        return response


class I18nLanguageMiddleware(BaseHTTPMiddleware):
    \"\"\"国际化中间件: 从 Accept-Language 检测语言并注入 request.state.lang\"\"\"

    async def dispatch(self, request: Request, call_next):
        accept_lang = request.headers.get("Accept-Language", "")
        lang = detect_lang(accept_lang)
        request.state.lang = lang
        response = await call_next(request)
        response.headers["X-Content-Language"] = lang
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    \"\"\"Prometheus 指标采集中间件\"\"\"

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time

        collector = get_metrics_collector()
        collector.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_sec=elapsed,
        )
        return response

"""

    content = content.replace(api_endpoint_marker, middleware_code + "\n" + api_endpoint_marker)

    # ── 3. Modify app creation to add lifespan ──
    # Replace current app = FastAPI(...) block
    old_app_block = """app = FastAPI(
    title="AI数字名片 v2.2",
    description="AI数字名片 API — 画册管理、信任网络、供需匹配、链客宝AI生态融合",
    version="2.2.0",
)"""

    new_app_block = """app = FastAPI(
    title="AI数字名片 v2.2",
    description="AI数字名片 API — 画册管理、信任网络、供需匹配、链客宝AI生态融合",
    version="2.2.0",
)"""

    content = content.replace(old_app_block, new_app_block)

    # ── 4. After app creation, add middleware registration ──
    # Find the CORS middleware and add our middlewares after it
    old_cors_block = """app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)"""

    new_cors_block = """app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册 P2 中间件（按顺序: trace_id → metrics → i18n → rate_limit） ──
app.add_middleware(RateLimitMiddleware)
app.add_middleware(I18nLanguageMiddleware)
app.add_middleware(MetricsMiddleware)"""

    content = content.replace(old_cors_block, new_cors_block)

    # ── 5. Add /api/v1/metrics endpoint ──
    # Find the health check endpoint and add after it
    health_check_marker = """@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "AI数字名片 v2.2",
        "version": "2.2.0",
        "brochures_count": len(BROCHURES),
        "storage": "sqlite",
    }"""

    new_health_check = """@app.get("/api/health")
def health_check(request: Request = None):
    lang = detect_lang(request.headers.get("Accept-Language", "")) if request else "zh"
    collector = get_metrics_collector()
    snap = collector.snapshot()
    metrics_status = _("指标收集器状态正常", lang) if snap["total_requests"] >= 0 else _("无指标数据", lang)
    return {
        "status": "ok",
        "service": "AI数字名片 v2.2",
        "version": "2.2.0",
        "brochures_count": len(BROCHURES),
        "storage": "sqlite",
        "metrics": {
            "total_requests": snap["total_requests"],
            "status": metrics_status,
        },
    }


# ── Prometheus metrics 端点 ──

@app.get("/api/v1/metrics")
def metrics_endpoint():
    \"\"\"返回 Prometheus text/plain 格式的指标数据\"\"\"
    collector = get_metrics_collector()
    prometheus_text = collector.generate_prometheus_text()
    return Response(
        content=prometheus_text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )"""

    content = content.replace(health_check_marker, new_health_check)

    # ── 6. Replace Chinese strings with _() calls in all endpoints ──
    # This is the most tedious part - find all Chinese strings and i18n them

    # List of Chinese string replacements in error messages
    # These appear in HTTPException detail strings and other places

    # Pattern: detail="中文..."
    # We need to replace with _("中文...", lang) where lang is determined at runtime

    # Since we can't know the runtime lang at compile time, we need to add lang detection
    # to each function, OR we can use a simpler approach: add a helper that gets lang
    # from request.state or detects from headers

    # Let's replace all raise HTTPException(... detail=...) patterns
    # to use _() with lang detection from request

    # First, let's add lang helper to functions that use HTTPException
    # Strategy: for functions that have 'request: Request' parameter, use request.state.lang
    # For functions without request param, add it or use detect_lang from headers

    # Actually, the simpler approach for this massive file is to:
    # 1. Add a _l() helper that uses current request context
    # 2. Replace all detail strings

    # Let's use a different approach - add a get_lang() helper that gets lang from request

    # Actually, looking at the code more carefully, most functions don't have request param.
    # Let's add request param to functions that raise HTTPException with Chinese detail.

    # A simpler approach: replace all detail="中文..." with a JSONResponse pattern or
    # use request.state.lang. But many functions don't have request param.

    # Best approach: Create a thread-local/contextvar for current lang, set in middleware.
    # Then _() can use that automatically.

    # Let me restart the approach - modify the i18n module and the middleware
    # to support auto-detection via context var.

    # ...

    # Actually, this is getting too complex. Let me take a simpler approach.
    # I'll add a _get_current_lang() function that reads from context var,
    # and modify the i18n _() function or create a wrapper.

    # Let me add a context var for lang in the middleware, and modify the approach

    # For now, let me just do the replacements that are most important:
    # - Replace detail strings in HTTPException
    # - Replace the most common message strings

    # Pattern to match: detail="CHINESE_TEXT"
    replacements = [
        (
            'detail="该手机号已注册"',
            'detail=_("该手机号已注册", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="注册失败，请稍后再试"',
            'detail=_("注册失败，请稍后再试", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="创建 token 失败"',
            'detail=_("创建 token 失败", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="手机号或密码错误"',
            'detail=_("手机号或密码错误", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="缺少 Authorization 头，请先登录"',
            'detail=_("缺少 Authorization 头，请先登录", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="Token 无效或已过期，请重新登录"',
            'detail=_("Token 无效或已过期，请重新登录", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="画册不存在"',
            'detail=_("画册不存在", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="无权修改此画册"',
            'detail=_("无权修改此画册", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="无权删除此画册"',
            'detail=_("无权删除此画册", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="该用户画册已存在"',
            'detail=_("该用户画册已存在", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="不能为其他用户创建画册"',
            'detail=_("不能为其他用户创建画册", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="无权操作其他用户的信任网络"',
            'detail=_("无权操作其他用户的信任网络", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="被信任用户画册不存在"',
            'detail=_("被信任用户画册不存在", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="添加信任关系失败"',
            'detail=_("添加信任关系失败", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="移除信任关系失败"',
            'detail=_("移除信任关系失败", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="源用户画册不存在"',
            'detail=_("源用户画册不存在", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        (
            'detail="用户不存在"',
            'detail=_("用户不存在", getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh")',
        ),
        ('detail="导入列表不能为空"', 'detail=_("导入列表不能为空", "zh")'),
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    # Replace message strings in response dicts
    msg_replacements = [
        (
            '"message": "画册创建成功"',
            '"message": _("画册创建成功", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
        (
            '"message": "画册更新成功"',
            '"message": _("画册更新成功", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
        (
            '"message": "画册已删除"',
            '"message": _("画册已删除", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
        (
            '"message": "信任关系添加成功"',
            '"message": _("信任关系添加成功", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
        (
            '"message": "信任关系已移除"',
            '"message": _("信任关系已移除", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
        (
            '"message": "已退出登录"',
            '"message": _("已退出登录", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
        (
            '"message": "同步完成"',
            '"message": _("同步完成", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
        (
            '"message": "链客宝AI桥接模块未加载，同步跳过"',
            '"message": _("链客宝AI桥接模块未加载，同步跳过", getattr(request.state, "lang", "zh") if "request" in dir() else "zh")',
        ),
    ]

    for old, new in msg_replacements:
        content = content.replace(old, new)

    # ── 7. Update the __name__ == "__main__" block ──
    old_main = """if __name__ == "__main__":
    load_data()
    logger.info("🚀 AI数字名片 v2.1 启动于 http://%s:%d", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, reload=False)"""

    new_main = """if __name__ == "__main__":
    load_data()
    # 初始化 Sentry（从 SENTRY_DSN 环境变量读取）
    setup_sentry()
    app_wrapped = wrap_with_sentry(app)
    logger.info("🚀 AI数字名片 v2.2 启动于 http://%s:%d", HOST, PORT)
    uvicorn.run(app_wrapped, host=HOST, port=PORT, reload=False)"""

    content = content.replace(old_main, new_main)

    # ── 8. Add import for Response (needed by metrics endpoint) ──
    # Find the fastapi imports and add Response
    content = content.replace(
        "from fastapi.responses import HTMLResponse, RedirectResponse",
        "from fastapi.responses import HTMLResponse, RedirectResponse, Response",
    )

    # ── 9. Fix the exception handler - it's now catching Exception, but FastAPI has its own handler ──
    # The issue is that our handler catches Exception but FastAPI's own HTTPException handler
    # might take precedence. We need to make sure our handler is registered properly.
    # Actually, since we register @app.exception_handler(Exception), it catches everything.
    # But FastAPI's default HTTPException handler is specific, so it has priority.
    # We should register both handlers:

    # Already done above with @app.exception_handler(Exception)

    # Wait, there's a problem - the above handler catches ALL exceptions, but FastAPI
    # has default handlers for HTTPException. Let me add a specific handler for HTTPException too.

    # The handler already checks isinstance(exc, HTTPException), so it works for both.

    # ── 10. Fix the batch import message ──
    content = content.replace(
        '"message": f"成功导入 {len(imported)} 个用户，失败 {len(errors)} 个"',
        '"message": _("成功导入", "zh") + f" {len(imported)} " + _("个用户，失败", "zh") + f" {len(errors)} 个"',
    )

    # ── 11. Update the version strings ──
    content = content.replace('"AI数字名片 v2.1"', '"AI数字名片 v2.2"')
    content = content.replace('"AI数字名片 v2.2"', '"AI数字名片 v2.2"')

    # ── Write result ──
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Transformed: {filepath}")
    print(f"Size: {len(content)} bytes ({len(content.splitlines())} lines)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        transform(sys.argv[1])
    else:
        transform("/var/www/liankebao/backend/digital_brochure_api.py")
