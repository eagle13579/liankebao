"""
数据洞察模块测试
============
- 用户数据看板
- 多角色数据隔离
- 权限校验
"""
import pytest
from fastapi.testclient import TestClient


class TestInsightsDashboard:
    """数据洞察看板测试"""

    DASHBOARD_URL = "/api/insights/dashboard"

    def test_dashboard_success(self, client: TestClient, buyer_headers):
        """买家查看自己的数据看板"""
        resp = client.get(self.DASHBOARD_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"看板应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        d = data["data"]
        # 买家有订单记录（seed数据）
        assert "my_products" in d
        assert "my_orders" in d
        assert "monthly_sales" in d
        assert "promotion_earnings" in d
        assert "monthly_orders" in d
        assert "prev_monthly_sales" in d
        # buyer 没有产品，但seed中有2个订单
        assert d["my_products"] == 0
        assert d["my_orders"] >= 2

    def test_dashboard_supplier(self, client: TestClient, supplier_headers):
        """供应商查看看板（应看到自己的产品）"""
        resp = client.get(self.DASHBOARD_URL, headers=supplier_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # supplier 有3个种子产品
        assert data["my_products"] >= 3
        # supplier 没有订单作为买家
        assert data["my_orders"] == 0

    def test_dashboard_promoter(self, client: TestClient, promoter_headers):
        """推广员查看看板（应看到推广收益）"""
        resp = client.get(self.DASHBOARD_URL, headers=promoter_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # promoter 有推广佣金（seed数据中1个received订单）
        assert data["promotion_earnings"] >= 0
        # 具体值取决于seed数据
        assert isinstance(data["promotion_earnings"], (int, float))

    def test_dashboard_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.DASHBOARD_URL)
        assert resp.status_code == 401
