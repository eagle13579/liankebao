# Developer Portal 迁移实施计划

## 概述

将 `D:\链客宝\backend\app\routers\developer_portal.py`（1025行）迁移到 `D:\chainke-full\backend\`。

**源文件依赖清单**（D:\链客宝\backend\app\）：
| 依赖模块 | 用途 |
|---|---|
| `app.auth → get_current_user` | JWT 用户认证依赖注入 |
| `app.database → get_db` | 数据库会话依赖 |
| `app.middleware.api_key_auth → hash_api_key` | API Key SHA256 哈希 |
| `app.models → ApiKey` | ORM 模型: api_keys 表 |
| `app.models → WebhookSubscriptionDB` | ORM 模型: webhook_subscriptions 表 |
| `app.models → WebhookDeliveryLog` | ORM 模型: webhook_delivery_logs 表 |
| `app.models → ApiUsageLog` | ORM 模型: api_usage_logs 表 |
| `app.webhook_v2 → EventType, WebhookDispatcher, WebhookEvent, create_subscription, delete_subscription` | Webhook 事件系统 |

**目标项目现状**（D:\chainke-full\backend\）：
- `app/database.py` — 有 SQLite 引擎 + `get_db()` + `Base`，**可用**
- `app/models/__init__.py` — 模型包结构，**可扩展**
- `app/middleware/auth_middleware.py` — AuthMiddleware（中间件模式，非 Depends 模式），**无 `get_current_user`**
- `app/routers/auth.py` — 有 JWT 登录端点，**有 User 概念但无 ORM User 表**
- `app/webhook_v2.py` — **不存在**
- `app/middleware/api_key_auth.py` — **不存在**

---

## 步骤总览（共 10 步）

```
步骤 1:  数据库模型 — 新增 4 个 ORM 模型
步骤 2:  Webhook 事件系统 — 移植 webhook_v2.py
步骤 3:  API Key 认证中间件 — 移植 api_key_auth.py
步骤 4:  用户认证适配层 — 创建 auth.py（get_current_user）
步骤 5:  Router 代码移植 — developer_portal.py → chainke-full
步骤 6:  模型注册 — 在 models/__init__.py 和 database.py 中注册新表
步骤 7:  路由注册 — 在 main.py 中注册 developer_portal_router
步骤 8:  中间件注册 — 在 main.py 中注册 api_key 中间件
步骤 9:  数据库迁移 — 创建新表
步骤 10: 验证测试 — 启动服务并测试所有端点
```

---

## 步骤 1: 数据库模型

### 新建文件: `app/models/developer_portal.py`

在 `D:\chainke-full\backend\app\models\` 下新建 `developer_portal.py`，定义4个 ORM 模型：

#### 1. `ApiKey` — 表名 `api_keys`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| key_id | String(64) UNIQUE | 公开标识 ID (lk_xxx) |
| key_hash | String(128) | SHA256 哈希 |
| key_prefix | String(16) | 前8位显示 |
| name | String(100) | Key 名称 |
| user_id | String(64) | 所属用户 ID（字符串，兼容 chainke-full 无 User 表） |
| scopes | String(500) | 权限范围 |
| tier | String(20) DEFAULT 'free' | 等级: free/pro/enterprise |
| rate_limit_per_hour | Integer DEFAULT 100 | 速率限制 |
| is_active | Boolean DEFAULT True | 是否启用 |
| last_used_at | DateTime NULL | 最后使用时间 |
| created_at | DateTime | 创建时间 |
| revoked_at | DateTime NULL | 吊销时间 |

**注意**：chainke-full 没有 ORM User 表，所以 `user_id` 使用 `String(64)` 而非 `ForeignKey("users.id")`，与现有 `BusinessCard.user_id` 保持一致。

#### 2. `WebhookSubscriptionDB` — 表名 `webhook_subscriptions`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| sub_id | String(64) UNIQUE | 订阅标识 (wh_xxx) |
| url | String(1024) | 回调 URL |
| events | String(500) | 事件类型 JSON 数组 |
| secret | String(128) | HMAC 签名密钥 |
| active | Boolean DEFAULT True | 是否启用 |
| user_id | String(64) | 所属用户 ID |
| retry_count | Integer DEFAULT 0 | 重试次数 |
| last_delivery_at | DateTime NULL | 上次投递时间 |
| last_delivery_status | String(100) NULL | 上次投递状态 |
| created_at | DateTime | 创建时间 |

#### 3. `ApiUsageLog` — 表名 `api_usage_logs`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| api_key_id | Integer FK(api_keys.id) | 关联 API Key |
| user_id | String(64) | 用户 ID |
| endpoint | String(255) | 请求路径 |
| method | String(10) | HTTP 方法 |
| status_code | Integer | HTTP 状态码 |
| latency_ms | Integer DEFAULT 0 | 延迟(毫秒) |
| ip_address | String(45) NULL | 客户端 IP |
| created_at | DateTime | 创建时间 |

#### 4. `WebhookDeliveryLog` — 表名 `webhook_delivery_logs`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| subscription_id | Integer FK(webhook_subscriptions.id) | 关联订阅 |
| event_type | String(50) | 事件类型 |
| event_id | String(64) | 事件 ID |
| status | String(20) | success/failed/retrying |
| attempt | Integer DEFAULT 1 | 尝试次数 |
| response_code | Integer NULL | HTTP 响应码 |
| error_message | String(500) NULL | 错误信息 |
| created_at | DateTime | 创建时间 |

### 依赖关系
- 无外部依赖
- 仅需 `from app.database import Base`

---

## 步骤 2: Webhook 事件系统

### 新建文件: `app/webhook_v2.py`

从 `D:\链客宝\backend\app\webhook_v2.py` 完整复制，包含：
- `EventType` 枚举（match/order/payment/user/enterprise/card 事件）
- `WebhookEvent` dataclass（CloudEvents v1.0 格式）
- `WebhookSubscription` dataclass（内存订阅模型）
- `_subscriptions` 内存存储 + 死信队列
- `create_subscription()` / `delete_subscription()` / `get_subscriptions()` / `get_subscriptions_by_event()`
- `WebhookDispatcher` 类（HMAC-SHA256 签名 + 指数退避重试 + 死信队列 + 超时控制）

### 修改说明
- 不需要修改逻辑，直接复制
- 注意 `from app.database import Base` 不需要（此模块无 ORM 模型）

### 依赖关系
- Python 标准库（`urllib.request`）无需额外安装

---

## 步骤 3: API Key 认证中间件

### 新建文件: `app/middleware/api_key_auth.py`

从 `D:\链客宝\backend\app\middleware\api_key_auth.py` 复制，包含：
- `hash_api_key()` — SHA256 哈希
- `verify_api_key()` — 从 `X-API-Key` header 验证
- `log_api_call()` — 记录 API 调用日志
- `check_rate_limit()` — 速率限制检查
- `api_key_middleware()` — FastAPI 中间件

### 修改说明
- 将 `from app.models import ApiKey, ApiUsageLog` 改为 `from app.models.developer_portal import ApiKey, ApiUsageLog`

### 依赖关系
- 步骤 1（新模型）
- 步骤 6（模型注册）

---

## 步骤 4: 用户认证适配层

### 问题分析
chainke-full 现有 `AuthMiddleware`（中间件模式），将 JWT payload 写入 `request.state.user`。但 `developer_portal.py` 使用 `Depends(get_current_user)` 模式（FastAPI 依赖注入），需要适配。

### 方案 A（推荐）: 创建 `app/auth.py` 适配层

新建 `D:\chainke-full\backend\app\auth.py`，提供 `get_current_user` 依赖注入：

```python
from fastapi import Depends, HTTPException, Request, status
from app.database import SessionLocal, get_db

class UserInfo:
    """从 JWT payload 提取的用户信息"""
    def __init__(self, username: str, role: str = "user", user_id: str = None):
        self.username = username
        self.role = role
        self.id = user_id or username
        self.sub = username

def get_current_user(request: Request) -> UserInfo:
    """从 AuthMiddleware 注入的 request.state.user 提取当前用户"""
    if not hasattr(request.state, "user") or request.state.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证，请先登录",
        )
    payload = request.state.user
    username = payload.get("sub", "anonymous")
    role = payload.get("role", "user")
    return UserInfo(username=username, role=role, user_id=username)
```

此方案的优点是：
1. 与现有 `AuthMiddleware` 兼容
2. `developer_portal.py` 无需大幅修改
3. 后续其他路由也可复用

### 方案 B: 直接修改 developer_portal.py 使用 `request.state.user`
如果不想新增文件，可以直接在 developer_portal.py 中使用 `Request` 参数读取 `request.state.user`，但需要大范围修改源代码。**不推荐**。

### 推荐方案: **方案 A**

### 依赖关系
- 无外部依赖

---

## 步骤 5: Router 代码移植

### 新建文件: `app/routers/developer_portal.py`

从源文件复制，修改以下导入路径：

| 源项目导入 | 目标项目导入 |
|---|---|
| `from app.auth import get_current_user` | `from app.auth import get_current_user`（步骤 4 新建） |
| `from app.database import get_db` | `from app.database import get_db`（不变） |
| `from app.middleware.api_key_auth import hash_api_key` | `from app.middleware.api_key_auth import hash_api_key`（步骤 3 新建） |
| `from app.models import ApiKey as ApiKeyModel` | `from app.models.developer_portal import ApiKey as ApiKeyModel` |
| `from app.models import ApiUsageLog, WebhookDeliveryLog, WebhookSubscriptionDB` | `from app.models.developer_portal import ApiUsageLog, WebhookDeliveryLog, WebhookSubscriptionDB` |
| `from app.webhook_v2 import ...` | `from app.webhook_v2 import ...`（步骤 2 新建） |

### 需要包含的端点清单

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | /api/developer/portal | 开发者门户首页 |
| POST | /api/developer/api-keys | 创建 API Key |
| GET | /api/developer/api-keys | 查询 API Keys |
| DELETE | /api/developer/api-keys/{key_id} | 撤销 API Key |
| POST | /api/developer/api-keys/{key_id}/renew | 重新生成 API Key |
| POST | /api/developer/webhooks | 创建 Webhook 订阅 |
| GET | /api/developer/webhooks | 查询 Webhook 订阅列表 |
| GET | /api/developer/webhooks/{sub_id} | 查询单个 Webhook |
| PUT | /api/developer/webhooks/{sub_id} | 更新 Webhook |
| DELETE | /api/developer/webhooks/{sub_id} | 删除 Webhook |
| POST | /api/developer/webhooks/test | 发送测试事件 |
| GET | /api/developer/docs | API 文档汇总 |
| GET | /api/developer/docs/swagger | Swagger UI 页面 |
| GET | /api/developer/usage | 用量统计 |
| GET | /api/developer/usage/timeline | 用量时间线 |
| GET | /api/developer/dashboard | Dashboard 概览 |

### 关键修改点

1. **User 模型差异**：源项目使用 `current_user.id`（int），chainke-full 中 `UserInfo.id` 是 `str`（username）。所有 `current_user.id` 引用需保持为字符串。

2. **`_get_event_description` 函数**: 在文件内部定义，不依赖外部，直接移植。

3. **`TIER_CONFIG` 配置**: 直接移植。

4. **Pydantic 模型**: 直接移植（`CreateApiKeyRequest`, `ApiKeyResponse` 等）。

5. **Swagger UI HTML**: 直接移植（品牌化 UI 不依赖后端配置）。

### 依赖关系
- 步骤 1（新 ORM 模型）
- 步骤 2（webhook_v2.py）
- 步骤 3（api_key_auth.py 的 hash_api_key）
- 步骤 4（auth.py 的 get_current_user）

---

## 步骤 6: 模型注册

### 修改文件: `app/models/__init__.py`

在文件末尾添加新的模型导出：

```python
# 开发者门户模型
from app.models.developer_portal import (
    ApiKey,
    WebhookSubscriptionDB,
    WebhookDeliveryLog,
    ApiUsageLog,
)

# 更新 __all__
__all__.extend([
    "ApiKey",
    "WebhookSubscriptionDB",
    "WebhookDeliveryLog",
    "ApiUsageLog",
])
```

### 修改文件: `app/database.py`（或 `app/models/_legacy.py` 中的 `init_models`）

确保 `init_models()` 能够创建新表。chainke-full 的 `init_models()` 调用 `Base.metadata.create_all(bind=_engine)`，会自动包含新注册的模型。

**不需要额外修改**，因为 `init_models()` 已经调用 `Base.metadata.create_all()`，只要模型在运行时被 import，表就会被自动创建。

### 依赖关系
- 步骤 1

---

## 步骤 7: 路由注册

### 修改文件: `app/main.py`

在路由注册区域添加：

```python
# ── 开发者门户 ────────────────────────────────────────────────────
try:
    from app.routers.developer_portal import router as developer_portal_router
    if developer_portal_router is not None:
        app.include_router(developer_portal_router)
        print("[Main] developer_portal 已注册 → /api/developer/*")
except ImportError as e:
    print(f"[Main] developer_portal 未安装，跳过 ({e})")
```

遵循 chainke-full 的现有风格（try/except 包裹 + print 日志）。

### 依赖关系
- 步骤 5（router 文件就绪）

---

## 步骤 8: 中间件注册

### 修改文件: `app/main.py`

在中间件注册区域（现有 `MetricsMiddleware`, `LoggingMiddleware`, `AuthMiddleware` 之后）添加：

```python
# ── API Key 认证中间件（开发者门户） ────────────────────────────
try:
    from app.middleware.api_key_auth import api_key_middleware
    app.middleware("http")(api_key_middleware)
    print("[Main] api_key_middleware 已注册 → /api/developer/*")
except ImportError as e:
    print(f"[Main] api_key_middleware 未安装，跳过 ({e})")
```

### 依赖关系
- 步骤 3

---

## 步骤 9: 数据库迁移

由于所有项目使用 SQLite + `Base.metadata.create_all()`，只需确保启动时新模型被导入即可自动建表。

### 执行方式
```bash
# 在 chainke-full 后端目录
cd D:\chainke-full\backend
python -c "
from app.database import engine
from app.models import Base
from app.models.developer_portal import ApiKey, WebhookSubscriptionDB, WebhookDeliveryLog, ApiUsageLog
Base.metadata.create_all(bind=engine)
print('所有表已创建')
"
```

### 验证
```bash
python -c "
from app.database import engine
from sqlalchemy import inspect
inspector = inspect(engine)
tables = inspector.get_table_names()
print('现有表:', tables)
assert 'api_keys' in tables
assert 'webhook_subscriptions' in tables
assert 'api_usage_logs' in tables
assert 'webhook_delivery_logs' in tables
print('✓ 开发者门户表创建成功')
"
```

### 回滚方案
删除对应的表文件（SQLite 为单个文件）或手动执行 `DROP TABLE`。

### 依赖关系
- 步骤 6（模型注册后）

---

## 步骤 10: 验证测试

### 10.1 启动服务
```bash
cd D:\chainke-full\backend
python main.py
```

### 10.2 测试端点

| 测试项 | 命令 |
|---|---|
| 门户首页 | `curl http://localhost:8001/api/developer/portal` |
| 登录获取 token | `curl -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}'` |
| 创建 API Key | `curl -X POST http://localhost:8001/api/developer/api-keys -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"name":"test-key","tier":"free"}'` |
| 查询 API Keys | `curl http://localhost:8001/api/developer/api-keys -H "Authorization: Bearer <token>"` |
| 创建 Webhook | `curl -X POST http://localhost:8001/api/developer/webhooks -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"url":"https://example.com/webhook","events":["order.created"]}'` |
| 查询 Webhooks | `curl http://localhost:8001/api/developer/webhooks -H "Authorization: Bearer <token>"` |
| 用量统计 | `curl http://localhost:8001/api/developer/usage -H "Authorization: Bearer <token>"` |
| Dashboard | `curl http://localhost:8001/api/developer/dashboard -H "Authorization: Bearer <token>"` |

### 依赖关系
- 所有前序步骤完成

---

## 完整文件清单与依赖图

```
步骤 1  ────────────────────────────────────────────
  新建: app/models/developer_portal.py
  依赖: app/database.py (已有)

步骤 2  ────────────────────────────────────────────
  新建: app/webhook_v2.py
  依赖: 无

步骤 3  ────────────────────────────────────────────
  新建: app/middleware/api_key_auth.py
  依赖: 步骤 1, 步骤 6

步骤 4  ────────────────────────────────────────────
  新建: app/auth.py
  依赖: app/middleware/auth_middleware.py (已有)

步骤 5  ────────────────────────────────────────────
  新建: app/routers/developer_portal.py
  依赖: 步骤 1, 2, 3, 4

步骤 6  ────────────────────────────────────────────
  修改: app/models/__init__.py
  依赖: 步骤 1

步骤 7  ────────────────────────────────────────────
  修改: app/main.py (路由注册)
  依赖: 步骤 5

步骤 8  ────────────────────────────────────────────
  修改: app/main.py (中间件注册)
  依赖: 步骤 3

步骤 9  ────────────────────────────────────────────
  执行: 数据库建表脚本
  依赖: 步骤 6

步骤 10 ────────────────────────────────────────────
  执行: 启动服务 + 测试
  依赖: 步骤 7, 8, 9
```

**关键依赖链**: 步骤 1 → 步骤 6 → (步骤 3, 5) → (步骤 7, 8)
**并行可执行**: 步骤 2 独立，步骤 4 独立

---

## 风险评估

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| chainke-full 缺少 User ORM 表，`user_id` 使用 String(64) 而非 FK | 中 | 与现有 BusinessCard 模式保持一致，不需外键约束 |
| AuthMiddleware 和 `get_current_user` 兼容性 | 低 | 步骤 4 的适配层已验证可行 |
| `webhook_v2.py` 中 `urllib.request.urlopen` 同步调用在 async 上下文 | 中 | 现有代码已经是同步（FastAPI sync endpoints），如果 future 需要异步可改为 `httpx.AsyncClient` |
| Swagger UI HTML 硬编码了 CDN URL | 低 | 可保留或替换为本地资源 |
| 速率限制使用内存计数（重启丢失） | 低 | 当前已经是 DB 查询实现，不需修改 |
| Webhook 测试端点对外暴露真实请求 | 低 | 需确认是否在生产环境公开 |
