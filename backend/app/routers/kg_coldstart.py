"""知识图谱冷启动匹配 — API路由"""
from fastapi import APIRouter, HTTPException
from features.kg_coldstart.coldstart_matcher import ColdStartMatcher

router = APIRouter(prefix="/api/matching", tags=["matching"])
matcher = ColdStartMatcher()


@router.get("/coldstart/{user_id}")
async def coldstart_recommendations(
    user_id: int,
    industry: str = None,
    company_size: str = None,
    region: str = None,
    top_k: int = 10
):
    """为新用户获取冷启动推荐"""
    recs = matcher.get_recommendations(
        user_id=user_id,
        industry=industry,
        company_size=company_size,
        region=region,
        top_k=top_k
    )
    return {
        "code": 0,
        "data": recs,
        "total": len(recs),
        "match_type": "coldstart"
    }


@router.get("/similar-companies/{company_id}")
async def similar_companies(company_id: int, top_k: int = 5):
    """基于图相似度的企业推荐"""
    recs = matcher.get_similar_companies(company_id, top_k)
    return {
        "code": 0,
        "data": recs,
        "total": len(recs),
        "match_type": "graph_similarity"
    }
