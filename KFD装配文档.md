# 链客宝 KFD 装配文档

> **Kernel → Feature → DataPack 装配蓝图**
> 版本: v1.0 | 日期: 2026-06-08 | 状态: 初稿

---

## 1. 项目概述

### 1.1 产品定位

链客宝是一个**企业家供需匹配平台**，核心使命是帮助企业家找到靠谱的合作伙伴。

- **JTBD 核心句式**: "当企业家需要找合作伙伴/供应商/客户，但缺乏靠谱的匹配渠道和信任背书时，他需要一个能精准匹配+身份认证+信任背书的对接平台"
- **目标用户**: 中小企业家、创业者、B2B服务商
- **核心价值**: 节省到处找关系的时间和踩坑的信任成本

### 1.2 KFD 装配原则

```
Kernel (内核) ← 最小可运行骨架
  ├── Feature (功能模块) ← 业务能力注入
  │     └── DataPack (数据包) ← 原子数据结构 + API
  └── 装配顺序: Phase 0 → Phase 6 (6维度全覆盖)
```

- **纯新增原则**: 每个 Feature/DataPack 装配时，不修改现有业务逻辑
- **Phase 依赖原则**: 后一 Phase 依赖前一 Phase 的内核稳定性
- **引用真实路径**: 所有 Feature/DataPack 引用代码中的真实文件路径

### 1.3 文档结构

| 章节 | 内容 |
|------|------|
| §2 | 最小内核定义 |
| §3 | 13个Feature装配清单 |
| §4 | 22个DataPack装配清单 |
| §5 | 7阶段装配步骤 |
| §6 | 6维度覆盖检查表 |
| §7 | 健康度监控指标 |
| §8 | 里程碑路线图 |

---

## 2. 最小内核 (Kernel) 定义

### 2.1 内核组件

链客宝最小内核由 **5个组件** 构成，是运行所有 Feature 的基础骨架：

```
┌─────────────────────────────────────────────────────┐
│                 API 网关 (Gateway)                    │
│    D:\chainke-full\backend\app\routers\*.py          │
├──────────┬──────────┬──────────┬──────────────────────┤
│ 用户认证  │ 企业名片  │ 基础撮合  │   数据库层           │
│ (Auth)   │ (Card)   │ (Match)  │   (Database)        │
├──────────┴──────────┴──────────┴──────────────────────┤
│                  FastAPI 应用层                        │
│         D:\chainke-full\backend\app\                  │
└──────────────────────────────────────────────────────┘
```

### 2.2 内核组件详情

| 组件 | 代码位置 | 状态 | 说明 |
|------|---------|------|------|
| **用户认证** | `D:\chainke-full\ywhy-ai-backend\api\auth.py` | ⚡ 待增强 | JWT认证，当前为mock |
| **用户认证** | `D:\chainke-full\ywhy-ai-backend\services\auth_service.py` | ⚡ 待增强 | 密码加密+令牌管理 |
| **企业名片** | `D:\chainke-full\src\pages\business-card\BusinessCardPage.tsx` | ✅ 已实现 | 名片创建/编辑/展示 |
| **企业名片组件** | `D:\chainke-full\src\pages\business-card\components\` (10组件) | ✅ 已实现 | 翻页/二维码/评价等 |
| **基础撮合** | `D:\chainke-full\src\pages\business-card\components\MatchResultsPanel.tsx` | ✅ 已实现 | AI匹配结果展示 |
| **基础撮合** | `D:\chainke-full\src\pages\business-card\api.ts` | ✅ 已实现 | 匹配API接口 |
| **数据库层** | 各router中 `list[...]` 内存存储 | 🔴 待替换 | 需迁移至PostgreSQL |
| **API网关** | `D:\chainke-full\backend\app\routers\*.py` | ✅ 已实现 | FastAPI路由 |
| **API网关** | `D:\chainke-full\ywhy-ai-backend\middleware\rate_limit.py` | ⚡ 待集成 | 限流中间件 |

### 2.3 内核启动验证

内核启动成功 = 以下5项全部通过：

```python
# 伪代码: 内核健康检查
kernel_checks = {
    "user_auth":    POST /api/auth/login      → 200 + JWT token
    "business_card": GET /api/business-card   → 200 + card data
    "basic_match":   GET /api/match           → 200 + match results
    "database":      query any table          → 200 + data
    "api_gateway":   GET /health              → 200 + {"status": "ok"}
}
```

---

## 3. Feature 装配清单 (13个)

### 3.1 Feature 索引

| # | Feature ID | 名称 | 维度 | 代码位置 | Phase |
|---|-----------|------|------|---------|-------|
| 1 | FEAT-SEC-001 | **安全加固中间件** | 体系 | `ywhy-ai-backend/middleware/rate_limit.py` | P1 |
| 2 | FEAT-ARC-001 | **架构标定与监控** | 体系 | 架构文档层 | P1 |
| 3 | FEAT-DEP-001 | **部署环境标准化** | 体系 | 运维配置层 | P1 |
| 4 | FEAT-TRUST-001 | **信任评分引擎** | 数据 | 待构建 | P2 |
| 5 | FEAT-ECON-001 | **单位经济仪表盘** | 数据 | `backend/app/routers/unit_economics.py` | P2 |
| 6 | FEAT-ECON-002 | **留存分析引擎** | 数据 | `backend/app/routers/retention_insights.py` | P2 |
| 7 | FEAT-USER-001 | **用户旅程管理** | 场景 | `backend/app/routers/learning_center.py` | P3 |
| 8 | FEAT-PROD-001 | **产品内核落地** | 场景 | `产品内核/链客宝JTBD核心句式.md` | P3 |
| 9 | FEAT-HYP-001 | **假设验证门禁** | 创造力 | `backend/app/routers/hypothesis_gate.py` | P4 |
| 10 | FEAT-GROW-001 | **增长引擎 (F1-F9复盘)** | 创造力 | `backend/app/routers/retro_board.py` | P4 |
| 11 | FEAT-CI-001 | **CI-CD流水线** | 基本功 | 运维配置层 | P5 |
| 12 | FEAT-TEST-001 | **自动化测试体系** | 基本功 | 测试配置层 | P5 |
| 13 | FEAT-VIS-001 | **视觉组件库** | 审美 | `src/components/` + `src/pages/admin/components/` | P6 |

### 3.2 Feature 详细引用

#### FEAT-SEC-001 — 安全加固中间件

```yaml
# Feature 定义 (路径: D:\chainke-full\KFD装配文档.md §3.2)
feature_id: FEAT-SEC-001
name: 安全加固中间件
dimension: 体系
code_path: D:\chainke-full\ywhy-ai-backend\middleware\rate_limit.py
injection_point: API网关层注入速率限制
assembly_phase: P1
status: 待装配
dependencies: Kernel (API网关)
```

#### FEAT-ARC-001 — 架构标定与监控

```yaml
feature_id: FEAT-ARC-001
name: 架构标定与监控
dimension: 体系
doc_path: D:\chainke-full\KFD架构标定报告.md
injection_point: 全系统架构观测
assembly_phase: P1
status: 待装配
dependencies: Kernel (所有组件)
```

#### FEAT-DEP-001 — 部署环境标准化

```yaml
feature_id: FEAT-DEP-001
name: 部署环境标准化
dimension: 体系
config_path: 待创建 (Dockerfile + docker-compose.yml)
injection_point: 基础设施层
assembly_phase: P1
status: 待装配
dependencies: Kernel (所有组件)
```

#### FEAT-TRUST-001 — 信任评分引擎

```yaml
feature_id: FEAT-TRUST-001
name: 信任评分引擎
dimension: 数据
code_path: 待构建 (建议: backend/app/routers/trust_score.py)
injection_point: 企业名片详情 + 匹配结果
assembly_phase: P2
status: 待构建
dependencies: Kernel (数据库层 + 企业名片)
```

#### FEAT-ECON-001 — 单位经济仪表盘

```yaml
feature_id: FEAT-ECON-001
name: 单位经济仪表盘 (M6)
dimension: 数据
code_path: D:\chainke-full\backend\app\routers\unit_economics.py
injection_point: /api/unit-economics/*
assembly_phase: P2
status: 已实现 (内存存储)
dependencies: Kernel (API网关 + 数据库层)
data_packs: DP-COST-001, DP-REVENUE-001, DP-CHANNEL-001, DP-METRICS-001
```

#### FEAT-ECON-002 — 留存分析引擎

```yaml
feature_id: FEAT-ECON-002
name: 留存分析引擎 (M7)
dimension: 数据
code_path: D:\chainke-full\backend\app\routers\retention_insights.py
injection_point: /api/retention/*
assembly_phase: P2
status: 已实现 (内存存储)
dependencies: Kernel (API网关 + 数据库层)
data_packs: DP-COHORT-001, DP-ACTIVITY-001, DP-CHURN-001, DP-STRATEGY-001
```

#### FEAT-USER-001 — 用户旅程管理

```yaml
feature_id: FEAT-USER-001
name: 用户旅程管理 (X1-X10 学习中心)
dimension: 场景
code_path: D:\chainke-full\backend\app\routers\learning_center.py
injection_point: /api/learning/*
assembly_phase: P3
status: 已实现 (内存存储)
dependencies: Kernel (用户认证 + API网关)
data_packs: DP-COURSE-001, DP-MODULE-001, DP-LESSON-001, DP-PROGRESS-001
```

#### FEAT-PROD-001 — 产品内核落地

```yaml
feature_id: FEAT-PROD-001
name: 产品内核落地
dimension: 场景
doc_path: D:\chainke-full\产品内核\链客宝JTBD核心句式.md
injection_point: 需求评审门禁 (D:\chainke-full\需求评审门禁_v2.md)
assembly_phase: P3
status: 已定义 (文档)
dependencies: Kernel (所有组件 — 指导所有功能决策)
```

#### FEAT-HYP-001 — 假设验证门禁

```yaml
feature_id: FEAT-HYP-001
name: 假设验证门禁 (M2)
dimension: 创造力
code_path: D:\chainke-full\backend\app\routers\hypothesis_gate.py
injection_point: /api/hypothesis/*
assembly_phase: P4
status: 已实现 (内存存储)
dependencies: Kernel (API网关 + 数据库层)
data_packs: DP-HYPOTHESIS-001, DP-EXPERIMENT-001, DP-VALIDATION-001
```

#### FEAT-GROW-001 — 增长引擎 (F1-F9复盘)

```yaml
feature_id: FEAT-GROW-001
name: 增长引擎 (F1-F9深度复盘看板)
dimension: 创造力
code_path: D:\chainke-full\backend\app\routers\retro_board.py
injection_point: /api/retro/*
assembly_phase: P4
status: 已实现 (内存存储)
dependencies: Kernel (API网关 + 数据库层)
data_packs: DP-BOARD-001, DP-RETROITEM-001, DP-ACTION-001
```

#### FEAT-CI-001 — CI-CD流水线

```yaml
feature_id: FEAT-CI-001
name: CI-CD流水线
dimension: 基本功
config_path: 待创建 (建议: .github/workflows/ci.yml)
injection_point: 代码仓库层
assembly_phase: P5
status: 待构建
dependencies: FEAT-DEP-001 (部署标准化)
```

#### FEAT-TEST-001 — 自动化测试体系

```yaml
feature_id: FEAT-TEST-001
name: 自动化测试体系
dimension: 基本功
config_path: 待创建 (建议: tests/ + pytest.ini)
injection_point: 所有路由层
assembly_phase: P5
status: 待构建
dependencies: Kernel (API网关)
```

#### FEAT-VIS-001 — 视觉组件库

```yaml
feature_id: FEAT-VIS-001
name: 视觉组件库
dimension: 审美
code_paths:
  - D:\chainke-full\src\components\TensionScoreWidget.tsx
  - D:\chainke-full\src\components\AbaccProductIntro.tsx
  - D:\chainke-full\src\pages\admin\components\TensionScoreGauge.tsx
  - D:\chainke-full\src\pages\admin\components\TensionWeaponLibrary.tsx
  - D:\chainke-full\src\pages\admin\components\AbaccEditor.tsx
injection_point: 前端页面层
assembly_phase: P6
status: 已实现
dependencies: 无 (纯前端组件)
data_packs: DP-TENSION-001, DP-ABACC-001
```

---

## 4. DataPack 装配清单 (22个)

### 4.1 DataPack 索引

| # | DataPack ID | 名称 | 所属Feature | 数据结构位置 | 字段数 |
|---|------------|------|------------|-------------|-------|
| 1 | DP-COST-001 | 成本条目 | FEAT-ECON-001 | `unit_economics.py` → `CostEntry` | 7 |
| 2 | DP-REVENUE-001 | 收入条目 | FEAT-ECON-001 | `unit_economics.py` → `RevenueEntry` | 9 |
| 3 | DP-CHANNEL-001 | 渠道经济 | FEAT-ECON-001 | `unit_economics.py` → `ChannelEconomics` | 8 |
| 4 | DP-METRICS-001 | 单位经济快照 | FEAT-ECON-001 | `unit_economics.py` → `UnitEconomicsSnapshot` | 11 |
| 5 | DP-COHORT-001 | 用户群组 | FEAT-ECON-002 | `retention_insights.py` → `Cohort` | 10 |
| 6 | DP-RETENTION-001 | 留存数据 | FEAT-ECON-002 | `retention_insights.py` → `CohortRetention` | 7 |
| 7 | DP-ACTIVITY-001 | 用户活跃 | FEAT-ECON-002 | `retention_insights.py` → `UserActivity` | 9 |
| 8 | DP-CHURN-001 | 流失信号 | FEAT-ECON-002 | `retention_insights.py` → `ChurnSignal` | 9 |
| 9 | DP-STRATEGY-001 | 留存策略 | FEAT-ECON-002 | `retention_insights.py` → `RetentionStrategy` | 7 |
| 10 | DP-COURSE-001 | 课程 | FEAT-USER-001 | `learning_center.py` → `Course` | 15 |
| 11 | DP-MODULE-001 | 课程模块 | FEAT-USER-001 | `learning_center.py` → `Module` | 10 |
| 12 | DP-LESSON-001 | 课时 | FEAT-USER-001 | `learning_center.py` → `Lesson` | 9 |
| 13 | DP-PROGRESS-001 | 学习进度 | FEAT-USER-001 | `learning_center.py` → `LearningProgress` | 12 |
| 14 | DP-TUTOR-001 | AI导师对话 | FEAT-USER-001 | `learning_center.py` → `AiTutorMessage` | 7 |
| 15 | DP-CERT-001 | 认证记录 | FEAT-USER-001 | `learning_center.py` → `Certification` | 9 |
| 16 | DP-HYPOTHESIS-001 | 商业假设 | FEAT-HYP-001 | `hypothesis_gate.py` → `Hypothesis` | 11 |
| 17 | DP-EXPERIMENT-001 | 实验设计 | FEAT-HYP-001 | `hypothesis_gate.py` → `ExperimentDesign` | 9 |
| 18 | DP-VALIDATION-001 | 验证结果 | FEAT-HYP-001 | `hypothesis_gate.py` → `ValidationResult` | 9 |
| 19 | DP-BOARD-001 | 复盘看板 | FEAT-GROW-001 | `retro_board.py` → `RetroBoard` | 10 |
| 20 | DP-RETROITEM-001 | 复盘条目 | FEAT-GROW-001 | `retro_board.py` → `RetroItem` | 8 |
| 21 | DP-ACTION-001 | 行动项 | FEAT-GROW-001 | `retro_board.py` → `ActionItem` | 10 |
| 22 | DP-SCRIPT-001 | 销售话术 | FEAT-GROW-001 | `sales_script.py` → `SalesScript` + `AbaccStep` | 10 |

### 4.2 DataPack 详细引用示例

#### DP-COST-001 — 成本条目

```yaml
# DataPack 定义 (路径: D:\chainke-full\KFD装配文档.md §4.2)
datapack_id: DP-COST-001
name: 成本条目
feature: FEAT-ECON-001 (单位经济仪表盘)
class: CostEntry
file: D:\chainke-full\backend\app\routers\unit_economics.py
injection: class CostEntry(BaseModel) 第18-26行
fields:
  - id: Optional[int]
  - name: str
  - category: str        # 市场推广/销售人力/渠道分成/工具订阅/其他
  - amount: float
  - period: str          # 月份 e.g. 2026-06
  - description: str
  - created_at: str
default_data:
  - name: "百度SEM关键词投放", amount: 25000.0, category: "市场推广", period: "2026-06"
  - name: "展会参展费用（2026上海）", amount: 35000.0, category: "市场推广", period: "2026-06"
  - name: "电销团队人力成本", amount: 48000.0, category: "销售人力", period: "2026-06"
  - name: "渠道合作伙伴分成", amount: 12000.0, category: "渠道分成", period: "2026-06"
  - name: "外呼系统月费", amount: 3000.0, category: "工具订阅", period: "2026-06"
```

#### DP-HYPOTHESIS-001 — 商业假设

```yaml
datapack_id: DP-HYPOTHESIS-001
name: 商业假设
feature: FEAT-HYP-001 (假设验证门禁)
class: Hypothesis
file: D:\chainke-full\backend\app\routers\hypothesis_gate.py
injection: class Hypothesis(BaseModel) 第18-30行
fields:
  - id: Optional[int]
  - title: str
  - description: str
  - category: str            # 增长/留存/转化/定价/产品
  - assumptions: list[str]
  - evidence_level: str      # 低/中/高
  - risk_score: Optional[int]  # 1-10
  - status: str              # 待验证/验证中/已验证/已关闭
  - tags: list[str]
  - created_at: str
  - updated_at: str
default_data:
  - title: "AI匹配推荐提升B2B获客转化率", category: "转化", status: "验证中"
  - title: "展会场景扫码即用降低获客门槛", category: "增长", status: "待验证"
  - title: "社交人脉可视化增加付费转化", category: "增长", status: "待验证"
```

*(其余18个DataPack类似结构，详见各源文件中的 BaseModel 定义)*

---

## 5. 装配步骤 (7 Phase)

### Phase 0: 内核启动验证

**目标**: 确认最小内核5组件全部可运行

| 步骤 | 操作 | 验证标准 |
|------|------|---------|
| 0.1 | 启动FastAPI应用 | `uvicorn backend.app.main:app --reload` 无报错 |
| 0.2 | 测试健康检查 | `GET /health` → 200 |
| 0.3 | 测试用户注册 | `POST /api/auth/register` → 201 + user_id |
| 0.4 | 测试用户登录 | `POST /api/auth/login` → 200 + JWT |
| 0.5 | 测试企业名片CRUD | `GET /api/business-card` → 200 |
| 0.6 | 测试基础撮合 | `GET /api/match` → 200 + 匹配列表 |
| 0.7 | 验证数据库读写 | 增删改查全链路通过 |

**输出**: `Kernel健康检查报告.md` (确认5/5组件通过)

---

### Phase 1: 体系Feature装配

**目标**: 架构/安全/部署三个体系Feature就位

| 步骤 | Feature | DataPack | 操作 |
|------|---------|----------|------|
| 1.1 | FEAT-SEC-001 | — | 装配 `rate_limit.py` 中间件到API网关 |
| 1.2 | FEAT-SEC-001 | — | 添加CORS域名白名单、HTTPS强制 |
| 1.3 | FEAT-ARC-001 | — | 创建 `KFD架构标定报告.md` 并建立架构监控看板 |
| 1.4 | FEAT-DEP-001 | — | 创建 `Dockerfile` + `docker-compose.yml` + `nginx.conf` |

**P1检查点**:
```
[✅] rate_limit中间件已注入API网关
[✅] CORS已限制为具体域名
[✅] 架构标定文档已就位
[✅] Docker部署配置已创建
```

---

### Phase 2: 数据Feature装配

**目标**: 信任评分 + 单位经济 + 留存分析

| 步骤 | Feature | DataPack | 操作 |
|------|---------|----------|------|
| 2.1 | FEAT-TRUST-001 | — | 构建信任评分引擎(新router: trust_score.py) |
| 2.2 | FEAT-ECON-001 | DP-COST-001~DP-METRICS-001 | 装配 `unit_economics.py` 路由 |
| 2.3 | FEAT-ECON-001 | DP-METRICS-001 | 连接数据库替换内存存储 |
| 2.4 | FEAT-ECON-002 | DP-COHORT-001~DP-STRATEGY-001 | 装配 `retention_insights.py` 路由 |
| 2.5 | FEAT-ECON-002 | DP-CHURN-001 | 配置流失预警通知（飞书/企微） |

**P2检查点**:
```
[✅] /api/unit-economics/* 路由已注册
[✅] /api/retention/* 路由已注册
[✅] 成本/收入数据可录入和查询
[✅] Cohort留存矩阵可展示
[✅] 流失信号可自动检测
```

---

### Phase 3: 场景Feature装配

**目标**: 用户旅程 + 产品内核

| 步骤 | Feature | DataPack | 操作 |
|------|---------|----------|------|
| 3.1 | FEAT-USER-001 | DP-COURSE-001~DP-CERT-001 | 装配 `learning_center.py` 路由 |
| 3.2 | FEAT-USER-001 | DP-TUTOR-001 | 集成AI导师问答功能 |
| 3.3 | FEAT-PROD-001 | — | 将JTBD核心句式落地到需求评审流程 |
| 3.4 | FEAT-PROD-001 | — | 创建 `需求评审门禁_v2.md` 并执行门禁 |

**P3检查点**:
```
[✅] /api/learning/* 路由已注册
[✅] X1-X10学习路径可访问
[✅] AI导师可回答用户提问
[✅] JTBD门禁已应用于需求评审
```

---

### Phase 4: 创造力Feature装配

**目标**: 假设验证 + 增长引擎

| 步骤 | Feature | DataPack | 操作 |
|------|---------|----------|------|
| 4.1 | FEAT-HYP-001 | DP-HYPOTHESIS-001 | 装配 `hypothesis_gate.py` 路由 |
| 4.2 | FEAT-HYP-001 | DP-EXPERIMENT-001~DP-VALIDATION-001 | 装配实验设计和验证结果路由 |
| 4.3 | FEAT-GROW-001 | DP-BOARD-001~DP-ACTION-001 | 装配 `retro_board.py` 路由 |
| 4.4 | FEAT-GROW-001 | DP-SCRIPT-001 | 装配 `sales_script.py` (ABACC话术引擎) |
| 4.5 | FEAT-GROW-001 | — | 创建增长飞轮看板 |

**P4检查点**:
```
[✅] /api/hypothesis/* 路由已注册
[✅] 假设→实验→验证→门禁全链路可用
[✅] /api/retro/* 路由已注册
[✅] F1-F9复盘流程可数字化执行
[✅] ABACC话术模板引擎可用
```

---

### Phase 5: 基本功Feature装配

**目标**: CI-CD + 测试

| 步骤 | Feature | 操作 |
|------|---------|------|
| 5.1 | FEAT-CI-001 | 创建 `.github/workflows/ci.yml` — 每次push自动运行测试 |
| 5.2 | FEAT-CI-001 | 创建 `.github/workflows/deploy.yml` — 自动部署到测试/生产环境 |
| 5.3 | FEAT-TEST-001 | 创建 `tests/` 目录 + `pytest.ini` |
| 5.4 | FEAT-TEST-001 | 编写API路由单元测试 (覆盖率目标 > 70%) |
| 5.5 | FEAT-TEST-001 | 编写DataPack数据模型测试 (覆盖率目标 > 80%) |

**P5检查点**:
```
[✅] CI流水线已配置 (lint + test + build)
[✅] CD流水线已配置 (自动部署)
[✅] API测试覆盖率 ≥ 70%
[✅] DataPack模型测试覆盖率 ≥ 80%
```

---

### Phase 6: 审美Feature装配

**目标**: 视觉组件 + 适配

| 步骤 | Feature | DataPack | 操作 |
|------|---------|----------|------|
| 6.1 | FEAT-VIS-001 | DP-TENSION-001 | 装配 `TensionScoreWidget.tsx` (张力评分小部件) |
| 6.2 | FEAT-VIS-001 | — | 装配 `TensionScoreGauge.tsx` (张力仪表盘) |
| 6.3 | FEAT-VIS-001 | — | 装配 `TensionWeaponLibrary.tsx` (张力武器库) |
| 6.4 | FEAT-VIS-001 | DP-ABACC-001 | 装配 `AbaccProductIntro.tsx` (产品介绍框架) |
| 6.5 | FEAT-VIS-001 | — | 装配 `AbaccEditor.tsx` (ABACC话术编辑器) |
| 6.6 | FEAT-VIS-001 | — | 响应式适配 + 暗黑模式支持 |

**P6检查点**:
```
[✅] 张力评分小部件在名片详情页可见
[✅] ABACC产品介绍框架在官网可见
[✅] 管理后台ABACC编辑器可用
[✅] 移动端适配通过
[✅] 暗黑模式切换正常
```

---

## 6. 6维度覆盖检查表

### 6.1 检查表总览

| 维度 | 必须≥1个Feature | 已装配 | 状态 |
|------|----------------|--------|------|
| 🏗️ **体系** (Architecture) | FEAT-SEC-001 / FEAT-ARC-001 / FEAT-DEP-001 | ❌ P1待做 | 🔴 |
| 📊 **数据** (Data) | FEAT-ECON-001 / FEAT-ECON-002 / FEAT-TRUST-001 | ❌ P2待做 | 🔴 |
| 🎬 **场景** (Scenario) | FEAT-USER-001 / FEAT-PROD-001 | ❌ P3待做 | 🔴 |
| 💡 **创造力** (Creativity) | FEAT-HYP-001 / FEAT-GROW-001 | ❌ P4待做 | 🔴 |
| 🛠️ **基本功** (Fundamentals) | FEAT-CI-001 / FEAT-TEST-001 | ❌ P5待做 | 🔴 |
| 🎨 **审美** (Aesthetics) | FEAT-VIS-001 | ❌ P6待做 | 🔴 |

### 6.2 逐维度过关条件

#### ✅ 维度1: 体系 (Architecture)

| 检查项 | 是否通过 | 说明 |
|--------|---------|------|
| 安全中间件已装配 | ❌ | rate_limit.py 待集成到API网关 |
| CORS白名单已配置 | ❌ | 当前为 `*` 通配 |
| 架构监控看板已建立 | ❌ | 待创建 |
| Docker部署已配置 | ❌ | 待创建 |

#### ✅ 维度2: 数据 (Data)

| 检查项 | 是否通过 | 说明 |
|--------|---------|------|
| 单位经济路由已注册 | ✅ | `unit_economics.py` 已实现 |
| 留存分析路由已注册 | ✅ | `retention_insights.py` 已实现 |
| 数据已迁移到数据库 | ❌ | 当前为内存存储 |
| 信任评分引擎已构建 | ❌ | 待构建 |

#### ✅ 维度3: 场景 (Scenario)

| 检查项 | 是否通过 | 说明 |
|--------|---------|------|
| 学习中心路由已注册 | ✅ | `learning_center.py` 已实现 |
| JTBD核心句式已定义 | ✅ | `产品内核/链客宝JTBD核心句式.md` |
| JTBD门禁已执行 | ❌ | 待应用于需求评审流程 |
| 用户旅程全链路可用 | ❌ | 学习中心未对接真实用户认证 |

#### ✅ 维度4: 创造力 (Creativity)

| 检查项 | 是否通过 | 说明 |
|--------|---------|------|
| 假设验证路由已注册 | ✅ | `hypothesis_gate.py` 已实现 |
| 复盘看板路由已注册 | ✅ | `retro_board.py` 已实现 |
| ABACC话术引擎已注册 | ✅ | `sales_script.py` 已实现 |
| 增长飞轮看板已建立 | ❌ | 待创建 |

#### ✅ 维度5: 基本功 (Fundamentals)

| 检查项 | 是否通过 | 说明 |
|--------|---------|------|
| CI流水线已配置 | ❌ | 待创建 `.github/workflows/` |
| 自动化测试已编写 | ❌ | 当前无 `tests/` 目录 |
| 测试覆盖率 ≥ 70% | ❌ | 无测试 |
| 代码规范检查已配置 | ❌ | 待配置 flake8 / ESLint |

#### ✅ 维度6: 审美 (Aesthetics)

| 检查项 | 是否通过 | 说明 |
|--------|---------|------|
| 张力评分组件已创建 | ✅ | `TensionScoreWidget.tsx` 已实现 |
| ABACC产品介绍组件已创建 | ✅ | `AbaccProductIntro.tsx` 已实现 |
| 张力仪表盘组件已创建 | ✅ | `TensionScoreGauge.tsx` 已实现 |
| 张力武器库组件已创建 | ✅ | `TensionWeaponLibrary.tsx` 已实现 |
| ABACC编辑器组件已创建 | ✅ | `AbaccEditor.tsx` 已实现 |
| 响应式适配已完成 | ❌ | 待完成 |
| 暗黑模式已支持 | ❌ | 待完成 |

### 6.3 维度覆盖雷达图 (文本)

```
                    体系 (Architecture)
                        ██
                        ░░
          审美 ███████████░████████████ 数据
          (Aesthetics)   ░░             (Data)
                        ░░
                        ░░
          基本功 ███████████░████████████ 场景
          (Fundamentals) ░░             (Scenario)
                        ░░
                        ░░
                    创造力 (Creativity)

    图例: ██ = 已实现  ░░ = 待装配
    当前: 3/6维度有代码, 0/6维度已完成装配到内核
```

---

## 7. 健康度监控指标

### 7.1 内核健康指标

| 指标 | 目标值 | 当前值 | 采集方式 |
|------|-------|-------|---------|
| 内核启动成功率 | ≥ 99.9% | — | /health 端点轮询 |
| API响应时间 P95 | ≤ 500ms | — | 请求日志 |
| 用户注册成功率 | ≥ 99% | — | 注册日志 |
| 名片CRUD成功率 | ≥ 99% | — | 操作日志 |
| 匹配请求成功率 | ≥ 99% | — | 匹配日志 |
| 数据库连接池使用率 | ≤ 70% | — | DB监控 |

### 7.2 装配进度指标

| 指标 | 目标值 | 当前值 | 计算方式 |
|------|-------|-------|---------|
| Feature装配率 | 100% (13/13) | 0% (0/13) | 已装配Feature数 / 13 |
| DataPack装配率 | 100% (22/22) | 0% (0/22) | 已装配DataPack数 / 22 |
| 6维度覆盖数 | 6/6 | 0/6 | 已通过维度数 |
| Phase完成数 | 7/7 | 0/7 | 已完成Phase数 |
| 代码→数据库迁移率 | 100% | 0% | 已迁移DataPack数 / 22 |

### 7.3 预警规则

```yaml
alerts:
  - metric: "Feature装配率"
    yellow: "< 50% (30天内)"
    red: "< 30% (60天内)"
  - metric: "维度覆盖数"
    yellow: "< 4/6 (30天内)"
    red: "< 2/6 (60天内)"
  - metric: "内核可用性"
    yellow: "< 99.5%"
    red: "< 99%"
```

---

## 8. 里程碑路线图

### 8.1 P0 — 已完成 (内核基础)

| 里程碑 | 状态 | 涉及路径 |
|--------|------|---------|
| 用户注册可运行 | ✅ 已实现 | `ywhy-ai-backend/api/auth.py` |
| 企业名片CRUD | ✅ 已实现 | `src/pages/business-card/BusinessCardPage.tsx` |
| 基础撮合匹配 | ✅ 已实现 | `src/pages/business-card/components/MatchResultsPanel.tsx` |
| FastAPI路由注册 | ✅ 已实现 | `backend/app/routers/*.py` |
| 数据模型定义 | ✅ 已实现 | 各router中 BaseModel 定义 |
| 预设样本数据 | ✅ 已实现 | 各router中 `list[...]` 初始数据 |

### 8.2 P1 — 待做 (代码改造)

| 里程碑 | 优先级 | 预估工时 | 涉及路径 |
|--------|--------|---------|---------|
| 内存存储→PostgreSQL迁移 | 🔴 P0 | 5d | 所有 `backend/app/routers/*.py` |
| 真实用户认证 (非mock) | 🔴 P0 | 3d | `ywhy-ai-backend/api/auth.py` + `services/auth_service.py` |
| 密码加盐哈希存储 | 🔴 P0 | 1d | `ywhy-ai-backend/services/auth_service.py` |
| JWT令牌管理与刷新 | 🔴 P0 | 2d | `ywhy-ai-backend/services/auth_service.py` |
| API Key 环境变量分离 | 🟡 P1 | 0.5d | `backend/.env` |
| CORS域名白名单配置 | 🟡 P1 | 0.5d | `backend/main.py:23` |
| RateLimit集成到API网关 | 🟡 P1 | 1d | `ywhy-ai-backend/middleware/rate_limit.py` |
| Docker部署配置 | 🟡 P1 | 2d | `Dockerfile` + `docker-compose.yml` |
| 前端对接真实API | 🟡 P1 | 3d | `src/pages/business-card/api.ts` + 其他前端文件 |
| 架构标定报告创建 | 🟡 P1 | 1d | `KFD架构标定报告.md` |

### 8.3 完整的装配路线时间线

```
Phase 0: 内核启动验证          [Day 1-2]   ← 当前阶段 (Kernel已就绪)
Phase 1: 体系 Feature 装配      [Day 3-7]   ← 下一个阶段
  ├── 安全加固 (SEC)            [Day 3-4]
  ├── 架构标定 (ARC)            [Day 5]
  └── 部署标准化 (DEP)          [Day 6-7]
Phase 2: 数据 Feature 装配      [Day 8-14]
  ├── 信任评分 (TRUST)          [Day 8-10]
  ├── 单位经济 (ECON-001)       [Day 11-12]
  └── 留存分析 (ECON-002)       [Day 13-14]
Phase 3: 场景 Feature 装配      [Day 15-19]
  ├── 用户旅程 (USER)           [Day 15-17]
  └── 产品内核 (PROD)           [Day 18-19]
Phase 4: 创造力 Feature 装配    [Day 20-25]
  ├── 假设验证 (HYP)            [Day 20-22]
  └── 增长引擎 (GROW)           [Day 23-25]
Phase 5: 基本功 Feature 装配    [Day 26-29]
  ├── CI-CD (CI)               [Day 26-27]
  └── 测试体系 (TEST)           [Day 28-29]
Phase 6: 审美 Feature 装配      [Day 30-33]
  └── 视觉组件库 (VIS)          [Day 30-33]
```

### 8.4 完成标准

当以下条件全部满足时，链客宝KFD装配完成：

```
[✅] 13/13 个Feature已装配到内核
[✅] 22/22 个DataPack已迁移到数据库
[✅] 6/6 个维度至少1个Feature通过检查
[✅] 7/7 个Phase全部完成
[✅] 所有Feature路由返回真实数据 (非mock)
[✅] CI-CD流水线绿色通过
[✅] 测试覆盖率 ≥ 70%
```

---

## 附录

### A. 源文件索引

| 类别 | 路径 | 说明 |
|------|------|------|
| 后端路由 | `D:\chainke-full\backend\app\routers\*.py` | 6个Feature路由 |
| 前端组件 | `D:\chainke-full\src\pages\business-card\components\*.tsx` | 名片系统10组件 |
| 管理后台 | `D:\chainke-full\src\pages\admin\*.tsx` + `components\*.tsx` | 销售话术系统 |
| 前端通用组件 | `D:\chainke-full\src\components\*.tsx` | 张力评分 + ABACC介绍 |
| 产品文档 | `D:\chainke-full\产品内核\链客宝JTBD核心句式.md` | JTBD核心句式 |
| 产品文档 | `D:\chainke-full\产品内核\内核共识清单_TEMPLATE.md` | 内核共识模板 |
| 经济模型 | `D:\chainke-full\单位经济模型仪表盘_设计文档.md` | LTV/CAC设计 |
| 战略分析 | `D:\chainke-full\ywhy-ai-backend\战略级差距分析.md` | 差距分析报告 |
| 需求管理 | `D:\chainke-full\需求评审门禁_v2.md` | 需求评审门禁 |
| 增长管理 | `D:\chainke-full\增长三周期\周期切换监控看板.md` | 增长周期看板 |
| 增长管理 | `D:\chainke-full\增长三周期\放大前自检三条件.md` | 增长自检 |
| 壁垒分析 | `D:\chainke-full\壁垒\六大伪壁垒战略评审门禁.md` | 壁垒评审 |

### B. 6维度Feature分布

| 维度 | Feature | DataPack数 | 核心文件 |
|------|---------|-----------|---------|
| 🏗️ 体系 | FEAT-SEC-001, FEAT-ARC-001, FEAT-DEP-001 | 0 | 中间件 + 配置 |
| 📊 数据 | FEAT-TRUST-001, FEAT-ECON-001, FEAT-ECON-002 | 9 | `unit_economics.py`, `retention_insights.py` |
| 🎬 场景 | FEAT-USER-001, FEAT-PROD-001 | 6 | `learning_center.py`, JTBD文档 |
| 💡 创造力 | FEAT-HYP-001, FEAT-GROW-001 | 7 | `hypothesis_gate.py`, `retro_board.py`, `sales_script.py` |
| 🛠️ 基本功 | FEAT-CI-001, FEAT-TEST-001 | 0 | CI/CD配置 |
| 🎨 审美 | FEAT-VIS-001 | 0 | 前端组件 |

### C. 术语表

| 术语 | 含义 |
|------|------|
| **Kernel (内核)** | 最小可运行骨架: 用户认证+企业名片+基础撮合+数据库层+API网关 |
| **Feature (功能模块)** | 业务能力单元，注入到内核中 |
| **DataPack (数据包)** | 原子数据结构(Data Model) + CRUD API |
| **Phase (阶段)** | 装配的顺序阶段，后一阶段依赖前一阶段 |
| **JTBD** | Jobs To Be Done，用户待完成任务 |
| **ABACC** | Attention→Before→After→Curiosity→Call Action，五步说服框架 |
| **F1-F9** | 深度复盘九步法: 目标→结果→亮点→问题→根因→经验→规律→行动→下一步 |
| **X1-X10** | 学习中心十阶段: AI导师→认知诊断→核心知识→案例→模拟→实战→互评→导师→复盘→认证 |

---

> **文档生成**: 2026-06-08 | **基于**: D:\chainke-full 代码审计 + 架构分析
> **下一步**: 创建 `D:\chainke-full\KFD架构标定报告.md` 作为 FEAT-ARC-001 的载体
