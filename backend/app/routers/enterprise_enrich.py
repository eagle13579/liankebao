"""
企查查企业信息丰富 API 路由

提供基于企查查开放平台的增强企业信息端点：
  - POST /api/enterprise/verify          — 企业三要素核验
  - GET  /api/enterprise/{credit_code}   — 企业信息查询（缓存 + 企查查 API）
  - POST /api/enterprise/batch-enrich    — 批量企业信息丰富

依赖 app.services.qichacha_client.QichachaClient，从环境变量读取 API 凭据。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.models import User
from app.schemas import ApiResponse
from app.services.qichacha_client import QichachaClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enterprise", tags=["企查查企业丰富"])


# ============================================================
# 请求/响应模型
# ============================================================


class VerifyRequest(BaseModel):
    """企业三要素核验请求"""

    name: str = Field(..., min_length=1, max_length=200, description="企业全称")
    credit_code: str = Field(
        ...,
        min_length=18,
        max_length=18,
        description="统一社会信用代码（18 位）",
    )
    legal_person: str = Field(..., min_length=1, max_length=50, description="法定代表人姓名")


class VerifyResponse(BaseModel):
    """企业三要素核验响应"""

    verified: bool = Field(..., description="是否核验通过")
    match_score: int = Field(..., ge=0, le=100, description="匹配分数 0-100")
    detail: str = Field("", description="核验详情")
    raw_data: Any | None = Field(None, description="原始返回数据（调试用）")


class BatchEnrichItem(BaseModel):
    """单条批量丰富请求项"""

    name: str = Field(..., min_length=1, description="企业名称")
    credit_code: str | None = Field(None, description="统一社会信用代码（可选）")


class BatchEnrichRequest(BaseModel):
    """批量企业信息丰富请求"""

    enterprises: list[BatchEnrichItem] = Field(..., min_length=1, max_length=100, description="企业列表（最多 100 条）")


class BatchEnrichResult(BaseModel):
    """单条批量丰富结果"""

    name: str
    credit_code: str | None = None
    success: bool
    data: dict | None = None
    error: str | None = None


# ============================================================
# 客户端单例
# ============================================================

_client: QichachaClient | None = None


def get_qichacha_client() -> QichachaClient:
    """获取企查查客户端单例（懒加载）"""
    global _client
    if _client is None:
        _client = QichachaClient()
    return _client


# ============================================================
# API 端点
# ============================================================


@router.post("/verify", response_model=ApiResponse, summary="企业三要素核验")
async def enterprise_verify(
    req: VerifyRequest,
    current_user: User = Depends(get_current_user),
    client: QichachaClient = Depends(get_qichacha_client),
):
    """企业三要素核验

    核验企业名称、统一社会信用代码、法定代表人是否一致。
    数据来源: 企查查开放平台 API
    结果缓存: 24 小时（企业三要素信息不常变）

    Args:
        req: { name, credit_code, legal_person }

    Returns:
        ApiResponse with data = {
            "verified": bool,       // 是否核验通过
            "match_score": int,     // 匹配分数 0-100
            "detail": str,          // 核验详情
            "raw_data": dict | None // 原始返回
        }
    """
    try:
        result = client.verify_enterprise(
            name=req.name,
            credit_code=req.credit_code,
            legal_person=req.legal_person,
        )
        logger.info(
            "企业三要素核验 [user=%s]: name=%s, credit_code=%s, verified=%s",
            current_user.id,
            req.name,
            req.credit_code,
            result.get("verified"),
        )
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error("企业三要素核验异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"核验服务异常: {str(e)}")


@router.get("/{credit_code}", response_model=ApiResponse, summary="企业信息查询")
async def enterprise_detail(
    credit_code: str = Path(..., min_length=18, max_length=18, description="统一社会信用代码（18 位）"),
    current_user: User = Depends(get_current_user),
    client: QichachaClient = Depends(get_qichacha_client),
):
    """企业信息查询

    根据统一社会信用代码查询企业详细信息。
    优先返回缓存数据（缓存 TTL 12 小时），缓存未命中时调用企查查 API。

    Args:
        credit_code: 18 位统一社会信用代码

    Returns:
        ApiResponse with data = 企业信息 dict
    """
    # 先尝试查企业详情
    detail = client.get_company_detail(credit_code)

    # 如果企业详情只返回了 error 字段（API 不可用），尝试走工商信息接口
    if detail.get("error"):
        base_info = client.get_company_base_info(credit_code)
        if not base_info.get("error"):
            detail = base_info
        # 如果两个接口都失败，返回缓存中可能存在的旧数据
        # （缓存已经在 get_company_detail 中检查过了，到这里确实是 API 不可用）

    if detail.get("error"):
        logger.warning("企查查 API 查询企业失败 [%s]: %s", credit_code, detail["error"])
        raise HTTPException(
            status_code=503,
            detail=f"企查查 API 服务暂不可用: {detail['error']}",
        )

    logger.info(
        "企业信息查询 [user=%s]: credit_code=%s, name=%s",
        current_user.id,
        credit_code,
        detail.get("name", ""),
    )
    return ApiResponse(code=200, message="success", data=detail)


@router.post("/batch-enrich", response_model=ApiResponse, summary="批量企业信息丰富")
async def enterprise_batch_enrich(
    req: BatchEnrichRequest,
    current_user: User = Depends(get_current_user),
    client: QichachaClient = Depends(get_qichacha_client),
):
    """批量企业信息丰富

    对一批企业名称/信用代码批量查询企查查信息。
    逐个企业查询，独立错误处理（一个企业失败不影响其他企业）。

    Args:
        req: { enterprises: [{ name, credit_code? }] }

    Returns:
        ApiResponse with data = {
            "total": int,
            "success_count": int,
            "fail_count": int,
            "results": [{
                "name": str,
                "credit_code": str | None,
                "success": bool,
                "data": dict | None,
                "error": str | None
            }]
        }
    """
    enterprises = req.enterprises
    total = len(enterprises)
    results: list[BatchEnrichResult] = []
    success_count = 0
    fail_count = 0

    for i, item in enumerate(enterprises):
        try:
            if item.credit_code:
                # 有信用代码：直接查询详情
                detail = client.get_company_detail(item.credit_code)
                if detail.get("error"):
                    # 尝试按名称搜索兜底
                    search_result = client.search_by_name(item.name, page=1, page_size=1)
                    if search_result.get("items"):
                        results.append(
                            BatchEnrichResult(
                                name=item.name,
                                credit_code=item.credit_code,
                                success=True,
                                data=search_result["items"][0],
                            )
                        )
                        success_count += 1
                    else:
                        results.append(
                            BatchEnrichResult(
                                name=item.name,
                                credit_code=item.credit_code,
                                success=False,
                                error=detail.get("error", "查询失败"),
                            )
                        )
                        fail_count += 1
                else:
                    results.append(
                        BatchEnrichResult(
                            name=item.name,
                            credit_code=item.credit_code,
                            success=True,
                            data=detail,
                        )
                    )
                    success_count += 1
            else:
                # 无信用代码：按名称搜索
                search_result = client.search_by_name(item.name, page=1, page_size=1)
                if search_result.get("items"):
                    best = search_result["items"][0]
                    results.append(
                        BatchEnrichResult(
                            name=item.name,
                            credit_code=best.get("credit_code", ""),
                            success=True,
                            data=best,
                        )
                    )
                    success_count += 1
                else:
                    results.append(
                        BatchEnrichResult(
                            name=item.name,
                            credit_code=None,
                            success=False,
                            error="未找到该企业信息",
                        )
                    )
                    fail_count += 1
        except Exception as e:
            logger.error("批量丰富单项失败 [%s]: %s", item.name, e)
            results.append(
                BatchEnrichResult(
                    name=item.name,
                    credit_code=item.credit_code,
                    success=False,
                    error=str(e),
                )
            )
            fail_count += 1

    logger.info(
        "批量企业信息丰富 [user=%s]: total=%d, success=%d, fail=%d",
        current_user.id,
        total,
        success_count,
        fail_count,
    )

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": total,
            "success_count": success_count,
            "fail_count": fail_count,
            "results": [r.model_dump() for r in results],
        },
    )
