#!/usr/bin/env python3
"""
Fix the i18n approach in digital_brochure_api.py:
Use context var for language instead of 'request' variable hack.
"""
import sys

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add _lang_var context var after the _trace_id_var declaration
    old_trace_var = "_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='')"
    new_trace_var = "_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='')\n_lang_var: contextvars.ContextVar[str] = contextvars.ContextVar('lang', default='zh')"
    content = content.replace(old_trace_var, new_trace_var)

    # 2. Update I18nLanguageMiddleware to set _lang_var
    old_middleware = """class I18nLanguageMiddleware(BaseHTTPMiddleware):
    \"\"\"国际化中间件: 从 Accept-Language 检测语言并注入 request.state.lang\"\"\"

    async def dispatch(self, request: Request, call_next):
        accept_lang = request.headers.get("Accept-Language", "")
        lang = detect_lang(accept_lang)
        request.state.lang = lang
        response = await call_next(request)
        response.headers["X-Content-Language"] = lang
        return response"""

    new_middleware = """class I18nLanguageMiddleware(BaseHTTPMiddleware):
    \"\"\"国际化中间件: 从 Accept-Language 检测语言并设置 _lang_var\"\"\"

    async def dispatch(self, request: Request, call_next):
        accept_lang = request.headers.get("Accept-Language", "")
        lang = detect_lang(accept_lang)
        _lang_var.set(lang)
        request.state.lang = lang
        response = await call_next(request)
        response.headers["X-Content-Language"] = lang
        return response"""

    content = content.replace(old_middleware, new_middleware)

    # 3. Replace all verbose `getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh"` with `_lang_var.get()`
    old_pattern = 'getattr(request.state, "lang", "zh") if hasattr(request, "state") else "zh"'
    content = content.replace(old_pattern, '_lang_var.get()')

    # 4. Also handle the health check function's lang detection
    old_health_lang = 'detect_lang(request.headers.get("Accept-Language", "")) if request else "zh"'
    new_health_lang = '_lang_var.get() or detect_lang(request.headers.get("Accept-Language", "")) if request else "zh"'
    content = content.replace(old_health_lang, new_health_lang)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Fixed: {filepath}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/var/www/liankebao/backend/digital_brochure_api.py"
    fix_file(path)
