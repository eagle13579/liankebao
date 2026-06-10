# 链客宝AI项目资产分析报告

> 扫描时间: 2026-06-04 17:01 | 项目路径: D:\链客宝AI

---

## 一、项目总览

**定位**: 企业家供需匹配平台（AI数字名片 + 供需撮合 + 推广分润）
**域名**: liankebao.top | www.go-aiport.com
**技术栈**: FastAPI(Python) + React 19 + Vite + Tailwind CSS + SQLAlchemy + MySQL/SQLite/PostgreSQL

### 目录结构

```
D:\链客宝AI\
├── backend/                    # FastAPI后端 (主API服务)
│   ├── app/
│   │   ├── models.py           # ORM数据模型（所有表）
│   │   ├── main.py             # FastAPI入口（注册33+路由模块）
│   │   ├── schemas.py          # Pydantic请求/响应模型
│   │   ├── auth.py             # JWT认证逻辑
│   │   ├── database.py         # 数据库连接（SQLite/MySQL自适应）
│   │   ├── routers/            # 28个路由模块
│   │   │   ├── membership.py   # 会员体系路由
│   │   │   ├── payment.py      # 支付路由（IJPay封装）
│   │   │   ├── orders.py       # 订单路由
│   │   │   ├── auth.py         # 认证路由
│   │   │   ├── admin.py        # 管理后台
│   │   │   ├── promoter.py     # 推广员
│   │   │   ├── products.py     # 产品
│   │   │   ├── recommend.py    # AI推荐
│   │   │   ├── contacts.py     # 联系人
│   │   │   ├── needs.py        # 供需匹配
│   │   │   ├── crm.py          # CRM管道
│   │   │   ├── enterprise.py   # 企业库
│   │   │   ├── growth.py       # 增长引擎
│   │   │   ├── business_card.py # AI数字名片
│   │   │   ├── recharge/       # 充值模块
│   │   │   └── ... (14+更多)
│   │   ├── services/           # 业务服务层
│   │   └── middleware/         # 中间件
│   ├── payment/                # IJPay支付底层封装
│   │   ├── config.py           # 支付配置注册中心
│   │   ├── sign.py             # 签名门面（RSA/MD5/HMAC/AES-GCM）
│   │   ├── wxpay/              # 微信支付（V3+V2兼容）
│   │   └── alipay/             # 支付宝（框架）
│   ├── recharge/               # 充值模块（独立子模块）
│   ├── data_security/          # 数据安全层
│   └── alembic/                # 数据库迁移
├── src/                        # 前端React SPA
│   ├── screens/                # 16个页面组件
│   ├── pages/                  # 17个独立页面
│   ├── api/                    # API客户端
│   ├── components/             # UI组件库
│   └── i18n/                   # 国际化（中/英）
├── liankebao-miniapp/          # 微信原生小程序
├── liankebao-weapp/            # Taro跨端小程序
└── docs/                       # 文档
```

---

## 二、会员体系（核心可复用资产）

### 2.1 等级定义

**4个等级**, 定义在 `backend/app/routers/membership.py` 的 `MEMBERSHIP_TIERS`:

| 等级 | 年费 | 有效期 | 对接券/月 | 分润率 | 标签 |
|------|------|--------|----------|--------|------|
| **free** (免费会员) | ¥0 | 永久 | 3次 | 5% | - |
| **gold** (金卡会员) | ¥999 | 365天 | 20次 | 8% | 推荐 |
| **diamond** (钻石会员) | ¥4,999 | 365天 | 60次 | 12% | 高性价比 |
| **board** (私董会) | ¥19,999 | 365天 | 200次 | 15% | 尊享 |

### 2.2 各等级权益

**free**: 浏览产品/企业信息, 发布供需需求, 每月3次对接机会, 查看平台成交案例

**gold**: 所有free权益 + 无限发布需求 + 查看对方联系方式 + AI匹配优先推荐 + 每月5次定向对接 + 企业身份认证标识 + 首月不满意全额退款

**diamond**: 所有gold权益 + 线上闭门对接会(每季1次) + 专属撮合经理服务 + 企业深度认证+信用报告 + 交易安全保障金 + CRM对接工具+合作追踪 + 续费推荐返现15%

**board** (私董会): 所有diamond权益 + 线下闭门私董会(每季1次) + 一对一商业诊断(季度) + 专家导师库(TOP100企业家) + 优先投资对接 + 独家项目路演 + 同行业不超过2家 + 限额50席·创始人邀请制

### 2.3 会员API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/membership/tiers` | 获取所有会员层级配置 |
| GET | `/api/membership/status` | 获取当前用户会员状态 |
| POST | `/api/membership/upgrade` | 升级会员（创建支付订单） |
| GET | `/api/membership/credits` | 获取剩余对接券 |
| POST | `/api/membership/credits/use` | 消耗一张对接券 |

---

## 三、用户数据库 Schema

### 3.1 users 表 (`backend/app/models.py:23`)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | Integer PK auto | - | 主键 |
| username | String(50) UNIQUE | - | 用户名（邮箱/手机号） |
| password_hash | String(255) NOT NULL | - | bcrypt密码哈希 |
| wechat_openid | String(100) UNIQUE | - | 微信openid |
| name | String(100) NOT NULL | - | 用户姓名 |
| phone | String(20) | - | 手机号 |
| company | String(200) | - | 公司 |
| position | String(100) | - | 职位 |
| role | String(20) | "buyer" | buyer/promoter/supplier/admin |
| avatar | String(500) | - | 头像URL |
| onboarding_pain_point | String(50) | - | 痛点标签 |
| version | BigInteger | 1 | 乐观锁 |
| membership_tier | String(20) | "free" | free/gold/diamond/board |
| membership_expires_at | DateTime | - | 会员过期时间 |
| match_credits | Integer | 3 | 剩余对接券数 |
| password_reset_token | String(255) | - | 重置令牌 |
| password_reset_expires | DateTime | - | 令牌过期时间 |
| organization_id | Integer | - | 多租户ID |
| created_at | DateTime | utcnow | 创建时间 |
| deleted_at | DateTime | - | 软删除时间 |
| is_deleted | Boolean | false | 软删除标记 |

### 3.2 核心关联表

| 表名 | 文件 | 说明 |
|------|------|------|
| membership_orders | models.py:525 | 会员升级订单（user_id, tier, amount, status, payment_platform, transaction_id） |
| match_credit_logs | models.py:549 | 对接券变更日志（user_id, amount, balance_after, reason） |
| orders | models.py:125 | 商品订单（user_id, product_id, quantity, total_price, status, 支付相关字段） |
| products | models.py:82 | 产品（name, price, category, stock, status, 推广分润率） |
| contacts | models.py:169 | 联系人（owner_id, name, phone, wechat_id, company, position） |
| business_needs | models.py:265 | 供需需求（user_id, title, category, budget, region） |
| business_cards | models.py:297 | AI数字名片（user_id, fields（JSON）, share_token） |
| enterprises | models.py:414 | 企业知识图谱 |
| enterprise_relations | models.py:452 | 企业关系图谱 |
| user_balances | recharge/models.py:12 | 用户余额（含乐观锁） |
| recharge_orders | recharge/models.py:28 | 充值订单 |
| private_board_orders | models.py:480 | 私董会申请订单 |
| online_matching_events | models.py:570 | 线上对接会 |
| online_matching_registrations | models.py:599 | 对接会报名 |
| withdrawals | models.py:350 | 提现记录 |
| deals | models.py:376 | CRM商机 |
| user_events | models.py:326 | 用户行为埋点 |

---

## 四、支付/订单系统

### 4.1 支付架构

基于IJPay设计思想封装的Python版支付层 (`backend/payment/`):

```
payment/
├── __init__.py     # 导出WxPayApi, AliPayApi, WxPayCallback等
├── config.py       # 多平台支付配置注册中心（微信/支付宝）
├── sign.py         # RSA/MD5/HMAC-SHA256/AES-GCM签名
├── http_delegate.py # HTTP委托抽象层
├── wxpay/          # 微信支付（V3 + V2 兼容）
└── alipay/         # 支付宝（框架层）
```

### 4.2 关键特性

- **双轨模式**: 真实支付(REAL) / Mock模式(MOCK)，开发环境无需真实密钥
- **V3 + V2 兼容**: 同时支持微信V3回调验签和V2 XML格式
- **重试队列**: 回调未匹配订单时自动加入重试队列（RetryEngine）
- **乐观锁**: 所有订单表有version字段防并发修改

### 4.3 订单状态机

```
pending → paid → shipped → received → refunded
    ↘ refunded
```

### 4.4 支付API端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/payment/wxpay/unified-order` | 微信统一下单(JSAPI) |
| POST | `/api/payment/wxpay/callback` | 微信支付回调 |
| GET | `/api/payment/wxpay/query/{order_no}` | 查询订单状态 |
| POST | `/api/payment/wxpay/refund` | 退款 |
| POST | `/api/payment/alipay/unified-order` | 支付宝统一下单 |
| GET | `/api/payment/config` | 获取支付配置 |

---

## 五、完整API路由结构

### 5.1 认证模块 `/api/auth`
- POST login | POST register | GET me | POST refresh | POST logout
- POST wechat-login | POST forgot-password | POST reset-password

### 5.2 产品模块 `/api/products`
- GET list | GET detail | POST create | PUT update | DELETE

### 5.3 订单模块 `/api/orders`
- GET list | GET detail | POST create | PUT status | POST pay-notify

### 5.4 支付模块 `/api/payment`
- POST wxpay/unified-order | POST wxpay/callback | GET wxpay/query
- POST wxpay/refund | POST alipay/unified-order | GET config

### 5.5 会员模块 `/api/membership`
- GET tiers | GET status | POST upgrade | GET credits | POST credits/use

### 5.6 充值模块 `/api/recharge`
- POST create | GET plans | POST callback

### 5.7 推广员 `/api/promoter`
- GET earnings | POST withdraw | GET qrcode

### 5.8 管理后台 `/api/admin`
- GET dashboard | GET/PUT users | GET/PUT products | GET withdrawals | PUT withdraw

### 5.9 联系人 `/api/contacts`
- CRUD + 搜索 + 标签筛选

### 5.10 供需匹配 `/api/needs`
- CRUD + 分类筛选

### 5.11 CRM `/api/crm`
- CRUD管道 | GET stages | PUT stage

### 5.12 AI匹配 `/api/matching`
- POST match | GET status | GET history

### 5.13 推荐 `/api/recommend`
- GET products | GET needs | GET ai-reason

### 5.14 企业库 `/api/enterprise`
- CRUD + 搜索 + 知识图谱关系

### 5.15 AI数字名片 `/api/card`
- POST create | GET share | POST update

### 5.16 更多模块
- search, imports, invoice, reconciliation, BI, insights
- events(埋点), notifications, brochure(翻页图册), growth(增长引擎)
- organization(组织), private-board(私董会), enrichment(数据丰富)

> 所有路由同时注册在 `/api/v1/...` 版本化路径下

---

## 六、前端页面资产

### 6.1 SPA页面 (`src/screens/`)

| 文件 | 功能 |
|------|------|
| AuthScreens.tsx | 登录/注册/密码重置 |
| MainScreens.tsx | 首页/产品池/搜索 |
| MembershipScreens.tsx | 会员中心/升级/权益展示 (1050行完整实现) |
| OrderScreens.tsx | 订单列表/详情 |
| ProductScreens.tsx | 产品管理/上架 |
| RechargeScreens.tsx | 余额充值 |
| PaymentBridge.tsx | 支付中转页 |
| AdminScreens.tsx | 管理后台看板 |
| PromoterScreen.tsx | 推广员中心/收益/提现 |
| SupplyDemandScreens.tsx | 供需发布/匹配 |
| ActivityScreens.tsx | 活动时间线 |
| NotificationsScreen.tsx | 通知列表 |
| SubordinateScreens.tsx | 下属管理 |
| PartnerPolicy.tsx | 合伙人政策 |
| DataInsightScreens.tsx | 数据洞察 |
| TutorialScreens.tsx | 新手指引 |

### 6.2 SPA独立页面 (`src/pages/`)

| 文件 | 功能 |
|------|------|
| DashboardPage.tsx | 数据看板 |
| BIPage.tsx | BI分析 |
| BusinessCardPage.tsx | AI数字名片管理 |
| ContactsPage.tsx | 联系人管理 |
| ContactDetailPage.tsx | 联系人详情 |
| ContactMergePage.tsx | 联系人合并 |
| ContactsImportPage.tsx | 通讯录导入 |
| PipelinePage.tsx | CRM管道视图 |
| PrivateBoardPage.tsx | 私董会 |
| ProfilePage.tsx | 个人资料 |
| RecommendPage.tsx | 推荐页面 |
| MatchingEventsPage.tsx | 对接会活动 |
| MatchingMetricsPage.tsx | 匹配指标 |
| DataEnrichPage.tsx | 数据丰富 |
| GrowthPage.tsx | 增长引擎 |

---

## 七、可复用资产清单

### 7.1 可直接复用的模块

1. **会员体系** (membership.py + MembershipScreens.tsx)
   - 4级会员定义、价格、权益配置
   - 会员状态查询、升级、对接券管理
   - 前端会员中心UI完整实现

2. **支付底层** (payment/ 模块)
   - IJPay设计思想的Python封装
   - 微信V3/V2双兼容 + 支付宝框架
   - 签名库(RSA/MD5/HMAC/AES-GCM)
   - 配置注册中心

3. **订单系统** (orders.py + OrderScreens.tsx)
   - 完整订单状态机
   - 分润计算
   - 库存管理

4. **推广分润体系** (promoter.py + PromoterScreen.tsx)
   - 推广员收益计算
   - 提现申请/审核
   - 小程序码生成

5. **用户认证系统** (auth.py + auth.py)
   - JWT + Refresh Token轮换
   - 微信登录(code→openid)
   - 密码重置
   - 登录频率限制

6. **充值模块** (recharge/ 独立子模块)
   - 用户余额模型(含乐观锁)
   - 充值订单
   - 充值回调处理

7. **CRM系统** (crm.py + crm_pipeline.py)
   - 管道/CDP模型
   - 商机(Deal)管理
   - 活动时间线

8. **企业知识图谱** (enterprise.py)
   - 企业库模型
   - 企业关系图谱(投资/竞争/供应链)
   - AI爬虫数据源

9. **数据安全层** (data_security/)
   - 数据合约(Data Contract)
   - 输出清洗(Sanitizer)
   - 攻击检测(Wolf)
   - 隔离区(Quarantine)
   - Gate3验证器

### 7.2 基础设施资产

- **OpenTelemetry全链路追踪** (observability.py + telemetry.py)
- **Rate Limiter** (滑动窗口, 零依赖)
- **Circuit Breaker熔断器**
- **Feature Flags灰度发布**
- **PostHog行为分析埋点**
- **多租户中间件** (PostgreSQL模式)
- **安全加固** (AES-256-GCM + CSP + SQL注入检测)
- **慢查询警告** (slow_query_warning.py)
- **重试引擎** (retry_engine.py)
- **乐观锁框架** (optimistic_lock.py)

### 7.3 前端基础设施

- **API客户端** (client.ts): 统一Token管理 + 两种格式兼容
- **国际化** (i18n/): 中英文双语
- **UI组件库** (components/ui/): Badge, Button, Card, Modal, Table
- **动画组件**: BorderGlow, Carousel, Dock, SplashCursor, SpotlightCard
- **页面过渡动画** (PageTransition.tsx)

---

## 八、关键发现与注意

1. **models.py中存在重复字段定义**: membership_tier, membership_expires_at, match_credits 在User类中被定义了两次（line 46-48 和 line 57-60），后者覆盖前者。board等级仅在第二次定义中出现。
2. **数据库双模**: SQLite(开发) / MySQL(生产) / PostgreSQL(多租户生产) 三模自适应
3. **支付Mock模式**: 无微信密钥时自动降级mock，不影响开发测试
4. **前端Vite SPA + 微信小程序双轨**: 一套后端支撑三个前端入口
5. **所有模型都有软删除**: is_deleted + deleted_at 字段
6. **所有模型都有乐观锁**: version字段
