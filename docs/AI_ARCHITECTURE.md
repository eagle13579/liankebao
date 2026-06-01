# 链客宝 AI原生企业信任关系网 — 顶层架构设计

> 编写日期: 2026-06-01 | 版本: v1.0 | 架构师视角

---

## 一、五层架构设计（接入层→调度层→执行层→值守层→机械层）

```
┌─────────────────────────────────────────────────────────┐
│  ① 接入层 (Access Layer)        用户触点 + API 网关    │
│  小程序 / H5 / 企业微信 / 公开分享 / OpenAPI            │
├─────────────────────────────────────────────────────────┤
│  ② 调度层 (Orchestration Layer)    AI 路由 + 策略引擎  │
│  路由分发 / Feature Flags / A/B测试 / LLM Cost Control  │
├─────────────────────────────────────────────────────────┤
│  ③ 执行层 (Execution Layer)      AI 能力执行单元        │
│  名片OCR / 向量搜索 / 匹配引擎 / 推荐引擎 / 信任评分    │
├─────────────────────────────────────────────────────────┤
│  ④ 值守层 (Watchdog Layer)       熔断 + 降级 + 监控    │
│  Circuit Breaker / 重试引擎 / 健康检查 / 指标收集       │
├─────────────────────────────────────────────────────────┤
│  ⑤ 机械层 (Persistence Layer)    数据持久化 + 索引     │
│  MySQL/SQLite / SQLite FTS5 / 向量索引 / Redis(规划)    │
└─────────────────────────────────────────────────────────┘
```

### ① 接入层（现状 → 目标）
- **现状**: FastAPI 网关 (gateway.py:11938行) + RateLimitMiddleware + 多终端（小程序/Web/H5）
- **升级**: 增加 AI 原生路由策略 —— 根据请求上下文自动选择 AI 版本（v1 规则引擎 / v2 向量增强）
- **新增入口**: AI名片分享链接 → 信任指数展示 → 一键对接触发

### ② 调度层（核心新增）
负责 AI 请求的编排和策略决策：
- **A/B 测试框架** (`matching_engine.py` 已有 `?strategy=v1|v2`)
- **Feature Flags** (`feature_flags.py` 已注册) — 控制AI功能灰度发布
- **LLM Cost Controller** (`llm_cost_controller` 已加载) — LLM 调用配额和预算管理
- **AI Router**（新增）— 根据用户画像、上下文、负载，智能路由到不同AI能力

### ③ 执行层（现有AI能力聚合）

| 模块 | 文件 | 功能 | 等级 |
|------|------|------|------|
| 名片OCR | `business_card_ai.py` | OCR提取→NLP字段提取→数字名片生成 | L2 |
| 向量搜索 | `vector_search.py` | M3E/OpenAI/DeepSeek Embedding + 语义搜索 | L2 |
| FTS搜索 | `search_index.py` | jieba分词 + FTS5全文检索 + 高亮 | L1 |
| 供需匹配 | `matching_engine.py` | 类目+关键词+价格+向量增强匹配 | L2 |
| 推荐引擎 | `recommend.py` | 行为协同过滤 + 热门兜底 | L1 |
| 企业爬虫 | `enterprise_crawler.py` | 公开渠道企业信息采集 | L2 |
| 信任评分 | （规划） | 企业信用+行为+好友链综合评分 | L3 |

### ④ 值守层（已具备，需强化AI专项）
- `circuit_breaker.py` — 熔断器已注册
- `retry_engine.py` — AI调用重试（指数退避）
- `observability.py` — 请求级指标收集
- `slow_query_warning.py` — 慢查询告警
- **新增**: AI 能力健康检查 + 自动切换降级路由

### ⑤ 机械层
- MySQL/SQLite — 业务主库（User/Product/Order/BusinessNeed/BusinessCard/UserEvent）
- SQLite FTS5 — 全文搜索索引（`search_index.py`）
- SQLite 向量索引 — `vector_index.db`（`vector_search.py` 持久化）
- **规划**: Redis 缓存层（匹配结果缓存 + 热点数据）

---

## 二、数据流全景

```
用户上传名片/照片
     │
     ▼
┌─────────────────┐    ┌──────────────────┐
│ ① 名片数据管道   │    │ ② 信任评分管道    │
│                 │    │                  │
│ scan_card()     │    │ 企业信息采集      │
│   ↓             │    │ (enterprise_     │
│ extract_fields()│    │  crawler.py)     │
│   ↓             │    │   ↓              │
│ generate_       │    │ 工商数据校验      │
│ digital_card()  │    │   ↓              │
│   ↓             │    │ 行为数据聚合      │
│ 存入 BusinessCard│    │ (UserEvent)      │
│ 表               │    │   ↓              │
│   ↓             │    │ 信任评分计算      │
│ match_supply_   │    │ (TrustScore —    │
│ demand() 触发    │    │  规划中)          │
│   ↓             │    │   ↓              │
└─────────────────┘    └──────────────────┘
        │                       │
        ▼                       ▼
┌──────────────────────────────────────────────┐
│ ③ 匹配推荐管道                                │
│                                              │
│ MatchingEngine.match_needs_to_products()     │
│   → 类目匹配 (0~40分)                         │
│   → 关键词匹配 TF-IDF (0~40分)                │
│   → 价格区间匹配 (0~20分)                     │
│   → 向量语义增强 (0~20分, 可选)               │
│   → 信任加权 (0~10分, 规划)                   │
│   → 总分归一化 0.0~1.0                        │
│                                              │
│ RecommendEngine.recommend_products()          │
│   → 行为协同 (看过同类产品的也看)              │
│   → 热门兜底                                 │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ ④ 成交闭环管道                                │
│                                              │
│ 对接请求 → 联系方式交换 → 商机创建             │
│   → Order 下单 → 支付 (wxpay/alipay)          │
│   → 成交数据回流 → 更新信任评分                │
│   → 行为事件沉淀 (UserEvent)                   │
│   → 反馈优化匹配模型                           │
└──────────────────────────────────────────────┘
```

### 关键数据实体依赖

| 实体 | 表名 | 被哪些AI模块消费 |
|------|------|-----------------|
| User | users | 全部AI模块 |
| Product | products | MatchingEngine, SearchIndex, Recommend |
| BusinessNeed | business_needs | MatchingEngine |
| BusinessCard | business_cards | card_ocr → match_supply_demand |
| UserEvent | user_events | Recommend, TrustScore |
| Contact | contacts | 信任关系网基础 |

---

## 三、AI能力分层

### L1 — 基础层（搜索+推荐）
| 能力 | 状态 | 技术栈 | 降级方案 |
|------|------|--------|---------|
| 全文搜索 | ✅ 已上线 | jieba+FTS5+memory | memory→fts5→auto |
| 热门推荐 | ✅ 已上线 | SQL聚合+行为统计 | 兜底: 最新产品排序 |
| 搜索建议 | ✅ 已上线 | 前缀匹配 | 无 |
| 首页功能排序 | ✅ 已上线 | 痛点标签映射 | 默认排序 |

### L2 — 核心层（名片OCR+匹配）
| 能力 | 状态 | 技术栈 | 降级方案 |
|------|------|--------|---------|
| 名片OCR扫描 | ⚠️ 半上线 | pdfplumber + Tesseract + DeepSeek Vision(规划) | pdfplumber→Tesseract→手动输入提示 |
| NLP字段提取 | ✅ 已上线 | 正则规则引擎 | 全部字段返回None |
| 数字名片生成 | ✅ 已上线 | JSON结构化 | — |
| 供需匹配(v1) | ✅ 已上线 | 规则引擎+TF-IDF | 类目匹配兜底 |
| 供需匹配(v2) | ✅ 已上线 | 向量增强+TF-IDF加权余弦 | 回退v1 |
| 向量搜索 | ⚠️ 半上线 | M3E/OpenAI/DeepSeek | numpy模拟→关闭 |
| 企业信息采集 | ✅ 已上线 | requests+BeautifulSoup+降级链 | urllib+re兜底 |

### L3 — 高级层（信任评分+智能推荐）
| 能力 | 状态 | 技术栈 | 降级方案 |
|------|------|--------|---------|
| 信任评分 | 📅 P2规划 | 多维度加权 | 默认评分0.5 |
| 智能推荐 | 📅 P2规划 | 向量召回+行为排序 | 降级L1热门推荐 |
| AI名片分析 | 📅 P2规划 | LLM语义分析 | 规则引擎降级 |
| 关系图谱 | 📅 远期 | Neo4j/图数据库 | — |

> 图例: ✅已上线 ⚠️半上线（需接通API Key） 📅规划中

---

## 四、模块依赖图

```
┌────────────────────────────────────────────────────────────────────┐
│                      模块依赖关系（箭头指向被依赖方）                │
└────────────────────────────────────────────────────────────────────┘

business_card_router ──→ business_card_ai (scan/extract/generate/match)
                            │
                            ├──→ matching_engine (match_supply_demand)
                            │       ├──→ app.models (Product, BusinessNeed)
                            │       ├──→ app.database (get_db)
                            │       ├──→ jieba (分词)
                            │       └──→ app.vector_search (可选向量增强)
                            │               ├──→ sentence-transformers/M3E
                            │               ├──→ OpenAI/DeepSeek API (可选)
                            │               └──→ SQLite (vector_index.db)
                            │
search_router ──→ search_index (MemorySearchEngine / FTS5SearchEngine)
                    ├──→ jieba (分词)
                    ├──→ app.models (Product)
                    └──→ app.vector_search (向量重排序, 可选)

recommend_router ──→ app.models (Product, UserEvent)
                    └──→ app.database (get_db)

enterprise_crawler ──→ requests (外部HTTP)
                     └──→ BeautifulSoup (HTML解析, 可选)

observability ──→ circuit_breaker ──→ retry_engine
feature_flags ──→ llm_cost_controller

AI模块共同依赖:
  ├── app.database (数据库会话)
  ├── app.models (ORM数据模型)
  ├── app.auth (用户认证)
  └── app.telemetry (OpenTelemetry追踪)
```

### 核心数据库依赖矩阵

| AI模块 | users | products | business_needs | business_cards | user_events | contacts | 向量索引DB |
|--------|-------|----------|----------------|----------------|-------------|----------|------------|
| 名片OCR | R/W | — | — | R/W | — | — | — |
| 供需匹配 | R | R | R | R | — | — | R(可选) |
| 全文搜索 | — | R | — | — | — | — | R(可选) |
| 推荐引擎 | R | R | — | — | R | — | — |
| 信任评分* | R | R | R | R | R | R | — |

① R=读取 W=写入 *=规划中

---

## 五、演进路线图

### P0 — 现有AI能力唤醒（1-2周）🔴

| 任务 | 涉及文件 | 优先级 |
|------|---------|--------|
| 1. DeepSeek Vision OCR 正式接入 | `business_card_ai.py:103` | P0 |
| 2. 向量搜索默认开启 (USE_VECTOR_SEARCH=1) | `vector_search.py` + `.env` | P0 |
| 3. M3E 模型预下载 + Docker集成 | `Dockerfile` + `vector_search.py` | P0 |
| 4. 匹配引擎缓存+单元测试补齐 | `matching_engine.py` + `test_matching_engine.py` | P0 |
| 5. 搜索索引重建定时任务 | `search_index.py` → cron/apscheduler | P0 |
| 6. 企业爬虫错误处理加固 | `enterprise_crawler.py` | P0 |

### P1 — AI能力统一（2-4周）🟡

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 1. AI能力统一入口 `/api/ai/*` | 整合card/匹配/搜索/推荐到统一AI网关 | P1 |
| 2. 匹配引擎接入向量搜索默认开 | `matching_engine.py` 正式依赖vector_search | P1 |
| 3. 同义词配置化 | 行业同义词库 → 提升匹配recall | P1 |
| 4. 匹配质量监控面板 | 匹配准确率/召回率/KPI仪表盘 | P1 |
| 5. AI路由熔断+降级策略全链路 | 任何AI模块故障自动降级 | P1 |
| 6. A/B测试框架完整化 | v1/v2/v3策略可配置，数据回传 | P1 |

### P2 — AI原生体验全面上线（4-8周）🟢

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 1. 信任评分引擎 (TrustScore) | 企业工商 + 交易行为 + 人脉链 → 综合评分 | P2 |
| 2. 智能推荐升级 (向量召回) | `recommend.py` 接入向量语义匹配 | P2 |
| 3. AI名片分析增强 | LLM分析名片→自动生成企业画像→推荐匹配 | P2 |
| 4. 以图搜图（名片/产品） | 视觉embedding → 跨模态搜索 | P2 |
| 5. AI对沟通辅助 | 供需双方AI撮合 → 自动生成对接话术 | P2 |
| 6. 关系图谱可视化 | 人脉→企业→交易链路可视化 | 远期 |

---

## 六、风险与控制

### 可用性风险矩阵

| 风险 | 概率 | 影响 | 等级 | 控制措施 |
|------|------|------|------|---------|
| LLM API 超时/限流 | 中 | 高 | 🔴 | 熔断 → 重试(3次) → 降级到规则引擎 |
| M3E 模型OOM | 低 | 高 | 🟡 | 惰性加载 + 进程级内存限制 |
| Tesseract OCR 不可用 | 中 | 中 | 🟡 | 降级到 pdfplumber → 手动输入提示 |
| 向量索引损坏 | 低 | 中 | 🟡 | 自动重建 + SQLite WAL模式 |
| High负载下匹配慢 | 中 | 中 | 🟡 | LRU缓存(60s TTL) + 分页 |
| 企业爬虫被封 | 中 | 低 | 🟢 | UA轮换 + 请求间隔 + 缓存 |

### 降级策略总表

```
正常流程                             降级路径
─────────────────────────────────────────────────────
M3E Embedding ────→ Numpy模拟Embedding ────→ 关闭向量搜索
DeepSeek Vision ──→ Tesseract OCR ────→ 手动输入提示
向量匹配增强 ──────→ v2 TF-IDF匹配 ────→ v1规则匹配
个性化推荐 ────────→ 协同过滤 ────→ 热门推荐
AI信任评分 ────────→ (规划) ────→ 默认评分0.5
```

### 关键控制指标（SLO）

| 指标 | 目标 | 告警阈值 |
|------|------|---------|
| 名片OCR成功率 | ≥95% | <90%持续5分钟 |
| 匹配API P99延迟 | <500ms | >1s |
| 向量搜索P99延迟 | <300ms | >800ms |
| AI模块可用率 | ≥99.5% | <99% |
| 降级触发频率 | <0.1%请求 | >1%请求 |

### 上线检查清单

- [ ] 所有AI模块都有熔断器（`circuit_breaker.py`）
- [ ] 所有外部API调用有超时控制（已验证: `enterprise_crawler.py` 15s超时）
- [ ] 所有AI模块有健康检查端点（`/health/ai` 新增）
- [ ] 降级路径经过自动化测试验证
- [ ] Embedding模型预热（M3E首次加载约5-10s，容器启动时预加载）
- [ ] LLM Cost Controller 配额配置（防预算失控）

---

## 现有AI能力清单（已审计）

```
文件                                    行数    状态    等级
─────────────────────────────────────────────────────────
backend/app/business_card_ai.py        1094    ✅ 可用  L2
backend/app/vector_search.py           1072    ⚠️ 需配API L2
backend/app/search_index.py            1237    ✅ 可用  L1
backend/matching_engine.py              878    ✅ 可用  L2
backend/app/routers/recommend.py        314    ✅ 可用  L1
backend/app/routers/business_card.py    734    ✅ 可用  L2
backend/app/enterprise_crawler.py       580    ✅ 可用  L2
backend/app/enterprise.py                ?     ✅ 可用  L2
backend/app/feature_flags.py             ?     ✅ 可用  调度
backend/app/circuit_breaker.py           ?     ✅ 可用  值守
backend/app/retry_engine.py              ?     ✅ 可用  值守
backend/app/observability.py             ?     ✅ 可用  值守
backend/app/llm_cost_controller.py       ?     ✅ 可用  调度
─────────────────────────────────────────────────────────
总计: ~5,900+ 行 AI相关代码
```
