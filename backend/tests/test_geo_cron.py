#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试: GEO Cron Job — AI知识库持续提交 + 监控报告
=================================================
化蛇(P8, 市场部, 营销增长/GEO)

测试覆盖:
  1. GeoCronJob 初始化 (×2)
  2. daily_submit() — sitemap生成 + 提交模拟 (×2)
  3. check_ai_index() — 索引检查 + 趋势 + 告警 + 覆盖率 (×4)
  4. weekly_report() — 报告生成 + 建议 + 文件保存 (×3)
  5. submit_log.json 文件完整性 (×1)
  6. 覆盖率边界值 (×1)
  7. 建议生成逻辑 (×2)
  8. 文本报告格式 (×1)
  9. 提交引擎结构 (×2)
  共计: ≥ 18 个测试用例
"""

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import geo_cron as gc_module
from geo_cron import GeoCronJob, _load_submit_log, _save_submit_log, _today_str, BASE_URL
from seo_optimizer import KnowledgeGraphSubmitter


# ═══════════════════════════════════════════════════════════════════════
# 辅助: 全局临时 data 目录 (在 run_all 中设置)
# ═══════════════════════════════════════════════════════════════════════

_ORIG_DATA_DIR = gc_module.DATA_DIR
_TEMP_DATA_DIR = None


def _setup_temp_data():
    """创建临时 data/geo 目录并返回路径"""
    global _TEMP_DATA_DIR
    tmpdir = tempfile.mkdtemp(prefix="geo_test_")
    gc_module.DATA_DIR = tmpdir
    _TEMP_DATA_DIR = tmpdir

    initial_log = {
        "metadata": {"site": BASE_URL, "created_at": "2026-01-01T00:00:00", "description": "test", "version": "1.0.0"},
        "submissions": [],
        "index_trend": [],
        "alerts": [],
    }
    with open(os.path.join(tmpdir, "submit_log.json"), "w", encoding="utf-8") as f:
        json.dump(initial_log, f)
    return tmpdir


def _reset_data_dir():
    """恢复原始 data 目录"""
    gc_module.DATA_DIR = _ORIG_DATA_DIR


def _today_minus_days(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════════════════════════════
# 1. 测试 GeoCronJob 初始化
# ═══════════════════════════════════════════════════════════════════════

def test_init_with_optimizer():
    """测试使用 seo_optimizer 初始化"""
    submitter = KnowledgeGraphSubmitter()
    job = GeoCronJob(seo_optimizer=submitter)
    assert job.base_url == "https://liankebao.top"
    assert job.submitter is submitter
    print("  ✅ test_init_with_optimizer PASS")


def test_init_without_optimizer():
    """测试无参数初始化 (延迟导入)"""
    job = GeoCronJob()
    assert job.base_url == "https://liankebao.top"
    assert job.submitter is not None
    print("  ✅ test_init_without_optimizer PASS")


# ═══════════════════════════════════════════════════════════════════════
# 2. 测试 daily_submit
# ═══════════════════════════════════════════════════════════════════════

def test_daily_submit_generates_sitemap():
    """测试 daily_submit 生成 sitemap 文件"""
    _setup_temp_data()
    try:
        job = GeoCronJob()
        result = job.daily_submit()

        assert result["status"] == "success"
        assert result["total_urls"] == 15
        assert result["date"] == _today_str()
        assert "google" in result
        assert "bing" in result
        assert "sitemap_path" in result

        sitemap_path = result["sitemap_path"]
        assert os.path.exists(sitemap_path), f"sitemap not found: {sitemap_path}"

        with open(sitemap_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "<?xml" in content
        assert "<urlset" in content
        assert BASE_URL in content
        print("  ✅ test_daily_submit_generates_sitemap PASS")
    finally:
        _reset_data_dir()


def test_daily_submit_logs_history():
    """测试 daily_submit 记录提交日志"""
    _setup_temp_data()
    try:
        job = GeoCronJob()
        job.daily_submit()

        log_data = _load_submit_log()
        assert len(log_data["submissions"]) == 1

        record = log_data["submissions"][0]
        assert record["date"] == _today_str()
        assert record["total_urls"] == 15
        assert record["google"]["engine"] == "Google"
        assert record["bing"]["engine"] == "Bing"
        print("  ✅ test_daily_submit_logs_history PASS")
    finally:
        _reset_data_dir()


# ═══════════════════════════════════════════════════════════════════════
# 3. 测试 check_ai_index
# ═══════════════════════════════════════════════════════════════════════

def test_check_ai_index_basic():
    """测试 check_ai_index 基本功能"""
    _setup_temp_data()
    try:
        job = GeoCronJob()
        result = job.check_ai_index()

        assert "date" in result
        assert "google_index" in result
        assert "bing_index" in result
        assert "daily_delta" in result
        assert "coverage" in result
        assert isinstance(result["google_index"], int)
        assert result["google_index"] >= 0
        print("  ✅ test_check_ai_index_basic PASS")
    finally:
        _reset_data_dir()


def test_check_ai_index_trend_recorded():
    """测试索引检查记录到趋势"""
    _setup_temp_data()
    try:
        job = GeoCronJob()
        job.check_ai_index()
        job.check_ai_index()

        log_data = _load_submit_log()
        assert len(log_data["index_trend"]) == 2

        for trend in log_data["index_trend"]:
            assert "date" in trend
            assert "google_index" in trend
            assert "bing_index" in trend
            assert "daily_delta" in trend
        print("  ✅ test_check_ai_index_trend_recorded PASS")
    finally:
        _reset_data_dir()


def test_check_ai_index_coverage_evaluation():
    """测试覆盖率评估输出"""
    _setup_temp_data()
    try:
        job = GeoCronJob()
        result = job.check_ai_index()

        coverage = result["coverage"]
        assert "level" in coverage
        assert "description" in coverage
        assert "indexed_pages" in coverage
        assert "target_pages" in coverage
        assert "coverage_ratio" in coverage
        assert coverage["level"] in ("critical", "poor", "fair", "good", "excellent")
        assert coverage["target_pages"] == 15
        print("  ✅ test_check_ai_index_coverage_evaluation PASS")
    finally:
        _reset_data_dir()


def test_alert_triggered_after_3_days_no_new():
    """测试连续3天无新增时触发告警"""
    _setup_temp_data()
    try:
        log_data = _load_submit_log()
        base_date = datetime.now() - timedelta(days=5)
        for i in range(5):
            d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            delta = 2 if i < 2 else 0
            log_data["index_trend"].append({
                "date": d,
                "timestamp": f"{d}T12:00:00",
                "google_index": 10 + delta,
                "bing_index": 8 + delta,
                "daily_delta": delta,
            })
        _save_submit_log(log_data)

        job = GeoCronJob()
        result = job.check_ai_index()

        assert result["alert"] is not None
        assert result["alert"]["type"] == "no_new_index"
        assert result["alert"]["severity"] == "warning"
        assert "连续" in result["alert"]["message"]
        print("  ✅ test_alert_triggered_after_3_days_no_new PASS")
    finally:
        _reset_data_dir()


# ═══════════════════════════════════════════════════════════════════════
# 4. 测试 weekly_report
# ═══════════════════════════════════════════════════════════════════════

def test_weekly_report_basic():
    """测试周报基本结构"""
    _setup_temp_data()
    try:
        job = GeoCronJob()
        job.daily_submit()
        job.check_ai_index()

        report = job.weekly_report()

        assert report["report_type"] == "weekly"
        assert "generated_at" in report
        assert "summary" in report
        assert "top_pages" in report
        assert "ai_coverage" in report
        assert "suggestions" in report

        s = report["summary"]
        assert "google_index" in s
        assert "google_weekly_change" in s
        assert "bing_index" in s
        assert "weekly_submissions" in s
        assert len(report["top_pages"]) >= 10
        print("  ✅ test_weekly_report_basic PASS")
    finally:
        _reset_data_dir()


def test_weekly_report_has_suggestions():
    """测试周报包含优化建议"""
    _setup_temp_data()
    try:
        job = GeoCronJob()
        job.daily_submit()
        job.check_ai_index()
        report = job.weekly_report()

        assert len(report["suggestions"]) > 0
        for s in report["suggestions"]:
            assert isinstance(s, str)
            assert len(s) > 10
        print("  ✅ test_weekly_report_has_suggestions PASS")
    finally:
        _reset_data_dir()


def test_weekly_report_saves_files():
    """测试周报保存为 JSON 和 TXT 文件"""
    tmpdir = _setup_temp_data()
    try:
        today = _today_str()
        job = GeoCronJob()
        job.daily_submit()
        job.check_ai_index()
        job.weekly_report()

        json_path = os.path.join(tmpdir, f"geo_report_{today}.json")
        txt_path = os.path.join(tmpdir, f"geo_report_{today}.txt")

        assert os.path.exists(json_path), f"JSON report not found: {json_path}"
        assert os.path.exists(txt_path), f"TXT report not found: {txt_path}"

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["report_type"] == "weekly"

        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()
        assert "GEO 收录周报" in text
        assert "优化建议" in text
        print("  ✅ test_weekly_report_saves_files PASS")
    finally:
        _reset_data_dir()


# ═══════════════════════════════════════════════════════════════════════
# 5. 测试数据文件完整性
# ═══════════════════════════════════════════════════════════════════════

def test_submit_log_file_exists():
    """测试 submit_log.json 文件存在且有效"""
    log_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "geo", "submit_log.json"
    )
    assert os.path.exists(log_path), f"File not found: {log_path}"

    with open(log_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "metadata" in data
    assert "submissions" in data
    assert "index_trend" in data
    assert "alerts" in data
    assert data["metadata"]["site"] == BASE_URL
    print("  ✅ test_submit_log_file_exists PASS")


# ═══════════════════════════════════════════════════════════════════════
# 6. 测试覆盖率边界值
# ═══════════════════════════════════════════════════════════════════════

def test_coverage_all_levels():
    """测试覆盖率评估所有等级"""
    job = GeoCronJob()
    test_cases = [
        (0, "critical"),
        (2, "poor"),       # < 15*0.3 = 4.5
        (5, "fair"),       # < 15*0.7 = 10.5
        (12, "good"),      # >= 10.5, < 15
        (20, "excellent"), # >= 15
    ]
    for index_count, expected_level in test_cases:
        coverage = job._evaluate_ai_coverage(index_count)
        assert coverage["level"] == expected_level, (
            f"index={index_count} expected={expected_level} got={coverage['level']}"
        )
        assert coverage["indexed_pages"] == index_count
    print("  ✅ test_coverage_all_levels PASS")


# ═══════════════════════════════════════════════════════════════════════
# 7. 测试建议生成
# ═══════════════════════════════════════════════════════════════════════

def test_suggestions_no_index():
    """测试索引为0时的紧急建议"""
    job = GeoCronJob()
    suggestions = job._generate_suggestions(0, 0, [], [])
    assert any("紧急" in s for s in suggestions)
    assert any("未被任何搜索引擎收录" in s for s in suggestions)
    print("  ✅ test_suggestions_no_index PASS")


def test_suggestions_negative_delta():
    """测试负增长时的建议"""
    job = GeoCronJob()
    suggestions = job._generate_suggestions(10, -3, [], [])
    assert any("无增长" in s or "无新增" in s for s in suggestions)
    print("  ✅ test_suggestions_negative_delta PASS")


# ═══════════════════════════════════════════════════════════════════════
# 8. 测试文本报告格式
# ═══════════════════════════════════════════════════════════════════════

def test_text_report_format():
    """测试文本报告包含所有必要章节"""
    _setup_temp_data()
    try:
        today = _today_str()

        report = {
            "report_type": "weekly",
            "generated_at": datetime.now().isoformat(),
            "report_date": today,
            "period": f"{_today_minus_days(7)} ~ {today}",
            "site": BASE_URL,
            "summary": {
                "google_index": 15,
                "google_weekly_change": 3,
                "bing_index": 12,
                "bing_weekly_change": 2,
                "weekly_submissions": 7,
                "total_submissions": 30,
                "total_alerts": 1,
            },
            "top_pages": [
                {"rank": i+1, "url": f"{BASE_URL}/page{i}", "changefreq": "weekly", "priority": "0.8", "note": ""}
                for i in range(10)
            ],
            "ai_coverage": {
                "level": "good",
                "description": "收录率良好",
                "indexed_pages": 15,
                "target_pages": 15,
                "coverage_ratio": 1.0,
            },
            "suggestions": ["🟢 核心页面收录良好", "💡 保持当前更新节奏"],
            "alerts": [],
        }

        job = GeoCronJob()
        text_path = os.path.join(_TEMP_DATA_DIR, f"test_report_{today}.txt")
        job._save_report_text(report, text_path)

        with open(text_path, "r", encoding="utf-8") as f:
            text = f.read()

        assert "收录概况" in text
        assert "AI知识库覆盖评估" in text
        assert "TOP10 收录页面" in text
        assert "优化建议" in text
        assert "化蛇" in text
        print("  ✅ test_text_report_format PASS")
    finally:
        _reset_data_dir()


# ═══════════════════════════════════════════════════════════════════════
# 9. 测试提交引擎结构
# ═══════════════════════════════════════════════════════════════════════

def test_submit_to_google_return_structure():
    """测试 Google 提交返回值结构"""
    job = GeoCronJob()
    urls = [{"loc": f"{BASE_URL}/test", "lastmod": "2026-01-01"}]
    result = job._submit_to_google(urls)

    assert result["engine"] == "Google"
    assert result["status"] in ("submitted", "failed")
    assert result["url_count"] == 1
    assert "submitted_at" in result
    print("  ✅ test_submit_to_google_return_structure PASS")


def test_submit_to_bing_return_structure():
    """测试 Bing 提交返回值结构"""
    job = GeoCronJob()
    urls = [{"loc": f"{BASE_URL}/test", "lastmod": "2026-01-01"}]
    result = job._submit_to_bing(urls)

    assert result["engine"] == "Bing"
    assert result["status"] in ("submitted", "failed")
    assert result["url_count"] == 1
    assert "submitted_at" in result
    print("  ✅ test_submit_to_bing_return_structure PASS")


# ═══════════════════════════════════════════════════════════════════════
# 运行全部测试
# ═══════════════════════════════════════════════════════════════════════

def run_all():
    tests = [
        # 初始化 (2)
        test_init_with_optimizer,
        test_init_without_optimizer,
        # 每日提交 (2)
        test_daily_submit_generates_sitemap,
        test_daily_submit_logs_history,
        # 索引检查 (4)
        test_check_ai_index_basic,
        test_check_ai_index_trend_recorded,
        test_check_ai_index_coverage_evaluation,
        test_alert_triggered_after_3_days_no_new,
        # 周报 (3)
        test_weekly_report_basic,
        test_weekly_report_has_suggestions,
        test_weekly_report_saves_files,
        # 数据文件 (1)
        test_submit_log_file_exists,
        # 覆盖率边界 (1)
        test_coverage_all_levels,
        # 建议生成 (2)
        test_suggestions_no_index,
        test_suggestions_negative_delta,
        # 文本报告 (1)
        test_text_report_format,
        # 提交引擎 (2)
        test_submit_to_google_return_structure,
        test_submit_to_bing_return_structure,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_fn.__name__} FAILED: {e}")
            traceback.print_exc()
            failed += 1

    total = len(tests)
    print(f"\n{'='*50}")
    print(f"📊 GEO Cron 测试结果: {passed}/{total} 通过, {failed} 失败")
    if failed == 0:
        print("🎉 全部通过!")
    return failed == 0


if __name__ == "__main__":
    run_all()
