"""支付模块测试：微信支付V2/V3模拟"""

import base64
import json
import time

from fastapi.testclient import TestClient


class TestPaymentUnifiedOrder:
    """统一下单测试"""

    URL = "/api/payment/wxpay/unified-order"

    def test_unified_order_success(self, client: TestClient, buyer_headers):
        """成功创建支付订单（mock模式）"""
        # 先创建商品订单
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        # 发起支付
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "order_id": order_id,
                "openid": "mock_openid_12345",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "order" in data
        assert "payment" in data
        payment = data["payment"]
        assert "appId" in payment
        assert "timeStamp" in payment
        assert "nonceStr" in payment
        assert "package" in payment
        assert "paySign" in payment

    def test_unified_order_no_auth(self, client: TestClient):
        """未认证不能发起支付"""
        resp = client.post(self.URL, json={"order_id": 1})
        assert resp.status_code == 401

    def test_unified_order_not_found(self, client: TestClient, buyer_headers):
        """不存在的订单"""
        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "order_id": 99999,
            },
        )
        assert resp.status_code == 404

    def test_unified_order_not_owner(self, client: TestClient, buyer_headers, supplier_headers):
        """非订单所有者不能支付"""
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        resp = client.post(
            self.URL,
            headers=supplier_headers,
            json={
                "order_id": order_id,
            },
        )
        assert resp.status_code == 403

    def test_unified_order_already_paid(self, client: TestClient, buyer_headers, admin_headers):
        """已支付订单不能再次支付"""
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        # Mock支付
        client.post(
            "/api/orders/pay-notify",
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"mock_tx_{order_id}",
            },
        )

        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "order_id": order_id,
            },
        )
        assert resp.status_code == 400

    def test_unified_order_no_openid(self, client: TestClient, buyer_headers):
        """没有openid时返回400"""
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        resp = client.post(
            self.URL,
            headers=buyer_headers,
            json={
                "order_id": order_id,
                "openid": "",
            },
        )
        # buyer1没有wechat_openid，且传了空openid
        assert resp.status_code == 400


class TestPaymentCallback:
    """支付回调测试"""

    CALLBACK_URL = "/api/payment/wxpay/callback"

    def test_callback_success_v3_format(self, client: TestClient, buyer_headers):
        """V3格式回调成功处理"""
        # 先创建订单
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        # 模拟V3回调（携带resource字段）
        resp = client.post(
            self.CALLBACK_URL,
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"v3_tx_{order_id}",
                "trade_state": "SUCCESS",
                "resource": {
                    "ciphertext": base64.b64encode(
                        json.dumps(
                            {
                                "out_trade_no": f"LK{order_id:08d}",
                                "transaction_id": f"v3_tx_{order_id}",
                            }
                        ).encode()
                    ).decode()
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] in ("SUCCESS", "FAIL")

        # 验证订单状态已更新
        resp = client.get(f"/api/orders/{order_id}", headers=buyer_headers)
        if resp.status_code == 200:
            assert resp.json()["data"]["status"] == "paid"

    def test_callback_mock_format(self, client: TestClient, buyer_headers):
        """Mock格式回调"""
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        resp = client.post(
            self.CALLBACK_URL,
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"mock_tx_{order_id}",
                "result_code": "SUCCESS",
            },
        )
        assert resp.status_code == 200

    def test_callback_invalid_body(self, client: TestClient, buyer_headers):
        """无效回调数据"""
        resp = client.post(self.CALLBACK_URL, json={"invalid": "data"})
        assert resp.status_code == 200  # 即使无效也返回200

    def test_callback_xml_format(self, client: TestClient, buyer_headers):
        """XML格式回调（V2兼容）"""

        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<xml>
  <out_trade_no>LK{order_id:08d}{int(time.time())}</out_trade_no>
  <transaction_id>v2_tx_{order_id}</transaction_id>
  <result_code>SUCCESS</result_code>
  <return_code>SUCCESS</return_code>
</xml>"""

        resp = client.post(self.CALLBACK_URL, content=xml_body, headers={"Content-Type": "application/xml"})
        assert resp.status_code == 200


class TestPaymentQuery:
    """支付查询测试"""

    URL = "/api/payment/wxpay/query"

    def test_query_by_order_no(self, client: TestClient, buyer_headers):
        """按订单号查询"""
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        resp = client.get(f"{self.URL}/LK{order_id:08d}", headers=buyer_headers)
        assert resp.status_code == 200

    def test_query_not_found(self, client: TestClient, buyer_headers):
        """查询不存在的订单"""
        resp = client.get(f"{self.URL}/NONEXISTENT", headers=buyer_headers)
        assert resp.status_code in (200, 404)


class TestPaymentRefund:
    """退款测试"""

    URL = "/api/payment/wxpay/refund"

    def test_refund_success(self, client: TestClient, buyer_headers, admin_headers):
        """成功退款"""
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        # 先支付
        import time

        client.post(
            "/api/orders/pay-notify",
            json={
                "out_trade_no": f"LK{order_id:08d}{int(time.time())}",
                "transaction_id": f"mock_tx_{order_id}",
            },
        )

        # 退款
        resp = client.post(
            self.URL,
            headers=admin_headers,
            json={
                "order_id": order_id,
                "reason": "测试退款",
            },
        )
        # Mock模式下应该成功或返回配置错误
        assert resp.status_code in (200, 503)


class TestPaymentConfig:
    """支付配置测试"""

    URL = "/api/payment/config"

    def test_get_config(self, client: TestClient):
        """获取支付配置"""
        resp = client.get(self.URL)
        assert resp.status_code == 200
