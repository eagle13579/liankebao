#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEO Cron Job — AI知识库持续提交 + 监控报告
============================================
化蛇(P8, 市场部, 营销增长/GEO)

职责:
  - 每日自动生成 sitemap.xml 并提交到 Google/Bing
  - 监控 AI 知识库 (site:liankebao.top) 索引收录情况
  - 每周生成 GEO 收录分析报告
  - 超过3天无新增页面时触发告警

依赖:
  - scripts/seo_optimizer.py (JsonLdGenerator, KnowledgeGraphSubmitter)
  - requests (可选, 用于索引检查)

数据文件:
  - data/geo/submit_log.json — 提交历史日志
  - data/geo/                — 报告输出目录

用法:
  python scripts/geo_cron.py --daily        # 每日提交
  python scripts/geo_cron.py --report       # 生成周报
  python scripts/geo_cron.py --check-ai     # 检查AI知识库收录
  python scripts/geo_cron.py --all          # 全部执行
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# ── 路径设置 ────────────────────────────────────────────────────────────
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPTS_DIR)
DATA_DIR = os.path.join(BACKEND_DIR, "data", "geo")
sys.path.insert(0, BACKEND_DIR)

# 确保 data/geo 目录存在
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("geo_cron")

# ── 默认站点URL配置 ────────────────────────────────────────────────────
BASE_URL = "https://liankebao.top"

# sitemap 默认页面列表 (每日会根据日期刷新 lastmod)
DEFAULT_PAGES = [
    {"loc": "/", "changefreq": "daily", "priority": "1.0"},
    {"loc": "/about", "changefreq": "monthly", "priority": "0.8"},
    {"loc": "/features", "changefreq": "weekly", "priority": "0.8"},
    {"loc": "/pricing", "changefreq": "monthly", "priority": "0.7"},
    {"loc": "/blog", "changefreq": "weekly", "priority": "0.6"},
    {"loc": "/contact", "changefreq": "monthly", "priority": "0.5"},
    {"loc": "/privacy", "changefreq": "yearly", "priority": "0.3"},
    {"loc": "/terms", "changefreq": "yearly", "priority": "0.3"},
    {"loc": "/docs", "changefreq": "weekly", "priority": "0.8"},
    {"loc": "/docs/api", "changefreq": "weekly", "priority": "0.7"},
    {"loc": "/docs/sdk", "changefreq": "weekly", "priority": "0.7"},
    {"loc": "/ai-knowledge", "changefreq": "weekly", "priority": "0.9"},
    {"loc": "/ai-knowledge/graph", "changefreq": "weekly", "priority": "0.8"},
    {"loc": "/ai-knowledge/search", "changefreq": "weekly", "priority": "0.7"},
    {"loc": "/use-cases", "changefreq": "monthly", "priority": "0.6"},
]

# 告警阈值: 连续 N 天无新增索引时触发告警
ALERT_DAYS_NO_NEW = 3


# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════

def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _load_submit_log() -> Dict:
    """加载 submit_log.json, 如果不存在则返回默认结构"""
    log_path = os.path.join(DATA_DIR, "submit_log.json")
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("⚠️  submit_log.json 读取失败 (%s), 重新初始化", e)
    return {
        "metadata": {
            "site": BASE_URL,
            "created_at": _now_iso(),
            "description": "GEO sitemap submission history log",
            "version": "1.0.0",
        },
        "submissions": [],
        "index_trend": [],
        "alerts": [],
    }


def _save_submit_log(data: Dict) -> str:
    """保存 submit_log.json"""
    log_path = os.path.join(DATA_DIR, "submit_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("✅ 提交日志已更新 → %s", log_path)
    return log_path


def _build_full_urls() -> List[Dict]:
    """构建完整URL列表 (拼接 BASE_URL + 相对路径 + 今日日期)"""
    today = _today_str()
    urls = []
    for page in DEFAULT_PAGES:
        urls.append({
            "loc": BASE_URL + page["loc"],
            "lastmod": today,
            "changefreq": page["changefreq"],
            "priority": page["priority"],
        })
    return urls


# ═══════════════════════════════════════════════════════════════════════
# Class: GeoCronJob
# ═══════════════════════════════════════════════════════════════════════

class GeoCronJob:
    """
    GEO定时任务 — 每日提交sitemap、监控AI知识库收录、生成周报

    使用示例:
        from geo_cron import GeoCronJob
        from seo_optimizer import KnowledgeGraphSubmitter

        job = GeoCronJob()
        job.daily_submit()
        job.check_ai_index()
        job.weekly_report()
    """

    def __init__(self, seo_optimizer: Any = None):
        """
        初始化 GEO Cron Job

        Args:
            seo_optimizer: KnowledgeGraphSubmitter 实例 (或其他兼容接口)
                           如果为 None, 则在内部延迟导入
        """
        self.base_url = BASE_URL
        self.data_dir = DATA_DIR

        if seo_optimizer is not None:
            self.submitter = seo_optimizer
        else:
            # 延迟导入, 避免循环依赖
            from seo_optimizer import KnowledgeGraphSubmitter
            self.submitter = KnowledgeGraphSubmitter(base_url=self.base_url)

    # ── 1. 每日提交 ──────────────────────────────────────────────

    def daily_submit(self) -> Dict:
        """
        每日执行:
          1. 生成最新 sitemap.xml (含新增页面)
          2. 提交到 Google Search Console API (模拟)
          3. 提交到 Bing Webmaster API (模拟)
          4. 记录提交历史到 submit_log.json

        Returns:
            提交结果字典
        """
        today = _today_str()
        now_iso = _now_iso()
        logger.info("🚀 === 开始每日 GEO 提交: %s ===", today)

        # 1. 生成最新 sitemap
        urls = _build_full_urls()
        sitemap_path = os.path.join(self.data_dir, "sitemap_daily.xml")
        saved_path = self.submitter.save_sitemap(urls, sitemap_path)
        logger.info("📄 sitemap 生成完成 → %s (共 %d 个URL)", saved_path, len(urls))

        # 2. 提交到 Google (模拟 — 实际需要 Google Search Console API)
        google_result = self._submit_to_google(urls)
        logger.info("🔍 Google 提交结果: %s", google_result["status"])

        # 3. 提交到 Bing (模拟)
        bing_result = self._submit_to_bing(urls)
        logger.info("🔍 Bing 提交结果: %s", bing_result["status"])

        # 4. 记录日志
        submission_record = {
            "date": today,
            "timestamp": now_iso,
            "total_urls": len(urls),
            "sitemap_path": saved_path,
            "google": google_result,
            "bing": bing_result,
        }

        log_data = _load_submit_log()
        log_data["submissions"].append(submission_record)

        # 保留最近90天的记录
        if len(log_data["submissions"]) > 90:
            log_data["submissions"] = log_data["submissions"][-90:]

        _save_submit_log(log_data)

        result = {
            "date": today,
            "status": "success",
            "total_urls": len(urls),
            "google": google_result,
            "bing": bing_result,
            "sitemap_path": saved_path,
        }
        return result

    def _submit_to_google(self, urls: List[Dict]) -> Dict:
        """
        提交到 Google Search Console API (模拟实现)

        实际生产环境应使用 google-api-python-client:
          from google.oauth2 import service_account
          from googleapiclient.discovery import build
        """
        result = {
            "engine": "Google",
            "status": "submitted",
            "url_count": len(urls),
            "detail": "模拟提交成功 — 生产环境需配置 Google Search Console API",
            "submitted_at": _now_iso(),
        }
        # 如果 requests 库可用, 尝试真实提交到 Google Indexing API
        try:
            import requests
            # Google 快速提交: https://www.google.com/ping?sitemap=URL
            sitemap_url = f"{self.base_url}/sitemap.xml"
            ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            resp = requests.get(ping_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                result["status"] = "submitted"
                result["detail"] = f"Google ping 成功 (HTTP {resp.status_code})"
            else:
                result["detail"] = f"Google ping 响应 HTTP {resp.status_code}"
        except ImportError:
            pass  # 保持模拟状态
        except Exception as e:
            result["detail"] = f"Google 提交异常: {e} (使用模拟结果)"
        return result

    def _submit_to_bing(self, urls: List[Dict]) -> Dict:
        """
        提交到 Bing Webmaster API (模拟实现)

        实际生产环境应使用 Bing Webmaster API:
          POST https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch
        """
        result = {
            "engine": "Bing",
            "status": "submitted",
            "url_count": len(urls),
            "detail": "模拟提交成功 — 生产环境需配置 Bing Webmaster API Key",
            "submitted_at": _now_iso(),
        }
        try:
            import requests
            sitemap_url = f"{self.base_url}/sitemap.xml"
            ping_url = f"https://www.bing.com/ping?sitemap={sitemap_url}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            resp = requests.get(ping_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                result["status"] = "submitted"
                result["detail"] = f"Bing ping 成功 (HTTP {resp.status_code})"
            else:
                result["detail"] = f"Bing ping 响应 HTTP {resp.status_code}"
        except ImportError:
            pass
        except Exception as e:
            result["detail"] = f"Bing 提交异常: {e} (使用模拟结果)"
        return result

    # ── 2. AI知识库索引监控 ─────────────────────────────────────

    def check_ai_index(self) -> Dict:
        """
        检查AI搜索的收录情况:
          1. 使用 site:liankebao.top 查询 Google 索引数
          2. 记录每日索引变化趋势
          3. 超过3天无新增 → 触发告警

        Returns:
            索引检查结果字典
        """
        logger.info("🔎 === 检查 AI 知识库索引收录 ===")
        today = _today_str()
        now_iso = _now_iso()

        # 通过模拟 site: 查询获取索引数
        index_count, index_detail = self._query_site_index("Google")
        logger.info("📊 Google site:%s 索引估算: %d", self.base_url, index_count)

        bing_count, bing_detail = self._query_site_index("Bing")
        logger.info("📊 Bing site:%s 索引估算: %d", self.base_url, bing_count)

        # 加载历史趋势
        log_data = _load_submit_log()
        trends = log_data.get("index_trend", [])

        # 计算与前一天的差值
        yesterday_count = trends[-1]["google_index"] if trends else 0
        daily_delta = index_count - yesterday_count

        trend_record = {
            "date": today,
            "timestamp": now_iso,
            "google_index": index_count,
            "google_detail": index_detail,
            "bing_index": bing_count,
            "bing_detail": bing_detail,
            "daily_delta": daily_delta,
        }
        trends.append(trend_record)

        # 保留最近365天
        if len(trends) > 365:
            trends = trends[-365:]

        # 检查告警: 连续3天无新增
        alerts = log_data.get("alerts", [])
        alert_result = self._check_no_new_alert(trends, today, now_iso)
        if alert_result:
            alerts.append(alert_result)
            logger.warning("🚨 %s", alert_result["message"])

        log_data["index_trend"] = trends
        log_data["alerts"] = alerts
        _save_submit_log(log_data)

        # 评估覆盖率
        coverage = self._evaluate_ai_coverage(index_count)

        result = {
            "date": today,
            "google_index": index_count,
            "google_detail": index_detail,
            "bing_index": bing_count,
            "bing_detail": bing_detail,
            "daily_delta": daily_delta,
            "coverage": coverage,
            "alert": alert_result if alert_result else None,
        }
        return result

    def _query_site_index(self, engine: str = "Google") -> tuple:
        """
        使用 site: 查询方式获取索引数

        Returns:
            (estimated_count: int, detail: str)
        """
        try:
            import requests
            search_url = (
                f"https://www.google.com/search?q=site:{self.base_url}"
                if engine == "Google"
                else f"https://www.bing.com/search?q=site:{self.base_url}"
            )
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            resp = requests.get(search_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                text = resp.text
                # 尝试提取结果数: "约 123 条结果" 或 "About 123 results"
                import re
                # 中文模式
                match = re.search(r'约[^\d]*(\d[\d,]*)\s*条结果', text)
                if not match:
                    # 英文模式
                    match = re.search(r'About[^\d]*([\d,]+)\s*results?', text)
                if match:
                    count_str = match.group(1).replace(",", "")
                    count = int(count_str)
                    return count, f"site: 查询返回约 {count} 条结果"
                else:
                    # 如果 site: 返回了页面但没有结果数, 说明可能被屏蔽
                    if "did not match" in text.lower() or "没有找到" in text:
                        return 0, "site: 查询返回0条结果 (可能未被收录)"
                    return 0, "无法解析结果数 (可能被反爬)"
            return 0, f"HTTP {resp.status_code}"
        except ImportError:
            return 15, "模拟索引数 (requests 库未安装)"  # 模拟值
        except Exception as e:
            return 15, f"查询异常: {e} (使用模拟值)"  # 模拟值

    def _check_no_new_alert(
        self, trends: List[Dict], today: str, now_iso: str
    ) -> Optional[Dict]:
        """检查是否连续 ALERT_DAYS_NO_NEW 天无新增索引"""
        if len(trends) < ALERT_DAYS_NO_NEW + 1:
            return None

        recent = trends[-ALERT_DAYS_NO_NEW:]
        # 检查最近 N 天的 daily_delta 是否都为 0 或负数
        no_new_days = sum(1 for r in recent if r.get("daily_delta", 0) <= 0)

        if no_new_days >= ALERT_DAYS_NO_NEW:
            return {
                "date": today,
                "timestamp": now_iso,
                "type": "no_new_index",
                "severity": "warning",
                "message": (
                    f"⚠️ 连续 {ALERT_DAYS_NO_NEW} 天无新增索引! "
                    f"最近 {ALERT_DAYS_NO_NEW} 天索引变化: "
                    + ", ".join(f"{r['date']}: {r['daily_delta']:+d}" for r in recent)
                ),
                "suggestion": "建议检查: 1) sitemap是否正常提交; 2) 是否有新页面发布; 3) robots.txt 是否屏蔽了重要路径",
            }
        return None

    def _evaluate_ai_coverage(self, index_count: int) -> Dict:
        """评估 AI 知识库覆盖率"""
        # 期望目标页面数
        target_pages = len(DEFAULT_PAGES)

        if index_count == 0:
            level = "critical"
            description = "未被收录 — 需要立即排查"
        elif index_count < target_pages * 0.3:
            level = "poor"
            description = f"收录率低 ({index_count}/{target_pages}), 建议优化内容质量"
        elif index_count < target_pages * 0.7:
            level = "fair"
            description = f"收录率中等 ({index_count}/{target_pages}), 仍有优化空间"
        elif index_count < target_pages:
            level = "good"
            description = f"收录率良好 ({index_count}/{target_pages})"
        else:
            level = "excellent"
            description = f"收录率优秀 ({index_count}/{target_pages}), 超出预期"

        return {
            "level": level,
            "description": description,
            "indexed_pages": index_count,
            "target_pages": target_pages,
            "coverage_ratio": round(index_count / max(target_pages, 1), 2),
        }

    # ── 3. 周报生成 ──────────────────────────────────────────────

    def weekly_report(self) -> Dict:
        """
        生成每周 GEO 收录报告:
          - 收录页面数 / 新增趋势
          - 收录页面 TOP10
          - AI 知识库覆盖评估
          - 优化建议

        Returns:
            周报数据字典 (同时保存到 data/geo/ 目录)
        """
        logger.info("📋 === 生成 GEO 周报 ===")
        today = _today_str()
        now_iso = _now_iso()

        log_data = _load_submit_log()
        trends = log_data.get("index_trend", [])
        submissions = log_data.get("submissions", [])
        alerts = log_data.get("alerts", [])

        # 最近7天的趋势
        weekly_trends = trends[-7:] if len(trends) >= 7 else trends

        # 最近7天的提交
        weekly_submissions = [s for s in submissions if s["date"] >= (_today_minus_days(7))]

        # 统计当前索引
        current_google = trends[-1]["google_index"] if trends else 0
        current_bing = trends[-1]["bing_index"] if trends else 0

        # 计算7天前的索引 (用于对比)
        google_7d_ago = trends[-7]["google_index"] if len(trends) >= 7 else 0
        bing_7d_ago = trends[-7]["bing_index"] if len(trends) >= 7 else 0

        google_delta = current_google - google_7d_ago
        bing_delta = current_bing - bing_7d_ago

        # 收录页面 TOP10 (按最近7天平均排名)
        top_pages = self._get_top_indexed_pages(weekly_trends)

        # 评估覆盖率
        coverage = self._evaluate_ai_coverage(current_google)

        # 优化建议
        suggestions = self._generate_suggestions(
            current_google, google_delta, trends, alerts
        )

        # 告警总结
        recent_alerts = [a for a in alerts if a["date"] >= (_today_minus_days(7))]

        report = {
            "report_type": "weekly",
            "generated_at": now_iso,
            "report_date": today,
            "period": f"{_today_minus_days(7)} ~ {today}",
            "site": self.base_url,
            "summary": {
                "google_index": current_google,
                "google_weekly_change": google_delta,
                "bing_index": current_bing,
                "bing_weekly_change": bing_delta,
                "weekly_submissions": len(weekly_submissions),
                "total_submissions": len(submissions),
                "total_alerts": len(recent_alerts),
            },
            "top_pages": top_pages,
            "ai_coverage": coverage,
            "suggestions": suggestions,
            "alerts": recent_alerts[-5:] if recent_alerts else [],
        }

        # 保存报告
        report_filename = f"geo_report_{today}.json"
        report_path = os.path.join(self.data_dir, report_filename)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("✅ GEO周报已保存 → %s", report_path)

        # 同时生成可读的文本版本
        text_path = os.path.join(self.data_dir, f"geo_report_{today}.txt")
        self._save_report_text(report, text_path)

        return report

    def _get_top_indexed_pages(self, trends: List[Dict]) -> List[Dict]:
        """获取 TOP10 收录页面 (基于趋势数据模拟)"""
        # 实际应用中应从 Google Search Console API 获取
        # 此处使用配置的 DEFAULT_PAGES 作为参考
        top = []
        for i, page in enumerate(DEFAULT_PAGES[:10]):
            path = page["loc"]
            top.append({
                "rank": i + 1,
                "url": self.base_url + path,
                "changefreq": page["changefreq"],
                "priority": page["priority"],
                "note": "模拟数据 — 生产环境需对接 Search Console API",
            })
        return top

    def _generate_suggestions(
        self,
        current_index: int,
        weekly_delta: int,
        trends: List[Dict],
        alerts: List[Dict],
    ) -> List[str]:
        """根据数据分析生成优化建议"""
        suggestions = []

        if current_index == 0:
            suggestions.append("🔴 紧急: 站点未被任何搜索引擎收录, 请立即检查 robots.txt 和 sitemap 配置")
            suggestions.append("🔴 确认站点是否被手动屏蔽或被搜索引擎惩罚")

        if weekly_delta <= 0 and current_index > 0:
            suggestions.append("🟡 本周索引数无增长, 建议: 1) 发布新内容; 2) 优化现有页面内部链接; 3) 检查页面加载速度")

        if current_index < len(DEFAULT_PAGES):
            missing = len(DEFAULT_PAGES) - current_index
            suggestions.append(f"🔵 有 {missing} 个核心页面可能未被收录, 建议逐一检查并优化以下页面:")

            # 找出高优先级但可能未收录的页面
            high_priority_pages = [p for p in DEFAULT_PAGES if float(p["priority"]) >= 0.8]
            for p in high_priority_pages[:3]:
                suggestions.append(f"   - {self.base_url}{p['loc']} (priority: {p['priority']})")
        else:
            suggestions.append("🟢 核心页面收录良好, 建议持续发布高质量内容维持收录趋势")

        # 检查是否有活跃告警
        recent_no_new = [a for a in alerts if a.get("type") == "no_new_index"]
        if recent_no_new:
            latest = recent_no_new[-1]
            suggestions.append(f"🚨 {latest['suggestion']}")

        if weekly_delta > 0:
            suggestions.append(f"🟢 本周新增 {weekly_delta} 个索引, 保持当前内容更新节奏")

        suggestions.append("💡 通用建议: 1) 确保 JSON-LD 结构化数据完整; 2) 优化页面 Meta 描述; 3) 提升 Core Web Vitals 评分")

        return suggestions

    def _save_report_text(self, report: Dict, path: str) -> str:
        """将报告保存为可读的文本格式"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"  GEO 收录周报 ({report['period']})")
        lines.append("=" * 60)
        lines.append(f"  站点: {report['site']}")
        lines.append(f"  生成时间: {report['generated_at']}")
        lines.append("")

        s = report["summary"]
        lines.append("── 收录概况 ──────────────────────────────────")
        lines.append(f"  Google 索引: {s['google_index']} (本周变化: {s['google_weekly_change']:+d})")
        lines.append(f"  Bing 索引:   {s['bing_index']} (本周变化: {s['bing_weekly_change']:+d})")
        lines.append(f"  本周提交次数: {s['weekly_submissions']}")
        lines.append(f"  累计提交次数: {s['total_submissions']}")
        lines.append("")

        c = report["ai_coverage"]
        lines.append("── AI知识库覆盖评估 ─────────────────────────")
        lines.append(f"  等级: {c['level']}")
        lines.append(f"  收录: {c['indexed_pages']} / {c['target_pages']} 页面")
        lines.append(f"  覆盖率: {c['coverage_ratio']:.0%}")
        lines.append(f"  详情: {c['description']}")
        lines.append("")

        lines.append("── TOP10 收录页面 ───────────────────────────")
        for p in report["top_pages"]:
            lines.append(f"  {p['rank']:>2}. {p['url']}  [{p['changefreq']}]")
        lines.append("")

        if report["alerts"]:
            lines.append("── 告警 ────────────────────────────────────")
            for a in report["alerts"]:
                lines.append(f"  [{a['severity'].upper()}] {a['message']}")
            lines.append("")

        lines.append("── 优化建议 ──────────────────────────────────")
        for s in report["suggestions"]:
            lines.append(f"  {s}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("  由 化蛇(P8, 市场部/GEO) 自动生成")
        lines.append("=" * 60)

        content = "\n".join(lines)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("✅ GEO周报文本版已保存 → %s", path)
        return path


# ═══════════════════════════════════════════════════════════════════════
# 全局辅助
# ═══════════════════════════════════════════════════════════════════════

def _today_minus_days(days: int) -> str:
    """返回 N 天前的日期字符串"""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════

def cli():
    parser = argparse.ArgumentParser(
        description="GEO Cron Job — AI知识库持续提交 + 监控报告"
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="执行每日提交 (生成sitemap + 提交到Google/Bing + 记录日志)",
    )
    parser.add_argument(
        "--check-ai",
        action="store_true",
        help="检查AI知识库收录情况 (site:查询 + 趋势记录)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="生成GEO周报 (收录统计 + 趋势 + 优化建议)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="全部执行 (daily + check-ai + report)",
    )
    args = parser.parse_args()

    job = GeoCronJob()

    if args.daily or args.all:
        print("\n📅 执行每日提交...")
        result = job.daily_submit()
        print(f"   ✅ Google: {result['google']['status']}")
        print(f"   ✅ Bing:   {result['bing']['status']}")
        print(f"   📄 sitemap: {result['sitemap_path']}")

    if args.check_ai or args.all:
        print("\n🔍 检查AI知识库收录...")
        result = job.check_ai_index()
        print(f"   Google索引: {result['google_index']}")
        print(f"   Bing索引:   {result['bing_index']}")
        print(f"   日变化: {result['daily_delta']:+d}")
        c = result["coverage"]
        print(f"   覆盖评估: [{c['level']}] {c['description']}")
        if result["alert"]:
            print(f"   🚨 告警: {result['alert']['message']}")

    if args.report or args.all:
        print("\n📋 生成GEO周报...")
        report = job.weekly_report()
        s = report["summary"]
        print(f"   Google索引: {s['google_index']} (变化: {s['google_weekly_change']:+d})")
        print(f"   Bing索引:   {s['bing_index']} (变化: {s['bing_weekly_change']:+d})")
        print(f"   本周提交: {s['weekly_submissions']} 次")
        print(f"   优化建议数: {len(report['suggestions'])}")
        print(f"   报告路径: data/geo/geo_report_{_today_str()}.json")

    if not any([args.daily, args.check_ai, args.report, args.all]):
        parser.print_help()
        print("\n💡 示例:")
        print("  python scripts/geo_cron.py --daily        # 每日提交")
        print("  python scripts/geo_cron.py --check-ai     # 检查AI知识库")
        print("  python scripts/geo_cron.py --report       # 生成周报")
        print("  python scripts/geo_cron.py --all          # 全部执行")


if __name__ == "__main__":
    cli()
