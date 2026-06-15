"""
SQLAlchemy 慢查询事件监听器

通过 SQLAlchemy 事件系统监听 after_cursor_execute，
对执行时间超过阈值的查询打印警告/错误日志。

阈值:
- > 500ms: warning 级别日志
- > 2s:    error 级别日志 + 打印调用堆栈

用法:
    from app.slow_query_warning import register_slow_query_listener
    register_slow_query_listener()
"""

import logging
import time
import traceback

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# 阈值配置（毫秒）
WARN_THRESHOLD_MS = 500
ERROR_THRESHOLD_MS = 2000

# 已注册标志，防止重复注册
_registered = False


def register_slow_query_listener(engine: Engine) -> None:
    """
    注册 SQLAlchemy 慢查询事件监听器

    Args:
        engine: SQLAlchemy引擎实例
    """
    global _registered
    if _registered:
        logger.debug("慢查询监听器已注册，跳过重复注册")
        return

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        """在执行查询前记录开始时间"""
        conn.info.setdefault("query_start_time", {})
        conn.info["query_start_time"]["time"] = time.time()

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        """在执行查询后检查耗时，超过阈值则记录日志"""
        start_time = conn.info.get("query_start_time", {}).get("time")
        if start_time is None:
            return

        elapsed_sec = time.time() - start_time
        elapsed_ms = round(elapsed_sec * 1000, 2)

        # 清理存储的开始时间
        conn.info["query_start_time"] = {}

        if elapsed_ms < WARN_THRESHOLD_MS:
            return

        # 截断超长 SQL 语句，避免日志爆炸
        sql_preview = statement
        if len(sql_preview) > 1000:
            sql_preview = sql_preview[:1000] + f"... [truncated, total {len(statement)} chars]"

        extra = {
            "elapsed_ms": elapsed_ms,
            "sql": sql_preview,
            "parameters": _safe_repr(parameters),
        }

        if elapsed_ms >= ERROR_THRESHOLD_MS:
            # > 2s: error 日志 + 堆栈
            stack = "".join(traceback.format_stack(limit=10))
            logger.error(
                f"慢查询(严重): {elapsed_ms}ms — 执行时间超过 {ERROR_THRESHOLD_MS}ms 阈值",
                extra={**extra, "stack": stack},
            )
        else:
            # > 500ms: warning 日志
            logger.warning(
                f"慢查询: {elapsed_ms}ms — 执行时间超过 {WARN_THRESHOLD_MS}ms 阈值",
                extra=extra,
            )

    _registered = True
    logger.info(f"慢查询监听器已注册: warning > {WARN_THRESHOLD_MS}ms, error > {ERROR_THRESHOLD_MS}ms")


def _safe_repr(params) -> str:
    """安全地将参数转换为字符串（截断避免日志爆炸）"""
    try:
        text = repr(params)
        if len(text) > 500:
            text = text[:500] + f"... [truncated, total {len(text)} chars]"
        return text
    except Exception:
        return "<repr failed>"
