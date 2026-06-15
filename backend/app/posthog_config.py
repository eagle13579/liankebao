"""
PostHog 用户行为分析埋点配置模块
通过环境变量 POSTHOG_API_KEY 和 POSTHOG_HOST 惰性初始化 PostHog 客户端

用法:
    from app.posthog_config import capture_event, identify_user
    capture_event("user_123", "event_name", {"property": "value"})
    identify_user("user_123", {"email": "user@example.com"})
"""

import logging
import os

logger = logging.getLogger(__name__)

_posthog_initialized: bool = False


def _get_posthog():
    """获取 PostHog 客户端实例（惰性初始化）"""
    global _posthog_initialized
    if _posthog_initialized:
        import posthog

        return posthog

    api_key = os.environ.get("POSTHOG_API_KEY", "").strip()
    host = os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com").strip()

    if not api_key:
        logger.info("PostHog 未配置（POSTHOG_API_KEY 未设置），跳过初始化")
        return None

    try:
        import posthog

        posthog.api_key = api_key
        posthog.host = host
        posthog.debug = os.environ.get("POSTHOG_DEBUG", "").lower() in ("1", "true", "yes")
        _posthog_initialized = True
        logger.info("PostHog 客户端初始化完成，host=%s", host)
        return posthog
    except ImportError:
        logger.warning("posthog 库未安装，PostHog 埋点不可用")
        return None
    except Exception as exc:
        logger.warning("PostHog 客户端初始化失败: %s", exc)
        return None


def capture_event(user_id: str, event: str, properties: dict = None) -> None:
    """捕获 PostHog 事件

    Args:
        user_id: 用户唯一标识（字符串）
        event: 事件名称（如 "page_view", "user_registered", "card_generated"）
        properties: 事件属性字典
    """
    ph = _get_posthog()
    if ph is None:
        return
    try:
        ph.capture(
            distinct_id=str(user_id),
            event=event,
            properties=properties or {},
        )
    except Exception as exc:
        logger.warning("PostHog capture_event 失败: %s", exc)


def identify_user(user_id: str, traits: dict = None) -> None:
    """识别 / 更新用户属性

    Args:
        user_id: 用户唯一标识（字符串）
        traits: 用户属性字典（如 {"email": "...", "name": "...", "role": "..."}）
    """
    ph = _get_posthog()
    if ph is None:
        return
    try:
        ph.identify(
            distinct_id=str(user_id),
            properties=traits or {},
        )
    except Exception as exc:
        logger.warning("PostHog identify_user 失败: %s", exc)


def is_posthog_active() -> bool:
    """检查 PostHog 是否已激活"""
    return _posthog_initialized


def close_posthog() -> None:
    """关闭 PostHog 客户端（应用关闭时调用）"""
    ph = _get_posthog()
    if ph is None:
        return
    try:
        ph.shutdown()
        logger.info("PostHog 客户端已关闭")
    except Exception as exc:
        logger.warning("PostHog 关闭失败: %s", exc)
