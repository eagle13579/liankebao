"""链客宝 — 支付回调处理模块

从旧版链客宝 recharge/callback.py 迁移，适配 chainke-full 架构。

模块结构:
    recharge_callback — 充值回调核心业务逻辑 (订单状态更新 + 余额处理)
    wxpay_callback    — 微信支付回调验签服务
    alipay_callback   — 支付宝回调验签服务

设计原则:
    - 回调验签委托给 payment/providers/ 下的 Provider.callback_verify()
    - 充值业务逻辑保持独立，可被多个支付渠道复用
    - 幂等保护: 状态机检查 (pending→paid) + order_no 唯一约束
"""
