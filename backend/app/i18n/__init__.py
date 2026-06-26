"""
链客宝 i18n 多语言模块
======================
提供中文(zh)、韩语(ko)、英语(en)三语支持。

导出：
  - Translator       翻译器类
  - I18nMiddleware   中间件
  - i18n_bp          API 路由器
"""

from app.i18n.translations import Translator
from app.i18n.middleware import I18nMiddleware
from app.i18n.routes import i18n_bp

__all__ = [
    "Translator",
    "I18nMiddleware",
    "i18n_bp",
]
