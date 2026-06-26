"""链客宝 — 支付模块

支付模块包含:
    router          — FastAPI 支付路由 (订单创建/查询/关闭/回调)
    models          — SQLAlchemy 支付订单模型
    payment_engine  — 微信支付 V3 独立引擎
    providers       — 支付渠道提供者 (支付宝、微信等)

设计原则:
    - 不依赖 backend/app/ 下的任何业务模块
    - 纯函数 + 依赖注入
    - 从旧版链客宝 payment/ 目录提取核心逻辑，适配迁移
"""

from payment.providers.alipay import AliPayConfig, AliPayCore, AliPayProvider
from payment.providers.wxpay import WxPayConfig, WxPayCore, WxPayProvider

__all__ = [
    "AliPayProvider",
    "AliPayCore",
    "AliPayConfig",
    "WxPayProvider",
    "WxPayCore",
    "WxPayConfig",
]
