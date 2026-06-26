"""
链客宝 - Cron 风格管道调度器
=================================
纯 Python 实现，零外部依赖，基于 threading 的后台任务调度器。

能力矩阵：
┌──────────────────┬──────────────────────────────────────────────┐
│ 方法              │ 说明                                         │
├──────────────────┼──────────────────────────────────────────────┤
│ start()          │ 启动后台调度线程                              │
│ stop()           │ 停止调度，等待当前任务完成                    │
│ add_job()        │ 注册定时任务（名称 / 函数 / 间隔分钟）       │
│ remove_job()     │ 移除已注册任务                                │
│ list_jobs()      │ 列出所有注册任务及下次运行时间                │
│ get_job_log()    │ 获取指定任务的执行日志                        │
└──────────────────┴──────────────────────────────────────────────┘

设计原则：
1. 零外部依赖，仅使用 threading / time / datetime / logging
2. 守护线程模式，不影响主进程退出
3. 任务异常不会影响调度器本身运行
4. 支持运行时动态增删任务
5. 精确到秒的间隔调度（非 cron 表达式，保持轻量）

快速开始：
    from backend.features.enterprise_data import PipelineScheduler

    scheduler = PipelineScheduler()
    scheduler.add_job("sync", my_sync_func, interval_minutes=30)
    scheduler.start()
    # ... 运行中 ...
    scheduler.stop()
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 任务数据模型
# ---------------------------------------------------------------------------


class Job:
    """调度任务描述符"""

    __slots__ = (
        "name", "func", "interval_minutes",
        "last_run", "next_run", "run_count", "error_count",
        "_lock",
    )

    def __init__(
        self,
        name: str,
        func: Callable[[], Any],
        interval_minutes: float,
    ) -> None:
        self.name = name
        self.func = func
        self.interval_minutes = max(0.1, interval_minutes)  # 最小间隔 6 秒
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count: int = 0
        self.error_count: int = 0
        self._lock = threading.Lock()

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "interval_minutes": self.interval_minutes,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
        }

    def __repr__(self) -> str:
        return (
            f"Job(name={self.name!r}, interval={self.interval_minutes}min, "
            f"next={self.next_run}, runs={self.run_count}, errors={self.error_count})"
        )


# ---------------------------------------------------------------------------
# 管道调度器
# ---------------------------------------------------------------------------


class PipelineScheduler:
    """Cron 风格的后台任务调度器

    使用后台守护线程轮询所有注册任务，当到达 next_run 时间时执行。
    支持运行时动态增删任务，异常隔离（单个任务崩溃不影响其他任务）。

    Usage:
        scheduler = PipelineScheduler()
        scheduler.add_job("full_sync", orchestrator.schedule_full_sync, interval_minutes=720)
        scheduler.add_job("incremental", orchestrator.schedule_incremental_sync, interval_minutes=60)
        scheduler.start()
        # ...
        scheduler.stop()
    """

    def __init__(self, poll_interval: float = 1.0) -> None:
        """初始化调度器

        Args:
            poll_interval: 轮询间隔（秒），默认 1 秒，控制调度精度
        """
        self._poll_interval = max(0.1, poll_interval)
        self._jobs: dict[str, Job] = {}
        self._jobs_lock = threading.Lock()
        self._running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._execution_log: list[dict[str, Any]] = []
        self._log_lock = threading.Lock()
        self._log_max = 500  # 最多保留 500 条日志

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台调度线程

        如果调度器已在运行，则忽略此次调用。
        """
        if self._running:
            logger.warning("调度器: 已在运行中，忽略重复 start()")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="PipelineScheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "调度器: 已启动 (轮询间隔=%ss, 任务数=%s)",
            self._poll_interval,
            len(self._jobs),
        )

    def stop(self, timeout: float = 10.0) -> None:
        """停止后台调度线程

        Args:
            timeout: 等待线程结束的超时秒数
        """
        if not self._running:
            logger.warning("调度器: 未在运行，忽略 stop()")
            return

        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("调度器: 线程未在 %ss 内结束", timeout)
        self._thread = None
        logger.info("调度器: 已停止")

    @property
    def is_running(self) -> bool:
        """调度器是否正在运行"""
        return self._running

    # ------------------------------------------------------------------
    # 任务管理
    # ------------------------------------------------------------------

    def add_job(
        self,
        name: str,
        func: Callable[[], Any],
        interval_minutes: float,
    ) -> Job:
        """注册定时任务

        Args:
            name: 任务名称（唯一标识，重复名称会覆盖旧任务）
            func: 要执行的函数（无参数）
            interval_minutes: 执行间隔（分钟）

        Returns:
            创建的 Job 对象
        """
        if not name or not name.strip():
            raise ValueError("任务名称不能为空")
        if not callable(func):
            raise TypeError("func 必须是可调用对象")
        if interval_minutes < 0.1:
            raise ValueError("interval_minutes 不能小于 0.1")

        name = name.strip()
        job = Job(name=name, func=func, interval_minutes=interval_minutes)
        job.next_run = datetime.now(timezone.utc)

        with self._jobs_lock:
            old = self._jobs.get(name)
            if old:
                logger.info("调度器: 覆盖已有任务 %r", name)
            self._jobs[name] = job

        logger.info(
            "调度器: 注册任务 %r (间隔=%smin)", name, interval_minutes
        )
        return job

    def remove_job(self, name: str) -> bool:
        """移除已注册任务

        Args:
            name: 任务名称

        Returns:
            True 如果任务存在并移除，False 如果任务不存在
        """
        with self._jobs_lock:
            if name in self._jobs:
                del self._jobs[name]
                logger.info("调度器: 移除任务 %r", name)
                return True
        logger.warning("调度器: 任务 %r 不存在", name)
        return False

    def get_job(self, name: str) -> Optional[Job]:
        """获取指定任务

        Args:
            name: 任务名称

        Returns:
            Job 对象，不存在则返回 None
        """
        with self._jobs_lock:
            return self._jobs.get(name)

    def list_jobs(self) -> list[dict[str, Any]]:
        """列出所有注册任务

        Returns:
            任务描述字典列表
        """
        with self._jobs_lock:
            return [job.to_dict() for job in self._jobs.values()]

    def get_job_log(
        self,
        job_name: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取任务执行日志

        Args:
            job_name: 可选，按任务名称过滤
            limit: 返回条数上限

        Returns:
            执行日志列表
        """
        with self._log_lock:
            logs = self._execution_log
            if job_name:
                logs = [log for log in logs if log.get("job_name") == job_name]
            return logs[-limit:]

    # ------------------------------------------------------------------
    # 内部调度循环
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """主调度循环（在后台线程中运行）"""
        logger.debug("调度器: 调度循环已启动")

        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            jobs_snapshot: list[Job] = []

            with self._jobs_lock:
                jobs_snapshot = list(self._jobs.values())

            for job in jobs_snapshot:
                if self._stop_event.is_set():
                    break

                if job.next_run and now >= job.next_run:
                    self._execute_job(job)

            # 轮询等待，支持被 stop_event 中断
            self._stop_event.wait(timeout=self._poll_interval)

        logger.debug("调度器: 调度循环已退出")

    def _execute_job(self, job: Job) -> None:
        """执行单个任务（带异常隔离和时间更新）"""
        start_time = datetime.now(timezone.utc)
        job_name = job.name

        logger.info("调度器: 执行任务 %r (第 %s 次)", job_name, job.run_count + 1)

        success = True
        error_msg: Optional[str] = None

        try:
            result = job.func()
            if isinstance(result, Exception):
                # 允许函数返回异常表示失败（非抛出模式）
                success = False
                error_msg = str(result)
        except Exception as exc:
            success = False
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("调度器: 任务 %r 异常 - %s", job_name, error_msg)

        end_time = datetime.now(timezone.utc)
        elapsed = (end_time - start_time).total_seconds()

        with job._lock:
            job.last_run = end_time
            job.run_count += 1
            if not success:
                job.error_count += 1
            # 计算下次运行时间
            job.next_run = end_time.replace(microsecond=0)  # 去掉毫秒
            # 从整点对齐：从 next_run 开始累加间隔
            from datetime import timedelta
            job.next_run += timedelta(minutes=job.interval_minutes)

        # 记录执行日志
        log_entry = {
            "job_name": job_name,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "success": success,
            "error": error_msg,
            "run_count": job.run_count,
        }
        with self._log_lock:
            self._execution_log.append(log_entry)
            if len(self._execution_log) > self._log_max:
                self._execution_log = self._execution_log[-self._log_max:]

        status = "✓" if success else "✗"
        logger.info(
            "调度器: 任务 %r 完成 %s (耗时=%ss, 下次=%s)",
            job_name, status, round(elapsed, 2),
            job.next_run.strftime("%H:%M:%S") if job.next_run else "N/A",
        )


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_scheduler(poll_interval: float = 1.0) -> PipelineScheduler:
    """创建调度器实例（便利函数）

    Args:
        poll_interval: 轮询间隔（秒）

    Returns:
        PipelineScheduler 实例
    """
    return PipelineScheduler(poll_interval=poll_interval)


__all__ = [
    "PipelineScheduler",
    "Job",
    "create_scheduler",
]
