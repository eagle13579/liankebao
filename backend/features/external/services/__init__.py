"""外部集成模块 - 业务逻辑"""
from features.external.services.adapter import ExternalModuleAdapter
from features.external.services.webhook import WebhookReceiver

__all__ = ["ExternalModuleAdapter", "WebhookReceiver"]
