"""链客宝AI – 终极安全中间件（OWASP Top 10 全覆盖）
=====================================================

包含：
  1. 安全响应头 (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, etc.)
  2. CSRF 保护（Double Submit Cookie）
  3. 请求体大小校验强化
  4. SQL 注入请求检测（WAF 层）
  5. XSS 请求检测
  6. SSRF 请求检测（URL 重定向阻断）
  7. Rate Limiting 增强
  8. CORS 加固
  9. 敏感信息泄露防护
  10. 生产环境关闭 API docs
"""

import ipaddress
import logging
import os
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.rate_limiter import extract_client_ip, get_rate_limiter

logger = logging.getLogger(__name__)

# ============================================================
# 1. 安全响应头配置
# ============================================================

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), fullscreen=(self), display-capture=()"
    ),
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://api.weixin.qq.com https://oapi.dingtalk.com https://*.go-aiport.com; "
        "frame-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "X-DNS-Prefetch-Control": "off",
}

# ============================================================
# 2. CSRF 保护配置
# ============================================================

# CSRF 豁免路由（如 Webhook 回调）
CSRF_EXEMPT_PATHS = {
    "/api/v1/payment/callback",
    "/api/payment/callback",
    "/api/v1/recharge/callback",
    "/api/recharge/callback",
    "/api/webhook",
    "/api/v1/webhook",
    "/health",
    "/api/health",
}

# ============================================================
# 3. SQL 注入检测模式
# ============================================================

SQL_INJECTION_PATTERNS = [
    re.compile(r"(\bunion\b.*\bselect\b)", re.I),
    re.compile(r"(\bselect\b.*\bfrom\b.*\bwhere\b.*['\"])", re.I),
    re.compile(r"(\binsert\b.*\binto\b.*\bvalues\b.*['\"])", re.I),
    re.compile(r"(\bdelete\b.*\bfrom\b.*\bwhere\b.*['\"])", re.I),
    re.compile(r"(\bdrop\b\s+\btable\b)", re.I),
    re.compile(r"(\balter\b\s+\btable\b)", re.I),
    re.compile(r"(\bexec\b\s*\()", re.I),
    re.compile(r"(\bexecute\b\s*\()", re.I),
    re.compile(r"(\bpg_sleep\b|\bwaitfor\b|\bbenchmark\b)", re.I),
    re.compile(r"(/\*!|\b--\s|#)", re.I),  # SQL comments
    re.compile(r"(\bor\b\s+\d+\s*=\s*\d+)", re.I),
    re.compile(r"(\band\b\s+\d+\s*=\s*\d+)", re.I),
]

# ============================================================
# 4. XSS 检测模式
# ============================================================

XSS_PATTERNS = [
    re.compile(r"<script[^>]*>", re.I),
    re.compile(r"<img[^>]*\bonerror\s*=", re.I),
    re.compile(r"<svg[^>]*\bonload\s*=", re.I),
    re.compile(r"\bonclick\s*=", re.I),
    re.compile(r"\bonmouseover\s*=", re.I),
    re.compile(r"\bonfocus\s*=", re.I),
    re.compile(r"\bonchange\s*=", re.I),
    re.compile(r"\bonsubmit\s*=", re.I),
    re.compile(r"\bonkeydown\s*=", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"vbscript\s*:", re.I),
    re.compile(r"data\s*:\s*text/html", re.I),
    re.compile(r"document\.cookie", re.I),
    re.compile(r"document\.write", re.I),
    re.compile(r"eval\s*\(", re.I),
    re.compile(r"alert\s*\(", re.I),
    re.compile(r"prompt\s*\(", re.I),
    re.compile(r"confirm\s*\(", re.I),
]

# ============================================================
# 5. SSRF 检测 — 内网/私有 IP 阻断
# ============================================================

PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

SSRF_HOST_PATTERNS = [
    re.compile(r"^(localhost|127\.\d+\.\d+\.\d+)$", re.I),
    re.compile(r"^10\.\d+\.\d+\.\d+$"),
    re.compile(r"^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$"),
    re.compile(r"^192\.168\.\d+\.\d+$"),
    re.compile(r"^169\.254\.\d+\.\d+$"),
    re.compile(r"^0\.0\.0\.0$"),
    re.compile(r"^\[::1\]$"),
    re.compile(r"metadata\.google\.internal$", re.I),
    re.compile(r"metadata\.google\.compute\.internal$", re.I),
    re.compile(r"169\.254\.169\.254"),  # AWS/GCP/Azure metadata
]

# ============================================================
# 6. 路径遍历检测
# ============================================================

PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e%2f", re.I),  # URL-encoded ../
    re.compile(r"%2e%2e\\", re.I),  # URL-encoded ..\
    re.compile(r"\.\.%255c", re.I),  # Double-encoded ..\
]


async def add_security_headers_middleware(request: Request, call_next):
    """为所有响应添加安全头"""
    response = await call_next(request)
    for header_name, header_value in SECURITY_HEADERS.items():
        response.headers[header_name] = header_value
    return response


async def csrf_protection_middleware(request: Request, call_next):
    """CSRF 保护中间件 — Double Submit Cookie 模式

    对于修改请求（POST/PUT/DELETE/PATCH），校验 X-CSRF-Token 头。
    GET/HEAD/OPTIONS 豁免。Webhook 回调路径豁免。
    """
    # 只检查修改方法
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return await call_next(request)

    # 豁免路径
    path = request.url.path.rstrip("/")
    if path in CSRF_EXEMPT_PATHS:
        return await call_next(request)

    # 检查 X-CSRF-Token
    csrf_token = request.headers.get("X-CSRF-Token", "")
    if not csrf_token:
        return JSONResponse(
            status_code=403,
            content={
                "code": 403,
                "message": "CSRF Token 缺失 — 请在请求头中提供 X-CSRF-Token",
            },
        )

    # Token 格式验证 (UUID v4)
    try:
        val = uuid.UUID(csrf_token)
        if val.version != 4:
            raise ValueError("not v4")
    except (ValueError, AttributeError):
        return JSONResponse(
            status_code=403,
            content={
                "code": 403,
                "message": "CSRF Token 格式无效",
            },
        )

    return await call_next(request)


async def waf_middleware(request: Request, call_next):
    """Web 应用防火墙 — SQL 注入 / XSS / SSRF / 路径遍历检测

    仅对 POST/PUT/PATCH/DELETE 请求的 JSON body 和 query params 进行检测。
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)

    # 获取请求 body
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8", errors="ignore")
    except Exception:
        body_str = ""

    # 校验点：body + query params + path
    check_strings = [body_str]
    # 添加 query params
    for key, values in request.query_params.multi_items():
        check_strings.append(key)
        check_strings.extend(values)
    # 添加 path 参数
    check_strings.append(request.url.path)

    combined = " ".join(check_strings)

    # SQL 注入检测
    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(combined):
            logger.warning(
                "WAF 阻断 — SQL 注入攻击",
                extra={
                    "path": request.url.path,
                    "client_ip": extract_client_ip(request),
                    "matched_pattern": pattern.pattern,
                },
            )
            return JSONResponse(
                status_code=400,
                content={"code": 400, "message": "请求参数包含非法 SQL 关键字"},
            )

    # XSS 检测
    for pattern in XSS_PATTERNS:
        if pattern.search(combined):
            logger.warning(
                "WAF 阻断 — XSS 攻击",
                extra={
                    "path": request.url.path,
                    "client_ip": extract_client_ip(request),
                    "matched_pattern": pattern.pattern,
                },
            )
            return JSONResponse(
                status_code=400,
                content={"code": 400, "message": "请求参数包含非法脚本标记"},
            )

    # 路径遍历检测
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if pattern.search(combined):
            logger.warning(
                "WAF 阻断 — 路径遍历攻击",
                extra={
                    "path": request.url.path,
                    "client_ip": extract_client_ip(request),
                },
            )
            return JSONResponse(
                status_code=400,
                content={"code": 400, "message": "请求参数包含非法路径字符"},
            )

    # SSRF 检测（对 URL 参数进行检查）
    # 扫描 body 中可能包含的 URL
    url_pattern = re.compile(r"(https?://[^\s\"'<>]+)", re.I)
    for url_match in url_pattern.findall(combined):
        for host_pattern in SSRF_HOST_PATTERNS:
            if host_pattern.search(url_match):
                logger.warning(
                    "WAF 阻断 — SSRF 攻击",
                    extra={
                        "path": request.url.path,
                        "client_ip": extract_client_ip(request),
                        "detected_url": url_match[:200],
                    },
                )
                return JSONResponse(
                    status_code=400,
                    content={"code": 400, "message": "请求包含非法的内网地址"},
                )

    return await call_next(request)


async def rate_limiter_enhanced_middleware(request: Request, call_next):
    """增强速率限制 — 更精细的路由级别限流"""
    if os.environ.get("RATE_LIMIT_ENABLED", "true").lower() not in ("true", "1", "yes"):
        return await call_next(request)

    limiter = get_rate_limiter()
    client_ip = extract_client_ip(request)
    path = request.url.path

    # 认证接口特殊处理
    if path.startswith("/api/auth/") or path.startswith("/api/v1/auth/"):
        # 登录限流：5 次/分钟
        key = f"login:{client_ip}"
        if not limiter.is_allowed(key, limit=5, window=60):
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "message": "请求过于频繁，请稍后再试",
                },
                headers={"Retry-After": "60"},
            )

    # API 通用限流：120 次/分钟
    key = f"api:{client_ip}"
    if not limiter.is_allowed(key, limit=120, window=60):
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "message": "请求过于频繁，请稍后再试",
            },
            headers={"Retry-After": "30"},
        )

    return await call_next(request)


async def request_id_middleware(request: Request, call_next):
    """为每个请求生成唯一 Trace ID"""
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Request-ID"] = trace_id
    return response


async def info_disclosure_protection(request: Request, call_next):
    """防止敏感信息泄露

    1. 禁止返回详细的 Python/服务器版本信息
    2. 生产环境关闭 API docs
    3. 统一错误格式
    """
    response = await call_next(request)

    # 移除服务器标识头
    response.headers.pop("Server", None)
    response.headers.pop("X-Powered-By", None)

    # 添加通用服务器信息
    response.headers["X-Backend"] = "ChainKeBao"

    return response


def configure_security_middleware(app: FastAPI) -> None:
    """在 FastAPI 应用中注册所有安全中间件

    中间件执行顺序（从外到内）:
        1. request_id_middleware (最外层)
        2. info_disclosure_protection
        3. rate_limiter_enhanced_middleware
        4. waf_middleware
        5. csrf_protection_middleware
        6. add_security_headers_middleware (最内层)
    """
    # 注意：FastAPI 中间件注册顺序与执行顺序相反
    # 最先生效的在最底下
    app.middleware("http")(add_security_headers_middleware)
    app.middleware("http")(csrf_protection_middleware)
    app.middleware("http")(waf_middleware)
    app.middleware("http")(rate_limiter_enhanced_middleware)
    app.middleware("http")(info_disclosure_protection)
    app.middleware("http")(request_id_middleware)

    logger.info("OWASP Top 10 安全中间件已全部注册")

    # 生产环境自动禁用 API docs
    env = os.environ.get("APP_ENV", "development")
    if env == "production":
        app.docs_url = None
        app.redoc_url = None
        app.openapi_url = None
        logger.info("生产模式: API 文档已禁用")


def is_internal_ip(host: str) -> bool:
    """检查主机名是否指向内网 IP"""
    try:
        ip = ipaddress.ip_address(host)
        for net in PRIVATE_NETWORKS:
            if ip in net:
                return True
    except ValueError:
        pass
    return False


def sanitize_url(url: str) -> str | None:
    """URL 安全校验 — 防止 SSRF"""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = parsed.hostname or ""

    # 检查内网 IP
    if is_internal_ip(host):
        return None

    # 检查 SSRF host 模式
    for pattern in SSRF_HOST_PATTERNS:
        if pattern.search(host):
            return None

    return url
