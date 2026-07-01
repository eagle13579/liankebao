"""
AI数字名片 推荐 API
===================
提供三种推荐接口:
  1. POST /api/recommend/personal   - 个性化推荐（基于用户行为+图谱+语义）
  2. POST /api/recommend/discover   - 发现推荐（全局发现页）
  3. POST /api/recommend/similar    - 相似名片推荐
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.feedback_loop import FeedbackLoop, apply_feedback_boost, get_feedback_loop
from app.ai.recommendation import RecommendEngine
from app.ai.rag_pipeline import RAGPipeline
from app.database import get_db
from app.models.tag import MatchRecord
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.feedback_service import FeedbackAction, FeedbackResult, get_feedback_service
from app.services.recommend_service import FeedbackRecommendation, RecommendService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommend", tags=["推荐"])


# ======================================================================
# 请求 / 响应模型
# ======================================================================


class FeedbackInline(BaseModel):
    """推荐结果的内联反馈（在推荐请求中直接提交）"""
    content_id: int = Field(..., description="被推荐用户/内容 ID")
    action: str = Field(..., description="反馈动作: like/dislike/skip")


class PersonalRecommendRequest(BaseModel):
    top_k: int = Field(20, ge=1, le=100, description="返回数量")
    strategy: str = Field("hybrid", description="推荐策略: tag | graph | semantic | hybrid")
    exclude_user_ids: list[int] = Field(default_factory=list, description="排除的用户 ID")
    feedback: list[FeedbackInline] | None = Field(None, description="历史推荐反馈 (针对之前推荐结果的 👍/👎/skip)")


class DiscoverRequest(BaseModel):
    top_k: int = Field(30, ge=1, le=100, description="返回数量")
    purpose: Optional[str] = Field(None, description="筛选用途: partner/client/investor/supplier")
    feedback: list[FeedbackInline] | None = Field(None, description="历史推荐反馈 (👍/👎/skip)")


class SimilarUsersRequest(BaseModel):
    target_user_id: int = Field(..., description="目标用户 ID（参考用户）")
    top_k: int = Field(10, ge=1, le=50, description="返回数量")
    feedback: list[FeedbackInline] | None = Field(None, description="历史推荐反馈 (👍/👎/skip)")


class RecommendItemResponse(BaseModel):
    user_id: int
    name: str
    company: str = ""
    title: str = ""
    avatar: str = ""
    intro: str = ""
    score: float = 0.0
    tag_match_score: float = 0.0
    graph_score: float = 0.0
    semantic_score: float = 0.0
    reasons: list[str] = []
    common_tags: list[str] = []
    match_type: str = "mixed"


class RecommendResponse(BaseModel):
    items: list[RecommendItemResponse]
    total: int
    strategy_used: str = ""


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="查询文本")
    top_k: int = Field(10, ge=1, le=50, description="向量搜索返回数量")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="LLM 温度")
    max_tokens: int = Field(2048, ge=64, le=8192, description="最大 token 数")


class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[dict] = []
    confidence: float = 0.0
    model_used: str = "deepseek-chat"
    tokens_used: int = 0


# ======================================================================
# 反馈闭环 请求/响应模型
# ======================================================================


class FeedbackSubmitRequest(BaseModel):
    """独立反馈提交请求"""
    content_id: int = Field(..., description="被推荐用户/内容 ID")
    action: str = Field(..., description="反馈动作: like/dislike/skip")
    source: str = Field("recommend", description="反馈来源: recommend/discover/similar")
    recommendation_id: str = Field("", description="推荐记录 ID (可选)")


class FeedbackSubmitResponse(FeedbackResult):
    """反馈提交响应"""
    recommendation_id: str = ""
    user_id: int = 0
    content_id: int = 0
    action: str = ""
    weight_delta: int = 0
    current_boost: float = 1.0
    message: str = ""


# ── 向下兼容: 旧版反馈模型 (留作已有 /{item_id}/feedback 使用) ──


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=-1, le=5, description="评分: 1-5(星级) | 1(👍) | -1(👎) | 0(中性)")
    source: str = Field("recommend", description="反馈来源: recommend/discover/similar")


class FeedbackResponse(BaseModel):
    id: int
    user_id: int
    item_id: int
    rating: int
    feedback_type: str
    boost_factor: float = 1.0
    message: str = "反馈已记录"


class FeedbackStatsResponse(BaseModel):
    total_feedback: int
    positive_feedback: int
    negative_feedback: int
    unique_users: int
    weight_cache_entries: int
    adjust_threshold: int


class FeedbackRecordResponse(BaseModel):
    id: int
    user_id: int
    item_id: int
    rating: int
    source: str
    feedback_type: str
    created_at: float
    updated_at: float


# ======================================================================
# 推荐 API 端点
# ======================================================================


@router.post("/personal", response_model=RecommendResponse)
async def personal_recommend(
    data: PersonalRecommendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """个性化推荐 - 基于标签匹配 + 关系图谱 + 语义相似度"""
    engine = RecommendEngine(db)
    feedback_service = get_feedback_service()

    # 处理内联反馈: 先记录用户对之前推荐结果的 👍/👎/skip
    if data.feedback:
        for fb in data.feedback:
            try:
                feedback_service.record_feedback(
                    user_id=current_user.id,
                    content_id=fb.content_id,
                    action=fb.action,
                    source="recommend",
                )
            except ValueError as e:
                logger.warning("内联反馈处理失败: %s", e)

    if data.strategy not in ("tag", "graph", "semantic", "hybrid"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的推荐策略: {data.strategy}，可选: tag, graph, semantic, hybrid",
        )

    # 获取已匹配用户 ID 列表（排除已 match 的用户）
    result = await db.execute(
        select(MatchRecord).where(
            (MatchRecord.user_a_id == current_user.id) | (MatchRecord.user_b_id == current_user.id)
        )
    )
    matched_records = result.scalars().all()
    matched_ids = set()
    for mr in matched_records:
        matched_ids.add(mr.user_b_id if mr.user_a_id == current_user.id else mr.user_a_id)

    exclude_ids = list(matched_ids | set(data.exclude_user_ids))

    result = await engine.personalize_recommend(
        user_id=current_user.id,
        top_k=data.top_k,
        exclude_ids=exclude_ids,
        strategy=data.strategy,
    )

    return RecommendResponse(
        items=[RecommendItemResponse(**i.to_dict()) for i in result.items],
        total=result.total,
        strategy_used=result.strategy_used,
    )


@router.post("/discover", response_model=RecommendResponse)
async def discover_recommend(
    data: DiscoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发现推荐 - 发现页全局推荐"""
    engine = RecommendEngine(db)
    feedback_service = get_feedback_service()

    # 处理内联反馈
    if data.feedback:
        for fb in data.feedback:
            try:
                feedback_service.record_feedback(
                    user_id=current_user.id,
                    content_id=fb.content_id,
                    action=fb.action,
                    source="discover",
                )
            except ValueError as e:
                logger.warning("内联反馈处理失败: %s", e)

    valid_purposes = (None, "partner", "client", "investor", "supplier")
    if data.purpose not in valid_purposes:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的用途: {data.purpose}，可选: partner, client, investor, supplier",
        )

    result = await engine.discover(
        user_id=current_user.id,
        top_k=data.top_k,
        purpose=data.purpose,
    )

    return RecommendResponse(
        items=[RecommendItemResponse(**i.to_dict()) for i in result.items],
        total=result.total,
        strategy_used=result.strategy_used,
    )


@router.post("/similar", response_model=RecommendResponse)
async def similar_users(
    data: SimilarUsersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """相似名片推荐 - 基于指定用户查找相似用户"""
    engine = RecommendEngine(db)
    feedback_service = get_feedback_service()

    # 处理内联反馈
    if data.feedback:
        for fb in data.feedback:
            try:
                feedback_service.record_feedback(
                    user_id=current_user.id,
                    content_id=fb.content_id,
                    action=fb.action,
                    source="similar",
                )
            except ValueError as e:
                logger.warning("内联反馈处理失败: %s", e)

    # 验证目标用户存在
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == data.target_user_id))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    result = await engine.similar_users(
        target_user_id=data.target_user_id,
        current_user_id=current_user.id,
        top_k=data.top_k,
    )

    return RecommendResponse(
        items=[RecommendItemResponse(**i.to_dict()) for i in result.items],
        total=result.total,
        strategy_used=result.strategy_used,
    )


@router.post("/rag-query", response_model=RAGQueryResponse)
async def rag_query(
    data: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RAG 智能问答 - 基于检索增强生成回答用户问题

    结合向量搜索 + 用户画像 + 关系图谱上下文，使用 DeepSeek 大模型生成回答。
    """
    pipeline = RAGPipeline(db)
    try:
        response = await pipeline.query(
            user_id=current_user.id,
            query_text=data.query,
            top_k=data.top_k,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )

        return RAGQueryResponse(
            answer=response.answer,
            sources=response.sources,
            confidence=response.confidence,
            model_used=response.model_used,
            tokens_used=response.tokens_used,
        )
    except Exception as e:
        logger.error(f"RAG query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG 查询失败: {str(e)}")
    finally:
        await pipeline.close()


@router.get("/graph-summary")
async def graph_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的关系图谱摘要"""
    from app.ai.knowledge_graph import CachedKnowledgeGraphBuilder
    builder = CachedKnowledgeGraphBuilder(db)
    summary = await builder.get_graph_summary(current_user.id)
    return summary


@router.get("/graph")
async def get_graph(
    depth: int = Query(1, ge=1, le=3, description="关系深度"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的完整关系图谱"""
    from app.ai.knowledge_graph import CachedKnowledgeGraphBuilder
    builder = CachedKnowledgeGraphBuilder(db)
    kg = await builder.build_user_graph(current_user.id, max_depth=depth)
    return kg.to_dict()


# ======================================================================
# 反馈闭环 API 端点
# ======================================================================


@router.post("/feedback", response_model=FeedbackSubmitResponse)
async def submit_feedback(
    data: FeedbackSubmitRequest,
    current_user: User = Depends(get_current_user),
):
    """提交推荐反馈 (👍/👎/skip)

    用户对推荐结果进行评价:
      - "like":   👍 点赞 (权重 +1)
      - "dislike": 👎 不喜欢 (权重 -1)
      - "skip":    跳过 (权重不变)

    反馈数据会:
      1. 持久化到 SQLite
      2. 每收集 10 条自动触发权重调整
      3. 影响后续推荐结果排序 (权重乘数范围 [0.6, 1.5])
    """
    svc = get_feedback_service()
    try:
        result = svc.record_feedback(
            user_id=current_user.id,
            content_id=data.content_id,
            action=data.action,
            source=data.source,
            recommendation_id=data.recommendation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FeedbackSubmitResponse(
        recommendation_id=result.recommendation_id,
        user_id=result.user_id,
        content_id=result.content_id,
        action=result.action,
        weight_delta=result.weight_delta,
        current_boost=result.current_boost,
        message=result.message,
    )


@router.post("/{item_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    item_id: int,
    data: FeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    """提交推荐反馈

    用户对推荐结果进行评价:
      - ⭐ 1-5: 星级评分 (5=非常喜欢)
      - 👍 rating=1: 点赞
      - 👎 rating=-1: 不喜欢
      - 0: 中性/跳过

    反馈数据会:
      1. 持久化到 SQLite
      2. 每收集 10 条自动触发权重调整
      3. 影响后续推荐结果排序
    """
    loop = get_feedback_loop()

    try:
        record = loop.record_feedback(
            user_id=current_user.id,
            item_id=item_id,
            rating=data.rating,
            source=data.source,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    boost = loop.get_feedback_boost(current_user.id, item_id)

    # 映射 rating -> 反馈类型描述
    type_map = {1: "点赞", -1: "踩", 0: "中性", 2: "2星", 3: "3星", 4: "4星", 5: "5星"}
    fb_type = type_map.get(data.rating, f"{data.rating}分")

    return FeedbackResponse(
        id=record.id,
        user_id=record.user_id,
        item_id=record.item_id,
        rating=record.rating,
        feedback_type=record.feedback_type,
        boost_factor=round(boost, 4),
        message=f"推荐反馈已记录: {fb_type}, 权重提升系数={boost:.2f}",
    )


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def feedback_stats(
    current_user: User = Depends(get_current_user),
):
    """获取反馈闭环全局统计"""
    loop = get_feedback_loop()
    stats = loop.get_global_stats()
    return FeedbackStatsResponse(**stats)


@router.get("/feedback/my", response_model=list[FeedbackRecordResponse])
async def my_feedback(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的所有反馈记录"""
    loop = get_feedback_loop()
    records = loop.get_user_feedback(current_user.id, limit=limit)
    return [
        FeedbackRecordResponse(
            id=r.id,
            user_id=r.user_id,
            item_id=r.item_id,
            rating=r.rating,
            source=r.source,
            feedback_type=r.feedback_type,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]


@router.post("/feedback/adjust")
async def trigger_adjustment(
    current_user: User = Depends(get_current_user),
):
    """手动触发权重调整（通常由系统自动触发）"""
    loop = get_feedback_loop()
    updated = loop.trigger_adjustment()
    return {
        "message": f"权重调整完成，更新 {updated} 条记录",
        "updated_count": updated,
    }


@router.get("/feedback/user/{target_user_id}", response_model=FeedbackStatsResponse)
async def user_feedback_stats(
    target_user_id: int,
    current_user: User = Depends(get_current_user),
):
    """获取当前用户对某个推荐目标的反馈统计"""
    loop = get_feedback_loop()
    stats = loop.get_user_item_stats(current_user.id, target_user_id)
    return FeedbackStatsResponse(
        total_feedback=stats.total_feedback,
        positive_feedback=stats.positive_count,
        negative_feedback=stats.negative_count,
        unique_users=1,
        weight_cache_entries=1,
        adjust_threshold=loop.ADJUST_THRESHOLD,
    )
