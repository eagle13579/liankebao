"""
i18n 语言路由 — 从URL前缀提取语言参数注入请求上下文
====================================================
配合 nginx 多语言 location 块工作：

nginx 行为:
  - /en/*  → 剥离 /en/ 前缀后 proxy_pass 到后端, 附加 X-Lang-Prefix: en 请求头
  - /ko/*  → 同上, X-Lang-Prefix: ko
  - /      → 根据 Accept-Language 自动重定向到 /en/ 或 /ko/, 否则默认中文

本路由器:
  1. 提供 get_current_lang() 依赖 — 从 X-Lang-Prefix 头 / URL 前缀 / Accept-Language 提取语言
  2. 提供 get_current_translator() 依赖 — 返回当前语言的 Translator 实例
  3. 提供 SPA 页面回退路由 — /en/{path:path} 和 /ko/{path:path} 渲染对应语言的 index.html
"""

import os
import re
from pathlib import Path
from functools import lru_cache

from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import HTMLResponse, FileResponse, Response
from starlette.types import ASGIApp, Scope, Receive, Send

from app.i18n.translations import Translator, TRANSLATIONS, AVAILABLE_LANGUAGES

# ── Router 定义 ──────────────────────────────────────────────────────────────
router = APIRouter(tags=["i18n routing"])

# 前端构建产物目录 (Docker 环境为 /app/frontend, 本地开发可用环境变量覆盖)
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", "/app/frontend"))

# ── 支持的语言前缀映射 ──────────────────────────────────────────────────────
LANG_PREFIX_MAP = {"/en/": "en", "/ko/": "ko"}
LANG_PREFIXES = list(LANG_PREFIX_MAP.keys())  # ["/en/", "/ko/"]


# =============================================================================
# 语言提取依赖
# =============================================================================

def get_current_lang(request: Request) -> str:
    """
    从请求中提取当前语言代码。

    优先级（从高到低）:
      1. X-Lang-Prefix 请求头 (nginx 设置)
      2. URL 路径前缀 (/en/xxx → en, /ko/xxx → ko)
      3. Cookie `lang`
      4. Accept-Language 请求头
      5. 默认 "zh"
    """
    # ── 1. X-Lang-Prefix 请求头 (nginx 设置) ──
    lang = request.headers.get("X-Lang-Prefix", "")
    if lang in TRANSLATIONS:
        _inject_state(request, lang)
        return lang

    # ── 2. URL 路径前缀 ──
    path = request.url.path
    for prefix, code in LANG_PREFIX_MAP.items():
        if path.startswith(prefix):
            _inject_state(request, code)
            return code

    # ── 3. Cookie lang ──
    lang = request.cookies.get("lang", "")
    if lang in TRANSLATIONS:
        _inject_state(request, lang)
        return lang

    # ── 4. Accept-Language ──
    accept_lang = request.headers.get("accept-language", "")
    if accept_lang:
        parsed = _parse_accept_language(accept_lang)
        if parsed and parsed in TRANSLATIONS:
            _inject_state(request, parsed)
            return parsed

    # ── 5. 回退到中文 ──
    _inject_state(request, "zh")
    return "zh"


def _inject_state(request: Request, lang: str) -> None:
    """将语言状态注入 request.state"""
    request.state.lang = lang
    request.state.t = Translator(lang).t


@lru_cache(maxsize=64)
def _parse_accept_language(header: str) -> str | None:
    """
    解析 Accept-Language 请求头，返回第一个匹配的支持语言代码。
    缓存结果避免重复解析。

    示例:
      "ko-KR,ko;q=0.9,en;q=0.8,zh;q=0.7" → "ko"
      "en-US,en;q=0.9"                      → "en"
      "zh-CN,zh;q=0.9"                      → "zh"
    """
    pattern = re.compile(r"([a-z]{2})(?:-[A-Za-z]+)?(?:\s*;\s*q\s*=\s*([\d.]+))?")
    candidates: list[tuple[float, str]] = []
    for segment in header.split(","):
        segment = segment.strip()
        m = pattern.match(segment)
        if m:
            code = m.group(1)
            q = float(m.group(2)) if m.group(2) else 1.0
            if code in TRANSLATIONS:
                candidates.append((q, code))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def get_current_translator(request: Request) -> Translator:
    """返回当前语言的 Translator 实例（已自动选择语言）"""
    lang = get_current_lang(request)
    return Translator(lang)


# =============================================================================
# SPA 多语言页面回退路由
# =============================================================================
# 当用户通过 /en/xxx 或 /ko/xxx 直接访问 SPA 页面时，
# nginx 会将请求代理到后端（含 X-Lang-Prefix 头），
# 本路由确保 SPA index.html 被正确返回。

async def _serve_spa_index(lang: str) -> Response:
    """返回对应语言的 SPA 入口页面"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        # 在 HTML 中注入 lang 属性
        content = content.replace(
            "<html", f'<html lang="{lang}"'
        )
        return HTMLResponse(content=content)
    return HTMLResponse(
        content=f"<!DOCTYPE html><html lang=\"{lang}\"><head><title>链客宝</title></head><body><div id=\"root\"></div></body></html>"
    )


@router.get("/en", include_in_schema=False)
async def en_root(request: Request):
    """英文首页 — /en 不带末尾斜杠时 301 到 /en/"""
    return Response(status_code=301, headers={"location": "/en/"})


@router.get("/ko", include_in_schema=False)
async def ko_root(request: Request):
    """韩文首页 — /ko 不带末尾斜杠时 301 到 /ko/"""
    return Response(status_code=301, headers={"location": "/ko/"})


@router.get("/en/{path:path}", include_in_schema=False)
async def en_spa_fallback(request: Request, path: str):
    """英文 SPA 页面回退 — 所有 /en/* 路径"""
    lang = get_current_lang(request)
    return await _serve_spa_index(lang)


@router.get("/ko/{path:path}", include_in_schema=False)
async def ko_spa_fallback(request: Request, path: str):
    """韩文 SPA 页面回退 — 所有 /ko/* 路径"""
    lang = get_current_lang(request)
    return await _serve_spa_index(lang)


# =============================================================================
# API 端点: 获取当前语言 / 切换语言
# =============================================================================

@router.get("/api/v1/i18n/current-lang", tags=["多语言 i18n"])
async def current_lang(lang: str = Depends(get_current_lang)):
    """返回当前请求的语言代码"""
    return {"lang": lang}


@router.get("/api/v1/i18n/set-lang", tags=["多语言 i18n"])
async def set_lang(
    lang: str = Query(..., description="目标语言代码 (zh/en/ko)"),
    request: Request = None,
):
    """
    切换语言并返回对应的翻译包。
    前端可通过此端点切换语言，返回翻译字典供前端动态更新。
    """
    if lang not in TRANSLATIONS:
        lang = "zh"
    translations = Translator.get_translations(lang)
    return {
        "lang": lang,
        "translations": translations,
        "available_languages": AVAILABLE_LANGUAGES,
    }


# =============================================================================
# ASGI 中间件: URL 前缀语言注入（兜底方案）
# =============================================================================
# 当 nginx 未配置剥离前缀时，此中间件会从 URL 路径提取语言前缀，
# 将其注入 scope state，并重写路径（剥离前缀）后继续处理。

class LangPrefixMiddleware:
    """
    语言前缀中间件 — 在 ASGI scope level 从 URL 提取语言前缀并注入 state。

    功能:
      1. 检测 URL 是否以 /en/ 或 /ko/ 开头
      2. 若匹配，将语言代码注入 scope["state"]["lang_from_prefix"]
      3. 不修改路径（留给 nginx 或应用层处理）

    注册方式（在 main.py 中）:
      app.add_middleware(LangPrefixMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        for prefix, code in LANG_PREFIX_MAP.items():
            if path.startswith(prefix):
                # 将语言注入 scope state
                if "state" not in scope:
                    scope["state"] = {}
                scope["state"]["lang_from_path"] = code
                break

        await self.app(scope, receive, send)
