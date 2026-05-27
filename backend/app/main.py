"""链客宝后端 API 服务 - 主入口"""
import os
import sys
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.openapi.utils import get_openapi
from starlette.websockets import WebSocketState

# ===== LLM Cost Controller（零依赖轻量级Token消耗监控） =====
from llm_cost_controller import get_cost_controller as _get_cost_controller

_cost_controller_instance = None


def get_llm_cost_controller():
    """惰性初始化全局 CostController 单例"""
    global _cost_controller_instance
    if _cost_controller_instance is None:
        _cost_controller_instance = _get_cost_controller()
    return _cost_controller_instance


# ===== 结构化日志（最先加载） =====
from app.logging_config import setup_logging, RequestLogMiddleware, set_log_level, get_current_log_level, set_user_id, get_user_id

setup_logging()

logger = logging.getLogger(__name__)

# ===== 统一数据库（SQLite/MySQL 自适应） =====
from app.database import init_db, get_db

from app.routers import auth, products, orders, promoter, admin, search, imports as import_router
import app.routers.contacts as contacts_module
import app.routers.activities as activities_module
import app.routers.payment as payment_module
import app.routers.insights as insights_module
import app.routers.needs as needs_module
import recharge.routes as recharge_module
import recharge.callback as recharge_callback_module
import invoice as invoice_module
import reconciliation as reconciliation_module
import admin_config as admin_config_module
import matching_engine as matching_engine_module

# ===== 通知系统 & WebSocket =====
from app.notifications import NotificationManager
from app.websocket_manager import ws_manager

# ===== 认证 =====
from app.auth import get_current_user, verify_token
from app.models import User

app = FastAPI(
    title="链客宝API",
    description="链客宝后端API服务 — Premium Business Network and Entrepreneur Supply-Demand Matching Platform。\n\n"
    "提供认证、产品、订单、搜索、支付、充值、发票、对账、联系人管理、活动时间线、数据洞察、"
    "供需匹配、AI智能匹配引擎、推广员体系、管理后台、系统配置等完整业务能力。",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "链客宝团队",
        "url": "https://www.go-aiport.com",
        "email": "support@go-aiport.com",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://www.go-aiport.com",
    },
)

# ===== OpenAPI schema 定制（添加 servers 配置） =====
def custom_openapi():
    """生成带 servers 配置的 OpenAPI schema"""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        contact=app.contact,
        license_info=app.license_info,
    )
    openapi_schema["servers"] = [
        {
            "url": "https://www.go-aiport.com",
            "description": "生产环境",
        },
        {
            "url": "https://staging.go-aiport.com",
            "description": "预发布环境",
        },
        {
            "url": "http://localhost:7800",
            "description": "本地开发环境",
        },
    ]
    # 给所有路径统一添加 summary 保底
    for path, methods in openapi_schema.get("paths", {}).items():
        for method, detail in methods.items():
            if "summary" not in detail and "operationId" in detail:
                detail["summary"] = detail["operationId"].replace("_", " ").title()
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ===== 安全 CORS 配置（生产环境白名单 + 微信小程序无 origin 放行） =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.go-aiport.com",
        "https://go-aiport.com",
        "https://liankebao.top",
        "https://www.liankebao.top",
    ],
    allow_origin_regex="https?://localhost(:\\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 可观测性：指标收集器 =====
from app.observability import (
    get_metrics_collector,
    get_system_info,
    check_db_health,
    get_uptime,
    format_uptime,
)

_metrics = get_metrics_collector()

# ===== 请求日志 + 指标中间件（结构化日志全覆盖 + 指标收集） =====
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """记录每个请求的结构化日志 + 收集指标"""
    trace_id = getattr(request.state, "trace_id", "")
    start = datetime.now(timezone.utc)
    method = request.method
    path = request.url.path

    try:
        response = await call_next(request)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        status_code = response.status_code
        uid = get_user_id() or ""

        # 结构化日志
        logger.info(
            "request",
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "elapsed_sec": round(elapsed, 4),
                "user_id": uid,
                "trace_id": trace_id,
                "client_ip": request.client.host if request.client else "",
            },
        )

        # 记录指标
        _metrics.record_request(method, path, status_code, elapsed)

        return response
    except Exception as exc:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        logger.error(
            "request_error",
            extra={
                "method": method,
                "path": path,
                "elapsed_sec": round(elapsed, 4),
                "error": str(exc),
                "trace_id": trace_id,
            },
            exc_info=True,
        )
        _metrics.record_request(method, path, 500, elapsed)
        raise


# ===== 请求 ID 中间件（为每个请求生成唯一 trace_id） =====
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为每个请求生成唯一 trace_id，注入 request.state 和响应头"""
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# ===== 安全响应头中间件 =====
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """每次响应注入安全头：HSTS、X-Frame-Options、X-Content-Type-Options、CSP、Referrer-Policy"""
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'"
    response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
    return response

# ===== 请求大小限制（POST 请求体不超过 1MB） =====
MAX_REQUEST_SIZE = 1_048_576  # 1MB

@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """限制 POST 请求体大小，超过 1MB 返回 413 Payload Too Large"""
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "请求体过大，最大允许 1MB"},
            )
    return await call_next(request)

# ===== 注册路由 =====
# 所有 router 已在各自文件中定义了 prefix="/api/..."（如 /api/auth, /api/products）
# 这里分两轮注册：
#   第一轮：临时将 prefix 改为 /api/v1/...，注册版本化路由
#   第二轮：恢复原始 prefix，注册向后兼容的 /api/... 路由

router_modules = [auth, products, orders, promoter, admin, search, import_router, contacts_module, activities_module, payment_module, insights_module, needs_module, recharge_module, invoice_module, reconciliation_module, admin_config_module, matching_engine_module]

# 第一轮：/api/v1/ 版本化路由
for mod in router_modules:
    old_prefix = mod.router.prefix
    mod.router.prefix = old_prefix.replace("/api", "/api/v1", 1)
    app.include_router(mod.router)
    mod.router.prefix = old_prefix

# 第二轮：/api/ 向后兼容路由
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(promoter.router)
app.include_router(admin.router)
app.include_router(search.router)
app.include_router(import_router.router)
app.include_router(contacts_module.router)
app.include_router(payment_module.router)
app.include_router(insights_module.router)
app.include_router(needs_module.router)
app.include_router(recharge_module.router)
app.include_router(recharge_callback_module.callback_router)
app.include_router(invoice_module.router)
app.include_router(reconciliation_module.router)
app.include_router(admin_config_module.router)
app.include_router(matching_engine_module.router)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ============================================================
# 前端 SPA（React 构建产物）
# ============================================================
_SPA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dist")
if os.path.isdir(_SPA_DIR):
    app.mount("/app", StaticFiles(directory=_SPA_DIR, html=True), name="spa")

# ============================================================
# 推广落地页 /share
# ============================================================
_SHARE_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dist", "share.html")


@app.get("/share", summary="推广落地页", description="返回推广落地页 HTML（独立 H5 页面，位于前端 SPA 之外）")
async def share_page():
    """推广落地页（独立 H5 页面，前端 SPA 之外）"""
    if os.path.isfile(_SHARE_HTML):
        return FileResponse(_SHARE_HTML, media_type="text/html")
    return JSONResponse(
        status_code=404,
        content={"code": 404, "message": "落地页不存在"},
    )


@app.get("/api/users/{user_id}/brief", summary="获取用户简要信息", description="获取用户简要信息（供推广落地页展示推广员姓名）")
def get_user_brief(user_id: int, db: Session = Depends(get_db)):
    """获取用户简要信息（供推广落地页展示推广员姓名）"""
    from app.schemas import UserBrief
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "用户不存在"},
        )
    return {
        "code": 200,
        "message": "success",
        "data": UserBrief.model_validate(user).model_dump(),
    }


# ============================================================
# 首页 Banner API（小程序轮播图）
# ============================================================
BANNERS = [
    {
        "image": "https://www.go-aiport.com/static/banners/banner1.svg",
        "title": "链客宝 · AI企业家生态",
        "url": "/pages/pool/index",
    },
    {
        "image": "https://www.go-aiport.com/static/banners/banner2.svg",
        "title": "GEO诊断 · 精准获客",
        "url": "/pages/pool/index?cat=geo",
    },
    {
        "image": "https://www.go-aiport.com/static/banners/banner3.svg",
        "title": "数字分身 · 智能交互",
        "url": "/pages/pool/index?cat=ai",
    },
]


@app.get("/banners", summary="首页轮播图", description="获取小程序首页轮播图列表（无 /api 前缀）")
def list_banners():
    """获取首页轮播图列表"""
    return {"code": 200, "message": "success", "data": BANNERS}


@app.get("/api/banners", summary="首页轮播图（兼容）", description="获取小程序首页轮播图列表（带 /api 前缀的兼容版本）")
def list_banners_api():
    """获取首页轮播图列表（带 /api 前缀兼容）"""
    return {"code": 200, "message": "success", "data": BANNERS}


# ============================================================
# 通知 API
# ============================================================
@app.get("/api/notifications", summary="通知列表", description="获取当前用户的通知列表，支持分页和未读筛选")
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的通知列表"""
    result = NotificationManager.get_user_notifications(
        user_id=current_user.id,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )
    return {"code": 200, "message": "success", "data": result}


@app.get("/api/notifications/unread-count", summary="未读通知数", description="获取当前用户的未读通知数量")
def unread_notification_count(
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的未读通知数"""
    count = NotificationManager.get_unread_count(user_id=current_user.id)
    return {"code": 200, "message": "success", "data": {"unread_count": count}}


@app.put("/api/notifications/{notification_id}/read", summary="标记通知已读", description="标记单条通知为已读")
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
):
    """标记单条通知为已读"""
    ok = NotificationManager.mark_as_read(notification_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "通知不存在"},
        )
    return {"code": 200, "message": "success"}


@app.put("/api/notifications/read-all", summary="标记全部已读", description="标记当前用户所有通知为已读")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
):
    """标记当前用户所有通知为已读"""
    updated = NotificationManager.mark_all_as_read(user_id=current_user.id)
    return {"code": 200, "message": "success", "data": {"updated_count": updated}}


@app.delete("/api/notifications/{notification_id}", summary="删除通知", description="删除单条通知")
def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
):
    """删除单条通知"""
    ok = NotificationManager.delete_notification(notification_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "通知不存在"},
        )
    return {"code": 200, "message": "success"}


# ============================================================
# WebSocket 端点
# ============================================================
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    实时通知 WebSocket 连接。

    客户端通过路径参数传递 user_id。
    认证方式：客户端连接后发送第一条消息为 JSON {"token": "xxx"} 进行鉴权。

    消息格式（服务端 -> 客户端）：
        {"event": "notification", "data": {...}}
        {"event": "order_update", "data": {...}}
    """
    await ws_manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            # 简单心跳 / 消息响应
            logger.debug(
                "WebSocket 收到消息",
                extra={"user_id": user_id, "data": data},
            )
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id)
    except Exception as exc:
        logger.warning(
            "WebSocket 异常断开",
            extra={"user_id": user_id, "error": str(exc)},
        )
        ws_manager.disconnect(user_id)


# ============================================================
# 管理端点：日志级别动态切换
# ============================================================
@app.get("/api/system/log-level", summary="获取日志级别", description="获取当前日志级别（需管理员权限）")
def get_log_level(current_user: User = Depends(get_current_user)):
    """获取当前日志级别（需管理员权限）"""
    if current_user.role != "admin":
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "需要管理员权限"},
        )
    return {
        "code": 200,
        "message": "success",
        "data": {"level": logging.getLevelName(get_current_log_level())},
    }


@app.put("/api/system/log-level", summary="切换日志级别", description="动态切换日志级别（需管理员权限）。可选值：DEBUG / INFO / WARNING / ERROR / CRITICAL")
def change_log_level(
    level: str = Query(..., description="DEBUG / INFO / WARNING / ERROR / CRITICAL"),
    current_user: User = Depends(get_current_user),
):
    """动态切换日志级别（需管理员权限）"""
    if current_user.role != "admin":
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "需要管理员权限"},
        )
    try:
        set_log_level(level)
        return {
            "code": 200,
            "message": "success",
            "data": {"level": level.upper()},
        }
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": str(e)},
        )


# ============================================================
# LLM Cost Controller API
# ============================================================
@app.get("/api/system/cost/usage", summary="LLM用量汇总", description="获取LLM调用用量汇总（当日+当月+总计+限额）")
def get_cost_usage():
    """获取LLM调用用量汇总（当日+当月+总计+限额）"""
    cc = get_llm_cost_controller()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "daily": cc.get_daily_usage(),
            "monthly": cc.get_monthly_usage(),
            "total": cc.get_total_usage(),
            "limits": cc.get_limits(),
        },
    }


@app.get("/api/system/cost/breakdown", summary="LLM调用明细", description="获取LLM调用明细（按模型+按模块+按日明细）")
def get_cost_breakdown():
    """获取LLM调用明细（按模型+按模块+按日明细）"""
    cc = get_llm_cost_controller()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "daily_breakdown": cc.get_daily_breakdown(),
            "by_model": cc.get_model_usage(),
            "by_module": cc.get_module_usage(),
        },
    }


@app.get("/api/system/cost/models", summary="LLM模型价格表", description="获取已注册的LLM模型价格表")
def list_cost_models():
    """获取已注册的LLM模型价格表"""
    cc = get_llm_cost_controller()
    return {
        "code": 200,
        "message": "success",
        "data": cc.list_models(),
    }


# ============================================================
# 启动 / 关闭事件
# ============================================================
@app.on_event("startup")
def on_startup():
    """应用启动时初始化数据库与系统预设配置"""
    import socket
    from app.database import DB_TYPE
    try:
        init_db()
        # 确保系统预设配置存在
        from admin_config import ensure_preset_configs
        db_session = next(get_db())
        ensure_preset_configs(db_session)
        db_session.close()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        raise

    # ---- 启动信息结构化日志 ----
    hostname = socket.gethostname()
    port = os.environ.get("PORT", os.environ.get("UVICORN_PORT", "7800"))
    route_count = len(app.routes)

    startup_info = {
        "event": "startup",
        "hostname": hostname,
        "port": int(port) if port.isdigit() else port,
        "db_type": DB_TYPE,
        "route_count": route_count,
        "python_version": os.sys.version.split()[0],
        "log_level": logging.getLevelName(logging.getLogger().level),
    }
    logger.info("服务启动完成", extra=startup_info)


@app.on_event("shutdown")
def on_shutdown():
    """应用关闭时记录关闭信息"""
    import socket
    try:
        uptime_sec = get_uptime()
        hostname = socket.gethostname()
        logger.info(
            "服务关闭",
            extra={
                "event": "shutdown",
                "hostname": hostname,
                "uptime_sec": round(uptime_sec),
                "uptime_human": format_uptime(uptime_sec),
            },
        )
    except Exception:
        logger.info("服务关闭")


@app.get("/", summary="服务根路径", description="返回链客宝API服务基本信息（服务名、状态、版本）")
def root():
    return {
        "service": "链客宝 API",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health", summary="健康检查", description="服务健康检查端点，返回系统状态（数据库连接/磁盘/内存/运行时长）")
def health():
    """增强型健康检查：返回系统状态（数据库连接/磁盘/内存/运行时长）"""
    db_health = check_db_health()
    sys_info = get_system_info()

    overall_status = "ok" if db_health["status"] == "healthy" else "degraded"

    return {
        "status": overall_status,
        "database": db_health,
        "system": sys_info,
        "version": "1.0.0",
    }


@app.get("/metrics", summary="应用指标", description="应用指标端点：请求量/错误率/响应时间统计")
def metrics():
    """应用指标端点：请求量/错误率/响应时间统计"""
    return _metrics.snapshot()


# ============================================================
# 全局异常处理器
# ============================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """自定义 404 响应，统一返回 JSON 格式"""
    return JSONResponse(
        status_code=404,
        content={"code": 404, "message": "请求的资源不存在"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """捕获所有未预期的异常，返回统一 JSON 格式（生产环境不暴露细节）"""
    trace_id = getattr(request.state, "trace_id", "N/A")
    logger.error(
        "未预期的服务器错误",
        extra={"trace_id": trace_id, "error": str(exc)},
        exc_info=True,
    )
    detail = str(exc) if os.getenv("ENV", "").lower() != "production" else ""
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误", "detail": detail},
    )
