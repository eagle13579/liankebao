# 链客宝告警通道系统

## 目录结构

```
backend/features/alerting/
├── __init__.py              # 包入口，导出所有核心类
├── alerter.py               # 集成告警管理器 (AlertManager)
├── channels/
│   ├── __init__.py
│   └── feishu.py            # 飞书通知通道 (FeishuNotifier)
└── README.md                # 本文件
```

## 快速开始

### 1. 环境变量配置（推荐）

```bash
# Windows CMD
set FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 或写入 .env 文件
echo FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx >> .env
```

### 2. 发送告警

```python
from backend.features.alerting import AlertManager

alert = AlertManager()
alert.alert("服务异常", "数据库连接超时", level="CRITICAL")
```

### 3. 带指标和值的告警

```python
alert.alert(
    title="磁盘告警",
    message="/data 分区使用率过高",
    level="WARN",
    metric="disk_usage",
    value="92%",
)
```

### 4. 阈值检测（与监控系统集成）

```python
from backend.features.alerting import AlertManager
from backend.scripts.monitor_setup import PipelineMonitor

alert = AlertManager(webhook_url="https://...")
monitor = PipelineMonitor()

health = monitor.check_health()
triggered = alert.check_thresholds(health)
print(f"触发了 {len(triggered)} 条告警")
```

### 5. 健康检查回调

```python
def my_handler(health_data):
    print("健康检查结果:", health_data["overall"]["status"])

alert.register_health_callback("my_handler", my_handler)
alert.run_health_callbacks(monitor.check_health())
```

### 6. 多通道

```python
from backend.features.alerting import BaseNotifier, AlertEvent

class MySms(BaseNotifier):
    def send(self, event: AlertEvent) -> bool:
        print(f"[SMS] {event.title}: {event.message}")
        return True

alert.add_notifier(MySms())
```

## 飞书消息类型

FeishuNotifier 支持三种消息格式：

```python
from backend.features.alerting import FeishuNotifier

n = FeishuNotifier()
n.send_text("纯文本消息")
n.send_markdown("**Markdown** 消息")
n.send_card("标题", "正文", level="WARN", fields=[{"key": "CPU", "value": "95%"}])
n.send_alert("告警", "内容", level="CRITICAL", metric="latency", value="5s")
```

## 告警级别

| 级别     | 严重性 | 说明                   |
|----------|--------|------------------------|
| DEBUG    | 0      | 调试信息               |
| INFO     | 1      | 一般通知/预警          |
| WARN     | 2      | 警告，需关注           |
| CRITICAL | 3      | 严重告警，需立即处理   |

## 配置项

```python
# 设置最低级别（低于此级别不推送）
alert.set_min_level("WARN")

# 设置去重沉默期（秒）
alert.set_dedup_seconds(600)  # 10分钟内相同 metric 不重复推送

# 完全禁用日志兜底
alert = AlertManager(enable_log_notifier=False)

# 纯飞书通道（无日志兜底）
alert = AlertManager.with_feishu(webhook_url="...")

# 开发模式（仅日志，DEBUG级别以上全显示）
alert = AlertManager.with_dev_defaults()
```

## 与现有系统兼容

本模块的 `AlertManager` 和 `create_alert_manager()` 与 `backend/scripts/monitor_setup.py` 
中的同名类和函数接口兼容，可直接替换使用。

```python
# 旧代码（scripts/monitor_setup.py）
from backend.scripts.monitor_setup import AlertManager

# 新代码（features/alerting）
from backend.features.alerting import AlertManager
# 接口完全一致，且新增了多通道、回调等能力
```

## 自定义通知通道

实现 `BaseNotifier` 接口即可：

```python
from backend.features.alerting import BaseNotifier, AlertEvent

class SlackNotifier(BaseNotifier):
    def __init__(self, webhook_url):
        self.url = webhook_url

    def send(self, event: AlertEvent) -> bool:
        # 实现 Slack webhook 调用
        return True

    @property
    def name(self) -> str:
        return "slack"

alert.add_notifier(SlackNotifier("https://hooks.slack.com/..."))
```
