"""
链客宝 Feature 模块 — 路由注册
==================================
注册 innovation_engine 和 design_review 两个 Feature 模块的 API 端点。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from features.innovation_engine import default_engine as innovation_engine
from features.design_review import default_engine as design_review_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/features", tags=["Features-智能特性"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================

class InnovationScanRequest(BaseModel):
    """创新扫描请求"""
    scan_category: Optional[str] = Field(None, description="机会扫描类别筛选")
    scan_min_pain: Optional[int] = Field(None, ge=1, le=10, description="机会扫描最小疼痛阈值 (1-10)")
    trend_category: Optional[str] = Field(None, description="趋势分析类别筛选")
    trend_min_momentum: Optional[float] = Field(None, ge=0, le=10, description="趋势分析最小动量值 (0-10)")
    top_k: Optional[int] = Field(None, ge=1, le=50, description="推荐返回数量上限")


class DesignReviewRequest(BaseModel):
    """审美评估请求"""
    design_data: dict = Field(..., description="设计数据字典")
    brand_name: Optional[str] = Field(None, description="自定义品牌名称（可选）")
    brand_primary_color: Optional[str] = Field(None, description="自定义品牌主色（可选）")
    brand_secondary_color: Optional[str] = Field(None, description="自定义品牌辅助色（可选）")
    report_format: str = Field("all", description="报告格式：dict / text / markdown / all")


# ============================================================
# API 端点
# ============================================================

@router.post(
    "/innovation/scan",
    summary="创新扫描",
    description="执行完整创新扫描流程：扫描机会 → 分析趋势 → 交叉推荐",
)
def innovation_scan(body: InnovationScanRequest):
    """
    运行创新发现引擎，返回包含机会扫描、趋势分析和交叉推荐在内的完整报告。
    """
    logger.info(f"[Features] 创新扫描请求: {body.model_dump(exclude_none=True)}")

    report = innovation_engine.run_innovation_scan(
        scan_category=body.scan_category,
        scan_min_pain=body.scan_min_pain,
        trend_category=body.trend_category,
        trend_min_momentum=body.trend_min_momentum,
        top_k=body.top_k,
    )

    return {
        "code": 200,
        "message": "创新扫描完成",
        "data": report.to_dict(),
    }


@router.post(
    "/design/review",
    summary="审美评估",
    description="执行完整审美评估流程：UI 一致性检查 → 品牌一致性检查 → 名片设计评估 → 报告生成",
)
def design_review(body: DesignReviewRequest):
    """
    运行审美评估系统，返回包含 UI 检查、品牌检查、名片评估和多种格式报告的完整结果。
    """
    logger.info(f"[Features] 审美评估请求: report_format={body.report_format}")

    # 构建可选品牌档案
    brand_profile = None
    if body.brand_name:
        from features.design_review.brand_checker import BrandProfile
        brand_profile = BrandProfile(
            name=body.brand_name,
            primary_color=body.brand_primary_color or "#1A73E8",
            secondary_color=body.brand_secondary_color or "#FFFFFF",
            font_families=["Inter", "PingFang SC"],
            tone="professional",
            has_logo=True,
            tagline="",
        )

    result = design_review_engine.run_design_review(
        design_data=body.design_data,
        brand_profile=brand_profile,
        report_format=body.report_format,
    )

    response_data = {
        "review_timestamp": result.review_timestamp,
        "report": result.report.to_dict() if result.report else None,
    }

    if result.report_text:
        response_data["report_text"] = result.report_text
    if result.report_markdown:
        response_data["report_markdown"] = result.report_markdown

    return {
        "code": 200,
        "message": "审美评估完成",
        "data": response_data,
    }


@router.get(
    "/health",
    summary="Features 模块健康检查",
    description="返回 features 模块中所有子模块的健康状态",
)
def features_health():
    """
    检查 innovation_engine 和 design_review 两个 Feature 模块的健康状态。
    """
    health_info = {
        "innovation_engine": {
            "status": "healthy",
            "version": "1.0.0",
            "components": ["opportunity_scanner", "trend_analyzer", "recommender"],
        },
        "design_review": {
            "status": "healthy",
            "version": "1.0.0",
            "components": ["ui_checker", "brand_checker", "card_design_evaluator", "report_generator"],
        },
    }

    # 简单自检：尝试实例化核心类
    all_healthy = True
    try:
        from features.innovation_engine import InnovationEngine
        eng = InnovationEngine()
        eng.run_innovation_scan(top_k=1)
    except Exception as e:
        health_info["innovation_engine"]["status"] = "degraded"
        health_info["innovation_engine"]["error"] = str(e)
        all_healthy = False

    try:
        from features.design_review import DesignReviewEngine
        dre = DesignReviewEngine()
        dre.run_design_review({"colors": []}, report_format="dict")
    except Exception as e:
        health_info["design_review"]["status"] = "degraded"
        health_info["design_review"]["error"] = str(e)
        all_healthy = False

    overall = "ok" if all_healthy else "degraded"

    return {
        "code": 200,
        "message": "Features 模块健康检查",
        "data": {
            "status": overall,
            "modules": health_info,
        },
    }
