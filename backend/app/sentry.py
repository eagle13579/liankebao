"""
链客宝 Sentry 错误追踪
=======================
Sentry SDK 初始化模块，支持从环境变量读取 DSN，无 DSN 或
sentry-sdk 未安装时自动降级（不崩溃、静默跳过）。

用法:
    from app.sentry import init_sentry, sentry_is_active

    init_sentry()           # 在 FastAPI 应用启动时调用
    if sentry_is_active():
        # 手动捕获异常
        ...

环境变量:
    SENTRY_DSN              — Sentry DSN（必填，为空则跳过初始化）
    SENTRY_ENVIRONMENT      — 环境名称（默认 "production"）
    SENTRY_TRACES_SAMPLE_RATE — 性能追踪采样率（默认 0.1）
"""

import logging
import os

logger = logging.getLogger("chainke.sentry")

# ── 状态 ───────────────────────────────────────────────────────────
_sentry_active = False


def sentry_is_active() -> bool:
    """Sentry 是否已成功初始化"""
    return _sentry_active


def init_sentry() -> None:
    """
    初始化 Sentry SDK。

    自动从环境变量读取配置。若 sentry-sdk 未安装或 SENTRY_DSN 为空，
    则静默降级，不抛出任何异常。
    """
    global _sentry_active

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("[Sentry] SENTRY_DSN 未设置，跳过 Sentry 初始化")
        _sentry_active = False
        return

    # ── 尝试导入 sentry_sdk ────────────────────────────────────────
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("[Sentry] sentry-sdk 未安装，跳过 Sentry 初始化")
        _sentry_active = False
        return

    # ── 读取其余配置 ────────────────────────────────────────────────
    environment = os.getenv("SENTRY_ENVIRONMENT", "production")
    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            # 不发送个人身份信息
            send_default_pii=False,
            # 按端点聚合异常
            attach_stacktrace=True,
        )
        _sentry_active = True
        logger.info("[Sentry] 初始化成功 — environment=%s, traces_sample_rate=%s",
                     environment, traces_sample_rate)
    except Exception as exc:
        logger.warning("[Sentry] 初始化失败: %s — 降级跳过", exc)
        _sentry_active = False
