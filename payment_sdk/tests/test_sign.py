"""签名工具单元测试

测试 payment_sdk.sign 模块的纯函数。
不依赖外部网络，仅测试本地算法正确性。
"""

import pytest
from payment_sdk.sign import (
    generate_nonce,
    md5,
    md5_upper,
    hmac_sha256,
    hmac_sha256_upper,
    sha256,
    build_v2_sign,
    verify_v2_sign,
    build_v3_sign_str,
    build_v3_response_sign_str,
    aes_gcm_decrypt,
)


class TestGenerateNonce:
    """随机字符串生成测试"""

    def test_default_length(self):
        nonce = generate_nonce()
        assert len(nonce) == 32

    def test_custom_length(self):
        nonce = generate_nonce(16)
        assert len(nonce) == 16

    def test_randomness(self):
        n1 = generate_nonce(32)
        n2 = generate_nonce(32)
        assert n1 != n2


class TestMD5:
    """MD5 哈希测试"""

    def test_md5_basic(self):
        result = md5("hello")
        assert result == "5d41402abc4b2a76b9719d911017c592"

    def test_md5_empty(self):
        result = md5("")
        assert result == "d41d8cd98f00b204e9800998ecf8427e"

    def test_md5_upper(self):
        result = md5_upper("hello")
        assert result == "5D41402ABC4B2A76B9719D911017C592"

    def test_md5_unicode(self):
        result = md5("你好")
        assert result == "7eca689f0d3389d9dea66ae112e5cfd7"


class TestHMAC:
    """HMAC-SHA256 测试"""

    def test_hmac_sha256(self):
        result = hmac_sha256("data", "key")
        assert len(result) == 64  # 32 bytes = 64 hex chars
        # Verify it's deterministic
        assert result == hmac_sha256("data", "key")

    def test_hmac_sha256_upper(self):
        result = hmac_sha256_upper("data", "key")
        assert result == hmac_sha256("data", "key").upper()
        assert result == hmac_sha256_upper("data", "key")


class TestSHA256:
    """SHA-256 测试"""

    def test_sha256_basic(self):
        result = sha256("hello")
        assert result == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


class TestBuildV2Sign:
    """微信 V2 签名构建"""

    def test_v2_sign_md5(self):
        params = {
            "appid": "wx_test",
            "mch_id": "1600000001",
            "nonce_str": "test_nonce",
            "body": "测试商品",
            "out_trade_no": "ORDER001",
            "total_fee": "1",
            "spbill_create_ip": "127.0.0.1",
            "notify_url": "https://example.com/notify",
            "trade_type": "JSAPI",
            "openid": "o_test",
        }
        sign = build_v2_sign(params, api_key="test_key_32chars_long_abc1234567")
        assert isinstance(sign, str)
        assert len(sign) == 32  # MD5 = 32 hex chars

    def test_v2_sign_excludes_empty_and_sign(self):
        params = {
            "appid": "wx_test",
            "mch_id": "1600000001",
            "nonce_str": "test_nonce",
            "sign": "old_sign",  # should be excluded
            "empty_field": "",   # should be excluded
            "none_field": None,  # should be excluded
        }
        sign = build_v2_sign(params, api_key="test_key")
        assert isinstance(sign, str)
        assert len(sign) == 32

    def test_v2_sign_deterministic(self):
        params = {"appid": "wx_test", "mch_id": "1600000001", "nonce_str": "abc"}
        s1 = build_v2_sign(params, api_key="key1")
        s2 = build_v2_sign(params, api_key="key1")
        assert s1 == s2

    def test_v2_sign_different_key(self):
        params = {"appid": "wx_test", "mch_id": "1600000001", "nonce_str": "abc"}
        s1 = build_v2_sign(params, api_key="key1")
        s2 = build_v2_sign(params, api_key="key2")
        assert s1 != s2


class TestVerifyV2Sign:
    """微信 V2 签名验证"""

    def test_verify_correct_sign(self):
        params = {
            "appid": "wx_test",
            "mch_id": "1600000001",
            "nonce_str": "abc",
        }
        sign = build_v2_sign(params, api_key="test_key")
        params_with_sign = {**params, "sign": sign}
        assert verify_v2_sign(params_with_sign, api_key="test_key") is True

    def test_verify_wrong_sign(self):
        params = {
            "appid": "wx_test",
            "mch_id": "1600000001",
            "nonce_str": "abc",
            "sign": "WRONG_SIGN",
        }
        assert verify_v2_sign(params, api_key="test_key") is False

    def test_verify_missing_sign(self):
        params = {"appid": "wx_test", "mch_id": "1600000001"}
        assert verify_v2_sign(params, api_key="test_key") is False


class TestBuildV3SignStr:
    """微信 V3 签名串构建"""

    def test_v3_sign_str_format(self):
        result = build_v3_sign_str(
            method="POST",
            url="/v3/pay/transactions/jsapi",
            timestamp="1700000000",
            nonce="abc123",
            body='{"test": true}',
        )
        assert result == "POST\n/v3/pay/transactions/jsapi\n1700000000\nabc123\n{\"test\": true}\n"

    def test_v3_sign_str_get_empty_body(self):
        result = build_v3_sign_str(
            method="GET",
            url="/v3/certificates",
            timestamp="1700000000",
            nonce="abc123",
            body="",
        )
        assert result.startswith("GET\n/v3/certificates\n1700000000\nabc123\n\n")


class TestBuildV3ResponseSignStr:
    """微信 V3 回调响应签名串"""

    def test_v3_response_sign_str_format(self):
        result = build_v3_response_sign_str(
            timestamp="1700000000",
            nonce="abc123",
            body='{"test": true}',
        )
        assert result == "1700000000\nabc123\n{\"test\": true}\n"


class TestAesGcmDecrypt:
    """AES-GCM 解密测试"""

    def test_decrypt_invalid_data_returns_none(self):
        result = aes_gcm_decrypt(
            ciphertext_b64="invalid_base64!!!",
            key="0123456789abcdef0123456789abcdef",
            nonce="nonce123",
            associated_data="transaction",
        )
        # Invalid base64 should return None gracefully
        assert result is None

    def test_decrypt_wrong_key_returns_none(self):
        import base64
        # 无法验证解密结果因为需要正确的加密数据
        # 但可以验证错误密钥不会崩溃
        result = aes_gcm_decrypt(
            ciphertext_b64=base64.b64encode(b"some_data").decode(),
            key="0123456789abcdef0123456789abcdef",
            nonce="nonce123",
            associated_data="transaction",
        )
        # 短数据+错误密钥会触发认证失败
        assert result is None  # or raises, but should be graceful
