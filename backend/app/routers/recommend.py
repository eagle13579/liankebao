"""个性化推荐路由"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Product, User, UserEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommend", tags=["recommend"])


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
