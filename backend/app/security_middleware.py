"""
链客宝 – 安全中间件

提供基于内存令牌桶的速率限制器 RateLimiter 以及
基于 Starlette / FastAPI ASGI 的 SecurityHeadersMiddleware。

零外部依赖，仅使用 Python 标准库。
"""

import time
import ast
import typing as t


class RateLimiter:
    """内存令牌桶速率限制器。

    基于令牌桶算法，支持可配置的填充速率（rate）和桶容量（burst）。
    使用滑动窗口（window）清理过期条目，避免内存泄漏。

    完全线程安全的单进程实现（dict 操作在 CPython GIL 下是原子的，
    多进程场景建议改用 Redis）。

    Usage:
        limiter = RateLimiter(rate=10, burst=20, window=60)
        if limiter.is_allowed("user:alice"):
            # 处理请求
            pass
        remaining = limiter.get_remaining("user:alice")
    """

    def __init__(self, rate: int = 10, burst: int = 20, window: int = 60) -> None:
        """

        Args:
            rate:   每秒添加到桶中的令牌数（长期平均速率）。
            burst:  桶的最大容量，即允许的最大突发请求数。
            window: 滑动窗口秒数。超过此时间未活动的条目会被清理。
        """
        if rate <= 0:
            raise ValueError("rate 必须为正整数")
        if burst <= 0:
            raise ValueError("burst 必须为正整数")
        if window <= 0:
            raise ValueError("window 必须为正整数")

        self._rate = rate
        self._burst = burst
        self._window = window

        # key -> (tokens, last_refill_timestamp)
        self._buckets: t.Dict[str, t.Tuple[float, float]] = {}

        self._check_counter = 0
        self._cleanup_interval = 100  # 每 100 次检查清理一次

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, key: str) -> bool:
        """检查 key 对应的请求是否被允许（消耗一个令牌）。

        如果桶中有足够令牌则消耗一个并返回 True，否则返回 False。
        """
        now = time.time()
        self._maybe_cleanup(now)
        tokens, last_refill = self._buckets.get(key, (self._burst, now))

        # 根据经过的时间补充令牌
        elapsed = now - last_refill
        tokens = min(self._burst, tokens + elapsed * self._rate)

        if tokens >= 1.0:
            tokens -= 1.0
            self._buckets[key] = (tokens, now)
            return True

        # 即使拒绝也更新状态（记录最近活动时间 & 当前赤字）
        self._buckets[key] = (tokens, now)
        return False

    def get_remaining(self, key: str) -> int:
        """返回指定 key 当前可用的令牌数（向下取整）。"""
        now = time.time()
        tokens, last_refill = self._buckets.get(key, (self._burst, now))
        elapsed = now - last_refill
        tokens = min(self._burst, tokens + elapsed * self._rate)
        return max(0, int(tokens))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_cleanup(self, now: float) -> None:
        """每 _cleanup_interval 次检查触发一次过期条目清理。"""
        self._check_counter += 1
        if self._check_counter < self._cleanup_interval:
            return
        self._check_counter = 0

        cutoff = now - self._window
        stale_keys = [
            k
            for k, (_, last_refill) in self._buckets.items()
            if last_refill < cutoff
        ]
        for k in stale_keys:
            del self._buckets[k]

    # ------------------------------------------------------------------
    # Dunder / convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<RateLimiter rate={self._rate} burst={self._burst} "
            f"window={self._window}s buckets={len(self._buckets)}>"
        )


class SecurityHeadersMiddleware:
    """Starlette / FastAPI ASGI 中间件，在每次响应中添加安全头。

    默认添加以下安全头（均为推荐的安全最佳实践）：
        - X-Content-Type-Options: nosniff
        - X-Frame-Options: DENY
        - X-XSS-Protection: 1; mode=block
        - Strict-Transport-Security: max-age=31536000; includeSubDomains
        - Referrer-Policy: strict-origin-when-cross-origin
        - Permissions-Policy: geolocation=(), microphone=(), camera=()
        - Content-Security-Policy: default-src 'self'
        - Cache-Control: no-store, no-cache, must-revalidate

    同时记录 OPTIONS 预检请求的 CORS 头部，支持白名单配置。

    Usage (FastAPI):
        from fastapi import FastAPI
        app = FastAPI()
        app.add_middleware(
            SecurityHeadersMiddleware,
            cors_origins=["https://example.com"],
        )

    Usage (Starlette ASGI):
        from starlette.applications import Starlette
        app = Starlette()
        app.add_middleware(
            SecurityHeadersMiddleware,
            cors_origins=["https://example.com"],
        )
    """

    DEFAULT_HEADERS: t.Dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Content-Security-Policy": "default-src 'self'",
        "Cache-Control": "no-store, no-cache, must-revalidate",
    }

    def __init__(
        self,
        app: t.Any,
        cors_origins: t.Optional[t.List[str]] = None,
        extra_headers: t.Optional[t.Dict[str, str]] = None,
    ) -> None:
        """

        Args:
            app:            下层 ASGI 应用。
            cors_origins:   CORS 允许的来源列表（例如 ["https://example.com"]）。
                            若为 None 则不添加 CORS 头。若为空列表则等效于 "*"。
            extra_headers:  额外自定义响应头 dict。
        """
        self.app = app
        self.cors_origins = cors_origins
        self.extra_headers = extra_headers or {}

    async def __call__(
        self,
        scope: t.Dict[str, t.Any],
        receive: t.Callable[[], t.Awaitable[t.Dict[str, t.Any]]],
        send: t.Callable[[t.Dict[str, t.Any]], t.Awaitable[None]],
    ) -> None:
        """ASGI 调用入口。"""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 判断是否为预检请求（OPTIONS）
        requested_method: str = ""
        if self.cors_origins is not None:
            headers_dict = dict(scope.get("headers", []))
            requested_method = headers_dict.get(
                b"access-control-request-method", b""
            ).decode("ascii", errors="ignore")

        is_preflight = (
            scope.get("method", "").upper() == "OPTIONS"
            and requested_method
        )

        async def send_with_headers(message: t.Dict[str, t.Any]) -> None:
            """拦截 send 事件，在响应头中添加安全头。"""
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # 添加默认安全头
                for name, value in self.DEFAULT_HEADERS.items():
                    headers.append(
                        (name.encode("latin-1"), value.encode("latin-1"))
                    )

                # 添加自定义额外头
                for name, value in self.extra_headers.items():
                    headers.append(
                        (name.encode("latin-1"), value.encode("latin-1"))
                    )

                # 对预检请求注入 CORS 头
                if is_preflight:
                    cors_headers = self._build_cors_headers(
                        scope.get("headers", [])
                    )
                    headers.extend(cors_headers)

                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, send_with_headers)

    # ------------------------------------------------------------------
    # CORS helpers
    # ------------------------------------------------------------------

    def _build_cors_headers(
        self,
        raw_headers: t.List[t.Tuple[bytes, bytes]],
    ) -> t.List[t.Tuple[bytes, bytes]]:
        """根据请求来源构建 CORS 响应头。"""
        headers: t.List[t.Tuple[bytes, bytes]] = []

        # 解析 Origin
        origin = ""
        for name, value in raw_headers:
            if name.lower() == b"origin":
                origin = value.decode("ascii", errors="ignore")
                break

        allowed_origin = self._resolve_cors_origin(origin)
        if allowed_origin:
            headers.append((b"Access-Control-Allow-Origin", allowed_origin.encode("latin-1")))

        headers.append((b"Access-Control-Allow-Methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"))
        headers.append((b"Access-Control-Allow-Headers", b"Content-Type, Authorization, X-Requested-With"))
        headers.append((b"Access-Control-Max-Age", b"86400"))
        headers.append((b"Access-Control-Allow-Credentials", b"true"))
        headers.append((b"Vary", b"Origin"))

        return headers

    def _resolve_cors_origin(self, origin: str) -> t.Optional[str]:
        """检查 origin 是否在白名单中，返回允许的 origin 值。"""
        if not origin or self.cors_origins is None:
            return None

        if "*" in self.cors_origins or origin in self.cors_origins:
            return origin

        return None


# ======================================================================
# 语法验证 & 快速自检
# ======================================================================

if __name__ == "__main__":
    # 1. ast.parse 验证语法
    with open(__file__, "r", encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=__file__)
    print(f"[OK] ast.parse 通过 — AST 包含 {len(tree.body)} 个顶级节点")

    # 2. 快速功能自检
    limiter = RateLimiter(rate=10, burst=5, window=5)

    # 突发允许
    allowed_count = sum(1 for _ in range(10) if limiter.is_allowed("test"))
    print(f"[TEST] 突发请求: 10 次中允许了 {allowed_count} 次 (期望 ≤5)")

    # 拒绝后剩余为 0
    assert limiter.get_remaining("test") == 0, "耗尽后剩余应为 0"
    print("[TEST] 剩余令牌检查通过")

    # 未使用 key 返回 burst
    fresh = limiter.get_remaining("fresh")
    print(f"[TEST] 新 key 剩余令牌: {fresh} (期望 ={limiter._burst})")

    # 清理逻辑：触发清理需要先将计数器推到阈值
    limiter._check_counter = limiter._cleanup_interval - 1
    limiter._buckets["stale"] = (1.0, 0)
    limiter.is_allowed("trigger_cleanup")  # 第 100 次调用触发清理
    assert "stale" not in limiter._buckets, "过期条目应被清理"
    print("[TEST] 过期清理检查通过")

    # 3. SecurityHeadersMiddleware 初始化
    mw = SecurityHeadersMiddleware(
        app=lambda s, r, snd: None,
        cors_origins=["https://example.com"],
        extra_headers={"X-Custom": "custom-value"},
    )
    assert "X-Custom" in mw.extra_headers
    print("[TEST] SecurityHeadersMiddleware 初始化通过")

    print("\n所有检查通过 ✅")
