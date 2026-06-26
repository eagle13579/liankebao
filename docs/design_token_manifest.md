# 链客宝 Design Token 体系定义

> 参考: Linear Design · Vercel Geist · shadcn/ui 设计语言
> 版本: v1.0 · 2026-06-25
> 状态: ✅ 初始定义

---

## 目录

1. [概述](#1-概述)
2. [色彩体系](#2-色彩体系)
3. [间距体系](#3-间距体系)
4. [字体体系](#4-字体体系)
5. [阴影 / 圆角 / 动画](#5-阴影--圆角--动画)
6. [暗色模式映射表](#6-暗色模式映射表)
7. [当前硬编码扫描摘要](#7-当前硬编码扫描摘要)

---

## 1. 概述

### 1.1 为什么需要 Design Token

当前项目（`D:\chainke-full\src`）中**不存在统一的设计令牌文件**。所有样式均通过 Tailwind 4 的 utility class 和内联 `style` 分散在各 `.tsx` 文件中，导致：

- **颜色不统一** — 同一种蓝色同时使用了 `blue-600`、`#2563eb`、`bg-blue-500` 等不同写法
- **品牌色重复** — 同一个渐变色（如 `from-blue-500 via-cyan-500 to-purple-600`）在 LoginPage 中写了两次
- **缺少暗色模式** — 当前仅 LoginPage 实现了暗色背景（`bg-slate-950`），其余页面（BusinessCardPage、AIChatWidget、NLSearchWidget）全部使用浅色主题
- **间距无约束** — 硬编码了 `p-3`、`p-4`、`p-5`、`p-6`、`p-8` 等各种值

### 1.2 Token 层级

```
├── 全局 Token (global)       — 无主题依赖的底层值
├── 语义 Token (semantic)     — 关联业务含义的映射
└── 组件 Token (component)    — 组件的专属变量（后续扩展）
```

### 1.3 命名规范

```
--ck-<category>-<property>-<variant>
   │        │          │
   │        │          └── 变体名: 50 / 100 / 200 / DEFAULT / hover / active
   │        └── 属性: color / spacing / radius / shadow / font / animate
   └── 命名空间: 链客宝
```

示例: `--ck-color-primary-DEFAULT`、`--ck-spacing-4`、`--ck-radius-md`

---

## 2. 色彩体系

### 2.1 主色 (Brand)

| Token | 值 | 用途 | 当前代码例 |
|-------|-----|------|-----------|
| `--ck-color-brand-50` | `#EFF6FF` | 极浅背景 | `bg-blue-50` / `#EFF6FF` |
| `--ck-color-brand-100` | `#DBEAFE` | 标签/提示背景 | `bg-blue-100` |
| `--ck-color-brand-200` | `#BFDBFE` | 边框/浅态 | `border-blue-200` |
| `--ck-color-brand-300` | `#93C5FD` | 悬停边框 | `hover:ring-blue-300` |
| `--ck-color-brand-400` | `#60A5FA` | 关联色 | `focus:ring-blue-400` |
| `--ck-color-brand-500` | `#3B82F6` | 主按钮/链接 (DEFAULT) | `bg-blue-500` / ABACC `#3B82F6` |
| `--ck-color-brand-600` | `#2563EB` | 主按钮悬停/激活 | `bg-blue-600 hover:bg-blue-700` |
| `--ck-color-brand-700` | `#1D4ED8` | 深色态 | `hover:text-blue-700` |
| `--ck-color-brand-800` | `#1E40AF` | — | |
| `--ck-color-brand-900` | `#1E3A8A` | — | |

> **说明**: 当前项目以 blue-500/600 为主色，AIChatWidget 和 TensionScoreWidget 额外使用了 purple-600，NLSearchWidget 使用了 indigo-600。**建议统一为 blue 系主色**，purple / indigo 降级为辅助色。

### 2.2 辅助色 (Secondary)

紫色 — 用于 AI 对话、张力评分、匹配评价等智能业务上下文。

| Token | 值 | 来源 |
|-------|-----|------|
| `--ck-color-secondary-50` | `#FAF5FF` | `bg-purple-50` |
| `--ck-color-secondary-100` | `#F3E8FF` | `border-purple-100` |
| `--ck-color-secondary-200` | `#E9D5FF` | `border-purple-200` |
| `--ck-color-secondary-400` | `#C084FC` | `focus:ring-purple-400` |
| `--ck-color-secondary-500` | `#A855F7` | `bg-purple-500` |
| `--ck-color-secondary-600` | `#9333EA` | `bg-purple-600` (AI Chat 主色) |
| `--ck-color-secondary-700` | `#7E22CE` | `hover:bg-purple-700` |

靛蓝 — 用于搜索相关上下文。

| Token | 值 | 来源 |
|-------|-----|------|
| `--ck-color-accent-50` | `#EEF2FF` | `bg-indigo-50` |
| `--ck-color-accent-100` | `#E0E7FF` | `border-indigo-100` |
| `--ck-color-accent-400` | `#818CF8` | `focus:ring-indigo-400` |
| `--ck-color-accent-500` | `#6366F1` | `text-indigo-500` (spin) |
| `--ck-color-accent-600` | `#4F46E5` | `bg-indigo-600` (搜索按钮) |
| `--ck-color-accent-700` | `#4338CA` | `hover:bg-indigo-700` |

### 2.3 金色点缀 (Gold Accent)

用于"暖金尊享"模板及高级VIP标识。

| Token | 值 |
|-------|-----|
| `--ck-color-gold-300` | `#FCD34D` |
| `--ck-color-gold-400` | `#FBBF24` |
| `--ck-color-gold-500` | `#F59E0B` |
| `--ck-color-gold-600` | `#D97706` |

> 当前代码在 TemplateSelector 中使用 `from-amber-400 via-orange-400 to-yellow-500` 渐变。

### 2.4 中性色 (Neutral / Gray)

| Token | 值 | 用途 | 当前代码例 |
|-------|-----|------|-----------|
| `--ck-color-neutral-50` | `#F9FAFB` | 极浅灰背景 | `bg-gray-50` |
| `--ck-color-neutral-100` | `#F3F4F6` | 分割线/卡片背景 | `border-gray-100 bg-gray-100` |
| `--ck-color-neutral-200` | `#E5E7EB` | 边框(默认) | `border-gray-200` |
| `--ck-color-neutral-300` | `#D1D5DB` | 输入框边框 | `border-gray-300` |
| `--ck-color-neutral-400` | `#9CA3AF` | 辅助文本/占位符 | `text-gray-400 placeholder-gray-400` |
| `--ck-color-neutral-500` | `#6B7280` | 次要文本 | `text-gray-500` |
| `--ck-color-neutral-600` | `#4B5563` | 正文/按钮文字 | `text-gray-600` |
| `--ck-color-neutral-700` | `#374151` | 标题 | `text-gray-700` |
| `--ck-color-neutral-800` | `#1F2937` | 强调标题 | `text-gray-800` |
| `--ck-color-neutral-900` | `#111827` | 极致标题 | `text-gray-900` |

### 2.5 语义色 (Semantic)

| Token | 值 | 用途 | 当前代码例 |
|-------|-----|------|-----------|
| `--ck-color-success-50` | `#F0FDF4` | 成功背景 | `bg-green-50` |
| `--ck-color-success-100` | `#DCFCE7` | 成功标签 | `bg-green-100 text-green-700` |
| `--ck-color-success-500` | `#22C55E` | 成功图标 | |
| `--ck-color-success-600` | `#16A34A` | 成功文字 | `text-green-600` |
| `--ck-color-success-700` | `#15803D` | 成功强调 | `text-green-700` |
| `--ck-color-warning-50` | `#FFFBEB` | 警告背景 | `bg-amber-50` / `bg-yellow-50` |
| `--ck-color-warning-100` | `#FEF3C7` | 警告标签 | `text-yellow-700 bg-yellow-100` |
| `--ck-color-warning-500` | `#F59E0B` | 警告图标/评分中 | |
| `--ck-color-warning-600` | `#D97706` | 警告文字 | |
| `--ck-color-error-50` | `#FEF2F2` | 错误背景 | `bg-red-50` |
| `--ck-color-error-100` | `#FEE2E2` | 错误标签 | `bg-red-100 text-red-700` |
| `--ck-color-error-200` | `#FECACA` | 错误边框 | `border-red-200` |
| `--ck-color-error-500` | `#EF4444` | 错误图标/文字 | `text-red-500` |
| `--ck-color-error-600` | `#DC2626` | 错误强调 | `text-red-600` |
| `--ck-color-error-700` | `#B91C1C` | 错误悬停 | `hover:text-red-700` |

### 2.6 渐变 (Gradients)

| Token | 值 | 用途 |
|-------|-----|------|
| `--ck-gradient-brand` | `linear-gradient(135deg, #3B82F6, #06B6D4, #9333EA)` | 品牌渐变（登录按钮/Logo） |
| `--ck-gradient-hero` | `linear-gradient(180deg, #F9FAFB, #FFFFFF)` | 页面背景渐变 |
| `--ck-gradient-dark` | `linear-gradient(135deg, #020617, #1E293B)` | 暗色主题渐变（Splash） |

> 当前 LoginPage 使用 `from-blue-500 via-cyan-500 to-purple-600`，需要对齐为统一的品牌渐变。

---

## 3. 间距体系

### 3.1 基础间距单位

基础单位 `4px`，遵循 4px 网格法则。

| Token | 值 | Tailwind 等价 | 用途 |
|-------|-----|--------------|------|
| `--ck-spacing-1` | `4px` | `gap-1` / `p-1` | 微间距（标签间隔） |
| `--ck-spacing-2` | `8px` | `gap-2` / `p-2` | 紧凑元素间距 |
| `--ck-spacing-3` | `12px` | `gap-3` / `p-3` | 卡片内间距 |
| `--ck-spacing-4` | `16px` | `gap-4` / `p-4` | **默认间距**（卡片 padding） |
| `--ck-spacing-5` | `20px` | `gap-5` / `p-5` | 表单/区块间距 |
| `--ck-spacing-6` | `24px` | `gap-6` / `p-6` | 大区块间距 |
| `--ck-spacing-8` | `32px` | `gap-8` / `p-8` | 页面容器 |
| `--ck-spacing-10` | `40px` | `gap-10` / `p-10` | 标题区 |
| `--ck-spacing-12` | `48px` | `gap-12` / `p-12` | 大段间隔 |
| `--ck-spacing-16` | `64px` | `gap-16` / `p-16` | 章节间距 |

> **当前代码缺乏约束**: 同时使用了 `p-3`, `p-4`, `p-5`, `p-6`, `p-8`, `p-10`。建议标准化:
> - 卡片内间距: `--ck-spacing-4` (16px) 或 `--ck-spacing-5` (20px)
> - 页面侧边距: `--ck-spacing-4` (16px)
> - 大标题区: `--ck-spacing-8` (32px) / `--ck-spacing-12` (48px)

### 3.2 布局宽度

| Token | 值 | 用途 |
|-------|-----|------|
| `--ck-width-content` | `56rem` (896px) | 内容区最大宽（当前 `max-w-4xl`） |
| `--ck-width-wide` | `64rem` (1024px) | 宽内容区（`max-w-5xl`） |
| `--ck-width-modal` | `28rem` (448px) | 弹窗宽度（`max-w-md`） |

---

## 4. 字体体系

### 4.1 字重 (Font Weight)

| Token | 值 | Tailwind | 用途 |
|-------|-----|----------|------|
| `--ck-font-weight-normal` | `400` | `font-normal` | 正文 |
| `--ck-font-weight-medium` | `500` | `font-medium` | 标签/按钮 |
| `--ck-font-weight-semibold` | `600` | `font-semibold` | 子标题 |
| `--ck-font-weight-bold` | `700` | `font-bold` | 大标题/Logo |

### 4.2 字号 / 行高 (Font Size / Line Height)

| Token | 字号 | 行高 | Tailwind | 用途 |
|-------|------|------|----------|------|
| `--ck-font-size-2xs` | `10px` | `14px` | `text-[10px]` | 标签/微提示 |
| `--ck-font-size-xs` | `12px` | `16px` | `text-xs` | 辅助文字/标签 |
| `--ck-font-size-sm` | `14px` | `20px` | `text-sm` | **正文/按钮** |
| `--ck-font-size-base` | `16px` | `24px` | `text-base` | 段落正文 |
| `--ck-font-size-lg` | `18px` | `28px` | `text-lg` | 小标题/导航 |
| `--ck-font-size-xl` | `20px` | `28px` | `text-xl` | 卡片标题 |
| `--ck-font-size-2xl` | `24px` | `32px` | `text-2xl` | 页面标题 |
| `--ck-font-size-3xl` | `30px` | `36px` | `text-3xl` | Hero 标题 |
| `--ck-font-size-4xl` | `36px` | `40px` | `text-4xl` | 大 Hero |

> **注意**: 当前代码大量使用 `text-[10px]` 和 `text-[11px]` 自定义字号，建议统一为 `--ck-font-size-2xs` (10px)。

### 4.3 字族 (Font Family)

| Token | 值 |
|-------|-----|
| `--ck-font-sans` | `'Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Noto Sans SC', sans-serif` |
| `--ck-font-mono` | `'JetBrains Mono', 'SF Mono', 'Fira Code', monospace` |

> 当前代码无统一字族定义，各页面默认使用 system-ui。

---

## 5. 阴影 / 圆角 / 动画

### 5.1 阴影 (Box Shadow)

| Token | 值 | Tailwind | 用途 |
|-------|-----|----------|------|
| `--ck-shadow-sm` | `0 1px 2px 0 rgb(0 0 0 / 0.05)` | `shadow-sm` | 轻微浮起 |
| `--ck-shadow-md` | `0 4px 6px -1px rgb(0 0 0 / 0.1)` | `shadow-md` | 卡片默认 |
| `--ck-shadow-lg` | `0 10px 15px -3px rgb(0 0 0 / 0.1)` | `shadow-lg` | 弹窗/下拉 |
| `--ck-shadow-xl` | `0 20px 25px -5px rgb(0 0 0 / 0.1)` | `shadow-xl` | 名片预览 |
| `--ck-shadow-2xl` | `0 25px 50px -12px rgb(0 0 0 / 0.25)` | `shadow-2xl` | 聊天窗口/Modal |
| `--ck-shadow-glow-brand` | `0 0 20px rgb(59 130 246 / 0.3)` | `shadow-blue-500/20` | 按钮发光 |

### 5.2 圆角 (Border Radius)

| Token | 值 | Tailwind | 用途 |
|-------|-----|----------|------|
| `--ck-radius-sm` | `6px` | `rounded-md` | 输入框/小控件 |
| `--ck-radius-md` | `8px` | `rounded-lg` | 按钮/卡片内部 |
| `--ck-radius-lg` | `12px` | `rounded-xl` | **默认卡片圆角** |
| `--ck-radius-xl` | `16px` | `rounded-2xl` | 大卡片/弹窗 |
| `--ck-radius-2xl` | `24px` | `rounded-3xl` | 毛玻璃容器 |
| `--ck-radius-full` | `9999px` | `rounded-full` | 圆形/标签 |

> **当前代码使用**: `rounded-md` (6px), `rounded-lg` (8px), `rounded-xl` (12px), `rounded-2xl` (16px), `rounded-3xl` (24px)。建议标准化为上面的层级。

### 5.3 动画 / 过渡 (Animation & Transition)

| Token | 值 | 用途 |
|-------|-----|------|
| `--ck-transition-fast` | `150ms ease` | 微交互（hover） |
| `--ck-transition-base` | `200ms ease` | **默认过渡**（当前使用 `duration-200`） |
| `--ck-transition-slow` | `300ms ease-out` | 面板展开/切换 |
| `--ck-transition-xslow` | `500ms ease-out` | 进度条/页面过渡 |
| `--ck-transition-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | 弹性动效（缩放/弹出） |

| 动画名称 | 描述 | 当前代码 |
|----------|------|---------|
| `spin` | 旋转（loading） | `animate-spin` |
| `pulse` | 脉冲（进度） | `animate-pulse` |
| `slide-in-bottom` | 从下进入 | `animate-in slide-in-from-bottom-4` |
| `fade-in` | 淡入 | `fade-in` |
| `scale-in` | 缩放进入 | `hover:scale-105` |

---

## 6. 暗色模式映射表

> **当前状态**: 项目中仅 LoginPage 实现了暗色背景（`bg-slate-950`），其余组件（BusinessCardPage、AIChatWidget、NLSearchWidget、TensionScoreWidget）使用浅色主题。**暗色模式尚未系统性实现**。

### 6.1 语义映射规则

```
── 浅色模式 (Light) ──→ 深色模式 (Dark)
── CSS 变量方案 ──→ 使用 data-theme="dark" 或 prefers-color-scheme
```

| 语义角色 | Light Token | Light 值 | Dark Token | Dark 值 |
|----------|-------------|----------|------------|---------|
| 页面背景 | `--ck-color-bg-page` | `#FFFFFF` | `--ck-color-bg-page-dark` | `#0F172A` |
| 卡片背景 | `--ck-color-bg-card` | `#FFFFFF` | `--ck-color-bg-card-dark` | `#1E293B` |
| 卡片边框 | `--ck-color-border-card` | `#E5E7EB` | `--ck-color-border-card-dark` | `#334155` |
| 输入框背景 | `--ck-color-bg-input` | `#FFFFFF` | `--ck-color-bg-input-dark` | `#1E293B` |
| 输入框边框 | `--ck-color-border-input` | `#D1D5DB` | `--ck-color-border-input-dark` | `#475569` |
| 标题文字 | `--ck-color-text-heading` | `#1F2937` | `--ck-color-text-heading-dark` | `#F1F5F9` |
| 正文文字 | `--ck-color-text-body` | `#4B5563` | `--ck-color-text-body-dark` | `#CBD5E1` |
| 辅助文字 | `--ck-color-text-muted` | `#9CA3AF` | `--ck-color-text-muted-dark` | `#64748B` |
| 主色默认 | `--ck-color-brand-500` | `#3B82F6` | `--ck-color-brand-500-dark` | `#60A5FA` |
| 主色悬停 | `--ck-color-brand-600` | `#2563EB` | `--ck-color-brand-600-dark` | `#3B82F6` |
| 成功 | `--ck-color-success-500` | `#22C55E` | `--ck-color-success-500-dark` | `#4ADE80` |
| 警告 | `--ck-color-warning-500` | `#F59E0B` | `--ck-color-warning-500-dark` | `#FBBF24` |
| 错误 | `--ck-color-error-500` | `#EF4444` | `--ck-color-error-500-dark` | `#F87171` |
| 主渐变 | `--ck-gradient-brand` | blue→cyan→purple | `--ck-gradient-brand-dark` | blue→cyan→purple (更亮) |
| 页面渐变 | `--ck-gradient-hero` | gray-50→white | `--ck-gradient-hero-dark` | slate-950→slate-900 |

### 6.2 暗色模式具体映射

| 卡片 | Light | Dark |
|------|-------|------|
| 卡片背景 | `bg-white` (ND) | `bg-slate-900` |
| 卡片边框 | `border-gray-200` (ND) | `border-slate-700` |
| 标题 | `text-gray-800` (ND) | `text-slate-100` |
| 正文 | `text-gray-500` (ND) | `text-slate-400` |
| 辅助标签背景 | `bg-blue-50` | `bg-blue-900/30` |
| 辅助标签文字 | `text-blue-600` | `text-blue-300` |
| 分割线 | `border-gray-100` | `border-slate-700` |
| 头部背景 | `bg-white/80` | `bg-slate-900/80` |
| 头部边框 | `border-gray-100` | `border-slate-700` |

| 输入/表单 | Light | Dark |
|-----------|-------|------|
| 输入框背景 | `bg-white` | `bg-slate-800` |
| 输入框边框 | `border-gray-200` | `border-slate-600` |
| 输入框聚焦环 | `ring-blue-500/50` | `ring-blue-400/50` |
| 占位符 | `placeholder-slate-500` | `placeholder-slate-400` |

| 导航/标签 | Light | Dark |
|-----------|-------|------|
| 活动标签背景 | `bg-white` | `bg-slate-800` |
| 活动标签边框 | `border-gray-200` | `border-slate-600` |
| 非活标签文字 | `text-gray-500` | `text-slate-400` |
| 非活标签 hover | `hover:text-gray-700` | `hover:text-slate-200` |

| 交互元素 | Light | Dark |
|---------|-------|------|
| Toast 背景 | `bg-gray-800` | `bg-gray-700` |
| Toast 文字 | `text-white` | `text-white` |
| 禁用按钮 | `bg-gray-200 text-gray-400` | `bg-slate-700 text-slate-500` |
| 阴影 | `shadow-{sm/md/lg/xl}` | `shadow-{sm/md/lg/xl} shadow-black/20` |

### 6.3 暗色模式实现策略

```css
/* 方案: data-theme 属性 + CSS 变量 */
:root,
[data-theme='light'] {
  --ck-color-bg-page: #FFFFFF;
  --ck-color-bg-card: #FFFFFF;
  --ck-color-text-heading: #1F2937;
  /* ... 其余 light 变量 */
}

[data-theme='dark'] {
  --ck-color-bg-page: #0F172A;
  --ck-color-bg-card: #1E293B;
  --ck-color-text-heading: #F1F5F9;
  /* ... 其余 dark 变量 */
}

/* 组件中统一使用 var() */
.card {
  background: var(--ck-color-bg-card);
  border-color: var(--ck-color-border-card);
}
```

---

## 7. 当前硬编码扫描摘要

基于对 `src/` 目录下所有 `.tsx` 文件的扫描结果。

### 7.1 颜色不一致

| 问题 | 出现位置 | 建议 |
|------|---------|------|
| `bg-blue-500` vs `#2563EB` vs `bg-blue-600` | App.tsx:23, LoginPage, BusinessCardPage | 统一为 `--ck-color-brand-500/600` |
| `bg-purple-600` (AI对话) vs `bg-indigo-600` (搜索) vs `bg-blue-600` (其他) | AIChatWidget, NLSearchWidget, 各主按钮 | 统一主色为 blue，purple/indigo 为辅助 |
| 内联 `#666` `#333` `#f3f4f6` | App.tsx:21-26 | 替换为 token 变量 |
| `text-indigo-500` 作为 spin 颜色 | NLSearchWidget:378 | 统一为 brand-500 |

### 7.2 间距散乱

| 值 | 出现频率 | 标准化建议 |
|----|---------|-----------|
| `p-3` (12px) | 高频 | 卡片内紧凑间距 → `--ck-spacing-3` |
| `p-4` (16px) | 高频 | **默认卡片 padding** → `--ck-spacing-4` |
| `p-5` (20px) | 次高频 | ABACC 卡片 等 → `--ck-spacing-5` |
| `p-6` (24px) | 偶用 | App.tsx home → `--ck-spacing-6` |
| `p-8` (32px) | 偶用 | 大区块 → `--ck-spacing-8` |
| `p-10` (40px) | 低用 | → `--ck-spacing-10` |

### 7.3 圆角不统一

| 值 | 出现 | 建议 |
|----|------|------|
| `rounded-xl` (12px) | 最多卡片 | → `--ck-radius-lg` |
| `rounded-2xl` (16px) | 对话窗口 | → `--ck-radius-xl` |
| `rounded-3xl` (24px) | 毛玻璃容器 | → `--ck-radius-2xl` |
| `rounded-lg` (8px) | 按钮/小卡片 | → `--ck-radius-md` |
| `rounded-md` (6px) | 输入框 | → `--ck-radius-sm` |

### 7.4 暗色模式缺失

| 组件 | 当前主题 | 暗色模式 |
|------|---------|---------|
| LoginPage | ✅ 暗色 (bg-slate-950) | 已实现 |
| BusinessCardPage | ❌ 浅色 (bg-gray-50→white) | 未实现 |
| AIChatWidget | ❌ 浅色 (bg-white bg-gray-50) | 未实现 |
| NLSearchWidget | ❌ 浅色 (bg-white bg-gray-50) | 未实现 |
| TensionScoreWidget | ❌ 浅色 (bg-white) | 未实现 |
| TemplateSelector | ❌ 浅色 (bg-white) | 未实现 |
| DefaultFillPreview | ❌ 浅色 (取决于模板) | 未实现 |
| StepIndicator | ❌ 浅色 (bg-gray-100) | 未实现 |
| MatchResultsPanel | ❌ 浅色 (bg-white) | 未实现 |
| AbaccProductIntro | ❌ 浅色 (from-gray-50) | 未实现 |
| ReviewFormModal | ❌ 浅色 (bg-white) | 未实现 |

---

## 附录 A: Tailwind CSS v4 变量配置参考

在 Tailwind CSS 4 中，通过 `@theme` 指令注册 Design Token：

```css
/* src/index.css 或 app.css */
@import "tailwindcss";

@theme {
  /* ── Colors ── */
  --color-brand-50: #EFF6FF;
  --color-brand-100: #DBEAFE;
  --color-brand-200: #BFDBFE;
  --color-brand-300: #93C5FD;
  --color-brand-400: #60A5FA;
  --color-brand-500: #3B82F6;
  --color-brand-600: #2563EB;
  --color-brand-700: #1D4ED8;
  --color-brand-800: #1E40AF;
  --color-brand-900: #1E3A8A;

  --color-secondary-50: #FAF5FF;
  --color-secondary-100: #F3E8FF;
  --color-secondary-200: #E9D5FF;
  --color-secondary-400: #C084FC;
  --color-secondary-500: #A855F7;
  --color-secondary-600: #9333EA;
  --color-secondary-700: #7E22CE;

  --color-accent-50: #EEF2FF;
  --color-accent-100: #E0E7FF;
  --color-accent-400: #818CF8;
  --color-accent-500: #6366F1;
  --color-accent-600: #4F46E5;
  --color-accent-700: #4338CA;

  --color-gold-300: #FCD34D;
  --color-gold-400: #FBBF24;
  --color-gold-500: #F59E0B;
  --color-gold-600: #D97706;

  --color-success-50: #F0FDF4;
  --color-success-100: #DCFCE7;
  --color-success-500: #22C55E;
  --color-success-600: #16A34A;
  --color-success-700: #15803D;

  --color-warning-50: #FFFBEB;
  --color-warning-100: #FEF3C7;
  --color-warning-500: #F59E0B;
  --color-warning-600: #D97706;

  --color-error-50: #FEF2F2;
  --color-error-100: #FEE2E2;
  --color-error-200: #FECACA;
  --color-error-500: #EF4444;
  --color-error-600: #DC2626;
  --color-error-700: #B91C1C;

  /* ── Spacing ── */
  --spacing: 4px;

  /* ── Font Size ── */
  --font-size-2xs: 10px;
  --font-size-xs: 12px;
  --font-size-sm: 14px;
  --font-size-base: 16px;
  --font-size-lg: 18px;
  --font-size-xl: 20px;
  --font-size-2xl: 24px;
  --font-size-3xl: 30px;
  --font-size-4xl: 36px;

  /* ── Border Radius ── */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-2xl: 24px;
  --radius-full: 9999px;

  /* ── Shadows ── */
  --shadow-glow-brand: 0 0 20px rgba(59, 130, 246, 0.3);

  /* ── Animations ── */
  --animate-spin: spin 1s linear infinite;
  --animate-pulse: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
```

---

*本文档由链客宝设计审查引擎自动扫描生成，结合 Linear + Geist + shadcn/ui 设计语言最佳实践整理。*
