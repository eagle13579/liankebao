"""
搜索路由 — 增强版

集成了增强搜索引擎 (search_index.py)，支持:
- FTS5/SQLite 全文搜索 或 内存倒排索引（自动切换）
- jieba 中文分词
- 多字段搜索（产品名+描述+标签+品牌+分类）
- 排序（相关性/价格/时间）
- 分页
- 搜索结果高亮
- 搜索建议/补全
- 分类列表
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import Product
from app.schemas import ApiResponse, ProductResponse
from app.search_index import get_search_engine, highlight_title, highlight_text

router = APIRouter(prefix="/api/search", tags=["搜索"])

# 有效排序方式
VALID_SORT_OPTIONS = ["relevance", "price_asc", "price_desc", "newest"]


@router.get("", response_model=ApiResponse)
def search_products(
    q: str = Query("", description="搜索关键词（产品名称/描述/标签/品牌）"),
    category: str = Query(None, description="分类筛选（精确匹配）"),
    region: str = Query(None, description="地区筛选（匹配规格中的产地）"),
    min_price: float = Query(None, ge=0, description="最低价格"),
    max_price: float = Query(None, ge=0, description="最高价格"),
    sort_by: str = Query(
        "relevance",
        description="排序方式: relevance(相关性) / price_asc(价格升序) / price_desc(价格降序) / newest(最新)",
    ),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    highlight: bool = Query(True, description="是否返回高亮片段"),
    db: Session = Depends(get_db),
):
    """
    产品搜索

    支持多维度筛选、全文搜索和中英文混合搜索。已上架 (approved) 产品可见。

    参数说明:
    - q: 搜索关键词，匹配产品名称、描述、标签、品牌（无需完整匹配，智能分词）
    - category: 按分类精确筛选
    - region: 按产地/地区筛选（模糊匹配规格JSON中的"产地"字段）
    - min_price / max_price: 价格区间筛选
    - sort_by: 排序方式
      - relevance（默认）: 按文本相关性降序
      - price_asc: 按价格升序（同价按相关性）
      - price_desc: 按价格降序（同价按相关性）
      - newest: 按创建时间降序（最新优先）
    - page / page_size: 分页
    - highlight: 是否返回高亮片段
    """
    # 校验排序参数
    if sort_by not in VALID_SORT_OPTIONS:
        sort_by = "relevance"

    # 如果没有搜索词但有筛选条件，使用传统 SQL 方式（更高效）
    if not q or not q.strip():
        return _search_with_sql(
            db=db,
            category=category,
            region=region,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )

    # 有搜索词 → 使用搜索引擎
    try:
        engine = get_search_engine()

        # 构建过滤器
        filters = {}
        if category and category.strip():
            filters["category"] = category.strip()
        if region and region.strip():
            filters["region"] = region.strip()
        if min_price is not None:
            filters["min_price"] = min_price
        if max_price is not None:
            filters["max_price"] = max_price

        # 搜索引擎查询
        result = engine.search(
            query=q.strip(),
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            filters=filters,
        )

        # 如果没有结果，回退到 SQL LIKE 搜索（模糊匹配更宽松）
        if not result["items"]:
            return _search_with_sql(
                db=db,
                q=q,
                category=category,
                region=region,
                min_price=min_price,
                max_price=max_price,
                sort_by=sort_by,
                page=page,
                page_size=page_size,
            )

        # 对于非 SQL 引擎的搜索结果，需要从数据库补充完整信息
        result_items = result["items"]
        product_ids = [item["id"] for item in result_items]
        products_map = {
            p.id: p
            for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
        }

        items = []
        for item in result_items:
            pid = item["id"]
            p = products_map.get(pid)
            if p:
                # 使用搜索引擎的高亮，但用数据库的完整数据
                item_data = ProductResponse.model_validate(p).model_dump()
                # 注入高亮字段
                if highlight:
                    item_data["highlight_title"] = item.get(
                        "highlight_title",
                        highlight_title(p.name or "", q),
                    )
                    item_data["highlight_content"] = item.get(
                        "highlight_content",
                        highlight_text(p.description or "", q, max_length=200),
                    )
                else:
                    item_data["highlight_title"] = p.name
                    item_data["highlight_content"] = (p.description or "")[:200]
                # 注入搜索分数
                item_data["_score"] = item.get("score", 0.0)
                items.append(item_data)

        return ApiResponse(
            code=200,
            message="success",
            data={
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "query": result["query"],
                "items": items,
            },
        )

    except Exception as e:
        logger.error(f"搜索引擎查询失败: {e}，回退到 SQL 方式", exc_info=True)
        return _search_with_sql(
            db=db,
            q=q,
            category=category,
            region=region,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )


def _search_with_sql(
    db: Session,
    q: str = "",
    category: Optional[str] = None,
    region: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: str = "relevance",
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse:
    """SQL 回退搜索 — 使用 LIKE 模糊匹配（兼容原有逻辑）

    当搜索引擎不可用或没有结果时自动回退到此方式。
    """
    # 基础查询：只查询已上架产品
    query = db.query(Product).filter(Product.status == "approved")

    # === 模糊搜索：名称 + 描述 + 标签 + 品牌 ===
    if q and q.strip():
        like_pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Product.name.like(like_pattern),
                Product.description.like(like_pattern),
                Product.tags.like(like_pattern),
                Product.brand.like(like_pattern),
            )
        )

    # === 分类筛选 ===
    if category and category.strip():
        query = query.filter(Product.category == category.strip())

    # === 地区筛选（从 specs JSON 中匹配 "产地" 字段） ===
    if region and region.strip():
        region_pattern = f"%{region.strip()}%"
        query = query.filter(Product.specs.like(region_pattern))

    # === 价格区间筛选 ===
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    # === 统计总数 ===
    total = query.count()

    # === 排序 ===
    if sort_by == "price_asc":
        order_clause = [Product.price.asc(), desc(Product.sort_order), desc(Product.created_at)]
    elif sort_by == "price_desc":
        order_clause = [Product.price.desc(), desc(Product.sort_order), desc(Product.created_at)]
    elif sort_by == "newest":
        order_clause = [desc(Product.created_at), desc(Product.sort_order)]
    else:  # relevance (default)
        order_clause = [desc(Product.sort_order), desc(Product.created_at)]

    # === 分页 ===
    products = (
        query.order_by(*order_clause)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for p in products:
        item = ProductResponse.model_validate(p).model_dump()
        if q and q.strip():
            item["highlight_title"] = highlight_title(p.name or "", q)
            item["highlight_content"] = highlight_text(p.description or "", q, max_length=200)
        else:
            item["highlight_title"] = p.name
            item["highlight_content"] = (p.description or "")[:200]
        items.append(item)

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "query": q,
            "items": items,
        },
    )


@router.get("/categories", response_model=ApiResponse)
def list_search_categories(db: Session = Depends(get_db)):
    """获取所有产品分类列表（去重，仅已上架产品）"""
    categories = (
        db.query(Product.category)
        .filter(
            Product.status == "approved",
            Product.category.isnot(None),
            Product.category != "",
        )
        .distinct()
        .order_by(Product.category)
        .all()
    )

    return ApiResponse(
        code=200,
        message="success",
        data={
            "categories": [c[0] for c in categories],
        },
    )


@router.get("/suggestions", response_model=ApiResponse)
def search_suggestions(
    q: str = Query("", description="输入前缀"),
    limit: int = Query(10, ge=1, le=50, description="最大返回数"),
    db: Session = Depends(get_db),
):
    """搜索建议（前缀补全），用于搜索框下拉提示

    优先使用搜索引擎的建议功能，回退到数据库 LIKE 查询。
    """
    if not q or not q.strip():
        return ApiResponse(code=200, message="success", data={"suggestions": []})

    try:
        engine = get_search_engine()
        suggestions = engine.suggest(prefix=q.strip(), limit=limit)

        if suggestions:
            return ApiResponse(
                code=200,
                message="success",
                data={"suggestions": suggestions},
            )
    except Exception as e:
        logger.warning(f"搜索引擎 suggest 失败，回退到 DB: {e}")

    # 回退：数据库模糊查询
    like_pattern = f"%{q.strip()}%"
    products = (
        db.query(Product.name)
        .filter(
            Product.status == "approved",
            Product.name.like(like_pattern),
        )
        .distinct()
        .limit(limit)
        .all()
    )

    suggestions = [p[0] for p in products]

    return ApiResponse(
        code=200,
        message="success",
        data={"suggestions": suggestions},
    )


@router.get("/rebuild", response_model=ApiResponse)
def rebuild_search_index_endpoint(db: Session = Depends(get_db)):
    """手动触发搜索引擎重建（管理接口）"""
    try:
        from app.search_index import rebuild_search_index
        count = rebuild_search_index(db_session=db)
        return ApiResponse(
            code=200,
            message="success",
            data={
                "indexed_count": count,
                "message": f"搜索引擎重建完成，共索引 {count} 个文档",
            },
        )
    except Exception as e:
        logger.error(f"搜索引擎重建失败: {e}", exc_info=True)
        return ApiResponse(
            code=500,
            message=f"搜索引擎重建失败: {e}",
        )


@router.get("/stats", response_model=ApiResponse)
def search_engine_stats():
    """获取搜索引擎状态和统计"""
    try:
        engine = get_search_engine()
        return ApiResponse(
            code=200,
            message="success",
            data=engine.stats,
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"获取搜索引擎状态失败: {e}",
        )
