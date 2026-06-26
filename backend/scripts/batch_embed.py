#!/usr/bin/env python
"""
链客宝 - M3E/BGE 离线批量嵌入生成脚本
==========================================

从 SQLite 数据库读取 business_cards 表的企业描述文本，
调用 BgeM3Embedding 编码，通过 EmbedScheduler 调度批处理。

支持:
  - 全量刷新 (full): 编码所有数据并生成新版本
  - 增量更新 (incremental): 仅处理指定时间戳之后的数据
  - 断点续传 (resume): 从中断位置恢复
  - 状态查询 (status): 查看当前进度

用法:
  python scripts/batch_embed.py --mode full [--batch-size 100] [--db-path ...]
  python scripts/batch_embed.py --mode incremental --since 2026-06-24 [--batch-size 100]
  python scripts/batch_embed.py --status
  python scripts/batch_embed.py --resume

Author: 金乌 (P6, 数据分析部, 批量处理专家)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("batch_embed")

# 错误日志文件
ERROR_LOG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "logs", "batch_embed_errors.log"
)

# 默认数据库路径
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "chainke.db"
)

# ---------------------------------------------------------------------------
# 项目导入
# ---------------------------------------------------------------------------

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _import_scheduler() -> Any:
    """延迟导入 EmbedScheduler"""
    from ml.features.embed_scheduler import EmbedScheduler, SQliteDataSource
    return EmbedScheduler, SQliteDataSource


def _import_embedder() -> Any:
    """延迟导入 BgeM3Embedding"""
    from features.embedding_service import BgeM3Embedding
    return BgeM3Embedding


# ---------------------------------------------------------------------------
# 进度报告器
# ---------------------------------------------------------------------------


class ProgressReporter:
    """
    进度报告器。

    每处理 `report_interval` 条记录输出一行进度报告。
    支持显式打印和通过 logger 输出。
    """

    def __init__(self, total: int, report_interval: int = 100, use_logger: bool = True) -> None:
        """
        Args:
            total: 总记录数
            report_interval: 每次报告的间隔条数
            use_logger: 使用 logger 而非 print
        """
        self.total = total
        self.report_interval = report_interval
        self.use_logger = use_logger
        self.processed = 0
        self.failed = 0
        self.start_time = time.perf_counter()
        self._last_report = 0

    def update(self, processed: int, failed: int = 0) -> None:
        """更新进度并条件输出报告"""
        self.processed = processed
        self.failed = failed
        # 每 report_interval 条或完成时报告
        if (self.processed - self._last_report >= self.report_interval) or (
            self.total > 0 and self.processed >= self.total
        ):
            self._report()
            self._last_report = self.processed

    def _report(self) -> None:
        """输出进度报告"""
        elapsed = time.perf_counter() - self.start_time
        pct = (self.processed / self.total * 100) if self.total > 0 else 0.0
        rate = self.processed / elapsed if elapsed > 0 else 0.0
        remaining = self.total - self.processed
        eta = ""
        if rate > 0 and remaining > 0:
            eta_secs = remaining / rate
            if eta_secs < 60:
                eta = f", ETA {eta_secs:.0f}s"
            elif eta_secs < 3600:
                eta = f", ETA {eta_secs / 60:.1f}m"
            else:
                eta = f", ETA {eta_secs / 3600:.1f}h"

        msg = (
            f"[进度] {self.processed}/{self.total} ({pct:.1f}%) | "
            f"失败 {self.failed} | "
            f"速率 {rate:.1f}条/秒 | "
            f"耗时 {elapsed:.1f}s{eta}"
        )

        if self.use_logger:
            logger.info(msg)
        else:
            print(msg)

    def summary(self) -> str:
        """返回最终总结"""
        elapsed = time.perf_counter() - self.start_time
        return (
            f"处理完成: {self.processed}/{self.total} 条, "
            f"失败 {self.failed} 条, "
            f"耗时 {elapsed:.2f}s"
        )


# ---------------------------------------------------------------------------
# 错误记录器
# ---------------------------------------------------------------------------


class ErrorLogger:
    """
    失败记录器，将处理失败的 ID 和错误信息写入 errors.log。
    单条失败不中断整体流程。
    """

    def __init__(self, log_path: str = ERROR_LOG_FILE) -> None:
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log_failure(self, record_id: str, text: str, error: str) -> None:
        """记录一条失败记录"""
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = {
            "timestamp": timestamp,
            "record_id": record_id,
            "text_preview": text[:120] if text else "",
            "error": str(error),
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("写入错误日志失败: %s", e)

    def get_failed_count(self) -> int:
        """获取已记录的失败数量"""
        if not os.path.exists(self.log_path):
            return 0
        count = 0
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for _ in f:
                    count += 1
        except OSError:
            pass
        return count


# ---------------------------------------------------------------------------
# 重试包装器
# ---------------------------------------------------------------------------


def retry_on_timeout(max_retries: int = 3, delay: float = 1.0):
    """
    网络超时自动重试的装饰器。

    捕获 ConnectionError, TimeoutError 等网络异常时自动重试，
    其他异常直接抛出。
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, TimeoutError, OSError) as e:
                    last_error = e
                    logger.warning(
                        "[重试] %s 失败 (尝试 %d/%d): %s",
                        func.__name__, attempt, max_retries, e,
                    )
                    if attempt < max_retries:
                        wait = delay * (2 ** (attempt - 1))
                        logger.info("[重试] %d 秒后重试...", wait)
                        time.sleep(wait)
                except Exception:
                    # 非网络异常直接抛出
                    raise
            # 所有重试耗尽
            logger.error(
                "[重试] %s 在 %d 次尝试后仍然失败: %s",
                func.__name__, max_retries, last_error,
            )
            raise last_error

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 批量嵌入生成器
# ---------------------------------------------------------------------------


class BatchEmbedGenerator:
    """
    批量嵌入生成器。

    整合 EmbedScheduler、BgeM3Embedding 和 SQliteDataSource，
    提供全量刷新、增量更新、断点续传和状态查询功能。
    """

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        batch_size: int = 100,
        force_fallback: bool = False,
        checkpoint_dir: Optional[str] = None,
        report_interval: int = 100,
    ) -> None:
        """
        Args:
            db_path: SQLite 数据库路径
            batch_size: 批处理大小
            force_fallback: 是否强制降级模式（测试用）
            checkpoint_dir: 检查点目录
            report_interval: 进度报告间隔
        """
        self.db_path = os.path.abspath(db_path)
        self.batch_size = batch_size
        self.report_interval = report_interval
        self.error_logger = ErrorLogger()

        # 延迟导入并初始化
        EmbedScheduler, _ = _import_scheduler()
        self._scheduler = EmbedScheduler(
            embedder_kwargs={"force_fallback": force_fallback},
            checkpoint_dir=checkpoint_dir,
        )

        # 进度报告器（在开始调度后初始化）
        self._progress: Optional[ProgressReporter] = None

    # ------------------------------------------------------------------
    # 数据源工厂
    # ------------------------------------------------------------------

    def _make_data_source(self, where_clause: str = "") -> Any:
        """创建 SQliteDataSource 实例"""
        _, SQliteDataSource = _import_scheduler()
        return SQliteDataSource(
            db_path=self.db_path,
            table="business_cards",
            text_field="fields",
            id_field="id",
            where_clause=where_clause,
        )

    @property
    def scheduler(self) -> Any:
        return self._scheduler

    # ------------------------------------------------------------------
    # 全量刷新
    # ------------------------------------------------------------------

    def run_full_refresh(self) -> str:
        """
        执行全量刷新。

        Returns:
            生成的版本号 (如 "v1")
        """
        logger.info("=" * 60)
        logger.info("全量刷新模式")
        logger.info("=" * 60)

        data_source = self._make_data_source()
        total = data_source.get_total_count()
        logger.info("数据库: %s", self.db_path)
        logger.info("数据源: %s", data_source.get_description())
        logger.info("总记录数: %d", total)

        if total == 0:
            logger.warning("数据库为空，无需处理")
            return ""

        # 进度报告器
        self._progress = ProgressReporter(
            total=total,
            report_interval=self.report_interval,
        )

        # 注册回调以更新进度
        version = self._scheduler.schedule_full_refresh(
            data_source=data_source,
            text_field="fields",
            batch_size=self.batch_size,
        )

        # 输出最终总结
        status = self._scheduler.status()
        if self._progress:
            self._progress.update(
                processed=status["processed"],
                failed=status["failed"],
            )
            logger.info(self._progress.summary())

        logger.info("版本: %s", version)
        for v in self._scheduler.list_version_metadata():
            logger.info(
                "  - %s: %d条, %s, model=%s",
                v["version"], v["record_count"], v["created_at"], v["embedding_model"],
            )

        return version

    # ------------------------------------------------------------------
    # 增量更新
    # ------------------------------------------------------------------

    def run_incremental(self, since: Optional[str] = None) -> int:
        """
        执行增量更新。

        Args:
            since: 起始时间戳 (ISO 格式)，None 则处理全部

        Returns:
            处理的数据条数
        """
        logger.info("=" * 60)
        logger.info("增量更新模式")
        logger.info("=" * 60)

        where = ""
        if since:
            where = f"created_at >= '{since}'"
            logger.info("起始时间: %s", since)

        data_source = self._make_data_source(where_clause=where)
        total = data_source.get_total_count()
        logger.info("数据库: %s", self.db_path)
        logger.info("数据源: %s", data_source.get_description())
        logger.info("待处理记录数: %d", total)

        if total == 0:
            logger.info("无增量数据需要处理")
            return 0

        self._progress = ProgressReporter(
            total=total,
            report_interval=self.report_interval,
        )

        processed = self._scheduler.schedule_incremental(
            data_source=data_source,
            text_field="fields",
            since_timestamp=since,
            batch_size=self.batch_size,
        )

        status = self._scheduler.status()
        if self._progress:
            self._progress.update(
                processed=processed,
                failed=status["failed"],
            )
            logger.info(self._progress.summary())

        logger.info("增量更新完成: 处理 %d 条", processed)
        return processed

    # ------------------------------------------------------------------
    # 断点续传
    # ------------------------------------------------------------------

    def run_resume(self) -> Dict[str, Any]:
        """
        从检查点恢复未完成的调度任务。

        Returns:
            结果字典 { "version", "processed", "failed", "status", ... }
        """
        logger.info("=" * 60)
        logger.info("断点续传模式")
        logger.info("=" * 60)

        result = self._scheduler.resume()
        logger.info("恢复状态:")
        for k, v in result.items():
            if k != "checkpoint":
                logger.info("  %s: %s", k, v)

        if result.get("status") == "no_checkpoint":
            logger.warning("没有可恢复的检查点，请使用 --mode full 重新开始")
            return result

        if result.get("status") == "completed":
            logger.info("该任务已完成，无需续传")
            return result

        # 重新执行全量刷新（传入相同 task_id 以实现续传）
        task_id = result.get("task_id", "")
        data_source = self._make_data_source()
        total = data_source.get_total_count()

        self._progress = ProgressReporter(
            total=total,
            report_interval=self.report_interval,
        )

        logger.info("从断点恢复: %s (已处理 %d/%d)", task_id, result.get("processed", 0), total)

        version = self._scheduler.schedule_full_refresh(
            data_source=data_source,
            text_field="fields",
            batch_size=self.batch_size,
            task_id=task_id,
        )

        status = self._scheduler.status()
        if self._progress:
            self._progress.update(
                processed=status["processed"],
                failed=status["failed"],
            )
            logger.info(self._progress.summary())

        return {
            "version": version,
            "task_id": task_id,
            "processed": status["processed"],
            "failed": status["failed"],
            "total": status["total"],
            "status": "completed",
        }

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def show_status(self) -> Dict[str, Any]:
        """显示当前调度状态和版本信息"""
        logger.info("=" * 60)
        logger.info("状态查询")
        logger.info("=" * 60)

        # 当前调度状态
        status = self._scheduler.status()
        logger.info("调度状态:")
        for k, v in status.items():
            logger.info("  %s: %s", k, v)

        # 版本信息
        versions = self._scheduler.list_version_metadata()
        logger.info("版本信息 (共 %d 个):", len(versions))
        if versions:
            for v in versions:
                logger.info(
                    "  - %s | %s | %d条 | %s | %s",
                    v["version"], v["created_at"][:19], v["record_count"],
                    v["embedding_model"], v["status"],
                )
        else:
            logger.info("  (无版本记录)")

        # 检查点信息
        checkpoints = self._scheduler.checkpoint_manager.list_checkpoints()
        logger.info("检查点 (共 %d 个):", len(checkpoints))
        for cp in checkpoints:
            cp_data = self._scheduler.checkpoint_manager.load(cp)
            logger.info(
                "  - %s: %d/%d 已处理",
                cp, cp_data.get("processed_count", 0), cp_data.get("total_count", 0),
            )

        # 错误日志统计
        error_count = self.error_logger.get_failed_count()
        logger.info("错误日志: %s (%d 条)", self.error_logger.log_path, error_count)

        return status


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="链客宝 M3E/BGE 离线批量嵌入生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python scripts/batch_embed.py --mode full
  python scripts/batch_embed.py --mode full --batch-size 200 --db-path ./data/chainke.db
  python scripts/batch_embed.py --mode incremental --since 2026-06-24
  python scripts/batch_embed.py --status
  python scripts/batch_embed.py --resume
  python scripts/batch_embed.py --mode full --force-fallback  (测试用，跳过模型下载)
        """,
    )

    # 模式
    parser.add_argument(
        "--mode", "-m",
        choices=["full", "incremental"],
        help="运行模式: full=全量刷新, incremental=增量更新",
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="查看进度和版本状态",
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="断点续传 (从最近的检查点恢复)",
    )

    # 参数
    parser.add_argument(
        "--db-path", "-d",
        default=DEFAULT_DB_PATH,
        help=f"SQLite 数据库路径 (默认: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=100,
        help="每批编码数量 (默认: 100)",
    )
    parser.add_argument(
        "--since", "-t",
        help="增量更新的起始时间 (ISO 格式, 如 2026-06-24)",
    )
    parser.add_argument(
        "--report-interval",
        type=int,
        default=100,
        help="进度报告间隔 (默认: 100)",
    )
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="强制使用降级嵌入器 (测试用，跳过模型下载)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        help="检查点文件目录 (默认: ~/.cache/chainke/scheduler_checkpoints)",
    )

    args = parser.parse_args(argv)

    # 验证参数
    if not args.mode and not args.status and not args.resume:
        parser.error("请指定运行模式: --mode, --status, 或 --resume")

    if args.mode == "incremental" and not args.since:
        parser.error("增量更新模式需要 --since 参数")

    return args


def main(argv: Optional[List[str]] = None) -> int:
    """主入口"""
    args = parse_args(argv)

    # 确保数据库存在
    db_path = os.path.abspath(args.db_path)

    # 创建生成器
    generator = BatchEmbedGenerator(
        db_path=db_path,
        batch_size=args.batch_size,
        force_fallback=args.force_fallback,
        checkpoint_dir=args.checkpoint_dir,
        report_interval=args.report_interval,
    )

    try:
        if args.status:
            generator.show_status()

        elif args.resume:
            result = generator.run_resume()
            if result.get("status") == "completed":
                logger.info("断点续传完成")
            else:
                logger.warning("断点续传未完成: %s", result.get("message", ""))

        elif args.mode == "full":
            version = generator.run_full_refresh()
            if version:
                logger.info("全量刷新成功，版本: %s", version)
            else:
                logger.warning("全量刷新未生成版本")

        elif args.mode == "incremental":
            processed = generator.run_incremental(since=args.since)
            logger.info("增量更新成功，处理 %d 条", processed)

        return 0

    except KeyboardInterrupt:
        logger.info("\n用户中断")
        return 130

    except Exception as e:
        logger.exception("运行时异常: %s", e)
        return 1


# ---------------------------------------------------------------------------
# 入口点
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
