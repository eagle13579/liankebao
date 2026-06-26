"""
链客宝 - health_check.py CLI 命令测试
=====================================
测试 health_check.py 中的 cmd_health / cmd_freshness / cmd_alert 等 CLI 函数。
使用 mock 模拟 PipelineMonitor 和 AlertManager，避免读写磁盘。
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 将项目根加入 sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.health_check import (
    cmd_health,
    cmd_freshness,
    cmd_alert,
    cmd_error_rate,
    cmd_report,
    main,
)


@pytest.fixture
def mock_monitor():
    """返回一个配置好返回值的 MagicMock PipelineMonitor"""
    monitor = MagicMock()
    monitor.check_health.return_value = {
        "full_sync": {
            "last_sync": "2026-06-26T10:00:00+00:00",
            "hours_since": 1.5,
            "status": "healthy",
            "errors": 0,
        },
        "incremental_sync": {
            "last_sync": "2026-06-26T10:30:00+00:00",
            "hours_since": 0.5,
            "status": "healthy",
            "errors": 0,
        },
        "overall": {
            "status": "healthy",
            "total_errors": 0,
            "total_syncs": 42,
            "is_running": False,
        },
    }
    monitor.check_data_freshness.return_value = {
        "full_sync_hours": 1.5,
        "incremental_sync_hours": 0.5,
        "max_hours": 0.5,
        "level": "healthy",
    }
    monitor.check_error_rate.return_value = {
        "window_hours": 24,
        "total_syncs": 42,
        "total_errors": 0,
        "error_rate": 0.0,
        "status": "healthy",
    }
    monitor.generate_report.return_value = "# 数据管道健康报告\n\n**状态**: healthy"
    return monitor


@pytest.fixture
def mock_alert_manager():
    """返回一个 MagicMock AlertManager"""
    mgr = MagicMock()
    mgr.check_thresholds.return_value = []
    mgr.send_feishu.return_value = True
    return mgr


# ===================================================================
# Test: cmd_health
# ===================================================================


class TestCmdHealth:
    """cmd_health 健康检查命令测试"""

    def test_cmd_health_prints_sync_info(self, mock_monitor, capsys):
        """cmd_health 输出全量和增量同步信息"""
        cmd_health(mock_monitor)
        captured = capsys.readouterr()

        assert "全量同步" in captured.out
        assert "增量同步" in captured.out
        assert "healthy" in captured.out
        assert "42" in captured.out  # total_syncs
        mock_monitor.check_health.assert_called_once()


# ===================================================================
# Test: cmd_freshness
# ===================================================================


class TestCmdFreshness:
    """cmd_freshness 数据新鲜度命令测试"""

    def test_cmd_freshness_prints_freshness_level(self, mock_monitor, capsys):
        """cmd_freshness 输出新鲜度级别和具体数值"""
        cmd_freshness(mock_monitor)
        captured = capsys.readouterr()

        assert "数据新鲜度" in captured.out
        assert "healthy" in captured.out
        assert "0.5" in captured.out or "1.5" in captured.out
        mock_monitor.check_data_freshness.assert_called_once()


# ===================================================================
# Test: cmd_alert / cmd_report / main
# ===================================================================


class TestCmdAlert:
    """cmd_alert 告警检查命令测试"""

    def test_cmd_alert_all_normal(self, mock_monitor, mock_alert_manager, capsys):
        """所有指标正常时输出 ✅ 所有指标正常"""
        cmd_alert(mock_monitor, mock_alert_manager)
        captured = capsys.readouterr()

        assert "所有指标正常" in captured.out
        mock_alert_manager.check_thresholds.assert_called_once()
        mock_alert_manager.send_feishu.assert_not_called()

    def test_cmd_alert_triggers_alerts(self, mock_alert_manager, capsys):
        """有告警触发时显示告警信息并推送飞书"""
        monitor = MagicMock()
        monitor.check_health.return_value = {
            "full_sync": {"last_sync": None, "hours_since": None, "status": "never_run", "errors": 0},
            "incremental_sync": {"last_sync": None, "hours_since": None, "status": "never_run", "errors": 0},
            "overall": {"status": "never_run", "total_errors": 0, "total_syncs": 0},
        }

        mock_alert_manager.check_thresholds.return_value = [
            {
                "level": "CRITICAL",
                "metric": "管道从未运行",
                "value": "N/A",
                "message": "管道从未运行，请立即启动",
            }
        ]

        cmd_alert(monitor, mock_alert_manager)
        captured = capsys.readouterr()

        assert "触发 1 条告警" in captured.out
        assert "CRITICAL" in captured.out
        mock_alert_manager.send_feishu.assert_called_once()
        mock_alert_manager.send_log.assert_called_once()
