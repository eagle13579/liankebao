"""向量搜索 API 路由 — 语义搜索 + 索引重建"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.vector_search import (
    USE_VECTOR_SEARCH,
    get_vector_index,
    sync_vector_index,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search/vector", tags=["vector_search"])
vector_search_router = router


@router.get(
    "",
    summary="语义搜索",
    description="使用向量 embedding 做语义相似度搜索，返回 top-k 匹配结果。需启用 USE_VECTOR_SEARCH=1",
)
def vector_search(
    q: str = Query("", description="搜索查询文本"),
    top_k: int = Query(10, ge=1, le=100, description="返回结果数量"),
):
    """语义向量搜索

    基于 cosine 相似度从向量索引中检索最匹配的文档。
    需要先启用 USE_VECTOR_SEARCH=1 并重建索引。
    """
    if not USE_VECTOR_SEARCH:
        raise HTTPException(
            status_code=503,
            detail="向量搜索未启用，请设置环境变量 USE_VECTOR_SEARCH=1",
        )

    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="搜索查询参数 q 不能为空")

    try:
        index = get_vector_index()
        results = index.search(q, top_k=top_k)

        # 格式化结果
        items = []
        for r in results:
            metadata = r.get("metadata", {})
            items.append(
                {
                    "id": r["id"],
                    "score": r["score"],
                    "text": r["text"],
                    "content_type": metadata.get("content_type", "unknown"),
                    "content_id": metadata.get("content_id", r["id"]),
                }
            )

        return {
            "code": 200,
            "message": "success",
            "data": {
                "items": items,
                "total": len(items),
                "query": q,
                "index_size": index.size,
            },
        }
    except Exception as e:
        logger.error(f"向量搜索失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"向量搜索失败: {str(e)}")


@router.post(
    "/rebuild",
    summary="重建向量索引",
    description="扫描所有 products 和 needs，增量同步到向量索引。需要启用 USE_VECTOR_SEARCH=1",
)
def rebuild_vector_index(
    db: Session = Depends(get_db),
):
    """重建/增量同步向量索引

    扫描数据库中所有 approved 状态的 products 和未删除的 needs，
    计算 embedding 并写入 SQLite 持久化存储。
    已存在的条目如果内容未变化则跳过（增量同步）。
    """
    if not USE_VECTOR_SEARCH:
        raise HTTPException(
            status_code=503,
            detail="向量搜索未启用，请设置环境变量 USE_VECTOR_SEARCH=1",
        )

    try:
        result = sync_vector_index(db_session=db)

        return {
            "code": 200,
            "message": "向量索引同步完成",
            "data": {
                "products_added": result.get("products_added", 0),
                "needs_added": result.get("needs_added", 0),
                "products_skipped": result.get("products_skipped", 0),
                "needs_skipped": result.get("needs_skipped", 0),
            },
        }
    except Exception as e:
        logger.error(f"向量索引重建失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"向量索引重建失败: {str(e)}")
