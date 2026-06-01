"""数据洞察全面测试 —— 仪表盘接口"""
import pytest
from fastapi.testclient import TestClient


class TestInsightsDashboard:
    """数据洞察仪表盘测试"""

    def test_dashboard(self, client: TestClient, buyer_headers: dict):
        """GET /api/insights/dashboard — 买家视角"""
        resp = client.get("/api/insights/dashboard", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        dashboard = data["data"]
        assert "my_products" in dashboard
        assert "my_orders" in dashboard
        assert "monthly_sales" in dashboard
        assert "promotion_earnings" in dashboard

    def test_dashboard_no_auth(self, client: TestClient):
        """GET /api/insights/dashboard — 无认证"""
        resp = client.get("/api/insights/dashboard")
        assert resp.status_code == 401

    def test_dashboard_promoter(self, client: TestClient, promoter_headers: dict):
        """GET /api/insights/dashboard — 推广员视角"""
        resp = client.get("/api/insights/dashboard", headers=promoter_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "promotion_earnings" in data

    def test_dashboard_supplier(self, client: TestClient, supplier_headers: dict):
        """GET /api/insights/dashboard — 供应商视角"""
        resp = client.get("/api/insights/dashboard", headers=supplier_headers)
        assert resp.status_code == 200
        assert "my_products" in resp.json()["data"]

    def test_dashboard_admin(self, client: TestClient, admin_headers: dict):
        """GET /api/insights/dashboard — 管理员视角"""
        resp = client.get("/api/insights/dashboard", headers=admin_headers)
        assert resp.status_code == 200

    def test_dashboard_v1(self, client: TestClient, buyer_headers: dict):
        """GET /api/v1/insights/dashboard"""
        resp = client.get("/api/v1/insights/dashboard", headers=buyer_headers)
        assert resp.status_code == 200
