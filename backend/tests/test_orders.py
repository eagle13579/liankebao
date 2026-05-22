"""
订单模块测试
============
- 创建订单
- 订单状态流转（paid → shipped → received → refunded）
"""
import pytest
from fastapi.testclient import TestClient


class TestCreateOrder:
    """创建订单测试"""

    CREATE_URL = "/api/orders"

    def test_create_order_success(self, client: TestClient, buyer_headers):
        """买家成功创建订单"""
        # 获取第一个 approved 产品的 ID
        list_resp = client.get("/api/products")
        products = list_resp.json()["data"]["items"]
        target_product = next(p for p in products if p["status"] == "approved")
        product_id = target_product["id"]

        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={
                "product_id": product_id,
                "quantity": 1,
            },
        )
        assert resp.status_code == 200, f"创建订单应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "下单成功"

        order = data["data"]["order"]
        assert order["product_id"] == product_id
        assert order["quantity"] == 1
        assert order["status"] == "pending"
        assert order["total_price"] == target_product["price"]
        assert "payment" in data["data"]

    def test_create_order_with_promoter(self, client: TestClient, buyer_headers):
        """创建订单时指定推广员"""
        list_resp = client.get("/api/products")
        products = list_resp.json()["data"]["items"]
        target_product = next(p for p in products if p["status"] == "approved")
        product_id = target_product["id"]

        # 获取推广员 ID
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "promoter1", "password": "Test1234"},
        )
        promoter_user = login_resp.json()["data"]["user"]
        promoter_id = promoter_user["id"]

        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={
                "product_id": product_id,
                "quantity": 2,
                "promoter_id": promoter_id,
            },
        )
        assert resp.status_code == 200, f"带推广员创建订单应成功: {resp.text}"
        data = resp.json()
        order = data["data"]["order"]
        assert order["promoter_id"] == promoter_id
        # 佣金 = earn_per_share * quantity * 0.5
        expected_commission = target_product["earn_per_share"] * 2 * 0.5
        assert order["commission"] == expected_commission, f"佣金应为 {expected_commission}"

    def test_create_order_unauthenticated(self, client: TestClient):
        """未认证用户创建订单应返回 401"""
        resp = client.post(
            self.CREATE_URL,
            json={"product_id": 1, "quantity": 1},
        )
        assert resp.status_code == 401

    def test_create_order_nonexistent_product(self, client: TestClient, buyer_headers):
        """不存在的产品应返回 404"""
        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={"product_id": 99999, "quantity": 1},
        )
        assert resp.status_code == 404

    def test_create_order_insufficient_stock(self, client: TestClient, buyer_headers):
        """库存不足应返回 400"""
        list_resp = client.get("/api/products")
        products = list_resp.json()["data"]["items"]
        target_product = next(p for p in products if p["status"] == "approved")
        product_id = target_product["id"]

        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={
                "product_id": product_id,
                "quantity": 99999,  # 远超库存
            },
        )
        assert resp.status_code == 400, "库存不足应被拒绝"
        assert "库存不足" in resp.text


class TestOrderStatusFlow:
    """订单状态流转测试"""

    def _create_paid_order(self, client: TestClient, buyer_headers) -> tuple:
        """辅助：创建一个已支付的订单（模拟创建后直接改为 paid）"""
        list_resp = client.get("/api/products")
        products = list_resp.json()["data"]["items"]
        target_product = next(p for p in products if p["status"] == "approved")

        create_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={"product_id": target_product["id"], "quantity": 1},
        )
        order = create_resp.json()["data"]["order"]
        order_id = order["id"]

        # 直接通过数据库将状态改为 paid
        from tests.conftest import TestSessionLocal
        from app.models import Order
        db = TestSessionLocal()
        try:
            db_order = db.query(Order).filter(Order.id == order_id).first()
            db_order.status = "paid"
            db_order.wx_transaction_id = f"mock_tx_{order_id}"
            db.commit()
        finally:
            db.close()

        return order_id, target_product["id"]

    def test_order_status_paid_to_shipped(self, client: TestClient, buyer_headers, supplier_headers):
        """订单状态：paid → shipped（产品方发货）"""
        order_id, _ = self._create_paid_order(client, buyer_headers)

        # 产品方发货
        resp = client.put(
            f"/api/orders/{order_id}/status",
            headers=supplier_headers,
            json={"status": "shipped"},
        )
        assert resp.status_code == 200, f"发货应成功: {resp.text}"
        assert "shipped" in resp.text or "已变更" in resp.text

    def test_order_status_shipped_to_received(self, client: TestClient, buyer_headers, supplier_headers):
        """订单状态：paid → shipped → received（买家确认收货）"""
        order_id, _ = self._create_paid_order(client, buyer_headers)

        # 产品方发货
        client.put(
            f"/api/orders/{order_id}/status",
            headers=supplier_headers,
            json={"status": "shipped"},
        )
        # 买家确认收货
        resp = client.put(
            f"/api/orders/{order_id}/status",
            headers=buyer_headers,
            json={"status": "received"},
        )
        assert resp.status_code == 200, f"确认收货应成功: {resp.text}"
        assert "received" in resp.text or "已变更" in resp.text

    def test_order_status_refund(self, client: TestClient, buyer_headers):
        """订单状态：paid → refunded（买家申请退款）"""
        order_id, _ = self._create_paid_order(client, buyer_headers)

        # 买家申请退款
        resp = client.put(
            f"/api/orders/{order_id}/status",
            headers=buyer_headers,
            json={"status": "refunded"},
        )
        assert resp.status_code == 200, f"退款应成功: {resp.text}"
        assert "refunded" in resp.text or "已变更" in resp.text

    def test_order_status_invalid_transition(self, client: TestClient, buyer_headers, supplier_headers):
        """非法状态流转应被拒绝（如 paid → received 跳过 shipped）"""
        order_id, _ = self._create_paid_order(client, buyer_headers)

        # 买家尝试从 paid 直接到 received（不合规）
        resp = client.put(
            f"/api/orders/{order_id}/status",
            headers=buyer_headers,
            json={"status": "received"},
        )
        # paid 允许的流转: shipped, refunded
        # received 不在 allowed 中
        assert resp.status_code in (400, 403), f"非法流转应被拒绝: {resp.text}"

    def test_order_status_unauthorized(self, client: TestClient, buyer_headers, promoter_headers):
        """普通推广员无权变更订单状态"""
        order_id, _ = self._create_paid_order(client, buyer_headers)

        resp = client.put(
            f"/api/orders/{order_id}/status",
            headers=promoter_headers,
            json={"status": "shipped"},
        )
        assert resp.status_code == 403, "推广员无权变更订单状态"
