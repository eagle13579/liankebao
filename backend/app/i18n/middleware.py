"""
I18nMiddleware — 多语言中间件
==============================
从请求头 Accept-Language 或 Cookie lang 检测语言，
设置 request.state.lang 和 request.state.t (翻译函数).
默认中文，无匹配回退到中文.
"""

from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.requests import HTTPConnection
import re

from app.i18n.translations import Translator, TRANSLATIONS


# 解析 Accept-Language，取第一个支持的语言
def _detect_language(accept_language: str | None) -> str:
    if not accept_language:
        return "zh"

    # 解析 q 值排序的语言列表
    # e.g. "ko-KR,ko;q=0.9,en;q=0.8,zh;q=0.7"
    pattern = re.compile(r"([a-z]{2})(?:-[A-Za-z]+)?(?:\s*;\s*q\s*=\s*([\d.]+))?")
    candidates: list[tuple[float, str]] = []
    for segment in accept_language.split(","):
        segment = segment.strip()
        m = pattern.match(segment)
        if m:
            lang_code = m.group(1)
            q = float(m.group(2)) if m.group(2) else 1.0
            if lang_code in TRANSLATIONS:
                candidates.append((q, lang_code))

    if not candidates:
        return "zh"

    # 按 q 值降序排列
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _get_cookie(scope: Scope, name: str) -> str:
    """从 scope headers 中解析指定 cookie 值"""
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            cookie_str = value.decode("utf-8", errors="replace")
            for part in cookie_str.split(";"):
                part = part.strip()
                if part.startswith(f"{name}="):
                    return part[len(name) + 1:]
    return ""


def _get_header(scope: Scope, name: bytes) -> str:
    """从 scope headers 中获取请求头值"""
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("utf-8", errors="replace")
    return ""


class I18nMiddleware:
    """多语言中间件 — 在 ASGI scope level 注入 i18n 状态

    用法:
        app.add_middleware(I18nMiddleware)

    注入:
        scope["state"]["lang"] — 当前语言代码
        scope["state"]["t"]    — 翻译函数 (translator.t)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 0. 优先从 X-Lang-Prefix 请求头读取 (nginx /en/ /ko/ 剥离前缀后设置)
        lang = _get_header(scope, b"x-lang-prefix")

        # 1. 其次从 Cookie 读取
        if not lang or lang not in TRANSLATIONS:
            lang = _get_cookie(scope, "lang")

        # 2. 从 Accept-Language 头检测
        if not lang or lang not in TRANSLATIONS:
            accept_lang = _get_header(scope, b"accept-language")
            lang = _detect_language(accept_language=accept_lang)

        # 3. 最终回退到中文
        if lang not in TRANSLATIONS:
            lang = "zh"

        # 4. 注入 scope state（FastAPI/Starlette 会将其映射到 request.state）
        translator = Translator(lang)
        scope["state"] = {
            "lang": lang,
            "t": translator.t,
        }

        await self.app(scope, receive, send)
