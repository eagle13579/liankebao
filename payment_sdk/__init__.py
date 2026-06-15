"""liankebao-payment-sdk — 支付模块独立SDK

基于链客宝AI backend/payment/ 核心逻辑提取，封装为独立 pip 包。
遵循 ADR-002 方案C：支付模块独立 SDK 化。

设计原则:
    - C-PAY-001: 不依赖 backend/app/ 下的任何业务模块
    - C-PAY-002: 纯函数 + 依赖注入，不持有全局状态
    - C-PAY-003: 从现有 payment/ 目录提取核心逻辑，不是重写

核心组件:
    IPaymentProvider       — 支付抽象接口 (pay/refund/query/callback_verify)
    WxPayV2Provider        — 微信支付 V2 (XML/MD5 签名)
    WxPayV3Provider        — 微信支付 V3 (JSON/RSA 签名)
    AliPayProvider         — 支付宝 (预留桩)
    WxPayConfig / AliPayConfig — 支付配置数据类
    HttpDelegate           — HTTP 委托抽象层
    sign.py                — 签名工具 (RSA/MD5/HMAC-SHA256/AES-GCM)
"""

from payment_sdk.config import AliPayConfig, WxPayConfig
from payment_sdk.http_delegate import HttpDelegate, HttpResponse
from payment_sdk.payment_provider import CallbackResult, IPaymentProvider, PaymentResult
from payment_sdk.providers.alipay import AliPayProvider
from payment_sdk.providers.wxpay_v2 import WxPayV2Provider
from payment_sdk.providers.wxpay_v3 import WxPayV3Provider
from payment_sdk.sign import (
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

__all__ = [
    "IPaymentProvider",
    "PaymentResult",
    "CallbackResult",
    "WxPayV2Provider",
    "WxPayV3Provider",
    "AliPayProvider",
    "WxPayConfig",
    "AliPayConfig",
    "HttpDelegate",
    "HttpResponse",
    "generate_nonce",
    "md5",
    "hmac_sha256",
    "rsa_sign",
    "rsa_verify",
    "rsa_verify_with_key",
    "build_v3_sign_str",
    "build_v2_sign",
    "verify_v2_sign",
    "aes_gcm_decrypt",
]

__version__ = "0.1.0"
