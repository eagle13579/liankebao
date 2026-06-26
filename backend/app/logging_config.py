"""
链客宝结构化日志配置
=====================
统一的 JSON 结构化日志模块，支持日志轮转、请求 ID 追踪、
环境感知级别控制。

用法:
    # 在应用入口处初始化
    from app.logging_config import setup_logging
    setup_logging()

    # 在任意模块中获取日志器
    from app.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("hello world", extra={"user_id": 123})

    # 或者使用标准 logging.getLogger() — 自动继承配置
    import logging
    logger = logging.getLogger("chainke.api")

环境变量:
    LOG_LEVEL           — 日志级别 (DEBUG/INFO/WARNING/ERROR), 默认 INFO
    LOG_JSON            — JSON 格式开关 (1/true 启用), 默认生产环境启用
    LOG_DIR             — 日志文件目录, 默认 ./logs
    LOG_MAX_BYTES       — 单个日志文件最大字节, 默认 100MB
    LOG_BACKUP_COUNT    — 保留的轮转文件数, 默认 30
    APP_ENV             — 环境名称 (development/production/testing), 默认 development
"""

import json
import logging
import logging.handlers
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── 请求 ID 上下文 ──────────────────────────────────────────────────
# 允许在异步请求中跨模块传递 request_id
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    """设置当前上下文的请求 ID"""
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """获取当前上下文的请求 ID"""
    return request_id_var.get()


# ── JSON 格式化器 ───────────────────────────────────────────────────


class JSONFormatter(logging.Formatter):
    """
    将日志记录格式化为 JSON 行。

    输出字段:
        timestamp   — ISO-8601 时间戳 (UTC)
        level       — 日志级别名称
        logger      — 日志器名称
        message     — 日志消息
        request_id  — 请求追踪 ID (若上下文中有)
        extra       — 用户自定义额外字段
        exception   — 异常堆栈信息 (若有)
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 附加请求 ID (从上下文变量获取)
        rid = get_request_id()
        if rid:
            log_entry["request_id"] = rid

        # 附加异常信息
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # 附加用户自定义 extra 字段 (排除标准 LogRecord 属性)
        standard_attrs = {
            "args", "asctime", "created", "exc_info", "exc_text",
            "filename", "funcName", "levelname", "levelno", "lineno",
            "message", "module", "msecs", "msg", "name", "pathname",
            "process", "processName", "relativeCreated", "stack_info",
            "thread", "threadName", "taskName",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
        if extras:
            log_entry["extra"] = extras

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# ── 开发环境友好格式化器 ────────────────────────────────────────────


class ColorFormatter(logging.Formatter):
    """开发环境友好的彩色文本格式化器"""

    _COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        level_color = self._COLORS.get(record.levelname, "")
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S")
        rid = get_request_id()
        rid_part = f" [rid={rid}]" if rid else ""
        return (
            f"{level_color}{record.levelname:8s}{self._RESET} | "
            f"{timestamp} | "
            f"{record.name:20s} |"
            f"{rid_part} "
            f"{record.getMessage()}"
        )


# ── 日志配置 ────────────────────────────────────────────────────────


def _read_env_bool(key: str, default: bool) -> bool:
    """读取环境变量并解析为布尔值"""
    val = os.getenv(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def setup_logging() -> None:
    """
    统一初始化日志系统。

    在 FastAPI 应用启动时尽早调用此函数。在所有模块 import 之前
    执行，确保所有 loggers 继承统一配置。

    行为差异:
        - 生产环境 (APP_ENV=production): JSON 格式 + 文件轮转
        - 开发环境 (默认): 彩色终端输出
    """
    env = os.getenv("APP_ENV", "development")
    log_level = os.getenv("LOG_LEVEL", "DEBUG" if env == "development" else "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)
    use_json = _read_env_bool("LOG_JSON", default=(env == "production"))

    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 清除已有的处理器 (避免重复初始化)
    root_logger.handlers.clear()

    # ── 控制台处理器 ─────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    if use_json:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ColorFormatter())

    root_logger.addHandler(console_handler)

    # ── 文件轮转处理器 (仅生产环境) ────────────────────────────
    if env == "production":
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)

        max_bytes = int(os.getenv("LOG_MAX_BYTES", str(100 * 1024 * 1024)))  # 100MB
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "30"))

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_dir / "app.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # ── 调整第三方库日志等级 ─────────────────────────────────────
    # 避免 uvicorn/httpx 等库的调试信息刷屏
    noisy_loggers = [
        "uvicorn.access",
        "uvicorn.error",
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    # 保留 uvicorn 自己的日志器但控制等级
    logging.getLogger("uvicorn").setLevel(logging.INFO if env == "production" else logging.DEBUG)

    # ── 启动日志 ─────────────────────────────────────────────────
    logger = logging.getLogger("chainke.boot")
    logger.info(
        "Logging initialized — env=%s, level=%s, json=%s",
        env, log_level, use_json,
    )


def get_logger(name: str) -> logging.Logger:
    """
    获取结构化日志器。

    用法:
        logger = get_logger(__name__)
        logger.info("message", extra={"key": "value"})

    与 logging.getLogger(name) 等价，但确保日志系统已就绪。
    """
    return logging.getLogger(name)
