# 链客宝AI 架构文档 (ARCHITECTURE.md)

> **版本**: 1.0.0 | **更新日期**: 2026-05-31
> **项目根目录**: `D:\链客宝AI\`
> **生产域名**: liankebao.top | www.liankebao.top | www.go-aiport.com

---

## 目录

- [1. 项目整体架构](#1-项目整体架构)
- [2. 后端架构](#2-后端架构)
- [3. 前端架构](#3-前端架构)
- [4. 小程序双轨](#4-小程序双轨)
- [5. 部署架构](#5-部署架构)
- [6. 数据流](#6-数据流)
- [7. 安全体系](#7-安全体系)
- [8. 当前开发规范摘要](#8-当前开发规范摘要)

---

## 1. 项目整体架构

链客宝AI采用 **前后端分离 + 多端适配** 的架构模式，一套后端服务支撑 Web 端、微信小程序原生版、微信小程序 Taro 版三个前端入口。

```
┌──────────────────────────────────────────────────────────────┐
│                       用户入口层                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  Web SPA │  │ 微信原生小程序 │  │ Taro 跨端小程序      │   │
│  │ (React)  │  │ (原生WXML)    │  │ (React→小程序)       │   │
│  └────┬─────┘  └──────┬───────┘  └──────────┬───────────┘   │
│       │               │                      │               │
├───────┼───────────────┼──────────────────────┼───────────────┤
│       │               │  HTTPS + WSS         │               │
│  ┌────┴───────────────┴──────────────────────┴────┐          │
│  │              Nginx 反向代理                      │          │
│  │   / → 前端静态文件 | /lkapi → FastAPI后端       │          │
│  │   /ws → WebSocket 代理 | 静态资源缓存           │          │
│  │   SSL终止 | Gzip压缩 | 安全头注入 | 限流        │          │
│  └────────────────────┬───────────────────────────┘          │
│                       │                                      │
│  ┌────────────────────┴───────────────────────────┐          │
│  │           FastAPI 后端 (Uvicorn)                │          │
│  │   24+ 路由模块 | 安全加固 | OpenTelemetry       │          │
│  │   Rate Limiter | Circuit Breaker | RBAC        │          │
│  └────────────────────┬───────────────────────────┘          │
│                       │                                      │
│  ┌────────────────────┴───────────────────────────┐          │
│  │          MySQL 8.0 / SQLite 数据库              │          │
│  │       SQLite(开发) / PostgreSQL(多租户生产)      │          │
│  └────────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
```

### 1.1 技术栈总览

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端框架 | React | 19.0.0 |
| 构建工具 | Vite | 6.2.0+ |
| 样式 | Tailwind CSS | 4.1.14 |
| 路由 | React Router (react-router-dom) | 7.14.2 |
| 动画 | Motion (Framer Motion) | 12.23.24 |
| 后端框架 | FastAPI (Python) | ≥3.10 |
| ORM | SQLAlchemy | — |
| 数据库 | MySQL 8.0 / SQLite / PostgreSQL | — |
| 反向代理 | Nginx | — |
| 容器化 | Docker / Docker Compose | — |
| 编排 | Kubernetes (K8s) | — |
| 可观测性 | Grafana + Jaeger + OpenTelemetry | — |
| 小程序原生 | 微信原生小程序 | — |
| 小程序Taro | Taro (React→小程序) | — |

### 1.2 端口分配

| 端口 | 服务 | 说明 |
|------|------|------|
| 3000 | Vite 开发服务器 | 前端热更新开发 |
| 7800 | FastAPI 后端(开发) | REST API 服务 |
| 8000 | FastAPI 后端(生产) | REST API 服务 |
| 8001 | FastAPI 后端(Docker) | 容器内 API 服务 |
| 3306 | MySQL | 数据库 |
| 80/443 | Nginx | 生产环境反向代理 |
| 18001 | 蓝部署后端 | Blue 实例 |
| 18002 | 绿部署后端 | Green 实例 |

---

## 2. 后端架构

### 2.1 目录结构

```
backend/
├── app/                          # 主应用包
│   ├── main.py                   # FastAPI 入口(中间件/路由注册/启动事件)
│   ├── database.py               # 数据库连接(MySQL/SQLite自适应)
│   ├── models.py                 # SQLAlchemy ORM 模型(14+个)
│   ├── schemas.py                # Pydantic 请求/响应模型
│   ├── auth.py                   # JWT 认证逻辑
│   ├── rbac.py                   # 基于角色的访问控制
│   ├── security_hardening.py     # AES-256-GCM 加密/CSP/SQL注入检测
│   ├── security_middleware_injection.py  # 数据安全中间件
│   ├── telemetry.py              # OpenTelemetry 全链路追踪
│   ├── observability.py          # 指标收集/健康检查
│   ├── rate_limiter.py           # 滑动窗口速率限制
│   ├── circuit_breaker.py        # 熔断器
│   ├── feature_flags.py          # 灰度发布
│   ├── tenant_middleware.py      # 多租户中间件
│   ├── tenant.py                 # 多租户逻辑
│   ├── notifications.py          # 通知系统
│   ├── websocket_manager.py      # WebSocket 连接管理
│   ├── search_index.py           # 搜索索引
│   ├── vector_search.py          # 向量搜索(Embedding)
│   ├── business_card_ai.py       # AI名片扫描(OCR+LLM)
│   ├── retry_engine.py           # 重试引擎
│   ├── slow_query_warning.py     # 慢查询告警
│   ├── sentry_config.py          # Sentry 错误追踪
│   ├── posthog_middleware.py     # PostHog 行为分析
│   ├── logging_config.py         # 结构化日志配置
│   ├── bi_routes.py              # BI 看板路由
│   ├── admin_config.py           # 系统配置管理
│   │
│   ├── routers/                  # 路由模块(24+个)
│   │   ├── auth.py               # 认证 /api/auth
│   │   ├── products.py           # 产品 /api/products
│   │   ├── orders.py             # 订单 /api/orders
│   │   ├── search.py             # 搜索 /api/search
│   │   ├── payment.py            # 支付 /api/payment
│   │   ├── promoter.py           # 推广员 /api/promoter
│   │   ├── admin.py              # 管理后台 /api/admin
│   │   ├── contacts.py           # 联系人 /api/contacts
│   │   ├── crm.py                # CRM管道 /api/crm
│   │   ├── enterprise.py         # 企业库 /api/enterprise
│   │   ├── business_card.py      # AI数字名片 /api/card
│   │   ├── needs.py              # 供需匹配 /api/needs
│   │   ├── matching_engine.py    # AI供需匹配 /api/matching
│   │   ├── events.py             # 行为事件 /api/events
│   │   ├── insights.py           # 数据洞察 /api/insights
│   │   ├── mission_control.py    # 任务面板 /api/home
│   │   ├── onboarding.py         # 新用户引导
│   │   ├── recommend.py          # 推荐系统
│   │   ├── activities.py         # 活动时间线
│   │   ├── imports.py            # 导入引擎 /api/imports
│   │   ├── brochure_bridge.py    # 翻页图册 /api/brochure
│   │   └── __init__.py
│   │
│   ├── __pycache__/              # Python 缓存
│   └── __init__.py
│
├── recharge/                     # 充值模块
│   ├── routes.py                 # 充值路由 /api/recharge
│   └── callback.py               # 充值回调 /api/recharge/callback
│
├── invoice/                      # 发票模块 /api/invoice
├── reconciliation/               # 对账模块 /api/reconciliation
├── matching_engine.py            # AI匹配引擎核心
├── data_migration.py             # 数据迁移脚本
├── seed_needs.py                 # 需求种子数据
│
├── data_security/                # 数据安全层
│   ├── core/
│   │   ├── data_contract.py      # 数据契约定义
│   │   ├── sanitizer.py          # 数据清洗
│   │   ├── data_write_gateway.py # 数据写入网关
│   │   └── anomaly_scorer.py     # 异常评分
│   ├── gate3/
│   │   └── gate3_validator.py    # Gate3 校验器
│   ├── quarantine/
│   │   └── quarantine_manager.py # 隔离区管理
│   ├── wolf/
│   │   ├── wolf_data_attack.py   # 数据攻击模拟
│   │   └── attack_payloads.py    # 攻击载荷库
│   ├── db/
│   │   └── migration_roles_permissions.sql
│   ├── data_security_loader.py
│   ├── test_e2e_data_security.py
│   └── validate_contracts.py
│
├── alembic/                      # 数据库迁移
│   ├── versions/
│   │   ├── add_tenant_models.py  # 多租户迁移
│   │   └── ...
│   └── env.py
│
├── tests/                        # 测试
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_products.py
│   ├── test_orders.py
│   ├── test_payment.py
│   ├── test_business_card.py
│   ├── test_matching_engine.py
│   ├── test_tenant.py
│   ├── test_tenant_rbac.py
│   └── e2e/
│       └── test_workflow.py
│
├── requirements.txt
├── matching_engine.py
└── openapi_cache.json
```

### 2.2 完整路由模块清单 (24个)

后端在 `main.py` 中通过两轮注册实现版本化兼容：第一轮以 `/api/v1/` 前缀注册版本化路由，第二轮以 `/api/` 前缀注册向后兼容路由。

| # | 模块 | 路由前缀 | 功能 | 认证 |
|---|------|---------|------|------|
| 1 | auth | `/api/auth` | 登录/注册/微信登录/Token刷新/登出/用户引导 | 部分 |
| 2 | products | `/api/products` | 产品CRUD/分类/审核/搜索 | 部分 |
| 3 | orders | `/api/orders` | 订单创建/状态流转/支付回调/分润计算 | 部分 |
| 4 | search | `/api/search` | 全文搜索/向量搜索/重排序/分类/建议 | 部分 |
| 5 | payment | `/api/payment` | 微信支付/支付宝/退款/查询 | 部分 |
| 6 | promoter | `/api/promoter` | 推广收益/提现/推广码/分润 | 是 |
| 7 | admin | `/api/admin` | 数据看板/用户管理/产品审核/提现审核 | admin |
| 8 | contacts | `/api/contacts` | 联系人CRUD/标签/批量导入/播种 | 是 |
| 9 | crm | `/api/crm` | 商机Deal/管道概览/活动日志 | 是 |
| 10 | enterprise | `/api/enterprise` | 企业库搜索/详情/关系图谱/AI补全 | 是 |
| 11 | business_card | `/api/card` | AI名片扫描生成/分享/供需匹配 | 部分 |
| 12 | needs | `/api/needs` | 需求发布/需求大厅/状态管理 | 部分 |
| 13 | matching | `/api/matching` | AI供需匹配/缓存/指标 | 部分 |
| 14 | events | `/api/events` | 用户行为事件埋点/热门统计 | 部分 |
| 15 | insights | `/api/insights` | 个人数据看板 | 是 |
| 16 | mission_control | `/api/home` | 任务控制面板 | 是 |
| 17 | onboarding | `/api/onboarding` | 新用户引导流程 | 否 |
| 18 | recommend | `/api/recommend` | AI推荐系统 | 是 |
| 19 | activities | `/api/activities` | 联系人活动时间线 | 是 |
| 20 | imports | `/api/imports` | CSV/VCF文件导入/AI列名识别 | 是 |
| 21 | recharge | `/api/recharge` | 充值/余额/流水 | 是 |
| 22 | recharge_callback | `/api/recharge/callback` | 充值支付回调 | 否 |
| 23 | invoice | `/api/invoice` | 发票申请/审核/统计 | 部分 |
| 24 | reconciliation | `/api/reconciliation` | 日对账/报告/审核 | admin |
| 25 | admin_config | `/api/admin/config` | 系统配置管理/变更日志 | admin |
| 26 | bi | `/api/bi` | BI看板/营收趋势/用户增长/漏斗/留存 | admin |
| 27 | brochue | `/api/brochure` | 翻页图册(名片专辑) | 部分 |
| — | notifications | `/api/notifications` | 通知列表/已读/删除 | 是 |
| — | system | `/api/system` | 日志级别/LLM用量/成本 | 部分 |
| — | banners | `/banners` + `/api/banners` | 首页轮播图 | 否 |
| — | websocket | `/ws/{user_id}` | 实时通知推送 | Token鉴权 |

> **注**: notifications、system、banners、websocket 直接在 `main.py` 中定义，不在独立 router 文件中。

### 2.3 数据库模型

位置: `backend/app/models.py`

| 模型 | 表名 | 核心字段 | 说明 |
|------|------|---------|------|
| **User** | `users` | id, username, password_hash, wechat_openid, name, phone, company, position, role(buyer/promoter/supplier/admin), avatar, onboarding_pain_point, version(乐观锁), organization_id(多租户) | 多角色用户 |
| **Product** | `products` | id, name, description, price, earn_per_share, category, stock, images, status(pending/approved/rejected), specs, details, brand, sale_price, video_url, tags, files, is_featured, sort_order, version, owner_id | 产品/商品 |
| **Order** | `orders` | id, user_id, product_id, quantity, total_price, status(pending/paid/shipped/received/refunded), promoter_id, commission, payment_platform, transaction_id, prepay_id | 订单+支付 |
| **Contact** | `contacts` | id, owner_id, name, phone, wechat_id, company, position, email, notes, tags, source, import_batch_id | 联系人 |
| **Activity** | `activities` | id, contact_id, action_type(note/call/meeting/email/wechat/order/import), summary, detail | 活动时间线 |
| **ImportHistory** | `import_history` | id, user_id, filename, file_type, total_rows, imported_rows, field_mapping, strategy, status, batch_id | 导入记录 |
| **BusinessNeed** | `business_needs` | id, user_id, title, description, category, budget, region, contact_name, status(open/closed) | 供需需求 |
| **BusinessCard** | `business_cards` | id, user_id, fields(JSON), share_token, view_count, cover_image, album_meta | AI数字名片 |
| **UserEvent** | `user_events` | id, user_id, event_type, target_type, target_id, search_keyword, session_id, page_url | 行为埋点 |
| **Withdrawal** | `withdrawals` | id, user_id, amount, status(pending/approved/rejected), bank_info | 提现 |
| **Deal** | `deals` | id, title, value, stage, probability, notes, owner_id, expected_close_date | CRM商机 |
| **DealActivity** | `deal_activities` | id, deal_id, user_id, action_type, summary, detail | 商机活动 |
| **Enterprise** | `enterprises` | id, name, credit_code, legal_person, industry, region, tags, website, confidence | 企业知识库 |
| **EnterpriseRelation** | `enterprise_relations` | id, source_id, target_id, relation_type(invest/compete/supply/subsidiary/partner/customer), confidence | 企业关系图谱 |

> 所有模型均包含 `created_at`、`deleted_at`、`is_deleted`（软删除）字段，以及可选的 `organization_id`（多租户外键）。

### 2.4 安全加固模块

位置: `backend/app/security_hardening.py`

```python
# 核心功能：
# 1. AES-256-GCM 加密：通过 @encrypted 装饰器自动加解密敏感字段
# 2. 密钥轮换：KEY_ROTATION_DAYS 环境变量控制(默认90天)
# 3. SQL注入检测：detect_raw_sql() 扫描 f-string / %-format SQL 拼接
# 4. CSP Headers：增强版安全响应头
# 5. SecurityHeadersMiddleware：ASGI中间件注入安全头
```

详见 [第7章 安全体系](#7-安全体系)。

### 2.5 支付模块

支付模块分布在多个文件中：

| 文件 | 功能 |
|------|------|
| `app/routers/payment.py` | 微信支付统一下单/回调/查询/退款，支付宝统一下单，支付配置 |
| `recharge/routes.py` | 充值预创建/查询/列表/余额/管理员调账 |
| `recharge/callback.py` | 充值回调(微信/模拟) |

支持的支付方式:
- **微信支付 JSAPI**（公众号/小程序内支付）
- **支付宝统一下单**
- **模拟支付**（开发/测试环境）

支付流程:
```
用户→创建订单→获取预支付ID→前端调起支付→
支付完成→异步回调→更新订单状态→分润计算→通知用户
```

---

## 3. 前端架构

### 3.1 目录结构

```
src/
├── api/                          # API 客户端层
│   ├── client.ts                 # Axios/fetch 封装, 拦截器
│   ├── generated.ts              # 自动生成的 API 类型
│   └── payment.ts                # 支付相关 API
│
├── components/                   # 共享组件
│   ├── ui/                       # 基础 UI 组件
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Modal.tsx
│   │   ├── Badge.tsx
│   │   ├── Table.tsx
│   │   └── index.ts
│   ├── Carousel.jsx              # 轮播图
│   ├── OnboardingPainSelector.tsx
│   ├── ErrorBoundary.tsx
│   ├── PageTransition.tsx
│   └── reactBitsIndex.ts         # 动画组件导出
│
├── screens/                      # 页面级组件
│   ├── AuthScreens.tsx           # 登录/注册
│   ├── MainScreens.tsx           # 首页/产品池/产品详情
│   ├── ProductScreens.tsx        # 上架产品/我的产品
│   ├── OrderScreens.tsx          # 订单确认/我的订单/订单管理
│   ├── PromoterScreen.tsx        # 推广中心
│   ├── AdminScreens.tsx          # 管理后台
│   ├── PaymentBridge.tsx         # 支付桥接
│   ├── RechargeScreens.tsx       # 充值
│   ├── SupplyDemandScreens.tsx   # 供需匹配
│   ├── PostNeedScreen.tsx        # 发布需求
│   ├── SubordinateScreens.tsx    # 下级推广员
│   ├── NotificationsScreen.tsx   # 通知
│   ├── DataInsightScreens.tsx    # 数据洞察
│   ├── ActivityScreens.tsx       # 活动管理
│   ├── PartnerPolicy.tsx         # 合伙人政策
│   └── ...
│
├── pages/                        # 独立页面
│   ├── ProfilePage.tsx           # 个人中心
│   ├── BIPage.tsx                # BI数据看板
│   ├── BusinessCardPage.tsx      # AI数字名片
│   └── ContactsImportPage.tsx    # 联系人导入
│
├── i18n/                         # 国际化
│   ├── index.tsx
│   ├── zh.ts                     # 中文
│   └── en.ts                     # 英文
│
├── App.tsx                       # 根组件(路由配置)
├── main.tsx                      # 入口文件
├── entry-server.tsx              # SSR 服务端入口
├── types.ts                      # TypeScript 类型定义
├── index.css                     # 全局样式 + Tailwind
├── pwa.tsx                       # PWA 配置
└── vite-env.d.ts                 # Vite 环境类型
```

### 3.2 技术栈详情

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19.0.0 | UI 框架 |
| TypeScript | 5.8.2 | 类型安全 |
| Vite | 6.2.0+ | 构建/开发服务器 |
| Tailwind CSS | 4.1.14 | 原子化样式 |
| @tailwindcss/vite | 4.1.14 | Tailwind Vite 插件 |
| React Router (react-router-dom) | 7.14.2 | 路由 |
| Motion | 12.23.24 | 动画(Framer Motion 继任者) |
| lucide-react | 0.546.0 | 图标库 |
| clsx | 2.1.1 | 条件 className |
| tailwind-merge | 3.5.0 | Tailwind 类名合并 |
| @google/genai | 1.29.0 | Google AI SDK |
| Express | 4.21.2 | SSR 服务端 |
| compression | 1.8.1 | SSR 响应压缩 |

### 3.3 Vite 配置双模式

`vite.config.ts` 根据 `SSR_BUILD` 环境变量切换构建模式：

- **客户端构建** (`npm run build`): 输出到 `dist/` 目录，`base: '/app/'`
- **SSR 构建** (`npm run build:ssr`): 输出到 `dist-ssr/`，打包 `src/entry-server.tsx` 为服务端入口

### 3.4 SSR 支持

SSR 通过 Express 服务端渲染实现:

```bash
# 开发模式 SSR
npm run dev:ssr

# 生产模式 SSR
npm run build && npm run build:ssr
npm run start:ssr
```

SSR 启动脚本位于 `server/ssr.ts`，使用 Express 托管静态资源并通过 Vite SSR 运行时渲染 React 组件。

### 3.5 路由结构

使用 React Router v7 的 layout routes 模式，在 `App.tsx` 中定义多级路由:

```
/                   → 首页/登录注册
/products           → 产品池
/products/:id       → 产品详情
/products/add       → 上架产品
/my-products        → 我的产品
/orders             → 我的订单
/order-confirm      → 订单确认
/promote            → 推广中心
/admin              → 管理后台
/needs              → 供需匹配
/card               → AI名片
/profile            → 个人中心
/bi                 → BI看板
/contacts           → 联系人
/import             → 联系人导入
/notifications      → 通知
/recharge           → 充值
```

---

## 4. 小程序双轨

### 4.1 双轨策略

```
liankebao-miniapp/     ← 微信原生小程序 (WXML + JS)
liankebao-weapp/       ← Taro 跨端框架 (React → 小程序)
```

### 4.2 原生小程序 (liankebao-miniapp)

| 用途 | 说明 |
|------|------|
| 框架 | 微信原生小程序 (WXML + WXSS + JS) |
| 目录 | `liankebao-miniapp/` |
| 测试 | Jest + jsdom (配置在 `jest.config.js`) |
| 入口 | 使用微信开发者工具打开此目录 |
| API | 通过 `wx.request` 调用 `https://www.go-aiport.com/lkapi/*` |

### 4.3 Taro 跨端小程序 (liankebao-weapp)

| 用途 | 说明 |
|------|------|
| 框架 | Taro (React 语法编译到小程序) |
| 目录 | `liankebao-weapp/` |
| 优势 | 代码复用率高，React 开发体验 |
| 目标平台 | 微信小程序（可扩展至支付宝/百度等） |

### 4.4 双轨共存原则

```
1. API 共享: 两个小程序调用同一套后端 API
2. 功能对等: 核心业务功能保持一致
3. 原生优先: 小程序特有的微信能力(如 wx.login, 订阅消息)在原生版优先实现
4. Taro 后续: Taro 版用于多端扩展，逐步追平原生版功能
```

---

## 5. 部署架构

### 5.1 部署架构总览

```
                          ┌──────────────────────┐
                          │    DNS / CDN          │
                          │  liankebao.top        │
                          └──────────┬───────────┘
                                     │
                          ┌──────────┴───────────┐
                          │   Nginx (反向代理)     │
                          │   阿里云 ECS          │
                          │   47.100.160.250      │
                          │   SSL / Gzip / 限流   │
                          └──────────┬───────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
   ┌──────────┴──────────┐ ┌────────┴────────┐ ┌──────────┴──────────┐
   │  前端静态文件         │ │  FastAPI 后端    │ │  WebSocket          │
   │  /dist (React SPA)   │ │  Blue:18001     │ │  ws:///ws/{uid}     │
   │  → / → index.html    │ │  Green:18002    │ │  实时通知            │
   └─────────────────────┘ └────────┬────────┘ └─────────────────────┘
                                     │
                          ┌──────────┴───────────┐
                          │     MySQL 8.0         │
                          │   阿里云 RDS / 本地    │
                          └──────────────────────┘
```

### 5.2 Docker 部署

`deploy/docker-compose.yml` 定义生产环境容器化部署:

```yaml
# 核心服务:
#   backend:    FastAPI + Uvicorn (端口 8001)
#   frontend:   Nginx 托管静态文件 + 反向代理
# 网络:        chainke_net (172.20.0.0/16)
# 数据卷:      chainke_db_data, chainke_logs
```

构建命令:
```bash
docker compose build
docker compose up -d
docker compose logs -f
```

多阶段构建 (`Dockerfile`):
```
Stage 1: backend — Python 依赖安装 + Uvicorn 启动
Stage 2: frontend — Node 构建 + Nginx 静态文件服务
```

SSR 模式另有 `Dockerfile.ssr`。

### 5.3 蓝绿部署

`deploy/nginx-bluegreen.conf` + `deploy/blue-green-deploy.sh` 实现零宕机部署：

```
蓝绿部署策略:
  Blue:  /opt/liankebao-blue/   端口 18001
  Green: /opt/liankebao-green/  端口 18002

切换流程:
  1. 更新非活跃环境代码
  2. 运行 health check
  3. 通过脚本生成 /etc/nginx/conf.d/chainke-active-backend.conf
  4. 重新加载 Nginx (systemctl reload nginx)
  5. 确认流量切换成功
```

`deploy/canary/canary-deploy.sh` 支持金丝雀发布（逐步灰度流量）。

### 5.4 Kubernetes 部署

`deploy/k8s/` 目录包含完整的 K8s 清单文件:

| 文件 | 说明 |
|------|------|
| `namespace.yaml` | 命名空间隔离 |
| `configmap.yaml` | 配置映射 |
| `backend-deployment.yaml` | 后端 Deployment |
| `backend-service.yaml` | 后端 Service (ClusterIP) |
| `frontend-deployment.yaml` | 前端 Deployment |
| `frontend-service.yaml` | 前端 Service |
| `ingress.yaml` | Ingress 路由规则 |
| `hpa.yaml` | 水平自动扩缩容 (HPA) |
| `kustomization.yaml` | Kustomize 配置管理 |

### 5.5 可观测性

| 工具 | 用途 | 部署方式 |
|------|------|---------|
| **Grafana** | 监控大盘/告警 | `deploy/grafana/docker-compose.yml` |
| **Prometheus** | 指标收集 | `deploy/grafana/prometheus.yml` |
| **Jaeger** | 分布式追踪 | `deploy/jaeger/docker-compose.yml` |
| **Tempo** | 追踪后端 | `deploy/grafana/tempo-config.yaml` |
| **OpenTelemetry** | 全链路追踪 | `app/telemetry.py` (FastAPI 自动插桩) |
| **Sentry** | 错误追踪 | `app/sentry_config.py` |
| **PostHog** | 用户行为分析 | `app/posthog_middleware.py` |
| **Metabase** | 业务数据分析 | `deploy/metabase/questions.json` |

监控端点:
- `/metrics` — 应用指标 (Prometheus/JSON 双格式)
- `/health` — 深度健康检查(数据库/支付/系统)
- `/health/live` — 存活检查
- `/health/ready` — 就绪检查

### 5.6 运维自动化

| 脚本/工具 | 用途 |
|-----------|------|
| `deploy/auto_recover.py` | 自动恢复(故障自愈) |
| `deploy/alert_manager.py` | 告警管理 |
| `deploy/deploy_local.sh` | 本地一键部署 |
| `deploy/blue-green-deploy.sh` | 蓝绿部署切换 |
| `deploy/canary/canary-deploy.sh` | 金丝雀发布 |

### 5.7 容灾与 SLA

详见 `deploy/disaster_recovery.md` 和 `deploy/SLA.md`。

---

## 6. 数据流

### 6.1 用户请求完整链路

```
用户(浏览器/小程序)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 1. DNS 解析 → liankebao.top → 阿里云 ECS 47.100... │
└─────────────────────────────────────────────────────┘
    │ HTTPS (TLS 1.3)
    ▼
┌─────────────────────────────────────────────────────┐
│ 2. Nginx 反向代理 (端口 443)                          │
│    ├── SSL 终止 (Let's Encrypt 证书)                   │
│    ├── 安全头注入 (HSTS/CSP/X-Frame-Options)          │
│    ├── 速率限制 (limit_req_zone)                      │
│    ├── 请求大小限制 (client_max_body_size 50M)         │
│    └── 路径分发:                                      │
│        ├── / → 前端 SPA (dist/index.html)             │
│        ├── /app/* → React SPA 静态资源                │
│        ├── /lkapi/* → 反向代理到 FastAPI (8001)        │
│        ├── /ws/* → WebSocket 代理                     │
│        ├── /static/* → 静态文件                        │
│        └── /.well-known/ → Let's Encrypt 验证          │
└─────────────────────────────────────────────────────┘
    │
    ▼ (如果路径是 /lkapi/*)
┌─────────────────────────────────────────────────────┐
│ 3. FastAPI 中间件链                                   │
│    ├── 请求ID中间件 (X-Trace-ID)                      │
│    ├── 安全响应头中间件 (CSP/HSTS/XSS)                │
│    ├── 请求大小限制 (1MB POST body)                   │
│    ├── 可观测性中间件 (结构化日志+指标收集)             │
│    ├── RateLimitMiddleware (滑动窗口限流)              │
│    ├── CORS 中间件 (白名单)                           │
│    ├── PostHog 中间件 (行为分析)                       │
│    ├── 多租户中间件 (PostgreSQL模式)                   │
│    ├── Feature Flags 中间件 (灰度发布)                 │
│    ├── Circuit Breaker 熔断器                         │
│    └── 数据安全中间件 (可选)                           │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 4. 路由分发                                          │
│    ├── /api/v1/auth/* → 版本化路由                    │
│    ├── /api/auth/* → 兼容路由                        │
│    ├── /api/products/* → 产品模块                    │
│    ├── /api/orders/* → 订单模块                      │
│    └── ... (24+ 路由模块)                            │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 5. 业务逻辑层                                        │
│    ├── 认证鉴权 (JWT Bearer Token)                   │
│    ├── RBAC 权限检查 (buyer/promoter/supplier/admin)  │
│    ├── 数据校验 (Pydantic schema)                     │
│    ├── 业务规则 (分润计算/状态机/库存)                │
│    └── 数据安全 (AES-256-GCM 加解密)                  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 6. 数据访问层 (SQLAlchemy ORM)                        │
│    ├── 数据库路由 (MySQL/SQLite 自适应)                │
│    ├── 多租户隔离 (organization_id 过滤)               │
│    ├── 慢查询告警 (超时 500ms 日志)                    │
│    ├── 乐观锁 (version 字段)                          │
│    └── 软删除 (is_deleted + deleted_at)               │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 7. MySQL 8.0 / SQLite                                 │
│    ├── 连接池 (SQLAlchemy pool)                       │
│    ├── 索引优化 (用户名/微信openid/外键)              │
│    └── 迁移管理 (Alembic)                             │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 8. 响应返回                                          │
│    统一格式: { code: 200, message: "success",       │
│                 data: { ... } }                      │
└─────────────────────────────────────────────────────┘
```

### 6.2 支付回调数据流

```
微信支付服务器 → Nginx → FastAPI /api/payment/wxpay/callback
    → 验证签名 → 更新订单状态 → 计算分润 → WebSocket 通知用户
```

### 6.3 WebSocket 实时通知流

```
客户端 → wss://host/ws/{user_id}
    → 发送 {"token": "xxx"} 鉴权
    → 服务端推送: {"event": "notification", "data": {...}}
    → 服务端推送: {"event": "order_update", "data": {...}}
```

### 6.4 OpenTelemetry 全链路追踪

```
用户请求 → Nginx (X-Trace-ID) → FastAPI (OpenTelemetry instrumentation)
    → SQLAlchemy (数据库调用追踪)
    → LLM 调用追踪
    → Jaeger/Tempo 收集 → Grafana 展示
```

---

## 7. 安全体系

### 7.1 七层纵深防御

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 7: 应用层安全                                          │
│   • CSP (Content Security Policy) 头                         │
│   • 速率限制 (Rate Limiter)                                  │
│   • 请求大小限制 (1MB POST)                                  │
│   • SQL注入检测 (detect_raw_sql)                             │
│   • LLM 输出注入检测                                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 6: 认证与授权                                           │
│   • JWT Token 认证 (Bearer)                                  │
│   • Refresh Token 轮换                                       │
│   • RBAC 角色控制 (buyer/promoter/supplier/admin)            │
│   • Feature Flags 灰度控制                                    │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: 数据加密                                             │
│   • AES-256-GCM 加密(phone/email/wechat_openid)              │
│   • 密钥轮换 (默认90天)                                       │
│   • 加密字段透明传输(@encrypted 装饰器)                       │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: 传输安全                                             │
│   • HTTPS (TLS 1.3, Let's Encrypt)                           │
│   • HSTS (HTTP Strict Transport Security)                    │
│   • WSS (WebSocket Secure)                                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Web 安全头                                           │
│   • X-Content-Type-Options: nosniff                          │
│   • X-Frame-Options: DENY                                    │
│   • X-XSS-Protection: 1; mode=block                          │
│   • Referrer-Policy: strict-origin-when-cross-origin          │
│   • Permissions-Policy (摄像头/麦克风/地理位置)               │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: 基础设施安全                                          │
│   • Nginx 安全加固配置 (deploy/nginx_security.conf)           │
│   • 安全响应头注入                                            │
│   • 请求速率限制 (limit_req_zone)                             │
│   • 隐藏 Nginx 版本号                                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: 可观测性与审计                                        │
│   • OpenTelemetry 全链路追踪                                  │
│   • 结构化日志 (请求日志/安全事件/异常)                        │
│   • Sentry 错误追踪                                           │
│   • 慢查询告警 (SQL > 500ms)                                  │
│   • 告警管理 (deploy/alert_manager.py)                        │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 AES-256-GCM 数据加密

位置: `backend/app/security_hardening.py`

```python
# 密钥管理
_ENCRYPTION_KEY: 从 ENCRYPTION_KEY 环境变量读取(Base64编码的32字节)
_KEY_ROTATION_DAYS = int(os.environ.get("KEY_ROTATION_DAYS", "90"))

# 加密范围
敏感字段: phone, email, wechat_openid (自动加解密)

# 使用方式
@encrypted  # Pydantic model 装饰器
class UserResponse(BaseModel):
    phone: str       # 自动加密写入, 自动解密读取
    email: str
```

### 7.3 CSP (Content Security Policy)

通过 `SecurityHeadersMiddleware` 注入增强版 CSP 头：

```http
Content-Security-Policy: default-src 'self';
    script-src 'self' 'unsafe-inline' https://res.wx.qq.com;
    style-src 'self' 'unsafe-inline';
    img-src 'self' data: https:;
    connect-src 'self' https://api.weixin.qq.com;
    frame-ancestors 'none';
```

### 7.4 SQL 注入检测

```python
# 自动扫描 f-string / %-format 拼接的 SQL
# 检测模式: f"SELECT {field}...", "WHERE id = %s" % value
# 触发时记录 WARNING 日志 + 告警
```

### 7.5 OpenTelemetry 链路追踪

```python
# 自动插桩
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

# 追踪范围
#   • HTTP 请求全链路
#   • 数据库查询 (SQLAlchemy)
#   • LLM API 调用
#   • 外部 HTTP 请求
```

---

## 8. 当前开发规范摘要

### 8.1 项目规范

| 规范 | 说明 |
|------|------|
| **版本控制** | Git (分支策略: main / develop / feature/*) |
| **Python版本** | ≥ 3.10 |
| **Node版本** | ≥ 18 |
| **数据库迁移** | Alembic (backend/alembic/) |
| **API版本化** | `/api/v1/*` (新) + `/api/*` (向后兼容) |
| **统一响应格式** | `{ "code": 200, "message": "success", "data": {...} }` |
| **错误格式** | `{ "code": 4xx/5xx, "message": "描述" }` |

### 8.2 编码规范

**后端 (Python/FastAPI):**
- 使用 SQLAlchemy ORM，避免裸 SQL
- 所有模型包含 `created_at`, `deleted_at`, `is_deleted` (软删除)
- 关键模型使用 `version` 字段实现乐观锁
- 敏感字段使用 `@encrypted` 装饰器自动加解密
- 路由统一在 `router_modules` 列表中注册
- 使用 Pydantic schema 做请求/响应校验
- 依赖注入 `Depends(get_current_user)` 获取当前用户

**前端 (React/TypeScript):**
- TypeScript 严格模式
- 组件粒度: screens/ (页面级) → components/ (共享组件)
- API 调用通过 `src/api/client.ts` 统一封装
- 样式使用 Tailwind CSS 原子类
- 路由在 `App.tsx` 中集中配置
- SSR 入口在 `entry-server.tsx`

### 8.3 命名规范

```
后端路由文件:     routers/{module_name}.py
后端路由前缀:     /api/{module_name}
数据库表名:       snake_case (复数)
模型类名:         PascalCase (单数)
API端点:         RESTful (GET/POST/PUT/DELETE)
Git分支:         feature/{description}, fix/{description}
```

### 8.4 测试规范

```
后端测试:    backend/tests/ (pytest)
前端测试:    src/__tests__/ (vitest)
E2E测试:     backend/tests/e2e/
小程序测试:   liankebao-miniapp/__tests__/ (Jest)
```

### 8.5 Commit 规范

```
feat:     新功能
fix:      修复
chore:    构建/工具
docs:     文档
refactor: 重构
test:     测试
security: 安全加固
```

### 8.6 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VITE_API_BASE` | API 基础路径 | `/lkapi` |
| `GEMINI_API_KEY` | Google Gemini API 密钥 | — |
| `APP_URL` | 应用部署 URL | — |
| `ENCRYPTION_KEY` | AES-256-GCM 密钥(Base64) | 自动生成 |
| `KEY_ROTATION_DAYS` | 密钥轮换周期 | 90 |
| `SECRET_KEY` | JWT 密钥 | — |
| `DATABASE_URL` | 数据库连接 | sqlite:///data/chainke.db |
| `SENTRY_DSN` | Sentry DSN | — |
| `USE_VECTOR_SEARCH` | 启用向量搜索 | 0 |
| `EMBEDDING_PROVIDER` | 嵌入模型供应商 | numpy |
| `PORT` | 服务端口 | 7800 |

### 8.7 关键依赖文件

```
前端:    package.json (npm)
后端:    backend/requirements.txt (pip)
Docker:  Dockerfile, Dockerfile.ssr, deploy/docker-compose.yml
K8s:     deploy/k8s/kustomization.yaml
```

---

> **参考文档**:
> - [README.md](./README.md) — 项目快速入门
> - [L5_API_CONTRACT.md](./L5_API_CONTRACT.md) — API 详细契约 (24+ 模块)
> - [PRICING.md](./PRICING.md) — 定价方案与商业模式
> - [deploy/SLA.md](./deploy/SLA.md) — SLA 服务等级协议
> - [deploy/disaster_recovery.md](./deploy/disaster_recovery.md) — 容灾方案
> - [deploy/README_DEPLOY.md](./deploy/README_DEPLOY.md) — 部署说明
