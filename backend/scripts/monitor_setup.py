"""
链客宝 - 数据管道监控 + 飞书告警系统
========================================
监控数据管道的健康状态、数据新鲜度、错误率，并通过飞书 Webhook 推送告警。

能力矩阵：
┌──────────────────────┬──────────────────────────────────────────────┐
│ 类 / 方法             │ 说明                                         │
├──────────────────────┼──────────────────────────────────────────────┤
│ PipelineMonitor      │ 管道监控器（健康检查 / 新鲜度 / 错误率）    │
│  .check_health()     │ 返回每个管道的运行状态/最后同步时间/错误数  │
│  .check_data_freshness() │ 数据新鲜度（距上次同步小时数）           │
│  .check_error_rate() │ 指定小时内错误率                             │
│  .generate_report()  │ Markdown 格式健康报告                        │
├──────────────────────┼──────────────────────────────────────────────┤
│ AlertManager         │ 告警管理器（阈值检查 / 飞书推送 / 本地日志） │
│  .check_thresholds() │ 触发告警的指标列表                           │
│  .send_feishu()      │ 飞书 Webhook 推送                           │
│  .send_log()         │ 本地日志                                     │
└──────────────────────┴──────────────────────────────────────────────┘

告警级别：
  - INFO:    新鲜度 > 4h
  - WARN:    新鲜度 > 12h
  - CRITICAL: 新鲜度 > 24h 或错误率 > 10%

快速开始：
    from backend.scripts.monitor_setup import PipelineMonitor, AlertManager

    monitor = PipelineMonitor()
    report = monitor.generate_report()
    print(report)

    alert = AlertManager()
    metrics = monitor.check_health()
    triggered = alert.check_thresholds(metrics)
    for item in triggered:
        alert.send_feishu(item["message"])
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 数据目录（相对于项目根）
DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "enterprise_sync",
)

# 状态 / 历史文件名
STATE_FILE = "pipeline_state.json"
HISTORY_FILE = "sync_history.json"

# 告警阈值（小时）
FRESHNESS_INFO_HOURS = 4
FRESHNESS_WARN_HOURS = 12
FRESHNESS_CRITICAL_HOURS = 24
ERROR_RATE_CRITICAL = 0.10  # 10%

# 飞书 Webhook URL 环境变量名
ENV_FEISHU_WEBHOOK_URL = "FEISHU_WEBHOOK_URL"


# ---------------------------------------------------------------------------
# 管道监控器
# ---------------------------------------------------------------------------


class PipelineMonitor:
    """数据管道监控器

    封装对 PipelineOrchestrator 状态文件和历史文件的读取分析，
    提供健康检查、数据新鲜度、错误率评估以及 Markdown 报告生成。

    Usage:
        monitor = PipelineMonitor()
        health = monitor.check_health()
        freshness = monitor.check_data_freshness()
        error_rate = monitor.check_error_rate(hours=24)
        report = monitor.generate_report()
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        """初始化监控器

        Args:
            data_dir: 状态数据目录，不传则使用默认路径
        """
        self._data_dir = data_dir or DEFAULT_DATA_DIR

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _state_path(self) -> str:
        return os.path.join(self._data_dir, STATE_FILE)

    def _history_path(self) -> str:
        return os.path.join(self._data_dir, HISTORY_FILE)

    def _load_json(self, path: str) -> Any:
        """安全加载 JSON 文件，失败返回默认值"""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("监控器: 读取 %s 失败 - %s", path, exc)
            return None

    @staticmethod
    def _hours_since(iso_timestamp: Optional[str]) -> Optional[float]:
        """计算从给定 ISO 时间到现在的小时数"""
        if not iso_timestamp:
            return None
        try:
            t = datetime.fromisoformat(iso_timestamp)
            now = datetime.now(timezone.utc)
            # 如果 t 没有时区信息，视作 UTC
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            delta = now - t
            return max(0.0, delta.total_seconds() / 3600.0)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    def check_health(self) -> dict[str, Any]:
        """检查每个管道的运行状态

        Returns:
            字典包含:
            {
                "full_sync": {"last_sync": str|None, "hours_since": float|None,
                              "status": str, "errors": int},
                "incremental_sync": {...},
                "overall": {"status": str, "total_errors": int, "total_syncs": int},
            }
        """
        state = self._load_json(self._state_path())

        if state is None:
            return {
                "full_sync": {
                    "last_sync": None,
                    "hours_since": None,
                    "status": "unknown",
                    "errors": 0,
                },
                "incremental_sync": {
                    "last_sync": None,
                    "hours_since": None,
                    "status": "unknown",
                    "errors": 0,
                },
                "overall": {
                    "status": "unknown",
                    "total_errors": 0,
                    "total_syncs": 0,
                },
            }

        last_full = state.get("last_full_sync")
        last_incr = state.get("last_incremental_sync")
        total_errors = state.get("total_errors", 0)
        total_syncs = state.get("total_syncs", 0)
        is_running = state.get("is_running", False)

        full_hours = self._hours_since(last_full)
        incr_hours = self._hours_since(last_incr)

        # 判断管道状态
        def _pipeline_status(hours: Optional[float]) -> str:
            if hours is None:
                return "never_run"
            if hours < FRESHNESS_INFO_HOURS:
                return "healthy"
            if hours < FRESHNESS_WARN_HOURS:
                return "stale"
            if hours < FRESHNESS_CRITICAL_HOURS:
                return "degraded"
            return "critical"

        full_status = _pipeline_status(full_hours)
        incr_status = _pipeline_status(incr_hours)

        # 整体状态取最差
        severity_order = {"healthy": 0, "never_run": 1, "stale": 2, "degraded": 3, "unknown": 4, "critical": 5}
        overall_status = max(
            [full_status, incr_status],
            key=lambda s: severity_order.get(s, 0),
        )

        return {
            "full_sync": {
                "last_sync": last_full,
                "hours_since": round(full_hours, 2) if full_hours is not None else None,
                "status": full_status,
                "errors": state.get("full_sync_errors", 0),
            },
            "incremental_sync": {
                "last_sync": last_incr,
                "hours_since": round(incr_hours, 2) if incr_hours is not None else None,
                "status": incr_status,
                "errors": state.get("incremental_sync_errors", 0),
            },
            "overall": {
                "status": overall_status,
                "total_errors": total_errors,
                "total_syncs": total_syncs,
                "is_running": is_running,
            },
        }

    # ------------------------------------------------------------------
    # 数据新鲜度
    # ------------------------------------------------------------------

    def check_data_freshness(self) -> dict[str, Any]:
        """检查数据新鲜度

        Returns:
            {
                "full_sync_hours": float|None,
                "incremental_sync_hours": float|None,
                "max_hours": float|None,
                "level": "healthy"|"info"|"warn"|"critical",
            }
        """
        state = self._load_json(self._state_path())

        if state is None:
            return {
                "full_sync_hours": None,
                "incremental_sync_hours": None,
                "max_hours": None,
                "level": "unknown",
            }

        full_hours = self._hours_since(state.get("last_full_sync"))
        incr_hours = self._hours_since(state.get("last_incremental_sync"))

        # 取最新（最小）的那个作为有效新鲜度
        effective_hours = None
        candidates = [h for h in (full_hours, incr_hours) if h is not None]
        if candidates:
            effective_hours = min(candidates)

        # 判断级别
        if effective_hours is None:
            level = "critical"
        elif effective_hours <= FRESHNESS_INFO_HOURS:
            level = "healthy"
        elif effective_hours <= FRESHNESS_WARN_HOURS:
            level = "info"
        elif effective_hours <= FRESHNESS_CRITICAL_HOURS:
            level = "warn"
        else:
            level = "critical"

        return {
            "full_sync_hours": round(full_hours, 2) if full_hours is not None else None,
            "incremental_sync_hours": round(incr_hours, 2) if incr_hours is not None else None,
            "max_hours": round(effective_hours, 2) if effective_hours is not None else None,
            "level": level,
        }

    # ------------------------------------------------------------------
    # 错误率
    # ------------------------------------------------------------------

    def check_error_rate(self, hours: int = 24) -> dict[str, Any]:
        """检查指定时间段内的错误率

        基于同步历史记录计算最近 N 小时内的错误比例。

        Args:
            hours: 统计时间窗口（小时），默认 24h

        Returns:
            {
                "window_hours": int,
                "total_syncs": int,
                "total_errors": int,
                "error_rate": float,
                "status": "healthy"|"critical",
            }
        """
        history = self._load_json(self._history_path())
        if not history or not isinstance(history, list):
            return {
                "window_hours": hours,
                "total_syncs": 0,
                "total_errors": 0,
                "error_rate": 0.0,
                "status": "healthy",
            }

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = []
        for record in history:
            ts = record.get("timestamp")
            if not ts:
                continue
            try:
                t = datetime.fromisoformat(ts)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t >= cutoff:
                    recent.append(record)
            except (ValueError, TypeError):
                continue

        total = len(recent)
        errors = sum(1 for r in recent if r.get("error_count", 0) > 0 or r.get("status") != "completed")
        error_rate = errors / total if total > 0 else 0.0

        status = "critical" if error_rate > ERROR_RATE_CRITICAL else "healthy"

        return {
            "window_hours": hours,
            "total_syncs": total,
            "total_errors": errors,
            "error_rate": round(error_rate, 4),
            "status": status,
        }

    # ------------------------------------------------------------------
    # 健康报告（Markdown）
    # ------------------------------------------------------------------

    def generate_report(self) -> str:
        """生成 Markdown 格式健康报告

        Returns:
            Markdown 格式的报告字符串
        """
        health = self.check_health()
        freshness = self.check_data_freshness()
        error_info = self.check_error_rate(hours=24)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"# 数据管道健康报告",
            "",
            f"**生成时间**: {now_str}",
            f"**数据目录**: `{self._data_dir}`",
            "",
            "---",
            "",
            "## 1. 管道运行状态",
            "",
            "| 管道 | 最后同步时间 | 距现在(h) | 状态 |",
            "|------|------------|----------|------|",
        ]

        def _sync_row(label: str, info: dict) -> str:
            last = info.get("last_sync") or "从未运行"
            hours = info.get("hours_since")
            hours_str = f"{hours:.1f}h" if hours is not None else "N/A"
            status = info.get("status", "unknown")
            return f"| {label} | {last} | {hours_str} | {status} |"

        def _fmt_hours(val):
            """格式化小时数，None 显示为 N/A"""
            if val is None:
                return "N/A"
            return f"{val}h"

        lines.append(_sync_row("全量同步", health.get("full_sync", {})))
        lines.append(_sync_row("增量同步", health.get("incremental_sync", {})))

        overall = health.get("overall", {})
        lines.extend([
            "",
            f"**整体状态**: {overall.get('status', 'unknown')}",
            f"**总同步次数**: {overall.get('total_syncs', 0)}",
            f"**总错误数**: {overall.get('total_errors', 0)}",
            f"**正在运行**: {'是' if overall.get('is_running') else '否'}",
            "",
            "---",
            "",
            "## 2. 数据新鲜度",
            "",
        ])

        f = freshness
        lines.append(f"- 全量同步: {_fmt_hours(f.get('full_sync_hours'))}")
        lines.append(f"- 增量同步: {_fmt_hours(f.get('incremental_sync_hours'))}")
        lines.append(f"- 有效新鲜度: {_fmt_hours(f.get('max_hours'))}")
        lines.append(f"- 级别: **{f.get('level', 'unknown')}**")
        lines.append("")

        # 新鲜度级别说明
        level = f.get("level")
        if level == "healthy":
            lines.append("✅ 数据新鲜，无需处理。")
        elif level == "info":
            lines.append("ℹ️ 数据新鲜度超过 4 小时，建议关注。")
        elif level == "warn":
            lines.append("⚠️ 数据新鲜度超过 12 小时，建议尽快同步。")
        elif level == "critical":
            lines.append("🚨 数据严重过期（超过 24 小时），请立即处理！")

        lines.extend([
            "",
            "---",
            "",
            "## 3. 错误率（最近 24h）",
            "",
        ])

        e = error_info
        lines.append(f"- 统计窗口: {e.get('window_hours', 24)}h")
        lines.append(f"- 同步次数: {e.get('total_syncs', 0)}")
        lines.append(f"- 错误次数: {e.get('total_errors', 0)}")
        lines.append(f"- 错误率: **{e.get('error_rate', 0) * 100:.2f}%**")
        lines.append(f"- 状态: **{e.get('status', 'healthy')}**")

        if e.get("status") == "critical":
            lines.append("")
            lines.append("🚨 错误率超过 10%，请立即检查管道！")

        lines.extend([
            "",
            "---",
            "",
            "*报告由 PipelineMonitor 自动生成*",
        ])

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 告警管理器
# ---------------------------------------------------------------------------


class AlertManager:
    """告警管理器

    检查各项指标是否超过阈值，支持通过飞书 Webhook 推送告警，
    以及写入本地日志。

    告警级别：
      - INFO:    新鲜度 > 4h
      - WARN:    新鲜度 > 12h
      - CRITICAL: 新鲜度 > 24h 或错误率 > 10%

    Usage:
        alert = AlertManager()
        metrics = monitor.check_health()
        triggered = alert.check_thresholds(metrics)
        for item in triggered:
            alert.send_feishu(item["message"])
            alert.send_log(item["message"])
    """

    def __init__(self, webhook_url: Optional[str] = None) -> None:
        """初始化告警管理器

        Args:
            webhook_url: 飞书 Webhook URL，不传则从环境变量读取
        """
        self._webhook_url = webhook_url or os.environ.get(ENV_FEISHU_WEBHOOK_URL, "")
        if not self._webhook_url:
            logger.info("告警管理器: 未设置飞书 Webhook URL，仅本地日志输出")

    # ------------------------------------------------------------------
    # 阈值检查
    # ------------------------------------------------------------------

    def check_thresholds(self, metrics: dict[str, Any]) -> list[dict[str, str]]:
        """检查各项指标是否超过阈值

        Args:
            metrics: 来自 PipelineMonitor.check_health() 的输出

        Returns:
            触发告警的指标列表，每个元素:
            {
                "level": "INFO" | "WARN" | "CRITICAL",
                "metric": str,
                "value": str,
                "message": str,
            }
        """
        triggered: list[dict[str, str]] = []

        # --- 检查全量同步新鲜度 ---
        full = metrics.get("full_sync", {})
        full_hours = full.get("hours_since")
        if full_hours is not None:
            item = self._check_freshness_threshold(
                metric_name="全量同步新鲜度",
                hours=full_hours,
            )
            if item:
                triggered.append(item)

        # --- 检查增量同步新鲜度 ---
        incr = metrics.get("incremental_sync", {})
        incr_hours = incr.get("hours_since")
        if incr_hours is not None:
            item = self._check_freshness_threshold(
                metric_name="增量同步新鲜度",
                hours=incr_hours,
            )
            if item:
                triggered.append(item)

        # --- 检查整体新鲜度（取最新那个）---
        all_hours = [h for h in (full_hours, incr_hours) if h is not None]
        if all_hours:
            effective = min(all_hours)
            item = self._check_freshness_threshold(
                metric_name="数据新鲜度",
                hours=effective,
            )
            if item:
                # 避免与上面重复
                existing_names = {t["metric"] for t in triggered}
                if item["metric"] not in existing_names:
                    triggered.append(item)

        # --- 同步从未运行过 ---
        if full_hours is None and incr_hours is None:
            triggered.append({
                "level": "CRITICAL",
                "metric": "管道从未运行",
                "value": "N/A",
                "message": (
                    "🚨 **[CRITICAL] 管道从未运行**\n"
                    "数据管道尚未执行过任何同步，请立即启动首次同步。"
                ),
            })

        # --- 检查全局错误数 ---
        overall = metrics.get("overall", {})
        total_errors = overall.get("total_errors", 0)
        total_syncs = overall.get("total_syncs", 0)
        if total_syncs > 0:
            error_rate = total_errors / total_syncs
            if error_rate > ERROR_RATE_CRITICAL:
                triggered.append({
                    "level": "CRITICAL",
                    "metric": "整体错误率",
                    "value": f"{error_rate * 100:.2f}%",
                    "message": (
                        "🚨 **[CRITICAL] 整体错误率过高**\n"
                        f"整体错误率: {error_rate * 100:.2f}% (>10%)\n"
                        f"总同步: {total_syncs}, 总错误: {total_errors}"
                    ),
                })
            elif total_errors > 0 and error_rate > ERROR_RATE_CRITICAL * 0.5:
                # 错误率超过 5% 但没到 10%，给个 INFO
                triggered.append({
                    "level": "INFO",
                    "metric": "整体错误率(预警)",
                    "value": f"{error_rate * 100:.2f}%",
                    "message": (
                        "ℹ️ **[INFO] 整体错误率偏高**\n"
                        f"整体错误率: {error_rate * 100:.2f}% (超过5%)\n"
                        f"总同步: {total_syncs}, 总错误: {total_errors}"
                    ),
                })

        return triggered

    def _check_freshness_threshold(
        self,
        metric_name: str,
        hours: float,
    ) -> Optional[dict[str, str]]:
        """检查单个新鲜度指标是否超过阈值"""
        if hours >= FRESHNESS_CRITICAL_HOURS:
            return {
                "level": "CRITICAL",
                "metric": metric_name,
                "value": f"{hours:.1f}h",
                "message": (
                    "🚨 **[CRITICAL] 数据严重过期**\n"
                    f"指标: {metric_name}\n"
                    f"距上次同步: {hours:.1f}h (超过{FRESHNESS_CRITICAL_HOURS}h)\n"
                    "请立即检查管道运行状态！"
                ),
            }
        if hours >= FRESHNESS_WARN_HOURS:
            return {
                "level": "WARN",
                "metric": metric_name,
                "value": f"{hours:.1f}h",
                "message": (
                    "⚠️ **[WARN] 数据同步延迟**\n"
                    f"指标: {metric_name}\n"
                    f"距上次同步: {hours:.1f}h (超过{FRESHNESS_WARN_HOURS}h)\n"
                    "建议尽快同步数据。"
                ),
            }
        if hours >= FRESHNESS_INFO_HOURS:
            return {
                "level": "INFO",
                "metric": metric_name,
                "value": f"{hours:.1f}h",
                "message": (
                    "ℹ️ **[INFO] 数据新鲜度关注**\n"
                    f"指标: {metric_name}\n"
                    f"距上次同步: {hours:.1f}h (超过{FRESHNESS_INFO_HOURS}h)\n"
                    "请安排同步。"
                ),
            }
        return None

    # ------------------------------------------------------------------
    # 飞书 Webhook 推送
    # ------------------------------------------------------------------

    def send_feishu(self, message: str) -> bool:
        """通过飞书 Webhook 推送告警消息

        飞书消息格式为富文本，使用 text / markdown 类型。
        如果未配置 Webhook URL，仅记录日志，不会崩溃。

        Args:
            message: 告警消息内容

        Returns:
            True 表示发送成功或无配置，False 表示发送失败
        """
        if not self._webhook_url:
            logger.info("告警管理器: 未配置飞书 Webhook，消息已忽略")
            return True

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "数据管道告警通知",
                    },
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": message,
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": f"链客宝监控系统 · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                            },
                        ],
                    },
                ],
            },
        }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            self._webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            resp = urlopen(req, timeout=10)
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("StatusCode") == 0:
                logger.info("告警管理器: 飞书消息推送成功")
                return True
            else:
                logger.warning("告警管理器: 飞书推送返回异常 - %s", body)
                return False
        except URLError as exc:
            logger.error("告警管理器: 飞书推送网络错误 - %s", exc)
            return False
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("告警管理器: 飞书推送异常 - %s", exc)
            return False

    # ------------------------------------------------------------------
    # 本地日志
    # ------------------------------------------------------------------

    def send_log(self, message: str) -> None:
        """将告警消息写入本地日志

        Args:
            message: 告警消息内容
        """
        logger.info("告警消息:\n%s", message)


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_monitor(data_dir: Optional[str] = None) -> PipelineMonitor:
    """创建管道监控器实例"""
    return PipelineMonitor(data_dir=data_dir)


def create_alert_manager(webhook_url: Optional[str] = None) -> AlertManager:
    """创建告警管理器实例"""
    return AlertManager(webhook_url=webhook_url)


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "PipelineMonitor",
    "AlertManager",
    "create_monitor",
    "create_alert_manager",
    "FRESHNESS_INFO_HOURS",
    "FRESHNESS_WARN_HOURS",
    "FRESHNESS_CRITICAL_HOURS",
    "ERROR_RATE_CRITICAL",
    "ENV_FEISHU_WEBHOOK_URL",
]
