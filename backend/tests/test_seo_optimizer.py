#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试: JSON-LD结构化数据生成 + AI知识库提交工具
=============================================
覆盖率: JsonLdGenerator (7类) + KnowledgeGraphSubmitter (5类)
总共: ≥ 12 个测试用例
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── 确保能找到 seo_optimizer ─────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seo_optimizer import (
    JsonLdGenerator,
    KnowledgeGraphSubmitter,
    SITE_CONFIG,
)

# ═══════════════════════════════════════════════════════════════════════
# 1. 测试 JsonLdGenerator
# ═══════════════════════════════════════════════════════════════════════

def test_organization_jsonld():
    """测试 Organization JSON-LD 生成"""
    gen = JsonLdGenerator()
    org = gen.generate_organization()

    assert org["@type"] == "Organization"
    assert org["name"] == "链刻"
    assert org["url"] == "https://liankebao.top"
    assert org["logo"] == "https://liankebao.top/logo.png"
    assert "sameAs" in org
    assert len(org["sameAs"]) >= 2
    assert "contactPoint" in org
    assert org["contactPoint"]["email"] == "contact@liankebao.top"
    assert org["contactPoint"]["telephone"] == "+86-400-000-0000"
    print("  ✅ test_organization_jsonld PASS")


def test_website_jsonld():
    """测试 WebSite JSON-LD 生成（含搜索Action）"""
    gen = JsonLdGenerator()
    site = gen.generate_web_site()

    assert site["@type"] == "WebSite"
    assert site["name"] == "链刻"
    assert "potentialAction" in site
    action = site["potentialAction"]
    assert action["@type"] == "SearchAction"
    assert "{search_term_string}" in action["target"]["urlTemplate"]
    assert "query-input" in action
    print("  ✅ test_website_jsonld PASS")


def test_webpage_jsonld():
    """测试 WebPage JSON-LD 生成"""
    gen = JsonLdGenerator()
    page = gen.generate_web_page(
        title="测试页面",
        desc="这是一个测试页面描述",
        url="https://liankebao.top/test",
    )

    assert page["@type"] == "WebPage"
    assert page["name"] == "测试页面"
    assert page["description"] == "这是一个测试页面描述"
    assert page["url"] == "https://liankebao.top/test"
    assert page["inLanguage"] == "zh-CN"
    print("  ✅ test_webpage_jsonld PASS")


def test_breadcrumb_jsonld():
    """测试 BreadcrumbList JSON-LD 生成"""
    gen = JsonLdGenerator()
    path = [
        {"name": "首页", "url": "https://liankebao.top/"},
        {"name": "产品", "url": "https://liankebao.top/products"},
        {"name": "AI写作", "url": "https://liankebao.top/products/ai-writing"},
    ]
    bc = gen.generate_breadcrumb(path)

    assert bc["@type"] == "BreadcrumbList"
    assert len(bc["itemListElement"]) == 3
    for i, item in enumerate(bc["itemListElement"], start=1):
        assert item["position"] == i
        assert item["name"] == path[i - 1]["name"]
        assert item["item"] == path[i - 1]["url"]
    print("  ✅ test_breadcrumb_jsonld PASS")


def test_faq_jsonld():
    """测试 FAQPage JSON-LD 生成"""
    gen = JsonLdGenerator()
    questions = [
        {"question": "链刻是什么？", "answer": "链刻是一款AI知识管理平台。"},
        {"question": "如何开始使用？", "answer": "注册账号即可开始使用。"},
        {"question": "是否支持团队协作？", "answer": "支持多人实时协作。"},
    ]
    faq = gen.generate_faq(questions)

    assert faq["@type"] == "FAQPage"
    assert len(faq["mainEntity"]) == 3
    for i, qa in enumerate(faq["mainEntity"]):
        assert qa["@type"] == "Question"
        assert qa["name"] == questions[i]["question"]
        assert qa["acceptedAnswer"]["@type"] == "Answer"
        assert qa["acceptedAnswer"]["text"] == questions[i]["answer"]
    print("  ✅ test_faq_jsonld PASS")


def test_local_business_jsonld():
    """测试 LocalBusiness JSON-LD 生成"""
    gen = JsonLdGenerator()
    lb = gen.generate_local_business()

    assert lb["@type"] == "LocalBusiness"
    assert lb["name"] == "链刻"
    assert "telephone" in lb
    assert "address" in lb
    assert lb["address"]["@type"] == "PostalAddress"
    assert lb["address"]["addressCountry"] == "CN"
    print("  ✅ test_local_business_jsonld PASS")


def test_generate_all():
    """测试 generate_all() 合并所有JSON-LD"""
    gen = JsonLdGenerator()
    all_data = gen.generate_all()

    assert isinstance(all_data, list)
    assert len(all_data) >= 4  # Org + WebSite + WebPage + Breadcrumb

    types_found = [g["@type"] for g in all_data]
    assert "Organization" in types_found
    assert "WebSite" in types_found
    assert "WebPage" in types_found
    assert "BreadcrumbList" in types_found
    print("  ✅ test_generate_all PASS")


def test_generate_all_json_format():
    """测试 generate_all_json() 输出格式有效性"""
    gen = JsonLdGenerator()
    json_str = gen.generate_all_json()

    # 验证是有效的 JSON
    parsed = json.loads(json_str)
    assert "@context" in parsed
    assert parsed["@context"] == "https://schema.org"
    assert "@graph" in parsed
    assert len(parsed["@graph"]) >= 4
    print("  ✅ test_generate_all_json_format PASS")


def test_save_and_load_schema():
    """测试保存和加载 schema_org.json"""
    gen = JsonLdGenerator()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        out_path = f.name

    try:
        gen.save_schema_config(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "@graph" in data
        assert len(data["@graph"]) >= 4
    finally:
        os.unlink(out_path)
    print("  ✅ test_save_and_load_schema PASS")


def test_html_script_tag():
    """测试 to_html_script_tag 包装"""
    gen = JsonLdGenerator()
    json_str = gen.generate_all_json()
    html = gen.to_html_script_tag(json_str)

    assert html.startswith('<script type="application/ld+json">')
    assert html.endswith("</script>")
    assert "链刻" in html
    print("  ✅ test_html_script_tag PASS")


# ═══════════════════════════════════════════════════════════════════════
# 2. 测试 KnowledgeGraphSubmitter
# ═══════════════════════════════════════════════════════════════════════

def test_sitemap_generation():
    """测试 sitemap.xml 生成"""
    submitter = KnowledgeGraphSubmitter()
    urls = [
        {"loc": "https://liankebao.top/", "lastmod": "2025-01-01", "changefreq": "daily", "priority": "1.0"},
        {"loc": "https://liankebao.top/about", "lastmod": "2025-01-01", "changefreq": "monthly", "priority": "0.8"},
    ]
    content = submitter.generate_sitemap(urls)

    assert '<?xml version="1.0"' in content
    assert "<urlset" in content
    assert "https://liankebao.top/" in content
    assert "https://liankebao.top/about" in content
    assert "<priority>1.0</priority>" in content
    assert "<changefreq>daily</changefreq>" in content
    assert "<lastmod>2025-01-01</lastmod>" in content
    print("  ✅ test_sitemap_generation PASS")


def test_sitemap_save():
    """测试保存 sitemap.xml 到文件"""
    submitter = KnowledgeGraphSubmitter()
    urls = [
        {"loc": "https://liankebao.top/", "lastmod": "2025-01-01", "changefreq": "daily", "priority": "1.0"},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        out_path = f.name

    try:
        submitter.save_sitemap(urls, out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "https://liankebao.top/" in content
        assert "<urlset" in content
    finally:
        os.unlink(out_path)
    print("  ✅ test_sitemap_save PASS")


def test_robots_txt_generation():
    """测试 robots.txt 生成"""
    submitter = KnowledgeGraphSubmitter()
    robots = submitter.generate_robots_txt()

    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "Sitemap:" in robots
    assert "Disallow: /admin/" in robots
    assert "Disallow: /api/" in robots
    assert "User-agent: GPTBot" in robots
    assert "User-agent: Google-Extended" in robots
    assert "User-agent: CCBot" in robots
    assert "User-agent: anthropic-ai" in robots
    assert "User-agent: PerplexityBot" in robots
    print("  ✅ test_robots_txt_generation PASS")


def test_robots_txt_save():
    """测试保存 robots.txt 到文件"""
    submitter = KnowledgeGraphSubmitter()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        out_path = f.name

    try:
        submitter.save_robots_txt(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "User-agent: *" in content
        assert "Disallow: /admin/" in content
    finally:
        os.unlink(out_path)
    print("  ✅ test_robots_txt_save PASS")


def test_index_check_no_requests():
    """测试索引检查在无requests库时的降级行为"""
    submitter = KnowledgeGraphSubmitter()
    result = submitter.check_google_index("https://example.com")

    assert "url" in result
    assert "engine" in result
    assert "indexed" in result
    # 没有requests库时应该返回False且detail包含提示
    if not result["indexed"]:
        assert "not installed" in result["detail"] or "Error" in result["detail"]
    print("  ✅ test_index_check_no_requests PASS")


def test_submission_report():
    """测试生成提交报告"""
    submitter = KnowledgeGraphSubmitter()
    urls = [
        "https://liankebao.top/",
        "https://liankebao.top/about",
    ]
    report = submitter.generate_submission_report(urls)

    assert "generated_at" in report
    assert "base_url" in report
    assert report["base_url"] == "https://liankebao.top"
    assert report["total_urls"] == 2
    assert len(report["results"]) == 2
    assert "summary" in report
    assert "google_indexed" in report["summary"]
    assert "bing_indexed" in report["summary"]
    print("  ✅ test_submission_report PASS")


# ═══════════════════════════════════════════════════════════════════════
# 3. 验证 JSON-LD 语法有效性
# ═══════════════════════════════════════════════════════════════════════

def test_all_jsonld_valid_json():
    """验证所有JSON-LD输出都是合法的JSON"""
    gen = JsonLdGenerator()

    # 测试每一种生成器
    generators = [
        ("Organization", gen.generate_organization),
        ("WebSite", gen.generate_web_site),
        ("WebPage", lambda: gen.generate_web_page("T", "D", "https://example.com")),
        ("BreadcrumbList", lambda: gen.generate_breadcrumb([{"name": "首页", "url": "https://example.com"}])),
        ("FAQPage", lambda: gen.generate_faq([{"question": "Q?", "answer": "A."}])),
        ("LocalBusiness", gen.generate_local_business),
    ]

    for name, fn in generators:
        data = fn()
        # 确保可以序列化反序列化
        json_str = json.dumps(data, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["@type"] == name
    print("  ✅ test_all_jsonld_valid_json PASS")


def test_schema_org_file_exists():
    """测试 schema_org.json 文件存在且有效"""
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "seo", "schema_org.json"
    )
    assert os.path.exists(schema_path), f"File not found: {schema_path}"

    with open(schema_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "@graph" in data
    assert len(data["@graph"]) >= 4
    print("  ✅ test_schema_org_file_exists PASS")


# ═══════════════════════════════════════════════════════════════════════
# 运行全部测试
# ═══════════════════════════════════════════════════════════════════════

def run_all():
    tests = [
        # JsonLdGenerator (10 tests)
        test_organization_jsonld,
        test_website_jsonld,
        test_webpage_jsonld,
        test_breadcrumb_jsonld,
        test_faq_jsonld,
        test_local_business_jsonld,
        test_generate_all,
        test_generate_all_json_format,
        test_save_and_load_schema,
        test_html_script_tag,
        # KnowledgeGraphSubmitter (5 tests)
        test_sitemap_generation,
        test_sitemap_save,
        test_robots_txt_generation,
        test_robots_txt_save,
        test_index_check_no_requests,
        test_submission_report,
        # 验证 (2 tests)
        test_all_jsonld_valid_json,
        test_schema_org_file_exists,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_fn.__name__} FAILED: {e}")
            failed += 1

    total = len(tests)
    print(f"\n{'='*50}")
    print(f"📊 测试结果: {passed}/{total} 通过, {failed} 失败")
    if failed == 0:
        print("🎉 全部通过!")
    return failed == 0


if __name__ == "__main__":
    run_all()
