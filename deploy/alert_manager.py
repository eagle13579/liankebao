#!/usr/bin/env python3
"""
链客宝AI告警管理器 — Alert Manager
==================================
监控服务健康、业务指标异常，通过多渠道发送告警通知。

通道: 钉钉Webhook, 飞书Webhook, 邮件(SMTP)
级别: INFO(日志), WARNING(通知), ERROR(即时通知), CRITICAL(电话模拟)
规则: 服务离线>30s, 500错误率>5%, 支付失败>3次/小时, 注册异常>10次/小时
频率控制: 同一告警30分钟内不重复发送
健康检查: 每60秒检查 :8001/health

启动: python scripts/alert_manager.py --daemon
"""

import argparse
import atexit
import logging
import os
import smtplib
import sys
import time
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from threading import Lock

import requests

# ============================================================
# 配置
# ============================================================

# 添加项目根目录到 sys.path
_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

# ---- 日志配置 ----
LOG_DIR = _BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "alert_manager.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("alert_manager")

# ---- 健康检查目标 ----
HEALTH_CHECK_URL = os.environ.get("HEALTH_CHECK_URL", "http://localhost:8001/health")
HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", "60"))  # 秒

# ---- 告警频率控制（秒） ----
ALERT_COOLDOWN = int(os.environ.get("ALERT_COOLDOWN", "1800"))  # 30分钟

# ---- 钉钉 Webhook ----
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "")

# ---- 飞书 Webhook ----
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")

# ---- 邮件(SMTP) ----
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_TO = os.environ.get("SMTP_TO", "")

# ---- PID文件 ----
PID_DIR = _BASE_DIR / "run"
PID_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = PID_DIR / "alert_manager.pid"

# ---- 告警升级 (PagerDuty风格) ----
ALERT_ESCALATION_MINUTES = int(os.environ.get("ALERT_ESCALATION_MINUTES", "5"))
DINGTALK_ESCALATION_WEBHOOK = os.environ.get(
    "DINGTALK_ESCALATION_WEBHOOK", DINGTALK_WEBHOOK
)

# ---- 维护窗口 ----
# 格式: "MON 02:00-04:00" 或 "SAT,SUN 00:00-23:59" 或 "* 03:00-05:00"
MAINTENANCE_WINDOWS = os.environ.get("MAINTENANCE_WINDOWS", "")
# 示例: MAINTENANCE_WINDOWS="WED 03:00-05:00,SAT 22:00-23:00"


# ============================================================
# 告警级别
# ============================================================
class AlertLevel:
    INFO = "INFO"  # 仅日志
    WARNING = "WARNING"  # 通知（钉钉/飞书）
    ERROR = "ERROR"  # 即时通知（钉钉+飞书+邮件）
    CRITICAL = "CRITICAL"  # 电话模拟（所有通道 + 日志高亮）

    LEVELS = [INFO, WARNING, ERROR, CRITICAL]


# ============================================================
# 频率控制器
# ============================================================
class AlertCooldownManager:
    """同一告警在指定时间内不重复发送"""

    def __init__(self, cooldown_seconds: int = 1800):
        self._cooldown = cooldown_seconds
        self._history: dict[str, datetime] = {}
        self._lock = Lock()

    def can_send(self, alert_key: str) -> bool:
        """检查该告警是否允许发送"""
        now = datetime.now(UTC)
        with self._lock:
            last = self._history.get(alert_key)
            if last and (now - last).total_seconds() < self._cooldown:
                return False
            self._history[alert_key] = now
        return True

    def cleanup(self):
        """清除过期的历史记录"""
        now = datetime.now(UTC)
        with self._lock:
            expired = [
                k
                for k, v in self._history.items()
                if (now - v).total_seconds() >= self._cooldown
            ]
            for k in expired:
                del self._history[k]


# 全局频率控制器
_cooldown_manager = AlertCooldownManager(ALERT_COOLDOWN)


# ============================================================
# 维护窗口管理器
# ============================================================
class MaintenanceWindow:
    """维护窗口 — 在指定时间段内自动静默告警"""

    # 星期名称映射
    WEEKDAY_MAP = {
        "MON": 0,
        "TUE": 1,
        "WED": 2,
        "THU": 3,
        "FRI": 4,
        "SAT": 5,
        "SUN": 6,
    }

    def __init__(self, spec: str):
        """解析维护窗口规格
        格式: "WED 03:00-05:00" 或 "SAT,SUN 00:00-23:59" 或 "* 03:00-05:00"
        """
        self.days: set[int] = set()  # 星期几 (0=Mon..6=Sun)
        self.start_minute: int = 0
        self.end_minute: int = 0
        self._parse(spec)

    def _parse(self, spec: str):
        spec = spec.strip()
        if not spec:
            return
        parts = spec.split()
        if len(parts) != 2:
            logger.warning(f"维护窗口格式错误(需要2部分): {spec}")
            return

        day_part, time_part = parts

        # 解析天
        if day_part == "*":
            self.days = set(range(7))
        else:
            for d in day_part.split(","):
                d = d.strip().upper()
                if d in self.WEEKDAY_MAP:
                    self.days.add(self.WEEKDAY_MAP[d])
                else:
                    logger.warning(f"未知的星期缩写: {d}")

        # 解析时间
        time_range = time_part.split("-")
        if len(time_range) != 2:
            logger.warning(f"维护窗口时间格式错误(需要 HH:MM-HH:MM): {time_part}")
            return

        def _to_minutes(t: str) -> int:
            parts = t.strip().split(":")
            return int(parts[0]) * 60 + int(parts[1])

        self.start_minute = _to_minutes(time_range[0])
        self.end_minute = _to_minutes(time_range[1])

    def is_active(self, now: datetime | None = None) -> bool:
        """检查当前是否在维护窗口内"""
        if now is None:
            now = datetime.now()
        weekday = now.weekday()
        current_minute = now.hour * 60 + now.minute

        if weekday not in self.days:
            return False

        if self.start_minute <= self.end_minute:
            # 正常区间, 如 03:00-05:00
            return self.start_minute <= current_minute < self.end_minute
        else:
            # 跨天区间, 如 22:00-02:00
            return (
                current_minute >= self.start_minute or current_minute < self.end_minute
            )


class MaintenanceWindowManager:
    """维护窗口管理器 — 管理多个维护窗口"""

    def __init__(self, windows_spec: str = ""):
        self.windows: list[MaintenanceWindow] = []
        if windows_spec:
            for spec in windows_spec.split(","):
                spec = spec.strip()
                if spec:
                    self.windows.append(MaintenanceWindow(spec))

    def is_in_maintenance(self, now: datetime | None = None) -> bool:
        """当前是否在任何维护窗口内"""
        if not self.windows:
            return False
        return any(w.is_active(now) for w in self.windows)

    def next_maintenance_end(self, now: datetime | None = None) -> datetime | None:
        """获取下一个维护窗口结束时间"""
        if now is None:
            now = datetime.now()
        # 简单实现: 如果当前在维护窗口, 返回当天的结束时间
        if self.is_in_maintenance(now):
            current_minute = now.hour * 60 + now.minute
            for w in self.windows:
                if w.is_active(now):
                    end_hour = w.end_minute // 60
                    end_min = w.end_minute % 60
                    return now.replace(
                        hour=end_hour, minute=end_min, second=0, microsecond=0
                    )
        return None


# 全局维护窗口管理器
_maintenance_manager = MaintenanceWindowManager(MAINTENANCE_WINDOWS)


# ============================================================
# 告警升级管理器 (PagerDuty风格)
# ============================================================
class AlertEscalationManager:
    """告警升级管理器
    如果 ERROR/CRITICAL 告警在指定时间内未被确认, 升级到更高优先级通道
    升级路径: 默认通道 → 钉钉群(紧急) → 电话(模拟)
    """

    class EscalationEntry:
        def __init__(self, alert_key: str, title: str, message: str, level: str):
            self.alert_key = alert_key
            self.title = title
            self.message = message
            self.level = level
            self.created_at = datetime.now(UTC)
            self.acknowledged = False
            self.acknowledged_by: str | None = None
            self.acknowledged_at: datetime | None = None
            self.escalation_count = 0  # 已升级次数

    def __init__(self, escalation_minutes: int = 5):
        self._escalation_minutes = escalation_minutes
        self._entries: dict[str, AlertEscalationManager.EscalationEntry] = {}
        self._lock = Lock()

    def register_alert(self, alert_key: str, title: str, message: str, level: str):
        """注册一个需要追踪的告警"""
        if level not in (AlertLevel.ERROR, AlertLevel.CRITICAL):
            return
        with self._lock:
            if alert_key not in self._entries:
                self._entries[alert_key] = self.EscalationEntry(
                    alert_key, title, message, level
                )
                logger.info(f"告警已注册升级追踪: {alert_key}")

    def acknowledge(self, alert_key: str, by: str = "system") -> bool:
        """确认告警, 阻止升级"""
        with self._lock:
            entry = self._entries.get(alert_key)
            if entry and not entry.acknowledged:
                entry.acknowledged = True
                entry.acknowledged_by = by
                entry.acknowledged_at = datetime.now(UTC)
                logger.info(f"告警已确认: {alert_key} (by {by})")
                return True
            return False

    def acknowledge_all(self, by: str = "system"):
        """确认所有告警"""
        with self._lock:
            for entry in self._entries.values():
                if not entry.acknowledged:
                    entry.acknowledged = True
                    entry.acknowledged_by = by
                    entry.acknowledged_at = datetime.now(UTC)
            logger.info(f"所有告警已确认 (by {by})")

    def check_escalations(self) -> list[tuple[str, str, str]]:
        """检查需要升级的告警
        返回: [(alert_key, title, message), ...]
        """
        now = datetime.now(UTC)
        escalations = []

        with self._lock:
            for alert_key, entry in list(self._entries.items()):
                if entry.acknowledged:
                    # 已确认的告警, 超过1小时清理
                    if (
                        entry.acknowledged_at
                        and (now - entry.acknowledged_at).total_seconds() > 3600
                    ):
                        del self._entries[alert_key]
                    continue

                elapsed = (now - entry.created_at).total_seconds()
                if elapsed >= self._escalation_minutes * 60:
                    # 未确认且超时, 需要升级
                    entry.escalation_count += 1
                    escalate_level = (
                        "ESCALATED_CRITICAL"
                        if entry.level == AlertLevel.CRITICAL
                        else "ESCALATED_ERROR"
                    )
                    escalations.append(
                        (
                            alert_key,
                            f"[升级#{entry.escalation_count}] {entry.title}",
                            (
                                f"⚠️ **告警升级通知**\n\n"
                                f"原始告警: {entry.title}\n"
                                f"告警级别: {entry.level}\n"
                                f"创建时间: {entry.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"未确认时长: {elapsed:.0f}秒\n"
                                f"升级次数: #{entry.escalation_count}\n\n"
                                f"---\n{entry.message}\n\n"
                                f"**请立即处理! 若已处理请确认:**\n"
                                f"`python alert_manager.py --ack {alert_key}`\n"
                                f"`python alert_manager.py --ack-all`"
                            ),
                        )
                    )
                    # 重置创建时间, 防止重复升级 (每小时最多升级一次)
                    entry.created_at = now

        return escalations

    def cleanup(self):
        """清理已完成的条目"""
        now = datetime.now(UTC)
        with self._lock:
            expired = [
                k
                for k, v in self._entries.items()
                if v.acknowledged
                and v.acknowledged_at
                and (now - v.acknowledged_at).total_seconds() > 7200  # 2小时后清理
            ]
            for k in expired:
                del self._entries[k]


# 全局升级管理器
_escalation_manager = AlertEscalationManager(ALERT_ESCALATION_MINUTES)


# ============================================================
# 通知通道
# ============================================================
class DingTalkNotifier:
    """钉钉群机器人 Webhook 通知"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, title: str, message: str, level: str) -> bool:
        if not self.webhook_url:
            return False
        try:
            color_map = {
                AlertLevel.INFO: "#1890ff",
                AlertLevel.WARNING: "#faad14",
                AlertLevel.ERROR: "#f5222d",
                AlertLevel.CRITICAL: "#ff0000",
            }
            color = color_map.get(level, "#1890ff")
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"[{level}] {title}",
                    "text": (
                        f"### 🔔 链客宝AI告警\n"
                        f'> **级别**: <font color="{color}">{level}</font>\n'
                        f"> **标题**: {title}\n"
                        f"> **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"{message}\n\n"
                        f"---\n"
                        f"链客宝AI告警管理系统"
                    ),
                },
            }
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            logger.info(f"钉钉通知发送结果: HTTP {resp.status_code} {resp.text[:100]}")
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"钉钉通知发送失败: {e}")
            return False


class FeishuNotifier:
    """飞书群机器人 Webhook 通知"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, title: str, message: str, level: str) -> bool:
        if not self.webhook_url:
            return False
        try:
            color_map = {
                AlertLevel.INFO: "blue",
                AlertLevel.WARNING: "yellow",
                AlertLevel.ERROR: "red",
                AlertLevel.CRITICAL: "vermilion",
            }
            tag_color = color_map.get(level, "blue")
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"[{level}] {title}"},
                        "template": tag_color,
                    },
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        },
                        {"tag": "markdown", "content": message},
                        {"tag": "hr"},
                        {
                            "tag": "note",
                            "elements": [
                                {"tag": "plain_text", "content": "链客宝AI告警管理系统"}
                            ],
                        },
                    ],
                },
            }
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            logger.info(f"飞书通知发送结果: HTTP {resp.status_code} {resp.text[:100]}")
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"飞书通知发送失败: {e}")
            return False


class EmailNotifier:
    """SMTP 邮件通知"""

    def __init__(self, host: str, port: int, user: str, password: str, to_addr: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.to_addr = to_addr

    def send(self, title: str, message: str, level: str) -> bool:
        if not all([self.host, self.user, self.password, self.to_addr]):
            return False
        try:
            msg = MIMEText(
                f"<html><body>"
                f"<h2>[{level}] {title}</h2>"
                f"<p><b>时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
                f"<hr><pre>{message}</pre>"
                f"<hr><p><small>链客宝AI告警管理系统</small></p>"
                f"</body></html>",
                "html",
                "utf-8",
            )
            msg["Subject"] = f"[{level}] 链客宝AI告警 - {title}"
            msg["From"] = self.user
            msg["To"] = self.to_addr

            use_tls = self.port == 465
            if use_tls:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=15)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=15)
                server.starttls()

            server.login(self.user, self.password)
            server.sendmail(self.user, [self.to_addr], msg.as_string())
            server.quit()
            logger.info(f"邮件通知发送成功: {self.to_addr}")
            return True
        except Exception as e:
            logger.error(f"邮件通知发送失败: {e}")
            return False


# ============================================================
# 通知分发器
# ============================================================
class AlertDispatcher:
    """根据告警级别分发到各通道"""

    def __init__(self):
        self.notifiers = {
            "dingtalk": DingTalkNotifier(DINGTALK_WEBHOOK),
            "feishu": FeishuNotifier(FEISHU_WEBHOOK),
            "email": EmailNotifier(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_TO),
        }

    def dispatch(self, title: str, message: str, level: str = AlertLevel.ERROR) -> bool:
        """分发告警到对应通道"""
        alert_key = f"{level}:{title}"

        # --- 维护窗口检查: 维护期间自动静默 ---
        if _maintenance_manager.is_in_maintenance():
            logger.info(
                f"[维护窗口] 告警被抑制: {alert_key}\n"
                f"  当前在维护窗口内, 告警已记录但未发送通知"
            )
            # 仍然记录日志, 但不发送通知
            logger.log(
                logging.CRITICAL
                if level == AlertLevel.CRITICAL
                else (
                    logging.ERROR
                    if level == AlertLevel.ERROR
                    else (
                        logging.WARNING if level == AlertLevel.WARNING else logging.INFO
                    )
                ),
                f"[维护窗口-已抑制] [{level}] {title}\n{message}",
            )
            return True

        if not _cooldown_manager.can_send(alert_key):
            logger.info(f"告警被频率限制抑制: {alert_key}")
            return True

        logger.log(
            logging.CRITICAL
            if level == AlertLevel.CRITICAL
            else (
                logging.ERROR
                if level == AlertLevel.ERROR
                else (logging.WARNING if level == AlertLevel.WARNING else logging.INFO)
            ),
            f"[{level}] 发送告警: {title}\n{message}",
        )

        if level == AlertLevel.INFO:
            # INFO 级别只记录日志
            return True

        sent = False
        # WARNING 级别: 通知通道（钉钉/飞书）
        if level == AlertLevel.WARNING:
            for name in ["dingtalk", "feishu"]:
                notifier = self.notifiers.get(name)
                if notifier and notifier.send(title, message, level):
                    sent = True

        # ERROR 级别: 所有通道（钉钉+飞书+邮件）
        elif level == AlertLevel.ERROR:
            for name in ["dingtalk", "feishu", "email"]:
                notifier = self.notifiers.get(name)
                if notifier and notifier.send(title, message, level):
                    sent = True

        # CRITICAL 级别: 所有通道 + 日志高亮
        elif level == AlertLevel.CRITICAL:
            for name in ["dingtalk", "feishu", "email"]:
                notifier = self.notifiers.get(name)
                if notifier and notifier.send(title, message, level):
                    sent = True
            # 模拟电话告警（写入高优先级日志文件）
            self._log_critical_alert(title, message)

        # 注册告警升级追踪 (ERROR 和 CRITICAL 级别)
        if level in (AlertLevel.ERROR, AlertLevel.CRITICAL):
            _escalation_manager.register_alert(alert_key, title, message, level)

        return sent

    def _log_critical_alert(self, title: str, message: str):
        """CRITICAL 告警写入单独的文件（模拟电话告警）"""
        critical_log = LOG_DIR / "critical_alerts.log"
        try:
            with open(critical_log, "a", encoding="utf-8") as f:
                f.write(
                    f"{'=' * 60}\n"
                    f"CRITICAL ALERT: {title}\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Message: {message}\n"
                    f"{'=' * 60}\n\n"
                )
            logger.critical(f"CRITICAL告警已记录到 {critical_log}")
        except Exception as e:
            logger.error(f"写入CRITICAL告警日志失败: {e}")


# 全局分发器
_dispatcher = AlertDispatcher()


# ============================================================
# 告警规则引擎
# ============================================================
class AlertRuleEngine:
    """告警规则引擎 — 检测并触发告警"""

    def __init__(self):
        self._consecutive_failures = 0
        self._last_health_status = True
        self._health_offline_since: datetime | None = None

        # 滑动窗口计数器（业务指标）
        self._window_size = timedelta(hours=1)
        self._error_500_events: list[datetime] = []
        self._payment_fail_events: list[datetime] = []
        self._registration_anomaly_events: list[datetime] = []
        self._request_count = 0
        self._lock = Lock()

    def check_health(self):
        """检查服务健康状态"""
        try:
            resp = requests.get(HEALTH_CHECK_URL, timeout=10)
            healthy = resp.status_code == 200
            if healthy:
                payload = resp.json()
                healthy = payload.get("status") == "ok"
        except requests.RequestException:
            healthy = False

        now = datetime.now(UTC)

        with self._lock:
            if not healthy:
                self._consecutive_failures += 1
                if self._consecutive_failures == 1:
                    self._health_offline_since = now

                # 服务离线>30秒（假设60秒检查间隔，连续1次即>30秒）
                if self._consecutive_failures >= 1:
                    offline_seconds = (
                        (now - self._health_offline_since).total_seconds()
                        if self._health_offline_since
                        else 60
                    )
                    if offline_seconds >= 30:
                        _dispatcher.dispatch(
                            title="服务离线告警",
                            message=(
                                f"后端服务 {HEALTH_CHECK_URL} 无法访问\n"
                                f"连续失败次数: {self._consecutive_failures}\n"
                                f"离线时长: {offline_seconds:.0f}秒\n"
                                f"检测时间: {now.strftime('%Y-%m-%d %H:%M:%S')}"
                            ),
                            level=AlertLevel.CRITICAL
                            if offline_seconds > 120
                            else AlertLevel.ERROR,
                        )
            else:
                # 恢复通知
                if self._consecutive_failures > 0:
                    _dispatcher.dispatch(
                        title="服务恢复通知",
                        message=(
                            f"后端服务 {HEALTH_CHECK_URL} 已恢复\n"
                            f"累计离线次数: {self._consecutive_failures}\n"
                            f"恢复时间: {now.strftime('%Y-%m-%d %H:%M:%S')}"
                        ),
                        level=AlertLevel.INFO,
                    )
                self._consecutive_failures = 0
                self._health_offline_since = None

            self._last_health_status = healthy

        return healthy

    def record_500_error(self, count: int = 1):
        """记录500错误"""
        now = datetime.now(UTC)
        with self._lock:
            self._request_count += max(count, 1)
            for _ in range(count):
                self._error_500_events.append(now)
            # 清理过期事件
            self._prune_window(self._error_500_events)
            self._check_500_error_rate()

    def record_payment_failure(self):
        """记录支付失败"""
        now = datetime.now(UTC)
        with self._lock:
            self._payment_fail_events.append(now)
            self._prune_window(self._payment_fail_events)
            self._check_payment_failures()

    def record_registration_anomaly(self):
        """记录注册异常"""
        now = datetime.now(UTC)
        with self._lock:
            self._registration_anomaly_events.append(now)
            self._prune_window(self._registration_anomaly_events)
            self._check_registration_anomaly()

    def _prune_window(self, events: list):
        """清理超出时间窗口的事件"""
        cutoff = datetime.now(UTC) - self._window_size
        while events and events[0] < cutoff:
            events.pop(0)

    def _check_500_error_rate(self):
        """检查500错误率是否>5%"""
        error_count = len(self._error_500_events)
        total = self._request_count
        if total < 20:  # 样本太少不告警
            return
        rate = (error_count / total) * 100
        if rate > 5:
            _dispatcher.dispatch(
                title="500错误率过高告警",
                message=(
                    f"过去1小时内500错误率: {rate:.2f}% (阈值: 5%)\n"
                    f"错误次数: {error_count}\n"
                    f"总请求数: {total}"
                ),
                level=AlertLevel.ERROR,
            )

    def _check_payment_failures(self):
        """检查支付失败>3次/小时"""
        count = len(self._payment_fail_events)
        if count > 3:
            _dispatcher.dispatch(
                title="支付失败过多告警",
                message=(
                    f"过去1小时内支付失败次数: {count} (阈值: 3次)\n"
                    f"请立即检查支付通道状态"
                ),
                level=AlertLevel.CRITICAL if count > 10 else AlertLevel.ERROR,
            )

    def _check_registration_anomaly(self):
        """检查注册异常>10次/小时"""
        count = len(self._registration_anomaly_events)
        if count > 10:
            _dispatcher.dispatch(
                title="注册异常过多告警",
                message=(
                    f"过去1小时内注册异常次数: {count} (阈值: 10次)\n"
                    f"可能存在恶意注册行为，请检查"
                ),
                level=AlertLevel.ERROR,
            )


# 全局规则引擎
_rule_engine = AlertRuleEngine()


# ============================================================
# 健康检查循环
# ============================================================
def health_check_loop():
    """定期健康检查循环"""
    logger.info(
        f"健康检查循环启动，目标: {HEALTH_CHECK_URL}，间隔: {HEALTH_CHECK_INTERVAL}s"
    )
    escalation_check_counter = 0
    while True:
        try:
            healthy = _rule_engine.check_health()
            status = "OK" if healthy else "FAIL"
            logger.info(f"健康检查: {HEALTH_CHECK_URL} -> {status}")

            # 每轮检查告警升级
            escalation_check_counter += 1
            _check_and_send_escalations()

            # 每10轮清理一次升级记录和频率控制
            if escalation_check_counter >= 10:
                _escalation_manager.cleanup()
                _cooldown_manager.cleanup()
                escalation_check_counter = 0

        except Exception as e:
            logger.error(f"健康检查异常: {e}")
        time.sleep(HEALTH_CHECK_INTERVAL)


def _check_and_send_escalations():
    """检查并发送告警升级通知"""
    try:
        escalations = _escalation_manager.check_escalations()
        for alert_key, title, message in escalations:
            logger.critical(f"告警升级: {title}")
            # 使用钉钉紧急通道发送升级通知
            dingtalk = DingTalkNotifier(DINGTALK_ESCALATION_WEBHOOK)
            dingtalk.send(title, message, AlertLevel.CRITICAL)
            # 也写到CRITICAL日志
            _dispatcher._log_critical_alert(title, message)
    except Exception as e:
        logger.error(f"告警升级检查异常: {e}")


# ============================================================
# Daemon 管理
# ============================================================
def write_pid():
    """写入PID文件"""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    logger.info(f"PID文件已写入: {PID_FILE} (PID: {os.getpid()})")


def remove_pid():
    """删除PID文件"""
    if PID_FILE.exists():
        PID_FILE.unlink()
        logger.info("PID文件已删除")


def is_running() -> bool:
    """检查是否已在运行"""
    if PID_FILE.exists():
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            # 检查进程是否存在（Windows兼容）
            if sys.platform == "win32":
                import ctypes

                handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, ValueError, ProcessLookupError):
            return False
    return False


def daemonize():
    """将进程转为守护进程（仅Linux/Mac，Windows下使用--daemon仅做后台标记）"""
    if sys.platform == "win32":
        logger.info("Windows环境: 跳过daemonize (使用--daemon参数仅做进程管理)")
        return

    pid = os.fork()
    if pid > 0:
        # 父进程退出
        sys.exit(0)

    # 子进程: 创建新的session
    os.setsid()
    os.umask(0)

    # 第二次fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # 重定向标准I/O到/dev/null
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "r") as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(os.devnull, "w") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


# ============================================================
# Main
# ============================================================
def _show_maintenance_status():
    """显示维护窗口状态"""
    maintenance_manager = _maintenance_manager
    if not maintenance_manager.windows:
        print("📋 未配置维护窗口 (设置 MAINTENANCE_WINDOWS 环境变量)")
        return

    print("📋 维护窗口状态:")
    for w in maintenance_manager.windows:
        days_str = (
            ", ".join(
                [k for k, v in MaintenanceWindow.WEEKDAY_MAP.items() if v in w.days]
            )
            or "每天"
        )
        print(
            f"  {days_str} {w.start_minute // 60:02d}:{w.start_minute % 60:02d} - {w.end_minute // 60:02d}:{w.end_minute % 60:02d}"
        )

    now = datetime.now()
    if maintenance_manager.is_in_maintenance(now):
        end = maintenance_manager.next_maintenance_end(now)
        end_str = end.strftime("%H:%M") if end else "?"
        print(f"  🟢 当前在维护窗口内 (预计结束: {end_str})")
    else:
        print("  🔴 当前不在维护窗口内")


def main():
    parser = argparse.ArgumentParser(description="链客宝AI告警管理器")
    parser.add_argument("--daemon", action="store_true", help="以守护进程模式运行")
    parser.add_argument("--stop", action="store_true", help="停止运行中的告警管理器")
    parser.add_argument("--status", action="store_true", help="查看运行状态")
    parser.add_argument(
        "--check-once", action="store_true", help="执行一次健康检查并退出"
    )
    parser.add_argument(
        "--ack",
        type=str,
        default="",
        help="确认指定告警 (告警key, 如 'ERROR:服务离线告警')",
    )
    parser.add_argument("--ack-all", action="store_true", help="确认所有未处理告警")
    parser.add_argument(
        "--maintenance-status", action="store_true", help="查看维护窗口状态"
    )
    args = parser.parse_args()

    if args.status:
        if is_running():
            with open(PID_FILE) as f:
                pid = f.read().strip()
            print(f"✅ 告警管理器正在运行 (PID: {pid})")
            # 同时显示维护窗口状态
            _show_maintenance_status()
            sys.exit(0)
        else:
            print("❌ 告警管理器未运行")
            sys.exit(1)

    if args.maintenance_status:
        _show_maintenance_status()
        sys.exit(0)

    if args.ack:
        acked = _escalation_manager.acknowledge(args.ack, by="cli")
        if acked:
            print(f"✅ 告警已确认: {args.ack}")
        else:
            print(f"⚠️ 告警未找到或已确认: {args.ack}")
        sys.exit(0)

    if args.ack_all:
        _escalation_manager.acknowledge_all(by="cli")
        print("✅ 所有告警已确认")
        sys.exit(0)

    if args.stop:
        if PID_FILE.exists():
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            try:
                if sys.platform == "win32":
                    import ctypes

                    handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid)
                    if handle:
                        ctypes.windll.kernel32.TerminateProcess(handle, 0)
                        ctypes.windll.kernel32.CloseHandle(handle)
                else:
                    os.kill(pid, 15)
                print(f"✅ 告警管理器已停止 (PID: {pid})")
                remove_pid()
            except ProcessLookupError:
                print(f"⚠️ 进程不存在 (PID: {pid})，清理PID文件")
                remove_pid()
            except Exception as e:
                print(f"❌ 停止失败: {e}")
                sys.exit(1)
        else:
            print("❌ PID文件不存在，告警管理器未运行")
        sys.exit(0)

    if args.check_once:
        healthy = _rule_engine.check_health()
        print(f"健康检查: {HEALTH_CHECK_URL} -> {'OK' if healthy else 'FAIL'}")
        sys.exit(0 if healthy else 1)

    if args.daemon:
        if is_running():
            with open(PID_FILE) as f:
                pid = f.read().strip()
            print(f"❌ 告警管理器已在运行 (PID: {pid})")
            sys.exit(1)
        daemonize()
        write_pid()
        atexit.register(remove_pid)

    logger.info("=" * 50)
    logger.info("链客宝AI告警管理器启动")
    logger.info(f"健康检查: {HEALTH_CHECK_URL}")
    logger.info(f"钉钉Webhook: {'已配置' if DINGTALK_WEBHOOK else '未配置'}")
    logger.info(f"飞书Webhook: {'已配置' if FEISHU_WEBHOOK else '未配置'}")
    logger.info(f"邮件SMTP: {'已配置' if SMTP_HOST else '未配置'}")
    logger.info(f"告警频率限制: {ALERT_COOLDOWN}秒")
    logger.info(f"告警升级: {ALERT_ESCALATION_MINUTES}分钟未确认升级")
    maint_count = len(_maintenance_manager.windows)
    logger.info(
        f"维护窗口: {'已配置' + str(maint_count) + '个' if maint_count else '未配置'}"
    )
    if _maintenance_manager.is_in_maintenance():
        logger.info("  → 当前在维护窗口内, 告警将被静默")
    logger.info("=" * 50)

    # 如果没有配置任何通道，打印警告
    if not any([DINGTALK_WEBHOOK, FEISHU_WEBHOOK, SMTP_HOST]):
        logger.warning("未配置任何告警通道！请设置环境变量启用告警通知。")
        logger.warning("  钉钉: DINGTALK_WEBHOOK")
        logger.warning("  飞书: FEISHU_WEBHOOK")
        logger.warning("  邮件: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_TO")

    try:
        health_check_loop()
    except KeyboardInterrupt:
        logger.info("收到中断信号，告警管理器退出")
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
