"""冷启动引导 — 路由层

端点：
  GET /api/v1/onboarding/templates  → 预设模板列表
  GET /api/v1/onboarding/defaults   → 三步引导默认填充
"""

from fastapi import APIRouter

from app.services.onboarding_service import get_templates, get_defaults

router = APIRouter(prefix="/api/v1/onboarding", tags=["冷启动引导"])


@router.get("/templates")
async def list_templates():
    """获取预设模板列表（6个模板，含 id/name/description/preview_color/tags）"""
    return {
        "code": 0,
        "message": "success",
        "data": get_templates(),
    }


@router.get("/defaults")
async def get_defaults_config():
    """获取三步引导配置（步骤名/描述/默认字段值）"""
    return {
        "code": 0,
        "message": "success",
        "data": get_defaults(),
    }
