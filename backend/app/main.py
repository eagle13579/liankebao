"""链客宝后端 API 服务 - 主入口"""
import os
import sys
import logging
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketState

# ===== 结构化日志（最先加载） =====
from app.logging_config import setup_logging, RequestLogMiddleware, set_log_level, get_current_log_level, set_user_id

setup_logging()

logger = logging.getLogger(__name__)

# ===== 统一数据库（SQLite/MySQL 自适应） =====
from app.database import init_db, get_db

from app.routers import auth, products, orders, promoter, admin, search, imports as import_router
import app.routers.contacts as contacts_module
import app.routers.activities as activities_module
import app.routers.payment as payment_module
import recharge.routes as recharge_module
import recharge.callback as recharge_callback_module

# ===== 通知系统 & WebSocket =====
from app.notifications import NotificationManager
from app.websocket_manager import ws_manager

# ===== 认证 =====
from app.auth import get_current_user, verify_token
from app.models import User

app = FastAPI(
    title="链客宝 API",
    description="Premium Business Network and Entrepreneur Supply-Demand Matching Platform",
    version="1.0.0",
)

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

# ===== 请求日志中间件（request_id + 耗时追踪，在 CORS 之后注册） =====
# 日志系统已在 setup_logging() 初始化
# 中间件已移除 — 旧版 RequestLogMiddleware 兼容 Starlette 新版本

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

router_modules = [auth, products, orders, promoter, admin, search, import_router, contacts_module, activities_module, payment_module, recharge_module]

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
app.include_router(recharge_module.router)
app.include_router(recharge_callback_module.callback_router)
import os
from fastapi.staticfiles import StaticFiles

_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


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


@app.get("/banners")
def list_banners():
    """获取首页轮播图列表"""
    return {"code": 200, "message": "success", "data": BANNERS}


@app.get("/api/banners")
def list_banners_api():
    """获取首页轮播图列表（带 /api 前缀兼容）"""
    return {"code": 200, "message": "success", "data": BANNERS}


# ============================================================
# 通知 API
# ============================================================
@app.get("/api/notifications")
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


@app.get("/api/notifications/unread-count")
def unread_notification_count(
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的未读通知数"""
    count = NotificationManager.get_unread_count(user_id=current_user.id)
    return {"code": 200, "message": "success", "data": {"unread_count": count}}


@app.put("/api/notifications/{notification_id}/read")
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


@app.put("/api/notifications/read-all")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
):
    """标记当前用户所有通知为已读"""
    updated = NotificationManager.mark_all_as_read(user_id=current_user.id)
    return {"code": 200, "message": "success", "data": {"updated_count": updated}}


@app.delete("/api/notifications/{notification_id}")
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
    WebSocket 连接端点。
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
@app.get("/api/system/log-level")
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


@app.put("/api/system/log-level")
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
# 启动事件
# ============================================================
@app.on_event("startup")
def on_startup():
    """应用启动时初始化数据库"""
    try:
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
        raise


@app.get("/")
def root():
    return {
        "service": "链客宝 API",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
