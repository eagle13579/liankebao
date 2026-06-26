#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEO Optimizer — JSON-LD结构化数据生成 + AI知识库提交工具
================================================================
赤鱬(P6, 内容运营, SEO/结构化数据)

功能:
  - JsonLdGenerator: 生成各类JSON-LD结构化数据
  - KnowledgeGraphSubmitter: 站点地图/robots.txt/AI知识库提交
  - CLI入口: --generate-all, --check-index, --sitemap

站点: https://liankebao.top
"""

import argparse
import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

# 确保可以找到 sibling 模块
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("seo_optimizer")

# ─── 站点配置 ─────────────────────────────────────────────────────────
SITE_CONFIG = {
    "name": "链刻",
    "full_name": "链刻 - AI知识管理与智能写作平台",
    "url": "https://liankebao.top",
    "logo_url": "https://liankebao.top/logo.png",
    "description": "链刻是一款AI驱动的知识管理与智能写作助手，帮助团队高效管理知识库、生成内容并优化SEO表现。",
    "language": "zh-CN",
    "social": {
        "github": "https://github.com/liankebao",
        "twitter": "https://twitter.com/liankebao",
    },
    "search_url": "https://liankebao.top/search?q={search_term_string}",
    "contact": {
        "email": "contact@liankebao.top",
        "phone": "+86-400-000-0000",
    },
    "address": {
        "street": "北京市海淀区中关村大街1号",
        "locality": "北京",
        "region": "北京市",
        "country": "CN",
        "postal_code": "100080",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Class: JsonLdGenerator
# ═══════════════════════════════════════════════════════════════════════
class JsonLdGenerator:
    """JSON-LD结构化数据生成器"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or SITE_CONFIG

    # ── 基础辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _ld_node(type_: str, **kwargs) -> Dict:
        """创建标准JSON-LD节点"""
        node = {
            "@context": "https://schema.org",
            "@type": type_,
        }
        node.update({k: v for k, v in kwargs.items() if v is not None})
        return node

    def _ld(self, type_: str, **kwargs) -> Dict:
        return self._ld_node(type_, **kwargs)

    # ── Organization ──────────────────────────────────────────────

    def generate_organization(self) -> Dict:
        """生成 Organization JSON-LD"""
        cfg = self.config
        node = self._ld(
            "Organization",
            name=cfg["name"],
            alternateName=cfg["full_name"],
            url=cfg["url"],
            logo=cfg["logo_url"],
            description=cfg["description"],
        )
        # 添加 sameAs 社交链接
        same_as = []
        for platform, link in cfg.get("social", {}).items():
            if link:
                same_as.append(link)
        if same_as:
            node["sameAs"] = same_as

        # 添加联系方式
        contact_point = {}
        email = cfg.get("contact", {}).get("email")
        phone = cfg.get("contact", {}).get("phone")
        if email:
            contact_point["email"] = email
        if phone:
            contact_point["telephone"] = phone
        if contact_point:
            contact_point["@type"] = "ContactPoint"
            contact_point["contactType"] = "customer service"
            node["contactPoint"] = contact_point

        return node

    # ── WebSite ──────────────────────────────────────────────────

    def generate_web_site(self) -> Dict:
        """生成 WebSite JSON-LD（含搜索Action）"""
        cfg = self.config
        node = self._ld(
            "WebSite",
            name=cfg["name"],
            url=cfg["url"],
            description=cfg["description"],
            inLanguage=cfg["language"],
        )
        # 站点搜索 Action
        search_url = cfg.get("search_url")
        if search_url:
            node["potentialAction"] = {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": search_url,
                },
                "query-input": "required name=search_term_string",
            }
        return node

    # ── WebPage ──────────────────────────────────────────────────

    def generate_web_page(self, title: str, desc: str, url: str) -> Dict:
        """生成 WebPage JSON-LD"""
        return self._ld(
            "WebPage",
            name=title,
            description=desc,
            url=url,
            inLanguage=self.config["language"],
            about=self.config["name"],
        )

    # ── BreadcrumbList ───────────────────────────────────────────

    def generate_breadcrumb(self, path: List[Dict]) -> Dict:
        """
        生成 BreadcrumbList JSON-LD
        path: [{"name": "首页", "url": "https://..."}, ...]
        """
        items = []
        for i, item in enumerate(path, start=1):
            items.append({
                "@type": "ListItem",
                "position": i,
                "name": item["name"],
                "item": item["url"],
            })
        return self._ld("BreadcrumbList", itemListElement=items)

    # ── LocalBusiness ────────────────────────────────────────────

    def generate_local_business(
        self, address: Optional[Dict] = None, phone: Optional[str] = None
    ) -> Dict:
        """生成 LocalBusiness JSON-LD"""
        cfg = self.config
        addr = address or cfg.get("address", {})
        phone = phone or cfg.get("contact", {}).get("phone")

        postal_address = {
            "@type": "PostalAddress",
            "streetAddress": addr.get("street", ""),
            "addressLocality": addr.get("locality", ""),
            "addressRegion": addr.get("region", ""),
            "addressCountry": addr.get("country", "CN"),
            "postalCode": addr.get("postal_code", ""),
        }

        node = self._ld(
            "LocalBusiness",
            name=cfg["name"],
            description=cfg["description"],
            url=cfg["url"],
            telephone=phone,
            address=postal_address,
        )
        return node

    # ── FAQPage ──────────────────────────────────────────────────

    def generate_faq(self, questions: List[Dict]) -> Dict:
        """
        生成 FAQPage JSON-LD
        questions: [{"question": "Q1?", "answer": "A1."}, ...]
        """
        main_entity = []
        for qa in questions:
            main_entity.append({
                "@type": "Question",
                "name": qa["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": qa["answer"],
                },
            })
        return self._ld("FAQPage", mainEntity=main_entity)

    # ── 合并全部 ─────────────────────────────────────────────────

    def generate_all(self) -> List[Dict]:
        """生成所有JSON-LD并合并到同一个 @graph 中"""
        graphs = [
            self.generate_organization(),
            self.generate_web_site(),
        ]
        # 默认首页 WebPage
        graphs.append(
            self.generate_web_page(
                title=self.config["full_name"],
                desc=self.config["description"],
                url=self.config["url"],
            )
        )
        # 默认面包屑
        graphs.append(
            self.generate_breadcrumb([
                {"name": "首页", "url": self.config["url"]},
            ])
        )
        return graphs

    def generate_all_json(self, indent: int = 2) -> str:
        """生成格式化的 JSON-LD 字符串（@graph 模式）"""
        graphs = self.generate_all()
        output = {"@context": "https://schema.org", "@graph": graphs}
        return json.dumps(output, ensure_ascii=False, indent=indent)

    def save_schema_config(self, output_path: str) -> str:
        """保存 schema_org.json 配置文件"""
        graphs = self.generate_all()
        output = {"@context": "https://schema.org", "@graph": graphs}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("✅ schema_org.json 已保存 → %s", output_path)
        return output_path

    def to_html_script_tag(self, json_str: str) -> str:
        """将JSON-LD包装为HTML script标签"""
        return f'<script type="application/ld+json">\n{json_str}\n</script>'


# ═══════════════════════════════════════════════════════════════════════
# Class: KnowledgeGraphSubmitter
# ═══════════════════════════════════════════════════════════════════════
class KnowledgeGraphSubmitter:
    """站点地图 & AI知识库提交工具"""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or SITE_CONFIG["url"]).rstrip("/")

    # ── 站点地图 ─────────────────────────────────────────────────

    def generate_sitemap(self, urls: List[Dict]) -> str:
        """
        生成 sitemap.xml 内容
        urls: [{"loc": "https://...", "lastmod": "2024-01-01", "priority": "0.8", "changefreq": "weekly"}, ...]
        """
        urlset = ET.Element("urlset")
        urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

        for entry in urls:
            u = ET.SubElement(urlset, "url")
            loc = ET.SubElement(u, "loc")
            loc.text = entry["loc"]
            if "lastmod" in entry and entry["lastmod"]:
                lm = ET.SubElement(u, "lastmod")
                lm.text = entry["lastmod"]
            if "changefreq" in entry and entry["changefreq"]:
                cf = ET.SubElement(u, "changefreq")
                cf.text = entry["changefreq"]
            if "priority" in entry and entry["priority"]:
                pr = ET.SubElement(u, "priority")
                pr.text = str(entry["priority"])

        # 美化输出
        rough_str = ET.tostring(urlset, encoding="unicode", short_empty_elements=True)
        # 用 minidom 美化
        import xml.dom.minidom
        dom = xml.dom.minidom.parseString(rough_str)
        pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
        # 去掉 XML 声明行 (保留 <?xml?> 符合标准)
        return pretty

    def save_sitemap(self, urls: List[Dict], output_path: str) -> str:
        """保存 sitemap.xml"""
        content = self.generate_sitemap(urls)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("✅ sitemap.xml 已保存 → %s", output_path)
        return output_path

    # ── robots.txt ───────────────────────────────────────────────

    def generate_robots_txt(self) -> str:
        """生成 robots.txt 建议内容"""
        lines = [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {self.base_url}/sitemap.xml",
            "",
            "# 禁止爬取敏感路径",
            "Disallow: /admin/",
            "Disallow: /api/",
            "Disallow: /private/",
            "Disallow: /temp/",
            "Disallow: /draft/",
            "Disallow: /_next/",
            "",
            "# 设置爬取间隔（建议值）",
            "Crawl-delay: 10",
            "",
            "# 指定AI知识库爬虫",
            "User-agent: GPTBot",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /api/",
            "",
            "User-agent: Google-Extended",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /api/",
            "",
            "User-agent: CCBot",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /api/",
            "",
            "User-agent: anthropic-ai",
            "Allow: /",
            "Disallow: /admin/",
            "",
            "User-agent: PerplexityBot",
            "Allow: /",
            "Disallow: /admin/",
            "",
            "# 生成时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]
        return "\n".join(lines)

    def save_robots_txt(self, output_path: str) -> str:
        """保存 robots.txt"""
        content = self.generate_robots_txt()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("✅ robots.txt 已保存 → %s", output_path)
        return output_path

    # ── 索引检查 ─────────────────────────────────────────────────

    def check_google_index(self, url: str) -> Dict:
        """
        检查 Google 是否已索引指定 URL
        使用 site: 查询方式（需要requests库）
        """
        result = {
            "url": url,
            "engine": "Google",
            "indexed": False,
            "detail": "",
            "checked_at": datetime.now().isoformat(),
        }
        try:
            import requests
            search_url = f"https://www.google.com/search?q=site:{url}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            resp = requests.get(search_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                # 如果搜索结果包含URL或"约多少条结果"表示已索引
                lower = resp.text.lower()
                if url.lower().rstrip("/") in lower or "条结果" in lower:
                    result["indexed"] = True
                    result["detail"] = "URL found in Google search results"
                else:
                    result["detail"] = "URL not found in search results"
            else:
                result["detail"] = f"HTTP {resp.status_code}"
        except ImportError:
            result["detail"] = "requests library not installed — cannot check"
        except Exception as e:
            result["detail"] = f"Error: {e}"
        return result

    def check_bing_index(self, url: str) -> Dict:
        """
        检查 Bing 是否已索引指定 URL
        """
        result = {
            "url": url,
            "engine": "Bing",
            "indexed": False,
            "detail": "",
            "checked_at": datetime.now().isoformat(),
        }
        try:
            import requests
            search_url = f"https://www.bing.com/search?q=site:{url}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            resp = requests.get(search_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                lower = resp.text.lower()
                if url.lower().rstrip("/") in lower or "条结果" in lower:
                    result["indexed"] = True
                    result["detail"] = "URL found in Bing search results"
                else:
                    result["detail"] = "URL not found in search results"
            else:
                result["detail"] = f"HTTP {resp.status_code}"
        except ImportError:
            result["detail"] = "requests library not installed — cannot check"
        except Exception as e:
            result["detail"] = f"Error: {e}"
        return result

    def generate_submission_report(self, urls: List[str]) -> Dict:
        """
        生成提交报告：检查多个URL在Google/Bing的索引状态
        """
        report = {
            "generated_at": datetime.now().isoformat(),
            "base_url": self.base_url,
            "total_urls": len(urls),
            "results": [],
        }
        for url in urls:
            google = self.check_google_index(url)
            bing = self.check_bing_index(url)
            report["results"].append({
                "url": url,
                "google": google,
                "bing": bing,
            })
        indexed_google = sum(1 for r in report["results"] if r["google"]["indexed"])
        indexed_bing = sum(1 for r in report["results"] if r["bing"]["indexed"])
        report["summary"] = {
            "google_indexed": indexed_google,
            "bing_indexed": indexed_bing,
        }
        return report


# ═══════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════
def cli():
    parser = argparse.ArgumentParser(
        description="SEO优化器 — JSON-LD结构化数据生成 + AI知识库提交工具"
    )
    parser.add_argument(
        "--generate-all",
        action="store_true",
        help="生成全部JSON-LD结构化数据并保存到 seo/schema_org.json",
    )
    parser.add_argument(
        "--check-index",
        type=str,
        nargs="?",
        const="https://liankebao.top",
        metavar="URL",
        help="检查指定URL在Google/Bing的索引状态",
    )
    parser.add_argument(
        "--sitemap",
        action="store_true",
        help="生成站点地图 sitemap.xml",
    )
    parser.add_argument(
        "--robots",
        action="store_true",
        help="生成 robots.txt",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="输出目录（默认: backend/seo/）",
    )
    parser.add_argument(
        "--to-html",
        action="store_true",
        help="输出JSON-LD时同时生成HTML script标签格式",
    )

    args = parser.parse_args()

    # 确定输出目录
    if args.output_dir:
        seo_dir = args.output_dir
    else:
        seo_dir = os.path.join(BACKEND_DIR, "seo")
    os.makedirs(seo_dir, exist_ok=True)

    generator = JsonLdGenerator()
    submitter = KnowledgeGraphSubmitter()

    # ── 生成全部 JSON-LD ────────────────────────────────────────
    if args.generate_all:
        schema_path = os.path.join(seo_dir, "schema_org.json")
        generator.save_schema_config(schema_path)

        if args.to_html:
            json_str = generator.generate_all_json()
            html_tag = generator.to_html_script_tag(json_str)
            html_path = os.path.join(seo_dir, "schema_org.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_tag)
            logger.info("✅ schema_org.html (script标签) 已保存 → %s", html_path)

        print("\n📋 生成的JSON-LD类型:")
        for g in generator.generate_all():
            print(f"   - {g['@type']}")
        print(f"\n🗂️  保存路径: {schema_path}")
        print(f"🔗 引用方式: <script type=\"application/ld+json\" src=\"/seo/schema_org.json\">")
        print("   或直接内联到首页 <head> 中。\n")

    # ── 检查索引状态 ─────────────────────────────────────────────
    if args.check_index:
        url = args.check_index
        print(f"\n🔍 检查索引状态: {url}")
        print("-" * 50)
        google = submitter.check_google_index(url)
        bing = submitter.check_bing_index(url)
        print(f"Google: {'✅ 已索引' if google['indexed'] else '❌ 未索引'} — {google['detail']}")
        print(f"Bing:   {'✅ 已索引' if bing['indexed'] else '❌ 未索引'} — {bing['detail']}")
        print()

    # ── 生成站点地图 ─────────────────────────────────────────────
    if args.sitemap:
        today = datetime.now().strftime("%Y-%m-%d")
        default_urls = [
            {"loc": f"{SITE_CONFIG['url']}/", "lastmod": today, "changefreq": "daily", "priority": "1.0"},
            {"loc": f"{SITE_CONFIG['url']}/about", "lastmod": today, "changefreq": "monthly", "priority": "0.8"},
            {"loc": f"{SITE_CONFIG['url']}/features", "lastmod": today, "changefreq": "weekly", "priority": "0.8"},
            {"loc": f"{SITE_CONFIG['url']}/pricing", "lastmod": today, "changefreq": "monthly", "priority": "0.7"},
            {"loc": f"{SITE_CONFIG['url']}/blog", "lastmod": today, "changefreq": "weekly", "priority": "0.6"},
            {"loc": f"{SITE_CONFIG['url']}/contact", "lastmod": today, "changefreq": "monthly", "priority": "0.5"},
            {"loc": f"{SITE_CONFIG['url']}/privacy", "lastmod": today, "changefreq": "yearly", "priority": "0.3"},
            {"loc": f"{SITE_CONFIG['url']}/terms", "lastmod": today, "changefreq": "yearly", "priority": "0.3"},
        ]
        sitemap_path = os.path.join(seo_dir, "sitemap.xml")
        submitter.save_sitemap(default_urls, sitemap_path)
        print(f"\n🗺️  站点地图已保存: {sitemap_path}")
        print(f"📦 包含 {len(default_urls)} 个URL\n")

    # ── 生成 robots.txt ──────────────────────────────────────────
    if args.robots:
        robots_path = os.path.join(seo_dir, "robots.txt")
        content = submitter.generate_robots_txt()
        with open(robots_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("✅ robots.txt 已保存 → %s", robots_path)
        print(f"\n🤖 robots.txt 已保存: {robots_path}\n")

    # 默认无参数时显示帮助
    if not any([args.generate_all, args.check_index, args.sitemap, args.robots]):
        parser.print_help()


if __name__ == "__main__":
    cli()
