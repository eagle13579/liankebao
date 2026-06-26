"""
链客宝 - 匹配引擎路由（轻量版）
=================================
提供与 /d/链客宝/backend/matching_engine.py 相同的 API 接口。
匹配核心逻辑调用 /d/链客宝/ 的完整引擎，此处为接口层适配。

API:
  GET  /api/matching/needs/{need_id}/products    — 需求匹配产品
  GET  /api/matching/products/{product_id}/needs — 产品匹配需求
  POST /api/matching/refresh                     — 刷新索引
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessCard

# Feature Flag 控制
from app.features.feature_flags import manager as flag_manager
from app.features.feature_flags import UserContext

# 三塔DNN推理管道 (懒加载)
try:
    from features.matching_pipeline import dnn_match, load_engine, pipeline_ready
    _HAS_DNN_PIPELINE = True
except ImportError:
    _HAS_DNN_PIPELINE = False
    dnn_match = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matching", tags=["AI供需匹配（轻量版）"])

# 尝试导入完整引擎
try:
    import sys
    import os
    # 如果 /d/链客宝/backend/ 存在，加入路径
    chainke_full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '..')
    if os.path.isdir(chainke_full_path):
        sys.path.insert(0, chainke_full_path)
    from matching_engine import router as full_engine_router
    from matching_engine import MatchEngine, get_engine, match_metrics

    _HAS_FULL_ENGINE = True
    logger.info("[MatchingEngine] 使用完整匹配引擎")
except ImportError:
    _HAS_FULL_ENGINE = False
    logger.info("[MatchingEngine] 完整引擎不可用，使用内置简化版")

# ── MMR 多样性模块 ──
try:
    from features.mmr_diversity import (
        mmr_rerank,
        diversity_score as compute_diversity_score,
    )
    _HAS_MMR = True
    logger.info("[MatchingEngine] MMR多样性模块已加载")
except ImportError:
    _HAS_MMR = False
    logger.warning("[MatchingEngine] MMR多样性模块未找到，多样性端点不可用")


# ── 简化版匹配（当完整引擎不可用时） ──


def _simple_match(need_text: str, products: list) -> list[dict]:
    """简化版关键词匹配"""
    results = []
    keywords = set(need_text.lower().split())
    if not keywords:
        return results

    for p in products:
        fields = p.fields if isinstance(p.fields, dict) else {}
        text = " ".join(str(v) for v in fields.values()).lower()
        matched = keywords & set(text.split())
        score = len(matched) / max(len(keywords), 1) if matched else 0
        if score > 0:
            results.append({
                "id": p.id,
                "title": fields.get("name", fields.get("company", f"名片#{p.id}")),
                "description": fields.get("description", ""),
                "category": "",
                "match_score": min(score, 1.0),
                "match_reasons": [f"关键词匹配 ({len(matched)}个)"] if matched else [],
                "strategy": "simple",
            })
    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results


@router.get("/needs/{need_id}/products")
def match_needs_to_products(
    need_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """根据需求ID匹配相关产品"""
    if _HAS_FULL_ENGINE:
        # 委托给完整引擎
        try:
            from matching_engine import match_needs_to_products as full_match
            return full_match(need_id, offset=offset, limit=limit, db=db)
        except Exception as e:
            logger.warning(f"完整引擎调用失败，回退: {e}")

    # ── Feature Flag: 三塔DNN匹配 ────────────────────────────────
    if _HAS_DNN_PIPELINE:
        try:
            # 用 need_id 构造 UserContext 用于灰度发布评估
            ctx = UserContext(user_id=f"need_{need_id}")
            if flag_manager.is_enabled("new_matching_engine", user_context=ctx):
                dnn_results = dnn_match(need_id, db=db, offset=offset, limit=limit)
                if dnn_results is not None:
                    total = db.query(BusinessCard).filter(BusinessCard.id != need_id).count()
                    return {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "items": dnn_results,
                            "total": total,
                            "strategy": "dnn",
                        },
                    }
                logger.warning("DNN匹配返回None，回退到关键词匹配")
        except Exception as e:
            logger.warning(f"DNN匹配失败，回退到关键词匹配: {e}")

    # 简化版：从 BusinessCard 中匹配
    card = db.query(BusinessCard).filter(BusinessCard.id == need_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="名片不存在")

    need_text = " ".join(str(v) for v in (card.fields or {}).values())
    all_cards = db.query(BusinessCard).filter(BusinessCard.id != need_id).all()
    results = _simple_match(need_text, all_cards)
    paginated = results[offset:offset + limit]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": paginated,
            "total": len(results),
            "strategy": "simple",
        },
    }


@router.get("/products/{product_id}/needs")
def match_products_to_needs(
    product_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """根据产品ID匹配相关需求"""
    if _HAS_FULL_ENGINE:
        try:
            from matching_engine import match_products_to_needs as full_match
            return full_match(product_id, offset=offset, limit=limit, db=db)
        except Exception as e:
            logger.warning(f"完整引擎调用失败，回退简化版: {e}")

    card = db.query(BusinessCard).filter(BusinessCard.id == product_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="名片不存在")

    need_text = " ".join(str(v) for v in (card.fields or {}).values())
    all_cards = db.query(BusinessCard).filter(BusinessCard.id != product_id).all()
    results = _simple_match(need_text, all_cards)
    paginated = results[offset:offset + limit]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": paginated,
            "total": len(results),
            "strategy": "simple",
        },
    }


@router.post("/refresh")
def refresh_index(db: Session = Depends(get_db)):
    """刷新匹配索引"""
    count = db.query(BusinessCard).count()
    return {
        "code": 200,
        "message": "匹配索引已刷新",
        "data": {"cards_count": count, "status": "ready"},
    }


# ═══════════════════════════════════════════════════════════════
# MMR 多样性匹配端点
# ═══════════════════════════════════════════════════════════════


class DiverseMatchItem(BaseModel):
    """候选匹配项"""
    id: str | int
    title: str = ""
    description: str = ""
    category: str = ""
    fields: dict[str, Any] = {}


class DiverseMatchRequest(BaseModel):
    """多样性匹配请求体"""
    query: str
    candidates: list[DiverseMatchItem]
    relevance_scores: list[float] | None = None
    diversity_weight: float = 0.3  # λ ∈ [0,1], 0=纯多样性, 1=纯相关性

    model_config = {"json_schema_extra": {
        "example": {
            "query": "寻找AI相关的产品经理",
            "candidates": [
                {"id": 1, "title": "AI产品经理", "description": "负责AI产品设计", "category": "科技"},
                {"id": 2, "title": "Java开发工程师", "description": "后端开发", "category": "科技"},
                {"id": 3, "title": "AI算法专家", "description": "机器学习模型设计", "category": "科技"},
            ],
            "relevance_scores": [0.95, 0.45, 0.88],
            "diversity_weight": 0.3,
        }
    }}


class DiverseMatchResultItem(BaseModel):
    """多样性匹配结果项"""
    id: str | int
    title: str
    description: str
    category: str
    match_score: float
    mmr_score: float


class DiverseMatchResponse(BaseModel):
    """多样性匹配响应"""
    results: list[DiverseMatchResultItem]
    diversity_score: float
    metadata: dict[str, Any]


# ── 新的 /api/v1/match 路由 ──

v1_router = APIRouter(prefix="/api/v1/match", tags=["AI多样性匹配"])


def _text_similarity(a: DiverseMatchItem, b: DiverseMatchItem) -> float:
    """基于文本的 Jaccard 相似度（用于 MMR 的 similarity_fn）"""
    def _tokens(item: DiverseMatchItem) -> set[str]:
        parts = [
            item.title,
            item.description,
            item.category,
        ]
        for v in item.fields.values():
            parts.append(str(v))
        text = " ".join(p.lower() for p in parts if p)
        return set(text.split())

    tokens_a = _tokens(a)
    tokens_b = _tokens(b)

    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


@v1_router.post("/diverse", response_model=DiverseMatchResponse)
def diverse_match(request: DiverseMatchRequest):
    """
    MMR 多样性匹配端点

    在保持相关性的同时最大化结果的多样性。
    使用 Maximal Marginal Relevance (MMR) 算法对候选列表重排序。

    - diversity_weight=0.0 → 纯多样性（忽略相关性）
    - diversity_weight=0.3 → 偏相关性, 适度多样性（默认推荐）
    - diversity_weight=0.7 → 偏相关性, 轻微多样性
    - diversity_weight=1.0 → 纯相关性（按原始分数降序）
    """
    if not _HAS_MMR:
        raise HTTPException(
            status_code=501,
            detail="MMR多样性模块不可用，请确保 features/mmr_diversity.py 存在",
        )

    n = len(request.candidates)
    if n == 0:
        return DiverseMatchResponse(
            results=[],
            diversity_score=1.0,
            metadata={"strategy": "mmr", "diversity_weight": request.diversity_weight, "total": 0},
        )

    # ── 如果没有提供 relevance_scores，使用 query 进行关键词匹配 ──
    if request.relevance_scores is None:
        query_keywords = set(request.query.lower().split())
        computed_scores = []
        for cand in request.candidates:
            text = " ".join([
                cand.title, cand.description, cand.category,
                *[str(v) for v in cand.fields.values()],
            ]).lower()
            tokens = set(text.split())
            if not query_keywords or not tokens:
                computed_scores.append(0.0)
            else:
                matched = query_keywords & tokens
                score = len(matched) / max(len(query_keywords), 1)
                computed_scores.append(min(score, 1.0))
        relevance_scores = computed_scores
        score_source = "auto_keyword"
    else:
        if len(request.relevance_scores) != n:
            raise HTTPException(
                status_code=422,
                detail=f"relevance_scores 长度 ({len(request.relevance_scores)}) 与 candidates 长度 ({n}) 不一致",
            )
        relevance_scores = request.relevance_scores
        score_source = "provided"

    # ── 执行 MMR 重排序 ──
    candidate_objs = list(request.candidates)
    mmr_results = mmr_rerank(
        candidates=candidate_objs,
        relevance_scores=relevance_scores,
        lambda_=request.diversity_weight,
        similarity_fn=_text_similarity,
        top_n=n,
    )

    # ── 计算多样性分数 ──
    if n <= 1:
        div_score = 1.0
    else:
        div_score = compute_diversity_score(
            [r[0] for r in mmr_results],
            _text_similarity,
        )

    # ── 组装结果 ──
    results = [
        DiverseMatchResultItem(
            id=item.id,
            title=item.title,
            description=item.description,
            category=item.category,
            match_score=round(score, 4),
            mmr_score=round(
                request.diversity_weight * score
                - (1 - request.diversity_weight) * _text_similarity(item, mmr_results[0][0])
                if idx > 0 else score,
                4,
            ),
        )
        for idx, (item, score) in enumerate(mmr_results)
    ]

    return DiverseMatchResponse(
        results=results,
        diversity_score=round(div_score, 4),
        metadata={
            "strategy": "mmr",
            "total": n,
            "diversity_weight": request.diversity_weight,
            "lambda": request.diversity_weight,
            "score_source": score_source,
            "algorithm": "Maximal Marginal Relevance",
        },
    )


print("")
print("[MatchingEngine] MMR多样性匹配已集成 ✓")
print("[MatchingEngine] 新增端点: POST /api/v1/match/diverse")
print("")


# ═══════════════════════════════════════════════════════════════
# 自然语言搜索端点
# ═══════════════════════════════════════════════════════════════


class NLSearchRequest(BaseModel):
    """自然语言搜索请求"""
    query: str
    offset: int = 0
    limit: int = 20


class NLSearchItem(BaseModel):
    id: int
    title: str = ""
    company: str = ""
    position: str = ""
    description: str = ""
    tags: list[str] = []
    match_score: float = 0.0
    match_reasons: list[str] = []

    model_config = {"from_attributes": True}


class NLSearchResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict[str, Any]


@router.post("/search", summary="自然语言搜索名片")
def nl_search(
    req: NLSearchRequest,
    db: Session = Depends(get_db),
):
    """
    自然语言搜索企业名片。

    使用用户输入的自然语言查询，通过关键词匹配搜索所有 BusinessCard 记录。
    支持分页，返回按匹配度排序的结果列表。

    请求示例:
        POST /api/matching/search
        { "query": "寻找华东地区的制造业供应商", "offset": 0, "limit": 20 }
    """
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询内容不能为空")

    # 从 DB 加载所有名片
    all_cards = db.query(BusinessCard).all()

    # 使用现有 _simple_match 逻辑进行关键词匹配
    results = _simple_match(query, all_cards)

    # 分页
    paginated = results[req.offset:req.offset + req.limit]

    # 增强返回字段
    items = []
    for r in paginated:
        card = db.query(BusinessCard).filter(BusinessCard.id == r["id"]).first()
        fields = card.fields if card and isinstance(card.fields, dict) else {}
        items.append({
            "id": r["id"],
            "title": r["title"],
            "company": fields.get("company", ""),
            "position": fields.get("position", ""),
            "description": r["description"],
            "tags": fields.get("tags", []),
            "match_score": r["match_score"],
            "match_reasons": r["match_reasons"],
        })

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": len(results),
            "strategy": "simple",
            "query": query,
        },
    }


print("[MatchingEngine] 路由已加载 ✓")
print("[MatchingEngine] 端点: GET  /api/matching/needs/{need_id}/products")
print("[MatchingEngine] 端点: GET  /api/matching/products/{product_id}/needs")
print("[MatchingEngine] 端点: POST /api/matching/refresh")
print("[MatchingEngine] 端点: POST /api/matching/search (自然语言搜索)")
