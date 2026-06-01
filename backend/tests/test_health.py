"""健康检查 / 基础路由测试

验证服务是否正常启动、路由是否可访问。
"""

from fastapi.testclient import TestClient


class TestHealth:
    """服务健康状态检查"""

    def test_root_endpoint(self, client: TestClient):
        """GET / → 返回服务基本信息"""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "链客宝 API"
        assert data["status"] == "running"

    def test_health_endpoint(self, client: TestClient):
        """GET /health → 深度健康检查"""
        resp = client.get("/health")
        # 可能 200 (healthy) 或 503 (degraded)，但必须能正常响应
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")
        assert "database" in data
        assert "payment" in data
        assert "system" in data

    def test_health_live(self, client: TestClient):
        """GET /health/live → 存活检查"""
        resp = client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    def test_health_ready(self, client: TestClient):
        """GET /health/ready → 就绪检查"""
        resp = client.get("/health/ready")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data

    def test_products_list(self, client: TestClient):
        """GET /api/products → 产品列表"""
        resp = client.get("/api/products")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        # 产品列表应当包含 data 字段（可能是列表或分页对象）
        assert "data" in data

    def test_banners_endpoint(self, client: TestClient):
        """GET /banners → Banner列表（无需认证）"""
        resp = client.get("/banners")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)
