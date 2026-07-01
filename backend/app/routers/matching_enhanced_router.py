"""
增强匹配API路由 — 信任加权+可解释性+分级匹配
=============================================
提供增强版匹配端点，在原有 matching_engine 基础上增加:
  1. 信任加权排序
  2. 匹配可解释性
  3. 分级匹配过滤
  4. 探索加成

端点:
  GET /api/matching/enhanced/needs/{id}/products
  GET /api/matching/enhanced/products/{id}/needs
  GET /api/matching/enhanced/explain/{match_id}
  POST /api/matching/search — 自然语言搜索名片
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.matching_enhanced import (
    EnhancedMatchResult,
    enhance_match_results,
)
from app.models import User
from matching_engine import MatchEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matching/enhanced", tags=["增强匹配"])

# ============================================================
# Pydantic 模型
# ============================================================


class ExplanationOut(BaseModel):
    reason_type: str
    reason_text: str
    score_contribution: float


class EnhancedMatchOut(BaseModel):
    target_id: int
    target_type: str
    rule_score: float
    ml_score: float | None = None
    trust_score: float | None = None
    trust_tier: str
    match_level: str
    total_score: float
    explanations: list[ExplanationOut] = []
    exploration_bonus: float = 0.0


class EnhancedMatchResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: dict[str, object]


# ============================================================
# 辅助函数
# ============================================================


def _format_results(results: list[EnhancedMatchResult]) -> list[EnhancedMatchOut]:
    return [
        EnhancedMatchOut(
            target_id=r.target_id,
            target_type=r.target_type,
            rule_score=r.rule_score,
            ml_score=r.ml_score,
            trust_score=r.trust_score,
            trust_tier=r.trust_tier,
            match_level=r.match_level,
            total_score=r.total_score,
            explanations=[
                ExplanationOut(
                    reason_type=e.reason_type,
                    reason_text=e.reason_text,
                    score_contribution=e.score_contribution,
                )
                for e in r.explanations
            ],
            exploration_bonus=r.exploration_bonus,
        )
        for r in results
    ]


# ============================================================
# API 端点
# ============================================================


@router.get("/needs/{need_id}/products")
def enhanced_match_needs_to_products(
    need_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    top_k: int = Query(20, ge=1, le=100, description="返回结果数"),
    strategy: str = Query("v2", regex="^(v1|v2)$", description="匹配策略"),
):
    """
    增强版需求匹配产品

    在原始匹配基础上增加:
    - 信任加权排序 (根据双方信任分调整排名)
    - 可解释性 (每项匹配附带推荐原因)
    - 分级匹配 (根据信任等级决定展示策略)
    - Bandit探索 (冷启动产品获得额外曝光)
    """
    try:
        # 1. 原始匹配
        engine = MatchEngine()
        if strategy == "v1":
            raw_matches = engine.match_needs_to_products(need_id, use_enhanced=False)
        else:
            raw_matches = engine.match_needs_to_products(need_id, use_enhanced=True)

        # 2. 格式化为增强匹配所需格式
        formatted = []
        for idx, match in enumerate(raw_matches):
            formatted.append(
                {
                    "id": match.get("product_id", match.get("id", idx)),
                    "type": "product",
                    "score": match.get("score", match.get("match_score", 50)),
                    "ml_score": match.get("ml_score"),
                    "user_id": match.get("user_id", match.get("owner_id", 0)),
                    "category_match": match.get("category_match", True),
                    "category": match.get("category", ""),
                    "matched_keywords": match.get("matched_keywords", []),
                    "price_match": match.get("price_match", False),
                    "budget_min": match.get("budget_min", 0),
                    "budget_max": match.get("budget_max", 0),
                    "price_min": match.get("price_min", 0),
                    "price_max": match.get("price_max", 0),
                    "same_region": match.get("same_region", False),
                    "region": match.get("region", ""),
                    "history_count": match.get("history_count", 0),
                    "activity_days": match.get("activity_days", 0),
                    "interactions": match.get("view_count", match.get("interactions", 0)),
                    "successes": match.get("match_count", match.get("successes", 0)),
                }
            )

        # 3. 增强
        enhanced = enhance_match_results(formatted, current_user.id, db)

        return EnhancedMatchResponse(
            data={
                "matches": [m.model_dump() for m in _format_results(enhanced[:top_k])],
                "total": len(enhanced),
                "strategy": strategy,
                "match_level": enhanced[0].match_level if enhanced else "manual",
            }
        )
    except Exception as e:
        logger.exception("增强匹配失败")
        raise HTTPException(status_code=500, detail=f"增强匹配失败: {str(e)}")


@router.get("/products/{product_id}/needs")
def enhanced_match_products_to_needs(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    top_k: int = Query(20, ge=1, le=100),
    strategy: str = Query("v2", regex="^(v1|v2)$"),
):
    """
    增强版产品匹配需求 (反向匹配)
    """
    try:
        engine = MatchEngine()
        raw_matches = engine.match_products_to_needs(product_id, use_enhanced=(strategy == "v2"))

        formatted = []
        for idx, match in enumerate(raw_matches):
            formatted.append(
                {
                    "id": match.get("need_id", match.get("id", idx)),
                    "type": "need",
                    "score": match.get("score", match.get("match_score", 50)),
                    "ml_score": match.get("ml_score"),
                    "user_id": match.get("user_id", match.get("creator_id", 0)),
                    "category_match": match.get("category_match", True),
                    "category": match.get("category", ""),
                    "matched_keywords": match.get("matched_keywords", []),
                    "price_match": match.get("price_match", False),
                    "budget_min": match.get("budget_min", 0),
                    "budget_max": match.get("budget_max", 0),
                    "price_min": match.get("price_min", 0),
                    "price_max": match.get("price_max", 0),
                    "same_region": match.get("same_region", False),
                    "region": match.get("region", ""),
                    "history_count": match.get("history_count", 0),
                    "activity_days": match.get("activity_days", 0),
                    "interactions": match.get("view_count", match.get("interactions", 0)),
                    "successes": match.get("match_count", match.get("successes", 0)),
                }
            )

        enhanced = enhance_match_results(formatted, current_user.id, db)

        return EnhancedMatchResponse(
            data={
                "matches": [m.model_dump() for m in _format_results(enhanced[:top_k])],
                "total": len(enhanced),
                "strategy": strategy,
            }
        )
    except Exception as e:
        logger.exception("增强匹配失败")
        raise HTTPException(status_code=500, detail=f"增强匹配失败: {str(e)}")


@router.get("/explain/{match_id}")
def get_match_explanation(
    match_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    获取匹配解释详情

    返回该匹配的完整可解释性分析:
    - 为什么推荐这个匹配
    - 各维度的贡献度
    - 信任评分详情
    """
    return {
        "code": 0,
        "message": "success",
        "data": {
            "match_id": match_id,
            "note": "可解释性详情已整合到增强匹配端点中",
            "tip": "请使用 /api/matching/enhanced/needs/{id}/products 获取带解释的匹配结果",
        },
    }


# ═══════════════════════════════════════════════════════════════
# 自然语言搜索端点 (NL Search)
# ═══════════════════════════════════════════════════════════════
# 前端 NLSearchWidget 调用 POST /api/matching/search
# ═══════════════════════════════════════════════════════════════

import re as _re

from app.models import BusinessCard


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
    data: dict[str, object]


search_router = APIRouter(prefix="/api/matching", tags=["自然语言搜索"])


def _simple_match(query: str, cards: list) -> list[dict]:
    """简化版关键词匹配 — 对 BusinessCard 按字段关键词打分"""
    keywords = set(_re.findall(r'[\w\u4e00-\u9fff]+', query.lower()))
    if not keywords:
        return []

    results = []
    for card in cards:
        fields = card.fields if isinstance(card.fields, dict) else {}
        text = " ".join(str(v) for v in fields.values()).lower()
        matched = keywords & set(_re.findall(r'[\w\u4e00-\u9fff]+', text))
        if not matched:
            continue
        score = len(matched) / max(len(keywords), 1)
        title = fields.get("name") or fields.get("company") or f"名片#{card.id}"
        results.append({
            "id": card.id,
            "title": title,
            "description": fields.get("description", ""),
            "category": fields.get("category", ""),
            "match_score": min(score, 1.0),
            "match_reasons": [f"关键词匹配 ({len(matched)}个)"],
            "strategy": "simple",
        })

    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results


@search_router.post("/search", summary="自然语言搜索名片", response_model=NLSearchResponse)
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

    # 关键词匹配
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


print("[MatchingEngine] 端点: POST /api/matching/search (自然语言搜索)")
