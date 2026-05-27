"""
支付模块测试 — 增强版(带parametrize)
=====================================
- 微信统一下单（mock 模式）
- 微信支付回调（V3 模拟、V2 XML 模拟、mock JSON）
- 支付宝统一下单（mock 模式）
- 支付配置查询
- 幂等性保护（重复回调不重复处理）
- 回调参数化测试
- 订单归属权校验
- 退款（mock 模式）
- 权限边界测试
"""

import time

import pytest
from fastapi.testclient import TestClient


class TestWxPayUnifiedOrder:
    """微信统一下单测试"""

    UNIFIED_URL = "/api/payment/wxpay/unified-order"

    def _get_approved_product_id(self, client: TestClient) -> int:
        """辅助：获取第一个 approved 产品的 ID"""
        resp = client.get("/api/products")
        products = resp.json()["data"]["items"]
        target = next(p for p in products if p["status"] == "approved")
        return target["id"]

    def _create_pending_order(self, client: TestClient, buyer_headers) -> int:
        """辅助：创建一个 pending 状态的订单，返回 order_id"""
        pid = self._get_approved_product_id(client)
        resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={"product_id": pid, "quantity": 1},
        )
        assert resp.status_code == 200
        return resp.json()["data"]["order"]["id"]

    def test_unified_order_success_mock(self, client: TestClient, buyer_headers):
        """微信统一下单成功（mock 模式）"""
        order_id = self._create_pending_order(client, buyer_headers)
        resp = client.post(
            self.UNIFIED_URL,
            headers=buyer_headers,
            json={"order_id": order_id, "openid": "mock_openid_12345"},
        )
        assert resp.status_code == 200, f"统一下单应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["payment"]["_mode"] in ("mock", "real")
        assert "prepay_id" in data["data"]["payment"].get("package", "")

    def test_unified_order_missing_openid(self, client: TestClient, buyer_headers):
        """缺少 openid 应返回 400"""
        order_id = self._create_pending_order(client, buyer_headers)
        resp = client.post(
            self.UNIFIED_URL,
            headers=buyer_headers,
            json={"order_id": order_id},
        )
        assert resp.status_code == 400
        assert "openid" in resp.text.lower()

    def test_unified_order_not_owner(self, client: TestClient, buyer_headers, promoter_headers):
        """非订单归属人下单应返回 403"""
        order_id = self._create_pending_order(client, buyer_headers)
        resp = client.post(
            self.UNIFIED_URL,
            headers=promoter_headers,
            json={"order_id": order_id, "openid": "mock_openid"},
        )
        assert resp.status_code == 403

    def test_unified_order_nonexistent(self, client: TestClient, buyer_headers):
        """不存在的订单返回 404"""
        resp = client.post(
            self.UNIFIED_URL,
            headers=buyer_headers,
            json={"order_id": 99999, "openid": "mock_openid"},
        )
        assert resp.status_code == 404

    def test_unified_order_wrong_status(self, client: TestClient, buyer_headers):
        """已支付的订单不能再次下单"""
        resp = client.post(
            self.UNIFIED_URL,
            headers=buyer_headers,
            json={"order_id": 2, "openid": "mock_openid"},
        )
        assert resp.status_code == 400
        assert "待支付" in resp.text

    def test_unified_order_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.post(
            self.UNIFIED_URL,
            json={"order_id": 1, "openid": "mock_openid"},
        )
        assert resp.status_code == 401


class TestWxPayCallback:
    """微信支付回调测试 — 含parametrize"""

    CALLBACK_URL = "/api/payment/wxpay/callback"

    def _create_pending_order_for_callback(self, client: TestClient, buyer_headers) -> tuple:
        """辅助：创建 order 并返回 (order_id, out_trade_no)"""
        resp = client.get("/api/products")
        products = resp.json()["data"]["items"]
        target = next(p for p in products if p["status"] == "approved")
        resp2 = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={"product_id": target["id"], "quantity": 1},
        )
        order = resp2.json()["data"]["order"]
        order_id = order["id"]
        out_trade_no = f"LK{order_id:08d}{int(time.time())}"
        return order_id, out_trade_no

    # ---- 参数化测试：多种回调格式 ----
    @pytest.mark.parametrize(
        "callback_body,desc",
        [
            ({"result_code": "SUCCESS"}, "仅result_code"),
            ({"result_code": "SUCCESS", "transaction_id": "mock_tx_001"}, "含transaction_id"),
            ({"result_code": "OK"}, "result_code=OK"),
            ({"result_code": "SUCCESS", "openid": "mock_user"}, "额外字段openid"),
            ({"result_code": "SUCCESS", "is_subscribe": "N", "trade_type": "JSAPI"}, "完整V2格式"),
            ({"result_code": "SUCCESS", "bank_type": "CFT", "fee_type": "CNY"}, "银行字段"),
        ],
    )
    def test_callback_parametrize_formats(self, client, buyer_headers, callback_body, desc):
        """参数化测试：多种回调body格式都能成功处理"""
        order_id, out_trade_no = self._create_pending_order_for_callback(client, buyer_headers)
        client.post(
            "/api/payment/wxpay/unified-order",
            headers=buyer_headers,
            json={"order_id": order_id, "openid": "mock_openid"},
        )
        body = {**callback_body, "out_trade_no": out_trade_no}
        resp = client.post(self.CALLBACK_URL, json=body)
        assert resp.status_code == 200, f"[{desc}] 回调应成功: {resp.text}"
        assert resp.json()["code"] == "SUCCESS", f"[{desc}] 应返回SUCCESS"

    @pytest.mark.parametrize(
        "bad_body,desc",
        [
            ({}, "空body"),
            ({"result_code": "FAIL"}, "支付失败"),
            ({"result_code": "PAY_ERROR"}, "异常状态"),
            ({"err_code": "FAIL"}, "错误格式"),
        ],
    )
    def test_callback_parametrize_failures(self, client, buyer_headers, bad_body, desc):
        """参数化测试：各种失败回调"""
        order_id, out_trade_no = self._create_pending_order_for_callback(client, buyer_headers)
        client.post(
            "/api/payment/wxpay/unified-order",
            headers=buyer_headers,
            json={"order_id": order_id, "openid": "mock_openid"},
        )
        body = {**bad_body, "out_trade_no": out_trade_no}
        resp = client.post(self.CALLBACK_URL, json=body)
        # 可能返回FAIL或已处理，但不应500
        assert resp.status_code == 200

    # ---- 幂等性参数化测试 ----
    @pytest.mark.parametrize("repeat_times", [2, 3, 5])
    def test_callback_idempotent_multi_repeat(self, client, buyer_headers, repeat_times):
        """参数化：重复回调多次幂等"""
        order_id, out_trade_no = self._create_pending_order_for_callback(client, buyer_headers)
        client.post(
            "/api/payment/wxpay/unified-order",
            headers=buyer_headers,
            json={"order_id": order_id, "openid": "mock_openid"},
        )

        responses = []
        for i in range(repeat_times):
            resp = client.post(
                self.CALLBACK_URL,
                json={"out_trade_no": out_trade_no, "result_code": "SUCCESS"},
            )
            responses.append(resp)
            assert resp.status_code == 200, f"第{i + 1}次回调应200"

        # 检查后续回调均返回SUCCESS
        for i, r in enumerate(responses[1:]):
            assert r.json()["code"] == "SUCCESS", f"第{i + 2}次回调应幂等"

        # 验证订单状态
        query_resp = client.get(f"/api/orders/{order_id}", headers=buyer_headers)
        assert query_resp.status_code == 200

    # ---- 原有单测保留 ----
    def test_callback_json_mock_success(self, client: TestClient, buyer_headers):
        order_id, out_trade_no = self._create_pending_order_for_callback(client, buyer_headers)
        client.post(
            "/api/payment/wxpay/unified-order",
            headers=buyer_headers,
            json={"order_id": order_id, "openid": "mock_openid"},
        )
        resp = client.post(
            self.CALLBACK_URL,
            json={
                "out_trade_no": out_trade_no,
                "transaction_id": f"mock_tx_{order_id}",
                "result_code": "SUCCESS",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

    def test_callback_v3_signature_headers(self, client: TestClient, buyer_headers):
        order_id, out_trade_no = self._create_pending_order_for_callback(client, buyer_headers)
        resp = client.post(
            self.CALLBACK_URL,
            headers={
                "Wechatpay-Signature": "mock_signature",
                "Wechatpay-Serial": "mock_serial",
                "Wechatpay-Timestamp": str(int(time.time())),
                "Wechatpay-Nonce": "mock_nonce",
            },
            json={
                "out_trade_no": out_trade_no,
                "transaction_id": f"v3_mock_tx_{order_id}",
                "trade_state": "SUCCESS",
            },
        )
        assert resp.status_code == 200

    def test_callback_idempotent(self, client: TestClient, buyer_headers):
        order_id, out_trade_no = self._create_pending_order_for_callback(client, buyer_headers)
        resp1 = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": out_trade_no, "result_code": "SUCCESS"},
        )
        assert resp1.json()["code"] == "SUCCESS"
        resp2 = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": out_trade_no, "result_code": "SUCCESS"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["code"] == "SUCCESS"

    def test_callback_no_out_trade_no(self, client: TestClient):
        resp = client.post(self.CALLBACK_URL, json={"result_code": "SUCCESS"})
        assert resp.status_code == 200
        assert resp.json()["code"] in ("SUCCESS", "FAIL")

    def test_callback_xml_v2_compatible(self, client: TestClient, buyer_headers):
        order_id, out_trade_no = self._create_pending_order_for_callback(client, buyer_headers)
        xml_body = (
            "<xml>"
            f"<out_trade_no>{out_trade_no}</out_trade_no>"
            f"<transaction_id>xml_tx_{order_id}</transaction_id>"
            "<result_code>SUCCESS</result_code>"
            "<return_code>SUCCESS</return_code>"
            "</xml>"
        )
        resp = client.post(
            self.CALLBACK_URL,
            content=xml_body,
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] in ("SUCCESS", "FAIL")

    def test_callback_order_not_pending(self, client: TestClient):
        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": "LK00000002123456789", "result_code": "SUCCESS"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"


class TestWxPayRefund:
    """微信退款测试"""

    REFUND_URL = "/api/payment/wxpay/refund"

    def test_refund_mock_success(self, client: TestClient, buyer_headers):
        resp = client.post(
            self.REFUND_URL,
            headers=buyer_headers,
            json={"order_id": 2, "reason": "测试退款"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "退款" in data["message"]

    def test_refund_not_owner(self, client: TestClient, promoter_headers):
        resp = client.post(
            self.REFUND_URL,
            headers=promoter_headers,
            json={"order_id": 2},
        )
        assert resp.status_code == 403

    def test_refund_nonexistent_order(self, client: TestClient, buyer_headers):
        resp = client.post(
            self.REFUND_URL,
            headers=buyer_headers,
            json={"order_id": 99999},
        )
        assert resp.status_code == 404

    def test_refund_invalid_status(self, client: TestClient, buyer_headers):
        resp = client.post(
            self.REFUND_URL,
            headers=buyer_headers,
            json={"order_id": 1},
        )
        assert resp.status_code == 400

    def test_refund_unauthenticated(self, client: TestClient):
        resp = client.post(
            self.REFUND_URL,
            json={"order_id": 1},
        )
        assert resp.status_code == 401


class TestAliPayUnifiedOrder:
    """支付宝统一下单测试"""

    ALIPAY_URL = "/api/payment/alipay/unified-order"

    def _create_pending_order(self, client: TestClient, buyer_headers) -> int:
        resp = client.get("/api/products")
        products = resp.json()["data"]["items"]
        target = next(p for p in products if p["status"] == "approved")
        resp2 = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={"product_id": target["id"], "quantity": 1},
        )
        return resp2.json()["data"]["order"]["id"]

    def test_alipay_unified_order_mock(self, client: TestClient, buyer_headers):
        order_id = self._create_pending_order(client, buyer_headers)
        resp = client.post(
            self.ALIPAY_URL,
            headers=buyer_headers,
            json={"order_id": order_id, "subject": "测试商品"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["_mode"] == "mock"
        assert "order_string" in data["data"]
        assert "alipay.trade.app.pay" in data["data"]["order_string"]

    def test_alipay_unified_order_not_owner(self, client: TestClient, promoter_headers):
        resp = client.post(
            self.ALIPAY_URL,
            headers=promoter_headers,
            json={"order_id": 1},
        )
        assert resp.status_code in (403, 404)

    def test_alipay_unified_order_unauthenticated(self, client: TestClient):
        resp = client.post(
            self.ALIPAY_URL,
            json={"order_id": 1},
        )
        assert resp.status_code == 401


class TestPaymentConfig:
    """支付配置查询测试"""

    CONFIG_URL = "/api/payment/config"

    def test_get_config_empty(self, client: TestClient):
        resp = client.get(self.CONFIG_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], dict)

    def test_get_config_with_mock_registration(self, client: TestClient):
        from payment.config import PLATFORM_WXPAY, WxPayConfig, register

        register(
            PLATFORM_WXPAY,
            WxPayConfig(
                app_id="test_app_id",
                mch_id="test_mch_id",
                api_key="test_key",
            ),
        )
        resp = client.get(self.CONFIG_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert "wxpay" in data["data"]
        assert data["data"]["wxpay"]["app_id"] == "test_app_id"
        assert data["data"]["wxpay"]["configured"] is True

    @pytest.mark.parametrize(
        "platform,key_prefix",
        [
            ("wxpay", "wx"),
            ("alipay", "ali"),
        ],
    )
    def test_get_config_with_registration(self, client, platform, key_prefix):
        """参数化：多平台配置注册后查询"""
        from payment.config import register

        if platform == "wxpay":
            from payment.config import PLATFORM_WXPAY as P
            from payment.config import WxPayConfig

            register(
                P, WxPayConfig(app_id=f"{key_prefix}_app", mch_id=f"{key_prefix}_mch", api_key=f"{key_prefix}_key")
            )
        else:
            from payment.config import PLATFORM_ALIPAY as P
            from payment.config import AliPayConfig

            register(P, AliPayConfig(app_id=f"{key_prefix}_app", private_key="test_key"))

        resp = client.get(self.CONFIG_URL)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert platform in data
        assert data[platform]["app_id"] == f"{key_prefix}_app"
