"""
Sentry 错误追踪配置模块
通过环境变量 SENTRY_DSN 惰性初始化 Sentry SDK

用法:
    from app.sentry_config import setup_sentry, wrap_with_sentry
    setup_sentry()          # 在 FastAPI 应用启动时调用
    app = wrap_with_sentry(app)  # 用 Sentry ASGI 中间件包裹应用
"""

import logging
import os

logger = logging.getLogger(__name__)

_sentry_initialized: bool = False


def setup_sentry() -> None:
    """惰性初始化 Sentry SDK

    仅在 SENTRY_DSN 环境变量存在时初始化。
    可安全多次调用——仅首次执行实际初始化。
    """
    global _sentry_initialized
    if _sentry_initialized:
        return

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("Sentry 未配置（SENTRY_DSN 未设置），跳过初始化")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("ENV", "development"),
            traces_sample_rate=float(
                os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0")
            ),
            integrations=[
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
        )
        _sentry_initialized = True
        logger.info("Sentry SDK 初始化完成，DSN=%s...", dsn[:20])
    except ImportError:
        logger.warning("sentry-sdk 未安装，Sentry 错误追踪不可用")
    except Exception as exc:
        logger.warning("Sentry SDK 初始化失败: %s", exc)


def wrap_with_sentry(app):
    """用 Sentry ASGI 中间件包裹 FastAPI 应用

    仅在 Sentry 已初始化且 sentry-sdk 可用时生效。
    应放在应用配置的最后一步调用，以确保捕获所有异常。
    """
    if not _sentry_initialized:
        return app
    try:
        from sentry_sdk.integrations.asgi import SentryASGIMiddleware

        logger.info("已应用 Sentry ASGI 中间件")
        return SentryASGIMiddleware(app)
    except ImportError:
        return app


def is_sentry_active() -> bool:
    """检查 Sentry 是否已激活并正在运行"""
    return _sentry_initialized
