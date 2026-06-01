"""个性化推荐路由"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Product, User, UserEvent

logger = logging.getLogger(__name__)

# ============================================================
# LLM 理由缓存（内存 dict，TTL 30 分钟）
# ============================================================

_AI_REASON_CACHE: dict[str, tuple[str, datetime]] = {}
_AI_REASON_CACHE_TTL = timedelta(minutes=30)


def _make_cache_key(product_id: int, need_id: int) -> str:
    return f"{product_id}:{need_id}"


def _get_cached_reason(product_id: int, need_id: int) -> Optional[str]:
    """从缓存中获取 AI 理由，过期条目自动失效"""
    key = _make_cache_key(product_id, need_id)
    entry = _AI_REASON_CACHE.get(key)
    if entry is None:
        return None
    reason, expire_at = entry
    if datetime.utcnow() > expire_at:
        del _AI_REASON_CACHE[key]
        return None
    return reason


def _set_cached_reason(product_id: int, need_id: int, reason: str) -> None:
    """将 AI 理由写入缓存，TTL 30 分钟"""
    key = _make_cache_key(product_id, need_id)
    _AI_REASON_CACHE[key] = (reason, datetime.utcnow() + _AI_REASON_CACHE_TTL)


def _evict_expired_cache() -> int:
    """清理过期缓存条目，返回清理数量（可定期调用）"""
    now = datetime.utcnow()
    expired_keys = [k for k, (_, exp) in _AI_REASON_CACHE.items() if now > exp]
    for k in expired_keys:
        del _AI_REASON_CACHE[k]
    return len(expired_keys)

router = APIRouter(prefix="/api/recommend", tags=["recommend"])
recommend_router = router  # 显式别名，满足外部引用约定


@router.get(
    "/products", summary="个性化产品推荐", description="根据用户行为推荐产品（有行为→同类推荐，无行为→热门推荐）"
)
def recommend_products(
    user_id: int = Query(None, description="用户ID（可选，未登录时返回热门）"),
    limit: int = Query(8, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """个性化推荐产品

    算法逻辑：
    1. 如果用户有行为记录 → 按用户最近浏览的产品的分类+标签推荐同类产品
    2. 如果用户无行为或新用户 → 按热门产品排序（按浏览量）
    """
    if user_id:
        # 尝试基于用户行为做个性化推荐
        personalized = _recommend_by_user_behavior(db, user_id, limit)
        if personalized:
            return {
                "code": 200,
                "message": "success",
                "data": {"items": personalized, "total": len(personalized), "strategy": "personalized"},
            }

    # 兜底：热门推荐
    hot_products = _recommend_hot_products(db, limit)

    return {
        "code": 200,
        "message": "success",
        "data": {"items": hot_products, "total": len(hot_products), "strategy": "hot"},
    }


def _recommend_by_user_behavior(db: Session, user_id: int, limit: int) -> list:
    """基于用户行为进行个性化推荐"""
    # 1. 获取用户最近浏览/点击的产品ID（最近30天）
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    recent_product_ids = (
        db.query(UserEvent.target_id)
        .filter(
            UserEvent.user_id == user_id,
            UserEvent.event_type.in_(["product_view", "product_click"]),
            UserEvent.target_id.isnot(None),
            UserEvent.created_at >= thirty_days_ago,
        )
        .order_by(UserEvent.created_at.desc())
        .limit(10)
        .all()
    )
    recent_product_ids = [r[0] for r in recent_product_ids]

    if not recent_product_ids:
        # 尝试找搜索事件来推断兴趣
        recent_searches = (
            db.query(UserEvent.search_keyword)
            .filter(
                UserEvent.user_id == user_id,
                UserEvent.event_type == "search",
                UserEvent.search_keyword.isnot(None),
                UserEvent.created_at >= thirty_days_ago,
            )
            .order_by(UserEvent.created_at.desc())
            .limit(5)
            .all()
        )
        if not recent_searches:
            return []

        # 按搜索关键词模糊匹配产品
        keywords = [r[0] for r in recent_searches]
        conditions = []
        for kw in keywords:
            conditions.append(Product.name.ilike(f"%{kw}%"))
            conditions.append(Product.tags.ilike(f"%{kw}%"))
            conditions.append(Product.category.ilike(f"%{kw}%"))

        if conditions:
            candidate_products = (
                db.query(Product)
                .filter(
                    ~Product.is_deleted.is_(True),
                    Product.status == "approved",
                    or_(*conditions),
                )
                .order_by(Product.sort_order.desc(), Product.created_at.desc())
                .limit(limit)
                .all()
            )
            return [_product_to_dict(p) for p in candidate_products]

        return []

    # 2. 获取这些产品的分类和标签
    recent_products = (
        db.query(Product)
        .filter(
            Product.id.in_(recent_product_ids),
            ~Product.is_deleted.is_(True),
        )
        .all()
    )

    # 收集分类和标签
    categories = set()
    tags_set = set()
    for p in recent_products:
        if p.category:
            categories.add(p.category)
        if p.tags:
            for tag in p.tags.split(","):
                tag = tag.strip()
                if tag:
                    tags_set.add(tag)

    # 3. 查找同类产品（排除已看过的）
    conditions = [~Product.is_deleted.is_(True), Product.status == "approved"]
    category_tag_conditions = []
    if categories:
        category_tag_conditions.append(Product.category.in_(list(categories)))
    if tags_set:
        tag_conditions = [Product.tags.ilike(f"%{tag}%") for tag in tags_set]
        category_tag_conditions.append(or_(*tag_conditions))
    # 使用 OR 逻辑：分类匹配 或 标签匹配
    if category_tag_conditions:
        conditions.append(or_(*category_tag_conditions))

    candidate_products = (
        db.query(Product)
        .filter(
            *conditions,
            ~Product.id.in_(recent_product_ids),  # 排除已看过的
        )
        .order_by(Product.sort_order.desc(), Product.created_at.desc())
        .limit(limit)
        .all()
    )

    # 如果不够，再从相同分类补充
    if len(candidate_products) < limit and categories:
        existing_ids = [p.id for p in candidate_products] + recent_product_ids
        additional = (
            db.query(Product)
            .filter(
                ~Product.is_deleted.is_(True),
                Product.status == "approved",
                Product.category.in_(list(categories)),
                ~Product.id.in_(existing_ids),
            )
            .order_by(Product.sort_order.desc(), Product.created_at.desc())
            .limit(limit - len(candidate_products))
            .all()
        )
        candidate_products.extend(additional)

    return [_product_to_dict(p) for p in candidate_products]


def _recommend_hot_products(db: Session, limit: int) -> list:
    """热门产品推荐"""
    # 统计过去7天浏览最多的产品
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    hot_product_ids_query = (
        db.query(
            UserEvent.target_id,
            func.count(UserEvent.id).label("view_count"),
        )
        .filter(
            UserEvent.event_type.in_(["product_view", "product_click"]),
            UserEvent.target_id.isnot(None),
            UserEvent.created_at >= seven_days_ago,
        )
        .group_by(UserEvent.target_id)
        .order_by(func.count(UserEvent.id).desc())
        .limit(limit)
        .subquery()
    )

    hot_products = (
        db.query(Product)
        .join(
            hot_product_ids_query,
            Product.id == hot_product_ids_query.c.target_id,
        )
        .filter(~Product.is_deleted.is_(True), Product.status == "approved")
        .order_by(hot_product_ids_query.c.view_count.desc())
        .limit(limit)
        .all()
    )

    # 如果没有热门数据, 按上架时间+排序权重取最新产品
    if not hot_products:
        hot_products = (
            db.query(Product)
            .filter(
                ~Product.is_deleted.is_(True),
                Product.status == "approved",
            )
            .order_by(Product.sort_order.desc(), Product.created_at.desc())
            .limit(limit)
            .all()
        )

    return [_product_to_dict(p) for p in hot_products]


def _product_to_dict(product: Product) -> dict:
    """将Product模型转为字典"""
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "earn_per_share": product.earn_per_share,
        "category": product.category,
        "stock": product.stock,
        "images": product.images,
        "status": product.status,
        "owner_id": product.owner_id,
        "brand": product.brand,
        "sale_price": product.sale_price,
        "tags": product.tags,
        "is_featured": product.is_featured,
        "sort_order": product.sort_order,
        "created_at": product.created_at.isoformat() if product.created_at else None,
    }


# ============================================================
# 新增路由：按用户ID推荐产品
# ============================================================


@router.get(
    "/products/{user_id}",
    summary="按用户ID推荐产品",
    description="基于用户浏览/偏好行为推荐产品，无行为时返回热门产品",
)
def recommend_products_by_user(
    user_id: int = Path(..., description="用户ID"),
    limit: int = Query(8, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """按用户ID推荐产品"""
    personalized = _recommend_by_user_behavior(db, user_id, limit)
    if personalized:
        return {
            "code": 200,
            "message": "success",
            "data": {"items": personalized, "total": len(personalized), "strategy": "personalized"},
        }
    hot_products = _recommend_hot_products(db, limit)
    return {
        "code": 200,
        "message": "success",
        "data": {"items": hot_products, "total": len(hot_products), "strategy": "hot"},
    }


# ============================================================
# 新增路由：热门产品推荐
# ============================================================


@router.get(
    "/hot",
    summary="热门产品推荐",
    description="返回过去7天浏览最多的产品列表，无数据时按上架时间返回",
)
def recommend_hot(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """热门产品推荐"""
    items = _recommend_hot_products(db, limit)
    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": len(items)},
    }


# ============================================================
# 新增路由：个性化推荐（结合 matching_engine）
# ============================================================


@router.get(
    "/personalized/{user_id}",
    summary="个性化推荐（结合匹配引擎 + LLM）",
    description="基于用户画像与 matching_engine 进行个性化供需匹配推荐，由 LLM 生成智能匹配理由",
)
def recommend_personalized(
    user_id: int = Path(..., description="用户ID"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """个性化推荐 — 使用 matching_engine 做协同过滤 + LLM 生成匹配理由"""
    try:
        from matching_engine import MatchEngine

        engine = MatchEngine(db)
        # 获取用户发布的需求（如果有），反向匹配产品
        user_needs = (
            db.query(UserEvent)
            .filter(
                UserEvent.user_id == user_id,
                UserEvent.event_type.in_(["need_view", "need_post"]),
                UserEvent.target_id.isnot(None),
            )
            .order_by(UserEvent.created_at.desc())
            .limit(5)
            .all()
        )
        need_ids = [e.target_id for e in user_needs if e.target_id]

        all_items = []
        seen_ids = set()

        if need_ids:
            for nid in need_ids[:3]:  # 最多取3个需求做匹配
                matches = engine.match_needs_to_products(nid)
                # 获取原始需求数据用于 LLM
                need_data = None
                try:
                    from app.models import Need

                    need_obj = db.query(Need).filter(Need.id == nid).first()
                    if need_obj:
                        need_data = {
                            "title": getattr(need_obj, "title", ""),
                            "description": getattr(need_obj, "description", ""),
                            "category": getattr(need_obj, "category", ""),
                        }
                except Exception:
                    pass

                for m in matches:
                    if m.id not in seen_ids:
                        # 尝试用 LLM 生成匹配理由（优先走缓存）
                        llm_reason = None
                        if need_data and hasattr(m, "title"):
                            # 1) 查缓存
                            llm_reason = _get_cached_reason(m.id, nid)
                            if llm_reason is None:
                                # 2) 缓存未命中 => 调用 LLM
                                try:
                                    from app.services.llm_service import generate_matching_reason

                                    product_data = {
                                        "name": getattr(m, "title", "") or getattr(m, "name", ""),
                                        "description": getattr(m, "description", ""),
                                        "category": getattr(m, "category", ""),
                                        "tags": getattr(m, "tags", ""),
                                        "price": getattr(m, "price", 0),
                                    }
                                    llm_reason = generate_matching_reason(product_data, need_data)
                                    if llm_reason:
                                        # 3) 写入缓存
                                        _set_cached_reason(m.id, nid, llm_reason)
                                except Exception:
                                    logger.debug("LLM 匹配理由生成失败，使用规则引擎理由")

                        all_items.append(
                            {
                                "id": m.id,
                                "title": m.title,
                                "match_score": m.match_score,
                                "match_reasons": m.match_reasons,
                                "llm_reason": llm_reason,  # AI 生成的理由（缓存或实时）
                                "strategy": m.strategy,
                            }
                        )
                        seen_ids.add(m.id)

        if not all_items:
            # 兜底：热门产品
            hot = _recommend_hot_products(db, limit)
            all_items = [
                {
                    "id": p["id"],
                    "title": p["name"],
                    "match_score": 0.5,
                    "match_reasons": ["热门推荐"],
                    "llm_reason": None,
                    "strategy": "hot",
                }
                for p in hot
            ]

        return {
            "code": 200,
            "message": "success",
            "data": {"items": all_items[:limit], "total": len(all_items[:limit])},
        }
    except ImportError:
        logger.warning("matching_engine 不可用，降级为行为推荐")
        return recommend_products_by_user(user_id, limit, db)


# ============================================================
# 新增路由：推荐反馈
# ============================================================


class FeedbackRequest(BaseModel):
    """推荐反馈请求模型"""

    user_id: int
    product_id: int
    action: str  # "like" 或 "dislike"
    source: str = "recommend"  # 推荐来源标识


@router.post(
    "/feedback",
    summary="记录推荐反馈",
    description="用户对推荐结果的反馈（喜欢/不喜欢），用于后续优化推荐质量。高价值反馈（like/click/adopt）同步至匹配引擎影响评分",
)
def record_feedback(
    feedback: FeedbackRequest,
    db: Session = Depends(get_db),
):
    """记录推荐反馈"""
    if feedback.action not in ("like", "dislike"):
        raise HTTPException(status_code=422, detail="action 必须为 'like' 或 'dislike'")

    product = db.query(Product).filter(Product.id == feedback.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 记录为 UserEvent
    event = UserEvent(
        user_id=feedback.user_id,
        event_type=f"recommend_{feedback.action}",
        target_type="product",
        target_id=feedback.product_id,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.commit()

    logger.info(
        "recommend_feedback",
        extra={
            "user_id": feedback.user_id,
            "product_id": feedback.product_id,
            "action": feedback.action,
            "source": feedback.source,
        },
    )

    # 高价值反馈同步到匹配引擎，影响后续匹配评分
    try:
        from matching_engine import MatchEngine

        MatchEngine.record_feedback(feedback.product_id, feedback.action)
        logger.debug(
            "feedback_synced_to_matching_engine",
            extra={
                "product_id": feedback.product_id,
                "action": feedback.action,
            },
        )
    except ImportError:
        logger.warning("matching_engine 不可用，反馈仅记录到 UserEvent")
    except Exception as e:
        logger.error(f"同步反馈到匹配引擎失败: {e}")

    return {
        "code": 200,
        "message": "反馈已记录",
        "data": {"action": feedback.action, "product_id": feedback.product_id},
    }


# ============================================================
# 首页推荐功能排序（基于用户核心痛点）
# ============================================================

_PAIN_POINT_FEATURES = {
    "low_acquisition_cost": [
        {"id": "product-pool", "label": "产品池", "desc": "精选优质货源", "priority": 1},
        {"id": "promotion-center", "label": "推广中心", "desc": "赚取高额分润", "priority": 2},
        {"id": "supply-demand", "label": "信任对接", "desc": "精准匹配可信商机", "priority": 3},
        {"id": "contacts", "label": "人脉管理", "desc": "高效触达客户", "priority": 4},
        {"id": "my-orders", "label": "我的订单", "desc": "订单物流追踪", "priority": 5},
        {"id": "data", "label": "数据洞察", "desc": "生意增长分析", "priority": 6},
    ],
    "lack_trust": [
        {"id": "supply-demand", "label": "信任对接", "desc": "精准匹配可信商机", "priority": 1},
        {"id": "contacts", "label": "人脉管理", "desc": "高效触达客户", "priority": 2},
        {"id": "product-pool", "label": "产品池", "desc": "精选优质货源", "priority": 3},
        {"id": "promotion-center", "label": "推广中心", "desc": "赚取高额分润", "priority": 4},
        {"id": "my-orders", "label": "我的订单", "desc": "订单物流追踪", "priority": 5},
        {"id": "data", "label": "数据洞察", "desc": "生意增长分析", "priority": 6},
    ],
    "distribution_pain": [
        {"id": "promotion-center", "label": "推广中心", "desc": "赚取高额分润", "priority": 1},
        {"id": "product-pool", "label": "产品池", "desc": "精选优质货源", "priority": 2},
        {"id": "my-orders", "label": "我的订单", "desc": "订单物流追踪", "priority": 3},
        {"id": "contacts", "label": "人脉管理", "desc": "高效触达客户", "priority": 4},
        {"id": "supply-demand", "label": "信任对接", "desc": "精准匹配可信商机", "priority": 5},
        {"id": "data", "label": "数据洞察", "desc": "生意增长分析", "priority": 6},
    ],
}

_DEFAULT_FEATURES = [
    {"id": "product-pool", "label": "产品池", "desc": "精选优质货源", "priority": 1},
    {"id": "promotion-center", "label": "推广中心", "desc": "赚取高额分润", "priority": 2},
    {"id": "contacts", "label": "人脉管理", "desc": "高效触达客户", "priority": 3},
    {"id": "my-orders", "label": "我的订单", "desc": "订单物流追踪", "priority": 4},
    {"id": "supply-demand", "label": "信任对接", "desc": "精准匹配可信商机", "priority": 5},
    {"id": "data", "label": "数据洞察", "desc": "生意增长分析", "priority": 6},
]


@router.get(
    "/features",
    summary="首页功能推荐排序",
    description="根据用户注册时选择的核心痛点，返回首页功能的推荐排序列表。未选择痛点的用户返回默认顺序。",
)
def recommend_features(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据用户核心痛点返回首页功能入口的推荐排序"""
    pain_point = current_user.onboarding_pain_point

    if pain_point and pain_point in _PAIN_POINT_FEATURES:
        features = _PAIN_POINT_FEATURES[pain_point]
    else:
        features = _DEFAULT_FEATURES

    return {
        "code": 200,
        "message": "success",
        "data": {
            "features": features,
            "pain_point": pain_point,
        },
    }
