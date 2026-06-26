"""
订单模块测试：订单流程
（已适配 chainke-full）

chainke-full 订单路由：
  POST   /api/orders/               — 创建订单
  GET    /api/orders/               — 订单列表
  GET    /api/orders/{id}           — 订单详情
"""

from fastapi.testclient import TestClient


class TestCreateOrder:
    """创建订单测试"""

    URL = "/api/orders"
    PRODUCT_URL = "/api/products"

    def test_create_order_no_auth(self, client: TestClient):
        """未认证不能下单"""
        resp = client.post(
            self.URL,
            json={"product_id": 1, "quantity": 1},
        )
        assert resp.status_code == 401

    def test_get_orders_no_auth(self, client: TestClient):
        """未认证不能查看订单"""
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_get_orders_with_auth(self, client: TestClient, admin_headers):
        """已认证可查看订单列表"""
        resp = client.get(self.URL, headers=admin_headers)
        assert resp.status_code in (200, 404)
