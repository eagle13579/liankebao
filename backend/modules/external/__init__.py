"""
外部模块接入框架 - 包入口

提供:
- ExternalModuleAdapter: 外部模块适配器基类
- WebhookReceiver: 统一Webhook事件接收与路由
- ExternalModule: 外部模块注册模型（数据库）

使用方式:
    from modules.external.adapter import ExternalModuleAdapter
    from modules.external.webhook import WebhookReceiver
    from modules.external.models.external_module import ExternalModule
"""
from modules.external.adapter import ExternalModuleAdapter
from modules.external.webhook import WebhookReceiver
from modules.external.models.external_module import ExternalModule

__all__ = [
    "ExternalModuleAdapter",
    "WebhookReceiver",
    "ExternalModule",
]
