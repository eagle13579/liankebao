# 链客宝 API 门户搭建方案

> 本文档为链客宝 API Portal 的完整设计方案
> 参考源: `D:\链客宝\backend\app\routers\developer_portal.py` (1025行)
> 适用项目: `D:\chainke-full\`
> 交付周期: 3 天

---

## 目录

1. [现状分析](#1-现状分析)
2. [架构概览](#2-架构概览)
3. [最小可行方案（MVP）](#3-最小可行方案mvp)
4. [数据模型设计](#4-数据模型设计)
5. [API 端点设计](#5-api-端点设计)
6. [API 门户 UI 方案](#6-api-门户-ui-方案)
7. [Webhook 管理](#7-webhook-管理)
8. [API Key 管理](#8-api-key-管理)
9. [3天交付计划](#9-3天交付计划)
10. [风险与依赖](#10-风险与依赖)

---

## 1. 现状分析

### 1.1 已具备的能力

| 项目 | 状态 |
|------|------|
| FastAPI 自动 Swagger ( `/docs`, `/redoc` ) | 已存在，但无品牌化 |
| 23 个路由模块、~105 个端点 | 已存在 |
| JWT 认证中间件 (AuthMiddleware) | 已存在 |
| 通知 Webhook 测试/注册端点 ( `notification_router.py` ) | 已存在（简易版，无持久化） |
| 参考实现 ( `developer_portal.py` ) | 存在于 `D:\链客宝`, 含完整 API Key + Webhook + 用量统计 |

### 1.2 缺失的能力

| 能力 | 缺失原因 |
|------|----------|
| API Key 自助管理 | 无 `ApiKey` 模型、无创建/撤销端点、无速率限制 |
| Webhook 订阅管理面板 | 无 `WebhookSubscriptionDB` 模型、无 CRUD、无投递日志 |
| 品牌化 API 文档门户 | 默认 Swagger UI 无品牌 Logo/配色 |
| 开发者控制台 Dashboard | 无概览大屏 |
| 用量统计 | 无 `ApiUsageLog` 模型、无中间件记录 |

### 1.3 参考实现盘点 (`developer_portal.py`)

`D:\链客宝\backend\app\routers\developer_portal.py` (1025行) 已实现：

```
GET    /api/developer/portal                    — 开发者门户首页
POST   /api/developer/api-keys                  — 创建API Key
GET    /api/developer/api-keys                  — 查询API Keys
DELETE /api/developer/api-keys/{key_id}         — 撤销API Key
POST   /api/developer/api-keys/{key_id}/renew   — 续期/重新生成
POST   /api/developer/webhooks                  — 创建Webhook订阅
GET    /api/developer/webhooks                  — 查询Webhook订阅
GET    /api/developer/webhooks/{sub_id}         — 查询单个Webhook
PUT    /api/developer/webhooks/{sub_id}         — 更新Webhook
DELETE /api/developer/webhooks/{sub_id}         — 删除Webhook订阅
POST   /api/developer/webhooks/test             — 发送测试事件
GET    /api/developer/docs                      — API文档 (OpenAPI JSON)
GET    /api/developer/docs/swagger              — Swagger UI 页面
GET    /api/developer/usage                     — 用量统计
GET    /api/developer/usage/timeline            — 用量时间线
GET    /api/developer/dashboard                 — Dashboard 概览
```

同时依赖的数据模型（需迁移到 chainke-full）：

```
ApiKey              — SQLAlchemy 模型 (key_id, key_hash, key_prefix, name, scopes, tier, ...)
WebhookSubscriptionDB — SQLAlchemy 模型 (sub_id, url, events, secret, active, ...)
WebhookDeliveryLog  — SQLAlchemy 模型 (event_type, event_id, status, attempt, ...)
ApiUsageLog         — SQLAlchemy 模型 (user_id, method, endpoint, status_code, latency_ms, ...)
```

---

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    前端浏览器                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │        API 门户 (独立 SPA 或 FastAPI Jinja2)      │  │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────────────┐   │  │
│  │  │ Dashboard│ │API Key   │ │ Webhook 管理     │   │  │
│  │  │ 概览卡片 │ │ 管理面板 │ │ (CRUD + 测试)     │   │  │
│  │  └─────────┘ └──────────┘ └──────────────────┘   │  │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────────────┐   │  │
│  │  │ 品牌化   │ │API文档   │ │ 用量统计         │   │  │
│  │  │ Swagger  │ │ 浏览     │ │ (图表+表格)      │   │  │
│  │  └─────────┘ └──────────┘ └──────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / X-API-Key / JWT
┌────────────────────────▼────────────────────────────────┐
│              FastAPI Backend                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │       developer_portal.py (新增路由模块)           │  │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────────┐  │  │
│  │  │ API Key   │ │ Webhook  │ │ 用量统计       │  │  │
│  │  │ 管理端点   │ │ 管理端点  │ │ / 仪表盘端点   │  │  │
│  │  └───────────┘ └──────────┘ └───────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │        中间件 (Middleware)                         │  │
│  │  APIKeyAuthMiddleware — API Key 鉴权 + 用量记录    │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │        数据模型 (新增)                            │  │
│  │  ApiKey / WebhookSubscriptionDB                  │  │
│  │  WebhookDeliveryLog / ApiUsageLog                │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │        现有路由 (~105个端点)                       │  │
│  │  auth / business-card / matching / ...           │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 3. 最小可行方案 (MVP)

### 3.1 MVP 范围

3天交付的核心功能，共 **15 个 API 端点 + 1 个门户页面 + 3 个数据模型**：

| 模块 | 功能 | 优先级 | 预计工时 |
|------|------|--------|----------|
| **数据模型** | ApiKey, WebhookSubscriptionDB, ApiUsageLog | P0 | 0.5天 |
| **API Key 管理** | 创建/查询/撤销 | P0 | 0.5天 |
| **Webhook 管理** | 创建/查询/更新/删除/测试 | P0 | 0.5天 |
| **品牌化文档门户** | 自定义 Swagger UI + 门户首页 HTML | P0 | 0.5天 |
| **用量统计中间件** | API 调用记录中间件 | P1 | 0.5天 |
| **Dashboard 概览** | Dashboard 端点 + 前端卡片 | P1 | 0.5天 |

### 3.2 MVP 排除项（后续迭代）

| 功能 | 原因 |
|------|------|
| API Key 续期 (renew) | 可通过撤销+重建替代 |
| 用量时间线 (timeline) | 纯可视化增强 |
| SDK 代码生成 | 非核心功能 |
| OAuth2 三方登录 | 依赖微信认证 |
| 多语言门户 | 暂用中文 |

---

## 4. 数据模型设计

### 4.1 ApiKey 模型

在 `app/models/` 下新增 `api_key.py`：

```python
class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_id = Column(String(32), unique=True, nullable=False, index=True)
    key_hash = Column(String(128), nullable=False)
    key_prefix = Column(String(16), nullable=False)
    name = Column(String(100), nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    scopes = Column(String(255), default="read")        # read,write,admin
    tier = Column(String(20), default="free")            # free,pro,enterprise
    rate_limit_per_hour = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 4.2 WebhookSubscriptionDB 模型

在 `app/models/` 下新增 `webhook.py`：

```python
class WebhookSubscriptionDB(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sub_id = Column(String(32), unique=True, nullable=False, index=True)
    url = Column(String(1024), nullable=False)
    events = Column(Text, nullable=False)      # JSON 数组 ["match.created","order.paid"]
    secret = Column(String(128), nullable=False)
    active = Column(Boolean, default=True)
    user_id = Column(Integer, nullable=False, index=True)
    last_delivery_at = Column(DateTime, nullable=True)
    last_delivery_status = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 4.3 ApiUsageLog 模型

在 `app/models/` 下新增 `usage_log.py`：

```python
class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    api_key_id = Column(String(32), nullable=True, index=True)
    method = Column(String(10), nullable=False)
    endpoint = Column(String(255), nullable=False)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Integer, default=0)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
```

### 4.4 模型注册

在 `app/models/__init__.py` 中注册新模型：

```python
from app.models.api_key import ApiKey
from app.models.webhook import WebhookSubscriptionDB, WebhookDeliveryLog
from app.models.usage_log import ApiUsageLog

__all__ += ["ApiKey", "WebhookSubscriptionDB", "WebhookDeliveryLog", "ApiUsageLog"]
```

---

## 5. API 端点设计

### 5.1 开发者门户主路由

**Router:** `APIRouter(prefix="/api/developer", tags=["开发者门户"])`

### 5.2 API Key 管理端点

| 方法 | 路径 | 功能 | Auth |
|------|------|------|------|
| POST | `/api/developer/api-keys` | 创建 API Key | JWT |
| GET | `/api/developer/api-keys` | 查询我的 API Keys | JWT |
| DELETE | `/api/developer/api-keys/{key_id}` | 撤销 API Key | JWT |
| POST | `/api/developer/api-keys/{key_id}/renew` | 续期 API Key(MVP后) | JWT |

**权限分级：**

| 等级 | 速率限制 | 权限范围 | 参考价格 |
|------|----------|----------|----------|
| free | 100次/小时 | read | 免费 |
| pro | 1000次/小时 | read, write | ¥99/月 |
| enterprise | 10000次/小时 | read, write, admin | ¥499/月 |

### 5.3 Webhook 管理端点

| 方法 | 路径 | 功能 | Auth |
|------|------|------|------|
| POST | `/api/developer/webhooks` | 创建 Webhook 订阅 | JWT |
| GET | `/api/developer/webhooks` | 查询我的 Webhooks | JWT |
| GET | `/api/developer/webhooks/{sub_id}` | 查询单个 Webhook 详情(含投递日志) | JWT |
| PUT | `/api/developer/webhooks/{sub_id}` | 更新 Webhook 配置 | JWT |
| DELETE | `/api/developer/webhooks/{sub_id}` | 删除 Webhook 订阅 | JWT |
| POST | `/api/developer/webhooks/test` | 发送测试事件 | JWT |

**支持的事件类型：**

| 事件类型 | 说明 |
|----------|------|
| `match.created` | 匹配创建 |
| `match.accepted` | 匹配接受 |
| `match.rejected` | 匹配拒绝 |
| `order.created` | 订单创建 |
| `order.paid` | 订单支付 |
| `order.completed` | 订单完成 |
| `order.cancelled` | 订单取消 |
| `payment.succeeded` | 支付成功 |
| `payment.failed` | 支付失败 |
| `user.registered` | 用户注册 |
| `card.created` | 名片创建 |
| `card.updated` | 名片更新 |

### 5.4 品牌化文档门户端点

| 方法 | 路径 | 功能 | Auth |
|------|------|------|------|
| GET | `/api/developer/portal` | 开发者门户首页信息 | 公开 |
| GET | `/api/developer/docs` | API 文档汇总 (JSON) | 公开 |
| GET | `/api/developer/docs/swagger` | 品牌化 Swagger UI 页面 | 公开 |

### 5.5 用量统计端点

| 方法 | 路径 | 功能 | Auth |
|------|------|------|------|
| GET | `/api/developer/usage` | 用量统计 (24h/7d/30d) | JWT |
| GET | `/api/developer/usage/timeline` | 用量时间线 (按小时/天聚合) | JWT |
| GET | `/api/developer/dashboard` | Dashboard 概览数据 | JWT |

---

## 6. API 门户 UI 方案

### 6.1 技术选型

| 层 | 方案 | 理由 |
|----|------|------|
| 服务端渲染 | **FastAPI + Jinja2Templates** | 零额外依赖，与现有栈一致 |
| 样式 | **Tailwind CSS (CDN)** | 开发速度快，响应式 |
| 图标 | **Heroicons / Font Awesome** | 免费且美观 |
| Swagger UI | **Swagger UI 5.x CDN** | 与FastAPI原生兼容 |
| 图表(用量) | **Chart.js CDN** | 轻量级，MIT协议 |

### 6.2 门户页面结构

```
开发者门户 SPA (单HTML页面)
├── 导航栏
│   ├── 链客宝 Logo + 品牌名
│   ├── 导航: Dashboard | API Keys | Webhooks | API文档 | 用量
│   └── 用户头像 + 退出
├── Dashboard 概览 (默认页)
│   ├── 卡片1: API Keys 总数 / 活跃数
│   ├── 卡片2: Webhooks 总数 / 活跃数
│   ├── 卡片3: 今日调用次数
│   └── 卡片4: 今日错误率
├── API Key 管理页面
│   ├── 创建 Key 按钮 → 弹出 Modal
│   │   ├── Key 名称 input
│   │   ├── 权限范围 checkbox (read/write/admin)
│   │   ├── 等级选择 (free/pro/enterprise)
│   │   └── 提交 → 显示完整 Key (仅一次)
│   └── Key 列表表格
│       ├── 名称 / 前缀 / 等级 / 权限 / 状态 / 最后使用 / 操作
│       └── 操作: 撤销 | 复制前缀
├── Webhook 管理页面
│   ├── 添加 Webhook 按钮 → 弹出 Modal
│   │   ├── URL input
│   │   ├── 事件多选 (按类别分组)
│   │   ├── Secret (自动生成/手动输入)
│   │   └── 提交
│   └── Webhook 列表表格
│       ├── URL / 事件数 / 状态 / 最后投递 / 操作
│       └── 操作: 详情 | 编辑 | 测试 | 删除
├── API 文档页面
│   ├── 嵌入式品牌化 Swagger UI
│   └── API Key 快速测试区域
└── 用量统计页面
    ├── 时间范围选择器 (1h/24h/7d/30d)
    ├── 统计卡片 (总调用/成功/错误/平均延迟)
    ├── 按端点聚合表格
    └── 时间趋势折线图 (Chart.js)
```

### 6.3 品牌化设计方案

**配色方案：**

```
主色:    #1a73e8 (链客蓝)
辅色:    #00bfa5 (匹配绿)
强调色:  #ff6d00 (活力橙)
背景:    #f8f9fa (浅灰)
卡片:    #ffffff (纯白)
文字:    #202124 (深灰)
副文:    #5f6368 (中灰)
错误:    #d93025 (红色)
警告:    #f9ab00 (黄色)
成功:    #0d904f (绿色)
```

**Logo 与品牌元素：**

- 导航栏左侧放置链客宝 Logo (SVG 格式)
- 页面标题区域显示 "链客宝 API 开发者平台"
- 页脚显示 "© 2026 链客宝 · 企业供需匹配平台"
- Favicon 同步更新

### 6.4 HTML 门户示例结构

门户首页 HTML (Jinja2 模板) — 关键代码片段：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>链客宝 API 开发者平台</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        :root {
            --primary: #1a73e8;
            --secondary: #00bfa5;
            --accent: #ff6d00;
        }
        .bg-primary { background-color: var(--primary); }
        .text-primary { color: var(--primary); }
        .border-primary { border-color: var(--primary); }
        .hover\:bg-primary-dark:hover { background-color: #1557b0; }
        /* ... 更多品牌样式 */
    </style>
</head>
<body class="bg-gray-50">
    <!-- 导航栏 -->
    <nav class="bg-white shadow-sm border-b">
        <div class="max-w-7xl mx-auto px-4">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <img src="/static/logo.svg" alt="链客宝" class="h-8 w-8">
                    <span class="ml-2 text-xl font-bold text-gray-900">链客宝 API</span>
                    <span class="ml-1 text-sm text-gray-500">开发者平台</span>
                </div>
                <div class="flex items-center space-x-4">
                    <a href="#dashboard" class="nav-link">Dashboard</a>
                    <a href="#api-keys" class="nav-link">API Keys</a>
                    <a href="#webhooks" class="nav-link">Webhooks</a>
                    <a href="#docs" class="nav-link">API文档</a>
                    <a href="#usage" class="nav-link">用量</a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Dashboard 概览 -->
    <main class="max-w-7xl mx-auto px-4 py-8">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center">
                    <div class="p-3 rounded-full bg-blue-100 text-blue-600">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                        </svg>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm text-gray-500">API Keys</p>
                        <p class="text-2xl font-semibold">{{ data.api_keys.active }}/{{ data.api_keys.total }}</p>
                    </div>
                </div>
            </div>
            <!-- ... 更多卡片 -->
        </div>
        <!-- ... 其他页面区域 -->
    </main>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // 前端交互逻辑：CRUD API调用、Chart渲染等
    </script>
</body>
</html>
```

### 6.5 文档页面与 Swagger UI 集成

参照 `developer_portal.py` 第 761-820 行的实现，在 `/api/developer/docs/swagger` 返回嵌入 Swagger UI 的 HTML 页面，配置：

- 内链到 `/openapi.json`
- 深色主题 CSS
- 自动注入 JWT Token (从 localStorage)
- `tryItOutEnabled: true` 允许交互测试

---

## 7. Webhook 管理

### 7.1 当前状态

`notification_router.py` 已有：
- `POST /api/notifications/bot/test` — 测试飞书/钉钉群机器人 Webhook
- `POST /api/notifications/bot/register` — 注册 Webhook（仅环境变量，不持久化）

### 7.2 升级方案

基于 `D:\链客宝\developer_portal.py` 中已实现的 Webhook v2 版本：

1. **新建 `app/webhook_v2.py`** — Webhook 事件分发引擎：
   - `EventType` 枚举（支持 18 种事件类型）
   - `WebhookDispatcher` 类（支持正则匹配、指数退避重试、死信队列）
   - `create_subscription()` / `delete_subscription()` 内存存储管理

2. **新建 `app/middleware/api_key_auth.py`** — API Key 鉴权中间件

3. **完善投递日志** — 每次 Webhook 投递记录到 `WebhookDeliveryLog` 表

### 7.3 事件推送流程

```
业务模块 (matching_engine/membership/...) 
    │
    ▼ 调用 dispatch_event(event)
WebhookDispatcher
    │
    ├── 匹配订阅者 (按事件类型)
    ├── 构建 CloudEvents v1.0 格式 Payload
    ├── HMAC-SHA256 签名 (X-Liankebao-Signature)
    ├── HTTP POST 到订阅者 URL
    ├── 失败重试 (指数退避: 2s, 4s, 8s, 最多3次)
    └── 记录投递日志 (WebhookDeliveryLog)
```

---

## 8. API Key 管理

### 8.1 生成策略

```
格式: lk_<96位 hex 前缀> (完整Key: 64位 hex = 128字符)
示例: lk_a1b2c3d4e5f6... (完整Key仅创建时返回一次)

存储:
  - 数据库存储: key_hash (SHA-256), key_prefix (前8位)
  - 用户可见: key_id, key_prefix, name, scopes, tier, status
```

### 8.2 鉴权流程

```
客户端请求
    │
    ▼
检查 X-API-Key Header
    │
    ├── 无 → 继续 JWT 鉴权流程（现有逻辑）
    │
    ▼ 有 Key
查找 key_hash(API-Key) 匹配的 ApiKey 记录
    │
    ├── 不存在 → 401 Unauthorized
    ├── 已撤销/禁用 → 403 Forbidden
    ├── 速率超限 → 429 Too Many Requests
    │
    ▼ 通过
记录 ApiUsageLog (method, endpoint, status_code, latency)
    │
    ▼ 转发到业务路由
```

### 8.3 API Key 鉴权中间件

新建 `app/middleware/api_key_auth.py`:

```python
class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # 查询 DB 验证
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            key_record = db.query(ApiKey).filter(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active == True
            ).first()
            if not key_record:
                return JSONResponse(status_code=401, detail="Invalid API Key")
            # 记录用量
            # 设置 request.state.user
        response = await call_next(request)
        return response
```

---

## 9. 3天交付计划

### Day 1 — 基础设施 (0.5天模型 + 0.5天中间件)

| 时段 | 任务 | 产出 |
|------|------|------|
| 上午 | 创建 4 个数据模型文件 | `app/models/api_key.py` |
| | | `app/models/webhook.py` |
| | | `app/models/usage_log.py` |
| | | 更新 `app/models/__init__.py` |
| 下午 | 创建 API Key 鉴权中间件 | `app/middleware/api_key_auth.py` |
| | 创建 Webhook 分发引擎 | `app/webhook_v2.py`（从 `D:\链客宝` 迁移） |
| | 执行 `alembic upgrade head` | 数据库表创建 |

### Day 2 — 核心端点 (1天)

| 时段 | 任务 | 产出 |
|------|------|------|
| 上午 | 开发 `developer_portal.py` 路由模块 (API Key 部分) | POST/GET/DELETE /api/developer/api-keys |
| | | API Key 创建/查询/撤销逻辑 |
| 下午 | 开发 Webhook 管理端点 | POST/GET/GET/PUT/DELETE/POST /api/developer/webhooks/* |
| | | Webhook 测试 + 投递日志 |

### Day 3 — 门户 UI + 集成测试 (0.5天UI + 0.5天测试)

| 时段 | 任务 | 产出 |
|------|------|------|
| 上午 | 门户首页 HTML 模板 | `templates/developer_portal.html` |
| | 品牌化 Swagger UI | 自定义 Swagger UI 页面 + 配色 |
| | 用量统计端点 | GET /api/developer/usage + timeline |
| | Dashboard 概览 | GET /api/developer/dashboard |
| 下午 | 集成测试 + 注册到 main.py | `app.include_router(developer_portal_router)` |
| | 全面测试 | Postman 测试所有新端点 |
| | 文档更新 | 更新 README + API 文档 |

### 里程碑清单

```
Day 1 18:00 — 数据库迁移成功，4张新表创建完成
Day 2 18:00 — 所有 API Key + Webhook 端点可正常调用
Day 3 12:00 — 门户 UI 渲染正确，Swagger UI 品牌化
Day 3 18:00 — 全部测试通过，PR 合入 main 分支
```

---

## 10. 风险与依赖

### 10.1 依赖项

| 依赖 | 状态 | 说明 |
|------|------|------|
| SQLAlchemy 模型创建 | 需新增 4 个模型文件 | 参考 `D:\链客宝\app\models.py` |
| Alembic 迁移 | 需执行 migration | 确保不破坏现有表 |
| FastAPI Jinja2Templates | 需安装 `jinja2` | 如未安装 `pip install jinja2` |
| 静态文件服务 | 需配置 `/static` 路由 | Logo 图片等 |
| Webhook 分发引擎 | 需从 `D:\链客宝` 迁移 | `app/webhook_v2.py` + `app/middleware/api_key_auth.py` |

### 10.2 风险

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| 模型名冲突 (如 `ApiKey` 已在其他文件定义) | 低 | 扫描现有代码确认 |
| 现有 `notification_router.py` 与新 Webhook 系统重复 | 中 | 保持兼容，新系统作为升级版 |
| 前端 SPA 单页面过大 | 低 | 可分拆为多个模板；MVP 用单页 |
| 3天工期紧张 | 中 | MVP 严格按范围执行；非P0功能延后 |

### 10.3 迁移注意事项

从 `D:\链客宝\backend\` 迁移到 `D:\chainke-full\backend\` 时需注意：

1. **模型路径适配** — `D:\链客宝` 使用扁平 `app/models.py`，`chainke-full` 使用 `app/models/` 包
2. **DB 连接** — `chainke-full` 使用 SQLite (`chainke.db`)，无需额外配置
3. **中间件注册** — 在 `main.py` 中添加新中间件时注意顺序（AuthMiddleware 之后）
4. **Webhook v2 依赖** — 确保 `app/webhook_v2.py` 中没有引用 `D:\链客宝` 特有的模块

---

## 附录 A: 参考文件清单

| 文件 | 位置 | 用途 |
|------|------|------|
| `developer_portal.py` | `D:\链客宝\backend\app\routers\` | 完整的参考实现 (1025行) |
| `notification_router.py` | `D:\chainke-full\backend\app\routers\` | 现有 Webhook 端点 (需升级) |
| `auth.py` | `D:\chainke-full\backend\app\routers\` | JWT 鉴权参考 |
| `main.py` | `D:\chainke-full\backend\app\` | 路由注册参考 |
| `chainke.db` | `D:\chainke-full\backend\app\` | 现有 SQLite 数据库 |

## 附录 B: 新增文件清单 (MVP)

```
backend/app/
├── models/
│   ├── api_key.py          [NEW]  — ApiKey 数据模型
│   ├── webhook.py          [NEW]  — WebhookSubscriptionDB, WebhookDeliveryLog
│   └── usage_log.py        [NEW]  — ApiUsageLog 数据模型
├── middleware/
│   └── api_key_auth.py     [NEW]  — API Key 鉴权中间件
├── routers/
│   └── developer_portal.py [NEW]  — 开发者门户路由 (参考 D:\链客宝 实现)
├── templates/
│   └── developer_portal.html [NEW]— 门户 HTML 模板
├── static/
│   └── logo.svg            [NEW]  — 链客宝 Logo
├── webhook_v2.py           [NEW]  — Webhook 事件分发引擎
└── main.py                 [MOD]  — 注册新路由 + 新中间件
```

---

*文档由 Hermes Agent 生成 | 基于代码扫描和 D:\链客宝\developer_portal.py 参考实现*
