"""链客宝AI后端 API 服务 - 主入口"""

import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

# ===== 安全加固模块 (AES-256-GCM + CSP + SQL注入检测) =====
from app.security_hardening import SecurityHeadersMiddleware, init_security_hardening

# 应用启动时初始化安全加固 (密钥加载、轮换检查等)
init_security_hardening()

# ===== OpenTelemetry APM 全链路追踪（最先加载，早于任何路由） =====
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    instrument_fastapi = FastAPIInstrumentor.instrument_app
except ImportError:

    def instrument_fastapi(app):
        pass


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
from app.logging_config import get_current_log_level, get_user_id, set_log_level, setup_logging

setup_logging()

# ===== Sentry 错误追踪（惰性初始化，依赖 SENTRY_DSN 环境变量） =====
from app.sentry_config import setup_sentry

setup_sentry()

logger = logging.getLogger(__name__)

# ===== 统一数据库（SQLite/MySQL 自适应） =====
import admin_config as admin_config_module
import app.bi_routes as bi_module
import app.routers.activities as activities_module
import app.routers.business_card as business_card_module
import app.routers.contacts as contacts_module
import app.routers.crm as crm_module
import app.routers.crm_pipeline as crm_pipeline_module
import app.routers.enrichment as enrichment_module
import app.routers.enterprise as enterprise_module
import app.routers.events as events_module
import app.routers.growth as growth_module
import app.routers.insights as insights_module
import app.routers.matching_events as matching_events_module
import app.routers.membership as membership_module
import app.routers.mission_control as mission_control_module
import app.routers.needs as needs_module
import app.routers.onboarding as onboarding_module
import app.routers.organization as organization_module
import app.routers.payment as payment_module
import app.routers.private_board as private_board_module
import app.routers.recommend as recommend_module
import app.routers.upload as upload_module
import app.routers.vector_search_router as vector_search_module

# ===== 搜索引擎（FTS5 / Memory 全文搜索） =====
import app.search_index as search_index_module

# ===== LLM 智能服务（DeepSeek API） =====
import app.services.llm_service as llm_service_module
import invoice as invoice_module
import matching_engine as matching_engine_module
import recharge.callback as recharge_callback_module
import recharge.routes as recharge_module
import reconciliation as reconciliation_module

# ===== 认证 =====
from app.auth import get_current_user
from app.database import get_db, init_db
from app.models import User

# ===== 通知系统 & WebSocket =====
from app.notifications import NotificationManager
from app.retry_engine import get_retry_engine
from app.routers import admin, auth, orders, products, promoter, search
from app.routers import imports as import_router
from app.websocket_manager import ws_manager

app = FastAPI(
    title="链客宝AIAPI",
    description="链客宝AI后端API服务 — Premium Business Network and Entrepreneur Supply-Demand Matching Platform。\n\n"
    "提供认证、产品、订单、搜索、支付、充值、发票、对账、联系人管理、活动时间线、数据洞察、"
    "供需匹配、AI智能匹配引擎、推广员体系、管理后台、系统配置等完整业务能力。",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "链客宝AI团队",
        "url": "https://www.go-aiport.com",
        "email": "support@go-aiport.com",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://www.go-aiport.com",
    },
)

# ===== OpenTelemetry FastAPI 自动追踪挂载（路由注册前） =====

instrument_fastapi(app)

# ===== 数据安全中间件（可选，默认关闭，由 SECURITY_MIDDLEWARE_ENABLED 环境变量控制） =====
from app.security_middleware_injection import (
    close_security_middleware,
    init_security_middleware,
)

init_security_middleware(app)


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
    allow_origin_regex="https?://localhost(:\\\\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== PostHog 行为分析中间件（在 CORS 之后，惰性初始化） =====
try:
    from app.posthog_middleware import PostHogMiddleware

    app.add_middleware(PostHogMiddleware)
    logger.info("PostHog 行为分析中间件已注册")
except Exception as e:
    logger.warning(f"PostHog 行为分析中间件注册失败: {e}")

# ===== 多租户中间件（PostgreSQL 模式启用，SQLite 模式跳过） =====
try:
    from app.tenant_middleware import TenantMiddleware

    app.add_middleware(TenantMiddleware)
    logger.info("多租户中间件已注册")
except Exception as e:
    logger.warning(f"多租户中间件注册失败: {e}")

# ===== Feature Flags 灰度发布中间件（在 Rate Limiter 之后） =====
try:
    from app.feature_flags import register_feature_flags

    register_feature_flags(app)
    logger.info("Feature Flags 灰度发布系统已注册")
except Exception as e:
    logger.warning(f"Feature Flags 灰度发布系统注册失败: {e}")

# ===== Circuit Breaker 熔断器路由（在 Feature Flags 之后） =====
try:
    from app.circuit_breaker import register_circuit_breakers

    register_circuit_breakers(app)
    logger.info("Circuit Breaker 熔断器路由已注册")
except Exception as e:
    logger.warning(f"Circuit Breaker 熔断器路由注册失败: {e}")

# ===== Rate Limiting 中间件（滑动窗口，零依赖） =====
# 必须在 CORSMiddleware 之后，确保 CORS 头已预先处理
from app.middleware.rate_limit import RateLimitMiddleware as NewRateLimitMiddleware

app.add_middleware(NewRateLimitMiddleware)

# ===== 可观测性：指标收集器 =====
from app.observability import (
    check_db_health,
    check_payment_health,
    format_uptime,
    get_metrics_collector,
    get_system_info,
    get_uptime,
)

_metrics = get_metrics_collector()


# ===== 请求日志 + 指标中间件（结构化日志全覆盖 + 指标收集） =====
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """记录每个请求的结构化日志 + 收集指标"""
    trace_id = getattr(request.state, "trace_id", "")
    start = datetime.now(UTC)
    method = request.method
    path = request.url.path

    try:
        response = await call_next(request)
        elapsed = (datetime.now(UTC) - start).total_seconds()
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
        elapsed = (datetime.now(UTC) - start).total_seconds()
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


# ===== 安全响应头中间件（增强版 — 由 security_hardening 模块提供） =====
# 使用 ASGI 中间件方式注册, 继承已有的 CSP/XSS/HSTS 等安全头
app.add_middleware(SecurityHeadersMiddleware)


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

router_modules = [
    auth,
    products,
    orders,
    promoter,
    admin,
    search,
    import_router,
    contacts_module,
    crm_module,
    crm_pipeline_module,
    enterprise_module,
    activities_module,
    payment_module,
    events_module,
    insights_module,
    needs_module,
    onboarding_module,
    recommend_module,
    business_card_module,
    matching_events_module,
    membership_module,
    private_board_module,
    upload_module,
    recharge_module,
    invoice_module,
    reconciliation_module,
    admin_config_module,
    matching_engine_module,
    bi_module,
    vector_search_module,
    enrichment_module,
    organization_module,
    growth_module,
]

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
app.include_router(crm_module.router)
app.include_router(crm_pipeline_module.router)
app.include_router(enterprise_module.router)
app.include_router(events_module.router)
app.include_router(payment_module.router)
app.include_router(insights_module.router)
app.include_router(needs_module.router)
app.include_router(mission_control_module.router)
app.include_router(onboarding_module.router)
app.include_router(recommend_module.router)
app.include_router(business_card_module.router)
app.include_router(matching_events_module.router)
app.include_router(membership_module.router)
app.include_router(private_board_module.router)
app.include_router(upload_module.router)
app.include_router(recharge_module.router)
app.include_router(recharge_callback_module.callback_router)
app.include_router(invoice_module.router)
app.include_router(reconciliation_module.router)
app.include_router(admin_config_module.router)
app.include_router(matching_engine_module.router)
app.include_router(bi_module.router)
app.include_router(vector_search_module.router)
app.include_router(enrichment_module.router)
app.include_router(organization_module.router)
app.include_router(membership_module.router)
app.include_router(growth_module.router)

# ===== 启动时初始化增长引擎数据库 =====
from app.routers.growth import init_growth_db

init_growth_db()
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
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


@app.get(
    "/api/users/{user_id}/brief",
    summary="获取用户简要信息",
    description="获取用户简要信息（供推广落地页展示推广员姓名）",
)
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
        "title": "链客宝AI · AI企业家生态",
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


@app.put(
    "/api/system/log-level",
    summary="切换日志级别",
    description="动态切换日志级别（需管理员权限）。可选值：DEBUG / INFO / WARNING / ERROR / CRITICAL",
)
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
        # 注册慢查询监听器
        try:
            from app.database import engine
            from app.slow_query_warning import register_slow_query_listener

            register_slow_query_listener(engine)
        except Exception as sqe:
            logger.warning(f"慢查询监听器注册失败: {sqe}")

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

    # ---- 启动重试引擎 ----
    try:
        _retry_engine = get_retry_engine()
        _retry_engine.start()
        logger.info("重试引擎已启动")
    except Exception as e:
        logger.warning(f"重试引擎启动失败: {e}")

    startup_info = {
        "event": "startup",
        "hostname": hostname,
        "port": int(port) if port.isdigit() else port,
        "db_type": DB_TYPE,
        "route_count": route_count,
        "python_version": os.sys.version.split()[0],
        "log_level": logging.getLevelName(logging.getLogger().level),
        "vector_search": os.environ.get("USE_VECTOR_SEARCH", "0"),
        "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "numpy"),
    }
    logger.info("服务启动完成", extra=startup_info)

    # 向量搜索状态日志
    vs_enabled = os.environ.get("USE_VECTOR_SEARCH", "0") == "1"
    if vs_enabled:
        ep = os.environ.get("EMBEDDING_PROVIDER", "numpy")
        logger.info(f"向量搜索已启用: provider={ep}, rerank_weight={os.environ.get('RERANK_WEIGHT', '0.3')}")
        # 启动向量索引自动同步
        from app.vector_search import sync_vector_index

        try:
            db_session = next(get_db())
            sync_result = sync_vector_index(db_session)
            db_session.close()
            logger.info("向量索引启动同步完成", extra=sync_result)
        except Exception as vsync_e:
            logger.warning(f"向量索引启动同步失败: {vsync_e}")
    else:
        logger.info("向量搜索未启用（设置 USE_VECTOR_SEARCH=1 开启）")

    # ---- 初始化搜索引擎 ----
    try:
        search_engine = search_index_module.get_search_engine()
        logger.info(f"搜索引擎已就绪: {type(search_engine).__name__}")
    except Exception as e:
        logger.warning(f"搜索引擎初始化失败（将在首次搜索时延迟初始化）: {e}")

    # ---- LLM 智能服务状态 ----
    api_key_configured = bool(llm_service_module.DEEPSEEK_API_KEY)
    if api_key_configured:
        logger.info(
            "LLM 服务已就绪",
            extra={
                "model": llm_service_module.DEEPSEEK_MODEL,
                "base_url": llm_service_module.DEEPSEEK_BASE_URL,
            },
        )
    else:
        logger.info("LLM 服务未配置（DEEPSEEK_API_KEY 未设置，相关功能将使用降级方案）")


@app.on_event("shutdown")
def on_shutdown():
    """应用关闭时记录关闭信息并停止重试引擎"""
    import socket

    # ---- 关闭安全中间件 ----
    try:
        close_security_middleware()
        logger.info("安全中间件已关闭")
    except Exception as e:
        logger.warning(f"安全中间件关闭异常: {e}")

    # ---- 停止重试引擎 ----
    try:
        _retry_engine = get_retry_engine()
        _retry_engine.stop()
        logger.info("重试引擎已停止")
    except Exception as e:
        logger.warning(f"重试引擎停止异常: {e}")

    # ---- 关闭 PostHog 客户端 ----
    try:
        from app.posthog_config import close_posthog

        close_posthog()
    except Exception:
        pass

    # ---- 关闭 OpenTelemetry 追踪 ----
    try:
        pass
    except Exception:
        pass

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


@app.get("/", summary="服务根路径", description="返回链客宝AIAPI服务基本信息（服务名、状态、版本）")
def root():
    return {
        "service": "链客宝AI API",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health", summary="深度健康检查", description="深度健康检查：检查数据库连接池、支付通道可达性、系统资源状态")
def health():
    """深度健康检查：检查DB连接池、支付通道可达性、系统资源"""
    db_health = check_db_health()
    payment_health = check_payment_health()
    sys_info = get_system_info()

    # 综合状态: 数据库必须健康，支付通道忽略 not_configured
    all_healthy = db_health["status"] == "healthy" and payment_health["status"] in ("healthy", "not_configured")

    overall_status = "ok" if all_healthy else "degraded"
    http_status = 200 if all_healthy else 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall_status,
            "database": db_health,
            "payment": payment_health,
            "system": sys_info,
            "version": "1.0.0",
        },
    )


@app.get("/health/live", summary="存活检查", description="轻量级存活检查，仅确认服务进程是否运行")
def health_live():
    """存活检查：仅确认服务进程在运行"""
    return {
        "status": "alive",
        "uptime_sec": round(get_uptime()),
    }


@app.get("/health/ready", summary="就绪检查", description="就绪检查：确认数据库和支付通道是否可用")
def health_ready():
    """就绪检查：确认数据库和支付通道是否可用"""
    db_health = check_db_health()
    payment_health = check_payment_health()

    ready = db_health["status"] == "healthy" and payment_health["status"] in ("healthy", "not_configured")

    http_status = 200 if ready else 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ready" if ready else "not_ready",
            "database": db_health,
            "payment": payment_health,
        },
    )


@app.get(
    "/metrics", summary="应用指标", description="应用指标端点：返回Prometheus格式指标（支持 ?format=json 获取JSON格式）"
)
def metrics(format: str = "prometheus"):
    """应用指标端点：返回Prometheus格式或JSON格式"""
    from app.observability import get_metrics_collector

    mc = get_metrics_collector()

    if format == "json":
        return mc.snapshot()

    # 默认: Prometheus 文本格式
    return Response(
        content=mc.generate_prometheus_text(),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )


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


# ===== Sentry ASGI 中间件（包裹在最后，确保捕获所有异常） =====
from app.sentry_config import wrap_with_sentry

app = wrap_with_sentry(app)

# ===== 直接启动入口 =====
from modules.workflow.routes import router as workflow_router

app.include_router(workflow_router)
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print(f"🚀 链客宝AI后端 API :{port}")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
