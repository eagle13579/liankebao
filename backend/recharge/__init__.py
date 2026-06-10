"""链客宝AI充值支付模块

模块结构:
    models     — 数据库模型 (SQLAlchemy)
    routes     — FastAPI 充值 API 路由
    callback   — 支付回调处理

在 main.py 中通过以下方式注册:
    import recharge.routes as recharge_module
    import recharge.callback as recharge_callback_module
    app.include_router(recharge_module.router)
    app.include_router(recharge_callback_module.callback_router)
"""
