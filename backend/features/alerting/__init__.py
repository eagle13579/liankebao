"""
链客宝 - 告警通道系统
====================
统一的告警管理框架，支持飞书 Webhook 推送、阈值检测和健康检查回调。

使用示例:
    from backend.features.alerting import AlertManager, FeishuNotifier

    # 方式1: 直接使用 AlertManager
    alert = AlertManager(webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
    alert.alert("系统异常", "数据库连接超时", level="CRITICAL")

    # 方式2: 使用通道
    feishu = FeishuNotifier(webhook_url="...")
    feishu.send_text("Hello from 链客宝!")

    # 方式3: 通过环境变量配置
    import os
    os.environ["FEISHU_WEBHOOK_URL"] = "https://..."
    alert = AlertManager()  # 自动读取环境变量

    # 方式4: 注册健康检查回调
    def on_health_check(health_data):
        if health_data["overall"]["status"] == "critical":
            alert.alert("健康检查失败", str(health_data))

    alert.register_health_callback("critical_alert", on_health_check)
"""

from backend.features.alerting.alerter import (
    AlertManager,
    AlertLevel,
    AlertEvent,
    BaseNotifier,
    LogNotifier,
    create_alert_manager,
)
from backend.features.alerting.channels.feishu import (
    FeishuNotifier,
    FeishuMessageType,
)

__all__ = [
    "AlertManager",
    "AlertLevel",
    "AlertEvent",
    "BaseNotifier",
    "LogNotifier",
    "FeishuNotifier",
    "FeishuMessageType",
    "create_alert_manager",
]
