"""IPaymentProvider 抽象接口测试

测试所有提供者必须实现的接口约定。
不依赖外部网络，使用 mock。
"""

import pytest

from payment_sdk.payment_provider import CallbackResult, IPaymentProvider, PaymentResult


class TestPaymentResult:
    """PaymentResult 数据类测试"""

    def test_ok_factory(self):
        result = PaymentResult.ok(data={"key": "value"}, out_trade_no="ORDER001")
        assert result.success is True
        assert result.code == "SUCCESS"
        assert result.data == {"key": "value"}
        assert result.out_trade_no == "ORDER001"

    def test_fail_factory(self):
        result = PaymentResult.fail(message="余额不足", code="NOT_ENOUGH")
        assert result.success is False
        assert result.code == "NOT_ENOUGH"
        assert result.message == "余额不足"


class TestCallbackResult:
    """CallbackResult 数据类测试"""

    def test_verified_true(self):
        result = CallbackResult(verified=True, data={"out_trade_no": "O1"}, message="验签通过")
        assert result.verified is True
        assert result.data["out_trade_no"] == "O1"
        assert result.message == "验签通过"

    def test_verified_false(self):
        result = CallbackResult(verified=False, message="签名验证失败")
        assert result.verified is False


class TestInterfaceContract:
    """验证所有具体提供者实现 IPaymentProvider 接口"""

    def test_all_methods_defined(self):
        """确保抽象方法在 IPaymentProvider 中定义"""
        methods = ["pay", "refund", "query", "callback_verify"]
        for m in methods:
            assert hasattr(IPaymentProvider, m), f"缺少方法: {m}"
            assert callable(getattr(IPaymentProvider, m)), f"方法不可调用: {m}"

    def test_cannot_instantiate_abstract(self):
        """确保不能直接实例化 IPaymentProvider"""
        with pytest.raises(TypeError):
            IPaymentProvider()  # type: ignore
