from app.models.ab_test import ABTest, ABTestEvent, ABTestVariant
from app.models.api_key import ApiKey, ApiKeyUsage
from app.models.audit import AuditLog
from app.models.brochure import Brochure, Page
from app.models.gaia import (
    GaiaEvolutionEvent,
    GaiaKnowledge,
    GaiaModelWeights,
    GaiaTrainingRun,
)
from app.models.integration import Integration
from app.models.invoice import Invoice
from app.models.message import Message
from app.models.payment import EnterpriseSubscription, PaymentOrder, TrialRecord
from app.models.tag import MatchRecord, UserTag
from app.models.trust import TrustNetwork
from app.models.user import User
from app.models.visitor import VisitorLog
from app.models.webhook import WebhookSubscription

# Lazy import to avoid circular chain:
# models.__init__ → crm.crm_models → crm.__init__ → crm_router → routers.auth → services → ai → vector_search → models.tag (loop!)
# Import directly from the module when needed: from app.crm.crm_models import CrmContact
# from app.crm.crm_models import (
#     CrmContact,
#     CrmDeal,
#     CrmPipelineStage,
#     CrmActivity,
#     CrmNote,
# )

__all__ = [
    "User",
    "Brochure",
    "Page",
    "UserTag",
    "MatchRecord",
    "VisitorLog",
    "TrustNetwork",
    "PaymentOrder",
    "EnterpriseSubscription",
    "Integration",
    "WebhookSubscription",
    "ABTest",
    "ABTestVariant",
    "ABTestEvent",
    "AuditLog",
    "ApiKey",
    "ApiKeyUsage",
    "Message",
    "Invoice",
    "GaiaKnowledge",
    "GaiaEvolutionEvent",
    "GaiaTrainingRun",
    "GaiaModelWeights",
    # CRM
    "CrmContact",
    "CrmDeal",
    "CrmPipelineStage",
    "CrmActivity",
    "CrmNote",
]
