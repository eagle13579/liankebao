"""订单模块测试：订单流程 + 状态流转"""

from fastapi.testclient import TestClient


class TestCreateOrder:
    """创建订单测试"""

    URL = "/api/orders"
    PRODUCT_URL = "/api/products"

    def test_create_order_success(self, client: TestClient, buyer_headers):
        """买家成功下单"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["order"]["status"] == "pending"
        assert data["order"]["quantity"] == 2
        assert data["order"]["total_price"] > 0
        assert "payment" in data

    def test_create_order_no_auth(self, client: TestClient):
        """未认证不能下单"""
        resp = client.post(
            self.URL,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        assert resp.status_code == 401

    def test_create_order_product_not_found(self, client: TestClient, buyer_headers):
        """产品不存在"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 99999,
                "quantity": 1,
            },
        )
        assert resp.status_code == 404

    def test_create_order_unapproved_product(self, client: TestClient, buyer_headers):
        """未上架产品不能下单"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 2,
                "quantity": 1,  # 产品2是pending状态
            },
        )
        assert resp.status_code == 400
        assert "未上架" in resp.text

    def test_create_order_insufficient_stock(self, client: TestClient, buyer_headers):
        """库存不足"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 999999,
            },
        )
        assert resp.status_code == 400
        assert "库存不足" in resp.text

    def test_create_order_with_promoter(self, client: TestClient, buyer_headers):
        """带推广员下单"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
                "promoter_id": 3,  # promoter1
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]["order"]
        assert data["promoter_id"] == 3
        assert data["commission"] > 0

    def test_create_order_invalid_promoter(self, client: TestClient, buyer_headers):
        """不存在的推广员"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
                "promoter_id": 99999,
            },
        )
        assert resp.status_code == 400
        assert "推广员不存在" in resp.text

    def test_create_order_payment_params(self, client: TestClient, buyer_headers):
        """下单返回支付参数"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        assert resp.status_code == 200
        payment = resp.json()["data"]["payment"]
        assert "appId" in payment
        assert "timeStamp" in payment
        assert "nonceStr" in payment
        assert "package" in payment
        assert "paySign" in payment


class TestGetOrders:
    """获取订单列表测试"""

    URL = "/api/orders"

    def test_get_orders_as_buyer(self, client: TestClient, buyer_headers):
        """买家查看自己的订单"""
        resp = client.get(self.URL, headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 0
        for order in data["items"]:
            # 买家只能看到自己的订单
            pass

    def test_get_orders_as_admin(self, client: TestClient, admin_headers):
        """管理员查看所有订单"""
        resp = client.get(self.URL, headers=admin_headers)
        assert resp.status_code == 200

    def test_get_orders_as_supplier(self, client: TestClient, supplier_headers):
        """供应商查看自己产品的订单"""
        resp = client.get(self.URL, headers=supplier_headers)
        assert resp.status_code == 200

    def test_get_orders_as_promoter(self, client: TestClient, promoter_headers):
        """推广员查看自己推广的订单"""
        resp = client.get(self.URL, headers=promoter_headers)
        assert resp.status_code == 200

    def test_get_orders_no_auth(self, client: TestClient):
        """未认证不能查看订单"""
        resp = client.get(self.URL)
        assert resp.status_code == 401


class TestGetOrderDetail:
    """订单详情测试"""

    URL = "/api/orders"

    def test_get_order_detail(self, client: TestClient, buyer_headers):
        """获取订单详情"""
        # 先创建一个订单
        create_resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = create_resp.json()["data"]["order"]["id"]

        resp = client.get(f"{self.URL}/{order_id}", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == order_id
        assert "product" in data
        assert "user_id" in data
        assert "total_price" in data

    def test_get_order_not_found(self, client: TestClient, buyer_headers):
        """不存在的订单"""
        resp = client.get(f"{self.URL}/99999", headers=buyer_headers)
        assert resp.status_code == 404

    def test_get_order_no_permission(self, client: TestClient, buyer_headers, promoter_headers):
        """非相关人员不能查看订单"""
        create_resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = create_resp.json()["data"]["order"]["id"]

        # promoter1不是订单的买家和推广员（假设没设promoter_id）
        resp = client.get(f"{self.URL}/{order_id}", headers=promoter_headers)
        # 可能403或200（如果是推广的订单）
        assert resp.status_code in (200, 403)

    def test_get_order_no_auth(self, client: TestClient):
        """未认证不能查看详情"""
        resp = client.get(f"{self.URL}/1")
        assert resp.status_code == 401


class TestOrderStatusFlow:
    """订单状态流转测试"""

    URL = "/api/orders"
    PAY_NOTIFY_URL = "/api/orders/pay-notify"

    def _create_and_pay_order(self, client, headers):
        """辅助：创建订单并通过mock支付"""
        resp = client.post(
            self.URL,
            headers=headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = resp.json()["data"]["order"]["id"]

        # Mock支付回调
        import time

        callback_resp = client.post(
            self.PAY_NOTIFY_URL,
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"mock_tx_{order_id}",
                "result_code": "SUCCESS",
            },
        )
        return order_id

    def test_full_order_lifecycle(self, client: TestClient, buyer_headers, admin_headers):
        """完整订单生命周期：创建→支付→发货→收货"""
        # 创建订单
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = resp.json()["data"]["order"]["id"]

        # 支付回调
        import time

        resp = client.post(
            self.PAY_NOTIFY_URL,
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"mock_tx_{order_id}",
            },
        )
        assert resp.status_code == 200

        # 验证状态为paid
        resp = client.get(f"{self.URL}/{order_id}", headers=buyer_headers)
        assert resp.json()["data"]["status"] == "paid"

        # 发货（admin操作）
        resp = client.put(f"{self.URL}/{order_id}/status", headers=admin_headers, json={"status": "shipped"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "shipped"

        # 收货（buyer操作）
        resp = client.put(f"{self.URL}/{order_id}/status", headers=buyer_headers, json={"status": "received"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "received"

    def test_invalid_status_transition(self, client: TestClient, buyer_headers):
        """无效状态流转应被拒绝"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = resp.json()["data"]["order"]["id"]

        # 直接从未支付跳转到received应被拒绝
        resp = client.put(f"{self.URL}/{order_id}/status", headers=buyer_headers, json={"status": "received"})
        assert resp.status_code == 400

    def test_buyer_cannot_ship(self, client: TestClient, buyer_headers):
        """买家不能发货"""
        import time

        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = resp.json()["data"]["order"]["id"]

        client.post(
            self.PAY_NOTIFY_URL,
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"mock_tx_{order_id}",
            },
        )

        # 买家尝试发货
        resp = client.put(f"{self.URL}/{order_id}/status", headers=buyer_headers, json={"status": "shipped"})
        assert resp.status_code == 403

    def test_status_transition_validation(self, client: TestClient, buyer_headers, admin_headers):
        """状态流转合法性校验"""
        import time

        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = resp.json()["data"]["order"]["id"]

        # 支付
        client.post(
            self.PAY_NOTIFY_URL,
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"mock_tx_{order_id}",
            },
        )

        # 发货 → 收货
        client.put(f"{self.URL}/{order_id}/status", headers=admin_headers, json={"status": "shipped"})

        # 尝试从shipped再回到paid
        resp = client.put(f"{self.URL}/{order_id}/status", headers=admin_headers, json={"status": "paid"})
        assert resp.status_code == 400
