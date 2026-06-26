# 链客宝 API 完整目录

> 生成日期: 2026-06-25
> 路由文件数: 20 (routers/ 目录) + 1 (i18n) + 1 (feature_flags) + 2 健康检查
> 注册路由模块数: 23 (main.py)
> 总计 API 端点: ~105 个

---

## 功能域分组总览

| 分组 | 前缀 | 端点数 | 路由文件 |
|------|------|--------|----------|
| **M0 - 基础能力** | 多个 | 17 | auth, business_card, brochure_bridge, onboarding |
| **M1 - 假设验证门禁** | `/api/hypothesis` | 10 | hypothesis_gate.py |
| **M2 - 学习中心** | `/api/learning` | 14 | learning_center.py |
| **M3 - 留存洞察** | `/api/retention` | 11 | retention_insights.py |
| **M4 - 深度复盘看板** | `/api/retro` | 15 | retro_board.py |
| **M5 - 单位经济** | `/api/unit-economics` | 8 | unit_economics.py |
| **M6 - 匹配引擎** | `/api/matching`, `/api/v1/match` | 4 | matching_engine.py |
| **M7 - 会员与额度** | `/api/membership` | 4 | membership.py |
| **反馈采集** | `/api/v1/feedback` | 3 | feedback.py |
| **销售话术** | `/api/sales-script` | 9 | sales_script.py |
| **通知与IM Bot** | `/api/notifications` | 2 | notification_router.py |
| **AI对话** | `/api/v1/chat` | 1 | chat.py |
| **审计日志** | `/api/v1/audit` | 6 | audit.py |
| **合规审计** | `/api/compliance` | 3 | compliance.py |
| **文件存储** | `/api/storage` | 3 | storage_router.py |
| **微信集成** | `/api/wechat` | 3 | wechat_router.py |
| **i18n多语言** | (由 i18n 模块注册) | - | i18n（非 routers/） |
| **Feature Flags** | (由 features 注册) | - | features（非 routers/） |
| **健康检查** | `/api/health`, `/health` | 2 | main.py |

---

## M0 - 基础能力

### 认证与微信解密 (`auth.py`)

**Router:** `APIRouter(prefix="/api/auth", tags=["认证与微信解密"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/auth/login` | 开发环境登录（用户名密码 → JWT Token） |
| POST | `/api/auth/decrypt-phone` | 微信手机号解密（code + encryptedData + iv → 手机号） |

### 企业数字名片 (`business_card.py`)

**Router:** `APIRouter(prefix="/api/business-card", tags=["企业数字名片"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/business-card/cards` | 创建名片 |
| GET | `/api/business-card/cards` | 获取名片列表 |
| GET | `/api/business-card/cards/{card_id}` | 获取名片详情 |
| PUT | `/api/business-card/cards/{card_id}` | 更新名片 |
| DELETE | `/api/business-card/cards/{card_id}` | 删除名片 |
| POST | `/api/business-card/generate-card` | AI 生成名片（含同步钩子） |
| GET | `/api/business-card/share/{share_token}` | 通过分享令牌获取名片 |

### 电子画册桥接 (`brochure_bridge.py`)

**Router:** `APIRouter(prefix="/api", tags=["电子画册桥接"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/brochure/{user_id}` | 获取用户电子画册（单数路径） |
| GET | `/api/brochures/{user_id}` | 获取用户电子画册（复数路径，小程序入口） |
| GET | `/api/brochure/t/{share_token}` | 通过分享令牌获取电子画册 |

### 冷启动引导 (`onboarding.py`)

**Router:** `APIRouter(prefix="/api/v1/onboarding", tags=["冷启动引导"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/v1/onboarding/templates` | 获取预设模板列表（6个模板） |
| GET | `/api/v1/onboarding/defaults` | 获取三步引导默认填充配置 |

---

## M1 - 假设验证门禁 (`hypothesis_gate.py`)

**Router:** `APIRouter(prefix="/api/hypothesis", tags=["假设验证门禁"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/hypothesis/hypotheses` | 获取假设列表 |
| GET | `/api/hypothesis/hypotheses/{hypothesis_id}` | 获取假设详情 |
| POST | `/api/hypothesis/hypotheses` | 创建假设 |
| PUT | `/api/hypothesis/hypotheses/{hypothesis_id}` | 更新假设 |
| DELETE | `/api/hypothesis/hypotheses/{hypothesis_id}` | 删除假设 |
| GET | `/api/hypothesis/experiments` | 获取实验列表 |
| POST | `/api/hypothesis/experiments` | 创建实验设计 |
| POST | `/api/hypothesis/validate` | 提交验证结果 |
| GET | `/api/hypothesis/results/{hypothesis_id}` | 获取假设的验证结果 |
| GET | `/api/hypothesis/gate-check/{hypothesis_id}` | 门禁检查 — 判断假设能否进入下一阶段 |

---

## M2 - 学习中心 (`learning_center.py`)

**Router:** `APIRouter(prefix="/api/learning", tags=["学习中心"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/learning/path` | 获取X1-X10学习路径定义 |
| GET | `/api/learning/courses` | 获取课程列表 |
| GET | `/api/learning/courses/{course_id}` | 获取课程详情 |
| POST | `/api/learning/courses` | 创建课程 |
| GET | `/api/learning/courses/{course_id}/modules` | 获取课程的所有模块 |
| POST | `/api/learning/modules` | 创建课程模块 |
| GET | `/api/learning/modules/{module_id}/lessons` | 获取模块的所有课时 |
| POST | `/api/learning/lessons` | 创建课时 |
| GET | `/api/learning/progress/{user_id}` | 获取用户学习进度 |
| POST | `/api/learning/progress` | 更新/创建学习进度 |
| GET | `/api/learning/tutor/{user_id}/{course_id}` | 获取AI导师对话历史 |
| POST | `/api/learning/tutor/ask` | 向AI导师提问 |
| GET | `/api/learning/certifications/{user_id}` | 获取用户认证记录 |
| POST | `/api/learning/certifications` | 颁发认证 |
| GET | `/api/learning/dashboard/{user_id}` | 获取用户学习仪表盘 |

---

## M3 - 留存洞察 (`retention_insights.py`)

**Router:** `APIRouter(prefix="/api/retention", tags=["留存分析引擎"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/retention/cohorts` | 获取Cohort列表 |
| POST | `/api/retention/cohorts` | 创建Cohort |
| GET | `/api/retention/cohorts/{cohort_id}/retention` | 获取Cohort留存数据 |
| GET | `/api/retention/retention-matrix` | 获取留存矩阵（所有Cohort） |
| GET | `/api/retention/activities` | 获取用户活跃记录 |
| POST | `/api/retention/activities` | 记录用户活跃 |
| GET | `/api/retention/churn-signals` | 获取流失信号列表 |
| POST | `/api/retention/churn-signals` | 创建流失信号 |
| PUT | `/api/retention/churn-signals/{signal_id}/resolve` | 标记流失信号为已解决 |
| GET | `/api/retention/strategies` | 获取留存策略推荐列表 |
| GET | `/api/retention/overview` | 留存分析总览 |

---

## M4 - 深度复盘看板 (`retro_board.py`)

**Router:** `APIRouter(prefix="/api/retro", tags=["深度复盘看板"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/retro/stages` | 获取F1-F9复盘阶段定义 |
| GET | `/api/retro/boards` | 获取复盘看板列表 |
| POST | `/api/retro/boards` | 创建复盘看板 |
| GET | `/api/retro/boards/{board_id}` | 获取复盘看板详情 |
| PUT | `/api/retro/boards/{board_id}/stage` | 推进复盘阶段（F1→F2→...→F9） |
| DELETE | `/api/retro/boards/{board_id}` | 删除复盘看板 |
| GET | `/api/retro/items/{board_id}` | 获取看板的所有复盘条目 |
| POST | `/api/retro/items` | 创建复盘条目 |
| PUT | `/api/retro/items/{item_id}` | 更新复盘条目 |
| DELETE | `/api/retro/items/{item_id}` | 删除复盘条目 |
| GET | `/api/retro/actions/{board_id}` | 获取看板的所有行动项 |
| POST | `/api/retro/actions` | 创建行动项 |
| PUT | `/api/retro/actions/{action_id}` | 更新行动项 |
| PUT | `/api/retro/actions/{action_id}/progress` | 更新行动项进度 |
| GET | `/api/retro/boards/{board_id}/summary` | 获取看板统计摘要 |

---

## M5 - 单位经济 (`unit_economics.py`)

**Router:** `APIRouter(prefix="/api/unit-economics", tags=["单位经济仪表盘"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/unit-economics/costs` | 获取成本条目列表 |
| POST | `/api/unit-economics/costs` | 录入成本条目 |
| DELETE | `/api/unit-economics/costs/{cost_id}` | 删除成本条目 |
| GET | `/api/unit-economics/revenues` | 获取收入条目列表 |
| POST | `/api/unit-economics/revenues` | 录入收入条目 |
| GET | `/api/unit-economics/calculate/{period}` | 计算指定月份的单位经济指标 |
| GET | `/api/unit-economics/dashboard` | 获取单位经济仪表盘数据 |
| GET | `/api/unit-economics/channels` | 获取各渠道经济分析 |

---

## M6 - 匹配引擎 (`matching_engine.py`)

### 主匹配引擎

**Router:** `APIRouter(prefix="/api/matching", tags=["AI供需匹配（轻量版）"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/matching/needs/{need_id}/products` | 根据需求ID匹配相关产品 |
| GET | `/api/matching/products/{product_id}/needs` | 根据产品ID匹配相关需求 |
| POST | `/api/matching/refresh` | 刷新匹配索引 |

### MMR 多样性匹配

**Router:** `APIRouter(prefix="/api/v1/match", tags=["AI多样性匹配"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/v1/match/diverse` | MMR多样性匹配（Maximal Marginal Relevance） |

---

## M7 - 会员与额度 (`membership.py`)

**Router:** `APIRouter(prefix="/api/membership", tags=["会员与额度（轻量版）"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/membership/credits` | 获取当前用户剩余匹配额度 |
| GET | `/api/membership/status` | 获取会员状态（含额度信息） |
| POST | `/api/membership/credits/use` | 消耗一次匹配额度（402检查） |
| GET | `/api/membership/credits/logs` | 获取额度消耗日志 |

---

## 反馈采集 (`feedback.py`)

**Router:** `APIRouter(prefix="/api/v1/feedback", tags=["反馈采集"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/v1/feedback` | 提交反馈（match_id, rating, comment, user_id） |
| GET | `/api/v1/feedback/stats` | 获取全局统计（总数/平均分/分布） |
| GET | `/api/v1/feedback` | 查询反馈记录列表（辅助调试） |

---

## 销售话术 (`sales_script.py`)

**Router:** `APIRouter(prefix="/api/sales-script", tags=["销售话术模板"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/sales-script/presets` | 获取ABACC预设模板列表 |
| GET | `/api/sales-script/presets/{script_id}` | 获取单个话术模板详情 |
| POST | `/api/sales-script/scripts` | 创建自定义话术模板 |
| PUT | `/api/sales-script/scripts/{script_id}` | 更新话术模板 |
| DELETE | `/api/sales-script/scripts/{script_id}` | 删除话术模板 |
| GET | `/api/sales-script/weapons/data-augmenter` | 获取数据增强器示例（类比/单位变换/对比） |
| GET | `/api/sales-script/weapons/magic-words` | 获取话术引导词推荐 |
| GET | `/api/sales-script/weapons/tension-check` | 获取张力自检评分标准 |
| POST | `/api/sales-script/weapons/analyze` | 分析话术张力并评分 |

---

## 通知与IM Bot (`notification_router.py`)

**Router:** `APIRouter(prefix="/api/notifications", tags=["通知"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/notifications/bot/test` | 测试飞书/钉钉群机器人Webhook连接 |
| POST | `/api/notifications/bot/register` | 注册新的Webhook URL |

---

## AI对话 (`chat.py`)

**Router:** `APIRouter(prefix="/api/v1/chat", tags=["AI对话"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/v1/chat` | 发送消息，获取AI回复（转发至DeepSeek） |

---

## 审计日志 (`audit.py`)

**Router:** `APIRouter(prefix="/api/v1/audit", tags=["审计日志"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/v1/audit/logs` | 获取分页审计日志 |
| GET | `/api/v1/audit/logs/user/{user_id}` | 获取指定用户的审计日志 |
| GET | `/api/v1/audit/logs/recent` | 获取最近审计日志 |
| GET | `/api/v1/audit/logs/export` | 导出审计日志（纯文本） |
| DELETE | `/api/v1/audit/logs/cleanup` | 清理审计日志 |
| GET | `/api/v1/audit/logs/stats` | 审计日志统计 |

---

## 合规审计 (`compliance.py`)

**Router:** `APIRouter(prefix="/api/compliance", tags=["合规审计"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/compliance/status` | 合规检查总体状态（通过/警告/未通过） |
| GET | `/api/compliance/report` | 完整合规报告（解析 compliance_report.md） |
| POST | `/api/compliance/scan` | 触发一次新的合规扫描 |

---

## 文件存储 (`storage_router.py`)

**Router:** `APIRouter(prefix="/api/storage", tags=["文件存储"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/storage/upload` | 上传文件（multipart/form-data, 10MB限制） |
| DELETE | `/api/storage/{path}` | 删除已上传的文件 |
| GET | `/api/storage/{path}` | 获取文件公开访问URL |

---

## 微信集成 (`wechat_router.py`)

**Router:** `APIRouter(prefix="/api/wechat", tags=["微信集成"])`

| 方法 | 路径 | 摘要 |
|------|------|------|
| POST | `/api/wechat/js-config` | 获取JS-SDK配置（wx.config()签名） |
| POST | `/api/wechat/oauth/login` | 微信网页授权登录（code → userinfo） |
| POST | `/api/wechat/miniapp/login` | 小程序code登录（code → openid/session_key） |

---

## 系统级端点 (`main.py`)

| 方法 | 路径 | 摘要 |
|------|------|------|
| GET | `/api/health` | 健康检查（含服务名和版本） |
| GET | `/health` | 健康检查（简洁版） |

### i18n 多语言路由

**来源:** `app.i18n`（非 routers/ 目录）

| 方法 | 路径 | 摘要 |
|------|------|------|
| 由 i18n_bp 注册 | - | 多语言翻译接口 |

### Feature Flags 功能开关

**来源:** `app.features`（非 routers/ 目录）

| 方法 | 路径 | 摘要 |
|------|------|------|
| 由 feature_flags_bp 注册 | - | 功能开关管理接口 |

---

## 路由文件元数据

| # | 文件名 | 行数 | 前缀 | 端点数 | 状态 |
|---|--------|------|------|--------|------|
| 1 | auth.py | 251 | `/api/auth` | 2 | 稳定 |
| 2 | brochure_bridge.py | 122 | `/api` | 3 | 稳定 |
| 3 | business_card.py | 331 | `/api/business-card` | 7 | 稳定 |
| 4 | onboarding.py | 32 | `/api/v1/onboarding` | 2 | 稳定 |
| 5 | hypothesis_gate.py | 294+ | `/api/hypothesis` | 10 | 稳定 |
| 6 | learning_center.py | 460+ | `/api/learning` | 14 | 稳定 |
| 7 | retention_insights.py | 352+ | `/api/retention` | 11 | 稳定 |
| 8 | retro_board.py | 319 | `/api/retro` | 15 | 稳定 |
| 9 | unit_economics.py | 353 | `/api/unit-economics` | 8 | 稳定 |
| 10 | matching_engine.py | 485 | `/api/matching` + `/api/v1/match` | 4 | 稳定 |
| 11 | membership.py | 171 | `/api/membership` | 4 | 稳定 |
| 12 | feedback.py | 138 | `/api/v1/feedback` | 3 | 稳定 |
| 13 | sales_script.py | 405 | `/api/sales-script` | 9 | 稳定 |
| 14 | notification_router.py | 219 | `/api/notifications` | 2 | 稳定 |
| 15 | chat.py | 107 | `/api/v1/chat` | 1 | 稳定 |
| 16 | audit.py | 217+ | `/api/v1/audit` | 6 | 稳定 |
| 17 | compliance.py | 576 | `/api/compliance` | 3 | 稳定 |
| 18 | storage_router.py | 138 | `/api/storage` | 3 | 稳定 |
| 19 | wechat_router.py | 238 | `/api/wechat` | 3 | 稳定 |
| 20 | developer_portal.py | *1025 | (存在于 D:\\链客宝, 待迁移) | 14 | 参考 |

---

## 认证方式分布

| 认证方式 | 说明 | 涉及模块 |
|----------|------|----------|
| JWT Bearer Token | 通过 `/api/auth/login` 获取 | 全局（AuthMiddleware） |
| X-API-Key Header | 开发者门户 API Key（需迁移 developer_portal） | 待实现 |
| 无认证（公开） | 健康检查、电子画册分享、名片分享 | health, brochure, share 等 |

---

## 需要 API Portal 覆盖的模块

根据现有路由结构，API 门户搭建后需重点覆盖以下能力的自助管理：

1. **API Key 自助管理** — 创建、查询、撤销、续期（参考 developer_portal.py）
2. **Webhook 订阅管理** — 创建、查询、更新、删除、测试（参考 developer_portal.py + notification_router.py）
3. **API 文档门户** — 品牌化 Swagger UI + 端点分类浏览
4. **用量统计** — 调用次数、错误率、延迟（按API Key/端点维度）
5. **开发者控制台 Dashboard** — 概览数据

---

*文档由 Hermes Agent 自动生成 | 基于 D:\\chainke-full\\backend\\app\\routers\\ 代码扫描*
