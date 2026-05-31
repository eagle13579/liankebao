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

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ===== OpenTelemetry 自定义追踪 =====
from app.database import get_db
from app.models import Enterprise, Product
from app.schemas import ApiResponse, ProductResponse
from app.search_index import get_search_engine, highlight_text, highlight_title
from app.telemetry import tracer

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
    """
    # 初始化搜索 span
    _search_span = None
    try:
        _search_span = tracer.start_as_current_span("search.products")
        _search_span.__enter__()
        _search_span.set_attribute("query", q or "")
        _search_span.set_attribute("category", category or "")
        _search_span.set_attribute("region", region or "")
        _search_span.set_attribute("sort_by", sort_by)
        _search_span.set_attribute("page", page)
        _search_span.set_attribute("page_size", page_size)
    except Exception:
        _search_span = None

    try:
        # 校验排序参数
        if sort_by not in VALID_SORT_OPTIONS:
            sort_by = "relevance"

        # 如果没有搜索词但有筛选条件，使用传统 SQL 方式（更高效）
        if not q or not q.strip():
            result = _search_with_sql(
                db=db,
                category=category,
                region=region,
                min_price=min_price,
                max_price=max_price,
                sort_by=sort_by,
                page=page,
                page_size=page_size,
            )
            if _search_span:
                _search_span.set_attribute("search_mode", "sql_fallback")
            return result

        # 有搜索词 → 使用搜索引擎
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
            if _search_span:
                _search_span.set_attribute("search_mode", "engine_empty_fallback")
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
            for p in db.query(Product)
            .filter(
                Product.id.in_(product_ids),
                Product.is_deleted == False,
            )
            .all()
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

        if _search_span:
            _search_span.set_attribute("search_mode", "engine")
            _search_span.set_attribute("result_count", len(items))
            _search_span.set_attribute("total_results", result["total"])

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
        if _search_span:
            _search_span.set_attribute("error", str(e))
            _search_span.set_attribute("search_mode", "error_fallback")
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
    finally:
        if _search_span:
            try:
                _search_span.__exit__(None, None, None)
            except Exception:
                pass


def _search_with_sql(
    db: Session,
    q: str = "",
    category: str | None = None,
    region: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort_by: str = "relevance",
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse:
    """SQL 回退搜索 — 使用 LIKE 模糊匹配（兼容原有逻辑）

    当搜索引擎不可用或没有结果时自动回退到此方式。
    """
    # 基础查询：只查询已上架产品且未删除
    query = db.query(Product).filter(
        Product.status == "approved",
        Product.is_deleted == False,
    )

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
    products = query.order_by(*order_clause).offset((page - 1) * page_size).limit(page_size).all()

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
            Product.is_deleted == False,
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
            Product.is_deleted == False,
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


# ======================================================================
# 向量搜索 + 重排序路由（可选，USE_VECTOR_SEARCH=1 时启用）
# ======================================================================


@router.get("/vector", response_model=ApiResponse)
def vector_search(
    q: str = Query("", description="搜索关键词"),
    top_k: int = Query(20, ge=1, le=100, description="返回结果数量"),
    db: Session = Depends(get_db),
):
    """向量语义搜索（需 USE_VECTOR_SEARCH=1）

    使用 embedding 向量进行语义匹配，不再依赖关键词字面匹配。
    返回结果按语义相似度降序排列。
    """
    if not q or not q.strip():
        return ApiResponse(code=200, message="success", data={"items": [], "total": 0})

    try:
        from app.vector_search import (
            USE_VECTOR_SEARCH,
            build_document_text,
            get_vector_index,
        )

        if not USE_VECTOR_SEARCH:
            return ApiResponse(
                code=400,
                message="向量搜索未启用（请设置 USE_VECTOR_SEARCH=1）",
            )

        # 从数据库加载产品到向量索引
        from app.models import Product

        vindex = get_vector_index()

        # 如果索引为空，重建
        if vindex.size == 0:
            products = (
                db.query(Product)
                .filter(
                    Product.status == "approved",
                    Product.is_deleted == False,
                )
                .all()
            )
            for p in products:
                region = ""
                if p.specs:
                    try:
                        specs = json.loads(p.specs)
                        region = specs.get("产地", specs.get("产地/发货地", ""))
                    except (json.JSONDecodeError, TypeError):
                        pass
                text = build_document_text(
                    title=p.name or "",
                    content=p.description or "",
                    category=p.category or "",
                    tags=p.tags or "",
                    brand=p.brand or "",
                )
                vindex.add_document(
                    doc_id=p.id,
                    text=text,
                    metadata={
                        "region": region,
                        "price": p.price or 0.0,
                        "category": p.category or "",
                    },
                )
            logger.info(f"向量搜索索引重建完成: {vindex.size} 个文档")

        # 向量搜索
        results = vindex.search(query=q, top_k=top_k)

        # 从数据库补充完整信息
        product_ids = [r["id"] for r in results]
        products_map = {
            p.id: p
            for p in db.query(Product)
            .filter(
                Product.id.in_(product_ids),
                Product.is_deleted == False,
            )
            .all()
        }

        items = []
        for r in results:
            p = products_map.get(r["id"])
            if p:
                item = ProductResponse.model_validate(p).model_dump()
                item["_vector_score"] = r["score"]
                item["_search_type"] = "vector"
                items.append(item)

        return ApiResponse(
            code=200,
            message="success",
            data={
                "total": len(items),
                "items": items,
                "query": q,
                "engine": "vector",
                "provider": getattr(vindex.stats, "provider", "numpy"),
            },
        )

    except Exception as e:
        logger.error(f"向量搜索失败: {e}", exc_info=True)
        return ApiResponse(code=500, message=f"向量搜索失败: {e}")


@router.get("/rerank", response_model=ApiResponse)
def rerank_search(
    q: str = Query("", description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """BM25 + 向量重排序混合搜索（需 USE_VECTOR_SEARCH=1）

    先用 BM25 做初步召回，再用向量相似度对结果重排序。
    比纯 BM25 更准确，比纯向量搜索更可靠（避免遗漏精确匹配）。
    """
    if not q or not q.strip():
        return ApiResponse(code=200, message="success", data={"items": [], "total": 0})

    try:
        from app.search_index import get_search_engine, highlight_text, highlight_title
        from app.vector_search import USE_VECTOR_SEARCH
        from app.vector_search import rerank as vector_rerank

        if not USE_VECTOR_SEARCH:
            return ApiResponse(
                code=400,
                message="向量重排序未启用（请设置 USE_VECTOR_SEARCH=1）",
            )

        # 先用 BM25 搜索（请求更多结果给重排序留空间）
        engine = get_search_engine()
        bm25_result = engine.search(
            query=q.strip(),
            page=1,
            page_size=page_size * 3,  # 多取一些供重排序筛选
            sort_by="relevance",
        )

        if not bm25_result["items"]:
            return ApiResponse(
                code=200,
                message="success",
                data={"items": [], "total": 0, "query": q},
            )

        # 向量重排序
        reranked = vector_rerank(q, bm25_result["items"])

        # 分页
        offset = (page - 1) * page_size
        page_items = reranked[offset : offset + page_size]

        # 从数据库补充完整信息
        from app.models import Product
        from app.schemas import ProductResponse

        product_ids = [item["id"] for item in page_items]
        products_map = {
            p.id: p
            for p in db.query(Product)
            .filter(
                Product.id.in_(product_ids),
                Product.is_deleted == False,
            )
            .all()
        }

        items = []
        for item in page_items:
            p = products_map.get(item["id"])
            if p:
                item_data = ProductResponse.model_validate(p).model_dump()
                item_data["highlight_title"] = item.get(
                    "highlight_title",
                    highlight_title(p.name or "", q),
                )
                item_data["highlight_content"] = item.get(
                    "highlight_content",
                    highlight_text(p.description or "", q, max_length=200),
                )
                item_data["_bm25_score"] = item.get("score", 0.0)
                item_data["_vector_score"] = item.get("_vector_score", 0.0)
                item_data["_final_score"] = item.get("_final_score", item.get("score", 0.0))
                item_data["_search_type"] = "hybrid"
                items.append(item_data)

        return ApiResponse(
            code=200,
            message="success",
            data={
                "total": len(reranked),
                "page": page,
                "page_size": page_size,
                "query": q,
                "items": items,
                "engine": "hybrid",
            },
        )

    except Exception as e:
        logger.error(f"向量重排序搜索失败: {e}", exc_info=True)
        return ApiResponse(code=500, message=f"向量重排序搜索失败: {e}")


@router.get("/vector/stats", response_model=ApiResponse)
def vector_search_stats():
    """获取向量搜索状态和统计"""
    try:
        from app.vector_search import get_vector_index

        vindex = get_vector_index()
        return ApiResponse(
            code=200,
            message="success",
            data=vindex.stats,
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            message=f"获取向量搜索状态失败: {e}",
        )


# ======================================================================
# 企业搜索（知识图谱注入）
# ======================================================================


@router.get("/enterprises", response_model=ApiResponse)
def search_enterprises(
    q: str = Query("", description="搜索关键词（企业名称/法人/信用代码）"),
    industry: str | None = Query(None, description="行业筛选"),
    region: str | None = Query(None, description="地区筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """企业搜索（知识图谱）

    在搜索产品的同时，搜索企业库返回匹配的企业列表。
    支持按关键词、行业、地区多维度筛选，分页返回。
    关键词模糊匹配：企业名称、法定代表人、统一社会信用代码、简称。
    """
    query = db.query(Enterprise)

    if q and q.strip():
        keyword = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Enterprise.name.ilike(keyword),
                Enterprise.legal_person.ilike(keyword),
                Enterprise.credit_code.ilike(keyword),
                Enterprise.short_name.ilike(keyword),
            )
        )

    if industry:
        query = query.filter(Enterprise.industry.ilike(f"%{industry}%"))

    if region:
        query = query.filter(Enterprise.region.ilike(f"%{region}%"))

    # 统计总数
    total = query.count()

    # 分页
    query = query.order_by(Enterprise.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    enterprises = query.all()

    # 序列化
    items = []
    for ent in enterprises:
        items.append(
            {
                "id": ent.id,
                "name": ent.name,
                "short_name": ent.short_name,
                "credit_code": ent.credit_code,
                "legal_person": ent.legal_person,
                "registered_capital": ent.registered_capital,
                "established_date": ent.established_date,
                "industry": ent.industry,
                "region": ent.region,
                "business_scope": ent.business_scope,
                "tags": ent.tags,
                "website": ent.website,
                "data_source": ent.data_source,
                "confidence": ent.confidence,
                "created_at": ent.created_at.isoformat() if ent.created_at else None,
                "updated_at": ent.updated_at.isoformat() if ent.updated_at else None,
            }
        )

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
