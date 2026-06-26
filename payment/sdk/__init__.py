"""链客宝支付 SDK | 核心工具包 (独立于 provider 实现)

从旧版 payment_sdk/ 提取核心工具类，适配到 chainke-full 项目结构。

包路径: payment.sdk.*
设计原则:
    - C-PAY-001: 不依赖 backend/app/ 下的任何业务模块
    - C-PAY-002: 纯函数 + 依赖注入，不持有全局状态
    - C-PAY-003: 从旧版 payment_sdk/ 提取核心逻辑，不是重写

核心组件:
    IPaymentProvider       — 支付抽象接口 (pay/refund/query/callback_verify)
    PaymentResult          — 支付操作统一结果
    CallbackResult         — 回调验证结果
    WxPayConfig            — 微信支付配置数据类
    AliPayConfig           — 支付宝配置数据类
    HttpDelegate           — HTTP 委托抽象层
    sign.*                 — 签名工具 (RSA/MD5/HMAC-SHA256/AES-GCM)

注意:
    具体支付提供者 (AliPayProvider / WxPayProvider) 位于 payment.providers.* 中。
"""

from payment.sdk.config import AliPayConfig, WxPayConfig, is_real_mode
from payment.sdk.http_delegate import HttpDelegate, HttpResponse
from payment.sdk.payment_provider import CallbackResult, IPaymentProvider, PaymentResult
from payment.sdk.sign import (
    aes_gcm_decrypt,
    build_v2_sign,
    build_v3_response_sign_str,
    build_v3_sign_str,
    generate_nonce,
    hmac_sha256,
    hmac_sha256_upper,
    md5,
    md5_upper,
    rsa_sign,
    rsa_sign_bytes,
    rsa_verify,
    rsa_verify_with_key,
    sha256,
    verify_v2_sign,
)

__all__ = [
    # 支付抽象接口
    "IPaymentProvider",
    "PaymentResult",
    "CallbackResult",
    # 配置数据类
    "WxPayConfig",
    "AliPayConfig",
    "is_real_mode",
    # HTTP 委托
    "HttpDelegate",
    "HttpResponse",
    # 签名工具
    "generate_nonce",
    "md5",
    "md5_upper",
    "hmac_sha256",
    "hmac_sha256_upper",
    "sha256",
    "rsa_sign",
    "rsa_sign_bytes",
    "rsa_verify",
    "rsa_verify_with_key",
    "build_v3_sign_str",
    "build_v3_response_sign_str",
    "build_v2_sign",
    "verify_v2_sign",
    "aes_gcm_decrypt",
]

__version__ = "0.2.0"
