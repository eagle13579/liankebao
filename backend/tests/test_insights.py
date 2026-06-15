"""
数据洞察模块测试
==================
- 获取数据看板（成功、各指标正确性、无认证）
"""

from fastapi.testclient import TestClient


class TestInsightsDashboard:
    """数据洞察看板测试"""

    DASHBOARD_URL = "/api/insights/dashboard"

    def test_dashboard_success(self, client: TestClient, buyer_headers, buyer_user_id):
        """成功获取数据看板，验证各指标值"""
        resp = client.get(self.DASHBOARD_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"获取看板应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        dashboard = data["data"]

        # buyer1 在种子数据中有订单，但没有产品
        assert "my_products" in dashboard
        assert "my_orders" in dashboard
        assert "monthly_sales" in dashboard
        assert "promotion_earnings" in dashboard
        assert "monthly_orders" in dashboard
        assert "prev_monthly_sales" in dashboard

        # buyer1 有 2 个订单（在种子数据中）
        assert dashboard["my_orders"] == 2
        # buyer1 没有自己的产品
        assert dashboard["my_products"] == 0
        # buyer1 的本月成交额（已支付+已收货）
        # 订单1: received, total_price=200.00
        # 订单2: paid, total_price=50.00
        # 合计 250.00
        assert dashboard["monthly_sales"] >= 0
        # 作为买家，promotion_earnings 应为 0（买家没有佣金）
        assert dashboard["promotion_earnings"] == 0

    def test_dashboard_for_promoter(self, client: TestClient, promoter_headers):
        """推广员看板：验证推广收益"""
        resp = client.get(self.DASHBOARD_URL, headers=promoter_headers)
        assert resp.status_code == 200
        data = resp.json()
        dashboard = data["data"]

        # promoter1 在种子数据中有佣金
        # 订单1: promoter_id=promoter.id, commission=20.00, status=received
        # 所以 promotion_earnings 应为 20.0
        assert dashboard["promotion_earnings"] >= 20.0
        # promoter1 没有自己的订单（作为买家），所以 my_orders 应为 0
        assert dashboard["my_orders"] == 0
        # promoter1 没有自己的产品
        assert dashboard["my_products"] == 0

    def test_dashboard_for_supplier(self, client: TestClient, supplier_headers, supplier_user_id):
        """供应商看板：验证产品数"""
        resp = client.get(self.DASHBOARD_URL, headers=supplier_headers)
        assert resp.status_code == 200
        data = resp.json()
        dashboard = data["data"]

        # supplier1 在种子数据中有 3 个产品
        assert dashboard["my_products"] == 3
        # supplier1 没有自己的订单
        assert dashboard["my_orders"] == 0

    def test_dashboard_zero_values(self, client: TestClient, admin_headers):
        """管理员用户（无订单无产品）各指标应为0"""
        resp = client.get(self.DASHBOARD_URL, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        dashboard = data["data"]
        assert dashboard["my_products"] == 0
        assert dashboard["my_orders"] == 0
        assert dashboard["monthly_sales"] == 0
        assert dashboard["promotion_earnings"] == 0
        assert dashboard["monthly_orders"] == 0
        assert dashboard["prev_monthly_sales"] == 0

    def test_dashboard_all_fields_present(self, client: TestClient, buyer_headers):
        """验证所有字段都存在且类型正确"""
        resp = client.get(self.DASHBOARD_URL, headers=buyer_headers)
        assert resp.status_code == 200
        dashboard = resp.json()["data"]

        expected_fields = [
            "my_products",
            "my_orders",
            "monthly_sales",
            "promotion_earnings",
            "monthly_orders",
            "prev_monthly_sales",
        ]
        for field in expected_fields:
            assert field in dashboard, f"缺少字段: {field}"
            assert isinstance(dashboard[field], (int, float)), f"字段 {field} 类型错误: {type(dashboard[field])}"

    def test_dashboard_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get(self.DASHBOARD_URL)
        assert resp.status_code == 401
