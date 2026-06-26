# 链客宝 更新日志 (CHANGELOG)

> 所有重要变更均记录在此文件中。
>
> 格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
> 版本管理遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## [Unreleased] — 待发布

### 规划中
- [ ] 三塔 DNN 匹配引擎灰度上线 (Feature Flag 控制)
- [ ] MMR 多样性匹配接入前端 NLSearchWidget
- [ ] 知识图谱 Neo4j 生产部署
- [ ] 向量检索管道与匹配引擎深度集成
- [ ] 在线学习权重自动调优上线
- [ ] 冠军挑战者 A/B 测试框架接入匹配排名
- [ ] 用户反馈驱动匹配闭环 (Feedback → Online Learning)

---

## [v1.0.0] — 2026-06-24

### 🚀 AI 智能推进 (2026-06-24)

本次发布标志着链客宝 AI 能力从 5.5 分向 8 分迈进的关键里程碑。多个此前仅存在于算法层的 AI 能力完成产品化封装与 API 化暴露。

#### ✨ 新增功能

- **AI 多样性匹配端点** (`POST /api/v1/match/diverse`)
  - MMR (Maximal Marginal Relevance) 算法，在保持相关性的同时最大化结果多样性
  - 支持自定义相关性分数或自动关键词匹配
  - 返回多样性评分与每项 MMR 评分
  - 可调节 diversity_weight (λ) 参数

- **AI 对话统一 API** (`POST /api/v1/chat`)
  - 前端 AIChatWidget → 后端 /api/v1/chat → ywhy-ai-backend → DeepSeek 全链路打通
  - 自动会话 ID 管理
  - 60 秒超时保护 + 502/504 降级提示

- **用户反馈采集管道** (`POST /api/v1/feedback`)
  - 文件级 JSONL 存储 (FeedbackStore)，无数据库依赖
  - 评分 1-5 + 评论文本
  - 全局统计查询 (`GET /api/v1/feedback/stats`)
  - 支持匹配 ID 关联，为后续反馈驱动学习奠定数据基础

- **冷启动引导** (`GET /api/v1/onboarding/{templates,defaults}`)
  - 6 个预设模板
  - 三步引导默认填充配置

- **三塔 DNN 推理管道** (`features/matching_pipeline.py`)
  - 懒加载单例引擎
  - 三向量余弦评分 (用户塔 × 企业塔 × 行为塔)
  - 自动回退：引擎不可用时降级到关键词匹配
  - Feature Flag 灰度控制

- **跨境匹配管线** (`features/cross_border_pipeline.py`)
  - BGE-M3 多语言嵌入 (中/韩/英)
  - 真实模型 / 模拟模式双模回退
  - 惰性加载，零额外部署依赖

- **向量检索管道** (`features/retrieval_pipeline.py`)
  - BGE-M3 编码 → EmbeddingCache → 余弦相似度检索
  - 三级降级：缓存 → 模型编码 → TF-IDF

- **知识图谱查询引擎** (`features/knowledge_graph.py`)
  - Neo4j + NetworkX 双模式
  - 自动降级：Neo4j 不可用时使用内存图
  - 三大接口：企业关系查询 / 行业地图 / 伙伴推荐

#### 🧩 新增核心前端组件

- **AIChatWidget** — 右下角浮动 AI 对话助手
- **AIMatchReasonCard** — 匹配原因可视化卡片
- **NLSearchWidget** — 自然语言搜索组件 (预备 MMR 接入)
- **TensionScoreWidget** — 张力评分展示组件

#### 🧠 深度学习模型增强

- **Three-Tower Ensemble** — 完成训练 + 推理 API + 在线学习权重优化
  - UserTower (用户 Embedding，Triplet Loss 训练)
  - EnterpriseTower (企业特征编码器)
  - BehaviorTower (行为序列 Transformer)
  - OnlineWeightOptimizer (AdaGrad 在线调优)
- **Champion/Challenger A/B 测试框架** (`ml/evaluation/`)
  - 统计显著性检验
  - 效应量计算 (Cohen's d)
  - 自动化实验报告

#### 🏗️ 新增后端模块

- **学习中心 (X1-X10)** — 课程/模块/进度/AI导师/考核认证全链路 API
- **假设验证门禁** — 商业假设 CRUD + 实验设计 + 验证结果 + 门禁判断
- **留存洞察** — Cohort 分析 + 用户分群 + 流失信号 + 留存策略推荐
- **深度复盘看板 (F1-F9)** — 目标回顾 → 行动规划 全流程数字化
- **单位经济仪表盘** — LTV/CAC/回收周期/毛利率等核心指标
- **会员额度管理** — 四等级额度 + 402 检查
- **ABACC 销售话术** — 五步说服框架 + 张力武器库
- **审计日志系统** — 完整 CRUD + CSV 导出 + 清理

#### 🔧 技术优化

- i18n 多语言中间件集成
- Feature Flag 功能开关系统 (支持灰度发布)
- 企业数据管线 (天眼查/企查查适配器)
- 分钟级增量索引 (minute_indexer)
- 实时数据同步 (realtime_sync)
- 设计审核引擎 (brand_checker, card_design_evaluator)

#### 📚 文档

- 新增 `README.md` — 项目总览 + 架构全景 + 快速启动
- 新增 `CHANGELOG.md` — 版本变更记录
- 新增 `docs/api.md` — 完整 API 端点文档
- 新增 `docs/ai-feature-requirements.md` — AI 智能维度提升规划

---

## [v0.9.0] — 2026-06-10

### ✨ 新增
- 企业数字名片 API (CRUD + AI 生成)
- 电子画册桥接模块 (微信小程序集成)
- 微信小程序认证与手机号解密
- 企业数据采集管线 (天眼查/企查查)

### 🔧 修复
- 画册桥接引用不存在的 CardProfile 模型 → 修正为 BusinessCard
- 数据同步钩子 (铁律九十二) `sync_brochure_from_card`

---

## [v0.8.0] — 2026-05-28

### ✨ 新增
- FastAPI 后端骨架搭建
- SQLite + SQLAlchemy ORM 初始化
- CORS、健康检查端点
- Docker / Docker Compose 编排
- Nginx 反向代理配置

---

## [v0.1.0] — 2026-04-15

### ✨ 初始版本
- 项目初始化
- React 前端脚手架
- 基本项目结构搭建

---

[Unreleased]: https://github.com/yourorg/chainke/compare/v1.0.0...HEAD
[v1.0.0]: https://github.com/yourorg/chainke/releases/tag/v1.0.0
[v0.9.0]: https://github.com/yourorg/chainke/releases/tag/v0.9.0
[v0.8.0]: https://github.com/yourorg/chainke/releases/tag/v0.8.0
[v0.1.0]: https://github.com/yourorg/chainke/releases/tag/v0.1.0
