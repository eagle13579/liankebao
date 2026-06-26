# 链客宝 API 文档

> **Base URL**: `http://localhost:8001` (本地开发) / `https://liankebao.top` (生产)
> **Protocol**: HTTP/JSON
> **Auth**: 微信小程序 code 认证 (部分接口)

---

## 目录

- [M0 — 健康检查](#m0--健康检查)
- [M1 — 基础能力](#m1--基础能力)
  - [数字名片](#数字名片)
  - [电子画册](#电子画册)
  - [认证解密](#认证解密)
  - [冷启动引导](#冷启动引导)
  - [会员额度](#会员额度)
- [M2 — AI 供需匹配](#m2--ai-供需匹配)
  - [匹配引擎](#匹配引擎)
  - [多样性匹配 (MMR)](#多样性匹配-mmr)
- [M3 — AI 对话](#m3--ai-对话)
- [M4 — 深度服务模块](#m4--深度服务模块)
  - [学习中心](#学习中心)
  - [假设验证门禁](#假设验证门禁)
  - [留存洞察](#留存洞察)
  - [深度复盘看板](#深度复盘看板)
  - [单位经济仪表盘](#单位经济仪表盘)
  - [ABACC 销售话术](#abacc-销售话术)
- [M5 — 辅助系统](#m5--辅助系统)
  - [反馈采集](#反馈采集)
  - [审计日志](#审计日志)
  - [多语言 i18n](#多语言-i18n)
  - [Feature Flags](#feature-flags)
- [附录：AI 对话后端 (ywhy-ai-backend)](#附录ai-对话后端-ywhy-ai-backend)

---

## M0 — 健康检查

### `GET /api/health`

服务健康检查。

```json
{
  "status": "ok",
  "service": "链客宝 Backend API",
  "version": "1.0.0"
}
```

### `GET /health`

简化健康检查。

```json
{ "status": "ok" }
```

---

## M1 — 基础能力

### 数字名片

#### `POST /api/business-card/generate-card`

AI 生成企业名片（自动同步至电子画册存储）。

**Request Body:**
```json
{
  "user_id": "user_001",
  "fields": {
    "name": "张三",
    "company": "链客宝科技有限公司",
    "position": "CEO",
    "phone": "13800138000",
    "email": "zhangsan@liankebao.top",
    "wechat": "zhangsan_wx",
    "website": "https://liankebao.top",
    "address": "北京市朝阳区",
    "description": "企业家供需匹配平台",
    "logo": "https://liankebao.top/logo.png",
    "tags": ["B2B", "企业家", "匹配"]
  }
}
```

#### `GET /api/business-card/cards`

获取所有名片列表。

**Query Parameters:** `user_id` (可选, 按用户筛选)

#### `GET /api/business-card/cards/{card_id}`

获取单张名片详情。

#### `PUT /api/business-card/cards/{card_id}`

更新名片信息。

#### `DELETE /api/business-card/cards/{card_id}`

删除名片。

### 电子画册

#### `GET /api/brochure/{user_id}`

获取用户电子画册数据（单数路径）。

#### `GET /api/brochures/{user_id}`

获取用户电子画册数据（复数路径，微信小程序主入口）。

#### `GET /api/brochure/t/{share_token}`

通过分享 token 获取画册（匿名访问）。

### 认证解密

#### `POST /api/auth/wx-mini/decrypt-phone`

解密微信小程序手机号。

**Request Body:**
```json
{
  "code": "微信临时登录code",
  "encrypted_data": "加密数据",
  "iv": "加密初始向量"
}
```

**Response:**
```json
{
  "phone_number": "+8613800138000",
  "pure_phone_number": "13800138000",
  "country_code": "+86"
}
```

### 冷启动引导

#### `GET /api/v1/onboarding/templates`

获取预设模板列表（6个模板）。
- 返回字段: `id`, `name`, `description`, `preview_color`, `tags`

#### `GET /api/v1/onboarding/defaults`

获取三步引导配置（步骤名/描述/默认字段值）。

### 会员额度

#### `GET /api/membership/credits`

获取当前用户剩余匹配额度。

**Query Parameters:** `user_id` (必填)

#### `GET /api/membership/status`

获取会员状态（含额度信息）。

**Query Parameters:** `user_id` (必填)

#### `POST /api/membership/credits/use`

消耗一次匹配额度。

**Request Body:**
```json
{
  "user_id": "user_001"
}
```

**Response (402 额度不足):**
```json
{
  "detail": "匹配额度不足，请升级会员"
}
```

---

## M2 — AI 供需匹配

### 匹配引擎

#### `GET /api/matching/needs/{need_id}/products`

根据需求 ID 匹配相关产品/企业。

**Path Parameters:**
| 参数 | 类型 | 说明 |
|------|------|------|
| `need_id` | int | 需求方的名片 ID |

**Query Parameters:**
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `offset` | int | 0 | 分页偏移 |
| `limit` | int | 20 | 每页数量 (max 100) |

**Response:**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 42,
        "title": "XX科技有限公司",
        "description": "专注于AI解决方案",
        "category": "",
        "match_score": 0.85,
        "match_reasons": ["关键词匹配 (3个)"],
        "strategy": "simple"
      }
    ],
    "total": 10,
    "strategy": "simple"
  }
}
```

**匹配策略优先级:**
1. 完整匹配引擎 (external) — 如果有 `/d/链客宝/` 完整引擎
2. 三塔 DNN 匹配 (Feature Flag: `new_matching_engine`) — 灰度控制
3. 简化版关键词匹配 (回退)

#### `GET /api/matching/products/{product_id}/needs`

根据产品 ID 匹配相关需求。

参数与响应格式同上。

#### `POST /api/matching/refresh`

刷新匹配索引。

```json
{
  "code": 200,
  "message": "匹配索引已刷新",
  "data": {
    "cards_count": 128,
    "status": "ready"
  }
}
```

### 多样性匹配 (MMR)

#### `POST /api/v1/match/diverse`

MMR 多样性匹配 — 在保持相关性的同时最大化结果多样性。

**Request Body:**
```json
{
  "query": "寻找AI相关的产品经理",
  "candidates": [
    { "id": 1, "title": "AI产品经理", "description": "负责AI产品设计", "category": "科技" },
    { "id": 2, "title": "Java开发工程师", "description": "后端开发", "category": "科技" },
    { "id": 3, "title": "AI算法专家", "description": "机器学习模型设计", "category": "科技" }
  ],
  "relevance_scores": [0.95, 0.45, 0.88],
  "diversity_weight": 0.3
}
```

**参数说明:**
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `query` | string | — | 查询文本 (未提供 scores 时自动关键词匹配) |
| `candidates` | array | — | 候选匹配项列表 |
| `relevance_scores` | array | null | 可选：候选相关性分数 (与 candidates 等长) |
| `diversity_weight` | float | 0.3 | λ ∈ [0,1]; 0=纯多样性, 1=纯相关性 |

**Response:**
```json
{
  "results": [
    { "id": 1, "title": "AI产品经理", "description": "负责AI产品设计", "category": "科技", "match_score": 0.95, "mmr_score": 0.95 },
    { "id": 3, "title": "AI算法专家", "description": "机器学习模型设计", "category": "科技", "match_score": 0.88, "mmr_score": 0.62 }
  ],
  "diversity_score": 0.52,
  "metadata": {
    "strategy": "mmr",
    "total": 3,
    "diversity_weight": 0.3,
    "lambda": 0.3,
    "score_source": "provided",
    "algorithm": "Maximal Marginal Relevance"
  }
}
```

---

## M3 — AI 对话

#### `POST /api/v1/chat`

发送消息给 AI 助手，获取回复。

**Request Body:**
```json
{
  "message": "你好，我想了解如何匹配供应商",
  "session_id": "chat_a1b2c3d4e5f6"
}
```

**参数说明:**
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `message` | string | — | 用户消息内容 (必填) |
| `session_id` | string | `null` | 会话 ID (为空时自动生成) |

**Response:**
```json
{
  "reply": "您好！链客宝可以帮您匹配优质供应商...",
  "session_id": "chat_a1b2c3d4e5f6"
}
```

**调用链:**
```
前端 AIChatWidget → POST /api/v1/chat → ywhy-ai-backend (:8100) → DeepSeek
```

**错误码:**
| 状态码 | 说明 |
|--------|------|
| 502 | AI 服务不可用 |
| 504 | AI 服务响应超时 |

---

## M4 — 深度服务模块

### 学习中心

#### `GET /api/v1/learning/courses`

获取课程列表。

**Query Parameters:** `category`, `level`, `page`, `size`

#### `POST /api/v1/learning/courses`

创建课程。

#### `GET /api/v1/learning/courses/{course_id}`

获取课程详情。

#### `PUT /api/v1/learning/courses/{course_id}`

更新课程。

#### `DELETE /api/v1/learning/courses/{course_id}`

删除课程。

#### `GET /api/v1/learning/courses/{course_id}/modules`

获取课程的模块列表 (X1-X10)。

#### `POST /api/v1/learning/courses/{course_id}/modules`

添加模块。

#### `GET /api/v1/learning/progress/{user_id}`

获取用户学习进度。

#### `POST /api/v1/learning/progress`

更新学习进度。

#### `POST /api/v1/learning/mentor/ask`

AI 导师问答。

### 假设验证门禁

#### `GET /api/v1/hypotheses`

获取假设列表。

**Query Parameters:** `status`, `category`, `page`, `size`

#### `POST /api/v1/hypotheses`

创建商业假设。

#### `GET /api/v1/hypotheses/{hypothesis_id}`

获取假设详情。

#### `PUT /api/v1/hypotheses/{hypothesis_id}`

更新假设。

#### `DELETE /api/v1/hypotheses/{hypothesis_id}`

删除假设。

#### `POST /api/v1/hypotheses/{hypothesis_id}/experiments`

为假设创建实验设计。

#### `POST /api/v1/hypotheses/{hypothesis_id}/validate`

执行假设验证（门禁判断）。

### 留存洞察

#### `GET /api/v1/retention/cohorts`

获取 Cohort 群组列表。

#### `POST /api/v1/retention/cohorts`

创建 Cohort 群组。

#### `GET /api/v1/retention/cohorts/{cohort_id}/retention`

获取 Cohort 留存数据。

#### `POST /api/v1/retention/activities`

记录用户行为。

#### `GET /api/v1/retention/insights`

获取留存洞察与策略建议。

#### `GET /api/v1/retention/churn-signals`

获取流失预测信号列表。

### 深度复盘看板

#### `GET /api/v1/retro/boards`

获取复盘看板列表。

**Query Parameters:** `status`, `stage`, `project`, `page`, `size`

#### `POST /api/v1/retro/boards`

创建复盘看板。

#### `GET /api/v1/retro/boards/{board_id}`

获取看板详情（含复盘条目 + 行动项）。

#### `PUT /api/v1/retro/boards/{board_id}`

更新看板。

#### `DELETE /api/v1/retro/boards/{board_id}`

删除看板。

#### `POST /api/v1/retro/boards/{board_id}/items`

添加复盘条目 (F1-F8)。

#### `PUT /api/v1/retro/boards/{board_id}/items/{item_id}`

更新复盘条目。

#### `POST /api/v1/retro/boards/{board_id}/actions`

添加行动项 (F9)。

#### `PUT /api/v1/retro/boards/{board_id}/actions/{action_id}`

更新行动项。

### 单位经济仪表盘

#### `GET /api/v1/unit-economics/snapshots`

获取单位经济快照列表。

**Query Parameters:** `period` (月份, 如 `2026-06`)

#### `POST /api/v1/unit-economics/costs`

录入成本条目。

#### `GET /api/v1/unit-economics/costs`

获取成本列表。

#### `POST /api/v1/unit-economics/revenues`

录入收入条目。

#### `GET /api/v1/unit-economics/revenues`

获取收入列表。

#### `GET /api/v1/unit-economics/dashboard`

获取仪表盘摘要（LTV/CAC/比/回收周期/毛利率）。

#### `GET /api/v1/unit-economics/trends`

获取趋势分析。

### ABACC 销售话术

#### `GET /api/v1/sales-scripts`

获取话术模板列表。

**Query Parameters:** `scenario`, `target_role`, `page`, `size`

#### `POST /api/v1/sales-scripts`

创建话术模板。

#### `GET /api/v1/sales-scripts/{script_id}`

获取话术模板详情。

#### `PUT /api/v1/sales-scripts/{script_id}`

更新话术模板。

#### `DELETE /api/v1/sales-scripts/{script_id}`

删除话术模板。

#### `POST /api/v1/sales-scripts/evaluate-tension`

评估话术张力分数。

---

## M5 — 辅助系统

### 反馈采集

#### `POST /api/v1/feedback`

提交匹配反馈。

**Request Body:**
```json
{
  "match_id": "match_001",
  "rating": 4,
  "comment": "匹配结果很好，推荐的企业很符合需求",
  "user_id": "user_001"
}
```

**Response (201):**
```json
{
  "match_id": "match_001",
  "rating": 4,
  "comment": "匹配结果很好，推荐的企业很符合需求",
  "user_id": "user_001",
  "timestamp": 1719234567.89,
  "message": "反馈提交成功"
}
```

#### `GET /api/v1/feedback`

获取反馈记录列表（最近优先，辅助调试）。

**Query Parameters:** `limit` (默认 20), `offset` (默认 0)

#### `GET /api/v1/feedback/stats`

获取全局反馈统计。

**Response:**
```json
{
  "total": 128,
  "avg_rating": 4.2,
  "rating_distribution": { "1": 5, "2": 8, "3": 15, "4": 40, "5": 60 },
  "by_date": { "2026-06-01": 12, "2026-06-02": 18 }
}
```

### 审计日志

#### `GET /api/v1/audit/logs`

日志查询 (分页+筛选)。

**Query Parameters:** `user_id`, `action`, `resource_type`, `result`, `from_date`, `to_date`, `page`, `size`

#### `GET /api/v1/audit/logs/user/{user_id}`

用户操作历史。

#### `GET /api/v1/audit/logs/recent`

最近 24 小时操作。

#### `GET /api/v1/audit/logs/export`

导出为 CSV。

#### `DELETE /api/v1/audit/logs/cleanup`

清理过期日志。

**Query Parameters:** `before_date` (清理此日期之前的日志)

### 多语言 i18n

#### `GET /api/i18n/translations/{lang}`

获取指定语言的翻译文本。

**Path Parameters:** `lang` — 语言代码 (如 `zh`, `en`, `ko`)

#### `POST /api/i18n/translations/{lang}`

更新翻译条目。

### Feature Flags

#### `GET /api/feature-flags`

获取所有功能开关状态。

#### `POST /api/feature-flags/{flag_name}/enable`

启用功能开关。

#### `POST /api/feature-flags/{flag_name}/disable`

禁用功能开关。

---

## 附录：AI 对话后端 (ywhy-ai-backend)

> **Base URL**: `http://localhost:8100`

### `POST /api/chat/completion`

对话补全 (非流式)。

**Request Body:**
```json
{
  "messages": [{ "role": "user", "content": "Hello" }],
  "model": "deepseek-chat",
  "stream": false
}
```

### `POST /api/upload/file`

文件上传 (受 50MB 大小限制)。

### `POST /api/auth/login`

认证登录 (速率限制: 20 次/分钟)。

### `GET /api/health`

健康检查。

---

> **文档版本**: v1.0.0 — 最后更新: 2026-06-24
