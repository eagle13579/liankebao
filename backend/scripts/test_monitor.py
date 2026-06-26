"""
链客宝 - 数据管道监控+飞书告警系统 综合测试
==============================================
测试覆盖：12 个用例，涵盖健康检查/阈值/告警级别/飞书推送Mock等。

运行方式：
    python -m pytest D:\\chainke-full\\backend\\scripts\\test_monitor.py -v
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# 确保可以导入项目模块
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

import pytest

from backend.scripts.monitor_setup import (
    PipelineMonitor,
    AlertManager,
    create_monitor,
    create_alert_manager,
    FRESHNESS_INFO_HOURS,
    FRESHNESS_WARN_HOURS,
    FRESHNESS_CRITICAL_HOURS,
    ERROR_RATE_CRITICAL,
    ENV_FEISHU_WEBHOOK_URL,
    STATE_FILE,
    HISTORY_FILE,
)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def temp_data_dir():
    """临时数据目录"""
    with tempfile.TemporaryDirectory(prefix="monitor_test_") as tmpdir:
        yield tmpdir


@pytest.fixture
def monitor(temp_data_dir):
    """创建监控器实例"""
    return PipelineMonitor(data_dir=temp_data_dir)


@pytest.fixture
def alert_manager():
    """创建告警管理器实例（默认无 webhook）"""
    return AlertManager(webhook_url="")


def _write_state(data_dir: str, state: dict) -> str:
    """写入状态文件并返回路径"""
    path = os.path.join(data_dir, STATE_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


def _write_history(data_dir: str, records: list[dict]) -> str:
    """写入历史文件并返回路径"""
    path = os.path.join(data_dir, HISTORY_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return path


# ======================================================================
# Test: PipelineMonitor
# ======================================================================


class TestPipelineMonitor:
    """PipelineMonitor 综合测试"""

    # ------------------------------------------------------------------
    # TC1: 无状态文件时的健康检查
    # ------------------------------------------------------------------
    def test_health_no_state_file(self, monitor):
        """TC1: 无状态文件时健康检查返回 unknown"""
        health = monitor.check_health()

        assert health["full_sync"]["status"] == "unknown"
        assert health["full_sync"]["last_sync"] is None
        assert health["incremental_sync"]["status"] == "unknown"
        assert health["overall"]["status"] == "unknown"
        assert health["overall"]["total_errors"] == 0
        assert health["overall"]["total_syncs"] == 0

    # ------------------------------------------------------------------
    # TC2: 正常状态文件的健康检查
    # ------------------------------------------------------------------
    def test_health_with_state(self, monitor, temp_data_dir):
        """TC2: 有状态文件时健康检查返回正确数据"""
        now = datetime.now(timezone.utc)
        state = {
            "last_full_sync": (now - timedelta(hours=2)).isoformat(),
            "last_incremental_sync": (now - timedelta(hours=1)).isoformat(),
            "is_running": False,
            "total_syncs": 10,
            "total_errors": 1,
            "total_companies_synced": 50,
        }
        _write_state(temp_data_dir, state)

        health = monitor.check_health()

        assert health["full_sync"]["status"] == "healthy"
        assert health["full_sync"]["hours_since"] is not None
        assert 1.5 <= health["full_sync"]["hours_since"] <= 3.0

        assert health["incremental_sync"]["status"] == "healthy"
        assert health["incremental_sync"]["hours_since"] is not None
        assert 0.5 <= health["incremental_sync"]["hours_since"] <= 2.0

        assert health["overall"]["status"] == "healthy"
        assert health["overall"]["total_syncs"] == 10
        assert health["overall"]["total_errors"] == 1
        assert health["overall"]["is_running"] is False

    # ------------------------------------------------------------------
    # TC3: 新鲜度检查 - healthy 级别
    # ------------------------------------------------------------------
    def test_freshness_healthy(self, monitor, temp_data_dir):
        """TC3: 新鲜度 healthy（<4h）"""
        now = datetime.now(timezone.utc)
        state = {
            "last_full_sync": (now - timedelta(hours=2)).isoformat(),
            "last_incremental_sync": (now - timedelta(hours=1)).isoformat(),
        }
        _write_state(temp_data_dir, state)

        freshness = monitor.check_data_freshness()
        assert freshness["level"] == "healthy"
        assert freshness["max_hours"] is not None
        assert freshness["max_hours"] < FRESHNESS_INFO_HOURS

    # ------------------------------------------------------------------
    # TC4: 新鲜度检查 - info 级别（>4h）
    # ------------------------------------------------------------------
    def test_freshness_info(self, monitor, temp_data_dir):
        """TC4: 新鲜度 info（>4h, <12h）"""
        now = datetime.now(timezone.utc)
        state = {
            "last_full_sync": (now - timedelta(hours=6)).isoformat(),
            "last_incremental_sync": (now - timedelta(hours=5)).isoformat(),
        }
        _write_state(temp_data_dir, state)

        freshness = monitor.check_data_freshness()
        assert freshness["level"] == "info"
        assert 4 < freshness["max_hours"] < 12

    # ------------------------------------------------------------------
    # TC5: 新鲜度检查 - warn 级别（>12h）
    # ------------------------------------------------------------------
    def test_freshness_warn(self, monitor, temp_data_dir):
        """TC5: 新鲜度 warn（>12h, <24h）"""
        now = datetime.now(timezone.utc)
        state = {
            "last_full_sync": (now - timedelta(hours=14)).isoformat(),
        }
        _write_state(temp_data_dir, state)

        freshness = monitor.check_data_freshness()
        assert freshness["level"] == "warn"
        assert 12 < freshness["max_hours"] < 24

    # ------------------------------------------------------------------
    # TC6: 新鲜度检查 - critical 级别（>24h）
    # ------------------------------------------------------------------
    def test_freshness_critical(self, monitor, temp_data_dir):
        """TC6: 新鲜度 critical（>24h）"""
        now = datetime.now(timezone.utc)
        state = {
            "last_full_sync": (now - timedelta(hours=48)).isoformat(),
        }
        _write_state(temp_data_dir, state)

        freshness = monitor.check_data_freshness()
        assert freshness["level"] == "critical"
        assert freshness["max_hours"] > FRESHNESS_CRITICAL_HOURS

    # ------------------------------------------------------------------
    # TC7: 错误率检查 - 健康
    # ------------------------------------------------------------------
    def test_error_rate_healthy(self, monitor, temp_data_dir):
        """TC7: 错误率 healthy（<10%）"""
        now = datetime.now(timezone.utc)
        history = [
            {
                "type": "full",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "status": "completed",
                "error_count": 0,
            },
            {
                "type": "full",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "status": "completed",
                "error_count": 0,
            },
            {
                "type": "incremental",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
                "status": "completed",
                "error_count": 0,
            },
        ]
        _write_history(temp_data_dir, history)

        error_info = monitor.check_error_rate(hours=24)
        assert error_info["status"] == "healthy"
        assert error_info["total_syncs"] == 3
        assert error_info["total_errors"] == 0
        assert error_info["error_rate"] == 0.0

    # ------------------------------------------------------------------
    # TC8: 错误率检查 - critical（>10%）
    # ------------------------------------------------------------------
    def test_error_rate_critical(self, monitor, temp_data_dir):
        """TC8: 错误率 critical（>10%）"""
        now = datetime.now(timezone.utc)
        history = [
            {
                "type": "full",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "status": "completed",
                "error_count": 0,
                "success_count": 5,
            },
            {
                "type": "full",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "status": "failed",
                "error_count": 3,
                "success_count": 0,
            },
            {
                "type": "incremental",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
                "status": "completed",
                "error_count": 0,
                "success_count": 2,
            },
            {
                "type": "full",
                "timestamp": (now - timedelta(hours=4)).isoformat(),
                "status": "failed",
                "error_count": 2,
                "success_count": 0,
            },
        ]
        _write_history(temp_data_dir, history)

        error_info = monitor.check_error_rate(hours=24)
        assert error_info["status"] == "critical"
        assert error_info["total_syncs"] == 4
        assert error_info["total_errors"] == 2
        assert error_info["error_rate"] > ERROR_RATE_CRITICAL

    # ------------------------------------------------------------------
    # TC9: 生成 Markdown 报告
    # ------------------------------------------------------------------
    def test_generate_report(self, monitor, temp_data_dir):
        """TC9: 生成 Markdown 健康报告"""
        now = datetime.now(timezone.utc)
        state = {
            "last_full_sync": (now - timedelta(hours=2)).isoformat(),
            "last_incremental_sync": (now - timedelta(hours=1)).isoformat(),
            "is_running": False,
            "total_syncs": 5,
            "total_errors": 0,
        }
        _write_state(temp_data_dir, state)

        history = [
            {
                "type": "full",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "status": "completed",
                "error_count": 0,
            },
        ]
        _write_history(temp_data_dir, history)

        report = monitor.generate_report()

        # 验证报告包含关键节点
        assert "# 数据管道健康报告" in report
        assert "全量同步" in report
        assert "增量同步" in report
        assert "数据新鲜度" in report
        assert "错误率" in report
        assert "健康" in report or "healthy" in report.lower()
        assert "PipelineMonitor" in report


# ======================================================================
# Test: AlertManager
# ======================================================================


class TestAlertManager:
    """AlertManager 综合测试"""

    # ------------------------------------------------------------------
    # TC10: 阈值检查 - 所有指标正常
    # ------------------------------------------------------------------
    def test_thresholds_all_healthy(self, alert_manager):
        """TC10: 所有指标正常时无告警"""
        metrics = {
            "full_sync": {
                "last_sync": "2026-06-24T12:00:00+00:00",
                "hours_since": 2.0,
                "status": "healthy",
                "errors": 0,
            },
            "incremental_sync": {
                "last_sync": "2026-06-24T13:00:00+00:00",
                "hours_since": 1.0,
                "status": "healthy",
                "errors": 0,
            },
            "overall": {
                "status": "healthy",
                "total_errors": 0,
                "total_syncs": 20,
                "is_running": False,
            },
        }

        triggered = alert_manager.check_thresholds(metrics)
        assert triggered == []

    # ------------------------------------------------------------------
    # TC11: 阈值检查 - 新鲜度 INFO / WARN / CRITICAL
    # ------------------------------------------------------------------
    def test_thresholds_freshness_levels(self, alert_manager):
        """TC11: 新鲜度告警级别 INFO / WARN / CRITICAL"""
        # --- INFO: 6h ---
        metrics_info = {
            "full_sync": {
                "last_sync": None,
                "hours_since": None,
                "status": "never_run",
                "errors": 0,
            },
            "incremental_sync": {
                "last_sync": "2026-06-24T07:00:00+00:00",
                "hours_since": 6.0,
                "status": "stale",
                "errors": 0,
            },
            "overall": {
                "status": "stale",
                "total_errors": 0,
                "total_syncs": 5,
                "is_running": False,
            },
        }
        triggered = alert_manager.check_thresholds(metrics_info)
        info_items = [t for t in triggered if t["level"] == "INFO"]
        assert len(info_items) >= 1
        assert any("新鲜度" in t["metric"] for t in info_items)

        # --- WARN: 14h ---
        metrics_warn = {
            "full_sync": {
                "last_sync": "2026-06-23T22:00:00+00:00",
                "hours_since": 14.0,
                "status": "degraded",
                "errors": 0,
            },
            "incremental_sync": {
                "last_sync": None,
                "hours_since": None,
                "status": "never_run",
                "errors": 0,
            },
            "overall": {
                "status": "degraded",
                "total_errors": 0,
                "total_syncs": 3,
                "is_running": False,
            },
        }
        triggered = alert_manager.check_thresholds(metrics_warn)
        warn_items = [t for t in triggered if t["level"] == "WARN"]
        assert len(warn_items) >= 1

        # --- CRITICAL: 48h ---
        metrics_critical = {
            "full_sync": {
                "last_sync": "2026-06-22T12:00:00+00:00",
                "hours_since": 48.0,
                "status": "critical",
                "errors": 0,
            },
            "incremental_sync": {
                "last_sync": None,
                "hours_since": None,
                "status": "never_run",
                "errors": 0,
            },
            "overall": {
                "status": "critical",
                "total_errors": 0,
                "total_syncs": 2,
                "is_running": False,
            },
        }
        triggered = alert_manager.check_thresholds(metrics_critical)
        critical_items = [t for t in triggered if t["level"] == "CRITICAL"]
        assert len(critical_items) >= 1

    # ------------------------------------------------------------------
    # TC12: 阈值检查 - 错误率 CRITICAL
    # ------------------------------------------------------------------
    def test_thresholds_error_rate_critical(self, alert_manager):
        """TC12: 错误率超过 10% 触发 CRITICAL"""
        metrics = {
            "full_sync": {
                "last_sync": "2026-06-24T12:00:00+00:00",
                "hours_since": 2.0,
                "status": "healthy",
                "errors": 0,
            },
            "incremental_sync": {
                "last_sync": "2026-06-24T13:00:00+00:00",
                "hours_since": 1.0,
                "status": "healthy",
                "errors": 0,
            },
            "overall": {
                "status": "healthy",
                "total_errors": 5,
                "total_syncs": 20,
                "is_running": False,
            },
        }

        triggered = alert_manager.check_thresholds(metrics)
        critical_items = [t for t in triggered if t["level"] == "CRITICAL" and "错误率" in t["metric"]]
        assert len(critical_items) >= 1
        assert "错误率" in critical_items[0]["message"]

    # ------------------------------------------------------------------
    # TC13: 管道从未运行 - CRITICAL
    # ------------------------------------------------------------------
    def test_thresholds_never_run(self, alert_manager):
        """TC13: 管道从未运行触发 CRITICAL"""
        metrics = {
            "full_sync": {
                "last_sync": None,
                "hours_since": None,
                "status": "never_run",
                "errors": 0,
            },
            "incremental_sync": {
                "last_sync": None,
                "hours_since": None,
                "status": "never_run",
                "errors": 0,
            },
            "overall": {
                "status": "never_run",
                "total_errors": 0,
                "total_syncs": 0,
                "is_running": False,
            },
        }

        triggered = alert_manager.check_thresholds(metrics)
        assert len(triggered) >= 1
        assert triggered[0]["level"] == "CRITICAL"
        assert "从未运行" in triggered[0]["metric"]

    # ------------------------------------------------------------------
    # TC14: 飞书 Webhook 推送 Mock
    # ------------------------------------------------------------------
    @patch("backend.scripts.monitor_setup.urlopen")
    def test_send_feishu_success(self, mock_urlopen, alert_manager):
        """TC14: 飞书 Webhook 推送成功（Mock）"""
        # 设置 webhook URL
        alert_manager._webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/test"

        # Mock 返回
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"StatusCode": 0, "StatusMessage": "success"}'
        mock_urlopen.return_value = mock_response

        result = alert_manager.send_feishu("测试告警消息")
        assert result is True
        mock_urlopen.assert_called_once()

    @patch("backend.scripts.monitor_setup.urlopen")
    def test_send_feishu_failure(self, mock_urlopen, alert_manager):
        """TC15: 飞书 Webhook 推送失败（Mock）"""
        alert_manager._webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/test"

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"StatusCode": 10001, "StatusMessage": "invalid signature"}'
        mock_urlopen.return_value = mock_response

        result = alert_manager.send_feishu("测试告警消息")
        assert result is False

    # ------------------------------------------------------------------
    # TC16: 无 Webhook 时不崩溃
    # ------------------------------------------------------------------
    def test_send_feishu_no_webhook(self, alert_manager):
        """TC16: 未配置 Webhook 时不崩溃"""
        alert_manager._webhook_url = ""
        result = alert_manager.send_feishu("测试消息")
        assert result is True  # 无配置视为成功（静默忽略）

    # ------------------------------------------------------------------
    # TC17: 本地日志不抛出异常
    # ------------------------------------------------------------------
    def test_send_log(self, alert_manager):
        """TC17: 本地日志写入不抛出异常"""
        try:
            alert_manager.send_log("测试日志消息")
        except Exception as exc:
            pytest.fail(f"send_log 不应抛出异常: {exc}")


# ======================================================================
# Test: 便利函数
# ======================================================================


class TestConvenienceFunctions:
    """便利函数测试"""

    def test_create_monitor(self):
        """TC18: create_monitor 返回 PipelineMonitor 实例"""
        monitor = create_monitor()
        assert isinstance(monitor, PipelineMonitor)

    def test_create_alert_manager(self, monkeypatch):
        """TC19: create_alert_manager 返回 AlertManager 实例"""
        monkeypatch.delenv(ENV_FEISHU_WEBHOOK_URL, raising=False)
        alert = create_alert_manager()
        assert isinstance(alert, AlertManager)
        assert alert._webhook_url == ""  # 无环境变量时为空

    def test_create_alert_manager_from_env(self, monkeypatch):
        """TC20: 从环境变量读取 Webhook URL"""
        test_url = "https://open.feishu.cn/open-apis/bot/v2/hook/env_test"
        monkeypatch.setenv(ENV_FEISHU_WEBHOOK_URL, test_url)
        alert = create_alert_manager()
        assert alert._webhook_url == test_url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
