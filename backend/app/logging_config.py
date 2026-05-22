"""
结构化 JSON 日志配置（升级版）
- request_id 追踪（基于 uuid）
- user_id 注入（通过 contextvars）
- JSON 行输出
- 动态日志级别切换（运行时）
- 请求耗时中间件
"""
import os
import sys
import json
import uuid
import logging
import traceback
from datetime import datetime, timezone
from contextvars import ContextVar

from fastapi import Request
from starlette.responses import Response

# ============================================================
# 上下文变量（用于在请求链路中传递 request_id 和 user_id）
# ============================================================
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
_user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")


def get_request_id() -> str:
    """获取当前请求的 request_id"""
    return _request_id_ctx.get()


def get_user_id() -> str:
    """获取当前请求的 user_id"""
    return _user_id_ctx.get()


# ============================================================
# 动态日志级别控制器
# ============================================================
_LOG_LEVEL_OVERRIDE: ContextVar[str | None] = ContextVar(
    "log_level_override", default=None
)


def set_log_level(level: str):
    """
    运行时动态设置根日志级别

    Args:
        level: DEBUG / INFO / WARNING / ERROR / CRITICAL
    """
    level = level.upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError(f"无效日志级别: {level}")

    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level)

    # 记录级别变更
    root.info("日志级别已动态切换", extra={"new_level": level})


def get_current_log_level() -> str:
    """获取当前日志级别"""
    return logging.getLogger().level


# ============================================================
# 格式化器
# ============================================================
class StructuredJsonFormatter(logging.Formatter):
    """结构化 JSON 日志格式器（升级版：自动读取上下文中的 request_id / user_id）"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        # ---- 自动注入上下文 request_id ----
        rid = get_request_id()
        if rid:
            log_entry["request_id"] = rid
        elif hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # ---- 自动注入上下文 user_id ----
        uid = get_user_id()
        if uid:
            log_entry["user_id"] = uid
        elif hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id

        # ---- 异常信息 ----
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": "".join(traceback.format_exception(*record.exc_info)),
            }

        # ---- 自定义额外字段 ----
        skip_keys = {
            "args", "asctime", "created", "exc_info", "exc_text",
            "filename", "funcName", "id", "levelname", "levelno",
            "lineno", "module", "msecs", "message", "msg",
            "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName",
            "request_id", "user_id",
        }
        for key, value in record.__dict__.items():
            if key not in skip_keys:
                try:
                    json.dumps({key: value})
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        return json.dumps(log_entry, ensure_ascii=False)


# ============================================================
# 日志初始化
# ============================================================
def setup_logging():
    """配置结构化日志"""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    # 控制台处理器（JSON 行）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(console_handler)

    # 可选：文件处理器
    log_file = os.environ.get("LOG_FILE", "")
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(log_level)
            file_handler.setFormatter(StructuredJsonFormatter())
            root_logger.addHandler(file_handler)
        except Exception as e:
            root_logger.warning(f"无法创建日志文件 {log_file}: {e}")

    # 调低第三方库日志噪音
    for noisy in ("httpx", "httpcore", "urllib3", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root_logger.info(
        "结构化日志已初始化",
        extra={"log_level": log_level},
    )


# ============================================================
# FastAPI 中间件
# ============================================================
class RequestLogMiddleware:
    """
    FastAPI 中间件：
    1. 为每个请求生成唯一 request_id（uuid4）
    2. 注入到日志上下文（日志自动携带）
    3. 记录请求耗时
    """

    def __init__(self, app, header_name: str = "X-Request-ID"):
        self.app = app
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        # 兼容 Starlette 1.0.0 BaseHTTPMiddleware
        return await self._process(request, call_next)

    async def __call__(self, scope, receive, send):
        # Starlette 1.0.0 ASGI 接口
        async def call_next(request):
            return await self._process(request, None)
        
        # 简单 ASGI 包装
        from starlette.middleware.base import _CachedRequest
        request = _CachedRequest(scope, receive)
        response = await self._process(request, None)
        await response(scope, receive, send)

    async def _process(self, request: Request, call_next=None):
        # ---- 生成/提取 request_id ----
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid.uuid4())

        # ---- 设置上下文 ----
        token_rid = _request_id_ctx.set(request_id)
        token_uid = _user_id_ctx.set("")  # user_id 后续可由认证中间件设置

        # ---- 记录请求开始 ----
        logger = logging.getLogger("api")
        start = datetime.now(timezone.utc)

        logger.info(
            "请求开始",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "client_ip": request.client.host if request.client else "",
            },
        )

        # ---- 执行请求 ----
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            logger.error(
                "请求异常",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "elapsed_sec": round(elapsed, 4),
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise
        finally:
            _request_id_ctx.reset(token_rid)
            _user_id_ctx.reset(token_uid)

        # ---- 记录请求结束 ----
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info(
            "请求完成",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_sec": round(elapsed, 4),
            },
        )

        # ---- 响应头注入 request_id ----
        response.headers[self.header_name] = request_id

        return response


# ============================================================
# 辅助函数：在认证成功后设置 user_id
# ============================================================
def set_user_id(user_id: int | str):
    """在认证中间件/路由中调用，将 user_id 注入日志上下文"""
    _user_id_ctx.set(str(user_id))


class RequestIdFilter(logging.Filter):
    """为日志记录添加 request_id（兼容旧代码）"""

    def __init__(self, request_id: str = ""):
        super().__init__()
        self.request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = self.request_id
        return True
