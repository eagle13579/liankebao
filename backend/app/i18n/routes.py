"""
i18n API 路由
==============
- GET /api/v1/i18n/translations?lang=ko → 返回该语言全部翻译
- GET /api/v1/i18n/languages           → 返回可用语言列表
"""

from fastapi import APIRouter, Query

from app.i18n.translations import Translator

i18n_bp = APIRouter(prefix="/api/v1/i18n", tags=["多语言 i18n"])


@i18n_bp.get("/translations")
async def get_translations(lang: str = Query("zh", description="语言代码")):
    """获取指定语言的完整翻译字典"""
    translations = Translator.get_translations(lang)
    return {
        "lang": lang if lang in Translator.available_languages() else "zh",
        "translations": translations,
    }


@i18n_bp.get("/languages")
async def get_languages():
    """返回可用语言列表"""
    return {
        "languages": Translator.available_languages(),
        "default": "zh",
    }
