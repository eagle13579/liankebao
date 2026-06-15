# 链客宝 Feature 资产复用分析报告

> 生成日期: 2026-06-08
> 分析范围: 链客宝(chainke-full) → 赛博参谋 · 盖娅进化大脑 · 其他产品

---

## 1. 链客宝 Feature 资产全景清单（按可复用性排序）

### Tier S — 零修改即可跨产品复用（通用基础设施层）

| # | 模块 | 行数 | 依赖 | 功能 | 复用场景 |
|---|------|------|------|------|---------|
| 1 | `observability.py` | 374 | 纯stdlib | 线程安全指标收集器(请求量/错误率/响应时间分布/P50/P95/P99) + 系统信息(CPU/内存/磁盘) | **所有产品**: 任何FastAPI服务都需要可观测性 |
| 2 | `logging_config.py` | 277 | 纯stdlib+contextvars | 结构化JSON日志 + request_id追踪 + user_id注入 + 动态日志级别切换 | **所有产品**: 目前赛博参谋和盖娅都缺少结构化日志 |
| 3 | `health_routes.py` (内嵌main.py) | — | FastAPI | `/health/live`, `/health/ready` 健康检查端点 | **所有产品**: 容器化/K8s部署标配 |
| 4 | `sentry_config.py` | 76 | sentry_sdk | Sentry DSN惰性初始化，环境变量控制启停 | **所有产品**: 一键接入错误追踪 |
| 5 | `retry_engine.py` | 536 | 纯stdlib+SQLite | 指数退避重试引擎 + 死信队列管理 + 持久化 | **所有产品**: 支付回调/第三方API调用/消息投递 |
| 6 | `slow_query_warning.py` | 118 | SQLAlchemy event | 慢查询监听(>500ms警告, >2s错误+堆栈) | **所有产品**: 数据库性能基线必备 |
| 7 | `optimistic_lock.py` | 73 | FastAPI+SQLAlchemy | 乐观锁冲突检测(version字段+409 Conflict) | **所有产品**: 并发编辑场景标配 |

### Tier A — 少量适配后可跨产品复用（通用中间件层）

| # | 模块 | 行数 | 依赖 | 功能 | 适配工作量 |
|---|------|------|------|------|-----------|
| 8 | `auth.py` | 186 | jose+passlib | JWT(access+refresh) + bcrypt密码哈希 + SHA256旧密码兼容 + Token黑名单 | **低**: 替换SECRET_KEY + 调整User模型字段 |
| 9 | `rbac.py` | 311 | 纯stdlib+FastAPI | Permission注册表 + 角色层次传播 + `require_roles()`依赖注入 + `@require_permission`装饰器 | **低**: 替换PERMISSION_REGISTRY定义 + Membership模型适配 |
| 10 | `rate_limiter.py` | 184 | 纯stdlib | 内存滑动窗口(per-IP/per-user) + 路径前缀匹配 + 环境变量控制启停 | **低**: 调整ROUTE_LIMITS配置即可 |
| 11 | `circuit_breaker.py` | 542 | 纯stdlib+FastAPI | 三态熔断器(CLOSED/OPEN/HALF_OPEN) + 装饰器 + 管理API | **低**: 替换breaker名称即可 |
| 12 | `feature_flags.py` | 634 | 纯stdlib+FastAPI | JSON文件配置 + 热加载(mtime检查) + 4种灰度策略(percentage/org_id/environment/always/never) + 管理API | **低**: 替换BUILTIN_FLAGS定义 |
| 13 | `security_hardening.py` | 522 | cryptography | AES-256-GCM字段加密 + 密钥轮换 + `@encrypted`装饰器 + SQL注入扫描 + CSP头工厂 | **低**: 调整SENSITIVE_FIELDS和CSP策略 |
| 14 | `database.py` | 585 | SQLAlchemy | 三引擎自适应(SQLite/MySQL/PG) + 多租户感知 + 连接池配置 | **低**: 改DB_NAME和model导入路径 |
| 15 | `telemetry.py` | 212 | opentelemetry | OpenTelemetry全链路追踪(FastAPI+SQLAlchemy) + 多后端导出(Jaeger/Tempo/ARMS) | **低**: 改OTEL_SERVICE_NAME |
| 16 | `tenant_middleware.py` | 114 | jose+FastAPI | 多租户上下文提取(X-Org-ID/JWT) + 数据自动隔离 | **中**: 需要产品有多租户需求 |
| 17 | `websocket_manager.py` | 217 | asyncio+FastAPI | WebSocket连接管理器(多用户/多设备/在线统计) | **低**: 通用，直接复制 |
| 18 | `notifications.py` | 303 | 纯stdlib+SQLite | 站内消息通知系统(独立SQLite存储) | **低**: 调整通知类型定义 |

### Tier B — 业务逻辑可复用（需重构的业务能力层）

| # | 模块 | 行数 | 功能 | 复用方式 |
|---|------|------|------|---------|
| 19 | `search_index.py` | 1237 | 三引擎搜索(memory/fts5/auto) + jieba分词 + 向量重排序 + 搜索建议 | **重构复用**: 提取搜索核心引擎为独立包，产品按需组合 |
| 20 | `vector_search.py` | 1072 | M3E本地模型 + OpenAI/DeepSeek API + 向量索引+重排序 | **重构复用**: 向量搜索是通用AI基础设施 |
| 21 | `business_card_ai.py` | 1094 | OCR + NLP字段提取 + 数字名片生成 + 供需匹配触发 | **理念复用**: 扫描→结构化提取→匹配的管线模式 |
| 22 | `posthog_middleware.py` | 131 | PostHog SDK | 行为分析自动采集(page_view/API耗时/注册事件) | **低**: 换PostHog API Key即可 |
| 23 | `posthog_config.py` | — | PostHog SDK | PostHog客户端配置+事件辅助函数 | **低**: 换API Key |
| 24 | `sync_bridge.py` | 67 | Flask+yaml | 跨环境AI同步桥(飞书AI↔本地) | **直接复用**: 盖娅进化大脑的跨环境同步场景 |
| 25 | `i18n.py` | — | 纯Python | 国际化支持 | **低**: 盖娅的中韩出海场景需要 |

### Tier C — 业务特定（参考设计模式）

| # | 模块 | 功能 | 复用价值 |
|---|------|------|---------|
| 26 | `feature_pipeline.py` | 特征工程管线(category/keyword/price相似度) | **模式复用**: 盖娅的六维Feature评分可以借鉴该管线架构 |
| 27 | `matching_engine` (外部模块) | 供需匹配引擎 | **参考**: 盖娅的六维匹配逻辑可借鉴 |
| 28 | 36个router模块 | 路由处理(business_card/crm/search/events/contacts等) | **低**: 业务绑定太强，仅路由模式可参考 |
| 29 | `wechat_pay.py` | 微信支付 | **低**: 产品特定 |
| 30 | `enterprise_crawler.py` | 企业信息爬虫 | **中**: 赛博参谋的竞品数据采集可参考 |

---

## 2. 各产品缺口分析

### 2.1 赛博参谋 (Cyberscope)

**当前架构**: 独立CLI工具 + Web引擎(Flask)，单文件 `cyberscope_core_inject.py` (475行)

**已有能力**:
- CFC三元素决策模型(文化+市场+竞争)
- 套利空间识别
- 竞争对手对标
- 维度降维分析
- 解决方案生成器

**基础设施缺口** (链客宝可以提供什么):

| 缺口 | 链客宝对应模块 | 严重程度 | 说明 |
|------|---------------|---------|------|
| ❌ 无认证系统 | `auth.py` + `rbac.py` | **P0** | 当前无用户体系，无法多用户隔离 |
| ❌ 无API速率限制 | `rate_limiter.py` | **P1** | Web版上线后需要防止滥用 |
| ❌ 无结构化日志 | `logging_config.py` | **P0** | 当前用print，无法排障 |
| ❌ 无可观测性/指标 | `observability.py` | **P1** | 无请求量/错误率/延迟监控 |
| ❌ 无数据库统一层 | `database.py` | **P2** | 用硬编码dict当数据库，不可扩展 |
| ❌ 无错误追踪 | `sentry_config.py` | **P0** | 线上错误靠手动排查 |
| ❌ 无Feature Flag | `feature_flags.py` | **P2** | 多引擎(A/B测试)无灰度能力 |
| ❌ 无重试机制 | `retry_engine.py` | **P1** | API调用失败无自动恢复 |
| ❌ 无搜索能力 | `search_index.py` | **P1** | 评估结果无法搜索/检索 |
| ❌ 无安全加固 | `security_hardening.py` | **P2** | 敏感字段明文存储 |

### 2.2 盖娅进化大脑 (Gaia Evolution Brain)

**当前架构**: 
- `gaia_awakening_engine.py` — 觉醒引擎(505行)
- `gaia_absorb_pipeline.py` — 认知吸收管道(623行)
- `gaia_monitor.py` — 监控面板(312行, Flask Blueprint)
- `discussion_engine.py` / `standalone_discussion.py` — 讨论引擎(417+235行, Flask)
- `gaia_kanban.py` — 看板管理

**已有能力**:
- 员工觉醒引擎(166人灵魂注入)
- 六维认知吸收管道(审美/体系/创造力/基本功/数据/场景)
- Feature库质量评分系统(98个Feature)
- 讨论引擎/公民管理/目标追踪
- 军团健康度仪表盘

**基础设施缺口**:

| 缺口 | 链客宝对应模块 | 严重程度 | 说明 |
|------|---------------|---------|------|
| ❌ 无统一认证/RBAC | `auth.py` + `rbac.py` | **P1** | 多员工系统无权限分层 |
| ❌ 无结构化日志 | `logging_config.py` | **P0** | 觉醒/吸收引擎无操作日志可查 |
| ❌ 无指标收集 | `observability.py` | **P1** | 觉醒效果/吸收进度无法量化追踪 |
| ❌ 无错误追踪/Sentry | `sentry_config.py` | **P0** | 觉醒引擎异常不可见 |
| ❌ 无重试+死信队列 | `retry_engine.py` | **P1** | 吸收管道LLM调用失败无重试 |
| ❌ 无Feature Flag | `feature_flags.py` | **P0** | 82个待打磨Feature需要灰度发布能力 |
| ❌ 无安全加密 | `security_hardening.py` | **P2** | 员工soul-injection.yaml含敏感描述 |
| ❌ 无慢查询监控 | `slow_query_warning.py` | **P2** | SQLite查询无性能基线 |
| ❌ 无乐观锁 | `optimistic_lock.py` | **P2** | 多员工同时修改Feature造成冲突 |
| ❌ 无数据库统一层 | `database.py` | **P1** | 当前分散使用SQLite + JSON文件，难以扩展 |
| ❌ 无多租户 | `tenant_middleware.py` | **P2** | 多项目独立部署时无数据隔离 |
| ❌ WebSocket实时推送 | `websocket_manager.py` | **P2** | 觉醒进度无法实时推送到监控面板 |
| ❌ Sync Bridge | `sync_bridge.py` | **P1** | 盖娅跨环境同步(飞书AI↔本地)可直接复用 |
| ❌ 搜索能力 | `search_index.py` | **P2** | 1900+五池条目/166员工无法全文搜索 |

### 2.3 链客宝旧版 (/mnt/d/链客宝/)

仅3个Python文件(向量搜索+联系人丰富)，基本可忽略。旧版design文档(L2_KANBAN_DESIGN.md, L3_EXECUTION_DESIGN.md)中的设计理念可参考。

---

## 3. 复用优先级排序

### P0 — 立即复用（基础设施，所有产品都缺）

| 优先级 | Feature | 目标产品 | 理由 |
|--------|---------|---------|------|
| P0-1 | `logging_config.py` | 赛博参谋 + 盖娅 | 无日志=瞎子，线上问题无法排查 |
| P0-2 | `sentry_config.py` | 赛博参谋 + 盖娅 | 无错误追踪=裸奔 |
| P0-3 | `feature_flags.py` | 盖娅 | 82个待打磨Feature需灰度上线 |
| P0-4 | `auth.py` + `rbac.py` | 赛博参谋 | Web版上线需要用户体系 |

### P1 — 短期复用（1-2周内）

| 优先级 | Feature | 目标产品 | 理由 |
|--------|---------|---------|------|
| P1-1 | `observability.py` | 赛博参谋 + 盖娅 | 需要请求量/觉醒进度等量化指标 |
| P1-2 | `rate_limiter.py` | 赛博参谋 | Web版防滥用 |
| P1-3 | `retry_engine.py` | 盖娅 | 吸收管道LLM调用失败恢复 |
| P1-4 | `retry_engine.py` | 赛博参谋 | 外部API(竞品数据)调用重试 |
| P1-5 | `database.py` | 赛博参谋 | 硬编码dict→数据库迁移 |
| P1-6 | `database.py` | 盖娅 | SQLite+JSON文件→统一数据库 |
| P1-7 | `sync_bridge.py` | 盖娅 | 跨环境同步(飞书AI↔本地)直接复用 |
| P1-8 | `search_index.py` | 赛博参谋 + 盖娅 | 搜索能力是AI产品标配 |

### P2 — 中期复用（1个月内）

| 优先级 | Feature | 目标产品 | 理由 |
|--------|---------|---------|------|
| P2-1 | `security_hardening.py` | 盖娅 | 员工敏感信息加密 |
| P2-2 | `websocket_manager.py` | 盖娅 | 觉醒进度实时推送 |
| P2-3 | `tenant_middleware.py` | 盖娅 | 多项目数据隔离 |
| P2-4 | `optimistic_lock.py` | 盖娅 | 多员工协作防冲突 |
| P2-5 | `slow_query_warning.py` | 盖娅 | SQLite性能基线 |
| P2-6 | `notifications.py` | 赛博参谋 | 评估完成通知 |
| P2-7 | `circuit_breaker.py` | 赛博参谋 | LLM API调用保护 |
| P2-8 | `i18n.py` | 盖娅 | 中韩出海场景 |

---

## 4. 各 Feature 适配方案

### 4.1 logging_config.py — 赛博参谋适配

```python
# 改动点:
# 1. 复制 app/logging_config.py 到赛博参谋项目
# 2. 修改 APP_NAME = "cyberscope"
# 3. 在 main.py 中 setup_logging()
# 工作量: 15分钟
```

### 4.2 sentry_config.py — 盖娅适配

```python
# 改动点:
# 1. 复制 app/sentry_config.py
# 2. 设置环境变量 SENTRY_DSN
# 3. 在 Flask app 启动时 setup_sentry()
# 工作量: 10分钟
```

### 4.3 feature_flags.py — 盖娅适配

```python
# 改动点:
# 1. 复制 app/feature_flags.py
# 2. 替换 BUILTIN_FLAGS 为盖娅的 Feature 定义
#    (98个Feature, 按六维分类)
# 3. 与盖娅现有 Feature 质量评分系统对接
#    - flags_config.json 作为 Feature 灰度配置
#    - 质量评分作为 rollout_percentage 决策依据
# 工作量: 2小时 (主要花在Feature定义映射)
```

### 4.4 auth.py + rbac.py — 赛博参谋适配

```python
# 改动点:
# 1. 复制 auth.py + rbac.py
# 2. 替换 SECRET_KEY
# 3. 简化 User 模型(赛博参谋只需 email/password/name)
# 4. 调整 PERMISSION_REGISTRY:
#    - "assessment.read": ["admin", "member", "viewer"]
#    - "assessment.write": ["admin", "member"]
#    - "report.export": ["admin", "member"]
# 5. 将赛博参谋的 Flask Blueprint 改为 FastAPI router
# 工作量: 4小时
```

### 4.5 observability.py — 通用适配

```python
# 改动点:
# 1. 复制 app/observability.py (纯stdlib, 零依赖)
# 2. 在中间件中调用 metrics.record_request()
# 3. 添加 GET /metrics 端点
# 工作量: 20分钟
```

### 4.6 database.py — 赛博参谋适配

```python
# 改动点:
# 1. 复制 app/database.py
# 2. 改 DB_NAME = "cyberscope.db"
# 3. 保留 SQLite/MySQL/PG 三引擎自适应
# 4. 赛博参谋无需多租户(初期), 设置 is_multi_tenant()→False
# 工作量: 30分钟
```

### 4.7 retry_engine.py — 盖娅吸收管道适配

```python
# 改动点:
# 1. 复制 app/retry_engine.py (纯stdlib+SQLite)
# 2. 在 gaia_absorb_pipeline.py 中集成:
#    - LLM API调用失败→入队重试
#    - 超限→死信队列(人工review)
# 3. 增加 LLM 调用特有的退避策略
#    - 首次重试: 10秒
#    - 二次: 60秒
#    - 三次+: 5分钟(限流避免)
# 工作量: 2小时
```

### 4.8 sync_bridge.py — 盖娅跨环境同步适配

```python
# 这个可以直接复制使用:
# 1. 复制 app/sync_bridge.py
# 2. 修改 HERMES 路径指向盖娅的同步目录
# 3. 启动即可
# 工作量: 10分钟
```

---

## 5. 产品间 Feature 互通矩阵

### 链客宝 → 赛博参谋 (可提供: 13项)

```
auth.py          → 用户认证体系
rbac.py          → 权限控制
rate_limiter.py  → API限流
logging_config   → 结构化日志
observability.py → 指标监控
sentry_config.py → 错误追踪
retry_engine.py  → 重试机制
circuit_breaker  → 熔断保护
search_index.py  → 搜索结果检索
database.py      → 统一数据库
security_hardening → 敏感数据加密
feature_flags.py → 灰度发布
notifications.py → 评估完成通知
```

### 链客宝 → 盖娅进化大脑 (可提供: 14项)

```
auth.py          → 员工认证
rbac.py          → 部门/角色权限
logging_config   → 觉醒日志
observability.py → 觉醒指标
sentry_config.py → 错误追踪
retry_engine.py  → 吸收管道重试
database.py      → 统一数据库
feature_flags.py → Feature灰度上线
websocket_manager → 觉醒实时推送
sync_bridge.py   → 跨环境同步(直接复制)
security_hardening → 员工信息加密
optimistic_lock  → 多员工协作防冲突
slow_query_warning → SQLite性能基线
i18n.py          → 国际化(中韩)
```

### 盖娅 → 链客宝 (可参考: 3项)

```
六维Feature库体系  → 链客宝Feature管理体系化参考
Feature质量评分    → 链客宝功能模块质量评估
吸收管道模式      → 链客宝数据丰富管线的成熟度模型
```

### 赛博参谋 → 链客宝 (可参考: 1项)

```
CFC多维评估模型 → 链客宝供需匹配的多维度评分参考
```

---

## 6. 推荐的第一步行动

### 行动1: 创建跨产品共享基础设施包 (本周)

```bash
# 创建公共 Python 包
mkdir -p /mnt/d/chainke-full/packages/hermes-infra/hermes_infra/

# 首批抽取的模块 (P0全部 + P1核心):
cp backend/app/logging_config.py     packages/hermes-infra/hermes_infra/
cp backend/app/observability.py      packages/hermes-infra/hermes_infra/
cp backend/app/sentry_config.py      packages/hermes-infra/hermes_infra/
cp backend/app/retry_engine.py       packages/hermes-infra/hermes_infra/
cp backend/app/slow_query_warning.py packages/hermes-infra/hermes_infra/
cp backend/app/optimistic_lock.py    packages/hermes-infra/hermes_infra/

# 创建 setup.py 或 pyproject.toml，允许 pip install hermes-infra
```

这个包的所有模块都是"零外部依赖"或"可选依赖"设计，安装即用。

### 行动2: 赛博参谋 Web 版加固 (本周)

1. 集成 `logging_config.py` + `sentry_config.py` → 解决线上可观测性
2. 集成 `auth.py` + `rbac.py` → 用户体系上线
3. 集成 `rate_limiter.py` → API防滥用
4. 集成 `database.py` → 持久化替代dict

### 行动3: 盖娅 Feature 灰度体系 (下周)

1. 集成 `feature_flags.py` → 替换现有的硬编码Feature启停
2. 建立 Feature 质量评分 ↔ rollout_percentage 映射规则
   - 评分 ≥ 8.0: prod 100% 灰度
   - 评分 5.0-7.9: staging 50% + prod 10%
   - 评分 < 5.0: dev only
3. 集成 `sync_bridge.py` → 跨环境同步觉醒进度

### 行动4: 知识库架构收敛 (长期)

将链客宝作为"基础设施模范项目"，其他产品按以下层次逐步对齐:

```
层1 - Kernel (共享基础设施)
  ├── logging_config / observability / sentry_config
  ├── auth / rbac / rate_limiter / circuit_breaker
  ├── database / retry_engine / optimistic_lock
  └── feature_flags / security_hardening

层2 - Feature (可独立部署)
  ├── search_engine (search_index + vector_search)
  ├── web_socket (websocket_manager + notifications)
  ├── sync_bridge (跨环境同步)
  └── i18n (国际化)

层3 - DataPack (产品特定)
  └── 各产品的业务模型、路由、业务逻辑
```

---

## 附录: 扫描摘要

### 扫描文件统计

| 来源 | Python文件数 | 核心行数 | 模块数 |
|------|------------|---------|--------|
| 链客宝 backend/app/ | 93 | ~35,000+ | 30+ 基础设施级模块 |
| 链客宝旧版 /mnt/d/链客宝/ | 3 | ~1,000 | 仅向量搜索+数据丰富 |
| 赛博参谋 | 15 | ~3,000 | CFC引擎+CLI+数据 |
| 盖娅进化大脑 | 8 | ~3,500 | 觉醒+吸收+监控+讨论 |
| 总计 | 119 | ~42,500 | — |

### 关键发现

1. **链客宝是基础设施最完善的产品** — 30+个基础设施级模块覆盖了认证/权限/限流/熔断/日志/追踪/加密/灰度/重试/搜索/通知/WebSocket等全部维度
2. **赛博参谋核心资产在业务逻辑** — CFC三元素决策模型是独特价值，但基础设施几乎为零
3. **盖娅的Feature体系最先进** — 六维+质量评分+灰度策略的组合是产品迭代的核武器
4. **三个产品互补性极强** — 链客宝提供基础设施，赛博参谋提供出海分析，盖娅提供Feature进化飞轮
