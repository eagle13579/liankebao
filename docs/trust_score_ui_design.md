# 信任评分前端展示设计方案

> 版本: v1.0  
> 日期: 2026-06-25  
> 状态: 设计提案

---

## 目录

1. [概述](#1-概述)
2. [信任评分模型](#2-信任评分模型)
3. [API 数据流设计](#3-api-数据流设计)
4. [前端页面结构](#4-前端页面结构)
5. [信任分仪表盘](#5-信任分仪表盘)
6. [信任分分解视图](#6-信任分分解视图)
7. [行为积分历史趋势](#7-行为积分历史趋势)
8. [担保链可视化](#8-担保链可视化)
9. [组件树与路由](#9-组件树与路由)
10. [与三塔模型的集成关系](#10-与三塔模型的集成关系)
11. [演进路线](#11-演进路线)

---

## 1. 概述

### 1.1 现状分析

当前系统拥有完整的**三塔DNN匹配引擎** (`TowerEnsemble`)，但**信任评分体系尚未产品化**：

| 已有资产 | 状态 |
|---------|------|
| UserTower (用户 Embedding 塔) | ✅ 已实现，triplet loss 训练 |
| EnterpriseTower (企业特征塔) | ✅ 已实现，含信用评分特征 |
| BehaviorTower (用户行为塔) | ✅ 已实现，Transformer 行为序列 |
| MatchingScorer (匹配评分器) | ✅ α·cos(user,ent) + β·cos(behav,ent) + γ·cos(user,behav) |
| OnlineWeightOptimizer | ✅ 在线学习权重调优 |
| **信任分前端展示** | ❌ **不存在** |
| **信任分 API** | ❌ **不存在** |
| **担保链数据 & UI** | ❌ **不存在** |
| **行为积分累积 UI** | ❌ **不存在** |

### 1.2 设计目标

1. **信任分仪表盘**: 用户可视化自己的信任等级 (0-1000, 四级)
2. **信任分分解**: 身份认证 / 行为信用 / 担保网络 三大维度评分占比
3. **行为积分历史**: 趋势图展示行为积分累积过程
4. **担保链可视化**: 谁为你担保 + 你为谁担保 的链式或网状图

---

## 2. 信任评分模型

### 2.1 评分范围与等级

```
 0 ────────────────────────────────────── 1000
 │         │          │           │
 Bronze    Silver     Gold      Platinum
 (0-250)   (251-500) (501-750)  (751-1000)
```

| 等级 | 分数区间 | 图标 | 颜色 (HSL) | 权益 |
|------|---------|------|-----------|------|
| 🥉 Bronze | 0–250 | 铜盾 | hsl(30, 60%, 55%) | 基础匹配额度 (3次/月) |
| 🥈 Silver | 251–500 | 银盾 | hsl(210, 50%, 65%) | 中等匹配额度 (20次/月) |
| 🥇 Gold | 501–750 | 金盾 | hsl(45, 85%, 55%) | 高匹配额度 + 高级筛选 |
| 💎 Platinum | 751–1000 | 钻盾 | hsl(260, 70%, 60%) | 无限制 + 优先推荐 + 专属客服 |

### 2.2 三维度分解

```
信任分 = 身份认证分 × w_identity
       + 行为信用分 × w_behavior
       + 担保网络分 × w_guarantee
```

| 维度 | 权重 | 满分 | 数据来源 | 指标项 |
|------|------|------|---------|-------|
| **身份认证** Identity | 35% | 350 | BusinessCard 字段 / 企业数据管道 | 实名认证✓, 企业资质✓, 行业标签完整度, 联系方式验证 |
| **行为信用** Behavior | 40% | 400 | BehaviorTower 行为序列 / Feedback | 登录频次, 匹配响应率, 反馈评分, 交易完成率, 投诉记录 |
| **担保网络** Guarantee | 25% | 250 | 知识图谱 / 担保关系表 | 担保人数量, 被担保人数量, 担保链深度, 担保人信用均值 |

**默认权重**: `w_identity=0.35, w_behavior=0.40, w_guarantee=0.25`  
(可复用 `OnlineWeightOptimizer` 机制根据用户行为动态调优)

### 2.3 身份认证分 (0–350)

| 指标 | 分值 | 计算方式 |
|------|------|---------|
| 实名认证 | 0/50 | 手机号+身份证验证通过 = 50 |
| 企业资质 | 0/100 | 上传营业执照 = 60, 已验证 = 100 |
| 行业标签 | 0/80 | 填写行业 = 20, 三级分类完整 = 80 |
| 联系方式 | 0/70 | 手机=20, 邮箱=20, 微信=30 |
| 企业数据匹配 | 0/50 | 天眼查/企查查数据匹配度 |

### 2.4 行为信用分 (0–400)

| 指标 | 分值 | 计算方式 |
|------|------|---------|
| 活跃度 | 0/100 | 近30天登录天数 × 3, 上限100 |
| 匹配响应 | 0/100 | 匹配请求响应率 × 100 |
| 反馈质量 | 0/80 | 历史反馈平均评分 × 20 |
| 交易完成 | 0/80 | 成功匹配且完成沟通的比率 × 80 |
| 投诉记录 | 0/−40 | 每次投诉扣10, 上限扣40 |

### 2.5 担保网络分 (0–250)

| 指标 | 分值 | 计算方式 |
|------|------|---------|
| 担保人数量 | 0/70 | 每1个担保人+15, 上限70 |
| 被担保人数 | 0/60 | 每担保1人+10, 上限60 |
| 担保链深度 | 0/50 | 二级担保链及以上+30, 三级+50 |
| 担保人信用均值 | 0/70 | 所有担保人信任分均值 × 0.07 |

---

## 3. API 数据流设计

### 3.1 数据流总图

```
┌─────────────┐      ┌──────────────┐      ┌──────────────────┐
│  前端页面    │ ──→  │  FastAPI     │ ──→  │  TrustService     │
│  Dashboard   │ ←──  │  Router      │ ←──  │  (评分计算引擎)   │
└─────────────┘      └──────────────┘      └───────┬──────────┘
                                                    │
                    ┌───────────────────────────────┼───────────────┐
                    │                               │               │
            ┌───────▼──────┐  ┌────────▼───────┐  ┌──▼──────────┐
            │ DB: users    │  │ DB: behaviors  │  │ Neo4j: KG   │
            │ BusinessCard │  │ feedbacks      │  │ 担保关系     │
            └──────────────┘  └────────────────┘  └─────────────┘
                                                          │
                                          ┌───────────────▼────────┐
                                          │ 后台 Cron / 事件驱动    │
                                          │ 信任分重新计算           │
                                          └────────────────────────┘
```

### 3.2 新增 API 端点

#### `GET /api/trust/score` — 获取用户信任分总览

```
Request:  Header: Authorization: Bearer <token>

Response:
{
  "code": 200,
  "data": {
    "user_id": 10086,
    "trust_score": 672,              // 总分 0-1000
    "trust_level": "gold",           // bronze|silver|gold|platinum
    "level_progress": 0.688,         // 当前等级内进度 (0-1)
    "next_level": "platinum",        // 下一等级名称
    "next_level_at": 751,            // 下一等级门槛分数
    "breakdown": {
      "identity": {
        "score": 280,
        "max": 350,
        "weight": 0.35,
        "detail": {
          "real_name_verified": 50,
          "enterprise_verified": 100,
          "industry_tags": 60,
          "contact_info": 40,
          "enterprise_data_match": 30
        }
      },
      "behavior": {
        "score": 260,
        "max": 400,
        "weight": 0.40,
        "detail": {
          "activity": 75,
          "match_response": 80,
          "feedback_quality": 45,
          "deal_completion": 60,
          "penalty": 0
        }
      },
      "guarantee": {
        "score": 132,
        "max": 250,
        "weight": 0.25,
        "detail": {
          "guarantors_count": 3,
          "guaranteed_count": 2,
          "chain_depth": 2,
          "avg_guarantor_score": 780
        }
      }
    },
    "updated_at": "2026-06-25T10:30:00Z"
  }
}
```

#### `GET /api/trust/behavior/history` — 行为积分历史

```
Request:  ?days=30&granularity=day

Response:
{
  "code": 200,
  "data": {
    "user_id": 10086,
    "granularity": "day",
    "points": [
      {"date": "2026-06-01", "score": 220, "events": [
        {"type": "login", "points": 5, "desc": "登录 +5"},
        {"type": "match_view", "points": 3, "desc": "查看匹配 +3"}
      ]},
      ...
    ],
    "total_accumulated": 380,     // 累计积分
    "current_behavior_score": 260, // 当前行为信用分
    "trend": "up"                  // up|stable|down
  }
}
```

#### `GET /api/trust/guarantee/network` — 担保链数据

```
Request:  ?depth=3

Response:
{
  "code": 200,
  "data": {
    "user_id": 10086,
    "nodes": [
      {
        "id": 10086,
        "name": "当前用户",
        "type": "self",
        "trust_score": 672,
        "trust_level": "gold"
      },
      {
        "id": 10001,
        "name": "张三 (XX科技有限公司)",
        "type": "guarantor",         // guarantor|guaranteed|chain
        "trust_score": 810,
        "trust_level": "platinum",
        "relation": "direct",         // direct|indirect
        "depth": 1                    // 担保链深度
      },
      ...
    ],
    "edges": [
      {
        "source": 10001,
        "target": 10086,
        "type": "guarantee",         // guarantee|recommend
        "created_at": "2026-03-15",
        "weight": 1.0
      },
      ...
    ],
    "stats": {
      "direct_guarantors": 3,
      "indirect_guarantors": 5,
      "guaranteed_users": 2,
      "max_depth": 2,
      "network_trust_avg": 735
    }
  }
}
```

#### `PUT /api/trust/refresh` — 手动刷新信任分

```
Request:  POST /api/trust/refresh

Response:
{
  "code": 200,
  "message": "信任分已重新计算",
  "data": {
    "trust_score": 680,
    "changed": 8,
    "recalculated_at": "2026-06-25T11:00:00Z"
  }
}
```

### 3.3 数据流时序

```
┌────────┐    ┌──────────┐    ┌──────────────┐    ┌────────┐    ┌────────────┐
│ 前端    │    │ FastAPI  │    │ TrustService  │    │ DB/KG  │    │ TowerEns.  │
│ (Vue)   │    │ Router   │    │               │    │        │    │ (可选)     │
└───┬────┘    └────┬─────┘    └──────┬────────┘    └───┬────┘    └─────┬──────┘
    │              │                 │                  │               │
    │  GET /score  │                 │                  │               │
    │─────────────→│                 │                  │               │
    │              │  get_trust_     │                  │               │
    │              │  score(user)    │                  │               │
    │              │────────────────→│                  │               │
    │              │                 │  查询用户身份数据 │               │
    │              │                 │─────────────────→│               │
    │              │                 │  ← 身份字段      │               │
    │              │                 │                  │               │
    │              │                 │  查询行为序列     │               │
    │              │                 │─────────────────→│               │
    │              │                 │  ← 行为数据      │               │
    │              │                 │                  │               │
    │              │                 │  查询担保关系(Neo4j)             │
    │              │                 │─────────────────→│               │
    │              │                 │  ← 担保网络数据  │               │
    │              │                 │                  │               │
    │              │                 │  ┌────────────────┴──────┐      │
    │              │                 │  │ 计算三维度分数        │      │
    │              │                 │  │ 加权汇总→信任分      │      │
    │              │                 │  │ 映射等级             │      │
    │              │                 │  └───────────────────────┘      │
    │              │                 │                  │               │
    │              │  ← 信任分响应   │                  │               │
    │              │←────────────────│                  │               │
    │  ← 渲染      │                 │                  │               │
    │  仪表盘      │                 │                  │               │
    │←────────────│                 │                  │               │
    │              │                 │                  │               │
```

### 3.4 可选: 利用三塔模型增强信任分

> 当前 T0 阶段可先实现**规则计算**的信任分，后续 T1 阶段可引入三塔嵌入增强。

```
# 信任分增强方案 (复用现有资产)
trust_score = rule_based_score * α + dnn_trust_boost * β

# dnn_trust_boost 复用 MatchingScorer:
#   将 "用户嵌入" 与 "平台理想用户嵌入" 的余弦相似度映射到 [0,1]
#   + BehaviorTower 输出的行为嵌入质量评分

# 代码示意:
user_emb = user_tower(user_features)            # (1, 128)
ideal_user_emb = platform_ideal_embedding        # (1, 128)
similarity = F.cosine_similarity(user_emb, ideal_user_emb)

behav_emb = behavior_tower(sequence, mask)       # (1, 128)
behav_quality = behav_emb.norm(dim=1)            # 行为嵌入的L2范数作为质量信号

dnn_trust_boost = 0.6 * similarity + 0.4 * behav_quality
```

---

## 4. 前端页面结构

### 4.1 路由

```
/trust                     → 信任分仪表盘 (主页面)
/trust/breakdown           → 信任分详细分解
/trust/behavior            → 行为积分历史趋势
/trust/guarantee           → 担保链可视化
/trust/settings            → 信任分设置 (刷新/隐私)
```

### 4.2 页面嵌套

```
App.vue
 └── MainLayout.vue
      ├── SidebarNav.vue
      │    └── TrustEntry.vue          ← 侧边栏"信任中心"入口
      │
      └── <router-view>
           ├── TrustDashboard.vue      ← /trust
           │    ├── TrustScoreGauge.vue        ← 环形进度/仪表盘
           │    ├── TrustLevelBadge.vue         ← 等级徽章
           │    ├── TrustBreakdownCard.vue      ← 三维度分解卡片
           │    ├── BehaviorMiniChart.vue       ← 行为积分迷你趋势
           │    └── GuaranteeMiniView.vue       ← 担保链迷你视图
           │
           ├── TrustBreakdownView.vue  ← /trust/breakdown
           │    ├── IdentityScorePanel.vue
           │    ├── BehaviorScorePanel.vue
           │    └── GuaranteeScorePanel.vue
           │
           ├── BehaviorHistoryView.vue ← /trust/behavior
           │    ├── BehaviorChart.vue           ← ECharts 趋势图
           │    ├── BehaviorEventLog.vue        ← 事件流水
           │    └── BehaviorCalendar.vue        ← 日历热力图
           │
           ├── GuaranteeNetworkView.vue← /trust/guarantee
           │    ├── GuaranteeGraph.vue          ← D3.js / ECharts 关系图
           │    ├── GuarantorList.vue           ← 我的担保人列表
           │    └── GuaranteedList.vue          ← 我担保的人列表
           │
           └── TrustSettings.vue       ← /trust/settings
```

---

## 5. 信任分仪表盘

### 5.1 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  🛡️ 信任中心                     [刷新] [分享] [...更多]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────┐  ┌──────────────────┐│
│  │         🥇 GOLD                   │  │  等级权益         ││
│  │                                   │  │  ┌──────────────┐ ││
│  │        ┌──────────┐              │  │  │ ✓ 20次/月匹配 │ ││
│  │        │  672      │  环形仪表    │  │  │ ✓ 高级筛选    │ ││
│  │        │  总分     │  (0-1000)    │  │  │ ✓ 排名优先    │ ││
│  │        └──────────┘              │  │  └──────────────┘ ││
│  │                                   │  │                   ││
│  │  还差 79 分升至 💎 Platinum       │  │  [升级指南 →]     ││
│  │  ████████████████░░░░ 68.8%      │  │                   ││
│  └───────────────────────────────────┘  └──────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  信任分分解                              [详情 →]      ││
│  │                                                         ││
│  │  🆔 身份认证         280 / 350  ████████████░░ 80%      ││
│  │  🎯 行为信用         260 / 400  ███████░░░░░░ 65%       ││
│  │  🔗 担保网络         132 / 250  █████░░░░░░░░ 53%       ││
│  │                                                         ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌───────────────────┐  ┌─────────────────────────────────┐│
│  │  行为积分趋势      │  │  担保链                        ││
│  │  ┌───────────────┐│  │  ┌────────────────────────────┐ ││
│  │  │ 📈 最近30天   ││  │  │  🧑‍💼 张三 ─→ 👤 我        │ ││
│  │  │ 迷你折线图    ││  │  │  🧑‍💼 李四 ─→ 👤 我        │ ││
│  │  └───────────────┘│  │  │  👤 我 ─→ 🧑‍💼 王五        │ ││
│  │                    │  │  │      ↳ 🧑‍💼 赵六        │ ││
│  │  累计: +380 分     │  │  └────────────────────────────┘ ││
│  │  [查看全部 →]      │  │  [查看完整网络 →]              ││
│  └───────────────────┘  └─────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  提升建议                                               ││
│  │  💡 完成企业资质验证 → +40 分                           ││
│  │  💡 邀请一位信誉良好的用户为您担保 → +15 分            ││
│  │  💡 回复待处理的匹配请求 → +20 分                       ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 5.2 TrustScoreGauge 组件

```
Props:
  score: Number (0-1000)
  level: String (bronze|silver|gold|platinum)
  size: String (sm|md|lg)

特性:
  - SVG 环形进度条 (半圆弧或整圆)
  - 渐变色填充 (根据等级: 铜色→银色→金色→紫色)
  - 中心显示分数 + 等级名
  - 底部进度条显示距下一等级的距离
```

### 5.3 TrustLevelBadge 组件

```
Props:
  level: String
  score: Number
  showScore: Boolean

渲染:
  🥇 Gold  或  🥈 Silver 等
  悬停时 Tooltip 显示具体分数和等级说明
```

---

## 6. 信任分分解视图

### 6.1 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  信任分分解                                          [返回] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  🆔 身份认证 (Identity)           权重 35%  280/350    ││
│  │                                                        ││
│  │  实名认证     ████████████████████░░  50/50  ✅ 已完成 ││
│  │  企业资质     ████████████████████░░ 100/100 ✅ 已完成 ││
│  │  行业标签     ████████████████░░░░░░  60/80  ⚠ 待完善 ││
│  │  联系方式     ████████░░░░░░░░░░░░░░  40/70  ⚠ 待完善 ││
│  │  企业数据     ██████░░░░░░░░░░░░░░░░  30/50  ⚠ 未匹配 ││
│  │                                                        ││
│  │  [完善资料 →]                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  🎯 行为信用 (Behavior)            权重 40%  260/400   ││
│  │                                                        ││
│  │  活跃度       ██████████████████░░░░  75/100  ↑ 上升   ││
│  │  匹配响应     ████████████████████░░  80/100  → 稳定   ││
│  │  反馈质量     ██████████░░░░░░░░░░░░  45/80   ↓ 下降   ││
│  │  交易完成     █████████████░░░░░░░░░  60/80   → 稳定   ││
│  │                                                        ││
│  │  违规扣分: 0                                           ││
│  │  [行为记录 →]                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  🔗 担保网络 (Guarantee)           权重 25%  132/250   ││
│  │                                                        ││
│  │  担保人数量   ████████████████░░░░░░  3人   42/70      ││
│  │  被担保人数   ██████████░░░░░░░░░░░░  2人   20/60      ││
│  │  担保链深度   ██████████████░░░░░░░░  2级   30/50      ││
│  │  担保人信用   ████████████████████░░  avg735 40/70     ││
│  │                                                        ││
│  │  [担保网络 →]                                          ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 6.2 各维度 ScorePanel 通用结构

```
Props:
  title: String          // 维度名称
  icon: String           // 图标
  score: Number          // 当前分数
  maxScore: Number       // 满分
  weight: Number         // 权重
  items: Array<{
    label: String,
    score: Number,
    max: Number,
    status: 'completed' | 'pending' | 'warning' | 'danger',
    hint: String?        // 提示文字
  }>
  onAction: Function?    // "完善/查看"按钮回调
```

---

## 7. 行为积分历史趋势

### 7.1 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  行为积分历史                                      [返回]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  时间范围: [7天 ▼]  [30天 ▼] [90天] [自定义]           ││
│  │                                                        ││
│  │  ┌──────────────────────────────────────────────────┐   ││
│  │  │                                                  │   ││
│  │  │    📈 折线图 (ECharts)                           │   ││
│  │  │    X轴: 日期  Y轴: 行为积分                      │   ││
│  │  │    两条线: 日积分 (柱状) + 累积积分 (折线)       │   ││
│  │  │    标注关键事件: 首次认证 / 完成交易 / 投诉      │   ││
│  │  │                                                  │   ││
│  │  └──────────────────────────────────────────────────┘   ││
│  │                                                        ││
│  │  统计: 累计 +380 · 日均 +12.7 · 最高单日 +45          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  积分事件流水                          [筛选: 全部 ▼]  ││
│  │                                                        ││
│  │  🕐 06-25 10:30  +3  查看匹配结果                     ││
│  │  🕐 06-25 09:15  +5  每日登录                          ││
│  │  🕐 06-24 14:20  +10 回复匹配请求                      ││
│  │  🕐 06-23 11:00  +20 完成首次企业认证                  ││
│  │  🕐 06-22 15:30  +3  查看匹配结果                      ││
│  │  ...                                                   ││
│  │                                                        ││
│  │  [加载更多...]                                         ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  行为日历热力图                                         ││
│  │  ┌───┬───┬───┬───┬───┬───┬───┐                        ││
│  │  │   │   │   │ █ │ █ │ █ │   │  周1-7                ││
│  │  │ █ │ █ │   │ █ │   │ █ │ █ │  周8-14               ││
│  │  │   │ █ │ █ │ █ │ █ │ █ │   │  周15-21              ││
│  │  │ █ │ █ │   │ █ │   │   │   │  周22-28              ││
│  │  └───┴───┴───┴───┴───┴───┴───┘                        ││
│  │  颜色: 越深 = 行为积分越高                               ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 7.2 BehaviorChart 组件技术方案

```
技术栈: ECharts

配置要点:
  - X轴: time 类型, 自动格式化日期
  - Y轴: 双轴 (左: 日积分柱状, 右: 累积积分折线)
  - tooltip: 显示日期 + 日积分 + 累积积分 + 当日事件摘要
  - markLine: 标注等级门槛线 (Bronze/Silver/Gold/Platinum)
  - visualMap: 事件标注点使用颜色区分类型
  - dataZoom: 底部滑块支持缩放

数据转换:
  API返回的 points[] → ECharts dataset
  events[] → markPoint 标注
```

### 7.3 BehaviorEventLog 组件

```
Props:
  events: Array<{
    timestamp: String,
    points: Number,       // 正数=加分, 负数=扣分
    type: String,         // login|match_view|feedback|deal|penalty
    description: String
  }>
  filter: String?         // 事件类型筛选

特性:
  - 虚拟滚动 (事件可能几百条)
  - 按天分组显示
  - 加分绿色 +, 扣分红色 -
  - 类型图标区分
```

---

## 8. 担保链可视化

### 8.1 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  担保网络                                          [返回]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                        │ │
│  │       🧑‍💼 张担保人  ───────────┐                     │ │
│  │        (Platinum 810)          │                     │ │
│  │                                ▼                      │ │
│  │       🧑‍💼 李担保人  ─────── 👤 当前用户              │ │
│  │        (Gold 680)             │  (Gold 672)          │ │
│  │                                │                      │ │
│  │       🧑‍💼 王担保人  ───────────┘                     │ │
│  │        (Silver 420)          ┌──────────┐            │ │
│  │                               │          │            │ │
│  │                               ▼          ▼            │ │
│  │       🧑‍💼 被我担保人A     🧑‍💼 被我担保人B          │ │
│  │        (Bronze 180)        (Silver 320)              │ │
│  │                                                        │ │
│  │        ───── 二级担保链 ─────                           │ │
│  │        🧑‍💼 张的担保人A ─→ 张 ─→ 我        │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─────────────┐  ┌──────────────────────────────────────┐ │
│  │ 统计面板     │  │ 节点筛选                            │ │
│  │ 担保人: 3   │  │ [☑ 直接担保人] [☑ 间接担保人]       │ │
│  │ 被担保: 2   │  │ [☑ 我担保的]   [☐ 上级担保链]       │ │
│  │ 网络深度: 2 │  │                                       │ │
│  │ 均分: 735    │  │ 等级颜色:                            │ │
│  └─────────────┘  │  💎 🥇 🥈 🥉                         │ │
│                    └──────────────────────────────────────┘ │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 担保人列表                                              │ │
│  │                                                        │ │
│  │ 🥇 张三 | Platinum 810 | 2026-03-15 为您担保          │ │
│  │   → 来自: 李四的担保链 (二级)                          │ │
│  │ 🥇 李四 | Gold 680     | 2026-01-10 为您担保          │ │
│  │ 🥉 王五 | Silver 420   | 2025-11-20 为您担保          │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 操作面板                                                │ │
│  │                                                        │ │
│  │ [🔗 邀请担保]  [🤝 为他人担保]  [📋 担保记录]         │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 GuaranteeGraph 组件技术方案

```
技术栈: ECharts Graph / D3.js force-directed graph

推荐方案: ECharts Graph (更易集成)

配置要点:
  - type: 'graph'
  - layout: 'force' (力导向布局)
  - roam: true (支持拖拽缩放)
  - nodes[].itemStyle.color: 按信任等级着色
  - nodes[].symbolSize: 按信任分大小 (50-100)
  - edges[].lineStyle.curveness: 担保方向曲线
  - edges[].arrow: 指向被担保人
  - emphasis.focus: 'adjacency' (悬停高亮关联节点)
  - tooltip: 显示名称 + 信任分 + 等级 + 担保日期

力导向参数:
  - repulsion: 300 (节点斥力)
  - edgeLength: [150, 300]
  - gravity: 0.1
  - friction: 0.1
```

### 8.3 担保关系表 (后端存储方案)

```sql
-- 担保关系表
CREATE TABLE trust_guarantees (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    guarantor_id  BIGINT NOT NULL,      -- 担保人
    guaranteed_id BIGINT NOT NULL,      -- 被担保人
    status        ENUM('active','revoked') DEFAULT 'active',
    reason        VARCHAR(500),         -- 担保理由
    created_at    DATETIME DEFAULT NOW(),
    revoked_at    DATETIME,
    UNIQUE KEY uk_relation (guarantor_id, guaranteed_id)
);

-- 行为积分流水表
CREATE TABLE trust_behavior_points (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       BIGINT NOT NULL,
    points        INT NOT NULL,          -- 正=加分, 负=扣分
    event_type    VARCHAR(50) NOT NULL,  -- login|match_view|feedback|...
    description   VARCHAR(200),
    created_at    DATETIME DEFAULT NOW(),
    INDEX idx_user_time (user_id, created_at)
);

-- 信任分快照表 (用于历史回溯)
CREATE TABLE trust_score_snapshots (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       BIGINT NOT NULL,
    trust_score   INT NOT NULL,
    breakdown_json JSON,                -- 三维度分解的 JSON 快照
    snapshot_date DATE NOT NULL,
    UNIQUE KEY uk_user_date (user_id, snapshot_date)
);
```

---

## 9. 组件树与路由

### 9.1 Vue Route 配置

```javascript
const routes = [
  {
    path: '/trust',
    name: 'TrustDashboard',
    component: () => import('@/views/trust/TrustDashboard.vue'),
    meta: { title: '信任中心', icon: 'shield' },
    children: [
      {
        path: 'breakdown',
        name: 'TrustBreakdown',
        component: () => import('@/views/trust/TrustBreakdownView.vue'),
        meta: { title: '信任分解' },
      },
      {
        path: 'behavior',
        name: 'BehaviorHistory',
        component: () => import('@/views/trust/BehaviorHistoryView.vue'),
        meta: { title: '行为积分' },
      },
      {
        path: 'guarantee',
        name: 'GuaranteeNetwork',
        component: () => import('@/views/trust/GuaranteeNetworkView.vue'),
        meta: { title: '担保网络' },
      },
      {
        path: 'settings',
        name: 'TrustSettings',
        component: () => import('@/views/trust/TrustSettings.vue'),
        meta: { title: '信任设置' },
      },
    ],
  },
]
```

### 9.2 Sidebar Entry

```javascript
// 侧边栏导航菜单
{
  key: 'trust',
  icon: '🛡️',
  label: '信任中心',
  children: [
    { key: 'trust-dashboard', label: '信任总览', route: '/trust' },
    { key: 'trust-breakdown', label: '信任分解', route: '/trust/breakdown' },
    { key: 'trust-behavior', label: '行为积分', route: '/trust/behavior' },
    { key: 'trust-guarantee', label: '担保网络', route: '/trust/guarantee' },
  ],
}
```

### 9.3 状态管理 (Vuex / Pinia)

```javascript
// store/trust.js
export const useTrustStore = defineStore('trust', {
  state: () => ({
    score: null,           // 信任分总览
    breakdown: null,       // 分解数据
    behaviorHistory: [],   // 行为历史
    guaranteeNetwork: {},  // 担保网络
    loading: false,
    lastFetched: null,
  }),
  getters: {
    trustLevel: (state) => {
      if (!state.score) return null
      if (state.score <= 250) return 'bronze'
      if (state.score <= 500) return 'silver'
      if (state.score <= 750) return 'gold'
      return 'platinum'
    },
    nextLevelThreshold: (state) => {
      if (state.score <= 250) return 251
      if (state.score <= 500) return 501
      if (state.score <= 750) return 751
      return null // 已满级
    },
  },
  actions: {
    async fetchTrustScore() { /* GET /api/trust/score */ },
    async fetchBehaviorHistory(days = 30) { /* GET /api/trust/behavior/history */ },
    async fetchGuaranteeNetwork(depth = 3) { /* GET /api/trust/guarantee/network */ },
    async refreshScore() { /* POST /api/trust/refresh */ },
  },
})
```

---

## 10. 与三塔模型的集成关系

### 10.1 现有资产复用

| 信任分维度 | 复用模块 | 复用方式 |
|-----------|---------|---------|
| 身份认证 | EnterpriseTower (企业特征) | 复用 `registered_capital`, `credit_rating` 等特征 |
| 行为信用 | BehaviorTower (行为序列) | 复用行为序列编码器 + Transformer 输出 |
| 行为信用 | OnlineWeightOptimizer | 复用在线学习机制动态调整行为信用权重 |
| 担保网络 | Knowledge Graph Builder | 复用 Neo4j 企业关系图，扩展担保关系边 |
| 匹配分数 | MatchingScorer | 用户信任分可作为 MatchingScorer 的辅助特征输入 |

### 10.2 TrustService 实现架构

```
TrustService (新模块)
  ├── IdentityScorer
  │     └── 直接查询 users / business_cards 表计算规则分数
  │
  ├── BehaviorScorer
  │     ├── 查询 behavior_points 流水表
  │     └── 可选: 调用 BehaviorTower 计算行为嵌入质量
  │
  ├── GuaranteeScorer
  │     ├── 查询 trust_guarantees 表
  │     ├── 查询 Neo4j 知识图谱中的担保关系
  │     └── 递归计算担保链深度和平均信用
  │
  ├── TrustAggregator
  │     ├── 加权汇总三维度分数
  │     ├── 映射等级
  │     └── 生成提升建议
  │
  └── TrustCache
        └── Redis 缓存信任分结果 (TTL=1h)
```

### 10.3 与 MatchingScorer 的协同

信任分可作为 MatchingScorer 的**辅助特征**输入，提升匹配质量：

```python
# 在 MatchingAPI.predict 中集成信任分
def predict_with_trust(self, user_info, candidates, ...):
    # 1. 计算匹配分数
    base_results = self.predict(user_info, candidates, ...)

    # 2. 获取用户信任分
    trust_score = trust_service.get_score(user_info['user_id'])

    # 3. 信任分归一化到 [0, 0.2] 区间, 作为 boost
    trust_boost = trust_score / 5000  # 1000 / 5000 = 0.2 上限

    # 4. 加权: final_score = (1 - λ) × match_score + λ × trust_boost
    lambda_ = 0.15  # 信任分占 15% 权重
    for r in base_results:
        r.score = (1 - lambda_) * r.score + lambda_ * trust_boost

    return base_results
```

---

## 11. 演进路线

### T0: MVP (2周)

| 任务 | 工作量 | 产出 |
|------|-------|------|
| 创建 trust_guarantees 表 + behavior_points 表 | 0.5d | 数据库迁移 |
| 实现 TrustService 规则评分 | 2d | 身份认证+行为信用规则计算 |
| 实现 3 个 API 端点 | 1d | `GET /score`, `GET /behavior/history`, `POST /refresh` |
| 实现 TrustDashboard 页面 | 2d | 环形仪表盘 + 三维度卡片 |
| 实现 BehaviorHistory 页面 | 1.5d | ECharts 趋势图 + 流水 |
| 实现 TrustBreakdown 页面 | 1d | 分解面板 |
| **总计** | **8d** | |

### T1: 担保网络 (1周)

| 任务 | 工作量 | 产出 |
|------|-------|------|
| 实现担保 API 端点 + Neo4j 集成 | 1.5d | `GET /guarantee/network` |
| 实现 GuaranteeNetwork 页面 | 2d | D3.js / ECharts 图谱 |
| 邀请担保/为他人担保操作 | 1d | 交互功能 |
| **总计** | **4.5d** | |

### T2: 三塔增强 (1周)

| 任务 | 工作量 | 产出 |
|------|-------|------|
| 信任分作为 MatchingScorer 辅助特征 | 1d | 匹配质量提升 |
| BehaviorTower 嵌入质量接入信任分 | 1d | 行为信用分更精准 |
| 行为积分实时事件流 | 1d | Kafka / 消息队列 |
| 信任分历史趋势回溯 | 1d | 月度报告 |
| **总计** | **4d** | |

### T3: 智能化 (2周)

| 任务 | 工作量 | 产出 |
|------|-------|------|
| LLM 生成信任分提升建议 | 2d | 个性化建议 |
| 信任分异常检测告警 | 1d | 信任风险预警 |
| 信用排行榜 (可选) | 1d | 社区激励 |
| 信任分联邦 (跨平台) | 2d | Web3 信用互认 |
| **总计** | **6d** | |

---

## 附录

### A. 技术依赖

| 库 | 用途 | 版本要求 |
|----|------|---------|
| ECharts 5+ | 图表可视化 (趋势图/热力图) | ^5.4.0 |
| D3.js / ECharts Graph | 关系图谱 (担保链) | ECharts 内置 |
| Element Plus / Ant Design Vue | UI 组件库 | 2.x+ |
| Pinia | 状态管理 | 2.x+ |
| Vue Router | 路由 | 4.x+ |

### B. 颜色系统

```scss
// 信任等级颜色
$trust-bronze:  #cd7f32;   // hsl(30, 60%, 55%)
$trust-silver:  #a8b8cc;   // hsl(210, 50%, 65%)
$trust-gold:    #d4a017;   // hsl(45, 85%, 55%)
$trust-platinum:#7b5ea7;   // hsl(260, 70%, 60%)

// 三维度颜色
$dimension-identity:  #4A90D9;   // 蓝色
$dimension-behavior:  #50B86C;   // 绿色
$dimension-guarantee: #F5A623;   // 橙色
```

### C. 关键组件数据接口 (TypeScript)

```typescript
interface TrustScoreResponse {
  user_id: number
  trust_score: number        // 0-1000
  trust_level: 'bronze' | 'silver' | 'gold' | 'platinum'
  level_progress: number     // 0-1
  next_level: string
  next_level_at: number
  breakdown: TrustBreakdown
  updated_at: string
}

interface TrustBreakdown {
  identity: ScoreDimension
  behavior: ScoreDimension
  guarantee: ScoreDimension
}

interface ScoreDimension {
  score: number
  max: number
  weight: number
  detail: Record<string, number>
}

interface BehaviorPoint {
  date: string
  score: number
  events: BehaviorEvent[]
}

interface BehaviorEvent {
  timestamp: string
  type: string
  points: number
  description: string
}

interface GuaranteeNode {
  id: number
  name: string
  type: 'self' | 'guarantor' | 'guaranteed' | 'chain'
  trust_score: number
  trust_level: string
  relation: 'direct' | 'indirect'
  depth: number
}

interface GuaranteeEdge {
  source: number
  target: number
  type: 'guarantee' | 'recommend'
  created_at: string
  weight: number
}
```

---

*本文档为信任评分前端展示的设计提案，具体实现时可结合产品PRD和技术资源调整优先级。*
