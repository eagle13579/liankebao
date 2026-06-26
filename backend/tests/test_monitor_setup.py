"""
链客宝 - PipelineMonitor & AlertManager 测试
=============================================
测试 monitor_setup.py 的 PipelineMonitor 和 AlertManager 类。
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, mock_open
from urllib.error import URLError

import pytest

# ---------------------------------------------------------------------------
# 将项目根加入 sys.path（与 conftest.py 一致）
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.monitor_setup import (
    PipelineMonitor,
    AlertManager,
    FRESHNESS_INFO_HOURS,
    FRESHNESS_WARN_HOURS,
    FRESHNESS_CRITICAL_HOURS,
    ERROR_RATE_CRITICAL,
    ENV_FEISHU_WEBHOOK_URL,
    STATE_FILE,
    HISTORY_FILE,
)

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_data_dir():
    """创建临时数据目录用作 data_dir"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _write_state(tmpdir: str, data: dict) -> str:
    """写入 pipeline_state.json 并返回路径"""
    path = os.path.join(tmpdir, STATE_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def _write_history(tmpdir: str, records: list) -> str:
    """写入 sync_history.json 并返回路径"""
    path = os.path.join(tmpdir, HISTORY_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return path


# ===================================================================
# Test: PipelineMonitor.check_health
# ===================================================================


class TestPipelineMonitorCheckHealth:
    """PipelineMonitor.check_health() 测试"""

    def test_no_state_file_returns_unknown(self, tmp_data_dir):
        """无状态文件时，所有管道状态为 unknown"""
        monitor = PipelineMonitor(data_dir=tmp_data_dir)
        result = monitor.check_health()

        assert result["full_sync"]["status"] == "unknown"
        assert result["full_sync"]["last_sync"] is None
        assert result["full_sync"]["errors"] == 0
        assert result["incremental_sync"]["status"] == "unknown"
        assert result["overall"]["status"] == "unknown"

    def test_healthy_state(self, tmp_data_dir):
        """最近同步在 4h 内，状态为 healthy"""
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        state = {
            "last_full_sync": recent,
            "last_incremental_sync": recent,
            "total_errors": 0,
            "total_syncs": 10,
            "is_running": False,
            "full_sync_errors": 0,
            "incremental_sync_errors": 0,
        }
        _write_state(tmp_data_dir, state)

        monitor = PipelineMonitor(data_dir=tmp_data_dir)
        result = monitor.check_health()

        assert result["full_sync"]["status"] == "healthy"
        assert result["incremental_sync"]["status"] == "healthy"
        assert result["overall"]["status"] == "healthy"
        assert result["full_sync"]["hours_since"] is not None
        assert 0 < result["full_sync"]["hours_since"] < 4

    def test_critical_state(self, tmp_data_dir):
        """超过 24h 未同步的状态为 critical"""
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        state = {
            "last_full_sync": old,
            "last_incremental_sync": None,
            "total_errors": 10,
            "total_syncs": 20,
            "is_running": False,
            "full_sync_errors": 5,
            "incremental_sync_errors": 0,
        }
        _write_state(tmp_data_dir, state)

        monitor = PipelineMonitor(data_dir=tmp_data_dir)
        result = monitor.check_health()

        assert result["full_sync"]["status"] == "critical"
        assert result["full_sync"]["hours_since"] >= 24
        assert result["incremental_sync"]["status"] == "never_run"
        assert result["overall"]["status"] == "critical"
        assert result["overall"]["total_errors"] == 10
        assert result["overall"]["total_syncs"] == 20

    def test_check_data_freshness_healthy(self, tmp_data_dir):
        """check_data_freshness 在 1h 内返回 healthy"""
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        state = {"last_full_sync": recent, "last_incremental_sync": recent}
        _write_state(tmp_data_dir, state)

        monitor = PipelineMonitor(data_dir=tmp_data_dir)
        result = monitor.check_data_freshness()

        assert result["level"] == "healthy"
        assert result["max_hours"] is not None
        assert result["max_hours"] <= 4

    def test_check_error_rate_from_history(self, tmp_data_dir):
        """check_error_rate 基于历史记录计算错误率"""
        now = datetime.now(timezone.utc)
        records = [
            {"timestamp": (now - timedelta(hours=1)).isoformat(), "status": "completed", "error_count": 0},
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "status": "completed", "error_count": 0},
            {"timestamp": (now - timedelta(hours=3)).isoformat(), "status": "failed", "error_count": 1},
        ]
        _write_history(tmp_data_dir, records)

        monitor = PipelineMonitor(data_dir=tmp_data_dir)
        # 给个假的状态文件，让 check_health 不崩（用于 generate_report 时不会用到历史）
        # 但 check_error_rate 直接读历史文件，不需要状态文件
        result = monitor.check_error_rate(hours=24)

        assert result["total_syncs"] == 3
        assert result["total_errors"] == 1
        assert result["error_rate"] == pytest.approx(1 / 3, 0.01)
        # 1/3 = 33% > 10% threshold => critical
        assert result["status"] == "critical"


# ===================================================================
# Test: AlertManager
# ===================================================================


class TestAlertManager:
    """AlertManager 阈值检查和飞书推送测试"""

    def test_check_thresholds_no_alert_when_healthy(self):
        """健康状态下 check_thresholds 返回空列表"""
        metrics = {
            "full_sync": {"last_sync": "2026-06-26T10:00:00+00:00", "hours_since": 1.0, "status": "healthy", "errors": 0},
            "incremental_sync": {"last_sync": "2026-06-26T10:00:00+00:00", "hours_since": 0.5, "status": "healthy", "errors": 0},
            "overall": {"status": "healthy", "total_errors": 0, "total_syncs": 10, "is_running": False},
        }
        alert = AlertManager(webhook_url="")
        triggered = alert.check_thresholds(metrics)
        assert triggered == []

    def test_check_thresholds_critical_freshness(self):
        """超过 24h 触发 CRITICAL 告警"""
        metrics = {
            "full_sync": {"last_sync": None, "hours_since": None, "status": "never_run", "errors": 0},
            "incremental_sync": {"last_sync": "2026-06-25T00:00:00+00:00", "hours_since": 36.0, "status": "critical", "errors": 0},
            "overall": {"status": "critical", "total_errors": 0, "total_syncs": 5, "is_running": False},
        }
        alert = AlertManager(webhook_url="")
        triggered = alert.check_thresholds(metrics)

        # 增量同步 36h -> critical, 同时整体新鲜度 36h -> critical（但不重复添加）
        # 管道从未运行也没触发因为 full_hours 是 None 但 incr_hours 不是 None
        levels = [t["level"] for t in triggered]
        assert "CRITICAL" in levels

    def test_send_feishu_no_webhook(self):
        """未配置 webhook 时 send_feishu 返回 True 且不报错"""
        alert = AlertManager(webhook_url="")
        result = alert.send_feishu("test message")
        assert result is True

    @patch("scripts.monitor_setup.urlopen")
    def test_send_feishu_success(self, mock_urlopen):
        """配置 webhook 时 send_feishu 成功返回 True"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"StatusCode": 0}'
        mock_urlopen.return_value = mock_resp

        alert = AlertManager(webhook_url="https://open.feishu.cn/hook/test")
        result = alert.send_feishu("test message")
        assert result is True
        mock_urlopen.assert_called_once()

    @patch("scripts.monitor_setup.urlopen")
    def test_send_feishu_network_error(self, mock_urlopen):
        """网络错误时 send_feishu 返回 False"""
        mock_urlopen.side_effect = URLError("Connection refused")

        alert = AlertManager(webhook_url="https://open.feishu.cn/hook/test")
        result = alert.send_feishu("test message")
        assert result is False
