"""
JSON-LD 结构化数据注入中间件
================================
自动在 HTML 页面底部注入 JSON-LD script 标签，提升搜索引擎对网站的理解能力。

注入的 Schema:
    1. WebSite — 站点头部信息，含 SearchAction
    2. Organization — 组织信息，含 logo、sameAs 链接
    3. Product — 产品详情页自动检测并注入 (URL 匹配 /products/<id> 模式)

使用方式:
    app.add_middleware(JsonLdMiddleware)
"""

from __future__ import annotations

import json
import re
import logging
from typing import Pattern

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ===================================================================
# 常量配置
# ===================================================================

SITE_URL = "https://liankebao.top"
SITE_NAME = "链客宝"
SITE_DESC = "链客宝是AI驱动的企业智能匹配平台，基于三塔DNN和知识图谱技术，为企业提供精准的供需匹配、信任评估和商业合作服务。"
SITE_LOGO = f"{SITE_URL}/logo.png"

# 社交媒体同站链接
SAME_AS = [
    "https://www.linkedin.com/company/liankebao",
    # 微信公众平台（占位，请替换为实际链接）
    # "https://weixin.qq.com/s/xxx",
]

# 产品详情页 URL 匹配模式
# 匹配 SPA 路由: /products/123, /product/123, /en/products/123 等
PRODUCT_URL_PATTERN: Pattern = re.compile(
    r"^/(?:(?:zh-CN|en|ko)/)?(?:product|products|item)/(?P<product_id>\d+)(?:/.*)?$"
)

# ===================================================================
# Schema 构建函数
# ===================================================================


def build_website_schema() -> dict:
    """构建 WebSite Schema (含 SearchAction)"""
    return {
        "@type": "WebSite",
        "@id": f"{SITE_URL}/#website",
        "url": SITE_URL,
        "name": SITE_NAME,
        "description": SITE_DESC,
        "inLanguage": ["zh-CN", "en", "ko"],
        "publisher": {"@id": f"{SITE_URL}/#organization"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{SITE_URL}/search?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def build_organization_schema() -> dict:
    """构建 Organization Schema"""
    return {
        "@type": "Organization",
        "@id": f"{SITE_URL}/#organization",
        "name": SITE_NAME,
        "url": SITE_URL,
        "logo": {
            "@type": "ImageObject",
            "url": SITE_LOGO,
            "width": 512,
            "height": 512,
        },
        "description": SITE_DESC,
        "foundingDate": "2024",
        "areaServed": "CN",
        "knowsAbout": "企业智能匹配、AI商业配对、供需对接",
        "sameAs": SAME_AS if SAME_AS else None,
    }


def build_product_schema(product_id: str, request: Request) -> dict | None:
    """
    构建 Product Schema。
    从请求中提取产品信息，如果无法获取则返回包含 ID 的基础结构。
    """
    return {
        "@type": "Product",
        "@id": f"{SITE_URL}/products/{product_id}#product",
        "name": f"链客宝产品 #{product_id}",
        "description": f"链客宝平台产品，ID: {product_id}。更多详情请访问产品页面。",
        "url": str(request.url),
        "offers": {
            "@type": "Offer",
            "priceCurrency": "CNY",
            "availability": "https://schema.org/InStock",
            "url": str(request.url),
        },
        "category": "企业服务",
    }


# ===================================================================
# 中间件
# ===================================================================


class JsonLdMiddleware(BaseHTTPMiddleware):
    """
    JSON-LD 结构化数据注入中间件。

    拦截所有 Content-Type 为 text/html 的响应，在 </body> 前插入
    JSON-LD script 标签。WebSite 和 Organization Schema 注入到所有
    页面，Product Schema 仅在检测到产品详情页时注入。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # 预构建全局 Schema（WebSite + Organization），避免每次请求重复构建
        self._global_schemas = [
            build_website_schema(),
            build_organization_schema(),
        ]
        logger.info(
            "[JsonLdMiddleware] 已初始化: WebSite + Organization Schema 预构建完成"
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # ── 仅处理 HTML 响应 ──────────────────────────────────────
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return response

        # ── 跳过 API 和非 HTML 端点 ───────────────────────────────
        path = request.url.path
        if path.startswith(("/api/", "/health")):
            return response

        # ── 尝试读取响应体 ─────────────────────────────────────────
        try:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
        except Exception:
            logger.warning("[JsonLdMiddleware] 无法读取响应体: %s", path)
            return response

        if not body:
            return response

        body_str = body.decode("utf-8")

        # ── 检查是否已存在 JSON-LD（避免重复注入） ─────────────────
        if 'application/ld+json' in body_str or 'type="application/ld+json"' in body_str:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # ── 构建本次请求的 Schema 列表 ─────────────────────────────
        schemas = list(self._global_schemas)

        # 自动检测产品详情页
        product_match = PRODUCT_URL_PATTERN.match(path)
        if product_match:
            product_id = product_match.group("product_id")
            product_schema = build_product_schema(product_id, request)
            if product_schema:
                schemas.append(product_schema)
                logger.info(
                    "[JsonLdMiddleware] 产品详情页检测: id=%s, path=%s",
                    product_id,
                    path,
                )

        # ── 生成 JSON-LD 标签 ─────────────────────────────────────
        json_ld_html = self._build_json_ld_html(schemas)

        # ── 注入到 </body> 前 ─────────────────────────────────────
        if "</body>" in body_str:
            body_str = body_str.replace("</body>", f"{json_ld_html}\n</body>")
        elif "</html>" in body_str:
            body_str = body_str.replace("</html>", f"{json_ld_html}\n</html>")
        else:
            # 没有 body/html 标签，追加到末尾
            body_str += f"\n{json_ld_html}\n"

        # ── 重新构建响应 ───────────────────────────────────────────
        new_body = body_str.encode("utf-8")
        headers = dict(response.headers)
        headers["content-length"] = str(len(new_body))

        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )

    @staticmethod
    def _build_json_ld_html(schemas: list[dict]) -> str:
        """将 Schema 列表渲染为 JSON-LD HTML 标签"""
        graph = {
            "@context": "https://schema.org",
            "@graph": schemas,
        }
        json_str = json.dumps(graph, ensure_ascii=False, indent=2)
        return f'<script type="application/ld+json">\n{json_str}\n</script>'
