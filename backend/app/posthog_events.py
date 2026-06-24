"""
PostHog 用户行为漏斗事件定义
提供完整的用户生命周期事件追踪：注册→激活→留存→付费→推荐

用法:
    from app.posthog_events import track_user_registered, track_card_created
    await track_user_registered(user_id, {"source": "wechat_miniapp"})
"""

import logging

from app.posthog_config import capture_event, identify_user, is_posthog_active

logger = logging.getLogger(__name__)

# =============================================================================
# 用户注册漏斗
# =============================================================================


def track_user_registered(
    user_id: str,
    traits: dict | None = None,
) -> None:
    """用户注册成功 — 漏斗第一层"""
    props = traits or {}
    props.setdefault("registration_source", "unknown")
    capture_event(user_id, "user_registered", props)
    identify_user(
        user_id,
        {
            "registration_source": props.get("registration_source"),
            "registration_date": props.get("registration_date", ""),
            "role": props.get("role", ""),
        },
    )
    logger.info("PostHog: user_registered | user=%s", user_id)


def track_email_verified(user_id: str) -> None:
    """邮箱/手机验证完成 — 激活关键节点"""
    capture_event(user_id, "email_verified")
    logger.info("PostHog: email_verified | user=%s", user_id)


def track_profile_completed(user_id: str, completion_pct: float = 0.0) -> None:
    """个人资料完善 — 激活里程碑"""
    capture_event(user_id, "profile_completed", {"completion_pct": completion_pct})
    if completion_pct >= 1.0:
        identify_user(user_id, {"profile_complete": True})
    logger.info("PostHog: profile_completed | user=%s | pct=%.0f%%", user_id, completion_pct * 100)


# =============================================================================
# 核心功能使用漏斗
# =============================================================================


def track_card_created(user_id: str, card_type: str = "digital") -> None:
    """创建数字名片 — 核心转化事件"""
    capture_event(
        user_id,
        "card_created",
        {
            "card_type": card_type,
        },
    )
    identify_user(user_id, {"has_card": True})
    logger.info("PostHog: card_created | user=%s | type=%s", user_id, card_type)


def track_card_shared(user_id: str, share_method: str = "wechat") -> None:
    """分享名片 — 病毒传播节点"""
    capture_event(
        user_id,
        "card_shared",
        {
            "share_method": share_method,
        },
    )
    logger.info("PostHog: card_shared | user=%s | method=%s", user_id, share_method)


def track_match_viewed(user_id: str, match_count: int = 0) -> None:
    """查看匹配结果 — 供需匹配参与"""
    capture_event(
        user_id,
        "match_viewed",
        {
            "match_count": match_count,
        },
    )
    logger.info("PostHog: match_viewed | user=%s | matches=%d", user_id, match_count)


def track_product_listed(user_id: str, product_category: str = "") -> None:
    """上架产品 — 供给方关键行为"""
    capture_event(
        user_id,
        "product_listed",
        {
            "category": product_category,
        },
    )
    identify_user(user_id, {"has_product": True})
    logger.info("PostHog: product_listed | user=%s | category=%s", user_id, product_category)


def track_search_performed(user_id: str, query: str = "", result_count: int = 0) -> None:
    """搜索行为 — 需求表达"""
    capture_event(
        user_id,
        "search_performed",
        {
            "query_length": len(query),
            "result_count": result_count,
        },
    )
    logger.info("PostHog: search_performed | user=%s | results=%d", user_id, result_count)


# =============================================================================
# 交易漏斗
# =============================================================================


def track_product_viewed(user_id: str, product_id: str, product_category: str = "") -> None:
    """浏览商品 — 交易漏斗第一层"""
    capture_event(
        user_id,
        "product_viewed",
        {
            "product_id": product_id,
            "category": product_category,
        },
    )
    logger.info("PostHog: product_viewed | user=%s | product=%s", user_id, product_id)


def track_added_to_cart(user_id: str, product_id: str, price: float = 0.0) -> None:
    """加入购物车 — 交易漏斗第二层"""
    capture_event(
        user_id,
        "added_to_cart",
        {
            "product_id": product_id,
            "price": price,
        },
    )
    logger.info("PostHog: added_to_cart | user=%s | product=%s", user_id, product_id)


def track_order_created(user_id: str, order_id: str, total_amount: float = 0.0) -> None:
    """创建订单 — 交易漏斗第三层"""
    capture_event(
        user_id,
        "order_created",
        {
            "order_id": order_id,
            "total_amount": total_amount,
        },
    )
    identify_user(user_id, {"has_purchased": True})
    logger.info("PostHog: order_created | user=%s | order=%s | ¥%.2f", user_id, order_id, total_amount)


def track_payment_completed(user_id: str, order_id: str, payment_method: str = "", amount: float = 0.0) -> None:
    """支付完成 — 交易漏斗第四层（最终转化）"""
    capture_event(
        user_id,
        "payment_completed",
        {
            "order_id": order_id,
            "payment_method": payment_method,
            "amount": amount,
        },
    )
    logger.info(
        "PostHog: payment_completed | user=%s | order=%s | method=%s | ¥%.2f", user_id, order_id, payment_method, amount
    )


# =============================================================================
# 留存与流失
# =============================================================================


def track_daily_active(user_id: str, session_duration_sec: float = 0.0) -> None:
    """日活标记 — 每天首次访问时触发"""
    capture_event(
        user_id,
        "daily_active",
        {
            "session_duration_sec": round(session_duration_sec, 1),
        },
    )


def track_feature_used(user_id: str, feature_name: str) -> None:
    """功能使用 — 功能级埋点"""
    capture_event(
        user_id,
        "feature_used",
        {
            "feature": feature_name,
        },
    )
    logger.info("PostHog: feature_used | user=%s | feature=%s", user_id, feature_name)


def track_invite_sent(user_id: str, invite_method: str = "wechat") -> None:
    """邀请好友 — 推荐传播"""
    capture_event(
        user_id,
        "invite_sent",
        {
            "invite_method": invite_method,
        },
    )
    logger.info("PostHog: invite_sent | user=%s | method=%s", user_id, invite_method)


def track_membership_upgraded(user_id: str, from_plan: str = "free", to_plan: str = "pro") -> None:
    """会员升级 — 付费转化"""
    capture_event(
        user_id,
        "membership_upgraded",
        {
            "from_plan": from_plan,
            "to_plan": to_plan,
        },
    )
    identify_user(user_id, {"plan": to_plan})
    logger.info("PostHog: membership_upgraded | user=%s | %s → %s", user_id, from_plan, to_plan)


def track_error_encountered(user_id: str, error_type: str, screen: str = "") -> None:
    """错误追踪 — 体验问题"""
    capture_event(
        user_id,
        "error_encountered",
        {
            "error_type": error_type,
            "screen": screen,
        },
    )
    logger.info("PostHog: error_encountered | user=%s | type=%s | screen=%s", user_id, error_type, screen)


# =============================================================================
# 漏斗查询辅助
# =============================================================================

FUNNEL_STEPS = {
    "registration": [
        "user_registered",  # 注册
        "email_verified",  # 验证
        "profile_completed",  # 完善资料
        "card_created",  # 创建名片
    ],
    "activation": [
        "user_registered",
        "card_created",
        "card_shared",  # 分享名片
        "match_viewed",  # 查看匹配
    ],
    "transaction": [
        "product_viewed",  # 浏览商品
        "added_to_cart",  # 加购
        "order_created",  # 下单
        "payment_completed",  # 支付
    ],
    "retention": [
        "daily_active",  # D1 日活
        "daily_active",  # D7 日活
        "daily_active",  # D30 日活
    ],
}


def is_funnel_active() -> bool:
    """检查漏斗追踪是否可用"""
    return is_posthog_active()
