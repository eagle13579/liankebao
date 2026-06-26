# 链客宝 SEO 优化配置 / sitemap 生成器
import datetime
from fastapi import APIRouter, Response
from app.i18n.translations import TRANSLATIONS, AVAILABLE_LANGUAGES

router = APIRouter(tags=["seo"])

SITE_URL = "https://liankebao.top"
SITE_NAME = "链客宝 - AI企业智能匹配平台"
SITE_DESC = "链客宝是AI驱动的企业智能匹配平台，基于三塔DNN和知识图谱技术，为企业提供精准的供需匹配、信任评估和商业合作服务。"

# ── 页面定义 ────────────────────────────────────────────────────────────────
# 每个页面按语言版本分别生成 <url> 条目，内含 xhtml:link 指向各语言版本
PAGES = [
    {"loc": "", "priority": "1.0", "changefreq": "daily"},       # 首页
    {"loc": "/login", "priority": "0.6", "changefreq": "monthly"},
    {"loc": "/business-card", "priority": "0.8", "changefreq": "weekly"},
    {"loc": "/trust", "priority": "0.7", "changefreq": "weekly"},
    {"loc": "/onboarding", "priority": "0.5", "changefreq": "monthly"},
    {"loc": "/admin", "priority": "0.4", "changefreq": "monthly"},
    {"loc": "/pricing", "priority": "0.8", "changefreq": "weekly"},
    {"loc": "/about", "priority": "0.5", "changefreq": "monthly"},
]

# 语言代码 → hreflang 代码映射
HREFLANG_MAP = {
    "zh": "zh-CN",
    "en": "en",
    "ko": "ko",
}


def _generate_urlset() -> str:
    """生成包含完整多语言 urlset 的 XML 字符串"""
    today = datetime.date.today().isoformat()
    url_entries: list[str] = []

    for page in PAGES:
        loc_path = page["loc"]
        priority = page["priority"]
        changefreq = page["changefreq"]

        for lang_code in AVAILABLE_LANGUAGES:
            hreflang = HREFLANG_MAP.get(lang_code, lang_code)

            if lang_code == "zh":
                # 中文版：无前缀路径
                page_url = f"{SITE_URL}{loc_path}"
            else:
                # 英文/韩文版：/en/xxx, /ko/xxx
                page_url = f"{SITE_URL}/{lang_code}{loc_path}"

            # 构建 xhtml:link 交替语言链接 (包含所有语言 + x-default)
            alternates = []
            for alt_lang in AVAILABLE_LANGUAGES:
                alt_hreflang = HREFLANG_MAP.get(alt_lang, alt_lang)
                if alt_lang == "zh":
                    alt_url = f"{SITE_URL}{loc_path}"
                else:
                    alt_url = f"{SITE_URL}/{alt_lang}{loc_path}"
                alternates.append(
                    f'    <xhtml:link rel="alternate" hreflang="{alt_hreflang}" href="{alt_url}"/>'
                )
            # x-default 指向中文版
            alternates.append(
                f'    <xhtml:link rel="alternate" hreflang="x-default" href="{SITE_URL}{loc_path}"/>'
            )

            url_entry = f"""  <url>
    <loc>{page_url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
{chr(10).join(alternates)}
  </url>"""
            url_entries.append(url_entry)

    urls_xml = "\n".join(url_entries)
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
{urls_xml}
</urlset>'''
    return xml


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    """生成多语言 sitemap.xml — 每个页面按语言分别列出，含 xhtml:link hreflang 交替链接"""
    xml = _generate_urlset()
    return Response(content=xml, media_type="application/xml")


@router.get("/robots.txt", include_in_schema=False)
async def robots():
    """Generate robots.txt"""
    content = f"""User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /_nuxt/

Sitemap: {SITE_URL}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")


@router.get("/seo/json-ld", include_in_schema=False)
async def json_ld():
    """Generate JSON-LD structured data"""
    import json
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{SITE_URL}/#organization",
                "name": "链客宝",
                "url": SITE_URL,
                "description": SITE_DESC,
                "foundingDate": "2024",
                "areaServed": ["CN", "KR", "US"],
                "knowsAbout": "企业智能匹配、AI商业配对",
            },
            {
                "@type": "WebSite",
                "@id": f"{SITE_URL}/#website",
                "url": SITE_URL,
                "name": SITE_NAME,
                "description": SITE_DESC,
                "publisher": {"@id": f"{SITE_URL}/#organization"},
                "inLanguage": ["zh-CN", "en", "ko"],
            },
        ]
    }
    return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/ld+json")
