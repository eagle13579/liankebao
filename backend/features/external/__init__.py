"""外部集成模块 (External Integration Module)

迁移自旧版链客宝 backend/modules/external/
适配 chainke-full 架构。

提供:
- ExternalModuleAdapter: 外部模块适配器基类
- WebhookReceiver: 统一Webhook事件接收与路由
- ExternalModule: 外部模块注册模型（数据库）

使用方式:
    from features.external.services.adapter import ExternalModuleAdapter
    from features.external.services.webhook import WebhookReceiver
    from features.external.models.external_module import ExternalModule
"""
