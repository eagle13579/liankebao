# 链客宝 (LianKeBao)

> **企业家供需匹配平台** — 用 AI 智能匹配 + 深度服务赋能企业家高效连接供需资源

---

## 目录

- [项目简介](#项目简介)
- [架构全景](#架构全景)
- [技术栈](#技术栈)
- [功能列表](#功能列表)
- [快速启动](#快速启动)
- [项目结构](#项目结构)
- [相关文档](#相关文档)

---

## 项目简介

链客宝是一个面向企业家的 B2B 供需匹配平台，核心价值在于通过 AI 智能匹配引擎、企业数字名片、电子画册和深度服务模块，帮助企业高效连接上下游资源。

**核心能力：**
- **AI 供需匹配** — 基于三塔 DNN、MMR 多样性算法、BGE-M3 多语言嵌入的智能匹配引擎
- **数字名片** — 企业名片全生命周期管理 + AI 生成
- **电子画册** — 企业宣传画册在线生成与分享（微信小程序端集成）
- **AI 对话助手** — 基于 DeepSeek（ywhy-ai-backend）的智能对话服务
- **知识图谱** — 企业关系网络（Neo4j + NetworkX 双模式）
- **跨境匹配** — 中/韩/英多语言语义匹配
- **冷启动引导** — 三步引导 + 预设模板，降低新用户上手门槛
- **学习中心 (X1-X10)** — AI 导师到认证考核全链路
- **假设验证门禁** — 商业假设 → 实验设计 → 数据验证 → 门禁判断
- **留存洞察** — Cohort 分析 + 流失预测 + 留存策略推荐
- **深度复盘看板 (F1-F9)** — 数字化复盘方法论
- **单位经济仪表盘** — LTV/CAC/回收周期等核心指标
- **ABACC 销售话术** — 五步说服框架 + 张力武器库

---

## 架构全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户层 (React SPA)                          │
│  AIChatWidget │ NLSearchWidget │ AIMatchReasonCard │ BusinessCard   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTP / JSON
┌───────────────────────────▼─────────────────────────────────────────┐
│                    Nginx 反向代理 (80)                                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                    FastAPI 主后端 (:8001)                             │
│                                                                      │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │ 基础能力      │ │ AI匹配引擎     │ │ 深度服务模块   │ │ 辅助系统      │ │
│  │ · 数字名片    │ │ · 三塔DNN     │ │ · 学习中心    │ │ · 反馈采集    │ │
│  │ · 电子画册    │ │ · MMR多样性  │ │ · 假设验证    │ │ · 审计日志    │ │
│  │ · 认证解密    │ │ · 知识图谱    │ │ · 留存洞察    │ │ · i18n       │ │
│  │ · 冷启动引导  │ │ · 跨语言匹配  │ │ · 复盘看板    │ │ · FeatureFlag│ │
│  │ · 会员额度    │ │ · 向量检索    │ │ · 单位经济    │ │              │ │
│  │              │ │              │ │ · ABACC话术  │ │              │ │
│  └─────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  ML推理层       │  │ AI对话后端     │  │ 基础设施       │
│ · TowerEnsemble│  │ (ywhy-ai)     │  │ · SQLite       │
│ · BGE-M3       │  │ · DeepSeek    │  │ · Redis        │
│ · Embedding    │  │ · 速率限制    │  │ · Neo4j (可选) │
│ · 在线学习      │  │ · 文件上传    │  │                │
└───────────────┘  └───────────────┘  └───────────────┘
```

---

## 技术栈

### 后端
| 类别 | 技术 | 用途 |
|------|------|------|
| 框架 | **FastAPI** (Python 3.11+) | REST API |
| 运行时 | **Uvicorn** | ASGI 服务器 |
| 数据库 | **SQLite** (SQLAlchemy ORM) | 主数据存储 |
| 缓存 | **Redis** | 匹配索引、会话 |
| 验证 | **Pydantic v2** | 数据模型与验证 |
| 向量 | **BGE-M3** (FlagEmbedding) | 多语言语义嵌入 |
| 图谱 | **Neo4j** / **NetworkX** | 企业关系知识图谱 |
| ML | **PyTorch** (三塔 DNN) | 匹配模型推理 |

### 前端
| 类别 | 技术 |
|------|------|
| 框架 | **React** + TypeScript |
| 核心组件 | AIChatWidget, NLSearchWidget, AIMatchReasonCard, BusinessCardPage |

### AI 对话 (ywhy-ai-backend)
| 类别 | 技术 |
|------|------|
| 模型 | **DeepSeek** (deepseek-chat) |
| 框架 | FastAPI |
| 限流 | 中间件速率限制 (20 req/min 认证接口) |

### 部署
| 类别 | 工具 |
|------|------|
| 容器 | Docker / Docker Compose |
| 反向代理 | Nginx |
| 端口 | 后端 8001, AI后端 8100, Nginx 80 |

---

## 功能列表

### M1 - 基础能力
- [x] 企业数字名片 (CRUD + AI生成 + 数据同步)
- [x] 电子画册桥接 (微信小程序入口)
- [x] 微信小程序认证与手机号解密
- [x] 冷启动引导 (模板选择 + 三步填充)
- [x] 会员额度管理 (免费/金卡/钻石/私董会)

### M2 - AI 供需匹配
- [x] 需求匹配产品 (`GET /api/matching/needs/{need_id}/products`)
- [x] 产品匹配需求 (`GET /api/matching/products/{product_id}/needs`)
- [x] MMR 多样性匹配 (`POST /api/v1/match/diverse`)
- [x] 三塔 DNN 推理管道 (Feature Flag 控制灰度发布)
- [x] 向量检索管道 (BGE-M3 + 缓存 + TF-IDF 回退)
- [x] 知识图谱伙伴推荐 (Neo4j/NetworkX)
- [x] 跨境多语言匹配 (中/韩/英)

### M3 - AI 对话
- [x] AI 对话助手 (`POST /api/v1/chat`)
- [x] 前端 AIChatWidget 浮动组件
- [x] 会话管理 (自动 session_id)

### M4 - 深度服务模块
- [x] 学习中心 X1-X10 (课程/模块/进度/考核)
- [x] 假设验证门禁 (假设模板/实验/验证/门禁)
- [x] 留存洞察 (Cohort分析/流失预测/策略推荐)
- [x] 深度复盘看板 F1-F9 (复盘方法论数字化)
- [x] 单位经济仪表盘 (LTV/CAC/毛利率/回收周期)
- [x] ABACC 销售话术 (五步框架 + 张力武器库)

### M5 - 辅助系统
- [x] 用户反馈采集 (`POST /api/v1/feedback`)
- [x] 审计日志 (完整 CRUD + CSV 导出)
- [x] 多语言 i18n (中间件 + 翻译管理)
- [x] Feature Flag 功能开关
- [x] 在线学习 (AdaGrad 权重调优)
- [x] 冠军挑战者 A/B 测试框架

---

## 快速启动

### 前置要求
- Python 3.11+
- Node.js 18+
- Redis (可选，部分功能需要)
- Docker & Docker Compose (可选，容器部署)

### 方式一：裸机启动

```bash
# 1. 克隆仓库
git clone <repo-url> chainke-full
cd chainke-full

# 2. 启动后端 (FastAPI)
cd backend
pip install -r requirements.txt
python -m app.main
# → 服务运行在 http://localhost:8001

# 3. 启动前端 (React)
cd ../src
npm install
npm start
# → 服务运行在 http://localhost:3099

# 4. 启动 AI 对话后端 (可选)
cd ../ywhy-ai-backend
pip install -r requirements.txt
python main.py
# → 服务运行在 http://localhost:8100
```

### 方式二：Docker Compose

```bash
docker compose up -d
# → 后端 :8001, Nginx :80, Redis :6379
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `8001` | 后端服务端口 |
| `WX_APPID` | `""` | 微信小程序 AppID |
| `WX_SECRET` | `""` | 微信小程序 Secret |
| `YWHY_AI_BASE_URL` | `http://localhost:8100` | AI 对话后端地址 |

---

## 项目结构

```
chainke-full/
├── backend/                    # FastAPI 主后端
│   ├── app/                    # 应用主代码
│   │   ├── main.py             # 入口 + 路由注册
│   │   ├── database.py         # SQLite 数据库配置
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── routers/            # API 路由 (14个模块)
│   │   ├── services/           # 业务服务层
│   │   ├── features/           # Feature Flag 控制
│   │   └── i18n/               # 多语言中间件
│   ├── features/               # 高阶 Feature 模块
│   │   ├── matching_pipeline.py   # 三塔DNN推理管道
│   │   ├── feedback_service.py    # 反馈采集存储
│   │   ├── cross_border_pipeline.py # 跨境匹配
│   │   ├── knowledge_graph.py    # 知识图谱引擎
│   │   ├── retrieval_pipeline.py # 向量检索管道
│   │   ├── embedding_service.py  # BGE-M3 嵌入
│   │   ├── embedding_cache.py    # 嵌入缓存
│   │   ├── mmr_diversity.py      # MMR多样性
│   │   └── innovation_engine/    # 创新发现引擎
│   ├── ml/                     # 机器学习模块
│   │   ├── models/             # 模型定义
│   │   │   ├── tower_ensemble.py # 三塔拼接推理
│   │   │   ├── user_tower.py     # 用户特征塔
│   │   │   ├── enterprise_tower.py # 企业特征塔
│   │   │   ├── behavior_tower.py # 行为序列塔
│   │   │   └── cross_border.py   # 跨境匹配模型
│   │   ├── pipelines/          # 实时数据处理
│   │   ├── evaluation/         # 评估框架
│   │   └── online_learning.py  # 在线学习
│   ├── tests/                  # 测试套件
│   └── requirements.txt        # Python依赖
├── src/                        # React 前端
│   ├── components/             # 核心组件
│   │   ├── AIChatWidget.tsx
│   │   ├── AIMatchReasonCard.tsx
│   │   ├── NLSearchWidget.tsx
│   │   └── ...
│   └── pages/                  # 页面
├── ywhy-ai-backend/            # AI 对话后端
│   ├── main.py                 # FastAPI 入口
│   ├── api/                    # 路由 (chat, auth, upload)
│   └── middleware/             # 速率限制中间件
├── docs/                       # 项目文档
├── docker-compose.yml          # Docker 编排
├── Dockerfile                  # Docker 构建文件
├── nginx.conf                  # Nginx 配置
└── gateway.py                  # API 网关
```

---

## 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| API 文档 | `docs/api.md` | 全部 API 端点列表 |
| 更新日志 | `CHANGELOG.md` | 版本变更记录 |
| AI 需求清单 | `docs/ai-feature-requirements.md` | AI 能力提升规划 |
| 安全文档 | `SECURITY.md` | 安全策略 |

---

## 许可

Proprietary — 版权所有 © 2026 链客宝
