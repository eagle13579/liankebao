"""
开发者门户 ORM 模型
====================
迁移自 source models.py (developer_portal 区域: ApiKey/WebhookSubscriptionDB/ApiUsageLog/WebhookDeliveryLog)

所包含模型:
  - ApiKey            — API Key 管理
  - WebhookSubscriptionDB — Webhook 订阅持久化
  - ApiUsageLog       — API 调用日志 (按 Key 维度)
  - WebhookDeliveryLog — Webhook 投递日志

适配说明:
  - 使用 String(64) 替代 ForeignKey 关联用户 (chainke-full 风格)
  - 移除 relationship() 引用 (无 User ORM 模型)
  - 使用 from app.database import Base
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class ApiKey(Base):
    """API Key 模型 — 开发者门户"""

    __tablename__ = "api_keys"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key_id = Column(String(64), unique=True, index=True, nullable=False, comment="公开标识 ID (lk_xxx)")
    key_hash = Column(String(128), nullable=False, comment="API Key 的 SHA256 哈希")
    key_prefix = Column(String(16), nullable=False, comment="Key 前 8 位用于显示")
    name = Column(String(100), nullable=False, comment="Key 名称")
    user_id = Column(String(64), nullable=False, index=True, comment="所属用户 ID")
    scopes = Column(String(500), nullable=False, default="read", comment="权限范围 JSON 数组")
    tier = Column(String(20), nullable=False, default="free", comment="API 等级: free/pro/enterprise")
    rate_limit_per_hour = Column(Integer, nullable=False, default=100)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ApiKey(key_id={self.key_id}, name={self.name}, user_id={self.user_id})>"


class WebhookSubscriptionDB(Base):
    """Webhook 订阅模型 — 数据库持久化"""

    __tablename__ = "webhook_subscriptions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sub_id = Column(String(64), unique=True, index=True, nullable=False, comment="订阅标识 (wh_xxx)")
    url = Column(String(1024), nullable=False, comment="回调 URL")
    events = Column(String(500), nullable=False, comment="订阅事件类型 JSON 数组")
    secret = Column(String(128), nullable=False, comment="HMAC 签名密钥")
    active = Column(Boolean, nullable=False, default=True)
    user_id = Column(String(64), nullable=False, index=True, comment="所属用户 ID")
    retry_count = Column(Integer, nullable=False, default=0)
    last_delivery_at = Column(DateTime, nullable=True)
    last_delivery_status = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WebhookSubscriptionDB(sub_id={self.sub_id}, url={self.url}, user_id={self.user_id})>"


class ApiUsageLog(Base):
    """API 调用日志 — 按 API Key 统计"""

    __tablename__ = "api_usage_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    api_key_id = Column(Integer, nullable=False, index=True, comment="关联 API Key 的 id (非 key_id)")
    user_id = Column(String(64), nullable=False, index=True, comment="所属用户 ID")
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False, default=0)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ApiUsageLog(api_key_id={self.api_key_id}, endpoint={self.endpoint}, user_id={self.user_id})>"


class WebhookDeliveryLog(Base):
    """Webhook 投递日志"""

    __tablename__ = "webhook_delivery_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subscription_id = Column(Integer, nullable=False, index=True, comment="关联 WebhookSubscription 的 id")
    event_type = Column(String(50), nullable=False)
    event_id = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, comment="success/failed/retrying")
    attempt = Column(Integer, nullable=False, default=1)
    response_code = Column(Integer, nullable=True)
    error_message = Column(String(500), nullable=True, comment="错误详情")
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WebhookDeliveryLog(subscription_id={self.subscription_id}, event_type={self.event_type}, status={self.status})>"
