# 链客宝AI API 契约文档（L5 基础设施）

> **版本**: 1.0.0
> **基地址**: `https://www.go-aiport.com` | `http://localhost:7800`
> **OpenAPI**: `/docs` (Swagger) | `/redoc` (ReDoc)
> **统一响应格式**:
> ```json
> { "code": 200, "message": "success", "data": { ... } }
> ```
> **认证方式**: `Authorization: Bearer <token>` (JWT)
> **速率限制**: 关键路径差异化限流，超限返回 429

---

## 目录

- [1. 认证模块 `/api/auth`](#1-认证模块-apiauth)
- [2. 产品模块 `/api/products`](#2-产品模块-apiproducts)
- [3. 订单模块 `/api/orders`](#3-订单模块-apiorders)
- [4. 搜索模块 `/api/search`](#4-搜索模块-apisearch)
- [5. 支付模块 `/api/payment`](#5-支付模块-apipayment)
- [6. 充值模块 `/api/recharge`](#6-充值模块-apirecharge)
- [7. 管理后台 `/api/admin`](#7-管理后台-apiadmin)
- [8. 联系人 `/api/contacts`](#8-联系人-apicontacts)
- [9. CRM管道 `/api/crm`](#9-crm管道-apicrm)
- [10. 企业库 `/api/enterprise`](#10-企业库-apienterprise)
- [11. AI数字名片 `/api/card`](#11-ai数字名片-apicard)
- [12. 供需匹配 `/api/needs`](#12-供需匹配-apineeds)
- [13. AI供需匹配 `/api/matching`](#13-ai供需匹配-apimatching)
- [14. 推广员 `/api/promoter`](#14-推广员-apipromoter)
- [15. 导入引擎 `/api/imports`](#15-导入引擎-apiimports)
- [16. 发票 `/api/invoice`](#16-发票-apiinvoice)
- [17. 对账 `/api/reconciliation`](#17-对账-apireconciliation)
- [18. BI看板 `/api/bi`](#18-bi看板-apibi)
- [19. 数据洞察 `/api/insights`](#19-数据洞察-apiinsights)
- [20. 首页 `/api/home`](#20-首页-apihome)
- [21. 通知 `/api/notifications`](#21-通知-apinotifications)
- [22. 系统管理 `/api/system`](#22-系统管理-apisystem)
- [23. 行为事件 `/api/events`](#23-行为事件-apievents)
- [24. 翻页图册 `/api/brochure`](#24-翻页图册-apibrochure)
- [25. 充值回调 `/api/recharge/callback`](#25-充值回调-apirechargecallback)
- [26. 系统配置 `/api/admin/config`](#26-系统配置-apiadminconfig)
- [27. 公共端点 (无前缀)](#27-公共端点-无前缀)
- [28. WebSocket](#28-websocket)

---

## 1. 认证模块 `/api/auth`

| 方法 | 路径 | 说明 | 认证 | 请求体 | 响应 |
|------|------|------|------|--------|------|
| POST | `/api/auth/login` | 用户登录（频率限制） | 否 | `{ username, password }` | `{ token, refresh_token, user }` |
| POST | `/api/auth/register` | 用户注册 | 否 | `{ username, password, name, phone?, company?, position?, role? }` | `{ token, refresh_token, user }` |
| GET | `/api/auth/me` | 获取当前用户信息 | 是 | — | `{ id, username, name, role, ... }` |
| POST | `/api/auth/refresh` | 刷新access token | 否 | `{ refresh_token }` | `{ token, refresh_token }` |
| POST | `/api/auth/logout` | 退出登录 | 是 | — | `{ code: 200 }` |
| POST | `/api/auth/wechat-login` | 微信登录（code→openid） | 否 | `{ code }` | `{ token, user }` |
| POST | `/api/auth/onboarding` | 新用户引导信息提交 | 否 | `{ company?, position?, invite_code? }` | `{ code: 200 }` |

> 注：所有认证路由同时注册为 `/api/v1/auth/...` 版本化路径。

---

## 2. 产品模块 `/api/products`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/products` | 产品列表（分页+筛选） | 否 | `?category=&status=&search=&page=&page_size=` | `{ items, total, page, page_size }` |
| GET | `/api/products/{id}` | 产品详情 | 否 | — | `{ id, name, price, ... }` |
| POST | `/api/products` | 创建产品 | 是 | `{ name, price, category, description?, images?, stock?, ... }` | `{ id, ... }` |
| PUT | `/api/products/{id}` | 更新产品（仅自己创建） | 是 | `{ name?, price?, ... }` | `{ code: 200 }` |
| DELETE | `/api/products/{id}` | 删除产品（或管理员） | 是 | — | `{ code: 200 }` |

---

## 3. 订单模块 `/api/orders`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/orders` | 订单列表（按角色过滤） | 是 | — | `[{ id, product, status, ... }]` |
| GET | `/api/orders/{id}` | 订单详情 | 是 | — | `{ id, product, amount, status, ... }` |
| POST | `/api/orders` | 创建订单→返回支付参数 | 是 | `{ product_id, quantity?, promoter_id? }` | `{ order_id, pay_params }` |
| PUT | `/api/orders/{id}/status` | 更新订单状态 | 是 | `{ status }` | `{ code: 200 }` |
| POST | `/api/orders/pay-notify` | 支付回调通知 | 否 | （原始支付回调数据） | `{ code: 200 }` |

---

## 4. 搜索模块 `/api/search`

| 方法 | 路径 | 说明 | 认证 | 参数 | 响应 |
|------|------|------|------|------|------|
| GET | `/api/search` | 产品搜索 | 否 | `?q=&category=&region=&min_price=&max_price=&sort_by=&page=&page_size=&highlight=` | `{ items, total, ... }` |
| GET | `/api/search/categories` | 获取所有分类列表 | 否 | — | `["分类1", "分类2", ...]` |
| GET | `/api/search/suggestions` | 搜索建议（前缀补全） | 否 | `?q=&limit=` | `[{ text, count }]` |
| GET | `/api/search/rebuild` | 重建搜索索引 | 是 | — | `{ indexed_count }` |
| GET | `/api/search/stats` | 搜索统计 | 是 | — | `{ total_docs, index_size }` |
| GET | `/api/search/vector` | 向量搜索 | 是 | `?q=&limit=&threshold=` | `[{ id, score, ... }]` |
| GET | `/api/search/rerank` | 重排序搜索 | 是 | `?q=&limit=` | `[{ id, score, ... }]` |
| GET | `/api/search/vector/stats` | 向量索引统计 | 是 | — | `{ vector_count, dimension }` |

---

## 5. 支付模块 `/api/payment`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| POST | `/api/payment/wxpay/unified-order` | 微信统一下单（JSAPI） | 是 | `{ order_id, openid? }` | `{ prepay_id, paySign, ... }` |
| POST | `/api/payment/wxpay/callback` | 微信支付回调 | 否 | （微信回调XML） | `{ return_code: "SUCCESS" }` |
| GET | `/api/payment/wxpay/query/{order_no}` | 查询订单支付状态 | 是 | — | `{ trade_state, total_fee, ... }` |
| POST | `/api/payment/wxpay/refund` | 微信退款 | 是 | `{ order_id, reason? }` | `{ refund_id, ... }` |
| POST | `/api/payment/alipay/unified-order` | 支付宝统一下单 | 是 | `{ order_id, subject? }` | `{ trade_no, ... }` |
| GET | `/api/payment/config` | 获取前端支付配置（无密钥） | 否 | — | `{ wxpay_appid, alipay_appid, ... }` |

---

## 6. 充值模块 `/api/recharge`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| POST | `/api/recharge/precreate` | 预创建充值单 | 是 | `{ amount, platform? }` | `{ order_no, pay_params }` |
| GET | `/api/recharge/query/{order_no}` | 查询充值单状态 | 是 | — | `{ status, amount, ... }` |
| GET | `/api/recharge/list` | 充值记录列表（分页） | 是 | `?page=&limit=` | `{ items, total, ... }` |
| GET | `/api/recharge/balance` | 查询余额+最近10条流水 | 是 | — | `{ balance, recent_transactions }` |
| POST | `/api/recharge/adjust` | 管理员调整余额 | 是(admin) | `{ user_id, amount, remark? }` | `{ new_balance }` |
| GET | `/api/recharge/balance-logs` | 分页查询余额流水 | 是 | `?page=&limit=` | `{ items, total }` |

---

## 7. 管理后台 `/api/admin`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/admin/dashboard` | 数据看板 | 是(admin) | — | `{ users_count, orders_count, revenue, ... }` |
| GET | `/api/admin/users` | 用户列表 | 是(admin) | — | `[{ id, username, role, ... }]` |
| PATCH | `/api/admin/users/{id}/role` | 修改用户角色 | 是(admin) | `{ role }` | `{ code: 200 }` |
| GET | `/api/admin/products` | 所有产品列表 | 是(admin) | `?status=` | `[{ id, name, status, ... }]` |
| PUT | `/api/admin/products/{id}/review` | 审核产品（通过/驳回） | 是(admin) | `{ action, reason? }` | `{ code: 200 }` |
| GET | `/api/admin/withdrawals` | 提现申请列表 | 是(admin) | `?status=` | `[{ id, amount, user, ... }]` |
| PUT | `/api/admin/withdrawals/{id}/review` | 审核提现 | 是(admin) | `{ action, reason? }` | `{ code: 200 }` |

---

## 8. 联系人 `/api/contacts`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/contacts` | 联系人列表（分页+标签筛选） | 是 | `?tag=&page=&page_size=` | `{ items, total, ... }` |
| POST | `/api/contacts` | 创建联系人 | 是 | `{ name, phone?, email?, company?, notes?, tags?, ... }` | `{ id, ... }` |
| GET | `/api/contacts/search` | 搜索联系人 | 是 | `?q=` | `[{ id, name, ... }]` |
| GET | `/api/contacts/tags` | 获取所有用户标签 | 是 | — | `["tag1", "tag2", ...]` |
| GET | `/api/contacts/{id}` | 联系人详情 | 是 | — | `{ id, name, ... }` |
| PUT | `/api/contacts/{id}` | 更新联系人 | 是 | `{ name?, phone?, ... }` | `{ code: 200 }` |
| DELETE | `/api/contacts/{id}` | 删除联系人 | 是 | — | `{ code: 200 }` |
| POST | `/api/contacts/batch` | 批量创建联系人 | 是 | `{ contacts: [...] }` | `{ created_count, ... }` |
| POST | `/api/contacts/seed` | 批量播种联系人 | 是 | `{ count, tags? }` | `{ seeded_count }` |

---

## 9. CRM管道 `/api/crm`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/crm/deals` | 交易列表 | 是 | — | `[{ id, contact, value, stage, ... }]` |
| POST | `/api/crm/deals` | 创建交易 | 是 | `{ contact_id, value, stage?, ... }` | `{ id, ... }` |
| GET | `/api/crm/deals/{id}` | 交易详情 | 是 | — | `{ id, contact, activities, ... }` |
| PATCH | `/api/crm/deals/{id}` | 更新交易 | 是 | `{ stage?, value?, ... }` | `{ code: 200 }` |
| POST | `/api/crm/deals/{id}/activities` | 添加交易活动 | 是 | `{ action_type, detail }` | `{ id, ... }` |
| GET | `/api/crm/pipeline` | 管道概览（各阶段汇总） | 是 | — | `{ stages: [{ name, count, value }] }` |

---

## 10. 企业库 `/api/enterprise`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/enterprise/search` | 企业搜索 | 是 | `?q=&industry=&region=&page=&page_size=` | `{ items, total }` |
| GET | `/api/enterprise/{id}` | 企业详情 | 是 | — | `{ id, name, industry, ... }` |
| POST | `/api/enterprise` | 创建企业 | 是 | `{ name, industry?, region?, ... }` | `{ id, ... }` |
| PUT | `/api/enterprise/{id}` | 更新企业 | 是 | `{ name?, industry?, ... }` | `{ code: 200 }` |
| DELETE | `/api/enterprise/{id}` | 删除企业 | 是 | — | `{ code: 200 }` |
| POST | `/api/enterprise/{id}/relation` | 添加企业关联 | 是 | `{ related_id, relation_type }` | `{ code: 200 }` |
| GET | `/api/enterprise/{id}/relations` | 获取企业关联图谱 | 是 | — | `{ relations: [...] }` |
| DELETE | `/api/enterprise/{id}/relation/{relation_id}` | 删除企业关联 | 是 | — | `{ code: 200 }` |
| POST | `/api/enterprise/enrich` | 企业信息智能补全 | 是 | `{ name, url? }` | `{ enriched_data }` |

---

## 11. AI数字名片 `/api/card`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| POST | `/api/card/scan` | 扫描名片（图片/PDF→AI字段） | 是 | `multipart: image/pdf` | `{ fields: { name, phone, company, ... } }` |
| POST | `/api/card/generate` | 生成数字名片 | 是 | `{ name, phone, company, title, ... }` | `{ id, token, url }` |
| GET | `/api/card` | 我的名片列表 | 是 | — | `[{ id, name, company, ... }]` |
| GET | `/api/card/{id}` | 名片详情（公开分享） | 否 | — | `{ id, name, company, ... }` |
| GET | `/api/card/token/{token}` | 通过分享令牌获取名片 | 否 | — | `{ id, name, company, ... }` |
| POST | `/api/card/{id}/match` | 名片供需匹配 | 是 | — | `{ matched_needs, matched_products }` |
| DELETE | `/api/card/{id}` | 删除名片（软删除） | 是 | — | `{ code: 200 }` |

---

## 12. 供需匹配 `/api/needs`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/needs` | 需求大厅列表（公开） | 否 | `?category=&status=&search=&page=&page_size=` | `{ items, total, ... }` |
| GET | `/api/needs/my` | 我的需求列表 | 是 | — | `[{ id, title, status, ... }]` |
| GET | `/api/needs/{id}` | 需求详情 | 否 | — | `{ id, title, description, budget, ... }` |
| POST | `/api/needs` | 发布需求 | 是 | `{ title, description, category?, budget?, contact_name, ... }` | `{ id, ... }` |
| PUT | `/api/needs/{id}` | 修改需求（发布者或管理员） | 是 | `{ title?, description?, status?, ... }` | `{ code: 200 }` |
| DELETE | `/api/needs/{id}` | 删除需求（发布者或管理员） | 是 | — | `{ code: 200 }` |

---

## 13. AI供需匹配 `/api/matching`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/matching/needs/{need_id}/products` | 需求→产品匹配 | 否 | — | `[{ product, score, ... }]` |
| GET | `/api/matching/products/{product_id}/needs` | 产品→需求匹配 | 否 | — | `[{ need, score, ... }]` |
| POST | `/api/matching/refresh` | 刷新匹配缓存 | 是 | — | `{ refreshed_count }` |
| GET | `/api/matching/metrics` | 匹配引擎指标 | 是 | — | `{ match_count, cache_hit_rate }` |
| GET | `/api/matching/cache/status` | 缓存状态 | 是 | — | `{ size, ttl, ... }` |

---

## 14. 推广员 `/api/promoter`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/promoter/earnings` | 推广员收益 | 是 | — | `{ total_earnings, pending, settled, ... }` |
| POST | `/api/promoter/withdraw` | 发起提现 | 是 | `{ amount, bank_info? }` | `{ withdrawal_id, status }` |
| GET | `/api/promoter/withdrawals` | 提现记录 | 是 | — | `[{ id, amount, status, created_at }]` |
| GET | `/api/promoter/wxacode` | 获取推广微信小程序码 | 是 | — | `(image/png binary)` |
| GET | `/api/promoter/wxacode-info` | 获取推广码信息 | 是 | — | `{ wxacode_url, qrcode_url }` |

---

## 15. 导入引擎 `/api/imports`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| POST | `/api/imports/preview` | 上传文件→解析→AI列名识别→预览 | 是 | `multipart: file` | `{ columns, rows, batch_id }` |
| POST | `/api/imports/confirm` | 确认导入（含去重策略） | 是 | `{ batch_id, field_mapping, duplicates?, strategy? }` | `{ imported_count, ... }` |
| GET | `/api/imports/history` | 导入历史 | 是 | `?page=&page_size=` | `{ items, total }` |

---

## 16. 发票 `/api/invoice`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| POST | `/api/invoice/apply` | 申请发票 | 是 | `{ order_id, title, tax_id?, email?, remark? }` | `{ invoice_id, status }` |
| GET | `/api/invoice/list` | 发票列表 | 是 | — | `[{ id, title, amount, status }]` |
| PUT | `/api/invoice/{id}/review` | 审核发票 | 是(admin) | `{ action, remark? }` | `{ code: 200 }` |
| GET | `/api/invoice/stats` | 发票统计 | 是(admin) | — | `{ total, pending, approved, rejected }` |

---

## 17. 对账 `/api/reconciliation`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/reconciliation/daily` | 日对账报表 | 是(admin) | `?date=` | `{ date, total_orders, total_amount, matched, ... }` |
| GET | `/api/reconciliation/list` | 对账记录列表 | 是(admin) | `?page=&page_size=` | `{ items, total }` |
| GET | `/api/reconciliation/{id}` | 对账报告详情 | 是(admin) | — | `{ id, date, details, ... }` |
| PUT | `/api/reconciliation/{id}/verify` | 审核对账报告 | 是(admin) | — | `{ code: 200 }` |
| GET | `/api/reconciliation/stats/summary` | 对账统计摘要 | 是(admin) | — | `{ total_reports, matched_rate, ... }` |

---

## 18. BI看板 `/api/bi`

| 方法 | 路径 | 说明 | 认证 | 参数 | 响应 |
|------|------|------|------|------|------|
| GET | `/api/bi/overview` | 总览（用户/产品/订单/今日注册） | 是(admin) | — | `{ total_users, total_products, total_orders, today_registrations }` |
| GET | `/api/bi/revenue` | 收入趋势（日/周/月） | 是(admin) | `?period=` | `{ labels, values }` |
| GET | `/api/bi/top-products` | 热门产品TOP10 | 是(admin) | — | `[{ name, sales, revenue }]` |
| GET | `/api/bi/user-growth` | 用户增长曲线（按日） | 是(admin) | `?days=` | `{ labels, values }` |
| GET | `/api/bi/card-stats` | AI名片统计 | 是(admin) | — | `{ total_cards, scan_count, ... }` |
| GET | `/api/bi/funnel` | 转化漏斗分析 | 是(admin) | `?start=&end=` | `{ stages: [{ name, count, rate }] }` |
| GET | `/api/bi/retention` | 用户留存率 | 是(admin) | `?period=` | `{ daily, weekly, monthly }` |
| GET | `/api/bi/churn-risk` | 流失预警用户 | 是(admin) | `?days=7` | `[{ user_id, name, last_active }]` |
| GET | `/api/bi/geo-distribution` | 用户地域分布 | 是(admin) | — | `{ provinces: [{ name, count }] }` |

---

## 19. 数据洞察 `/api/insights`

| 方法 | 路径 | 说明 | 认证 | 响应 |
|------|------|------|------|------|
| GET | `/api/insights/dashboard` | 个人数据看板 | 是 | `{ product_count, order_count, contact_count, card_count, earnings }` |

---

## 20. 首页 `/api/home`

| 方法 | 路径 | 说明 | 认证 | 响应 |
|------|------|------|------|------|
| GET | `/api/home/mission-control` | 任务控制面板（3核心状态） | 是 | `{ publish_task, invite_partner, track_split }` |

---

## 21. 通知 `/api/notifications`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/notifications` | 通知列表（分页+未读筛选） | 是 | `?page=&page_size=&unread_only=` | `{ items, total, unread_count }` |
| GET | `/api/notifications/unread-count` | 未读通知数 | 是 | — | `{ unread_count }` |
| PUT | `/api/notifications/{id}/read` | 标记单条已读 | 是 | — | `{ code: 200 }` |
| PUT | `/api/notifications/read-all` | 标记全部已读 | 是 | — | `{ updated_count }` |
| DELETE | `/api/notifications/{id}` | 删除通知 | 是 | — | `{ code: 200 }` |

---

## 22. 系统管理 `/api/system`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| GET | `/api/system/log-level` | 获取日志级别 | 是(admin) | — | `{ level }` |
| PUT | `/api/system/log-level` | 切换日志级别 | 是(admin) | `?level=DEBUG/INFO/WARNING/ERROR/CRITICAL` | `{ level }` |
| GET | `/api/system/cost/usage` | LLM用量汇总 | 是 | — | `{ daily, monthly, total, limits }` |
| GET | `/api/system/cost/breakdown` | LLM调用明细 | 是 | — | `{ daily_breakdown, by_model, by_module }` |
| GET | `/api/system/cost/models` | LLM模型价格表 | 是 | — | `{ models: [{ name, price, ... }] }` |

---

## 23. 行为事件 `/api/events`

| 方法 | 路径 | 说明 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------|------------|------|
| POST | `/api/events` | 记录用户行为事件 | 是 | `{ event_type, data?, ... }` | `{ code: 200 }` |
| POST | `/api/events/track` | 记录事件（JSON body） | 否 | `{ event_type, user_id?, data? }` | `{ code: 200 }` |
| GET | `/api/events/user/{user_id}/recent` | 获取用户最近事件 | 是(admin) | `?limit=` | `[{ event_type, created_at }]` |
| GET | `/api/events/stats/hot-products` | 热门产品统计TOP N | 否 | `?limit=10` | `[{ product_id, views, ... }]` |

---

## 24. 翻页图册 `/api/brochure`

| 方法 | 路径 | 说明 | 认证 | 请求体 | 响应 |
|------|------|------|------|--------|------|
| GET | `/api/brochure/{user_id}` | 获取翻页图册 | 否 | — | `{ user, products, cards }` |
| POST | `/api/brochure/{user_id}/visit` | 记录图册访问 | 否 | — | `{ code: 200 }` |
| POST | `/api/brochure/{user_id}/interest` | 记录用户感兴趣 | 否 | `{ product_id? }` | `{ code: 200 }` |

---

## 25. 充值回调 `/api/recharge/callback`

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/recharge/callback/mock` | 模拟充值回调（测试用） | 否 |
| POST | `/api/recharge/callback/wxpay` | 微信支付充值回调 | 否 |

---

## 26. 系统配置 `/api/admin/config`

| 方法 | 路径 | 说明 | 认证 | 请求体 | 响应 |
|------|------|------|------|--------|------|
| GET | `/api/admin/config` | 获取所有配置 | 是(admin) | — | `{ key: value, ... }` |
| PUT | `/api/admin/config/{key}` | 更新配置项 | 是(admin) | `{ value }` | `{ code: 200 }` |
| GET | `/api/admin/config/logs` | 配置变更日志 | 是(admin) | — | `[{ key, old_value, new_value, changed_by, time }]` |

---

## 27. 公共端点（无前缀）

| 方法 | 路径 | 说明 | 认证 | 响应 |
|------|------|------|------|------|
| GET | `/` | 服务根路径 | 否 | `{ service, status, version }` |
| GET | `/health` | 深度健康检查 | 否 | `{ status, database, payment, system }` |
| GET | `/health/live` | 存活检查 | 否 | `{ status, uptime_sec }` |
| GET | `/health/ready` | 就绪检查 | 否 | `{ status, database, payment }` |
| GET | `/metrics` | 应用指标（Prometheus/JSON） | 否 | `?format=prometheus|json` |
| GET | `/banners` | 首页轮播图（无/api前缀） | 否 | `{ data: [{ image, title, url }] }` |
| GET | `/api/banners` | 首页轮播图（带/api前缀） | 否 | `{ data: [{ image, title, url }] }` |
| GET | `/api/users/{user_id}/brief` | 获取用户简要信息 | 否 | `{ data: { id, name, company } }` |
| GET | `/share` | 推广落地页 | 否 | `(HTML)` |
| GET | `/docs` | Swagger API文档 | 否 | `(HTML)` |
| GET | `/redoc` | ReDoc API文档 | 否 | `(HTML)` |
| 静态 | `/static/*` | 静态文件 | 否 | 文件 |
| 静态 | `/app/*` | 前端SPA（dist构建产物） | 否 | 前端HTML |

---

## 28. WebSocket

| 路径 | 说明 |
|------|------|
| `ws://host/ws/{user_id}` | 实时通知通道。客户端先发送 `{"token": "xxx"}` 鉴权。服务端推送：`{"event": "notification", "data": {...}}`、`{"event": "order_update", "data": {...}}` |

---

## 统一错误响应

```json
// 400 Bad Request
{ "code": 400, "message": "参数错误描述" }

// 401 Unauthorized
{ "code": 401, "message": "未认证" }

// 403 Forbidden
{ "code": 403, "message": "权限不足" }

// 404 Not Found
{ "code": 404, "message": "资源不存在" }

// 429 Rate Limited
{ "code": 429, "message": "请求过于频繁", "retry_after": 30 }

// 500 Internal Error
{ "code": 500, "message": "服务器内部错误" }
```
