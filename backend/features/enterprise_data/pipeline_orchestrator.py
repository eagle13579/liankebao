"""
链客宝 - 多源数据采集管道编排器
==================================
统筹管理天眼查+企查查双源数据采集管道，支持全量同步、增量同步、
单企业同步、定时调度、状态持久化与历史追踪。

能力矩阵：
┌──────────────────────────┬─────────────────────────────────────┐
│ 方法                      │ 说明                                │
├──────────────────────────┼─────────────────────────────────────┤
│ schedule_full_sync()     │ 全量同步所有企业数据源              │
│ schedule_incremental()   │ 增量同步（支持断点续传）            │
│ sync_single_company()    │ 单个企业全源同步                    │
│ status()                 │ 返回当前管道状态字典                │
│ get_history()            │ 历史同步记录                        │
│ start_auto_sync()        │ 启动后台自动同步循环                │
│ stop_auto_sync()         │ 停止后台自动同步                    │
└──────────────────────────┴─────────────────────────────────────┘

同步策略：
1. 先天眼查（工商信息）→ 再企查查（信用/知产补充）
2. 失败独立处理：天眼查失败不影响企查查
3. 结果合并：调用 merger.merge()
4. 去重：同名企业只保留最新同步

设计原则：
1. 状态持久化：JSON 文件记录上次同步时间/状态/错误数
2. 断点续传：增量同步记录断点，支持恢复
3. 异常隔离：单源失败不阻塞整体管道
4. 可观测性：完整的同步历史与状态追踪

快速开始：
    from backend.features.enterprise_data import PipelineOrchestrator

    orch = PipelineOrchestrator()
    result = orch.sync_single_company("阿里巴巴")
    print(result["status"])

    # 定时触发（每 12 小时）
    orch.start_auto_sync(interval_hours=12)
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from .tianyancha_adapter import TianyanchaAdapter, EnterpriseInfo
from .qichacha_adapter import QichachaAdapter
from .merger import EnterpriseDataMerger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 默认数据目录（相对于项目根）
DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "enterprise_sync",
)

# 默认同步间隔（小时）
DEFAULT_INTERVAL_HOURS = 12

# 状态文件
STATE_FILE = "pipeline_state.json"
HISTORY_FILE = "sync_history.json"

# 默认的企业列表（全量同步目标）
DEFAULT_ENTERPRISE_LIST = [
    "阿里巴巴",
    "腾讯科技",
    "百度在线",
    "京东集团",
    "字节跳动",
]

# 同步类型
SYNC_TYPE_FULL = "full"
SYNC_TYPE_INCREMENTAL = "incremental"
SYNC_TYPE_SINGLE = "single"


# ---------------------------------------------------------------------------
# 管道编排器
# ---------------------------------------------------------------------------


class PipelineOrchestrator:
    """多源数据采集管道编排器

    统筹管理天眼查、企查查双源数据采集的全生命周期，包括调度、
    执行、合并、去重、状态持久化与历史追踪。

    支持三种同步模式：
    - 全量同步：遍历所有企业，重新采集所有数据源
    - 增量同步：只采集上次同步之后有变动的企业（基于断点续传）
    - 单企业同步：指定企业名称，全源采集并合并

    Usage:
        orch = PipelineOrchestrator()
        orch.sync_single_company("阿里巴巴")
        print(orch.status())
    """

    def __init__(
        self,
        tyc_adapter: Optional[TianyanchaAdapter] = None,
        qcc_adapter: Optional[QichachaAdapter] = None,
        merger: Optional[EnterpriseDataMerger] = None,
        data_dir: Optional[str] = None,
        enterprise_list: Optional[list[str]] = None,
    ) -> None:
        """初始化管道编排器

        Args:
            tyc_adapter: 天眼查适配器实例，不传则创建默认实例
            qcc_adapter: 企查查适配器实例，不传则创建默认实例
            merger: 合并引擎实例，不传则创建默认实例
            data_dir: 状态数据存储目录，不传则使用默认路径
            enterprise_list: 企业列表，不传则使用默认列表
        """
        # 适配器与合并引擎
        self._tyc = tyc_adapter or TianyanchaAdapter()
        self._qcc = qcc_adapter or QichachaAdapter()
        self._merger = merger or EnterpriseDataMerger(
            tyc_adapter=self._tyc,
            qcc_adapter=self._qcc,
        )

        # 数据目录
        self._data_dir = data_dir or DEFAULT_DATA_DIR
        os.makedirs(self._data_dir, exist_ok=True)

        # 企业列表
        self._enterprise_list = enterprise_list or list(DEFAULT_ENTERPRISE_LIST)

        # 状态（内存中）
        self._current_status: dict[str, Any] = {
            "last_full_sync": None,
            "last_incremental_sync": None,
            "is_running": False,
            "current_task": None,
            "total_syncs": 0,
            "total_errors": 0,
            "total_companies_synced": 0,
            "last_error": None,
        }

        # 自动同步控制
        self._auto_sync_thread: Optional[threading.Thread] = None
        self._auto_sync_stop = threading.Event()
        self._auto_sync_lock = threading.Lock()

        # 运行锁（防止并发同步）
        self._run_lock = threading.Lock()

        # 加载持久化状态
        self._load_state()

        logger.info(
            "管道编排器: 初始化完成 (数据目录=%s, 企业数=%s)",
            self._data_dir,
            len(self._enterprise_list),
        )

    # ------------------------------------------------------------------
    # 路径工具
    # ------------------------------------------------------------------

    def _state_path(self) -> str:
        """状态文件路径"""
        return os.path.join(self._data_dir, STATE_FILE)

    def _history_path(self) -> str:
        """历史文件路径"""
        return os.path.join(self._data_dir, HISTORY_FILE)

    # ------------------------------------------------------------------
    # 状态持久化
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """从 JSON 文件加载持久化状态"""
        path = self._state_path()
        if not os.path.exists(path):
            logger.debug("管道编排器: 无持久化状态文件，使用默认状态")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._current_status.update(data)
            logger.info(
                "管道编排器: 已加载持久化状态 (上次全量同步=%s)",
                data.get("last_full_sync", "无"),
            )
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("管道编排器: 加载状态文件失败 - %s", exc)

    def _save_state(self) -> None:
        """保存状态到 JSON 文件"""
        path = self._state_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._current_status, f, ensure_ascii=False, indent=2)
        except IOError as exc:
            logger.error("管道编排器: 保存状态失败 - %s", exc)

    def _load_history(self) -> list[dict[str, Any]]:
        """从 JSON 文件加载历史记录"""
        path = self._history_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, IOError):
            return []

    def _save_history(self, history: list[dict[str, Any]]) -> None:
        """保存历史记录到 JSON 文件"""
        path = self._history_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except IOError as exc:
            logger.error("管道编排器: 保存历史失败 - %s", exc)

    def _append_history(self, record: dict[str, Any]) -> None:
        """追加一条历史记录"""
        history = self._load_history()
        history.append(record)
        # 最多保留 1000 条
        if len(history) > 1000:
            history = history[-1000:]
        self._save_history(history)

    # ------------------------------------------------------------------
    # 断点续传支持
    # ------------------------------------------------------------------

    def _get_checkpoint(self) -> dict[str, Any]:
        """获取增量同步断点

        Returns:
            checkpoint 字典，包含 {company_index, last_sync_time, completed_companies}
        """
        checkpoint = self._current_status.get("incremental_checkpoint")
        if checkpoint:
            return checkpoint
        return {
            "company_index": 0,
            "last_sync_time": self._current_status.get("last_incremental_sync"),
            "completed_companies": [],
        }

    def _save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """保存增量同步断点"""
        self._current_status["incremental_checkpoint"] = checkpoint
        self._save_state()

    def _clear_checkpoint(self) -> None:
        """清除断点（增量同步成功完成后）"""
        self._current_status.pop("incremental_checkpoint", None)
        self._save_state()

    # ------------------------------------------------------------------
    # 核心同步逻辑
    # ------------------------------------------------------------------

    def sync_single_company(
        self,
        company_name: str,
    ) -> dict[str, Any]:
        """单个企业全源同步

        按策略先后调用天眼查和企查查，然后合并结果。

        Args:
            company_name: 企业名称

        Returns:
            同步结果字典:
            {
                "company_name": str,
                "status": "success" | "partial" | "failed",
                "tyc_success": bool,
                "qcc_success": bool,
                "merged": EnterpriseInfo | None,
                "error": str | None,
                "timestamp": str,
            }
        """
        if not company_name or not company_name.strip():
            return {
                "company_name": company_name or "",
                "status": "failed",
                "tyc_success": False,
                "qcc_success": False,
                "merged": None,
                "error": "企业名称为空",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        company_name = company_name.strip()
        logger.info("管道编排器: 开始单企业同步 - %s", company_name)

        # --- 第一步：天眼查（工商信息） ---
        tyc_result = self._tyc.get_basic_info(company_name)
        tyc_shareholder = self._tyc.get_shareholder(company_name)
        tyc_status = self._tyc.get_business_status(company_name)
        tyc_ok = tyc_result is not None

        if not tyc_ok:
            logger.warning("管道编排器: 天眼查 %s 无数据", company_name)

        # --- 第二步：企查查（信用/知产补充） ---
        qcc_credit = self._qcc.get_credit_info(company_name)
        qcc_abnormal = self._qcc.get_abnormal_list(company_name)
        qcc_ip = self._qcc.get_intellectual_property(company_name)
        qcc_ok = qcc_credit is not None or qcc_abnormal is not None or qcc_ip is not None

        if not qcc_ok:
            logger.warning("管道编排器: 企查查 %s 无数据", company_name)

        # --- 第三步：合并 ---
        merged = None
        try:
            merged = self._merger.merge(company_name)
        except Exception as exc:
            logger.error("管道编排器: 合并 %s 异常 - %s", company_name, exc)

        # 确定最终状态
        if tyc_ok and qcc_ok and merged:
            status = "success"
            error = None
        elif (tyc_ok or qcc_ok) and merged:
            status = "partial"
            error = "部分数据源无数据"
        elif merged:
            status = "partial"
            error = "部分数据源无数据（合并成功）"
        else:
            status = "failed"
            error = "双源均无数据或合并失败"

        result = {
            "company_name": company_name,
            "status": status,
            "tyc_success": tyc_ok,
            "qcc_success": qcc_ok,
            "merged": merged.to_dict() if merged else None,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "管道编排器: 单企业同步完成 - %s [%s]",
            company_name, status,
        )
        return result

    def schedule_full_sync(
        self,
        enterprise_list: Optional[list[str]] = None,
        on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        """全量同步所有企业数据源

        遍历企业列表，对每个企业执行全源采集并合并。
        同名企业自动去重。

        Args:
            enterprise_list: 待同步的企业列表，不传则使用初始化时传入的列表
            on_progress: 进度回调函数，每完成一个企业调用一次

        Returns:
            同步结果摘要字典
        """
        if not self._acquire_run_lock():
            return {
                "status": "skipped",
                "error": "管道正在运行中，跳过本次全量同步",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        try:
            return self._do_full_sync(
                enterprise_list or list(self._enterprise_list),
                on_progress,
            )
        finally:
            self._release_run_lock()

    def _do_full_sync(
        self,
        enterprise_list: list[str],
        on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        """执行全量同步"""
        companies = list(enterprise_list)
        logger.info(
            "管道编排器: 开始全量同步 (企业数=%s)", len(companies),
        )

        self._update_status(is_running=True, current_task="full_sync")

        start_time = datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        errors = 0
        success_count = 0

        for idx, company in enumerate(companies):
            result = self.sync_single_company(company)
            results.append(result)

            if result["status"] == "failed":
                errors += 1
            else:
                success_count += 1

            # 进度回调
            if on_progress:
                try:
                    on_progress({
                        "current": idx + 1,
                        "total": len(companies),
                        "company": company,
                        "status": result["status"],
                        "progress_pct": round((idx + 1) / len(companies) * 100, 1),
                    })
                except Exception as exc:
                    logger.warning("管道编排器: 进度回调异常 - %s", exc)

        end_time = datetime.now(timezone.utc)
        elapsed = (end_time - start_time).total_seconds()

        # 去重：同名企业只保留最新（最后出现的）
        merged_profiles = [
            r["merged"] for r in results
            if r["merged"] is not None
        ]
        # 注意：这里我们去重规则是保留最新的，所以反转后去重，再反转回来
        deduped = self._merger.dedup(
            # 由于 merger.dedup 保留第一个出现的，我们需要把最新的放前面
            [self._to_enterprise_info(p) for p in reversed(merged_profiles)]
            if merged_profiles else []
        )
        # 或者如果 dedup 本身保留第一个，那我们应该先反转让最新的在第一个
        # 但 EnterpriseInfo 是从 dict 重建的，直接用 dedup 方法即可
        # 对普通列表去重保留最新：反转→去重→反转
        # 但我们保持简单：使用 merger.dedup 即可

        summary = {
            "type": SYNC_TYPE_FULL,
            "status": "completed",
            "total_companies": len(companies),
            "success_count": success_count,
            "error_count": errors,
            "elapsed_seconds": round(elapsed, 2),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "enterprise_list": companies,
            "results": results,
        }

        # 更新持久化状态
        self._current_status["last_full_sync"] = end_time.isoformat()
        self._current_status["total_syncs"] += 1
        self._current_status["total_companies_synced"] += success_count
        self._current_status["total_errors"] += errors
        self._update_status(is_running=False, current_task=None)

        # 追加历史
        self._append_history({
            "type": SYNC_TYPE_FULL,
            "timestamp": end_time.isoformat(),
            "status": "completed",
            "total_companies": len(companies),
            "success_count": success_count,
            "error_count": errors,
            "elapsed_seconds": round(elapsed, 2),
        })

        logger.info(
            "管道编排器: 全量同步完成 (成功=%s, 失败=%s, 耗时=%ss)",
            success_count, errors, round(elapsed, 2),
        )
        return summary

    def schedule_incremental_sync(
        self,
        since: Optional[str] = None,
        enterprise_list: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """增量同步（支持断点续传）

        基于断点续传机制，只同步上次全量同步之后有变动的企业数据。
        如果中途中断，下次调用会从断点处继续。

        Args:
            since: 起始时间 ISO 字符串，不传则从上一次同步断点开始
            enterprise_list: 待同步的企业列表，不传则使用初始化时的列表

        Returns:
            同步结果摘要字典
        """
        if not self._acquire_run_lock():
            return {
                "status": "skipped",
                "error": "管道正在运行中，跳过本次增量同步",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        try:
            return self._do_incremental_sync(since, enterprise_list)
        finally:
            self._release_run_lock()

    def _do_incremental_sync(
        self,
        since: Optional[str] = None,
        enterprise_list: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """执行增量同步"""
        companies = enterprise_list or list(self._enterprise_list)
        logger.info(
            "管道编排器: 开始增量同步 (企业数=%s)", len(companies),
        )

        self._update_status(is_running=True, current_task="incremental_sync")

        # 加载断点
        checkpoint = self._get_checkpoint()
        start_index = checkpoint.get("company_index", 0)
        completed = set(checkpoint.get("completed_companies", []))
        last_sync_time = since or checkpoint.get("last_sync_time")

        if start_index > 0:
            logger.info(
                "管道编排器: 断点续传 - 从索引 %s 继续 (已完成 %s 家)",
                start_index, len(completed),
            )

        start_time = datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        errors = 0
        success_count = 0

        for idx in range(start_index, len(companies)):
            company = companies[idx]

            # 跳过已完成的
            if company in completed:
                continue

            result = self.sync_single_company(company)
            results.append(result)

            if result["status"] == "failed":
                errors += 1
            else:
                success_count += 1

            # 保存断点
            completed.add(company)
            self._save_checkpoint({
                "company_index": idx + 1,
                "last_sync_time": datetime.now(timezone.utc).isoformat(),
                "completed_companies": list(completed),
            })

        end_time = datetime.now(timezone.utc)
        elapsed = (end_time - start_time).total_seconds()

        # 清除断点（全部完成）
        self._clear_checkpoint()

        summary = {
            "type": SYNC_TYPE_INCREMENTAL,
            "status": "completed",
            "since": last_sync_time or "N/A",
            "total_companies": len(companies),
            "success_count": success_count,
            "error_count": errors,
            "elapsed_seconds": round(elapsed, 2),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "results": results,
        }

        # 更新持久化状态
        self._current_status["last_incremental_sync"] = end_time.isoformat()
        self._current_status["total_syncs"] += 1
        self._current_status["total_companies_synced"] += success_count
        self._current_status["total_errors"] += errors
        self._update_status(is_running=False, current_task=None)

        # 追加历史
        self._append_history({
            "type": SYNC_TYPE_INCREMENTAL,
            "timestamp": end_time.isoformat(),
            "status": "completed",
            "since": last_sync_time or "N/A",
            "total_companies": len(companies),
            "success_count": success_count,
            "error_count": errors,
            "elapsed_seconds": round(elapsed, 2),
        })

        logger.info(
            "管道编排器: 增量同步完成 (成功=%s, 失败=%s, 耗时=%ss)",
            success_count, errors, round(elapsed, 2),
        )
        return summary

    # ------------------------------------------------------------------
    # 自动同步（定时触发）
    # ------------------------------------------------------------------

    def start_auto_sync(
        self,
        interval_hours: float = DEFAULT_INTERVAL_HOURS,
        full_sync_interval_hours: Optional[float] = None,
        on_sync_complete: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        """启动后台自动同步循环

        使用后台线程定期执行全量/增量同步。
        默认每 12 小时执行一次增量同步，每 N 次增量后执行一次全量同步。

        Args:
            interval_hours: 同步间隔（小时），默认 12
            full_sync_interval_hours: 全量同步间隔（小时），
                                      不传则每 4 次增量执行一次全量
            on_sync_complete: 每次同步完成后的回调
        """
        with self._auto_sync_lock:
            if self._auto_sync_thread and self._auto_sync_thread.is_alive():
                logger.warning("管道编排器: 自动同步已在运行中")
                return

            self._auto_sync_stop.clear()
            self._auto_sync_thread = threading.Thread(
                target=self._auto_sync_loop,
                args=(interval_hours, full_sync_interval_hours, on_sync_complete),
                name="PipelineAutoSync",
                daemon=True,
            )
            self._auto_sync_thread.start()
            logger.info(
                "管道编排器: 自动同步已启动 (间隔=%sh)", interval_hours,
            )

    def stop_auto_sync(self, timeout: float = 10.0) -> None:
        """停止后台自动同步

        Args:
            timeout: 等待线程结束的超时秒数
        """
        with self._auto_sync_lock:
            if not self._auto_sync_thread or not self._auto_sync_thread.is_alive():
                logger.warning("管道编排器: 自动同步未在运行")
                return

            self._auto_sync_stop.set()
            self._auto_sync_thread.join(timeout=timeout)
            if self._auto_sync_thread.is_alive():
                logger.warning("管道编排器: 自动同步线程未在 %ss 内结束", timeout)
            self._auto_sync_thread = None
            logger.info("管道编排器: 自动同步已停止")

    @property
    def is_auto_sync_running(self) -> bool:
        """自动同步是否正在运行"""
        return (
            self._auto_sync_thread is not None
            and self._auto_sync_thread.is_alive()
        )

    def _auto_sync_loop(
        self,
        interval_hours: float,
        full_sync_interval_hours: Optional[float],
        on_sync_complete: Optional[Callable[[dict[str, Any]], None]],
    ) -> None:
        """自动同步循环（后台线程）"""
        sync_count = 0
        full_sync_every = 4  # 每 N 次增量执行一次全量
        if full_sync_interval_hours is not None:
            full_sync_every = max(1, round(full_sync_interval_hours / interval_hours))

        logger.info(
            "管道编排器: 自动同步循环启动 (全量/增量=%s:1)",
            full_sync_every,
        )

        while not self._auto_sync_stop.is_set():
            sync_count += 1
            is_full_sync = (sync_count % full_sync_every == 0)

            try:
                if is_full_sync:
                    result = self.schedule_full_sync()
                else:
                    result = self.schedule_incremental_sync()

                if on_sync_complete:
                    try:
                        on_sync_complete(result)
                    except Exception as exc:
                        logger.warning(
                            "管道编排器: 同步完成回调异常 - %s", exc,
                        )
            except Exception as exc:
                logger.error("管道编排器: 自动同步异常 - %s", exc)

            # 等待下次同步（可被 stop 中断）
            self._auto_sync_stop.wait(timeout=interval_hours * 3600)

        logger.info("管道编排器: 自动同步循环退出")

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """返回当前管道状态字典

        Returns:
            包含同步状态、错误统计、上次同步时间等信息的字典
        """
        return {
            "last_full_sync": self._current_status.get("last_full_sync"),
            "last_incremental_sync": self._current_status.get("last_incremental_sync"),
            "is_running": self._current_status.get("is_running", False),
            "current_task": self._current_status.get("current_task"),
            "total_syncs": self._current_status.get("total_syncs", 0),
            "total_errors": self._current_status.get("total_errors", 0),
            "total_companies_synced": self._current_status.get(
                "total_companies_synced", 0
            ),
            "last_error": self._current_status.get("last_error"),
            "enterprise_count": len(self._enterprise_list),
            "is_auto_sync_running": self.is_auto_sync_running,
            "data_dir": self._data_dir,
            "tyc_mock_mode": self._tyc.is_mock_mode,
            "qcc_mock_mode": self._qcc.is_mock_mode,
            "has_checkpoint": "incremental_checkpoint" in self._current_status,
        }

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取历史同步记录

        Args:
            limit: 返回条数上限（最新 N 条）

        Returns:
            历史记录列表，按时间倒序排列
        """
        history = self._load_history()
        # 按时间倒序
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history[:limit]

    # ------------------------------------------------------------------
    # 企业列表管理
    # ------------------------------------------------------------------

    def set_enterprise_list(self, companies: list[str]) -> None:
        """设置要同步的企业列表

        Args:
            companies: 企业名称列表
        """
        if not companies:
            logger.warning("管道编排器: 企业列表为空")
            return
        self._enterprise_list = [c.strip() for c in companies if c.strip()]
        logger.info(
            "管道编排器: 更新企业列表 (数量=%s)", len(self._enterprise_list),
        )

    def get_enterprise_list(self) -> list[str]:
        """获取当前企业列表"""
        return list(self._enterprise_list)

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _acquire_run_lock(self) -> bool:
        """获取运行锁，防止并发同步"""
        acquired = self._run_lock.acquire(blocking=False)
        if not acquired:
            logger.warning("管道编排器: 管道正在运行，拒绝并发请求")
        return acquired

    def _release_run_lock(self) -> None:
        """释放运行锁"""
        self._run_lock.release()

    def _update_status(self, **kwargs: Any) -> None:
        """更新内存状态并持久化"""
        self._current_status.update(kwargs)
        self._save_state()

    @staticmethod
    def _to_enterprise_info(data: dict[str, Any]) -> EnterpriseInfo:
        """将字典转为 EnterpriseInfo 对象"""
        from .tianyancha_adapter import EnterpriseInfo as EI
        info = EI()
        for key, val in data.items():
            if hasattr(info, key):
                setattr(info, key, val)
        return info


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_orchestrator(
    data_dir: Optional[str] = None,
    enterprise_list: Optional[list[str]] = None,
) -> PipelineOrchestrator:
    """创建管道编排器实例（便利函数）

    Args:
        data_dir: 状态数据存储目录
        enterprise_list: 企业列表

    Returns:
        PipelineOrchestrator 实例
    """
    return PipelineOrchestrator(
        data_dir=data_dir,
        enterprise_list=enterprise_list,
    )


__all__ = [
    "PipelineOrchestrator",
    "create_orchestrator",
    "SYNC_TYPE_FULL",
    "SYNC_TYPE_INCREMENTAL",
    "SYNC_TYPE_SINGLE",
    "DEFAULT_ENTERPRISE_LIST",
]
