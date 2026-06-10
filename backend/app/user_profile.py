"""用户行为序列画像模块

从 UserEvent 读取最近 30 天用户行为，构建可序列化的行为画像供推荐系统使用。
"""

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Product, UserEvent

logger = logging.getLogger(__name__)

# 活跃时段分桶
_HOUR_BUCKETS = {
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 22),
    "night": (0, 6),
}


def _get_hour_bucket(hour: int) -> str:
    """将小时映射到时段名称"""
    for bucket, (start, end) in _HOUR_BUCKETS.items():
        if start <= hour < end:
            return bucket
    return "night"


def build_user_profile(db: Session, user_id: int, days: int = 30) -> dict:
    """构建用户行为序列画像

    Args:
        db: 数据库会话
        user_id: 用户ID
        days: 分析天数（默认30天）

    Returns:
        dict: 用户画像（JSON可序列化）
    """
    since = datetime.utcnow() - timedelta(days=days)

    # ================================================================
    # 1. 读取用户行为事件
    # ================================================================
    events = (
        db.query(UserEvent)
        .filter(
            UserEvent.user_id == user_id,
            UserEvent.created_at >= since,
        )
        .order_by(UserEvent.created_at.desc())
        .all()
    )

    if not events:
        return _empty_profile(user_id)

    # ================================================================
    # 2. 分类：按 event_type 分组
    # ================================================================
    view_events = [e for e in events if e.event_type in ("product_view", "product_click")]
    click_events = [e for e in events if e.event_type == "product_click"]
    search_events = [e for e in events if e.event_type == "search"]
    need_events = [e for e in events if e.event_type in ("need_view", "need_post")]

    # ================================================================
    # 3. 最近点击的 product category 分布
    # ================================================================
    target_product_ids = list(
        set(
            e.target_id
            for e in view_events
            if e.target_id is not None and e.target_type == "product"
        )
    )

    category_counter: Counter = Counter()
    brand_counter: Counter = Counter()
    tag_counter: Counter = Counter()
    price_list: list[float] = []

    if target_product_ids:
        products = (
            db.query(Product)
            .filter(
                Product.id.in_(target_product_ids),
                ~Product.is_deleted.is_(True),
            )
            .all()
        )
        for p in products:
            if p.category:
                category_counter[p.category] += 1
            if p.brand:
                brand_counter[p.brand] += 1
            if p.tags:
                for tag in p.tags.split(","):
                    tag = tag.strip()
                    if tag:
                        tag_counter[tag] += 1
            # 价格偏好：取 price 或 sale_price 的均值
            p_price = p.sale_price if p.sale_price else p.price
            if p_price > 0:
                price_list.append(p_price)

    # ================================================================
    # 4. 最近搜索关键词
    # ================================================================
    recent_keywords = [
        e.search_keyword
        for e in search_events
        if e.search_keyword
    ]
    # 去重保留顺序
    seen_keywords = set()
    unique_keywords = []
    for kw in recent_keywords:
        kw_lower = kw.lower().strip()
        if kw_lower and kw_lower not in seen_keywords:
            seen_keywords.add(kw_lower)
            unique_keywords.append(kw.strip())

    # ================================================================
    # 5. 点击/浏览比例
    # ================================================================
    total_views = len(view_events)
    total_clicks = len(click_events)
    view_click_ratio = round(total_clicks / total_views, 4) if total_views > 0 else 0.0

    # ================================================================
    # 6. 活跃时段分布
    # ================================================================
    hour_bucket_counter: Counter = Counter()
    for e in events:
        bucket = _get_hour_bucket(e.created_at.hour)
        hour_bucket_counter[bucket] += 1

    # ================================================================
    # 7. 价格偏好
    # ================================================================
    price_preference = {
        "avg_price": round(sum(price_list) / len(price_list), 2) if price_list else 0,
        "min_price": round(min(price_list), 2) if price_list else 0,
        "max_price": round(max(price_list), 2) if price_list else 0,
        "sample_count": len(price_list),
    }

    # ================================================================
    # 8. 活跃天数
    # ================================================================
    active_dates = set(e.created_at.date() for e in events)
    days_active = len(active_dates)

    # ================================================================
    # 9. 事件类型统计
    # ================================================================
    event_type_counter: Counter = Counter(e.event_type for e in events)

    # ================================================================
    # 组装画像
    # ================================================================
    profile = {
        "user_id": user_id,
        "days_analyzed": days,
        "total_events": len(events),
        "days_active": days_active,
        "summary": {
            "total_views": total_views,
            "total_clicks": total_clicks,
            "total_searches": len(search_events),
            "total_needs_interacted": len(need_events),
            "view_click_ratio": view_click_ratio,
        },
        "category_distribution": dict(category_counter.most_common(10)),
        "brand_distribution": dict(brand_counter.most_common(10)),
        "tag_distribution": dict(tag_counter.most_common(15)),
        "recent_keywords": unique_keywords[:20],
        "active_hours": {
            bucket: hour_bucket_counter.get(bucket, 0)
            for bucket in ["morning", "afternoon", "evening", "night"]
        },
        "price_preference": price_preference,
        "event_type_breakdown": dict(event_type_counter),
        "top_category": category_counter.most_common(1)[0][0] if category_counter else None,
        "top_category_score": round(category_counter.most_common(1)[0][1] / max(total_views, 1), 4)
        if category_counter
        else 0,
    }

    return profile


def _empty_profile(user_id: int) -> dict:
    """返回空画像（无行为数据时）"""
    return {
        "user_id": user_id,
        "days_analyzed": 30,
        "total_events": 0,
        "days_active": 0,
        "summary": {
            "total_views": 0,
            "total_clicks": 0,
            "total_searches": 0,
            "total_needs_interacted": 0,
            "view_click_ratio": 0.0,
        },
        "category_distribution": {},
        "brand_distribution": {},
        "tag_distribution": {},
        "recent_keywords": [],
        "active_hours": {"morning": 0, "afternoon": 0, "evening": 0, "night": 0},
        "price_preference": {"avg_price": 0, "min_price": 0, "max_price": 0, "sample_count": 0},
        "event_type_breakdown": {},
        "top_category": None,
        "top_category_score": 0,
    }
