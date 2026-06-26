"""
链客宝 - 集成告警管理器 (AlertManager)
======================================
统一的告警管理器，整合了:
1. 告警级别定义 (AlertLevel)
2. 基础通知通道接口 (BaseNotifier)
3. 飞书 Webhook 推送 (通过 FeishuNotifier 集成)
4. 阈值检测 (数据新鲜度监控、错误率监控)
5. 健康检查回调注册机制
6. 多通道并行推送

快速开始:
    from backend.features.alerting import AlertManager

    # 基础用法 - 直接发送告警
    alert = AlertManager(webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
    alert.alert("系统异常", "数据库连接超时", level="CRITICAL", metric="connection_pool")

    # 阈值检测
    alert.check_thresholds(health_data)  # 从 PipelineMonitor.check_health() 获取

    # 健康检查回调
    alert.register_health_callback("my_cb", lambda data: print(data))
    alert.run_health_callbacks(health_data)

    # 多通道
    alert.add_notifier(my_custom_notifier)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from backend.features.alerting.channels.feishu import FeishuNotifier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量 - 告警阈值（与 monitor_setup.py 保持一致）
# ---------------------------------------------------------------------------

FRESHNESS_INFO_HOURS = 4
FRESHNESS_WARN_HOURS = 12
FRESHNESS_CRITICAL_HOURS = 24
ERROR_RATE_CRITICAL = 0.10  # 10%
ENV_FEISHU_WEBHOOK_URL = "FEISHU_WEBHOOK_URL"


# ---------------------------------------------------------------------------
# 告警级别
# ---------------------------------------------------------------------------


class AlertLevel(str, Enum):
    """告警级别枚举"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"

    def __str__(self) -> str:
        return self.value

    def severity_score(self) -> int:
        """严重性评分（用于排序）"""
        return {"DEBUG": 0, "INFO": 1, "WARN": 2, "CRITICAL": 3}.get(self.value, 0)


# ---------------------------------------------------------------------------
# 告警事件数据类
# ---------------------------------------------------------------------------


@dataclass
class AlertEvent:
    """一次告警事件的完整数据"""

    title: str
    message: str
    level: AlertLevel = AlertLevel.INFO
    metric: Optional[str] = None
    value: Optional[str] = None
    source: str = "alerting"
    timestamp: Optional[str] = None  # ISO 格式，不传则由 AlertManager 填充

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "message": self.message,
            "level": self.level.value,
            "metric": self.metric,
            "value": self.value,
            "source": self.source,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# 通知通道接口
# ---------------------------------------------------------------------------


class BaseNotifier(ABC):
    """通知通道抽象基类

    所有自定义通知通道应继承此类并实现 send() 方法。
    """

    @abstractmethod
    def send(self, event: AlertEvent) -> bool:
        """发送告警事件

        Args:
            event: 告警事件数据

        Returns:
            True 表示发送成功，False 表示失败
        """
        ...

    @property
    def name(self) -> str:
        """通道名称（默认使用类名）"""
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# 内置飞书通知通道适配器
# ---------------------------------------------------------------------------


class _FeishuNotifierAdapter(BaseNotifier):
    """将 FeishuNotifier 适配为 BaseNotifier 接口"""

    def __init__(self, feishu: FeishuNotifier) -> None:
        self._feishu = feishu

    def send(self, event: AlertEvent) -> bool:
        return self._feishu.send_alert(
            title=event.title,
            message=event.message,
            level=event.level.value,
            metric=event.metric,
            value=event.value,
        )

    @property
    def name(self) -> str:
        return "feishu"


# ---------------------------------------------------------------------------
# 日志通知通道（兜底）
# ---------------------------------------------------------------------------


class LogNotifier(BaseNotifier):
    """本地日志通知通道

    将告警写入 Python logging，作为兜底通道。
    """

    def send(self, event: AlertEvent) -> bool:
        level_name = event.level.value
        log_msg = (
            f"[{level_name}] {event.title}"
            + (f" | {event.metric}={event.value}" if event.metric else "")
            + f"\n  {event.message}"
        )
        logger.info("告警消息:\n%s", log_msg)
        return True


# ---------------------------------------------------------------------------
# 告警管理器
# ---------------------------------------------------------------------------


class AlertManager:
    """集成告警管理器

    核心功能:
    1. 多通道推送 - 支持飞书 Webhook、本地日志、以及自定义通知通道
    2. 阈值检测   - 基于 PipelineMonitor 输出的健康数据进行阈值判定
    3. 健康检查回调 - 注册回调函数，在健康检查结果产生时自动触发
    4. 告警去重   - 相同指标在沉默期内不再重复推送

    Usage:
        # 基本用法
        alert = AlertManager()
        alert.alert("磁盘告警", "/data 使用率 95%", level="WARN")

        # 使用飞书 Webhook
        alert = AlertManager(webhook_url="https://...")
        alert.alert("服务异常", "响应超时", level="CRITICAL", metric="latency_p99", value="5s")

        # 阈值检测
        health_data = monitor.check_health()
        triggered = alert.check_thresholds(health_data)

        # 注册健康检查回调
        def on_health(data):
            alert.alert("定期健康检查", str(data["overall"]))
        alert.register_health_callback("periodic", on_health)
        alert.run_health_callbacks(health_data)

        # 添加自定义通道
        class SmsNotifier(BaseNotifier):
            def send(self, event): ...
        alert.add_notifier(SmsNotifier())
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        *,
        min_level: str = "INFO",
        enable_log_notifier: bool = True,
    ) -> None:
        """初始化告警管理器

        Args:
            webhook_url: 飞书 Webhook URL。不传则从环境变量 FEISHU_WEBHOOK_URL 读取。
            min_level:   最低告警级别，低于此级别的告警将被忽略（默认 INFO）
            enable_log_notifier: 是否启用本地日志兜底通道（默认启用）
        """
        self._min_level = AlertLevel(min_level.upper())
        self._notifiers: list[BaseNotifier] = []

        # 默认添加日志兜底通道
        if enable_log_notifier:
            self._notifiers.append(LogNotifier())

        # 如果提供了 Webhook URL 或环境变量存在，添加飞书通道
        feishu_url = webhook_url
        if not feishu_url:
            import os

            feishu_url = os.environ.get(ENV_FEISHU_WEBHOOK_URL)
        if feishu_url:
            feishu = FeishuNotifier(webhook_url=feishu_url)
            self._notifiers.append(_FeishuNotifierAdapter(feishu))
            logger.info("AlertManager: 飞书通知通道已启用")
        else:
            logger.info("AlertManager: 未配置飞书 Webhook，仅使用本地日志通道")

        # 健康检查回调注册表: {name: callable}
        self._health_callbacks: dict[str, Callable[[dict[str, Any]], None]] = {}

        # 告警去重缓存: {metric_key: last_alert_time}
        self._dedup_cache: dict[str, float] = {}
        self._dedup_seconds: float = 300.0  # 默认沉默期 5 分钟

    # ------------------------------------------------------------------
    # 通道管理
    # ------------------------------------------------------------------

    def add_notifier(self, notifier: BaseNotifier) -> "AlertManager":
        """添加自定义通知通道

        Args:
            notifier: 实现了 BaseNotifier 接口的通知通道实例

        Returns:
            self (链式调用)
        """
        self._notifiers.append(notifier)
        logger.info("AlertManager: 添加通知通道 '%s'", notifier.name)
        return self

    def remove_notifier(self, name: str) -> bool:
        """移除指定名称的通知通道

        Args:
            name: 通道名称 (BaseNotifier.name)

        Returns:
            True 表示移除成功，False 表示未找到
        """
        for i, n in enumerate(self._notifiers):
            if n.name == name:
                self._notifiers.pop(i)
                logger.info("AlertManager: 移除通知通道 '%s'", name)
                return True
        return False

    @property
    def notifiers(self) -> list[BaseNotifier]:
        """当前所有注册的通知通道"""
        return list(self._notifiers)

    # ------------------------------------------------------------------
    # 告警推送
    # ------------------------------------------------------------------

    def alert(
        self,
        title: str,
        message: str,
        *,
        level: str = "INFO",
        metric: Optional[str] = None,
        value: Optional[str] = None,
        source: str = "alerting",
        force: bool = False,
    ) -> bool:
        """发送一条告警

        Args:
            title:   告警标题
            message: 告警描述
            level:   告警级别 (DEBUG / INFO / WARN / CRITICAL)
            metric:  触发指标名称（可选，用于去重）
            value:   触发值（可选）
            source:  告警来源
            force:   是否强制发送（跳过级别过滤和去重检查）

        Returns:
            是否至少有一个通道发送成功
        """
        event_level = AlertLevel(level.upper())

        # 级别过滤
        if not force and event_level.severity_score() < self._min_level.severity_score():
            logger.debug(
                "AlertManager: 告警级别 %s 低于最低级别 %s，已忽略",
                event_level,
                self._min_level,
            )
            return False

        # 去重检查
        if not force and metric:
            import time

            now = time.time()
            last = self._dedup_cache.get(metric, 0.0)
            if now - last < self._dedup_seconds:
                logger.debug(
                    "AlertManager: 指标 '%s' 在沉默期内，已去重忽略",
                    metric,
                )
                return False
            self._dedup_cache[metric] = now

        # 构建事件
        event = AlertEvent(
            title=title,
            message=message,
            level=event_level,
            metric=metric,
            value=value,
            source=source,
        )

        # 推送所有通道
        any_success = False
        for notifier in self._notifiers:
            try:
                ok = notifier.send(event)
                if ok:
                    any_success = True
            except Exception as exc:
                logger.error(
                    "AlertManager: 通道 '%s' 发送失败 - %s",
                    notifier.name,
                    exc,
                )

        return any_success

    # ------------------------------------------------------------------
    # 阈值检测
    # ------------------------------------------------------------------

    def check_thresholds(
        self, metrics: dict[str, Any]
    ) -> list[dict[str, str]]:
        """检查各项指标是否超过阈值

        与 scripts/monitor_setup.py 中的 AlertManager.check_thresholds 保持兼容。

        Args:
            metrics: 来自 PipelineMonitor.check_health() 的输出

        Returns:
            触发告警的指标列表，每个元素格式:
            {"level": str, "metric": str, "value": str, "message": str}

        注意：此方法会同时通过所有通知通道推送告警。
        """
        triggered: list[dict[str, str]] = []

        # --- 全量同步新鲜度 ---
        full = metrics.get("full_sync", {})
        full_hours = full.get("hours_since")
        if full_hours is not None:
            item = self._check_freshness_threshold("全量同步新鲜度", full_hours)
            if item:
                triggered.append(item)

        # --- 增量同步新鲜度 ---
        incr = metrics.get("incremental_sync", {})
        incr_hours = incr.get("hours_since")
        if incr_hours is not None:
            item = self._check_freshness_threshold("增量同步新鲜度", incr_hours)
            if item:
                triggered.append(item)

        # --- 整体新鲜度（取最新那个）---
        all_hours = [h for h in (full_hours, incr_hours) if h is not None]
        if all_hours:
            effective = min(all_hours)
            item = self._check_freshness_threshold("数据新鲜度", effective)
            if item:
                existing_names = {t["metric"] for t in triggered}
                if item["metric"] not in existing_names:
                    triggered.append(item)

        # --- 从未运行 ---
        if full_hours is None and incr_hours is None:
            msg = (
                "🚨 **[CRITICAL] 管道从未运行**\\n"
                "数据管道尚未执行过任何同步，请立即启动首次同步。"
            )
            triggered.append({
                "level": "CRITICAL",
                "metric": "管道从未运行",
                "value": "N/A",
                "message": msg,
            })

        # --- 整体错误率 ---
        overall = metrics.get("overall", {})
        total_errors = overall.get("total_errors", 0)
        total_syncs = overall.get("total_syncs", 0)
        if total_syncs > 0:
            error_rate = total_errors / total_syncs
            if error_rate > ERROR_RATE_CRITICAL:
                msg = (
                    "🚨 **[CRITICAL] 整体错误率过高**\\n"
                    f"整体错误率: {error_rate * 100:.2f}% (>10%)\\n"
                    f"总同步: {total_syncs}, 总错误: {total_errors}"
                )
                triggered.append({
                    "level": "CRITICAL",
                    "metric": "整体错误率",
                    "value": f"{error_rate * 100:.2f}%",
                    "message": msg,
                })
            elif total_errors > 0 and error_rate > ERROR_RATE_CRITICAL * 0.5:
                msg = (
                    "ℹ️ **[INFO] 整体错误率偏高**\\n"
                    f"整体错误率: {error_rate * 100:.2f}% (超过5%)\\n"
                    f"总同步: {total_syncs}, 总错误: {total_errors}"
                )
                triggered.append({
                    "level": "INFO",
                    "metric": "整体错误率(预警)",
                    "value": f"{error_rate * 100:.2f}%",
                    "message": msg,
                })

        # 推送所有触发的告警
        for item in triggered:
            self.alert(
                title=f"[{item['level']}] {item['metric']}",
                message=item["message"],
                level=item["level"],
                metric=item["metric"],
                value=item["value"],
                source="threshold_check",
            )

        return triggered

    def _check_freshness_threshold(
        self, metric_name: str, hours: float
    ) -> Optional[dict[str, str]]:
        """检查单个新鲜度指标是否超过阈值"""
        if hours >= FRESHNESS_CRITICAL_HOURS:
            return {
                "level": "CRITICAL",
                "metric": metric_name,
                "value": f"{hours:.1f}h",
                "message": (
                    "🚨 **[CRITICAL] 数据严重过期**\\n"
                    f"指标: {metric_name}\\n"
                    f"距上次同步: {hours:.1f}h (超过{FRESHNESS_CRITICAL_HOURS}h)\\n"
                    "请立即检查管道运行状态！"
                ),
            }
        if hours >= FRESHNESS_WARN_HOURS:
            return {
                "level": "WARN",
                "metric": metric_name,
                "value": f"{hours:.1f}h",
                "message": (
                    "⚠️ **[WARN] 数据同步延迟**\\n"
                    f"指标: {metric_name}\\n"
                    f"距上次同步: {hours:.1f}h (超过{FRESHNESS_WARN_HOURS}h)\\n"
                    "建议尽快同步数据。"
                ),
            }
        if hours >= FRESHNESS_INFO_HOURS:
            return {
                "level": "INFO",
                "metric": metric_name,
                "value": f"{hours:.1f}h",
                "message": (
                    "ℹ️ **[INFO] 数据新鲜度关注**\\n"
                    f"指标: {metric_name}\\n"
                    f"距上次同步: {hours:.1f}h (超过{FRESHNESS_INFO_HOURS}h)\\n"
                    "请安排同步。"
                ),
            }
        return None

    # ------------------------------------------------------------------
    # 健康检查回调
    # ------------------------------------------------------------------

    def register_health_callback(
        self,
        name: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> "AlertManager":
        """注册健康检查回调

        当 run_health_callbacks() 被调用时，所有注册的回调会按注册顺序执行。

        Args:
            name:     回调名称（用于后续取消注册）
            callback: 回调函数，接收 health_data (dict) 作为唯一参数

        Returns:
            self (链式调用)
        """
        if name in self._health_callbacks:
            logger.warning(
                "AlertManager: 健康检查回调 '%s' 已存在，将被覆盖", name
            )
        self._health_callbacks[name] = callback
        logger.debug("AlertManager: 注册健康检查回调 '%s'", name)
        return self

    def unregister_health_callback(self, name: str) -> bool:
        """取消注册健康检查回调

        Args:
            name: 回调名称

        Returns:
            True 表示取消成功，False 表示未找到
        """
        if name in self._health_callbacks:
            del self._health_callbacks[name]
            logger.debug("AlertManager: 取消注册健康检查回调 '%s'", name)
            return True
        return False

    def run_health_callbacks(self, health_data: dict[str, Any]) -> None:
        """运行所有已注册的健康检查回调

        Args:
            health_data: 来自 PipelineMonitor.check_health() 的健康数据
        """
        if not self._health_callbacks:
            return

        logger.debug(
            "AlertManager: 运行 %d 个健康检查回调",
            len(self._health_callbacks),
        )
        for name, cb in self._health_callbacks.items():
            try:
                cb(health_data)
            except Exception as exc:
                logger.error(
                    "AlertManager: 健康检查回调 '%s' 执行失败 - %s",
                    name,
                    exc,
                )

    # ------------------------------------------------------------------
    # 配置方法
    # ------------------------------------------------------------------

    def set_dedup_seconds(self, seconds: float) -> "AlertManager":
        """设置告警去重沉默期

        Args:
            seconds: 沉默期（秒），相同 metric 在此时间内不会重复推送
        """
        self._dedup_seconds = max(0.0, seconds)
        return self

    def set_min_level(self, level: str) -> "AlertManager":
        """设置最低告警级别

        Args:
            level: DEBUG / INFO / WARN / CRITICAL
        """
        self._min_level = AlertLevel(level.upper())
        return self

    # ------------------------------------------------------------------
    # 快捷工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def with_feishu(
        cls,
        webhook_url: Optional[str] = None,
        min_level: str = "INFO",
    ) -> "AlertManager":
        """创建仅包含飞书通道的 AlertManager（不含日志兜底）

        Args:
            webhook_url: 飞书 Webhook URL
            min_level:   最低告警级别
        """
        mgr = cls(
            webhook_url=webhook_url,
            min_level=min_level,
            enable_log_notifier=False,
        )
        # cls() 已经加了飞书通道，但没加日志
        # 如果需要日志兜底再加
        mgr._notifiers.append(LogNotifier())
        return mgr

    @classmethod
    def with_dev_defaults(cls) -> "AlertManager":
        """创建开发环境默认配置的告警管理器

        仅启用本地日志，适合开发和测试环境使用。
        """
        return cls(min_level="DEBUG", enable_log_notifier=True)


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_alert_manager(
    webhook_url: Optional[str] = None,
    min_level: str = "INFO",
) -> AlertManager:
    """创建告警管理器实例（与 monitor_setup.py 兼容）"""
    return AlertManager(webhook_url=webhook_url, min_level=min_level)


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "AlertManager",
    "AlertLevel",
    "AlertEvent",
    "BaseNotifier",
    "LogNotifier",
    "FeishuNotifier",
    "create_alert_manager",
    "FRESHNESS_INFO_HOURS",
    "FRESHNESS_WARN_HOURS",
    "FRESHNESS_CRITICAL_HOURS",
    "ERROR_RATE_CRITICAL",
    "ENV_FEISHU_WEBHOOK_URL",
]
