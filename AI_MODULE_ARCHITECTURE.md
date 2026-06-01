# 链客宝 AI 模块技术架构与集成方案
> 技术总监视角 · 2026-06-01

---

## 1. 现有 AI 模块架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                      统一 API 网关 (:5136)                        │
│  gateway.py: /lkapi/ → :8001, /api/match/ → :8003, ...          │
└──────┬────────────────────────────────┬─────────────────────────┘
       │                                │
       ▼                                ▼
┌──────────────────────┐    ┌──────────────────────────────┐
│ 链客宝后端 (:8001)     │    │ AI 数字名片独立服务 (:8003)   │
│ main.py (1002行)      │    │ digital_brochure_api.py    │
│                       │    │ (59KB, 28+ 路由)            │
│ AI 模块:              │    │                              │
│ ┌───────────────────┐ │    │ 独立 DB (digital_brochure.db)│
│ │ matching_engine   │ │    │ 独立模型层                    │
│ │ → /api/matching/* │ │    │ 独立 H5 前端                  │
│ │ → 类目+关键词+价格 │ │    │                              │
│ │ → 可选向量重排序   │ │    │ 路由:                        │
│ ├───────────────────┤ │    │ /api/brochure/*             │
│ │ business_card_ai  │ │    │ /api/tag/*                  │
│ │ + router          │ │    │ /api/match/*  ← 冲突!       │
│ │ → /api/card/*     │ │    │ /api/external/*             │
│ ├───────────────────┤ │    │ /api/digital-brochure/*     │
│ │ recommend.py      │ │    └──────────────────────────────┘
│ │ → /api/recommend/*│ │
│ ├───────────────────┤ │
│ │ search_index.py   │ │
│ │ → /api/search/*   │ │
│ ├───────────────────┤ │
│ │ vector_search.py  │ │    ┌──────────────────────────────┐
│ │ (默认关闭)         │ │    │ GEO 诊断服务集群              │
│ ├───────────────────┤ │    │ :5061 诊断 / :5062 定位      │
│ │ brochure_bridge   │ │    │ :5063 内容                    │
│ │ → /api/brochure/* │ │    └──────────────────────────────┘
│ └───────────────────┘ │
│                       │
│ DB: chainke.db        │
│ └ models.py           │
└──────────────────────┘
```

### 数据流路径

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐
│ 前端页面  │───▶│ 统一网关:5136 │───▶│ 后端:8001    │
│          │    │              │    │ matching_eng │
│ Product  │    │ /api/matching│    │ → query DB   │
│ Pool     │    │ → 转发到8003 │    │ → 类目/关键词 │
│          │    │ (冲突! 8001  │    │ → 向量增强*   │
│ Profile  │    │  也有匹配)   │    │              │
│ Page     │    │              │    │ DB: chainke  │
│          │    │ /api/card/*  │    │ .db          │
└──────────┘    │ → 直通8001   │    └──────────────┘
                │              │
                │ /api/match/* │    ┌──────────────┐
                │ → 转发到8003 │───▶│ 数字名片:8003 │
                │              │    │ 独立匹配逻辑  │
                │ /api/brochure│    │ 独立数据库    │
                │ / → 8001 &  │    └──────────────┘
                │    8003     │
                └──────────────┘
```

---

## 2. 路由冲突/重叠分析

### 关键冲突点

| 路径 | 8001 后端 | 8003 独立服务 | 网关处理 |
|------|-----------|---------------|----------|
| `/api/match/*` | matching_engine: 规则+关键词匹配 | 独立匹配逻辑 | → 转发到 8003 |
| `/api/brochure/*` | brochure_bridge.py: 桥接 | 数字名片主服务(28+路由) | → 转发到 8003 |
| `/api/brochures/` | 无 | 有 (前端用了s复数) | 重写 → /api/brochure/ |

**核心问题:** 
- 网关(gateway.py L43) 把 `/api/match/*` 全部转发到 :8003，导致 8001 的 matching_engine 路由 (`/api/matching/needs/{id}/products`, `/api/matching/products/{id}/needs`, `/api/matching/refresh`) **永远不会被外部访问到**。
- brochure_bridge.py (8001) 的 `/api/brochure/{user_id}` 路由因为网关同样转发到 8003，也处于"被覆盖"状态。
- 8001 内部的 brochure_bridge 路由虽然在 main.py 中注册，但通过网关访问时永远命中不了。

### 重叠影响

- **匹配引擎双轨运行**: 8003 的数字名片有自己的匹配逻辑，8001 也有 matching_engine，两套系统互不通信，匹配模型和数据不一致。
- **数据库孤岛**: 8003 使用独立的 digital_brochure.db，8001 使用 chainke.db，名片数据、匹配记录无法互通。

---

## 3. 数据库数据模型建议

### 当前缺失的表

**models.py 中不存在任何匹配记录、信任评分相关模型。**

### 建议新增模型

```python
# --- 匹配记录表 ---
class MatchRecord(Base):
    """AI供需匹配记录"""
    __tablename__ = "match_records"
    
    id = Column(Integer, primary_key=True)
    need_id = Column(Integer, ForeignKey("business_needs.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    card_id = Column(Integer, ForeignKey("business_cards.id"), nullable=True)
    score = Column(Float, nullable=False)        # 匹配分 0~1
    strategy = Column(String(16), default="v2")  # 引擎版本
    match_type = Column(String(16))              # need→product / product→need / card→match
    result_count = Column(Integer, default=0)    # 返回结果数
    elapsed_ms = Column(Integer, nullable=True)  # 耗时(ms)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- 用户反馈表 ---
class MatchFeedback(Base):
    """匹配结果用户反馈（用于质量监控）"""
    __tablename__ = "match_feedback"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_record_id = Column(Integer, ForeignKey("match_records.id"), nullable=True)
    target_type = Column(String(16))    # "product" / "need"
    target_id = Column(Integer)
    rating = Column(Integer)             # 1~5 星
    is_helpful = Column(Boolean)         # 是否标记有用
    feedback_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- 信任评分表 ---
class TrustScore(Base):
    """用户信任评分（用于匹配权重）"""
    __tablename__ = "trust_scores"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    score = Column(Float, default=0.5)          # 0~1
    deal_count = Column(Integer, default=0)     # 成交数
    response_rate = Column(Float, default=0.0)  # 响应率
    avg_rating = Column(Float, default=0.0)     # 平均评分
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 匹配引擎数据流建议

```
[用户行为] → UserEvent (已有)
[匹配请求] → MatchRecord (新增) → 写入匹配历史
[匹配结果] → MatchingEngine → 返回给前端
[用户反馈] → MatchFeedback (新增) → 用于质量监控/模型优化
[信任分]   → TrustScore (新增) → 影响匹配排序权重
```

---

## 4. 前端集成方案

### 4.1 ProductPool 接入匹配

**现状**: search.tsx (24999行) 已有搜索功能，matching_engine 匹配结果通过 `/api/matching/` 路由可用。

**方案**:
```
ProductPool 页面
├── 搜索 Tab → 现有 search_index.py (FTS5)
├── 推荐 Tab → /api/recommend/products (已有)
└── AI匹配 Tab (新增)
    └── 调用 GET /api/matching/needs/{needId}/products?strategy=v2
    └── 展示匹配分 + 匹配理由标签
```

前端需要做的：
1. 在 ProductPool 页面新增"AI匹配"Tab
2. 获取当前用户的 BusinessNeed ID 列表
3. 调用 `/api/matching/needs/{need_id}/products`
4. 展示 `match_score` + `match_reasons`（关键差异化卖点）

### 4.2 ProfilePage 接入名片

**现状**: business_card.py 路由 (`/api/card/*`) 已在 8001 注册，但无法通过网关访问（未在 gateway.py 配置）。

**方案**:
```
ProfilePage
├── 个人资料编辑
├── 名片名片管理 (新增)
│   ├── POST /api/card/scan — 上传名片扫描
│   ├── POST /api/card/generate — 生成数字名片
│   ├── GET  /api/card/{id} — 查看名片
│   └── POST /api/card/{id}/match — 触发匹配
└── 数字名片展示
    └── GET /api/brochure/{user_id} (8001 bridge)
```

**前提**: gateway.py 需要添加 `/api/card/*` → 8001 的路由。

### 4.3 网关路由修正

当前网关没有 `/api/card/*` 的路由规则，`/api/card/*` 会回退到默认路由 `→ http://localhost:8001`（L217），所以实际上是能用的，只是隐式依赖"未匹配走默认"的兜底逻辑。

但更安全的方式是显式添加：
```
("/api/card/", "http://localhost:8001", None),
```

---

## 5. 技术风险

### 风险 1: Vector Search 默认关闭
- `USE_VECTOR_SEARCH=0` 是硬编码默认值
- matching_engine 中的 `_apply_vector_bonus()` 仅在 `USE_VECTOR_SEARCH=1` 时执行
- M3E 模型启动时需下载数百 MB 模型文件，线上环境需要预下载
- **建议**: MVP 阶段保持关闭，仅用 jieba+TF-IDF

### 风险 2: matching_engine 已注册但被网关覆盖
- ✅ 已在 main.py L72/L426/L461 注册
- ❌ 网关 gateway.py L43 将 `/api/match/*` 转发到 :8003
- **影响**: 8001 的匹配引擎对前端完全不可见
- **修复**: 网关改为 `/api/match/v2/*` → 8003, `/api/matching/*` → 8001（或统一收敛）

### 风险 3: 数据库打通方案
- 8003 独立服务使用自己的 digital_brochure.db
- 8001 使用 chainke.db
- 两个数据库中的名片/业务数据无法 JOIN
- **建议方案**:
  - 短期: 8003 只存翻页图册元数据，核心业务数据仍在 chainke.db
  - 长期: 将 8003 的 brochure 模型迁移到 8001 models.py，合并数据库
  - 过渡: gateway 层做数据聚合（expensive，不推荐）

### 风险 4: brochure_bridge 路由冲突
- 8001 的 brochure_bridge 和 8003 的 brochure 路由路径相同 (`/api/brochure/`)
- 网关当前指向 8003，8001 的 bridge 被完全忽略

### 风险 5: 前端目录不存在
- `D:/链客宝/frontend/src/screens/` 未找到
- 前端可能位于其他路径或尚未完成迁移

---

## 6. MVP AI 功能技术实现路径

### Phase 0 — 基础设施修复 (1-2天)

```
□ 网关修复: gateway.py 添加 /api/card/* → 8001
□ 网关修复: 明确 /api/matching/* → 8001，/api/match/* → 8003
□ 确认前端的实际目录结构
□ 确认 8003 服务当前是否正常运行
```

### Phase 1 — 最简匹配 (3-5天)

```
1. matching_engine 已验证可工作
   └── 类目匹配(0-20) + 关键词匹配(0-40) + 价格匹配(0-40) = 满分100
   └── 权重: 类目0.3 + 关键词0.4 + 价格0.3
   └── A/B 测试: ?strategy=v1|v2

2. 新增 3 个路由在网关暴露:
   └── /api/matching/needs/{id}/products  ✅ 已有
   └── /api/matching/products/{id}/needs  ✅ 已有
   └── /api/matching/refresh             ✅ 已有

3. 前端产品池页面:
   └── 添加"AI智能匹配"按钮
   └── 调用 /api/matching/needs/{id}/products
   └── 展示匹配分(进度条) + 匹配理由(Tag)
```

### Phase 2 — OCR名片扫描 (5-7天)

```
1. business_card_ai.py 管线:
   └── scan_card() → 已有 (pdfplumber + DeepSeek OCR + Tesseract 降级)
   └── extract_fields() → 已有 (NLP 正则提取)
   └── validate_card_fields() → 已有

2. 前端 ProfilePage:
   └── 添加名片上传(拍照/选择文件)
   └── 调用 POST /api/card/scan
   └── 字段预览 + 手动修正
   └── 调用 POST /api/card/generate 保存

3. 匹配联动:
   └── POST /api/card/{id}/match → 触发供需匹配
   └── 展示匹配结果
```

### Phase 3 — 推荐 + 匹配质量 (7-10天)

```
1. recommend.py 完善:
   └── UserEvent 行为数据积累
   └── 基于浏览/搜索的协同过滤

2. 数据模型迁移:
   └── 建 MatchRecord / MatchFeedback 表
   └── matching_engine 写入匹配记录
   └── 统计引擎监控指标

3. 信任评分:
   └── TrustScore 表
   └── 匹配排序引入信任分权重
```

### Phase 4 — 向量搜索 (可选, 10-15天)

```
1. 环境变量 USE_VECTOR_SEARCH=1
2. M3E 模型预下载到 data/ 目录
3. vector_search.py 建立索引 + embedding 持久化
4. matching_engine 启用 _apply_vector_bonus()
5. search_index.py 启用 RERANK_WEIGHT
```

---

## 总结建议

| 优先级 | 事项 | 影响 |
|--------|------|------|
| P0 | 修复网关路由 (8001 vs 8003 冲突) | matching_engine 对前端不可见 |
| P0 | 确认前端目录结构 | 无法进行前端集成 |
| P1 | ProductPool 接入匹配路由 | 用户可见 MVP 功能 |
| P1 | ProfilePage 接入名片扫描 | 名片→匹配闭环 |
| P2 | 新建 MatchRecord/MatchFeedback 表 | 匹配质量监控 |
| P2 | TrustScore 信任评分 | 匹配排序优化 |
| P3 | 向量搜索启用 | 匹配精度提升 |
| P3 | 数据库合并 (8003 → 8001) | 消除数据孤岛 |
