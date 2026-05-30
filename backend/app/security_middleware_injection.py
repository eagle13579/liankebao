#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全中间件注入文件 (Security Middleware Injection)
===================================================
为链客宝后端 FastAPI 应用注入可选的数据安全中间件。

功能:
  - 拦截所有写入 core schema 的 HTTP 请求 (POST/PUT/PATCH/DELETE)
  - 调用 data_security_loader.DataSecurity.validate_and_write() 验证数据
  - 不影响只读请求 (GET/HEAD/OPTIONS)
  - 按环境变量 SECURITY_MIDDLEWARE_ENABLED=true/false 开关 (默认关闭)
  - 添加 /api/security/health 健康检查端点
  - 添加 /api/security/stats 统计端点

用法 (在 main.py 中):
    from app.security_middleware_injection import init_security_middleware
    init_security_middleware(app)

环境变量:
    SECURITY_MIDDLEWARE_ENABLED  — true 开启, false 关闭 (默认 false)
    SECURITY_DATA_DIR            — data_security 模块所在目录 (默认: ../data_security)
    SECURITY_CONTRACTS_DIR       — 契约文件目录 (默认: data_security/contracts)
    SECURITY_QUARANTINE_DB       — 检疫区数据库路径 (默认: 系统临时目录)

模块：向海容知識庫 · 記憶宮殿 · 数据安全层
"""

import json
import logging
import os
import sys
import time
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_security_instance = None
_enabled = False
_stats = {
    "total_requests": 0,
    "passed": 0,
    "rejected": 0,
    "quarantined": 0,
    "errors": 0,
    "start_time": time.time(),
}


def _load_security_module(data_dir: str):
    """动态加载 data_security 模块"""
    data_dir = os.path.abspath(data_dir)
    if data_dir not in sys.path:
        sys.path.insert(0, data_dir)

    try:
        from data_security_loader import DataSecurity
        return DataSecurity
    except ImportError as e:
        logger.warning(f"无法加载 data_security 模块 (from {data_dir}): {e}")
        return None


def _is_write_request(method: str, path: str) -> bool:
    """判断是否为写入 core schema 的请求"""
    # 只拦截写操作
    if method.upper() not in ("POST", "PUT", "PATCH", "DELETE"):
        return False

    # 跳过安全相关的 API 端点自身
    if path.startswith(("/api/security/", "/health", "/metrics", "/docs", "/redoc", "/openapi.json")):
        return False

    # 匹配 core schema 路径 (包含 /api/ 的写入请求)
    # 只有 /api/ 路径下的写入请求才需要检查
    if not path.startswith("/api/"):
        return False

    return True


def _extract_core_table(path: str, method: str) -> Optional[str]:
    """从请求路径中提取 core schema 表名"""
    # 尝试从路径中提取有意义的表名
    parts = [p for p in path.split("/") if p]

    # 跳过 api/v1 或 api
    if parts and parts[0] == "api":
        parts = parts[1:]
    if parts and parts[0] in ("v1", "v2"):
        parts = parts[1:]

    if not parts:
        return None

    # 使用资源名作为表名
    resource = parts[0]
    # Map common resources to core tables
    table_map = {
        "auth": "core.users",
        "users": "core.users",
        "products": "core.products",
        "orders": "core.orders",
        "contacts": "core.contacts",
        "business_card": "core.business_cards",
        "payment": "core.payments",
        "notifications": "core.notifications",
        "activities": "core.activities",
        "insights": "core.insights",
        "needs": "core.needs",
        "admin": "core.admin_logs",
    }
    return table_map.get(resource, f"core.{resource}")


def _extract_module(path: str) -> str:
    """从请求路径中提取模块名"""
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "api":
        parts = parts[1:]
    if parts and parts[0] in ("v1", "v2"):
        parts = parts[1:]
    return parts[0] if parts else "unknown"


async def _security_middleware(request: Request, call_next):
    """FastAPI 中间件：拦截写入 core schema 的请求并调用 DataSecurity 验证"""
    global _security_instance, _enabled, _stats

    if not _enabled or _security_instance is None:
        return await call_next(request)

    method = request.method
    path = request.url.path

    # 只拦截写入 core schema 的请求
    if not _is_write_request(method, path):
        return await call_next(request)

    _stats["total_requests"] += 1

    # 尝试读取请求体
    try:
        body = await request.body()
        if not body:
            return await call_next(request)

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 非 JSON 请求体，跳过
            return await call_next(request)
    except Exception:
        _stats["errors"] += 1
        return await call_next(request)

    # 提取模块和表名
    module = _extract_module(path)
    table = _extract_core_table(path, method) or f"core.{module}"

    # 构建上下文
    context = {
        "_dwg_mode": os.environ.get("SECURITY_DWG_MODE", "normal"),
        "user_id": getattr(request.state, "user_id", 0) or 0,
        "request_id": getattr(request.state, "trace_id", f"req-{int(time.time())}"),
        "module_name": module,
        "ip": request.client.host if request.client else "",
        "method": method,
        "path": path,
    }

    try:
        result = _security_instance.validate_and_write(
            module=module,
            table=table,
            data=data,
            context=context,
        )
    except Exception as e:
        logger.error(f"安全中间件内部异常: {e}", exc_info=True)
        _stats["errors"] += 1
        return await call_next(request)

    status = result.get("status", "passed")

    if status == "rejected":
        _stats["rejected"] += 1
        logger.warning(
            "安全中间件拒绝请求",
            extra={"path": path, "method": method, "reason": result.get("reason", "")},
        )
        return JSONResponse(
            status_code=403,
            content={
                "code": 403,
                "message": "请求被安全策略拒绝",
                "reason": result.get("reason", "数据验证未通过"),
                "security_status": "rejected",
            },
        )

    if status == "quarantined":
        _stats["quarantined"] += 1
        logger.warning(
            "安全中间件隔离请求",
            extra={
                "path": path,
                "method": method,
                "reason": result.get("reason", ""),
                "quarantine_id": result.get("quarantine_id"),
            },
        )
        # 隔离模式下允许写入，但记录
        # 在响应头中标记
        response = await call_next(request)
        response.headers["X-Security-Status"] = "quarantined"
        if result.get("quarantine_id"):
            response.headers["X-Security-Quarantine-ID"] = str(result["quarantine_id"])
        return response

    # passed
    _stats["passed"] += 1
    return await call_next(request)


def _register_security_routes(app: FastAPI):
    """注册安全相关的 API 端点"""

    @app.get("/api/security/health", summary="安全中间件健康检查")
    async def security_health():
        """安全中间件健康检查端点"""
        global _security_instance, _enabled
        if not _enabled:
            return {
                "status": "disabled",
                "message": "安全中间件未启用 (设置 SECURITY_MIDDLEWARE_ENABLED=true 开启)",
            }
        if _security_instance is None:
            return {
                "status": "error",
                "message": "安全中间件未初始化",
            }
        return {
            "status": "healthy",
            "message": "安全中间件运行中",
            "enabled": _enabled,
        }

    @app.get("/api/security/stats", summary="安全中间件统计")
    async def security_stats():
        """安全中间件统计端点"""
        global _stats, _enabled
        uptime = time.time() - _stats["start_time"]
        return {
            "enabled": _enabled,
            "uptime_sec": round(uptime, 2),
            "total_requests": _stats["total_requests"],
            "passed": _stats["passed"],
            "rejected": _stats["rejected"],
            "quarantined": _stats["quarantined"],
            "errors": _stats["errors"],
            "pass_rate": f"{(_stats['passed'] / max(_stats['total_requests'], 1)) * 100:.1f}%",
        }


def init_security_middleware(app: FastAPI):
    """
    初始化安全中间件并注入到 FastAPI 应用。

    参数:
        app: FastAPI 应用实例

    环境变量:
        SECURITY_MIDDLEWARE_ENABLED — 设为 true 启用 (默认 false)
        SECURITY_DATA_DIR           — data_security 模块目录 (默认: ../data_security)
        SECURITY_CONTRACTS_DIR      — 契约文件目录 (默认: data_security/contracts)
    """
    global _security_instance, _enabled

    # 检查是否启用
    enabled = os.environ.get("SECURITY_MIDDLEWARE_ENABLED", "false").lower()
    if enabled not in ("true", "1", "yes"):
        logger.info("安全中间件未启用 (SECURITY_MIDDLEWARE_ENABLED=false)")
        # 即使未启用也注册端点，让用户可以查看状态
        _enabled = False
        _register_security_routes(app)
        return

    _enabled = True

    # 确定 data_security 模块目录
    data_dir = os.environ.get(
        "SECURITY_DATA_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data_security"),
    )

    contracts_dir = os.environ.get(
        "SECURITY_CONTRACTS_DIR",
        os.path.join(data_dir, "contracts"),
    )

    quarantine_db = os.environ.get(
        "SECURITY_QUARANTINE_DB",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "data",
            "security_quarantine.db",
        ),
    )

    # 加载 DataSecurity 模块
    DataSecurity = _load_security_module(data_dir)
    if DataSecurity is None:
        logger.error(
            f"安全中间件初始化失败: data_security 模块未找到 (搜索路径: {data_dir})"
        )
        _register_security_routes(app)
        return

    try:
        _security_instance = DataSecurity(
            contracts_dir=contracts_dir,
            quarantine_db=quarantine_db,
            verbose=os.environ.get("SECURITY_VERBOSE", "false").lower() == "true",
        )
        logger.info("安全中间件初始化成功")
        logger.info(f"  契约目录: {contracts_dir}")
        logger.info(f"  检疫区数据库: {quarantine_db}")
    except Exception as e:
        logger.error(f"安全中间件初始化失败: {e}", exc_info=True)
        _register_security_routes(app)
        return

    # 注册路由端点 (包括健康检查和统计)
    _register_security_routes(app)

    # 注入中间件
    app.middleware("http")(_security_middleware)
    logger.info("安全中间件已注入到 FastAPI 应用")


def close_security_middleware():
    """关闭安全中间件，释放资源"""
    global _security_instance
    if _security_instance is not None:
        try:
            _security_instance.close()
            logger.info("安全中间件已关闭")
        except Exception as e:
            logger.warning(f"安全中间件关闭异常: {e}")
        _security_instance = None
