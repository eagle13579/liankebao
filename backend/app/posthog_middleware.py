"""
PostHog 行为分析中间件
自动采集:
  - page_view (每个 API 请求)
  - API 调用耗时
  - 用户注册事件（通过辅助函数供路由注入）
  - 名片生成事件（通过辅助函数供路由注入）

用法:
    app.add_middleware(PostHogMiddleware)  # 在 CORS 之后注册
"""

import logging
import time

from fastapi import Request

from app.posthog_config import capture_event, identify_user

logger = logging.getLogger(__name__)

# 健康检查 / 静态资源路径白名单（不记录 page_view）
_HEALTH_PATHS = {"/", "/health", "/health/live", "/health/ready", "/metrics", "/docs", "/redoc", "/openapi.json"}
_STATIC_PREFIXES = ("/static", "/app")


class PostHogMiddleware:
    """FastAPI 中间件 — 自动采集 PostHog page_view 和 API 调用耗时"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from fastapi import Request

        request = Request(scope, receive)
        path = request.url.path

        # 跳过健康检查和静态资源
        if path in _HEALTH_PATHS or path.startswith(_STATIC_PREFIXES):
            await self.app(scope, receive, send)
            return

        # 记录开始时间
        start_ns = time.monotonic_ns()

        # 构造自定义 send 以捕获响应状态码
        captured_status_code = [200]  # 默认值

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                captured_status_code[0] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            captured_status_code[0] = 500
            raise
        finally:
            elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000
            status_code = captured_status_code[0]

            # 提取用户 ID（从 request.state 或查询参数）
            user_id = self._extract_user_id(request)

            # 收集事件属性
            properties = {
                "path": path,
                "method": request.method,
                "status_code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
                "host": request.headers.get("host", ""),
                "user_agent": request.headers.get("user-agent", "")[:256],
                "referer": request.headers.get("referer", "")[:512],
            }

            # 异步发送 page_view（PostHog SDK 内部使用队列，不会阻塞）
            capture_event(
                user_id=user_id,
                event="page_view",
                properties=properties,
            )

    @staticmethod
    def _extract_user_id(request: Request) -> str:
        """从请求中提取用户 ID 字符串，匿名用户返回 'anonymous'"""
        # 优先从 state 取（由 auth 中间件/依赖注入设置）
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return str(user_id)

        # 其次从查询参数取（某些公开端点带 user_id）
        query_user_id = request.query_params.get("user_id")
        if query_user_id:
            return str(query_user_id)

        return "anonymous"


# ===== 辅助函数：供路由端点显式调用的埋点 =====


def capture_user_registered(user_id: str, traits: dict = None) -> None:
    """用户注册事件埋点

    在注册成功时调用。
    """
    capture_event(
        user_id=str(user_id),
        event="user_registered",
        properties=traits or {},
    )
    # 同步设置用户属性
    identify_user(str(user_id), traits)


def capture_card_generated(user_id: str, card_properties: dict = None) -> None:
    """名片生成事件埋点

    在数字名片成功生成时调用。
    """
    capture_event(
        user_id=str(user_id),
        event="card_generated",
        properties=card_properties or {},
    )
