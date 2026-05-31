"""支付模块配置测试

测试 WxPayConfig 和 AliPayConfig 数据类。
不依赖外部网络。
"""

import os

from payment_sdk.config import AliPayConfig, WxPayConfig, is_real_mode


class TestWxPayConfig:
    """WxPayConfig 测试"""

    def test_default_values(self):
        config = WxPayConfig()
        assert config.app_id == ""
        assert config.mch_id == ""
        assert config.is_configured is False

    def test_from_env_wxpay_prefix(self):
        os.environ["WXPAY_APPID"] = "wx_test"
        os.environ["WXPAY_MCH_ID"] = "mch_test"
        os.environ["WXPAY_API_KEY"] = "key_test_32chars_long_test_abc123"
        try:
            config = WxPayConfig.from_env()
            assert config.app_id == "wx_test"
            assert config.mch_id == "mch_test"
            assert config.is_configured is True
        finally:
            del os.environ["WXPAY_APPID"]
            del os.environ["WXPAY_MCH_ID"]
            del os.environ["WXPAY_API_KEY"]

    def test_from_env_wechat_prefix_fallback(self):
        os.environ["WECHAT_APPID"] = "wx_wechat"
        os.environ["WECHAT_MCH_ID"] = "mch_wechat"
        os.environ["WECHAT_API_KEY"] = "key_wechat_32chars_long_test_abc123"
        try:
            config = WxPayConfig.from_env()
            assert config.app_id == "wx_wechat"
        finally:
            del os.environ["WECHAT_APPID"]
            del os.environ["WECHAT_MCH_ID"]
            del os.environ["WECHAT_API_KEY"]

    def test_wxpay_prefix_preferred(self):
        os.environ["WXPAY_APPID"] = "wx_primary"
        os.environ["WECHAT_APPID"] = "wx_fallback"
        os.environ["WXPAY_MCH_ID"] = "mch_primary"
        os.environ["WECHAT_MCH_ID"] = "mch_fallback"
        os.environ["WXPAY_API_KEY"] = "key_primary_32chars_long_test_abc12"
        try:
            config = WxPayConfig.from_env()
            assert config.app_id == "wx_primary"
            assert config.mch_id == "mch_primary"
        finally:
            del os.environ["WXPAY_APPID"]
            del os.environ["WECHAT_APPID"]
            del os.environ["WXPAY_MCH_ID"]
            del os.environ["WECHAT_MCH_ID"]
            del os.environ["WXPAY_API_KEY"]

    def test_not_configured_without_api_key(self):
        os.environ["WXPAY_APPID"] = "wx_test"
        os.environ["WXPAY_MCH_ID"] = "mch_test"
        try:
            config = WxPayConfig.from_env()
            assert config.is_configured is False
        finally:
            del os.environ["WXPAY_APPID"]
            del os.environ["WXPAY_MCH_ID"]

    def test_from_env_custom_prefix(self):
        os.environ["CUSTOM_APPID"] = "wx_custom"
        os.environ["CUSTOM_MCH_ID"] = "mch_custom"
        os.environ["CUSTOM_API_KEY"] = "key_custom_32chars_long_test_abc12"
        try:
            config = WxPayConfig.from_env(prefix="CUSTOM_")
            # 自定义前缀不匹配 WXPAY_/WECHAT_ 模式
            # from_env 内部的 _get_env_dual 仍使用那些前缀
            # 所以 custom prefix 不会生效
            assert config.app_id == ""
        finally:
            del os.environ["CUSTOM_APPID"]
            del os.environ["CUSTOM_MCH_ID"]
            del os.environ["CUSTOM_API_KEY"]


class TestAliPayConfig:
    """AliPayConfig 测试"""

    def test_default_values(self):
        config = AliPayConfig()
        assert config.app_id == ""
        assert config.gateway == "https://openapi.alipay.com/gateway.do"
        assert config.is_configured is False

    def test_from_env(self):
        os.environ["ALIPAY_APP_ID"] = "ali_test"
        os.environ["ALIPAY_PRIVATE_KEY"] = "private_key_content"
        try:
            config = AliPayConfig.from_env()
            assert config.app_id == "ali_test"
            assert config.is_configured is True
        finally:
            del os.environ["ALIPAY_APP_ID"]
            del os.environ["ALIPAY_PRIVATE_KEY"]

    def test_not_configured_without_private_key(self):
        os.environ["ALIPAY_APP_ID"] = "ali_test"
        try:
            config = AliPayConfig.from_env()
            assert config.is_configured is False
        finally:
            del os.environ["ALIPAY_APP_ID"]


class TestIsRealMode:
    """支付模式测试"""

    def test_default_is_mock(self):
        # 默认不设置 PAYMENT_MODE 时应为 mock
        if "PAYMENT_MODE" in os.environ:
            del os.environ["PAYMENT_MODE"]
        assert is_real_mode() is False

    def test_real_mode(self):
        os.environ["PAYMENT_MODE"] = "real"
        try:
            assert is_real_mode() is True
        finally:
            del os.environ["PAYMENT_MODE"]

    def test_mock_mode(self):
        os.environ["PAYMENT_MODE"] = "mock"
        try:
            assert is_real_mode() is False
        finally:
            del os.environ["PAYMENT_MODE"]

    def test_case_insensitive(self):
        os.environ["PAYMENT_MODE"] = "REAL"
        try:
            assert is_real_mode() is True
        finally:
            del os.environ["PAYMENT_MODE"]
