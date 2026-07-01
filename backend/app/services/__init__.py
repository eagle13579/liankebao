from app.services.brochure import BrochureService
from app.services.tag_service import TagService
# These imports trigger a circular chain through:
# matching_engine → vector_search → models.tag → crm.crm_models → crm_router → routers.auth → services.chainke_bridge → services (loop!)
# They are imported lazily in the modules that actually need them.
# from app.services.matching_engine import MatchEngine
from app.services.trust_service import TrustService
from app.services.brochure_render import BrochureRenderer
from app.services.media_service import MediaService
from app.services.team_service import TeamService
from app.services.invoice_service import InvoiceService
from app.services.subscription_service import (
    PLANS,
    PlanConfig,
    TRIAL_DAYS,
    can_downgrade,
    can_upgrade,
    downgrade_subscription,
    get_current_subscription,
    get_plan,
    get_trial_status,
    has_used_trial,
    start_trial,
    upgrade_subscription,
)
from app.services.feedback_service import FeedbackService, FeedbackAction, FeedbackResult, FeedbackSummary, get_feedback_service
from app.services.recommend_service import (
    FeedbackRecommendation,
    RecommendService,
)
from app.services.bot_service import BotBase, BotMessage, BotCard, BotCommand, register_bot, get_bot, get_enabled_bots, list_bots
from app.services.bot_slack import SlackBot, slack_bot
from app.services.bot_feishu import FeishuBot, feishu_bot
from app.services.bot_dingtalk import DingTalkBot, dingtalk_bot
from app.services.email_service import EmailService, email_service
from app.services.email_templates import (
    welcome_html,
    trial_expiring_3d_html,
    trial_expiring_1d_html,
    trial_expired_html,
    crm_new_contact_html,
)
from app.services.calendar_service import (
    CalendarBase,
    CalendarEvent,
    CalendarResult,
    register_calendar,
    get_calendar,
    get_enabled_calendars,
    list_calendars,
)
from app.services.calendar_zoom import ZoomCalendar, zoom_calendar
from app.services.calendar_tencent import TencentCalendar, tencent_calendar

__all__ = [
    "BrochureService",
    "TagService",
    "MatchEngine",
    "TrustService",
    "BrochureRenderer",
    "MediaService",
    "TeamService",
    "InvoiceService",
    "PLANS",
    "PlanConfig",
    "TRIAL_DAYS",
    "can_downgrade",
    "can_upgrade",
    "downgrade_subscription",
    "get_current_subscription",
    "get_plan",
    "get_trial_status",
    "has_used_trial",
    "start_trial",
    "upgrade_subscription",
    "FeedbackService",
    "FeedbackAction",
    "FeedbackResult",
    "FeedbackSummary",
    "get_feedback_service",
    "FeedbackRecommendation",
    "RecommendService",
    # IM 机器人
    "BotBase",
    "BotMessage",
    "BotCard",
    "BotCommand",
    "register_bot",
    "get_bot",
    "get_enabled_bots",
    "list_bots",
    "SlackBot",
    "slack_bot",
    "FeishuBot",
    "feishu_bot",
    "DingTalkBot",
    "dingtalk_bot",
    # 邮件服务
    "EmailService",
    "email_service",
    "welcome_html",
    "trial_expiring_3d_html",
    "trial_expiring_1d_html",
    "trial_expired_html",
    "crm_new_contact_html",
    # 日历集成
    "CalendarBase",
    "CalendarEvent",
    "CalendarResult",
    "register_calendar",
    "get_calendar",
    "get_enabled_calendars",
    "list_calendars",
    "ZoomCalendar",
    "zoom_calendar",
    "TencentCalendar",
    "tencent_calendar",
]
