"""
数据丰富 API 路由

提供企业信息丰富端点：
- GET /api/v1/enrich/company?name=xxx — 企业信息丰富
- GET /api/v1/enrich/contacts?company=xxx — 获取企业联系人
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.models import User
from app.schemas import ApiResponse
from app.services.data_enrichment import get_enricher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enrich", tags=["数据丰富"])


@router.get("/company", response_model=ApiResponse)
async def enrich_company(
    name: str = Query(..., min_length=1, description="企业名称（全称或关键词）"),
    current_user: User = Depends(get_current_user),
):
    """
    企业信息丰富

    根据企业名称搜索并返回企业基本信息、经营范围和联系人信息。
    数据来源：企查查/天眼查（模拟API，生产环境切换为真实API）。
    结果带有缓存（24小时有效期）。
    """
    try:
        enricher = get_enricher()
        result = enricher.enrich(name)
        return ApiResponse(
            code=200,
            message="success",
            data=result,
        )
    except Exception as exc:
        logger.error("企业信息丰富失败 (name=%s): %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据丰富服务异常: {str(exc)}")


@router.get("/company/basic", response_model=ApiResponse)
async def enrich_company_basic(
    name: str = Query(..., min_length=1, description="企业名称"),
    current_user: User = Depends(get_current_user),
):
    """
    企业基本信息查询

    仅返回企业的工商基本信息（名称、信用代码、法人、注册资本、行业等）。
    """
    try:
        enricher = get_enricher()
        result = enricher.search_company(name)
        return ApiResponse(
            code=200,
            message="success",
            data=result,
        )
    except Exception as exc:
        logger.error("企业基本信息查询失败 (name=%s): %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据丰富服务异常: {str(exc)}")


@router.get("/company/scope", response_model=ApiResponse)
async def enrich_company_scope(
    name: str = Query(..., min_length=1, description="企业名称"),
    current_user: User = Depends(get_current_user),
):
    """
    企业经营范围查询

    返回企业的经营范围、所属行业等信息。
    """
    try:
        enricher = get_enricher()
        result = enricher.get_business_scope(name)
        return ApiResponse(
            code=200,
            message="success",
            data=result,
        )
    except Exception as exc:
        logger.error("经营范围查询失败 (name=%s): %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据丰富服务异常: {str(exc)}")


@router.get("/contacts", response_model=ApiResponse)
async def enrich_contacts(
    company: str = Query(..., min_length=1, description="企业名称"),
    current_user: User = Depends(get_current_user),
):
    """
    获取企业联系人

    返回企业的联系人列表、电话、邮箱、地址等信息。
    """
    try:
        enricher = get_enricher()
        result = enricher.get_contacts(company)
        return ApiResponse(
            code=200,
            message="success",
            data=result,
        )
    except Exception as exc:
        logger.error("企业联系人查询失败 (company=%s): %s", company, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据丰富服务异常: {str(exc)}")
