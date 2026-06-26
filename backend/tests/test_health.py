"""
健康检查 / 基础路由测试
（已适配 chainke-full）

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
        assert data["service"] == "链客宝AI API"
        assert data["status"] == "running"

    def test_health_endpoint(self, client: TestClient):
        """GET /health → 健康检查"""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_live(self, client: TestClient):
        """GET /health/live → 存活检查"""
        resp = client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    def test_health_ready(self, client: TestClient):
        """GET /health/ready → 就绪检查"""
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
