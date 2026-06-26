# 链客宝 AI 智能维度提升 — Feature 需求清单

> 当前 AI 能力评分: **5.5 / 10**
> 目标评分: **10 / 10**
> 对标基准: 全球最佳 B2B 平台 AI 能力 (Alibaba.com AI Sourcing, Made-in-China Smart Match, ThomasNet AI, Kompass AI, Global Sources AI)

---

## 一、当前 AI 能力评估 (5.5 → 现有资产盘点)

### 已有但未产品化/未闭环的核心 AI 资产

| # | 模块 | 文件 | 状态 | 成熟度 |
|---|------|------|------|--------|
| 1 | **三塔 DNN 匹配引擎** | `ml/models/tower_ensemble.py` | ✅ 已实现，但 Feature Flag 关闭 | 算法级 |
| 2 | **用户行为塔 (Transformer)** | `ml/models/behavior_tower.py` | ✅ 已实现，未部署 | 算法级 |
| 3 | **企业特征塔** | `ml/models/enterprise_tower.py` | ✅ 已实现，未部署 | 算法级 |
| 4 | **用户 Embedding 塔** | `ml/models/user_tower.py` | ✅ Triplet Loss 训练 + 编码器 | 算法级 |
| 5 | **200+ 维特征工厂** | `ml/features/feature_factory.py` | ✅ 五类特征全覆盖 | 组件级 |
| 6 | **在线学习 (AdaGrad)** | `ml/online_learning.py` | ✅ 权重自动调优 | 组件级 |
| 7 | **知识图谱 (NetworkX)** | `ml/knowledge_graph/builder.py` | ✅ 企业关系+行业树+竞争关系 | 组件级 |
| 8 | **BGE-M3 嵌入服务** | `features/embedding_service.py` | ✅ 多语言向量编码 | 组件级 |
| 9 | **向量检索管道** | `features/retrieval_pipeline.py` | ✅ 缓存→编码→检索→降级 | 组件级 |
| 10 | **分钟级增量索引** | `ml/pipelines/minute_indexer.py` | ✅ 实时索引更新 | 组件级 |
| 11 | **跨境匹配 (中/韩/英)** | `ml/models/cross_border.py` | ✅ 多语言语义匹配 | 组件级 |
| 12 | **机会扫描 + 趋势分析** | `features/innovation_engine/` | ✅ 创新发现引擎 | 组件级 |
| 13 | **A/B 测试框架** | `ml/evaluation/champion_challenger.py` | ✅ 冠军挑战者实验 | 框架级 |
| 14 | **统计分析引擎** | `ml/evaluation/analysis_reporter.py` | ✅ 显著性检验+效应量 | 框架级 |
| 15 | **用户反馈采集** | `app/routers/feedback.py` | ✅ POST/PUT/GET 完整 | 接口级 |
| 16 | **冷启动引导** | `app/routers/onboarding.py` | ✅ 模板+三步引导 | 接口级 |
| 17 | **企业数据管道 (双源)** | `features/enterprise_data/` | ✅ 天眼查+企查查 | 数据级 |
| 18 | **MMR 多样性重排序** | `features/mmr_diversity.py` | ✅ 结果多样性优化 | 组件级 |
| 19 | **轻量匹配引擎** | `app/routers/matching_engine.py` | ✅ 关键词+完整引擎回退 | 接口级 |
| 20 | **LLM 客户端 (DeepSeek)** | `ywhy-ai-backend/services/llm_client.py` | ✅ 流式+非流式+Mock | 组件级 |
| 21 | **YAI 对话 API** | `ywhy-ai-backend/main.py` | ✅ Chat + Upload + Auth | 接口级 |
| 22 | **Feature Flag 系统** | `app/features/feature_flags.py` | ✅ 开关+百分比+白名单 | 框架级 |
| 23 | **设计评审引擎** | `features/design_review/` | ✅ 名片设计静态分析 | 组件级 |

### 核心差距: 为什么只有 5.5?

1. **一切 AI 能力 Feature Flag 全部关闭** — `new_matching_engine: false`, `cross_border: false`, `multi_language: false`
2. **前端/用户侧零感知** — 用户看到的仍是关键词匹配，DNN/向量/图谱能力未触达用户
3. **缺乏 AI 交互界面** — 无 AI 助手、无智能搜索框、无匹配解释
4. **没有闭环反馈回路** — 反馈已采集但未驱动模型实时调优
5. **算法资产沉淀在代码层** — 缺乏产品化包装和 API 端点暴露

---

## 二、Feature 需求清单 (按 P0/P1/P2)

### P0: 最小可让用户感知到的 AI 能力 (5.5 → 7.0)

这些 Feature 直接让用户 "感受到 AI 的存在"，是扭转评分的关键。

#### P0-1: AI 智能匹配结果页改版 — 展示匹配理由和置信度

- **用户故事**: 作为企业家用户，我看到匹配结果时能知道 "为什么匹配我" 以及 "匹配度有多高"
- **现状**: 匹配结果只显示 `match_score` 小数，无解释
- **方案**:
  - 后端: 在匹配 API 返回中增加 `match_reasons` (具体) 和 `confidence_label` (高/中/低)
  - 从 TowerEnsemble 的得分分解 (α=用户相似度, β=行为相似度, γ=一致性) 映射为自然语言理由
  - 前端: MatchResultsPanel 增加 "AI 匹配解释" 卡片，显示 3 条匹配理由 + 置信度仪表盘
- **工作量**: 2-3 天 (后端包装 + 前端组件)
- **对标**: Alibaba.com 的 "Why this supplier" 匹配解释

#### P0-2: 自然语言智能搜索框 (取代关键词搜索)

- **用户故事**: 我可以直接输入 "找能做汽车零部件出口韩国的中型企业" 这种自然语言描述，而不是只搜关键词
- **现状**: 只有字段关键词匹配
- **方案**:
  - 前端: 搜索框增加 NL 模式 (可通过 / 或按钮切换)
  - 后端: LLM 解析意图 → 提取行业/地域/规模/需求 → BGE-M3 向量检索 → TowerEnsemble 排序
  - 使用已有 `RetrievalPipeline` + `LLMClient`
- **工作量**: 3-5 天 (LLM prompt 工程 + 检索集成 + 前端)
- **对标**: Alibaba.com AI Sourcing Assistant

#### P0-3: 匹配反馈闭环 (点赞/点踩 → 在线学习实时生效)

- **用户故事**: 我对推荐结果点赞/点踩后，下次匹配立刻变准
- **现状**: 反馈已存数据库但未被消费; OnlineWeightOptimizer 未接入
- **方案**:
  - 后端: FeedbackService 写入后触发 `OnlineWeightOptimizer.update()`
  - 实时调整 TowerEnsemble 的 α/β/γ 权重
  - 前端: 已有的 ThumbsUp/ThumbsDown 按钮保留，增加 Toast 提示 "已为您调优"
- **工作量**: 1-2 天 (管道连接)
- **对标**: 所有推荐系统的核心闭环

#### P0-4: AI 冷启动引导 — "AI 帮您填资料"

- **用户故事**: 新注册用户输入公司名后，AI 自动填充工商信息、行业标签、业务描述
- **现状**: 冷启动只有模板选择，无 AI 填充
- **方案**:
  - 后端: 调用已有的企业数据管道 (天眼查/企查查) 通过公司名查询 → 映射到 BusinessCard 字段
  - LLM 自动生成业务简介 (根据工商经营范围)
  - 前端: 在引导流程增加 "AI 智能填充" 按钮
- **工作量**: 2-3 天 (数据管道调用 + LLM 生成 + 前端)
- **对标**: LinkedIn AI Profile Assistant

#### P0-5: 开启 Feature Flag + 产品化 API

- **用户故事**: (运营/技术) 一键开启所有已有的 AI 能力
- **现状**: `new_matching_engine: false`, `cross_border: false`
- **方案**:
  - 将 `tower_ensemble.py` 包装为 FastAPI 路由 `/api/v2/matching/predict`
  - 开启 Feature Flag (灰度 10% → 50% → 100%)
  - 为每个已有的 ML 模块增加健康检查和降级逻辑
- **工作量**: 1 天

---

### P1: 显著提升智能体验 (7.0 → 9.0)

这些 Feature 让 AI 从 "存在感" 升级为 "不可或缺的智能助手"。

#### P1-1: AI 匹配助手 (对话式交互)

- **用户故事**: 我能像跟顾问聊天一样，通过对话逐步明确需求，AI 实时推荐匹配
- **方案**:
  - 利用现有 `YAI Backend` + `LLMClient` 构建对话式匹配助手
  - Multi-turn 对话: 用户描述需求 → LLM 追问 → 结构化 intent → 检索 → 展示结果
  - 前端: 浮动聊天窗口 (类似 Intercom)
- **工作量**: 5-7 天
- **对标**: Alibaba.com AI Sourcing Assistant, Global Sources AI Match

#### P1-2: 企业画像 AI 摘要 + 智能标签

- **用户故事**: 点开一家企业时，AI 自动生成摘要、推荐合作场景、提示风险
- **方案**:
  - 后端: LLM + 知识图谱 + 企业数据 → 生成 3 段式摘要 (企业概况 / 合作亮点 / 潜在风险)
  - 自动打标签 (AI 从业务描述中提取行业/能力/资质标签)
  - 前端: 企业卡片页增加 "AI 洞察" 区域
- **工作量**: 3-5 天
- **对标**: ThomasNet AI Company Profiles

#### P1-3: 跨语言匹配前端体验 (中/韩/英)

- **用户故事**: 我输入中文需求，能看到韩国企业的匹配结果
- **现状**: `cross_border` 模块已实现但关闭; 前端无入口
- **方案**:
  - 开启 `cross_border` Feature Flag
  - 前端增加语言切换和 "跨境匹配" 入口
  - 匹配结果标注来源语言
- **工作量**: 2-3 天
- **对标**: Made-in-China 多语言匹配

#### P1-4: 智能匹配快照 + 历史趋势

- **用户故事**: 我想看到我的匹配历史变化趋势，了解 AI 是否在变准
- **方案**:
  - 后端: 聚合用户匹配历史，计算每周匹配质量指标 (平均分/反馈率/沟通转化率)
  - 前端: 个人中心增加 "AI 匹配报告" 仪表盘
- **工作量**: 2-3 天
- **对标**: LinkedIn "Your Job Match Trends"

#### P1-5: AI 主动推送 — 智能匹配通知

- **用户故事**: 不用我搜，AI 发现有新的匹配时主动通知我
- **方案**:
  - 后台分钟级索引扫描新企业/新需求
  - 匹配引擎实时跑分 → 超过阈值自动推送
  - 前端: NotificationBell 组件接收推送
- **工作量**: 3-5 天
- **对标**: Alibaba.com Smart RFQ Matching Alert

#### P1-6: 知识图谱可视化

- **用户故事**: 我能看到企业之间的关联网络 — 谁和谁竞争、谁是上下游
- **现状**: Knowledge Graph Builder 已实现，数据已就绪
- **方案**:
  - 后端: 暴露图谱查询 API (`/api/graph/enterprise/{id}/relations`)
  - 前端: 企业详情页增加 "关系图谱" Tab，使用 ECharts/D3.js 渲染
- **工作量**: 3-4 天
- **对标**: Kompass Company Network Visualization

---

### P2: 锦上添花 (9.0 → 10.0)

这些是让 AI 能力从 "优秀" 到 "卓越" 的差异化功能。

#### P2-1: AI 智能报价/询价 (RFQ) 建议

- **用户故事**: 发询价时 AI 帮我写 RFQ，收报价时 AI 帮我比较
- **方案**:
  - LLM 根据用户资料和需求自动生成标准 RFQ 模板
  - 收到多份报价后，AI 自动对比表格 (价格/交期/资质)
- **工作量**: 5-7 天
- **对标**: Global Sources RFQ AI Assistant

#### P2-2: 竞争情报 AI

- **用户故事**: 我想知道同行的供需动态、市场热点变化
- **现状**: `TrendAnalyzer` + `OpportunityScanner` 已实现
- **方案**:
  - 产品化 `InnovationEngine` 的输出
  - 运营后台展示趋势看板: 品类热度 / 供需缺口 / 新兴领域
  - 前端: 用户版精简数据看板
- **工作量**: 3-5 天
- **对标**: ThomasNet Market Intelligence

#### P2-3: 多目标匹配优化 (Relevance + Diversity + Serendipity)

- **用户故事**: 我不想只看最相关的，也想要一些 "意外发现"
- **现状**: MMR 模块已实现但未集成到主流程
- **方案**:
  - 将 MMR 集成到 TowerEnsemble 的后处理流程
  - 匹配结果按 `Relevance × (1 - λ·SimilarityToPrevious)` 重排序
  - 前端: 匹配结果增加 "探索发现" 标签
- **工作量**: 2-3 天
- **对标**: Google Discover / TikTok For You

#### P2-4: AI 名片设计评分

- **用户故事**: 我的名片设计好不好？AI 给个评分和建议
- **现状**: `CardDesignEvaluator` 已实现
- **方案**:
  - 产品化为 API `/api/v1/design/score`
  - 前端: 名片编辑页集成评分组件 + 改进建议列表
  - 比较: 使用 LLM 生成视觉设计建议
- **工作量**: 2-3 天
- **对标**: Canva AI Design Score

#### P2-5: 销售话术 AI 生成 (ABACC 框架)

- **用户故事**: 拿到匹配结果后，AI 告诉我怎么跟对方聊
- **现状**: SalesScriptPage 已有 ABACC 框架和张力武器库
- **方案**:
  - 根据匹配双方的行业/规模/需求 → LLM 自动生成个性化话术
  - 集成到匹配结果页的 "联系" 按钮后
- **工作量**: 3-4 天
- **对标**: Gong AI Sales Scripts

#### P2-6: AI 驱动的 A/B 实验自动推送

- **用户故事**: (运营) 不用手动配置实验，AI 自动决定哪个模型上线
- **现状**: ChampionChallenger 框架已实现
- **方案**:
  - 自动化: 新模型训练 → 自动创建实验 → 自动分流 → 自动统计 → 自动推送冠军
  - 运营后台增加实验看板
- **工作量**: 3-5 天
- **对标**: Netflix / Meta 的 AI 实验平台

---

## 三、对标全球最佳 B2B 平台 — 能力缺口矩阵

| AI 能力 | 链客宝现状 | Alibaba.com | Made-in-China | ThomasNet | 优先级 | 建议 |
|---------|-----------|-------------|---------------|-----------|--------|------|
| 自然语言智能搜索 | ❌ 关键词匹配 | ✅ AI Sourcing | ✅ Smart Search | ✅ AI Search | **P0** | 已有 BGE-M3 + LLM，缺包装 |
| 匹配理由解释 | ❌ 无 | ✅ "Why This Supplier" | ✅ Match Reasons | ✅ Match Quality | **P0** | TowerEnsemble 得分可分解 |
| 反馈驱动调优 | ⚠️ 已采集未用 | ✅ Implicit+Explicit | ✅ Learning Loop | ✅ | **P0** | 接 OnlineWeightOptimizer |
| AI 冷启动填充 | ❌ 仅有模板 | ✅ AI Profile Builder | ✅ Auto Fill | ✅ | **P0** | 工商数据 + LLM |
| 对话式 AI 助手 | ⚠️ YAI 后端已有 | ✅ AI Sourcing Chat | ✅ Smart Assistant | ❌ | **P1** | 包装 YAI → 匹配助手 |
| 企业 AI 摘要 | ❌ 无 | ✅ Company Insights | ✅ Enterprise Profile | ✅ | **P1** | KG + LLM 生成 |
| 跨语言匹配 | ⚠️ 引擎已有 | ✅ Multi-language | ✅ 中/英/韩 | ❌ | **P1** | 开启 Feature Flag |
| 智能推送通知 | ❌ 无 | ✅ Smart Alert | ✅ Matching Alert | ✅ | **P1** | 分钟级索引触发 |
| 知识图谱可视化 | ⚠️ Builder 已有 | ❌ | ❌ | ✅ Company Network | **P1** | NetworkX → ECharts |
| RFQ AI 辅助 | ❌ 无 | ✅ Smart RFQ | ✅ RFQ AI | ❌ | **P2** | LLM 生成 + 比较 |
| 竞争情报 | ⚠️ 引擎已有 | ❌ | ❌ | ✅ Market Intel | **P2** | InnovationEngine 产品化 |
| 多目标优化 (MMR) | ⚠️ 模块已有 | ✅ Diversified Results | ❌ | ❌ | **P2** | 集成到主流程 |
| 设计 AI 评分 | ⚠️ 模块已有 | ❌ | ❌ | ❌ | **P2** | 差异化优势 |
| 销售话术 AI | ⚠️ 框架已有 | ❌ | ❌ | ❌ | **P2** | 链客宝独有 |
| 自动 A/B 实验 | ⚠️ 框架已有 | ✅ Auto Experiment | ❌ | ❌ | **P2** | 自动化冠军推送 |
| 多模态搜索 (图片) | ❌ 无 | ✅ Image Search | ❌ | ❌ | 后置 | 依赖 GPU/模型 |
| 供应链风险 AI | ❌ 无 | ✅ | ❌ | ✅ Risk Alert | 后置 | 需外部数据源 |
| 价格预测/趋势 | ❌ 无 | ✅ Price Trends | ❌ | ❌ | 后置 | 需交易数据 |

---

## 四、实施路线图 (建议)

```
Week 1-2 (P0 · 5.5→7.0)
├── P0-1 匹配理由展示 [2d]
├── P0-2 自然语言搜索 [4d]
├── P0-3 反馈闭环 [1d]
├── P0-4 AI 冷启动填充 [2d]
└── P0-5 Feature Flag 开启 + API 产品化 [1d]

Week 3-4 (P1 · 7.0→9.0)
├── P1-1 AI 匹配助手 [5d]
├── P1-2 企业 AI 摘要 [3d]
├── P1-3 跨语言匹配前端 [2d]
├── P1-4 匹配报告看板 [2d]
├── P1-5 智能推送通知 [3d]
└── P1-6 知识图谱可视化 [3d]

Week 5-6 (P2 · 9.0→10.0)
├── P2-1 RFQ AI 辅助 [5d]
├── P2-2 竞争情报看板 [3d]
├── P2-3 MMR 多目标优化 [2d]
├── P2-4 名片 AI 评分 [2d]
├── P2-5 话术 AI 生成 [3d]
└── P2-6 自动 A/B 实验 [3d]
```

---

## 五、关键成功指标 (KSI)

| 指标 | 当前值 | P0 目标 | P1 目标 | P2 目标 |
|------|--------|---------|---------|---------|
| AI 智能评分 | 5.5 | 7.0 | 9.0 | 10.0 |
| 匹配结果点击率 | (基线) | +30% | +60% | +100% |
| 用户反馈率 | (基线) | 15% | 30% | 50% |
| 匹配后沟通转化率 | (基线) | +20% | +40% | +80% |
| 7 日留存 (新用户) | (基线) | +15% | +30% | +50% |
| NPS (AI 相关) | (基线) | 30 | 50 | 70 |

---

## 六、技术风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| BGE-M3/FlagEmbedding 依赖导致部署困难 | 中 | 高 | 已有 Mock 降级 + 回退到 TF-IDF |
| TowerEnsemble 需 PyTorch 运行时 | 中 | 中 | 不在生产环境训练，只做推理; 用 ONNX 导出 |
| LLM API 成本随用量增长 | 高 | 中 | 缓存常见查询; 用 DeepSeek (便宜); mock 模式兜底 |
| 知识图谱数据稀疏 | 中 | 低 | 从企业数据推导 + 增量式构建 |
| 多语言场景冷启动 | 低 | 低 | BGE-M3 原生支持 100+ 语言 |

---

> **结论**: 链客宝的 AI 代码资产非常丰富 (200+ 维特征 / 三塔 DNN / 知识图谱 / BGE-M3 / 在线学习 / A/B 测试框架一应俱全)，当前 5.5 分的主要原因是 **AI 能力停留在代码层，未被产品化触达用户**。通过 P0 的 5 个最小可行 Feature (约 10 个工作日) 即可将评分提升至 7.0，所有 P0 功能在现有代码资产上均可快速实现。
