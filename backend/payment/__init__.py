"""
链客宝AI支付底层模块
基于 IJPay 设计思想封装 (Python 版)

模块结构:
    config      — ApiConfigKit 多平台支付配置注册中心
    sign        — PayKit 签名门面 (RSA/MD5/HMAC-SHA256/AES-GCM)
    http_delegate — HttpDelegate HTTP 委托抽象层
    wxpay       — 微信支付模块 (V3 + V2 兼容)
    alipay      — 支付宝模块 (框架)
"""

from payment.alipay import AliPayApi, AliPayCore
from payment.config import (
    PAYMENT_MODE_MOCK,
    PAYMENT_MODE_REAL,
    PLATFORM_ALIPAY,
    PLATFORM_WXPAY,
    AliPayConfig,
    WxPayConfig,
    get_config,
    get_current_platform,
    has_config,
    init_default_config,
    is_real_mode,
    list_platforms,
    register,
    remove_config,
    set_current_platform,
)
from payment.http_delegate import HttpDelegate, HttpResponse
from payment.sign import (
    aes_gcm_decrypt,
    build_v2_sign,
    build_v3_sign_str,
    generate_nonce,
    hmac_sha256,
    md5,
    rsa_sign,
    rsa_verify,
    rsa_verify_with_key,
    verify_v2_sign,
)
from payment.wxpay import WxPayApi, WxPayAuth, WxPayCallback

# 向后兼容名称
ApiConfigKit = type(
    "ApiConfigKit",
    (),
    {
        "register": staticmethod(register),
        "get_config": staticmethod(get_config),
        "set_current_platform": staticmethod(set_current_platform),
        "get_current_platform": staticmethod(get_current_platform),
        "init_default_config": staticmethod(init_default_config),
        "has_config": staticmethod(has_config),
        "list_platforms": staticmethod(list_platforms),
        "remove_config": staticmethod(remove_config),
    },
)

PayKit = type(
    "PayKit",
    (),
    {
        "generate_nonce": staticmethod(generate_nonce),
        "md5": staticmethod(md5),
        "hmac_sha256": staticmethod(hmac_sha256),
        "rsa_sign": staticmethod(rsa_sign),
        "rsa_verify": staticmethod(rsa_verify),
        "build_v3_sign_str": staticmethod(build_v3_sign_str),
        "build_v2_sign": staticmethod(build_v2_sign),
        "verify_v2_sign": staticmethod(verify_v2_sign),
        "aes_gcm_decrypt": staticmethod(aes_gcm_decrypt),
    },
)

__all__ = [
    # Config
    "ApiConfigKit",
    "WxPayConfig",
    "AliPayConfig",
    "register",
    "get_config",
    "set_current_platform",
    "get_current_platform",
    "has_config",
    "list_platforms",
    "remove_config",
    "init_default_config",
    "payment_platform_middleware",
    "PLATFORM_WXPAY",
    "PLATFORM_ALIPAY",
    "is_real_mode",
    "PAYMENT_MODE_REAL",
    "PAYMENT_MODE_MOCK",
    # Sign
    "PayKit",
    "generate_nonce",
    "md5",
    "hmac_sha256",
    "rsa_sign",
    "rsa_verify",
    "build_v3_sign_str",
    "build_v2_sign",
    "verify_v2_sign",
    "aes_gcm_decrypt",
    # HTTP
    "HttpDelegate",
    "HttpResponse",
    # WxPay
    "WxPayApi",
    "WxPayAuth",
    "WxPayCallback",
    # AliPay
    "AliPayApi",
    "AliPayCore",
]
