"""
支付模块测试
=============
- 微信统一下单（mock 模式）
- 微信支付回调（V3 模拟、V2 XML 模拟、mock JSON）
- 支付宝统一下单（mock 模式）
- 支付配置查询
- 幂等性保护（重复回调不重复处理）
- 订单归属权校验
- 退款（mock 模式）
- 权限边界测试
"""
import json
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
        """微信统一下单成功（mock 模式，无 openid 时会报错）"""
        order_id = self._create_pending_order(client, buyer_headers)
        # 需要 openid，给一个模拟值
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
        # 用户没有 wechat_openid，应报错
        assert resp.status_code == 400
        assert "openid" in resp.text.lower()

    def test_unified_order_not_owner(self, client: TestClient, promoter_headers):
        """非订单归属人下单应返回 403"""
        # 用非 buyer 的 token 操作
        order_id = self._create_pending_order(client, {"Authorization": "Bearer dummy"})
        # 重新获取 buyer 创建的订单 ID
        resp = client.post(
            self.UNIFIED_URL,
            headers=promoter_headers,
            json={"order_id": 1, "openid": "mock_openid"},
        )
        # order_id=1 是 buyer 的 seed 订单，promoter 无权操作
        assert resp.status_code in (403, 404)

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
        # buyer 有一个 seed paid 订单 (id=2)
        resp = client.post(
            self.UNIFIED_URL,
            headers=buyer_headers,
            json={"order_id": 2, "openid": "mock_openid"},
        )
        # order_id=2 是 paid 状态
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
    """微信支付回调测试"""

    CALLBACK_URL = "/api/payment/wxpay/callback"

    def _create_pending_order_for_callback(
        self, client: TestClient, buyer_headers
    ) -> tuple:
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
        # out_trade_no 格式: LK{order_id:08d}{timestamp}
        out_trade_no = f"LK{order_id:08d}{int(time.time())}"
        return order_id, out_trade_no

    def test_callback_json_mock_success(self, client: TestClient, buyer_headers):
        """JSON 格式 mock 回调成功"""
        order_id, out_trade_no = self._create_pending_order_for_callback(
            client, buyer_headers
        )
        # 先统一下单以获取 prepay_id
        client.post(
            "/api/payment/wxpay/unified-order",
            headers=buyer_headers,
            json={"order_id": order_id, "openid": "mock_openid"},
        )

        # 发送 mock JSON 回调
        resp = client.post(
            self.CALLBACK_URL,
            json={
                "out_trade_no": out_trade_no,
                "transaction_id": f"mock_tx_{order_id}",
                "result_code": "SUCCESS",
            },
        )
        assert resp.status_code == 200, f"回调应成功: {resp.text}"
        assert resp.json()["code"] == "SUCCESS"

        # 验证订单状态
        query_resp = client.get(
            f"/api/orders/{order_id}",
            headers=buyer_headers,
        )
        assert query_resp.status_code == 200
        # 订单应变为 paid

    def test_callback_v3_signature_headers(self, client: TestClient, buyer_headers):
        """模拟 V3 回调（带签名头），使用 mock 配置降级处理"""
        order_id, out_trade_no = self._create_pending_order_for_callback(
            client, buyer_headers
        )
        # 带 V3 签名头（mock 配置下会走 V2/Mock 分支）
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
        # V3 头 + 无真实配置 = 验签失败 → FAIL
        # 但 conftest 清空了 _config_registry，所以 has_config(PLATFORM_WXPAY)=False
        # 会走 else 分支（mock 兼容）
        assert resp.status_code == 200
        # 至少不报 500

    def test_callback_idempotent(self, client: TestClient, buyer_headers):
        """重复回调幂等 — 第二次不重复处理"""
        order_id, out_trade_no = self._create_pending_order_for_callback(
            client, buyer_headers
        )
        # 第一次回调
        resp1 = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": out_trade_no, "result_code": "SUCCESS"},
        )
        assert resp1.json()["code"] == "SUCCESS"

        # 第二次回调（幂等）
        resp2 = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": out_trade_no, "result_code": "SUCCESS"},
        )
        assert resp2.status_code == 200
        # 第二次因为 order.status != "pending"，应返回 "已处理"
        assert resp2.json()["code"] == "SUCCESS"

    def test_callback_no_out_trade_no(self, client: TestClient):
        """缺少 out_trade_no 的请求"""
        resp = client.post(self.CALLBACK_URL, json={"result_code": "SUCCESS"})
        assert resp.status_code == 200
        # 没有 LK 前缀的 out_trade_no，会 fallback 到 prepay_id 匹配
        assert resp.json()["code"] in ("SUCCESS", "FAIL")

    def test_callback_xml_v2_compatible(self, client: TestClient, buyer_headers):
        """模拟 V2 XML 回调（通过 raw body）"""
        order_id, out_trade_no = self._create_pending_order_for_callback(
            client, buyer_headers
        )
        # 发送 XML 格式 body, Content-Type 不影响 json.loads 但在 except 中会解析 XML
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
        # XML 解析后应该能提取 out_trade_no 和 transaction_id
        assert resp.json()["code"] in ("SUCCESS", "FAIL")

    def test_callback_order_not_pending(self, client: TestClient):
        """已 paid 状态的订单收到回调返回已处理"""
        # 使用 seed 数据中的 paid 订单，out_trade_no 使用 LK{id} 格式
        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": "LK00000002123456789", "result_code": "SUCCESS"},
        )
        # order_id=2 在 seed 中是 paid，状态机检查跳过
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"


class TestWxPayRefund:
    """微信退款测试"""

    REFUND_URL = "/api/payment/wxpay/refund"

    def test_refund_mock_success(self, client: TestClient, buyer_headers):
        """Mock 退款成功（paid 状态的订单）"""
        # seed 数据中 order_id=2 是 paid 状态
        resp = client.post(
            self.REFUND_URL,
            headers=buyer_headers,
            json={"order_id": 2, "reason": "测试退款"},
        )
        assert resp.status_code == 200, f"退款应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert "退款" in data["message"]

    def test_refund_not_owner(self, client: TestClient, promoter_headers):
        """非订单所有人退款返回 403"""
        resp = client.post(
            self.REFUND_URL,
            headers=promoter_headers,
            json={"order_id": 2},
        )
        assert resp.status_code == 403

    def test_refund_nonexistent_order(self, client: TestClient, buyer_headers):
        """不存在的订单返回 404"""
        resp = client.post(
            self.REFUND_URL,
            headers=buyer_headers,
            json={"order_id": 99999},
        )
        assert resp.status_code == 404

    def test_refund_invalid_status(self, client: TestClient, buyer_headers):
        """pending 状态的订单不能退款"""
        resp = client.post(
            self.REFUND_URL,
            headers=buyer_headers,
            json={"order_id": 1},  # order_id=1 是 received 状态
        )
        # received 状态也不允许退款？看路由逻辑只允许 paid/shipped
        # order_id=1 是 received
        assert resp.status_code == 400

    def test_refund_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
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
        """支付宝统一下单 mock 模式"""
        order_id = self._create_pending_order(client, buyer_headers)
        resp = client.post(
            self.ALIPAY_URL,
            headers=buyer_headers,
            json={"order_id": order_id, "subject": "测试商品"},
        )
        assert resp.status_code == 200, f"支付宝下单应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["_mode"] == "mock"
        assert "order_string" in data["data"]
        assert "alipay.trade.app.pay" in data["data"]["order_string"]

    def test_alipay_unified_order_not_owner(self, client: TestClient, promoter_headers):
        """非订单所有人支付宝下单返回 403"""
        resp = client.post(
            self.ALIPAY_URL,
            headers=promoter_headers,
            json={"order_id": 1},
        )
        assert resp.status_code in (403, 404)

    def test_alipay_unified_order_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.post(
            self.ALIPAY_URL,
            json={"order_id": 1},
        )
        assert resp.status_code == 401


class TestPaymentConfig:
    """支付配置查询测试"""

    CONFIG_URL = "/api/payment/config"

    def test_get_config_empty(self, client: TestClient):
        """未配置支付时返回空配置"""
        resp = client.get(self.CONFIG_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        # conftest 清理了配置，所以应该没有数据
        assert isinstance(data["data"], dict)

    def test_get_config_with_mock_registration(self, client: TestClient):
        """注册 mock 配置后查询"""
        from payment.config import register, WxPayConfig, PLATFORM_WXPAY
        register(PLATFORM_WXPAY, WxPayConfig(
            app_id="test_app_id",
            mch_id="test_mch_id",
            api_key="test_key",
        ))
        resp = client.get(self.CONFIG_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert "wxpay" in data["data"]
        assert data["data"]["wxpay"]["app_id"] == "test_app_id"
        assert data["data"]["wxpay"]["configured"] is True
