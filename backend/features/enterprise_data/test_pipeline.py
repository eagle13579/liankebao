"""
链客宝 - 管道编排器 + 调度器 综合测试
=========================================
测试覆盖：8+ 个用例，涵盖同步/调度/状态/去重等核心功能。

运行方式：
    python -m pytest D:\\chainke-full\\backend\\features\\enterprise_data\\test_pipeline.py -v
"""

import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# 确保可以导入项目模块
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

import pytest

from backend.features.enterprise_data.pipeline_orchestrator import (
    PipelineOrchestrator,
    SYNC_TYPE_FULL,
    SYNC_TYPE_INCREMENTAL,
    SYNC_TYPE_SINGLE,
    DEFAULT_ENTERPRISE_LIST,
)
from backend.features.enterprise_data.pipeline_scheduler import (
    PipelineScheduler,
    Job,
)
from backend.features.enterprise_data.tianyancha_adapter import (
    TianyanchaAdapter,
    EnterpriseInfo,
)
from backend.features.enterprise_data.qichacha_adapter import QichachaAdapter
from backend.features.enterprise_data.merger import EnterpriseDataMerger


# ======================================================================
# 管道编排器测试
# ======================================================================


@pytest.fixture
def temp_data_dir():
    """临时数据目录（模块级 fixture）"""
    with tempfile.TemporaryDirectory(prefix="pipeline_test_") as tmpdir:
        yield tmpdir


class TestPipelineOrchestrator:
    """PipelineOrchestrator 综合测试"""

    @pytest.fixture
    def orchestrator(self, temp_data_dir):
        """创建管道编排器实例（模拟模式）"""
        return PipelineOrchestrator(
            data_dir=temp_data_dir,
            enterprise_list=["阿里巴巴", "腾讯科技", "测试企业"],
        )

    # ------------------------------------------------------------------
    # 测试用例 1: 初始化与状态
    # ------------------------------------------------------------------
    def test_initialization_and_status(self, orchestrator):
        """TC1: 编排器初始化和状态查询"""
        status = orchestrator.status()

        assert status is not None
        assert status["is_running"] is False
        assert status["current_task"] is None
        assert status["total_syncs"] == 0
        assert status["total_errors"] == 0
        assert status["total_companies_synced"] == 0
        assert status["enterprise_count"] == 3
        assert status["last_full_sync"] is None
        assert status["last_incremental_sync"] is None
        assert status["is_auto_sync_running"] is False
        assert status["tyc_mock_mode"] is True  # 模拟模式
        assert status["qcc_mock_mode"] is True  # 模拟模式
        assert status["has_checkpoint"] is False

        # 验证企业列表
        assert orchestrator.get_enterprise_list() == ["阿里巴巴", "腾讯科技", "测试企业"]

    # ------------------------------------------------------------------
    # 测试用例 2: 单企业同步（成功）
    # ------------------------------------------------------------------
    def test_sync_single_company_success(self, orchestrator):
        """TC2: 单个企业全源同步 - 成功场景"""
        result = orchestrator.sync_single_company("阿里巴巴")

        assert result is not None
        assert result["company_name"] == "阿里巴巴"
        assert result["status"] in ("success", "partial")
        assert result["tyc_success"] is True   # 模拟模式一定成功
        assert result["qcc_success"] is True   # 模拟模式一定成功
        assert result["merged"] is not None
        assert result["error"] is None or result["status"] == "partial"
        assert result["timestamp"] is not None

        # 验证 merged 数据包含关键字段
        merged = result["merged"]
        assert merged["company_name"] == "阿里巴巴"
        assert merged["credit_code"] != ""
        assert merged["legal_person"] != ""

        # 验证状态已更新
        status = orchestrator.status()
        assert status["total_syncs"] == 0        # sync_single 不计数
        assert status["total_companies_synced"] == 0

    # ------------------------------------------------------------------
    # 测试用例 3: 单企业同步（空名称）
    # ------------------------------------------------------------------
    def test_sync_single_company_empty_name(self, orchestrator):
        """TC3: 单企业同步 - 空名称处理"""
        result = orchestrator.sync_single_company("")
        assert result["status"] == "failed"
        assert result["error"] == "企业名称为空"
        assert result["merged"] is None

        result2 = orchestrator.sync_single_company("   ")
        assert result2["status"] == "failed"
        assert result2["error"] == "企业名称为空"

    # ------------------------------------------------------------------
    # 测试用例 4: 全量同步
    # ------------------------------------------------------------------
    def test_full_sync(self, orchestrator):
        """TC4: 全量同步"""
        summary = orchestrator.schedule_full_sync()

        assert summary is not None
        assert summary["type"] == SYNC_TYPE_FULL
        assert summary["status"] == "completed"
        assert summary["total_companies"] == 3
        assert summary["success_count"] == 3   # 模拟模式全部成功
        assert summary["error_count"] == 0
        assert summary["elapsed_seconds"] >= 0  # 模拟模式可能瞬间完成
        assert summary["start_time"] is not None
        assert summary["end_time"] is not None
        assert len(summary["results"]) == 3

        # 验证每个企业的同步结果
        for result in summary["results"]:
            assert result["status"] in ("success", "partial")
            assert result["merged"] is not None

        # 验证状态持久化
        status = orchestrator.status()
        assert status["last_full_sync"] is not None
        assert status["total_syncs"] == 1
        assert status["total_companies_synced"] == 3
        assert status["total_errors"] == 0

    # ------------------------------------------------------------------
    # 测试用例 5: 增量同步（含断点续传）
    # ------------------------------------------------------------------
    def test_incremental_sync_with_checkpoint(self, orchestrator):
        """TC5: 增量同步 - 断点续传支持"""
        # 先做一次全量同步
        orchestrator.schedule_full_sync()

        # 再做增量同步
        summary = orchestrator.schedule_incremental_sync()

        assert summary is not None
        assert summary["type"] == SYNC_TYPE_INCREMENTAL
        assert summary["status"] == "completed"
        assert summary["total_companies"] == 3
        assert summary["success_count"] == 3
        assert summary["error_count"] == 0

        # 验证断点已清除
        status = orchestrator.status()
        assert status["has_checkpoint"] is False
        assert status["last_incremental_sync"] is not None

        # 验证状态累加
        assert status["total_syncs"] == 2  # 全量+增量

    # ------------------------------------------------------------------
    # 测试用例 6: 并发锁机制
    # ------------------------------------------------------------------
    def test_concurrent_sync_lock(self, orchestrator):
        """TC6: 并发同步时拒绝机制"""
        # 手动获取运行锁
        orchestrator._acquire_run_lock()
        try:
            # 尝试再次同步应该被拒绝
            result = orchestrator.schedule_full_sync()
            assert result["status"] == "skipped"
            assert "正在运行" in result["error"]
        finally:
            orchestrator._release_run_lock()

    # ------------------------------------------------------------------
    # 测试用例 7: 历史记录
    # ------------------------------------------------------------------
    def test_sync_history(self, orchestrator):
        """TC7: 同步历史记录"""
        # 没有同步时历史为空
        history = orchestrator.get_history(limit=10)
        assert history == []

        # 做两次同步
        orchestrator.schedule_full_sync()
        orchestrator.schedule_incremental_sync()

        # 检查历史
        history = orchestrator.get_history(limit=10)
        assert len(history) == 2

        # 第一条应该是最新的（增量同步）
        assert history[0]["type"] == SYNC_TYPE_INCREMENTAL
        assert history[0]["status"] == "completed"

        # 第二条是更早的（全量同步）
        assert history[1]["type"] == SYNC_TYPE_FULL
        assert history[1]["status"] == "completed"

        # limit 参数
        limited = orchestrator.get_history(limit=1)
        assert len(limited) == 1

    # ------------------------------------------------------------------
    # 测试用例 8: 企业列表管理
    # ------------------------------------------------------------------
    def test_enterprise_list_management(self, orchestrator):
        """TC8: 企业列表管理"""
        # 默认列表
        assert len(orchestrator.get_enterprise_list()) == 3

        # 更新列表
        new_list = ["新公司A", "新公司B"]
        orchestrator.set_enterprise_list(new_list)
        assert orchestrator.get_enterprise_list() == new_list

        # 空列表不会更新
        orchestrator.set_enterprise_list([])
        assert orchestrator.get_enterprise_list() == new_list  # 保持不变

    # ------------------------------------------------------------------
    # 测试用例 9: 自动同步启停
    # ------------------------------------------------------------------
    def test_auto_sync_start_stop(self, orchestrator):
        """TC9: 自动同步启动与停止"""
        assert orchestrator.is_auto_sync_running is False

        # 启动（用极短间隔以快速测试）
        orchestrator.start_auto_sync(interval_hours=999)  # 不会触发同步
        assert orchestrator.is_auto_sync_running is True

        # 重复启动不会报错
        orchestrator.start_auto_sync(interval_hours=999)
        assert orchestrator.is_auto_sync_running is True

        # 停止
        orchestrator.stop_auto_sync(timeout=5)
        assert orchestrator.is_auto_sync_running is False

        # 重复停止不会报错
        orchestrator.stop_auto_sync()

    # ------------------------------------------------------------------
    # 测试用例 10: 状态文件持久化
    # ------------------------------------------------------------------
    def test_state_persistence(self, temp_data_dir):
        """TC10: 状态持久化 - JSON 文件读写"""
        orch1 = PipelineOrchestrator(
            data_dir=temp_data_dir,
            enterprise_list=["测试企业"],
        )
        orch1.schedule_full_sync()

        # 创建新实例，应该能从文件加载状态
        orch2 = PipelineOrchestrator(
            data_dir=temp_data_dir,
            enterprise_list=["测试企业"],
        )

        status = orch2.status()
        assert status["last_full_sync"] is not None
        assert status["total_syncs"] == 1
        assert status["total_companies_synced"] == 1

    # ------------------------------------------------------------------
    # 测试用例 11: 自定义企业列表全量同步
    # ------------------------------------------------------------------
    def test_custom_enterprise_list_full_sync(self, orchestrator):
        """TC11: 自定义企业列表的全量同步"""
        custom_list = ["字节跳动", "京东集团"]
        summary = orchestrator.schedule_full_sync(enterprise_list=custom_list)

        assert summary["total_companies"] == 2
        assert summary["success_count"] == 2

        # 验证同步的是自定义列表中的企业
        companies_synced = [r["company_name"] for r in summary["results"]]
        assert "字节跳动" in companies_synced
        assert "京东集团" in companies_synced
        assert "阿里巴巴" not in companies_synced


# ======================================================================
# 管道调度器测试
# ======================================================================


class TestPipelineScheduler:
    """PipelineScheduler 综合测试"""

    @pytest.fixture
    def scheduler(self):
        """创建调度器实例"""
        return PipelineScheduler(poll_interval=0.1)

    # ------------------------------------------------------------------
    # 测试用例 12: 调度器初始化
    # ------------------------------------------------------------------
    def test_scheduler_initialization(self, scheduler):
        """TC12: 调度器初始化和任务管理"""
        assert scheduler.is_running is False
        assert scheduler.list_jobs() == []
        assert scheduler.get_job_log() == []

    # ------------------------------------------------------------------
    # 测试用例 13: 注册/列出/移除任务
    # ------------------------------------------------------------------
    def test_add_list_remove_job(self, scheduler):
        """TC13: 注册、列出和移除任务"""
        # 注册任务
        def dummy():
            pass

        job = scheduler.add_job("test_job", dummy, interval_minutes=10)
        assert isinstance(job, Job)
        assert job.name == "test_job"
        assert job.interval_minutes == 10
        assert job.run_count == 0

        # 列出任务
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["name"] == "test_job"
        assert jobs[0]["interval_minutes"] == 10

        # 获取单个任务
        fetched = scheduler.get_job("test_job")
        assert fetched is not None
        assert fetched.name == "test_job"

        # 获取不存在的任务
        assert scheduler.get_job("nonexistent") is None

        # 移除任务
        assert scheduler.remove_job("test_job") is True
        assert scheduler.list_jobs() == []

        # 移除不存在的任务
        assert scheduler.remove_job("nonexistent") is False

    # ------------------------------------------------------------------
    # 测试用例 14: 任务执行
    # ------------------------------------------------------------------
    def test_job_execution(self, scheduler):
        """TC14: 定时任务执行"""
        executed = {"count": 0}

        def my_job():
            executed["count"] += 1

        scheduler.add_job("counter", my_job, interval_minutes=0.1)  # 最小间隔
        scheduler.start()

        # 等待任务执行至少一次
        time.sleep(1.5)

        scheduler.stop(timeout=5)

        # 检查任务是否被触发
        assert executed["count"] >= 1

        # 检查任务日志
        logs = scheduler.get_job_log(job_name="counter")
        assert len(logs) >= 1
        assert logs[0]["job_name"] == "counter"
        assert logs[0]["success"] is True

    # ------------------------------------------------------------------
    # 测试用例 15: 任务异常隔离
    # ------------------------------------------------------------------
    def test_job_error_isolation(self, scheduler):
        """TC15: 任务异常不影响调度器"""
        error_job_executed = {"count": 0}

        def error_job():
            error_job_executed["count"] += 1
            raise ValueError("测试异常")

        scheduler.add_job("error_job", error_job, interval_minutes=0.1)
        scheduler.start()

        time.sleep(1.5)
        scheduler.stop(timeout=5)

        # 异常任务应该被触发但不会崩溃调度器
        assert error_job_executed["count"] >= 1

        # 检查日志显示失败
        logs = scheduler.get_job_log(job_name="error_job")
        error_logs = [log for log in logs if not log["success"]]
        assert len(error_logs) >= 1

    # ------------------------------------------------------------------
    # 测试用例 16: 调度器启停
    # ------------------------------------------------------------------
    def test_scheduler_start_stop(self, scheduler):
        """TC16: 调度器启动和停止"""
        assert scheduler.is_running is False

        scheduler.start()
        assert scheduler.is_running is True

        # 重复启动
        scheduler.start()  # 不应报错
        assert scheduler.is_running is True

        scheduler.stop()
        assert scheduler.is_running is False

        # 重复停止
        scheduler.stop()  # 不应报错
        assert scheduler.is_running is False

    # ------------------------------------------------------------------
    # 测试用例 17: 多任务调度
    # ------------------------------------------------------------------
    def test_multiple_jobs(self, scheduler):
        """TC17: 多任务注册与调度"""
        results = {"a": 0, "b": 0, "c": 0}

        def make_job(key):
            def job():
                results[key] += 1
            return job

        scheduler.add_job("job_a", make_job("a"), interval_minutes=0.1)
        scheduler.add_job("job_b", make_job("b"), interval_minutes=0.1)
        scheduler.add_job("job_c", make_job("c"), interval_minutes=0.1)

        assert len(scheduler.list_jobs()) == 3

        scheduler.start()
        time.sleep(1.5)
        scheduler.stop(timeout=5)

        # 所有任务都应该被执行
        assert results["a"] >= 1
        assert results["b"] >= 1
        assert results["c"] >= 1

    # ------------------------------------------------------------------
    # 测试用例 18: 参数校验
    # ------------------------------------------------------------------
    def test_job_parameter_validation(self, scheduler):
        """TC18: 任务参数校验"""
        def dummy():
            pass

        # 空名称
        with pytest.raises(ValueError, match="不能为空"):
            scheduler.add_job("", dummy, 10)

        # 非可调用对象
        with pytest.raises(TypeError, match="可调用"):
            scheduler.add_job("bad", 123, 10)

        # 无效间隔
        with pytest.raises(ValueError, match="不能小于"):
            scheduler.add_job("bad2", dummy, 0)

        # 有效的边界值
        job = scheduler.add_job("min_interval", dummy, 0.1)
        assert job.interval_minutes == 0.1


# ======================================================================
# 集成测试
# ======================================================================


class TestOrchestratorWithScheduler:
    """编排器 + 调度器 集成测试"""

    def test_orchestrator_with_scheduler(self, temp_data_dir):
        """TC19: 编排器与调度器集成"""
        orch = PipelineOrchestrator(
            data_dir=temp_data_dir,
            enterprise_list=["阿里巴巴"],
        )
        sched = PipelineScheduler(poll_interval=0.1)

        # 注册全量同步任务
        sched.add_job(
            "full_sync",
            orch.schedule_full_sync,
            interval_minutes=0.1,  # 最短间隔
        )

        sched.start()
        time.sleep(1.5)
        sched.stop(timeout=5)

        # 验证调度器记录了执行
        logs = sched.get_job_log(job_name="full_sync")
        assert len(logs) >= 1

        # 验证编排器状态已更新
        status = orch.status()
        assert status["total_syncs"] >= 1

    def test_end_to_end_pipeline(self, temp_data_dir):
        """TC20: 端到端管道流程"""
        orch = PipelineOrchestrator(
            data_dir=temp_data_dir,
            enterprise_list=["支付宝", "微信"],
        )

        # 1. 单企业同步
        single = orch.sync_single_company("支付宝")
        assert single["status"] in ("success", "partial")

        # 2. 全量同步
        full = orch.schedule_full_sync()
        assert full["success_count"] == 2

        # 3. 增量同步
        incr = orch.schedule_incremental_sync()
        assert incr["success_count"] == 2

        # 4. 状态检查
        status = orch.status()
        assert status["total_syncs"] == 2  # 全量+增量
        assert status["total_companies_synced"] == 4  # 2+2

        # 5. 历史
        history = orch.get_history()
        assert len(history) == 2

        # 6. 自动同步
        orch.start_auto_sync(interval_hours=999)
        assert orch.is_auto_sync_running is True
        orch.stop_auto_sync()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
