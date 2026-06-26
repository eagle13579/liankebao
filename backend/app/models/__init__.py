"""链客宝 — 数据模型包

原 app/models.py 拆分为 app/models/ 包。
__init__.py 向后兼容导出: from app.models import BusinessCard, ... 仍可用。
feedback.py 为新增反馈模块。
"""

# ── 向后兼容：导入原 models.py 所有导出符号 ──────────────────────
from app.models._legacy import (
    BusinessCard,
    BROCHURE_SYNC_STORE,
    sync_brochure_from_card,
    get_brochure_from_store,
    init_models,
    Base,
)
from app.database import engine
from app.models.feedback import Feedback, FeedbackStats
from app.models.audit_log import AuditLog
from app.notification_service import NotificationRecord
from app.models.developer_portal_models import (
    ApiKey,
    ApiUsageLog,
    WebhookDeliveryLog,
    WebhookSubscriptionDB,
)
from app.models.trust_score_models import (
    BehaviorPoint,
    TrustGuarantee,
    TrustScore,
    get_trust_tier,
)
from features.orders.models import Order
from features.products.models import Product
from features.promoter.models import Withdrawal
from features.contacts.models import Contact, ImportHistory
from features.needs.models import BusinessNeed
from features.activities.models import Activity

from features.external.models import ExternalModule
from app.models.user import User, hash_password, verify_password
from features.subscription.models import SubscriptionPlan, Subscription, Invoice

__all__ = [
    "Feedback",
    "FeedbackStats",
    "AuditLog",
    "NotificationRecord",
    "BusinessCard",
    "BROCHURE_SYNC_STORE",
    "sync_brochure_from_card",
    "get_brochure_from_store",
    "init_models",
    "Base",
    "engine",
    "ApiKey",
    "ApiUsageLog",
    "WebhookDeliveryLog",
    "WebhookSubscriptionDB",
    "TrustScore",
    "BehaviorPoint",
    "TrustGuarantee",
    "get_trust_tier",
    "Order",
    "Product",
    "Withdrawal",
    "Contact",
    "ImportHistory",
    "BusinessNeed",
    "Activity",
    "ExternalModule",
    "User",
    "hash_password",
    "verify_password",
]
