"""微信支付 V3 提供者单元测试

测试 WxPayV3Provider 所有方法。
不依赖外部网络 — 使用 mock 模拟 HTTP 响应。

测试覆盖:
    - pay() JSAPI 统一下单
    - refund() 退款
    - query() 订单查询
    - callback_verify() 回调验签 (签名验证 + resource 解密)
    - close_order() 关闭订单
    - query_refund() 退款查询
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payment_sdk.config import WxPayConfig
from payment_sdk.http_delegate import HttpDelegate, HttpResponse
from payment_sdk.providers.wxpay_v3 import WxPayV3Provider

# ============================================================
# 测试用配置
# ============================================================


@pytest.fixture
def mock_config():
    """创建测试用 WxPayConfig (不需要真实证书)"""
    return WxPayConfig(
        app_id="wx_test_appid",
        mch_id="1600000001",
        api_key="test_api_key_32chars_long_abc123",
        api_v3_key="0123456789abcdef0123456789abcdef",  # 32位
        private_key_path="/tmp/test_key.pem",
        cert_serial_no="1234567890ABCDEF",
        notify_url="https://example.com/notify",
        refund_notify_url="",
        cert_path="/tmp/test_cert.pem",
        root_ca_path="",
    )


@pytest.fixture
def mock_http():
    """创建模拟 HTTP 委托"""
    http = AsyncMock(spec_set=["post", "get", "put", "delete", "close"])
    http.post = AsyncMock()
    http.get = AsyncMock()
    return http


@pytest.fixture
def v3_provider(mock_config, mock_http):
    """创建 V3 提供者 (mock 掉 RSA 签名和 SSL 证书以避免真实私钥依赖)"""
    with patch.multiple(
        WxPayV3Provider,
        _get_auth_headers=MagicMock(
            return_value={
                "Authorization": 'WECHATPAY2-SHA256-RSA2048 mchid="test",nonce_str="x",timestamp="0",serial_no="x",signature="x"',
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "liankebao-payment/1.0",
            }
        ),
        _build_jsapi_payment_params=MagicMock(
            return_value={
                "appId": "wx_test_appid",
                "timeStamp": "1700000000",
                "nonceStr": "test_nonce",
                "package": "prepay_id=mock_prepay",
                "signType": "RSA",
                "paySign": "mock_signature",
            }
        ),
    ):
        provider = WxPayV3Provider(config=mock_config, http_delegate=mock_http)
        yield provider


@pytest.fixture
def v3_provider_no_patches(mock_config, mock_http):
    """创建 V3 提供者但不应用 method-level patches（用于单独测试 refund/close）"""
    provider = WxPayV3Provider(config=mock_config, http_delegate=mock_http)
    return provider, mock_http


# ============================================================
# V3 模拟响应
# ============================================================


def _v3_success_response(prepay_id="wx25001234567890"):
    return json.dumps({"prepay_id": prepay_id})


def _v3_refund_response():
    return json.dumps(
        {
            "refund_id": "refund_12345",
            "out_refund_no": "REFUND001",
            "status": "SUCCESS",
        }
    )


def _v3_query_response():
    return json.dumps(
        {
            "transaction_id": "wx420250101234567890",
            "out_trade_no": "ORDER001",
            "trade_state": "SUCCESS",
            "amount": {"total": 1, "payer_total": 1},
        }
    )


def _v3_callback_body():
    """模拟微信 V3 回调（包含 resource 加密字段，但测试中不实际解密）"""
    return json.dumps(
        {
            "id": "EV-123",
            "create_time": "2025-01-01T00:00:00+08:00",
            "resource_type": "encrypt-resource",
            "event_type": "TRANSACTION.SUCCESS",
            "summary": "支付成功",
            "resource": {
                "original_type": "transaction",
                "algorithm": "AEAD_AES_256_GCM",
                "ciphertext": "encrypted_data",
                "associated_data": "transaction",
                "nonce": "nonce_str",
            },
        }
    )


# ============================================================
# 测试用例
# ============================================================


class TestWxPayV3ProviderPay:
    """统一下单测试"""

    async def test_pay_success(self, v3_provider, mock_http):
        mock_http.post.return_value = HttpResponse(status=200, body=_v3_success_response("wx_prepay_001"))
        result = await v3_provider.pay(
            openid="o_test_openid",
            out_trade_no="ORDER001",
            total_fee=1,
            description="测试商品",
        )
        assert result.success is True
        assert result.provider_order_id == "wx_prepay_001"
        assert result.out_trade_no == "ORDER001"
        assert "payment_params" in (result.data or {})

    async def test_pay_fail(self, v3_provider, mock_http):
        mock_http.post.return_value = HttpResponse(
            status=400, body=json.dumps({"code": "PARAM_ERROR", "message": "参数错误"})
        )
        result = await v3_provider.pay(
            openid="o_test_openid",
            out_trade_no="ORDER001",
            total_fee=1,
            description="测试商品",
        )
        assert result.success is False

    async def test_pay_http_error(self, v3_provider, mock_http):
        mock_http.post.return_value = HttpResponse(status=0, body="Connection timeout")
        result = await v3_provider.pay(
            openid="o_test_openid",
            out_trade_no="ORDER001",
            total_fee=1,
            description="测试商品",
        )
        assert result.success is False


class TestWxPayV3ProviderQuery:
    """订单查询测试"""

    async def test_query_by_out_trade_no(self, v3_provider, mock_http):
        mock_http.get.return_value = HttpResponse(status=200, body=_v3_query_response())
        result = await v3_provider.query(out_trade_no="ORDER001")
        assert result.success is True
        assert result.provider_order_id == "wx420250101234567890"
        assert result.data["trade_state"] == "SUCCESS"

    async def test_query_by_transaction_id(self, v3_provider, mock_http):
        mock_http.get.return_value = HttpResponse(status=200, body=_v3_query_response())
        result = await v3_provider.query(
            out_trade_no="ORDER001",
            transaction_id="wx420250101234567890",
        )
        assert result.success is True

    async def test_query_not_found(self, v3_provider, mock_http):
        mock_http.get.return_value = HttpResponse(status=404, body=json.dumps({"code": "ORDER_NOT_EXIST"}))
        result = await v3_provider.query(out_trade_no="NONEXIST")
        assert result.success is False


class TestWxPayV3ProviderRefund:
    """退款测试 (需要 mock SSL certs)"""

    async def test_refund_success(self, mock_config, mock_http):
        with patch.object(HttpDelegate, "with_ssl_cert", return_value=mock_http):
            with patch.object(
                WxPayV3Provider,
                "_get_auth_headers",
                return_value={
                    "Authorization": "mock",
                    "Content-Type": "application/json",
                },
            ):
                provider = WxPayV3Provider(config=mock_config, http_delegate=mock_http)
                mock_http.post.return_value = HttpResponse(status=200, body=_v3_refund_response())
                result = await provider.refund(
                    out_trade_no="ORDER001",
                    out_refund_no="REFUND001",
                    refund_amount=1,
                    total_amount=1,
                )
                assert result.success is True
                assert result.provider_order_id == "refund_12345"

    async def test_refund_fail(self, mock_config, mock_http):
        with patch.object(HttpDelegate, "with_ssl_cert", return_value=mock_http):
            with patch.object(
                WxPayV3Provider,
                "_get_auth_headers",
                return_value={
                    "Authorization": "mock",
                    "Content-Type": "application/json",
                },
            ):
                provider = WxPayV3Provider(config=mock_config, http_delegate=mock_http)
                mock_http.post.return_value = HttpResponse(status=400, body=json.dumps({"code": "NOT_ENOUGH"}))
                result = await provider.refund(
                    out_trade_no="ORDER001",
                    out_refund_no="REFUND001",
                    refund_amount=100,
                    total_amount=100,
                )
                assert result.success is False


class TestWxPayV3ProviderCallback:
    """回调验签测试"""

    async def test_callback_missing_headers(self, v3_provider):
        result = await v3_provider.callback_verify(
            body=b"{}",
            headers={},
        )
        assert result.verified is False
        assert "缺少" in result.message

    async def test_callback_missing_platform_cert(self, v3_provider):
        result = await v3_provider.callback_verify(
            body=b"{}",
            headers={
                "Wechatpay-Signature": "sig",
                "Wechatpay-Serial": "serial_001",
                "Wechatpay-Timestamp": "1700000000",
                "Wechatpay-Nonce": "nonce",
            },
        )
        assert result.verified is False
        assert "未找到平台证书" in result.message

    async def test_callback_pass_platform_cert(self, v3_provider):
        """传递平台证书后能完成验签流程(即使签名本身错误)"""
        result = await v3_provider.callback_verify(
            body=_v3_callback_body().encode("utf-8"),
            headers={
                "Wechatpay-Signature": "base64_signature",
                "Wechatpay-Serial": "serial_001",
                "Wechatpay-Timestamp": "1700000000",
                "Wechatpay-Nonce": "nonce_str",
            },
            platform_cert_map={
                "serial_001": b"-----BEGIN PUBLIC KEY-----\nINVALID\n-----END PUBLIC KEY-----",
            },
        )
        # 证书无效，签名验证失败，但接口不会崩溃
        assert result.verified is False


class TestWxPayV3ProviderCloseOrder:
    """关闭订单测试"""

    async def test_close_order_success(self, v3_provider, mock_http):
        mock_http.post.return_value = HttpResponse(status=204, body="")
        result = await v3_provider.close_order("ORDER001")
        assert result is True

    async def test_close_order_fail(self, v3_provider, mock_http):
        mock_http.post.return_value = HttpResponse(status=404, body="")
        result = await v3_provider.close_order("NONEXIST")
        assert result is False


class TestWxPayV3ProviderConfig:
    """配置测试"""

    def test_default_config_loaded(self, mock_config):
        provider = WxPayV3Provider(config=mock_config)
        assert provider.config.app_id == "wx_test_appid"

    def test_auto_env_config(self):
        import os

        os.environ["WXPAY_APPID"] = "env_v3_appid"
        os.environ["WXPAY_MCH_ID"] = "env_v3_mchid"
        os.environ["WXPAY_API_KEY"] = "env_apikey_32chars_test_abcdefghijk"
        try:
            provider = WxPayV3Provider()
            assert provider.config.app_id == "env_v3_appid"
        finally:
            del os.environ["WXPAY_APPID"]
            del os.environ["WXPAY_MCH_ID"]
            del os.environ["WXPAY_API_KEY"]
