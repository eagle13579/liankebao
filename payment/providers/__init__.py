"""支付渠道提供者 — 包初始化

导出所有支付提供者。
"""

from payment.providers.alipay import AliPayProvider
from payment.providers.wxpay import WxPayProvider

__all__ = [
    "AliPayProvider",
    "WxPayProvider",
]
