"""
链客宝 - BatchEmbedGenerator / ProgressReporter / ErrorLogger / retry_on_timeout 测试
======================================================================================
测试 batch_embed.py 中的核心独立组件。
"""

import json
import os
import sys
import tempfile
import time
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# 将项目根加入 sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.batch_embed import (
    ProgressReporter,
    ErrorLogger,
    retry_on_timeout,
    parse_args,
    BatchEmbedGenerator,
)

# ===================================================================
# Test: ProgressReporter
# ===================================================================


class TestProgressReporter:
    """ProgressReporter 进度报告器测试"""

    def test_update_progress(self):
        """update 更新 processed/failed 计数，完成时触发报告"""
        reporter = ProgressReporter(total=100, report_interval=50, use_logger=False)
        assert reporter.processed == 0
        assert reporter.failed == 0

        reporter.update(processed=50, failed=2)
        assert reporter.processed == 50
        assert reporter.failed == 2

        # 到达 report_interval 应该触发 _report（但我们只验证计数）
        reporter.update(processed=100, failed=3)
        assert reporter.processed == 100
        assert reporter.failed == 3

    def test_summary_output(self):
        """summary 返回格式化的完成字符串"""
        reporter = ProgressReporter(total=200, report_interval=100, use_logger=False)
        reporter.update(processed=200, failed=5)
        summary = reporter.summary()

        assert "200" in summary
        assert "200" in summary  # total
        assert "5" in summary    # failed
        assert "处理完成" in summary

    def test_zero_total_does_not_divide_by_zero(self):
        """total=0 时进度计算不崩溃"""
        reporter = ProgressReporter(total=0, report_interval=10, use_logger=False)
        reporter.update(processed=0, failed=0)
        # 不应抛出 ZeroDivisionError
        assert reporter.processed == 0
        summary = reporter.summary()
        assert "0" in summary


# ===================================================================
# Test: ErrorLogger
# ===================================================================


class TestErrorLogger:
    """ErrorLogger 错误记录器测试"""

    def test_log_failure_creates_file(self):
        """log_failure 写入日志文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "errors.log")
            logger = ErrorLogger(log_path=log_path)
            logger.log_failure(
                record_id="rec_001",
                text="某企业描述文本",
                error="模型推理超时",
            )

            assert os.path.exists(log_path)
            with open(log_path, "r", encoding="utf-8") as f:
                line = f.readline()
            entry = json.loads(line)
            assert entry["record_id"] == "rec_001"
            assert "模型推理超时" in entry["error"]
            assert "timestamp" in entry

    def test_get_failed_count(self):
        """get_failed_count 返回正确行数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "errors.log")
            logger = ErrorLogger(log_path=log_path)
            assert logger.get_failed_count() == 0

            logger.log_failure("id1", "text1", "err1")
            logger.log_failure("id2", "text2", "err2")
            assert logger.get_failed_count() == 2


# ===================================================================
# Test: retry_on_timeout 装饰器
# ===================================================================


class TestRetryOnTimeout:
    """retry_on_timeout 重试装饰器测试"""

    def test_success_on_first_try(self):
        """第一次调用成功，不重试"""
        @retry_on_timeout(max_retries=3, delay=0.01)
        def succeed():
            return "ok"

        result = succeed()
        assert result == "ok"

    def test_retry_then_succeed(self):
        """前两次失败，第三次成功"""
        call_count = 0

        @retry_on_timeout(max_retries=3, delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("timeout")
            return "recovered"

        result = flaky()
        assert result == "recovered"
        assert call_count == 3

    def test_all_retries_exhausted(self):
        """所有重试耗尽后抛出最后一个异常"""
        @retry_on_timeout(max_retries=2, delay=0.01)
        def always_fails():
            raise TimeoutError("connection timed out")

        with pytest.raises(TimeoutError, match="connection timed out"):
            always_fails()


# ===================================================================
# Test: parse_args
# ===================================================================


class TestParseArgs:
    """parse_args 命令行参数解析测试"""

    def test_parse_full_mode(self):
        """--mode full 正确解析"""
        args = parse_args(["--mode", "full"])
        assert args.mode == "full"
        assert args.batch_size == 100

    def test_parse_incremental_requires_since(self):
        """增量模式缺少 --since 报错"""
        with pytest.raises(SystemExit):
            parse_args(["--mode", "incremental"])

    def test_parse_incremental_with_since(self):
        """增量模式加上 --since 正常"""
        args = parse_args(["--mode", "incremental", "--since", "2026-06-24"])
        assert args.mode == "incremental"
        assert args.since == "2026-06-24"

    def test_parse_custom_batch_size(self):
        """--batch-size 自定义值"""
        args = parse_args(["--mode", "full", "--batch-size", "200"])
        assert args.batch_size == 200

    def test_parse_status(self):
        """--status 解析"""
        args = parse_args(["--status"])
        assert args.status is True
