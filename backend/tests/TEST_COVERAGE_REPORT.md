# 链客宝AI后端测试覆盖分析报告

> 生成日期: 2026-05-27
> 项目路径: D:/链客宝AI/backend/

---

## 一、总体概览

| 模块 | 路由数 | 行数 | 测试文件 | 测试数 | 覆盖状态 |
|------|--------|------|----------|--------|----------|
| auth | 6 | 349 | test_auth.py | 13 | ✅ 已覆盖 |
| products | 5 | 219 | test_products.py | 9 | ✅ 已覆盖（有缺口） |
| orders | 5 | 421 | test_orders.py | 10 | ✅ 已覆盖（有缺口） |
| needs | 6 | 216 | test_needs.py | 27 | ✅ 覆盖良好 |
| payment | 6 | 571 | test_payment.py | 26 | ✅ 覆盖良好 |
| promoter | 5 | 236 | test_promoter.py | 10 | ✅ 已覆盖（有缺口） |
| recharge | - | - | test_recharge.py | 29 | ✅ 覆盖良好 |
| recharge(comprehensive) | - | - | test_recharge_comprehensive.py | 35 | ✅ 覆盖良好 |
| search | 5 | 389 | test_search.py | 43 | ✅ 覆盖良好 |
| **activities** | **2** | **108** | **❌ 缺失** | **0** | **❌ 无测试** |
| **admin** | **7** | **220** | **❌ 缺失** | **0** | **❌ 无测试** |
| **contacts** | **8** | **269** | **❌ 缺失** | **0** | **❌ 无测试** |
| **imports** | **3** | **413** | **❌ 缺失** | **0** | **❌ 无测试** |
| **insights** | **1** | **85** | **❌ 缺失** | **0** | **❌ 无测试** |
| API集成E2E | - | 421 | test_api_integration.py | 17 | ✅ 多模块覆盖 |
| **总计** | **59** | **3496** | **12文件** | **219** | **71.4%模块覆盖** |

---

## 二、缺失测试模块 — 详细分析

### 2.1 `activities.py` (108行, 2路由)

**路由清单:**

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| GET | `/api/contacts/{contact_id}/activities` | JWT | 获取联系人的活动列表 |
| POST | `/api/contacts/{contact_id}/activities` | JWT | 为联系人添加活动 |

**输入/输出分析:**

| 端点 | 输入参数 | 边界条件 | 响应码 |
|------|---------|---------|--------|
| GET | contact_id(路径), page(1-∞), page_size(1-100) | 联系人不存在(404)、page=1、page_size=100(上限)、page_size=1(下限)、无活动列表(空[]) | 200/404 |
| POST | contact_id(路径), ActivityCreate{action_type,summary,detail} | 联系人不存在(404)、无效action_type(400)、summary超500字、detail为空、action_type=wechat/order/import等边界值 | 201/400/404 |

**测试需求:**
1. ✅ 成功获取活动列表（分页）
2. ✅ 联系人不存在返回404
3. ✅ 分页参数边界（page_size=1, page_size=100）
4. ✅ 空活动列表返回空数组
5. ✅ 成功创建活动（每种action_type至少测一次）
6. ✅ 无效action_type返回400
7. ✅ 不同用户的联系人隔离（跨用户访问返回404）
8. ✅ 未认证返回401

---

### 2.2 `admin.py` (220行, 7路由)

**路由清单:**

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| GET | `/api/admin/dashboard` | Admin | 数据看板统计 |
| GET | `/api/admin/users` | Admin | 用户列表 |
| PATCH | `/api/admin/users/{user_id}/role` | Admin | 修改用户角色 |
| GET | `/api/admin/products` | Admin | 所有产品列表 |
| PUT | `/api/admin/products/{product_id}/review` | Admin | 审核产品 |
| GET | `/api/admin/withdrawals` | Admin | 提现申请列表 |
| PUT | `/api/admin/withdrawals/{withdrawal_id}/review` | Admin | 审核提现 |

**输入/输出分析:**

| 端点 | 输入参数 | 边界条件 | 响应码 |
|------|---------|---------|--------|
| GET /dashboard | 无 | 无数据时统计为0 | 200 |
| GET /users | 无 | 无用户返回空列表 | 200 |
| PATCH /users/{id}/role | user_id, role | 不能修改自己角色(400)、用户不存在(404)、无效角色(422)、非管理员访问(403) | 200/400/404/403 |
| GET /products | status(可选) | 无产品返回空列表、按状态筛选 | 200 |
| PUT /products/{id}/review | product_id, action+reason | 产品不存在(404)、无效action(400)、重复审核 | 200/400/404 |
| GET /withdrawals | status(可选) | 无提现返回空列表、按状态筛选 | 200 |
| PUT /withdrawals/{id}/review | withdrawal_id, action+reason | 提现不存在(404)、无效action(400) | 200/400/404 |

**测试需求:**
1. ✅ 看板数据正确（总数统计,今日订单,待审核产品数,待处理提现数）
2. ✅ 用户列表返回所有非删除用户
3. ✅ 修改用户角色（buyer→supplier→promoter→admin）
4. ✅ 不能修改自己的角色
5. ✅ 用户不存在返回404
6. ✅ 产品列表（无筛选、按status筛选）
7. ✅ 产品审核（通过/驳回）
8. ✅ 产品不存在返回404
9. ✅ 提现列表（无筛选、按status筛选）
10. ✅ 提现审核（通过/驳回）
11. ✅ 非管理员角色访问所有端点返回403
12. ✅ 未认证返回401
13. ✅ 无效action值返回400

---

### 2.3 `contacts.py` (269行, 8路由)

**路由清单:**

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| GET | `/api/contacts` | JWT | 联系人列表（分页+标签筛选） |
| POST | `/api/contacts` | JWT | 创建联系人 |
| GET | `/api/contacts/search` | JWT | FTS搜索联系人 |
| GET | `/api/contacts/tags` | JWT | 获取所有标签 |
| GET | `/api/contacts/{contact_id}` | JWT | 联系人详情 |
| PUT | `/api/contacts/{contact_id}` | JWT | 更新联系人 |
| DELETE | `/api/contacts/{contact_id}` | JWT | 删除联系人（软删除） |
| POST | `/api/contacts/batch` | JWT | 批量创建联系人 |

**输入/输出分析:**

| 端点 | 输入参数 | 边界条件 | 响应码 |
|------|---------|---------|--------|
| GET /contacts | tag(可选), page(1-∞), page_size(1-100) | 无联系人返回空、标签筛选精确匹配、分页边界 | 200 |
| POST /contacts | ContactCreate{name,phone,wechat_id,etc} | name必填(422)、phone格式(422)、各字段超长 | 201/422 |
| GET /contacts/search | q(必填), page, page_size | 空q(422)、无结果返回空、模糊匹配各字段 | 200/422 |
| GET /contacts/tags | 无 | 无标签返回空列表、有重复标签去重、排序 | 200 |
| GET /contacts/{id} | contact_id | 不存在404、跨用户隔离 | 200/404 |
| PUT /contacts/{id} | contact_id, ContactUpdate | 部分字段更新、清空字段、不存在404 | 200/404 |
| DELETE /contacts/{id} | contact_id | 软删除后不可查、不存在404 | 200/404 |
| POST /contacts/batch | List[ContactCreate] | 空数组、大量批量、某条数据校验失败 | 201/422 |

**测试需求:**
1. ✅ 联系人列表（分页、标签筛选）
2. ✅ 创建联系人（所有字段填写/仅必填）
3. ✅ 创建联系人name为空返回422
4. ✅ 搜索联系人（按姓名/电话/公司/备注等多字段FTS）
5. ✅ 搜索无结果返回空
6. ✅ 获取标签列表（去重+排序）
7. ✅ 联系人详情（获取/不存在404）
8. ✅ 更新联系人（部分字段）
9. ✅ 删除联系人（软删除后的隔离）
10. ✅ 批量创建联系人
11. ✅ 跨用户数据隔离（用户A不能看到/修改用户B的联系人）
12. ✅ 未认证返回401
13. ✅ 标签筛选的精确匹配和子串行为

---

### 2.4 `imports.py` (413行, 3路由)

**路由清单:**

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| POST | `/api/imports/preview` | JWT | 上传文件→解析→返回预览 |
| POST | `/api/imports/confirm` | JWT | 确认导入（含去重策略） |
| GET | `/api/imports/history` | JWT | 导入历史列表 |

**输入/输出分析:**

| 端点 | 输入参数 | 边界条件 | 响应码 |
|------|---------|---------|--------|
| POST /preview | UploadFile(file) | 文件超10MB(413)、不支持格式(400)、空文件(400)、CSV/VCF格式、解析失败(400) | 200/400/413 |
| POST /confirm | ImportConfirmRequest{batch_id,field_mapping,strategy,duplicates} | batch_id不存在(404)、无权操作批次(403)、去重策略skip/merge/update、逐行指定处理方式 | 200/404/403 |
| GET /history | page, page_size | 无导入历史返回空、分页 | 200 |

**测试需求:**
1. ✅ 文件上传预览（CSV格式返回200）
2. ✅ 文件过大返回413
3. ✅ 不支持的文件格式返回400
4. ✅ 确认导入（skip策略）
5. ✅ 确认导入（merge策略）
6. ✅ 确认导入（update策略）
7. ✅ 批次ID过期/不存在返回404
8. ✅ 无权操作其他用户的批次返回403
9. ✅ 导入历史查询（分页）
10. ✅ 未认证所有端点返回401
11. ✅ 逐行指定duplicates处理方式

---

### 2.5 `insights.py` (85行, 1路由)

**路由清单:**

| 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|
| GET | `/api/insights/dashboard` | JWT | 用户数据洞察看板 |

**输入/输出分析:**

| 端点 | 输入参数 | 边界条件 | 响应码 |
|------|---------|---------|--------|
| GET /dashboard | 无 | 无产品/无订单返回0、有上月数据做环比、推广佣金0、月初月末边界 | 200 |

**测试需求:**
1. ✅ 获取数据看板（产品数、订单数、本月成交额、推广收益、上月环比）
2. ✅ 无数据时返回0而非None
3. ✅ 金额精度保留2位小数
4. ✅ 月初/月末跨月时间边界
5. ✅ 未认证返回401

---

## 三、已有测试模块 — 缺口分析

### 3.1 `test_products.py` 缺口

当前测试覆盖:
- 列表（未登录只看approved、管理员看全部、分页、分类筛选）
- 创建（认证用户、未认证401）
- 搜索（按名称/描述、无结果）

**缺失场景:**
| 缺失项目 | 重要性 | 说明 |
|---------|--------|------|
| 获取产品详情 (GET /api/products/{id}) | 🔴 高 | 详情页核心API，含404测试 |
| 更新产品 (PUT /api/products/{id}) | 🔴 高 | 供应商修改自有产品 |
| 删除产品 (DELETE /api/products/{id}) | 🔴 高 | 软删除 |
| 产品详情含owner信息 | 🟡 中 | 返回数据结构验证 |
| 非产品所有人无法修改 | 🟡 中 | 权限隔离 |
| 产品创建含所有可选字段 | 🟢 低 | images/specs/brand等 |
| 库存为0时产品状态 | 🟢 低 | 是否标记为缺货 |
| 价格负值/零值校验 | 🟢 低 | 业务校验 |

### 3.2 `test_orders.py` 缺口

当前测试覆盖:
- 创建订单（成功、指定推广员、未认证401、产品不存在404、库存不足400）
- 状态流转（paid→shipped→received→refunded、非法流转、权限）

**缺失场景:**
| 缺失项目 | 重要性 | 说明 |
|---------|--------|------|
| 我的订单列表 (GET /api/orders) | 🔴 高 | 订单核心功能 |
| 订单详情 (GET /api/orders/{id}) | 🔴 高 | 查看单个订单 |
| 按状态筛选订单列表 | 🟡 中 | filter by status |
| 取消订单 (pending→cancelled) | 🟡 中 | 支付前取消 |
| 订单列表分页 | 🟡 中 | page/page_size |
| 非订单持有人查看详情返回403/404 | 🟡 中 | 权限隔离 |
| 下单时promoter_id不存在 | 🟢 低 | 边界 |

### 3.3 `test_promoter.py` 缺口

当前测试覆盖:
- 收益查询（总收益/已提现/提现中/可提现）
- 提现（成功/超额/零金额/权限）
- 提现记录查询

**缺失场景:**
| 缺失项目 | 重要性 | 说明 |
|---------|--------|------|
| 推广统计数据 (订单明细/佣金明细) | 🟡 中 | 如果存在相关接口 |
| 提现记录分页 | 🟡 中 | page/page_size参数 |
| 提现银行信息格式校验 | 🟢 低 | JSON格式验证 |

### 3.4 `test_auth.py` 缺口

当前测试覆盖:
- 注册（成功/重复/密码太短/非法用户名）
- 登录（成功/错密码/不存在/频率限制）
- 刷新token（成功/轮换/无效token/access_token刷新）
- 退出（成功/无token）

**缺失场景:**
| 缺失项目 | 重要性 | 说明 |
|---------|--------|------|
| 获取当前用户 (GET /api/auth/me) | 🔴 高 | 用户信息核心API |
| 微信登录 | 🟡 中 | 如果实现 |
| 更新用户信息 | 🟡 中 | 修改个人资料 |
| 修改密码 | 🟡 中 | 旧密码验证 |
| token过期返回401 | 🟡 中 | JWT过期测试 |
| 注册时role无效值 | 🟢 低 | buyer/promoter/supplier/admin之外 |

### 3.5 `test_needs.py` 缺口

当前测试覆盖-良好（27个测试覆盖了CRUD、权限、分页、筛选等），仅少数边界场景补充:
| 缺失项目 | 重要性 | 说明 |
|---------|--------|------|
| 多个标签/品类组合筛选 | 🟢 低 | AND/OR逻辑 |
| contact_phone格式校验 | 🟢 低 | 手机号正则 |
| 需求数量过多时分页边界 | 🟢 低 | max_page_size行为 |

---

## 四、测试优先级建议

### P0 - 必须立即补充（核心功能+安全）
| 模块 | 测试文件 | 优先级原因 |
|------|---------|-----------|
| admin | test_admin.py | 7个管理端点，涉及用户角色、产品审核、提现审核等敏感操作 |
| contacts | test_contacts.py | 8个端点，核心业务模块，联系人数据隔离安全 |
| products | (补充) get/update/delete产品 | 核心CRUD缺失 |

### P1 - 重要（业务流程完整性）
| 模块 | 测试文件 | 优先级原因 |
|------|---------|-----------|
| activities | test_activities.py | 联系人时间线功能 |
| imports | test_imports.py | 文件导入功能，含去重逻辑 |
| insights | test_insights.py | 用户数据看板 |
| orders | (补充) 列表/详情/取消 | 订单列表核心功能 |
| auth | (补充) /me端点 | 用户信息API |

### P2 - 建议补充（边界场景）
| 模块 | 说明 |
|------|------|
| products | 价格负值/超长字段名 |
| needs | 组合筛选 |
| promoter | 分页参数边界 |

---

## 五、结论

- **总路由数**: 59 (12个模块)
- **已有测试**: 7个模块有独立测试文件（含219个测试）+ 1个E2E集成测试
- **完全缺失测试**: 5个模块（activities, admin, contacts, imports, insights）
- **测试覆盖率**: 模块覆盖率 58.3%（7/12完全覆盖），路由覆盖率约 64%（38/59）
- **风险点**: admin管理后台无任何认证和权限测试，是最大的安全风险
- **推荐行动**: 优先创建 admin + contacts 的测试文件，这两者涉及核心业务和安全权限
