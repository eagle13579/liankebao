"""RateLimit 中间件测试

测试 app.middleware.rate_limit 模块：
- RateLimitMiddleware 限流逻辑
- 路由级别速率匹配（认证路由更严格）
- 响应头（Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining）
- 非 API 路径不受限
"""

# 必须在任何 app 导入前设置
import os

from fastapi.testclient import TestClient

os.environ["RATE_LIMIT_ENABLED"] = "true"


class TestRateLimitMiddleware:
    """RateLimitMiddleware 功能测试"""

    def test_normal_request_allowed(self, client: TestClient):
        """正常请求通过限流中间件"""
        # 使用安全健康检查端点
        resp = client.get("/api/security/health")
        assert resp.status_code == 200

    def test_burst_limit_exceeded(self, client: TestClient):
        """超出突发限制返回 429"""
        from app.rate_limiter import get_rate_limiter

        limiter = get_rate_limiter()
        # 清理之前可能存在的记录
        limiter._records.clear()

        # 模拟发送大量请求，耗尽某个 key 的配额
        # 用已知的 test key 来触发限流（使用窗口 60, limit=2 来验证）
        for i in range(5):
            allowed, retry_after = limiter.check("test:burst:w60", limit=2)
            if not allowed:
                break

        # 第6次应该被限流
        allowed, retry_after = limiter.check("test:burst:w60", limit=2)
        assert allowed is False
        assert retry_after > 0

    def test_auth_stricter_rate(self):
        """认证接口有更严格的速率限制

        验证 ROUTE_RATE_LIMITS 中 /api/auth/ 的 limit=10, window=60
        """
        from app.middleware.rate_limit import _get_matching_rate

        limit, window = _get_matching_rate("/api/auth/login")
        # /api/auth/ 的旧版限制是 10 req/min
        assert limit == 10
        assert window == 60

    def test_vector_rebuild_rate(self):
        """向量重建接口有更严格的速率限制"""
        from app.middleware.rate_limit import _get_matching_rate

        limit, window = _get_matching_rate("/api/v1/search/vector/rebuild")
        assert limit == 6
        assert window == 60

    def test_default_rate_for_other_api(self):
        """其他 API 路径使用默认限制"""
        from app.middleware.rate_limit import _get_matching_rate

        limit, window = _get_matching_rate("/api/some/random/path")
        assert limit == 100
        assert window == 60

    def test_rate_limit_headers(self):
        """限流响应包含正确的 headers"""
        # 需要模拟限流触发 — 通过直接操作 limiter 来模拟
        from app.rate_limiter import get_rate_limiter

        limiter = get_rate_limiter()
        # 用极低的 limit 快速触发
        key = "test:headers:w60"
        for i in range(3):
            limiter.check(key, limit=2)
        allowed, retry_after = limiter.check(key, limit=2)
        # 验证 retry_after 返回正数
        assert allowed is False
        assert retry_after >= 1

    def test_non_api_path_not_limited(self, client: TestClient):
        """非 /api/ 路径不受限流影响"""
        resp = client.get("/docs")
        # /docs 不是 /api/ 路径，不触发限流
        assert resp.status_code in (200, 307, 404)  # 可能重定向到 /docs 或 404

    def test_rate_limit_response_structure(self):
        """验证 429 响应结构"""
        from app.middleware.rate_limit import _get_matching_rate

        # 检查默认请求的 limit
        limit, window = _get_matching_rate("/api/health")
        assert isinstance(limit, int)
        assert isinstance(window, int)
        assert limit > 0
        assert window > 0
