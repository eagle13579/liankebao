# 盖娅商业 — AI数智军团即服务
## 全景架构框架 (Panoramic Architecture Framework)

> 逆向工程版本: v1.0
> 来源: https://gaia-commercial.vercel.app/workbench
> 技术栈: Next.js + Vercel + Tailwind CSS (Dark Theme)
> 生成日期: 2026-06-16

---

## 1. 顶层架构框架 (Top-Level Architecture)

### 产品定位

> **盖娅商业 (Gaia Business) — AI数智军团即服务**
>
> 一站式AI驱动企业数智化工作台，以"蜂巢式部门军团"为原子单元，为中小出海企业提供合规、情报、法务、财务等9大AI数智部门即开即用，按需订阅。

### 三层架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                        UI LAYER (表现层)                             │
│                                                                      │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│  │ 🛡️   │ │ 🔍   │ │ 📢   │ │ ⚖️   │ │ 💰   │ │ 🧠   │ │ ⚙️   │  │
│  │合规部 │ │情报部 │ │市场部 │ │法务部 │ │财务部 │ │战略部 │ │技术部 │  │
│  │免费   │ │标准   │ │标准   │ │专业   │ │专业   │ │专业   │ │标准   │  │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘  │
│  ┌──────┐ ┌──────┐                                                  │
│  │ 🎨   │ │ 📊   │     [9 Department Panels]                        │
│  │设计部 │ │运营部 │                                                  │
│  │标准   │ │标准   │                                                  │
│  └──────┘ └──────┘                                                  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │  共享功能区 (Shared Feature Bar)                          │       │
│  │  📁 文件库 0  |  📋 公告板  |  📜 政策简述              │       │
│  └──────────────────────────────────────────────────────────┘       │
├──────────────────────────────────────────────────────────────────────┤
│                     FEATURE LAYER (功能层)                           │
│                                                                      │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────────┐    │
│  │ DepartmentPanel│  │  HiveMeeting    │  │    ChatWindow        │    │
│  │ • Header+emoji │  │ • 状态指示器    │  │ • 消息输入框         │    │
│  │ • 定价标签     │  │ • 参与者列表    │  │ • 快速问题(3个/部门) │    │
│  │ • 员工列表     │  │ • 话题卡片      │  │ • 员工头像快捷栏     │    │
│  │ • 展开/折叠    │  │ • 🟢进行中标识  │  │ • AI上下文感知       │    │
│  └──────────────┘  └────────────────┘  └──────────────────────┘    │
│                                                                      │
│  ┌──────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │  BulletinBoard    │  │  EmployeeCard  │  │  PolicyBriefCard   │   │
│  │ • 部门话题卡片    │  │ • 表情头像     │  │ • 标题             │   │
│  │ • 🤖 AI刷新按钮  │  │ • 中文姓名     │  │ • 摘要             │   │
│  │ • 政策简述嵌入    │  │ • 职务头衔     │  │ • 分类标签         │   │
│  │ • 实时更新        │  │ • 🟢在线状态   │  │ • 跨部门共享       │   │
│  └──────────────────┘  └────────────────┘  └────────────────────┘   │
├──────────────────────────────────────────────────────────────────────┤
│                      DATA LAYER (数据层)                             │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                  Knowledge Base (知识库)                    │     │
│  │  • 部门专属知识: 合规法规库 / 市场情报库 / 法务案例库     │     │
│  │  • 跨部门共享: 政策简述库 / 行业动态库                    │     │
│  │  • AI训练数据: 对话历史 / 快速问答对 / 公告内容           │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                                                      │
│  ┌─────────────────────┐  ┌───────────────────┐                    │
│  │  Policy Briefs       │  │  File Library      │                    │
│  │  (政策简述·全部门共享) │  │  (文件库·部门隔离)  │                    │
│  │  • 新规速递          │  │  • 按部门归类       │                    │
│  │  • 行业动态          │  │  • 文档管理         │                    │
│  └─────────────────────┘  └───────────────────┘                    │
└──────────────────────────────────────────────────────────────────────┘
```

### 架构核心原则

| 原则 | 说明 |
|------|------|
| **蜂巢同构 (Hive Homogeneity)** | 9个部门共享同一套组件模式，仅在数据和定价层级上差异化 |
| **按需订阅 (Tiered Access)** | 免费/标准/专业三级定价，决定可解锁的部门范围 |
| **AI驱动 (AI-Native)** | 每个部门的聊天、公告、快速问题均由AI生成和响应 |
| **跨部门共享 (Cross-Dept Sharing)** | 政策简述为全局共享，文件库按部门隔离 |

---

## 2. 部门Feature矩阵 (Department Feature Matrix)

### 2.1 Feature覆盖矩阵

| 部门 | 定价层级 | 员工配置 | 蜂巢会议 | AI聊天 | 快速问题 | 公告板 | 文件库 |
|:----|:--------:|:--------:|:--------:|:------:|:--------:|:------:|:------:|
| 🛡️ 合规部 | 免费 | ✅ 3人 | ✅ 🟢进行中 | ✅ | ✅ 3条 | ✅ | ✅ 0 |
| 🔍 情报部 | 标准 | ✅ 3人 | ✅ 🟢进行中 | ✅ | ✅ 3条 | ✅ | ✅ 0 |
| 📢 市场部 | 标准 | ✅ 3人 | ✅ 🟢进行中 | ✅ | ✅ 3条 | ✅ (暂无) | ✅ 0 |
| ⚖️ 法务部 | 专业 | ✅ (未展开) | ✅ | ✅ | ✅ | ✅ | ✅ 0 |
| 💰 财务部 | 专业 | ✅ (未展开) | ✅ | ✅ | ✅ | ✅ | ✅ 0 |
| 🧠 战略部 | 专业 | ✅ (未展开) | ✅ | ✅ | ✅ | ✅ | ✅ 0 |
| ⚙️ 技术部 | 标准 | ✅ (未展开) | ✅ | ✅ | ✅ | ✅ | ✅ 0 |
| 🎨 设计部 | 标准 | ✅ (未展开) | ✅ | ✅ | ✅ | ✅ | ✅ 0 |
| 📊 运营部 | 标准 | ✅ (未展开) | ✅ | ✅ | ✅ | ✅ | ✅ 0 |

### 2.2 Feature共享性分析

| 维度 | 部门特有 (Department-Specific) | 跨部门共享 (Shared Across Depts) |
|:----|:-----------------------------:|:-------------------------------:|
| **员工数据** | 每个部门3名AI员工，姓名/职务均不同 | — |
| **蜂巢会议** | 话题内容随部门类型变化 | 会议状态UI模式共享 |
| **AI聊天** | 上下文绑定部门知识库 | 聊天组件UI完全复用 |
| **快速问题** | 问题内容由部门类型决定 | 3条固定结构复用 |
| **公告板** | 话题内容部门专属 | 组件模式、AI刷新机制共享 |
| **文件库** | 文件按部门隔离存储 | 计数显示组件复用 |
| **政策简述** | — | ✅ **全局共享**：所有部门看到相同两条政策 |
| **定价展示** | 免费/标准/专业标签 | 标签样式组件复用 |

### 2.3 按定价层级可见的Feature

| Feature | 免费(合规部) | 标准(5部门) | 专业(3部门) |
|:--------|:----------:|:----------:|:----------:|
| 部门面板 | ✅ (1个) | ✅ (6个) | ✅ (9个) |
| 蜂巢会议 | ✅ | ✅ | ✅ |
| AI聊天 | ✅ | ✅ | ✅ |
| 快速问题 | ✅ | ✅ | ✅ |
| 公告板 | ✅ | ✅ | ✅ |
| 文件库 | ✅ (受限) | ✅ | ✅ |
| 政策简述 | ✅ | ✅ | ✅ |
| 全部员工可见 | ✅ | ✅ | ✅ |
| 高价值部门解锁 | ❌ | ❌ | ✅ (法务/财务/战略) |

---

## 3. 通用组件模式提取 (Common Component Patterns)

### 3.1 DepartmentPanel (部门面板)

```
┌──────────────────────────────────────────────────┐
│ 🛡️ 合规部                          [免费]  [↗]  │  ← Header + Tier Badge
│                                                  │
│ ┌────────────────┐  ┌────────────────┐          │
│ │ 徐准            │  │ 宰贤            │          │  ← Employee Cards
│ │ 合规总监        │  │ 知识产权专员    │          │    (emoji + name + title)
│ │ 🟢              │  │ 🟢              │          │
│ └────────────────┘  └────────────────┘          │
│ ┌────────────────┐                               │
│ │ 意恒            │                               │
│ │ 合规工程师      │                               │
│ │ 🟢              │                               │
│ └────────────────┘                               │
│                                                  │
│  [展开部门详情 ▾]                                 │  ← Expand/Collapse
└──────────────────────────────────────────────────┘
```

**Props Interface (推测):**
```typescript
interface DepartmentPanelProps {
  department: Department;
  isExpanded: boolean;
  onToggle: (id: string) => void;
  tier: 'free' | 'standard' | 'pro';
}
```

**状态管理:**
- 展开/折叠: 局部状态 (useState)
- 员工数据: 从全局 departments 数据中按 ID 提取
- 定价标签: 按 tier 属性渲染不同样式 (免费=绿, 标准=蓝, 专业=紫)

---

### 3.2 HiveMeeting (蜂巢会议)

```
┌──────────────────────────────────────┐
│ 🏢 部门蜂巢              🟢 进行中   │  ← Header + Status Badge
│                                      │
│  ┌────────────────────────────┐      │
│  │ 法规穿透 · 合规诊断 ·     │      │  ← Topic Tags
│  │ 风险预警 · 3人参会        │      │    (部门特有内容)
│  └────────────────────────────┘      │
│                                      │
│  👤👤👤                              │  ← Participant Avatars
└──────────────────────────────────────┘
```

**通用结构:**
```
[部门名称]蜂巢 · [关键词1] · [关键词2] · [关键词3] · N人参会
```

**部门主题映射:**
| 部门 | 蜂巢主题模板 |
|:----|:------------|
| 合规部 | `法规穿透 · 合规诊断 · 风险预警 · 3人参会` |
| 情报部 | `竞品分析 · 市场情报 · 趋势捕捉 · 3人参会` |
| 市场部 | `品牌传播 · 内容营销 · 增长策略 · 3人参会` |
| 其他部门 | 推测为 `[部门核心职能] · [业务目标1] · [业务目标2] · N人参会` |

---

### 3.3 ChatWindow (AI聊天窗口)

```
┌──────────────────────────────────────────────┐
│ ⚡ 工作区                          空闲/待命  │  ← Status
│                                               │
│ 👤 👤 👤                                      │  ← Employee Icon Buttons
│  徐准 宰贤 意恒                                │    (快速唤起特定员工)
│                                               │
│  ┌─────────────────────────────────────┐      │
│  │ 向合规部提问...                      │      │  ← Input Placeholder
│  └─────────────────────────────────────┘      │    (部门感知)
│                                               │
│  快速提问:                                    │  ← Dynamic Quick Questions
│  ┌────────────────┐  ┌────────────────┐       │    (3条/部门)
│  │ 最新法规变更   │  │ 合规健康度检查 │       │
│  │ 影响?          │  │ ?              │       │
│  └────────────────┘  └────────────────┘       │
│  ┌────────────────┐                           │
│  │ 数据合规注意   │                           │
│  │ 事项?          │                           │
│  └────────────────┘                           │
└──────────────────────────────────────────────┘
```

**Props Interface (推测):**
```typescript
interface ChatWindowProps {
  departmentId: string;
  quickQuestions: QuickQuestion[];
  employees: Employee[];
  placeholder?: string; // 动态生成, 如 "向合规部提问..."
}
```

**快速问题映射 (Quick Questions per Department):**

| 部门 | Q1 | Q2 | Q3 |
|:----|:---|:---|:---|
| 🛡️ 合规部 | 最新法规变更影响 | 合规健康度检查 | 数据合规注意事项 |
| 🔍 情报部 | 竞品最近动作 | 市场趋势分析 | 行业最新动态 |
| 📢 市场部 | 品牌定位优化 | 营销增长策略 | 目标受众画像 |
| ⚖️ 法务部 | (推测) 合同风险审查 | (推测) 诉讼策略建议 | (推测) 知识产权保护 |
| 💰 财务部 | (推测) 现金流分析 | (推测) 税务筹划 | (推测) 成本优化 |
| 🧠 战略部 | (推测) 市场进入策略 | (推测) 竞争定位 | (推测) 增长路径 |
| ⚙️ 技术部 | (推测) 技术架构评估 | (推测) 安全审计 | (推测) DevOps优化 |
| 🎨 设计部 | (推测) 品牌视觉统一 | (推测) UX优化建议 | (推测) 设计系统 |
| 📊 运营部 | (推测) 运营效率分析 | (推测) 用户增长策略 | (推测) 数据驱动决策 |

---

### 3.4 BulletinBoard (公告板)

```
┌──────────────────────────────────────────────┐
│ 📋 公告板                          [🤖 刷新]  │  ← Header + AI Refresh
│                                               │
│  合规部热点                                    │  ← Section: Department Topic
│  ┌──────────────────────────────────┐         │
│  │ 新公司法注册资本5年实缴          │         │  ← Topic Card
│  │ 2024年7月1日起，全体股东认缴...  │         │    (部门特有)
│  └──────────────────────────────────┘         │
│                                               │
│  📜 政策简述                                  │  ← Section: Shared Policy
│  ┌──────────────────────────────────┐         │
│  │ 新规速递                         │         │  ← Policy Brief Card
│  │ [摘要内容...]                    │         │    (全部门共享)
│  └──────────────────────────────────┘         │
│  ┌──────────────────────────────────┐         │
│  │ 行业动态                         │         │
│  │ [摘要内容...]                    │         │
│  └──────────────────────────────────┘         │
└──────────────────────────────────────────────┘
```

**组件构成:**
```
BulletinBoard
├── Header ("📋 公告板")
│   └── AI Refresh Button ("🤖 刷新")
├── DepartmentSection
│   └── TopicCard[] (部门特有热点话题)
└── PolicyBriefSection (跨部门共享)
    └── PolicyBriefCard[] (政策简述列表)
```

**AI Refresh 行为:**
- 点击 🤖 刷新 → 调用 AI 生成新的部门热点话题
- 市场部初始状态为"暂无话题"，暗示需要首次 AI 生成
- 刷新操作应当是异步的，可能伴随加载状态

---

### 3.5 EmployeeCard (员工卡片)

```
┌──────────────────────┐
│       🟢             │  ← Status Dot (在线/忙碌/离线)
│                      │
│   [Emoji] 徐准       │  ← Emoji Icon + Chinese Name
│   合规总监           │  ← Title (职务头衔)
└──────────────────────┘
```

**员工数据映射 (已知员工):**

| 部门 | 员工 | Emoji(推测) | 职务 |
|:----|:----|:-----------|:----|
| 🛡️ 合规部 | 徐准 | 👤 | 合规总监 |
| 🛡️ 合规部 | 宰贤 | 👤 | 知识产权专员 |
| 🛡️ 合规部 | 意恒 | 👤 | 合规工程师 |
| 🔍 情报部 | 晟勋 | 👤 | 情报总监 |
| 🔍 情报部 | 慧珍 | 👤 | 市场分析师 |
| 🔍 情报部 | 东健 | 👤 | 情报分析师 |
| 📢 市场部 | 九尾狐 | 🦊 | 公关总监 |
| 📢 市场部 | 英招 | 🐉 | 市场总监 |
| 📢 市场部 | 相柳 | 🐍 | 商务拓展总监 |

> **注:** 合规部和情报部员工使用通用👤头像；市场部使用神话/神兽emoji (九尾狐🦊, 英招🐉, 相柳🐍) — 这暗示市场部员工可能有定制化avatar，高级部门(专业层级)可能拥有更丰富的形象资产。

---

## 4. Feature Dependency Graph (Feature依赖关系图)

```
                        ┌─────────────────────────┐
                        │     Pricing Tier         │
                        │   (免费/标准/专业)        │
                        └──────────┬──────────────┘
                                   │ 决定可访问的部门集合
                                   ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     Department (部门)                        │
  │  • id, name, emoji, tier                                    │
  │  • 决定员工配置、会议主题、快速问题内容                      │
  └──┬──────────────┬──────────────┬──────────────┬────────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
  │ Employee │ │ Meeting  │ │  Chat    │ │ BulletinBoard    │
  │ 员工     │◄┤ 会议主题 │ │  AI聊天  │ │ 公告板            │
  └──────────┘ │ 由部门   │ │  ┌──────┐│ │  ┌────────────┐ │
  │ 知识库     │ │ 类型决定 │ │  │Quick ││ │  │DeptTopic  │ │
  ▼            │ └──────────┘ │  │Qs    ││ │  │(部门特有)  │ │
  ┌──────────┐ │             │  │depends││ │  └──────┬─────┘ │
  │ Chat     │ │             │  │on dept││ │         │       │
  │ context  │◄┤             │  │type   ││ │    ┌────▼─────┐ │
  │ (dept KB)│ │             │  └──┴───┘│ │    │AI Refresh│ │
  └──────────┘ │             │         │ │    │ 生成话题  │ │
               │             └─────────┘ │    └──────────┘ │
               │                        └──────────────────┘
               │
               ▼
  ┌──────────────────────────────────────────────────────────┐
  │                   Shared Resources                        │
  │  ┌─────────────────────┐  ┌─────────────────────────┐   │
  │  │  PolicyBriefs        │  │  File Library            │   │
  │  │  (全局共享)           │  │  (按部门隔离)            │   │
  │  │  • 新规速递          │  │  每个部门有独立文件空间  │   │
  │  │  • 行业动态          │  │                          │   │
  │  └─────────────────────┘  └─────────────────────────┘   │
  └──────────────────────────────────────────────────────────┘
```

### 依赖关系说明

| 依赖路径 | 类型 | 说明 |
|:---------|:----|:-----|
| **Department → Employee** | 1:N | 一个部门包含3名员工 |
| **Department → Meeting** | 1:1 | 会议主题由部门类型模板生成 |
| **Department → Quick Questions** | 1:N | 3条快速问题内容取决于部门 |
| **Employee → Chat Context** | 依赖 | Chat以员工知识库为基础进行AI响应 |
| **Chat → Quick Questions** | 组合 | Quick Questions是Chat的快捷入口 |
| **Department → Bulletin Topic** | 1:N | 公告话题按部门生成唯一内容 |
| **AI Refresh → Bulletin Topic** | 生成 | 点击刷新 ⇒ AI生成新话题 |
| **BulletinBoard → PolicyBriefs** | 包含 | 公告板组件嵌入政策简述区块 |
| **PolicyBriefs** | 全局共享 | 所有部门看到相同两条政策 |

---

## 5. Data Model 逆向工程 (Data Model Reverse Engineering)

### 5.1 Department (部门)

```typescript
interface Department {
  id: string;                    // 唯一标识: "compliance", "intelligence", "marketing"...
  name: string;                  // 中文名称: "合规部", "情报部", "市场部"...
  emoji: string;                 // 表情符号: "🛡️", "🔍", "📢"...
  tier: 'free' | 'standard' | 'pro';  // 定价层级
  order: number;                 // 显示顺序 (1-9)
  employees: Employee[];         // 员工列表 (每个部门3人)
  meetingStatus: 'active' | 'idle' | 'offline';  // 会议状态
  meetingTopics: string[];       // 蜂巢会议话题标签
  meetingParticipantCount: number; // 参会人数
  bulletinTopics: BulletinItem[]; // 公告板话题 (部门特有)
  fileCount: number;             // 文件数量
}

// 示例: 合规部
const complianceDept: Department = {
  id: 'compliance',
  name: '合规部',
  emoji: '🛡️',
  tier: 'free',
  order: 1,
  employees: [
    { id: 'xu-zhun', name: '徐准', emoji: '👤', title: '合规总监', department: 'compliance', status: 'online' },
    { id: 'zai-xian', name: '宰贤', emoji: '👤', title: '知识产权专员', department: 'compliance', status: 'online' },
    { id: 'yi-heng', name: '意恒', emoji: '👤', title: '合规工程师', department: 'compliance', status: 'online' },
  ],
  meetingStatus: 'active',
  meetingTopics: ['法规穿透', '合规诊断', '风险预警'],
  meetingParticipantCount: 3,
  bulletinTopics: [
    { id: 'b1', departmentId: 'compliance', title: '新公司法注册资本5年实缴', summary: '2024年7月1日起...', source: 'AI', timestamp: '2024-06-16' }
  ],
  fileCount: 0,
};
```

### 5.2 Employee (员工)

```typescript
interface Employee {
  id: string;                    // 唯一标识
  name: string;                  // 中文姓名
  emoji: string;                 // 表情头像: "👤" (通用) 或 "🦊" (定制)
  title: string;                 // 职务头衔: "合规总监", "市场分析师"...
  department: string;            // 所属部门ID
  status: 'online' | 'busy' | 'away' | 'offline';  // 在线状态
  avatarUrl?: string;            // 自定义头像URL (推测高级部门有此字段)
  specialty?: string[];          // 专长领域 (推测)
  bio?: string;                  // 个人简介 (推测)
}
```

### 5.3 QuickQuestion (快速问题)

```typescript
interface QuickQuestion {
  id: string;                    // 唯一标识
  departmentId: string;          // 所属部门ID
  text: string;                  // 问题文本: "最新法规变更影响?"
  order: number;                 // 显示顺序 (1, 2, 3)
  employeeRef?: string;          // 关联员工ID (可选, 用于定向提问)
  category?: string;             // 问题分类 (推测)
}

// 预配置数据 (每个部门3条, 固定)
const complianceQuickQs: QuickQuestion[] = [
  { id: 'q1', departmentId: 'compliance', text: '最新法规变更影响?', order: 1 },
  { id: 'q2', departmentId: 'compliance', text: '合规健康度检查?', order: 2 },
  { id: 'q3', departmentId: 'compliance', text: '数据合规注意事项?', order: 3 },
];
```

### 5.4 BulletinItem (公告条目)

```typescript
interface BulletinItem {
  id: string;                    // 唯一标识
  departmentId: string;          // 所属部门ID (部门特有)
  title: string;                 // 话题标题
  summary: string;               // 话题摘要
  source: 'AI' | 'system' | 'user';  // 来源
  timestamp: string;             // 时间戳
  url?: string;                  // 外部链接 (推测)
  tags?: string[];               // 标签 (推测)
}

// AI生成的部门热点话题
const complianceBulletin: BulletinItem = {
  id: 'b1',
  departmentId: 'compliance',
  title: '新公司法注册资本5年实缴',
  summary: '2024年7月1日起，全体股东认缴的出资额由股东按照公司章程的规定自公司成立之日起五年内缴足。',
  source: 'AI',
  timestamp: '2024-06-16T00:00:00Z',
};
```

### 5.5 PolicyBrief (政策简述)

```typescript
interface PolicyBrief {
  id: string;                    // 唯一标识
  title: string;                 // 政策标题
  summary: string;               // 政策摘要
  category: 'regulation' | 'industry' | 'policy';  // 分类
  shared: true;                  // 始终为 true (全局共享)
  url?: string;                  // 原始链接 (推测)
  publishedDate?: string;        // 发布日期 (推测)
  departmentIds?: string[];      // 适用部门 (所有部门, 推测)
}

// 全局共享的两条政策
const sharedPolicyBriefs: PolicyBrief[] = [
  {
    id: 'p1',
    title: '新规速递',
    summary: '最新政策法规变化摘要...',
    category: 'regulation',
    shared: true,
  },
  {
    id: 'p2',
    title: '行业动态',
    summary: '跨境电商出口退税政策利好...',
    category: 'industry',
    shared: true,
  },
];
```

### 5.6 数据关系图 (ER Diagram)

```
┌──────────────┐      1:N      ┌────────────────┐
│  Department  │──────────────►│   Employee      │
│  (9 records) │               │  (3 per dept)   │
└──────┬───────┘               └────────────────┘
       │
       │ 1:N                    ┌────────────────┐
       ├───────────────────────►│ QuickQuestion   │
       │                       │  (3 per dept)   │
       │ 1:N                   └────────────────┘
       ├───────────────────────►┌────────────────┐
       │                       │ BulletinItem    │
       │                       │  (dept-specific)│
       │                       └────────────────┘
       │
       │ (全局共享)              ┌────────────────┐
       └───────────────────────►│ PolicyBrief     │
                                │  (2 records)    │
                                └────────────────┘
                                                   
┌────────────────┐      1:1      ┌────────────────┐
│  Department    │──────────────►│ HiveMeeting     │
│                │               │ (derived from   │
│                │               │  dept template) │
└────────────────┘               └────────────────┘
```

---

## 6. API Contracts (推测)

基于UI行为和数据流模式，推断以下API端点：

### 6.1 部门相关

#### `GET /api/departments`
获取所有部门及完整数据（含员工、会议状态、快速问题、公告话题等）

**Response:**
```json
{
  "departments": [
    {
      "id": "compliance",
      "name": "合规部",
      "emoji": "🛡️",
      "tier": "free",
      "order": 1,
      "meetingStatus": "active",
      "meetingTopics": ["法规穿透", "合规诊断", "风险预警"],
      "meetingParticipantCount": 3,
      "fileCount": 0,
      "employees": [
        { "id": "xu-zhun", "name": "徐准", "emoji": "👤", "title": "合规总监", "status": "online" },
        { "id": "zai-xian", "name": "宰贤", "emoji": "👤", "title": "知识产权专员", "status": "online" },
        { "id": "yi-heng", "name": "意恒", "emoji": "👤", "title": "合规工程师", "status": "online" }
      ],
      "quickQuestions": [
        { "id": "q1", "text": "最新法规变更影响?", "order": 1 },
        { "id": "q2", "text": "合规健康度检查?", "order": 2 },
        { "id": "q3", "text": "数据合规注意事项?", "order": 3 }
      ],
      "bulletinTopics": [
        { "id": "b1", "title": "新公司法注册资本5年实缴", "summary": "2024年7月1日起...", "source": "AI" }
      ]
    }
    // ... 其他8个部门
  ],
  "sharedPolicyBriefs": [
    { "id": "p1", "title": "新规速递", "summary": "最新政策法规变化摘要...", "category": "regulation" },
    { "id": "p2", "title": "行业动态", "summary": "跨境电商出口退税政策利好...", "category": "industry" }
  ]
}
```

**说明:** 此端点聚合了所有必要数据，用于SSR (Server-Side Rendering) 初始页面渲染。Next.js 的 `getServerSideProps` 或 RSC 在此处获取数据。

---

#### `GET /api/department/:id`
获取单个部门详情（展开面板时按需加载）

**Response:**
```json
{
  "department": {
    "id": "legal",
    "name": "法务部",
    "emoji": "⚖️",
    "tier": "pro",
    "order": 4,
    "meetingStatus": "active",
    "meetingTopics": ["合同审查", "诉讼策略", "知识产权"],
    "meetingParticipantCount": 3,
    "fileCount": 0,
    "employees": [
      { "id": "...", "name": "...", "emoji": "👤", "title": "法务总监", "status": "online" },
      { "id": "...", "name": "...", "emoji": "👤", "title": "合同律师", "status": "online" },
      { "id": "...", "name": "...", "emoji": "👤", "title": "知识产权律师", "status": "online" }
    ],
    "quickQuestions": [
      { "id": "lq1", "text": "合同风险审查?", "order": 1 },
      { "id": "lq2", "text": "诉讼策略建议?", "order": 2 },
      { "id": "lq3", "text": "知识产权保护?", "order": 3 }
    ],
    "bulletinTopics": []
  }
}
```

---

### 6.2 聊天相关

#### `POST /api/chat`
发送消息并获取AI响应

**Request:**
```json
{
  "departmentId": "compliance",
  "message": "最新的出海合规政策有哪些变化？",
  "employeeId": "xu-zhun",
  "conversationId": "conv_12345"
}
```

**Response:**
```json
{
  "reply": "根据最新法规，2024年7月1日起新公司法要求注册资本5年内实缴...",
  "suggestedQuestions": [
    "这对跨境电商有什么影响？",
    "如何调整公司注册资本？"
  ],
  "sources": [
    { "title": "新公司法全文", "url": "..." }
  ],
  "conversationId": "conv_12345"
}
```

**说明:** 聊天是AI驱动的核心交互。`employeeId` 字段暗示消息可能定向到特定AI员工，响应附带建议问题用于UX连续性。`conversationId` 用于追踪对话上下文。

---

### 6.3 公告相关

#### `GET /api/bulletin/:deptId`
获取指定部门的公告话题

**Response:**
```json
{
  "departmentId": "compliance",
  "topics": [
    {
      "id": "b1",
      "title": "新公司法注册资本5年实缴",
      "summary": "2024年7月1日起，全体股东认缴的出资额由股东按照公司章程的规定自公司成立之日起五年内缴足。",
      "source": "AI",
      "timestamp": "2024-06-16T00:00:00Z",
      "url": "https://example.com/company-law"
    }
  ]
}
```

---

#### `POST /api/bulletin/refresh`
AI重新生成部门热点话题

**Request:**
```json
{
  "departmentId": "marketing"
}
```

**Response:**
```json
{
  "departmentId": "marketing",
  "topics": [
    {
      "id": "bm1",
      "title": "TikTok电商东南亚市场爆发",
      "summary": "2024年TikTok Shop东南亚GMV预计突破200亿美元...",
      "source": "AI",
      "timestamp": "2024-06-16T01:00:00Z"
    }
  ]
}
```

**说明:** 市场部初始状态显示"暂无话题"，点击🤖刷新后触发此端点。这是平台AI主动生成内容能力的关键体现。

---

### 6.4 政策简述相关

#### `GET /api/policies`
获取全局共享的政策简述

**Response:**
```json
{
  "policies": [
    {
      "id": "p1",
      "title": "新规速递",
      "summary": "最新政策法规变化摘要...",
      "category": "regulation",
      "updatedAt": "2024-06-15T00:00:00Z"
    },
    {
      "id": "p2",
      "title": "行业动态",
      "summary": "跨境电商出口退税政策利好...",
      "category": "industry",
      "updatedAt": "2024-06-14T00:00:00Z"
    }
  ]
}
```

---

### 6.5 文件相关 (推测)

#### `GET /api/files/:deptId`
获取部门文件列表

**Response:**
```json
{
  "departmentId": "compliance",
  "files": [],
  "totalCount": 0
}
```

#### `POST /api/files/upload`
上传文件到部门文件库

**Request:** `multipart/form-data`
- `departmentId`: string
- `file`: File

---

### 6.6 API架构总结

```
API Architecture (推测)
=======================

RESTful endpoints under /api/

GET  /api/departments              → 全量数据聚合 (SSR初始渲染)
GET  /api/department/:id           → 单部门详情 (按需加载)
POST /api/chat                     → AI聊天 (核心交互)
GET  /api/chat/:conversationId     → 对话历史 (推测)
GET  /api/bulletin/:deptId         → 部门公告话题
POST /api/bulletin/refresh         → AI生成新话题
GET  /api/policies                 → 全局政策简述
GET  /api/files/:deptId            → 部门文件列表
POST /api/files/upload             → 文件上传
POST /api/auth/login               → 用户认证 (推测)
GET  /api/user/profile             → 用户订阅信息 (推测)

数据流动模式:
┌─────────┐   SSR/CSR    ┌─────────────┐   REST    ┌──────────┐
│ Browser │◄───────────►│ Next.js App  │◄─────────►│  API     │
│ (Client)│              │ (Server)     │           │  Layer   │
└─────────┘              └─────────────┘           └──────────┘
                                  │                      │
                                  ▼                      ▼
                          ┌──────────────┐     ┌──────────────┐
                          │ React State  │     │  Database /  │
                          │ (客户端状态)  │     │  AI Service  │
                          └──────────────┘     └──────────────┘
```

---

## 7. 定价矩阵 (Pricing Matrix)

### 7.1 定价层级总览

| 维度 | 免费 (合规) | 标准 (5部门) | 专业 (3部门) |
|:----|:----------:|:------------:|:------------:|
| **定价策略** | Freemium 引流 | 核心业务订阅 | 高端增值订阅 |
| **目标用户** | 初创企业/个人 | 成长型出海企业 | 成熟跨境企业 |
| **部门数量** | 1 (🛡️合规) | 6 (免费+5标准) | 9 (全部) |
| **可用部门** | 合规部 | 合规+情报+市场+技术+设计+运营 | 全部9部门 |
| **价格** | ¥0 (免费) | 推测 ¥299-699/月 | 推测 ¥999-1999/月 |

### 7.2 Feature定价映射

| Feature | 免费 | 标准 | 专业 |
|:--------|:----:|:----:|:----:|
| 合规部 | ✅ | ✅ | ✅ |
| 情报部 | ❌ | ✅ | ✅ |
| 市场部 | ❌ | ✅ | ✅ |
| 技术部 | ❌ | ✅ | ✅ |
| 设计部 | ❌ | ✅ | ✅ |
| 运营部 | ❌ | ✅ | ✅ |
| 法务部 | ❌ | ❌ | ✅ |
| 财务部 | ❌ | ❌ | ✅ |
| 战略部 | ❌ | ❌ | ✅ |
| **AI聊天 (单部门)** | ✅ (合规限定) | ✅ (6部门) | ✅ (全部) |
| **AI聊天 (跨部门)** | ❌ | ❌ | ✅ |
| **蜂巢会议** | ✅ | ✅ | ✅ |
| **公告板** | ✅ (合规话题) | ✅ (6部门话题) | ✅ (全部话题) |
| **政策简述** | ✅ | ✅ | ✅ |
| **文件库** | ❌ | ✅ (推测有限) | ✅ (推测无限) |
| **AI刷新公告** | ❌ | ✅ (推测有限次) | ✅ (无限次) |
| **快速问题** | ✅ (3条固定) | ✅ (3条/部门) | ✅ (3条/部门+自定义) |
| **员工详情** | 基础 | 基础 | 含定制化头像/简历 |
| **API访问** | ❌ | ❌ | ✅ (推测) |
| **优先支持** | ❌ | ❌ | ✅ (推测) |

### 7.3 定价维度分层策略

```
免费 (合规部)
  ├── 部门数: 1/9
  ├── AI能力: 基础级 (合规限定知识库)
  ├── 存储: 0
  ├── 目的: 教育用户 + 展示AI能力 + 收集使用数据
  └── 升级触发: 需要情报/市场部门时

标准 (5部门)
  ├── 部门数: 6/9
  ├── AI能力: 增强级 (6个知识域)
  ├── 存储: 有限 (推测)
  ├── 目的: 覆盖核心业务场景
  └── 升级触发: 需要法务/财务/战略高级部门时

专业 (3部门)
  ├── 部门数: 9/9 (全集)
  ├── AI能力: 旗舰级 (全知识域+跨域推理)
  ├── 存储: 无限 (推测)
  ├── 目的: 全功能解锁, 高端出海企业一站式方案
  └── 增值点: 法务合同审查、财务数据分析、战略规划
```

---

## 8. 非Feature化总结 (De-featurization Summary)

> **核心理念:** 所有UI组件和交互模式都可以"去特征化"——剥离具体业务形态后，还原为通用的 **原子心智模型 (Atomic Mental Models)**。以下分析展示每种UI组件如何映射到底层Feature原子。

### 8.1 什么是"非Feature化"？

**Feature化视角:** "合规部有3个快速问题：最新法规变更、合规健康度检查、数据合规注意事项"
**非Feature化视角:** "每个部门面板有一个 QuestionSet[3] 槽位，内容由 department.type 参数决定"

换句话说：**将具体业务内容从组件结构中剥离，留下纯抽象的交互模式。**

### 8.2 UI → 原子Feature映射

| # | UI组件 | 非Feature化抽象 | 原子心智模型 |
|:--|:-------|:---------------|:------------|
| 1 | **部门面板** | `EntityPanel[T]` | 一个带定价标签的实体卡片容器，可展开显示子实体列表 |
| 2 | **蜂巢会议** | `StatusBoard[label, tags[], participantCount]` | 一个带状态指示器的标签组展示模块 |
| 3 | **AI聊天** | `AIChat[contextId, placeholders[], quickActions[]]` | 上下文感知的AI对话界面，附带快捷操作入口 |
| 4 | **快速问题** | `QuickActionSet[items[]: {text, action}]` | 一组预定义的快捷操作按钮，减少用户输入成本 |
| 5 | **公告板** | `ContentFeed[section[]: {title, items[], refreshable}]` | 按分区组织的动态内容流，支持手动刷新 |
| 6 | **政策简述** | `SharedCardSet[items[]: {title, summary, category}]` | 一组全局共享的知识卡片，在所有上下文中可见 |
| 7 | **员工卡片** | `AgentCard[avatar, name, role, status]` | 一个智能体身份展示单元，包含头像、身份信息和状态 |
| 8 | **员工快捷栏** | `AgentQuickBar[agents[]: {id, avatar}]` | 智能体切换栏，用于快速切换对话上下文 |
| 9 | **文件库** | `FileCounter[count, scopeId]` | 一个带作用域隔离的文档计数器 |

### 8.3 组件 → Feature 组合规则

```
UI组件 = Feature原子 + 业务数据 + 定价策略
       ^^^^^^^^^   ^^^^^^^^^^   ^^^^^^^^^^
       可复用      可配置       可限制
```

**示例:**
```
合规部公告板 = ContentFeed (通用) 
            + {title: "新公司法注册资本5年实缴", source: "AI"} (业务数据)
            + 免费版可访问 (定价策略)

市场部公告板 = ContentFeed (通用)
            + null (暂无话题, 等待AI生成)
            + 标准版可访问
```

### 8.4 Feature原子树 (Feature Atom Tree)

```
┌─────────────────────────────────────────────────────┐
│                   Feature Atom Tree                 │
│                                                      │
│  ┌─────────────────────────────────────────┐        │
│  │  Container Atoms (容器原子)              │        │
│  │  ├── EntityPanel       → 实体卡片容器    │        │
│  │  ├── ContentFeed       → 内容流容器      │        │
│  │  ├── AIChat            → AI对话容器      │        │
│  │  └── StatusBoard       → 状态展示面板    │        │
│  └─────────────────────────────────────────┘        │
│                                                      │
│  ┌─────────────────────────────────────────┐        │
│  │  Interaction Atoms (交互原子)            │        │
│  │  ├── QuickActionSet    → 快捷操作按钮组  │        │
│  │  ├── AgentQuickBar     → 智能体切换栏    │        │
│  │  ├── RefreshButton     → 刷新/生成按钮   │        │
│  │  └── ExpandToggle      → 展开/折叠切换   │        │
│  └─────────────────────────────────────────┘        │
│                                                      │
│  ┌─────────────────────────────────────────┐        │
│  │  Display Atoms (展示原子)               │        │
│  │  ├── AgentCard         → 智能体身份卡   │        │
│  │  ├── TagGroup          → 标签组         │        │
│  │  ├── SharedCardSet     → 共享卡片集     │        │
│  │  └── FileCounter       → 文件计数器     │        │
│  └─────────────────────────────────────────┘        │
│                                                      │
│  ┌─────────────────────────────────────────┐        │
│  │  Decorator Atoms (装饰原子)              │        │
│  │  ├── StatusDot         → 状态圆点       │        │
│  │  ├── TierBadge         → 定价层级标签   │        │
│  │  └── EmojiIcon         → Emoji图标      │        │
│  └─────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

### 8.5 非Feature化价值

| 价值 | 说明 |
|:----|:------|
| **跨项目复用** | 剥离业务内容后，Feature原子可移植到其他行业垂直SaaS |
| **快速扩展新部门** | 新增部门只需定义: `{type, employees[], quickQs[]}`，无需新组件 |
| **统一定价策略** | 按Feature原子粒度控制访问权限，而非UI页面级别 |
| **简化测试** | Feature原子可独立测试，业务数据以fixture注入 |
| **技术标准化** | 每个原子有明确的Props接口，便于团队并行开发 |

### 8.6 从Feature原子重新构建任意部门

```typescript
// 定义一个部门的本质 = 组合Feature原子 + 填充业务数据
function createDepartment(config: DepartmentConfig): DepartmentUI {
  return {
    panel: EntityPanel({ title: config.name, emoji: config.emoji, tier: config.tier }),
    meeting: StatusBoard({ 
      label: `${config.name}蜂巢`, 
      tags: config.meetingTopics, 
      status: config.meetingStatus 
    }),
    chat: AIChat({
      contextId: config.id,
      placeholders: [`向${config.name}提问...`],
      quickActions: QuickActionSet({ items: config.quickQuestions }),
      agentBar: AgentQuickBar({ agents: config.employees })
    }),
    feed: ContentFeed({
      sections: [
        { title: `${config.name}热点`, items: config.bulletinTopics, refreshable: true },
        { title: '政策简述', items: sharedPolicyBriefs, refreshable: false }
      ]
    }),
    files: FileCounter({ count: config.fileCount, scopeId: config.id })
  };
}

// 仅需数据差异即可生成9个不同部门
const compliance = createDepartment(complianceConfig);  // 免费版
const marketing  = createDepartment(marketingConfig);   // 标准版
const legal      = createDepartment(legalConfig);       // 专业版
```

---

## 附录

### A. 已知部门配置速查表

| # | 部门 | Emoji | ID推测 | Tier | 员工数 | 已知员工 |
|:-:|:----|:-----:|:------:|:----:|:------:|:---------|
| 1 | 合规部 | 🛡️ | compliance | free | 3 | 徐准, 宰贤, 意恒 |
| 2 | 情报部 | 🔍 | intelligence | standard | 3 | 晟勋, 慧珍, 东健 |
| 3 | 市场部 | 📢 | marketing | standard | 3 | 九尾狐, 英招, 相柳 |
| 4 | 法务部 | ⚖️ | legal | pro | 3 | (未展开) |
| 5 | 财务部 | 💰 | finance | pro | 3 | (未展开) |
| 6 | 战略部 | 🧠 | strategy | pro | 3 | (未展开) |
| 7 | 技术部 | ⚙️ | technology | standard | 3 | (未展开) |
| 8 | 设计部 | 🎨 | design | standard | 3 | (未展开) |
| 9 | 运营部 | 📊 | operations | standard | 3 | (未展开) |

### B. 技术栈推测

| 技术 | 用途 | 证据 |
|:----|:-----|:-----|
| Next.js 14+ (App Router) | 框架 | Vercel部署 + SSR需求 |
| React Server Components | 服务端渲染 | 初始数据聚合 |
| Tailwind CSS | 样式 | Dark Theme / slate-900 |
| Zustand / Context | 状态管理 (推测) | 跨部门数据共享 |
| Vercel AI SDK | AI集成 (推测) | AI聊天 + 公告生成 |
| Prisma / Drizzle | ORM (推测) | 部门/员工数据持久化 |
| PostgreSQL | 数据库 (推测) | Vercel Postgres集成 |

### C. 迭代建议

| 优先级 | 改进方向 | 说明 |
|:------|:---------|:-----|
| P0 | 市场部初始空状态处理 | 当前"暂无话题"缺乏引导，应提供首次"AI生成"操作提示 |
| P0 | 文件库功能完善 | 当前仅显示计数"0"，应提供上传/管理能力 |
| P1 | 员工定制化Emoji | 市场部已有定制emoji，应推广到全部员工 |
| P1 | 跨部门聊天上下文 | 专业版应支持@提及其他部门员工 |
| P2 | 公告时间线 | 显示话题更新的时间戳，提升信息可信度 |
| P2 | 快速问题动态化 | 允许用户自定义或基于历史动态推荐 |

---

> **文档版本:** v1.0
> **逆向工程源:** https://gaia-commercial.vercel.app/workbench
> **技术框架:** Next.js + Vercel + Tailwind CSS
> **生成目的:** 为"中韩出海数智港"产品提供架构参考与Feature原子化设计方法论
