# Tailwind CSS v4 @theme 实施方案

> 基于 `docs/design_token_manifest.md` (v1.0) 的实现规划
> 目标: 建立统一 Design Token 体系，收敛主色分歧，系统性支持暗色模式
> 状态: 📋 规划阶段 · 预计实施: 1 天 (最小可行方案)

---

## 目录

1. [现状分析](#1-现状分析)
2. [基础设施方案](#2-基础设施方案)
3. [@theme 完整配置](#3-theme-完整配置)
4. [globals.css 创建方案](#4-globalscss-创建方案)
5. [主色收敛方案](#5-主色收敛方案)
6. [暗色模式实施策略](#6-暗色模式实施策略)
7. [硬编码替换清单](#7-硬编码替换清单)
8. [1 天最小可行方案](#8-1-天最小可行方案)
9. [后续扩展](#9-后续扩展)

---

## 1. 现状分析

### 1.1 关键发现

| 项目 | 现状 |
|------|------|
| 构建工具 | Vite 6 + React 18 (TypeScript) |
| CSS 入口 | **不存在** — 无 `globals.css` / `index.css` / `app.css` |
| Tailwind | **未安装** — 不在 `package.json` 依赖中，`node_modules` 中无 `tailwindcss` 包 |
| PostCSS | 无 `postcss.config.*` 配置文件 |
| 样式实现 | 全部通过 utility class + 内联 `style` 属性写在 `.tsx` 中 |
| 主色分裂 | `blue`(LoginPage/BusinessCard) / `purple`(AIChatWidget/TensionScore) / `indigo`(NLSearchWidget) |
| 硬编码扫描 | 27 处颜色值硬编码，间距/圆角无统一约束 |
| 暗色模式 | 仅 LoginPage 实现了暗色背景 (bg-slate-950)，其余 8+ 组件为纯浅色 |

### 1.2 组件与当前主色对照

| 组件 | 当前主色 | 使用位置 | 收敛目标 |
|------|---------|---------|---------|
| LoginPage | blue-500/600 | 登录按钮、聚焦环、渐变 | 保留 blue 为主线 |
| BusinessCardPage | blue-600 | 导航标签、按钮、链接 | 保留 blue |
| AIChatWidget | purple-600 | 标题栏、发送按钮、消息气泡、浮动按钮 | → secondary-600 |
| NLSearchWidget | indigo-500/600 | 搜索按钮、聚焦环、标签、spinner | → brand-500/600 (主色) |
| TensionScoreWidget | purple-600 | 分析按钮、聚焦环 | → secondary-600 |
| AbaccProductIntro | #3B82F6 | 卡片颜色定义 (ABACC_CARDS) | → brand-500 |
| TemplateSelector | 多色渐变 | 模板卡片渐变 | 保留模板多样性 |

### 1.3 Tailwind 版本现状

项目**未安装 Tailwind CSS**。代码中大量使用 `bg-blue-500`、`flex`、`min-h-screen` 等 Tailwind 风格 class name，但这些 class 当前**无效**（无 CSS 规则提供它们）。这意味着：

- 页面实际渲染时仅依赖浏览器默认样式 + 内联 `style`
- 安装 Tailwind CSS v4 并引入后，所有 utility class 将立即生效
- 不需要向后兼容的顾虑 — 这是**从零搭建样式体系**的最佳时机

---

## 2. 基础设施方案

### 2.1 安装

```bash
# 在 deploy/docker/ 目录下执行
cd D:\chainke-full\deploy\docker
npm install tailwindcss @tailwindcss/vite
```

### 2.2 Vite 配置更新

在 `deploy/docker/vite.config.ts` 中添加 Tailwind Vite 插件:

```ts
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [
    tailwindcss(),   // 添加在 react() 之前
    react(),
  ],
  // ... 其余配置不变
});
```

### 2.3 入口 CSS 文件

创建 `src/globals.css`:

```css
@import "tailwindcss";

/* 所有 Design Token 定义在下面的 @theme 块中 */
```

### 2.4 挂载到应用

在 `src/main.tsx` 中添加导入:

```ts
import './globals.css';  // 新增
import App from './App';
```

> **注意**: `@tailwindcss/vite` 插件会自动处理 `@import "tailwindcss"`，无需 `postcss.config.*`

---

## 3. @theme 完整配置

### 3.1 完整 @theme 块

以下为 `src/globals.css` 中 `@theme` 配置的完整代码:

```css
@import "tailwindcss";

@theme {
  /* ════════════════════════════════════════════════════
     ── 品牌色 (Brand) — 主色: Blue 系
     ════════════════════════════════════════════════════ */
  --color-brand-50: #EFF6FF;
  --color-brand-100: #DBEAFE;
  --color-brand-200: #BFDBFE;
  --color-brand-300: #93C5FD;
  --color-brand-400: #60A5FA;
  --color-brand-500: #3B82F6;   /* 主色 DEFAULT */
  --color-brand-600: #2563EB;   /* 主色 hover/active */
  --color-brand-700: #1D4ED8;
  --color-brand-800: #1E40AF;
  --color-brand-900: #1E3A8A;

  /* ════════════════════════════════════════════════════
     ── 辅助色系 (Secondary) — Purple 系 (AI/评分上下文)
     ════════════════════════════════════════════════════ */
  --color-secondary-50: #FAF5FF;
  --color-secondary-100: #F3E8FF;
  --color-secondary-200: #E9D5FF;
  --color-secondary-300: #D8B4FE;
  --color-secondary-400: #C084FC;
  --color-secondary-500: #A855F7;
  --color-secondary-600: #9333EA;
  --color-secondary-700: #7E22CE;
  --color-secondary-800: #6B21A8;
  --color-secondary-900: #581C87;

  /* ════════════════════════════════════════════════════
     ── 强调色 (Accent) — Indigo 系 (搜索上下文)
     ════════════════════════════════════════════════════ */
  --color-accent-50: #EEF2FF;
  --color-accent-100: #E0E7FF;
  --color-accent-200: #C7D2FE;
  --color-accent-300: #A5B4FC;
  --color-accent-400: #818CF8;
  --color-accent-500: #6366F1;
  --color-accent-600: #4F46E5;
  --color-accent-700: #4338CA;
  --color-accent-800: #3730A3;
  --color-accent-900: #312E81;

  /* ════════════════════════════════════════════════════
     ── 金色点缀 (Gold)
     ════════════════════════════════════════════════════ */
  --color-gold-300: #FCD34D;
  --color-gold-400: #FBBF24;
  --color-gold-500: #F59E0B;
  --color-gold-600: #D97706;

  /* ════════════════════════════════════════════════════
     ── 中性色 (Neutral)
     ════════════════════════════════════════════════════ */
  --color-neutral-50: #F9FAFB;
  --color-neutral-100: #F3F4F6;
  --color-neutral-200: #E5E7EB;
  --color-neutral-300: #D1D5DB;
  --color-neutral-400: #9CA3AF;
  --color-neutral-500: #6B7280;
  --color-neutral-600: #4B5563;
  --color-neutral-700: #374151;
  --color-neutral-800: #1F2937;
  --color-neutral-900: #111827;

  /* ════════════════════════════════════════════════════
     ── 语义色 (Semantic)
     ════════════════════════════════════════════════════ */
  --color-success-50: #F0FDF4;
  --color-success-100: #DCFCE7;
  --color-success-200: #BBF7D0;
  --color-success-300: #86EFAC;
  --color-success-400: #4ADE80;
  --color-success-500: #22C55E;
  --color-success-600: #16A34A;
  --color-success-700: #15803D;
  --color-success-800: #166534;
  --color-success-900: #14532D;

  --color-warning-50: #FFFBEB;
  --color-warning-100: #FEF3C7;
  --color-warning-200: #FDE68A;
  --color-warning-300: #FCD34D;
  --color-warning-400: #FBBF24;
  --color-warning-500: #F59E0B;
  --color-warning-600: #D97706;
  --color-warning-700: #B45309;
  --color-warning-800: #92400E;
  --color-warning-900: #78350F;

  --color-error-50: #FEF2F2;
  --color-error-100: #FEE2E2;
  --color-error-200: #FECACA;
  --color-error-300: #FCA5A5;
  --color-error-400: #F87171;
  --color-error-500: #EF4444;
  --color-error-600: #DC2626;
  --color-error-700: #B91C1C;
  --color-error-800: #991B1B;
  --color-error-900: #7F1D1D;

  /* ════════════════════════════════════════════════════
     ── 间距 (Spacing)
     基础单位 4px，遵循 4px 网格
     ════════════════════════════════════════════════════ */
  --spacing: 4px;

  /* ════════════════════════════════════════════════════
     ── 字号 / 行高 (Font Size / Line Height)
     ════════════════════════════════════════════════════ */
  --font-size-2xs: 10px;
  --font-size-2xs--line-height: 14px;
  --font-size-xs: 12px;
  --font-size-xs--line-height: 16px;
  --font-size-sm: 14px;
  --font-size-sm--line-height: 20px;
  --font-size-base: 16px;
  --font-size-base--line-height: 24px;
  --font-size-lg: 18px;
  --font-size-lg--line-height: 28px;
  --font-size-xl: 20px;
  --font-size-xl--line-height: 28px;
  --font-size-2xl: 24px;
  --font-size-2xl--line-height: 32px;
  --font-size-3xl: 30px;
  --font-size-3xl--line-height: 36px;
  --font-size-4xl: 36px;
  --font-size-4xl--line-height: 40px;

  /* ════════════════════════════════════════════════════
     ── 字重 (Font Weight)
     ════════════════════════════════════════════════════ */
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;

  /* ════════════════════════════════════════════════════
     ── 字族 (Font Family)
     ════════════════════════════════════════════════════ */
  --font-family-sans: 'Inter', 'system-ui', '-apple-system', 'Segoe UI',
                      'Noto Sans SC', sans-serif;
  --font-family-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;

  /* ════════════════════════════════════════════════════
     ── 圆角 (Border Radius)
     ════════════════════════════════════════════════════ */
  --radius-sm: 6px;     /* 输入框/小控件 (当前 rounded-md) */
  --radius-md: 8px;     /* 按钮/卡片内部 (当前 rounded-lg) */
  --radius-lg: 12px;    /* 默认卡片圆角 (当前 rounded-xl) */
  --radius-xl: 16px;    /* 大卡片/弹窗 (当前 rounded-2xl) */
  --radius-2xl: 24px;   /* 毛玻璃容器 (当前 rounded-3xl) */
  --radius-full: 9999px;

  /* ════════════════════════════════════════════════════
     ── 阴影 (Box Shadow)
     ════════════════════════════════════════════════════ */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
  --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1);
  --shadow-2xl: 0 25px 50px -12px rgb(0 0 0 / 0.25);
  --shadow-glow-brand: 0 0 20px rgb(59 130 246 / 0.3);

  /* ════════════════════════════════════════════════════
     ── 动画 / 过渡 (Animation & Transition)
     ════════════════════════════════════════════════════ */
  --transition-duration-fast: 150ms;
  --transition-duration-base: 200ms;
  --transition-duration-slow: 300ms;
  --transition-duration-xslow: 500ms;

  --animate-spin: spin 1s linear infinite;
  --animate-pulse: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  --animate-slide-in-bottom: slide-in-bottom 200ms ease-out;
  --animate-fade-in: fade-in 200ms ease-out;
  --animate-scale-in: scale-in 200ms ease-out;
}

/* ── Keyframes for custom animations ── */
@keyframes slide-in-bottom {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes scale-in {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
```

### 3.2 @theme 使用说明

配置后的 Tailwind utility class 对照:

| Design Token | Tailwind 类名 | 示例 |
|-------------|---------------|------|
| `--color-brand-500` | `bg-brand-500`, `text-brand-500`, `border-brand-500` | `bg-brand-500` |
| `--color-secondary-600` | `bg-secondary-600` | AIChatWidget 标题栏 |
| `--color-accent-500` | `text-accent-500` | NLSearchWidget spinner |
| `--color-neutral-800` | `text-neutral-800` | 标题 |
| `--color-error-50` | `bg-error-50` | 错误背景 |
| `--spacing-4` | `p-4` (4×4px=16px) | 卡片内间距 |
| `--radius-lg` | `rounded-lg` | 卡片圆角 |
| `--shadow-xl` | `shadow-xl` | 名片预览 |
| `--font-size-2xs` | `text-2xs` | 10px 微提示 |

---

## 4. globals.css 创建方案

### 4.1 文件结构

```
src/
├── globals.css        ← 新建: @import "tailwindcss" + @theme + CSS变量 + 暗色模式
├── main.tsx           ← 修改: 添加 import './globals.css'
└── ...其余组件
```

### 4.2 CSS 变量与暗色模式

在 `@theme` 块之后，添加语义 CSS 变量层和暗色模式:

```css
/* ════════════════════════════════════════════════════
   ── 语义 CSS 变量 (Light Theme)
   ════════════════════════════════════════════════════ */
:root {
  /* 背景 */
  --ck-color-bg-page: #FFFFFF;
  --ck-color-bg-card: #FFFFFF;
  --ck-color-bg-input: #FFFFFF;

  /* 边框 */
  --ck-color-border-card: var(--color-neutral-200);
  --ck-color-border-input: var(--color-neutral-300);

  /* 文字 */
  --ck-color-text-heading: var(--color-neutral-800);
  --ck-color-text-body: var(--color-neutral-600);
  --ck-color-text-muted: var(--color-neutral-400);

  /* 渐变 */
  --ck-gradient-brand: linear-gradient(135deg, #3B82F6, #06B6D4, #9333EA);
  --ck-gradient-hero: linear-gradient(180deg, #F9FAFB, #FFFFFF);
}

/* ════════════════════════════════════════════════════
   ── 暗色模式 (prefers-color-scheme)
   ════════════════════════════════════════════════════ */
@media (prefers-color-scheme: dark) {
  :root {
    /* 背景 */
    --ck-color-bg-page: #0F172A;
    --ck-color-bg-card: #1E293B;
    --ck-color-bg-input: #1E293B;

    /* 边框 */
    --ck-color-border-card: #334155;
    --ck-color-border-input: #475569;

    /* 文字 */
    --ck-color-text-heading: #F1F5F9;
    --ck-color-text-body: #CBD5E1;
    --ck-color-text-muted: #64748B;

    /* 渐变 (暗色版更亮) */
    --ck-gradient-brand: linear-gradient(135deg, #60A5FA, #22D3EE, #C084FC);
    --ck-gradient-hero: linear-gradient(180deg, #020617, #1E293B);
  }
}

/* ════════════════════════════════════════════════════
   ── data-theme 属性方案 (手动切换备用)
   ════════════════════════════════════════════════════ */
[data-theme='dark'] {
  /* 同上暗色值，与 prefers-color-scheme 保持一致 */
  --ck-color-bg-page: #0F172A;
  --ck-color-bg-card: #1E293B;
  --ck-color-bg-input: #1E293B;
  --ck-color-border-card: #334155;
  --ck-color-border-input: #475569;
  --ck-color-text-heading: #F1F5F9;
  --ck-color-text-body: #CBD5E1;
  --ck-color-text-muted: #64748B;
  --ck-gradient-brand: linear-gradient(135deg, #60A5FA, #22D3EE, #C084FC);
  --ck-gradient-hero: linear-gradient(180deg, #020617, #1E293B);
}

/* ════════════════════════════════════════════════════
   ── 全局基础样式
   ════════════════════════════════════════════════════ */
body {
  font-family: 'Inter', 'system-ui', '-apple-system', 'Segoe UI',
               'Noto Sans SC', sans-serif;
  background-color: var(--ck-color-bg-page);
  color: var(--ck-color-text-body);
  transition: background-color 200ms ease, color 200ms ease;
}
```

### 4.3 组件中使用 CSS 变量的模式

对于需要跨主题动态变化的场景（如 LoginPage 的毛玻璃背景），组件中直接使用 CSS 变量:

```tsx
{/* 使用 CSS 变量实现自动深浅切换 */}
<div style={{ background: 'var(--ck-color-bg-card)', borderColor: 'var(--ck-color-border-card)' }}>
```

但**优先使用 Tailwind utility class**，只在需要动态主题切换且 Tailwind 类不能满足时使用 CSS 变量。

---

## 5. 主色收敛方案

### 5.1 收敛原则

```
brand (blue)  = 全局面板、导航、主按钮、链接 → 主线色
secondary (purple) = AI 对话、张力评分、智能上下文 → 辅助色
accent (indigo) = 搜索相关 → 强调色
gold = VIP/高级标识 → 点缀色
```

### 5.2 逐组件迁移映射

#### LoginPage

| 当前代码 | 替换为 | 说明 |
|---------|--------|------|
| `bg-blue-500/20` | `bg-brand-500/20` | 光晕背景 |
| `bg-cyan-400/15` | `bg-cyan-400/15` | 保留 (cyan 不在 token 中，考虑后续加入 gradient 辅助) |
| `bg-purple-600/20` | `bg-secondary-600/20` | 紫色光晕 |
| `from-blue-500 via-transparent to-purple-600/5` | `from-brand-500/5 via-transparent to-secondary-600/5` | 文字渐变背景 |
| `from-blue-600 via-cyan-500 to-purple-600` | `bg-[var(--ck-gradient-brand)]` | 按钮渐变 |
| `hover:from-blue-500 hover:via-cyan-400 hover:to-purple-500` | `hover:opacity-90` | hover 用透明度 |
| `focus:ring-blue-500/50` | `focus:ring-brand-500/50` | 聚焦环 |
| `text-slate-400/500/300` | `text-neutral-400/500` | 文字 (保持 slate？这里用中性色统一) |

> **决定**: LoginPage 的暗色主题使用 slate/slate 色调，保持其独特视觉身份。全局中性色使用 neutral(gray) 而非 slate。LoginPage 是唯一使用 slate 色调的页面，可继续使用 `text-slate-*` / `bg-slate-*` 或统一到 `text-neutral-*`。建议保留 LoginPage 的 slate 色调不变，因为它本身就是暗色主题的特殊页面。

#### AIChatWidget (purple → secondary)

| 当前代码 | 替换为 | 说明 |
|---------|--------|------|
| `bg-purple-600` | `bg-secondary-600` | 标题栏背景 |
| `hover:bg-purple-500` | `hover:bg-secondary-500` | 关闭按钮 hover |
| `bg-purple-600 text-white rounded-br-md` | `bg-secondary-600 text-white rounded-br-md` | 用户消息气泡 |
| `bg-purple-600 text-white rounded-xl` | `bg-secondary-600 text-white rounded-xl` | 发送按钮 |
| `hover:bg-purple-700` | `hover:bg-secondary-700` | 按钮 hover |
| `focus:ring-purple-400` | `focus:ring-secondary-400` | 输入框聚焦 |
| `bg-white` (消息气泡背景) | 保持不变 | 浅色背景不变 |

#### NLSearchWidget (indigo → brand)

| 当前代码 | 替换为 | 说明 |
|---------|--------|------|
| `text-indigo-500` (spinner) | `text-brand-500` | loading 图标 |
| `bg-indigo-50 text-indigo-600` | `bg-brand-50 text-brand-600` | 搜索标签 |
| `bg-indigo-600 text-white` | `bg-brand-600 text-white` | 搜索按钮 |
| `hover:bg-indigo-700` | `hover:bg-brand-700` | 按钮 hover |
| `focus:ring-indigo-500 focus:border-indigo-500` | `focus:ring-brand-500 focus:border-brand-500` | 输入框聚焦 |
| `hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-600` | `hover:bg-brand-50 hover:border-brand-200 hover:text-brand-600` | 示例按钮 hover |

#### TensionScoreWidget (purple → secondary)

| 当前代码 | 替换为 | 说明 |
|---------|--------|------|
| `bg-purple-600 text-white` | `bg-secondary-600 text-white` | 分析按钮 |
| `hover:bg-purple-700` | `hover:bg-secondary-700` | hover |
| `focus:ring-purple-500 focus:border-purple-500` | `focus:ring-secondary-500 focus:border-secondary-500` | 聚焦环 |

#### BusinessCardPage

| 当前代码 | 替换为 | 说明 |
|---------|--------|------|
| `bg-gray-50 to-white` | `bg-[var(--ck-gradient-hero)]` | 页面渐变背景 |
| `bg-white/80` | `bg-[var(--ck-color-bg-card)]/80` | header 背景 |
| `border-gray-100` | `border-neutral-100` | header 边框 |
| `text-gray-800` | `text-neutral-800` | 标题 |
| `text-blue-600` | `text-brand-600` | 链接/按钮 |
| `hover:text-blue-700` | `hover:text-brand-700` | 链接 hover |
| `bg-white` (active tab) | `bg-[var(--ck-color-bg-card)]` | 活动标签 |
| `text-blue-600` (active tab) | `text-brand-600` | 活动标签文字 |
| `bg-red-50 border-red-200 text-red-600` | `bg-error-50 border-error-200 text-error-600` | 错误提示 |

### 5.3 模板颜色 (保留多样性)

TemplateSelector 的模板渐变（现代蓝调、极简白、暖金尊享、自然绿意、暗夜优雅、梦幻紫韵）**保持不变**。这些是用户可见的模板选择，属于业务功能而非设计系统，不需要收敛。

### 5.4 辅助色使用规范

| 场景 | 使用色 | 示例 |
|------|-------|------|
| AI 对话 UI | secondary | AIChatWidget 标题、气泡、按钮 |
| 张力/评分 UI | secondary | TensionScoreWidget 按钮、聚焦环 |
| 搜索 UI | brand (主线) | NLSearchWidget 按钮、标签、聚焦环 |
| 匹配历史/收藏 | brand 或 secondary | MatchHistoryPage purple 标签 → secondary |
| 分享按钮渐变 | brand + secondary | ShareActions `from-blue-600 to-purple-600` → `from-brand-600 to-secondary-600` |

---

## 6. 暗色模式实施策略

### 6.1 方案选择: prefers-color-scheme + data-theme 双通道

```
优先: CSS @media (prefers-color-scheme: dark)
备选: [data-theme="dark"] 属性 (用于手动切换/测试)
```

两者在 globals.css 中都有定义，值保持一致。未来如需"用户手动切换主题"，只需在 `<html>` 上切换 `data-theme` 属性即可覆盖系统偏好。

### 6.2 组件暗色模式对照表

| 组件 | Light 当前值 | Dark 值 | 实现方式 |
|------|-------------|---------|---------|
| 页面背景 | `bg-gray-50 to-white` | `bg-slate-950` (Login) / `bg-[var(--ck-color-bg-page)]` | CSS 变量自动 |
| 卡片背景 | `bg-white` | `bg-[var(--ck-color-bg-card)]` → dark: `#1E293B` | CSS 变量 |
| 卡片边框 | `border-gray-200` | `border-[var(--ck-color-border-card)]` → dark: `#334155` | CSS 变量 |
| 标题文字 | `text-gray-800` | `text-[var(--ck-color-text-heading)]` → dark: `#F1F5F9` | CSS 变量 |
| 正文文字 | `text-gray-500` | `text-[var(--ck-color-text-body)]` → dark: `#CBD5E1` | CSS 变量 |
| 输入框背景 | `bg-white` | `bg-[var(--ck-color-bg-input)]` | CSS 变量 |
| 输入框边框 | `border-gray-200` | `border-[var(--ck-color-border-input)]` | CSS 变量 |

### 6.3 逐步迁移策略

**Phase 1 (MVS)**: 仅添加 CSS 变量定义和暗色模式 media query。基础色自动切换。

**Phase 2 (组件适配)**: 逐个组件将 `bg-white` 替换为 `bg-[var(--ck-color-bg-card)]`，`text-gray-800` 替换为 `text-[var(--ck-color-text-heading)]`。

**Phase 3 (细粒度)**: 处理特殊场景 — 标签背景、分割线、阴影、渐变等。

### 6.4 暗色模式优先级

1. **LoginPage** — 已实现，仅需对齐 CSS 变量命名 (当前是硬编码 `bg-slate-950`)
2. **BusinessCardPage 主面板** — 最高优先级 (首页/核心页面)
3. **AIChatWidget** — 中优先级 (浮动组件，影响面较小)
4. **NLSearchWidget** — 中优先级
5. **其余组件** — 按需推进

---

## 7. 硬编码替换清单

### 7.1 颜色 (27 处)

| # | 文件 | 行(约) | 当前值 | 替换值 |
|---|------|--------|-------|--------|
| 1 | App.tsx | 19 | `#666` | `text-neutral-500` |
| 2 | App.tsx | 23 | `#2563eb` | `bg-brand-600` |
| 3 | App.tsx | 23 | `#fff` | `text-white` |
| 4 | App.tsx | 24 | `#f3f4f6` | `bg-neutral-100` |
| 5 | App.tsx | 26 | `#333` | `text-neutral-700` |
| 6 | LoginPage | 35 | `bg-blue-500/20` | `bg-brand-500/20` |
| 7 | LoginPage | 38 | `bg-purple-600/20` | `bg-secondary-600/20` |
| 8 | LoginPage | 39 | `from-blue-500/5 ... to-purple-600/5` | CSS 变量渐变 |
| 9 | LoginPage | 97 | `from-blue-400 via-cyan-300 to-purple-400` | CSS 变量渐变 |
| 10 | LoginPage | 130 | `focus:ring-blue-500/50` | `focus:ring-brand-500/50` |
| 11 | LoginPage | 159 | `from-blue-600 via-cyan-500 to-purple-600` | `bg-[var(--ck-gradient-brand)]` |
| 12 | BusinessCardPage | 59 | `from-gray-50 to-white` | `bg-[var(--ck-gradient-hero)]` |
| 13 | BusinessCardPage | 65 | `bg-white/80` | `bg-[var(--ck-color-bg-card)]/80` |
| 14 | BusinessCardPage | 65 | `border-gray-100` | `border-neutral-100` |
| 15 | BusinessCardPage | 68 | `text-gray-800` | `text-neutral-800` |
| 16 | BusinessCardPage | 72 | `text-blue-600 hover:text-blue-700` | `text-brand-600 hover:text-brand-700` |
| 17 | BusinessCardPage | 148 | `text-blue-600` | `text-brand-600` |
| 18 | AIChatWidget | 116 | `bg-purple-600` | `bg-secondary-600` |
| 19 | AIChatWidget | 135 | `hover:bg-purple-500` | `hover:bg-secondary-500` |
| 20 | AIChatWidget | 159 | `bg-purple-600` | `bg-secondary-600` |
| 21 | AIChatWidget | 179 | `focus:ring-purple-400` | `focus:ring-secondary-400` |
| 22 | AIChatWidget | 184 | `bg-purple-600` | `bg-secondary-600` |
| 23 | AIChatWidget | 211 | `bg-purple-600 hover:bg-purple-700` | `bg-secondary-600 hover:bg-secondary-700` |
| 24 | NLSearchWidget | 378 | `text-indigo-500` | `text-brand-500` |
| 25 | NLSearchWidget | 455 | `bg-indigo-50 text-indigo-600` | `bg-brand-50 text-brand-600` |
| 26 | NLSearchWidget | 499 | `bg-indigo-600 ... hover:bg-indigo-700` | `bg-brand-600 ... hover:bg-brand-700` |
| 27 | NLSearchWidget | 563 | `focus:ring-indigo-500 focus:border-indigo-500` | `focus:ring-brand-500 focus:border-brand-500` |

### 7.2 间距标准化建议

| 当前 | 建议 | 语义 |
|-----|------|------|
| `p-3` (12px) | 保留 `p-3` (对应 spacing-3) | 卡片内紧凑间距 |
| `p-4` (16px) | 保留 `p-4` (对应 spacing-4) | 默认卡片 padding |
| `p-5` (20px) | 保留 `p-5` (对应 spacing-5) | 表单/区块间距 |
| `p-6` (24px) | 保留 `p-6` (对应 spacing-6) | 大区块 |
| `p-8` (32px) | 保留 `p-8` (对应 spacing-8) | 页面容器 |
| `p-10` (40px) | 保留 `p-10` (对应 spacing-10) | 标题区 |

当前间距使用已经基本合理，`@theme` 中 `--spacing: 4px` 会自动使 Tailwind 的 `p-*` 类使用 4px 网格，不需要改动。

### 7.3 圆角标准化

| 当前 | @theme Token | 建议 |
|------|-------------|------|
| `rounded-md` (6px) | `--radius-sm` | → `rounded-sm` |
| `rounded-lg` (8px) | `--radius-md` | → `rounded-md` |
| `rounded-xl` (12px) | `--radius-lg` | → `rounded-lg` |
| `rounded-2xl` (16px) | `--radius-xl` | → `rounded-xl` |
| `rounded-3xl` (24px) | `--radius-2xl` | → `rounded-2xl` |

---

## 8. 1 天最小可行方案

### 8.1 实施步骤 (4-6 小时)

```
Day 1 - 上午 (2-3h)
├── Step 1: 安装依赖 + 配置 Vite + 创建 globals.css (30min)
│   ├── npm install tailwindcss @tailwindcss/vite
│   ├── 修改 vite.config.ts 添加 tailwindcss() 插件
│   ├── 创建 src/globals.css (@import + @theme + CSS变量)
│   └── 修改 src/main.tsx 导入 globals.css
│
├── Step 2: 验证基础 (30min)
│   ├── npm run dev 确认编译无错误
│   └── 浏览器确认 utility class (bg-brand-500, text-neutral-800) 生效
│
├── Step 3: AIChatWidget 主色收敛 (30min)
│   ├── bg-purple-600 → bg-secondary-600 (4处)
│   ├── hover:bg-purple-500/700 → hover:bg-secondary-500/700 (3处)
│   └── focus:ring-purple-400 → focus:ring-secondary-400 (1处)
│
├── Step 4: NLSearchWidget 主色收敛 (30min)
│   ├── text-indigo-500 → text-brand-500 (1处, spinner)
│   ├── bg-indigo-50/600 → bg-brand-50/600 (2处)
│   ├── hover:bg-indigo-50/700 → hover:bg-brand-50/700 (3处)
│   └── focus:ring-indigo-500 → focus:ring-brand-500 (2处)
│
└── Step 5: BusinessCardPage 主色 + 中性色标准化 (30min)
    ├── text-gray-800 → text-neutral-800 (多处)
    ├── border-gray-100/200 → border-neutral-100/200 (多处)
    ├── text-blue-600 → text-brand-600 (多处)
    └── from-gray-50 to-white → bg-[var(--ck-gradient-hero)]

Day 1 - 下午 (1-2h)
├── Step 6: 剩余组件主色收敛 (1h)
│   ├── TensionScoreWidget: purple → secondary (3处)
│   ├── ShareActions: from-blue-600 to-purple-600 → from-brand-600 to-secondary-600
│   ├── MatchResultsPanel: purple-50/600 → secondary-50/600 (2处)
│   └── TemplateSelector/TensionWeaponLibrary: 保持或收敛
│
├── Step 7: LoginPage 对齐 (30min)
│   ├── 渐变路径对齐 CSS 变量
│   └── 品牌色对齐 brand token
│
└── Step 8: 构建验证 (30min)
    ├── npm run build 确认无 TS/CSS 错误
    └── Vite 预览确认所有页面样式正常
```

### 8.2 产出物清单

| 产出 | 路径 | 说明 |
|------|------|------|
| ✅ `globals.css` | `src/globals.css` | Tailwind @theme + CSS 变量 + 暗色模式 |
| ✅ `vite.config.ts` | `deploy/docker/vite.config.ts` | + tailwindcss() 插件 |
| ✅ `main.tsx` | `src/main.tsx` | + import './globals.css' |
| ✅ `package.json` | `deploy/docker/package.json` | + tailwindcss, @tailwindcss/vite 依赖 |

### 8.3 不包含在 MVS 中的内容

以下**推迟到后续迭代**:

- ❌ 全局圆角标准化 (rounded-md→rounded-sm 等) — 视觉无大变化，纯规范调整
- ❌ App.tsx HomePage 内联样式替换 — 仅开发用首页
- ❌ 暗色模式逐组件适配 — 仅添加 CSS 变量定义，不修改组件
- ❌ 阴影自定义 — `shadow-glow-brand` 暂不导入，继续使用标准 shadow
- ❌ 动画 Token 映射 — 自定义动画 keyframes 添加但不强制替换
- ❌ 字族统一 — `--font-family-sans` 定义但不强制修改组件

### 8.4 回滚方案

如果实施后出现问题:

1. 移除 `vite.config.ts` 中的 `tailwindcss()` 插件
2. 移除 `main.tsx` 中的 `import './globals.css'`
3. `npm uninstall tailwindcss @tailwindcss/vite`
4. 还原修改过的组件文件

由于所有样式变更都是 `purple → secondary` / `indigo → brand` 的**命名字符串替换**，回滚时只需 `git checkout` 即可。

---

## 9. 后续扩展

### 9.1 Phase 2 (第 2-3 天)

- 圆角标准化: `rounded-xl` → `rounded-lg` 等
- App.tsx HomePage 内联样式 → Tailwind utility class
- 暗色模式: BusinessCardPage 主面板适配
- 阴影: 添加 `shadow-glow-brand` 发光效果

### 9.2 Phase 3 (第 4-5 天)

- 暗色模式: 全组件适配完成
- 自定义动画: 替换 `animate-in slide-in-from-bottom-4` → `animate-slide-in-bottom`
- 字族: 全局应用 `font-sans` (Inter)
- 间距审计: 统一各处间距语义

### 9.3 Phase 4 (长期)

- 组件级 Token: 建立 `--ck-component-*` 命名空间
- 主题切换 UI: 在设置中添加 light/dark 手动切换
- CSS 变量 vs Tailwind utility 的边界规则文档化

---

## 附录 A: 主色收敛前后对照图

```
实施前:                           实施后:
LoginPage        → blue          LoginPage        → brand (blue) ✓
BusinessCard     → blue          BusinessCard     → brand (blue) ✓
AIChatWidget     → purple        AIChatWidget     → secondary (purple) ✓
NLSearchWidget   → indigo        NLSearchWidget   → brand (blue) ✓ ← 重点收敛
TensionScore     → purple        TensionScore     → secondary (purple) ✓
AbaccProductIntro→ #3B82F6       AbaccProductIntro→ brand-500 ✓
ShareActions     → blue→purple   ShareActions     → brand→secondary ✓
MatchResultsPanel→ purple        MatchResultsPanel→ secondary ✓
```

## 附录 B: Tailwind CSS v4 @theme 快速参考

| 配置 | 语法 | 说明 |
|------|------|------|
| 颜色 | `--color-{name}-{shade}: #hex;` | 生成 `bg-{name}-{shade}` 等 |
| 间距 | `--spacing: {base};` | 基准值，`p-4` = 4×base |
| 字号 | `--font-size-{name}: {size};` | 生成 `text-{name}` |
| 圆角 | `--radius-{name}: {value};` | 生成 `rounded-{name}` |
| 阴影 | `--shadow-{name}: {value};` | 生成 `shadow-{name}` |
| 字族 | `--font-family-{name}: {value};` | 生成 `font-{name}` |
| 动画 | `--animate-{name}: {definition};` | 生成 `animate-{name}` |

---

*本文档由链客宝设计审查引擎自动分析生成，结合 Tailwind CSS v4 @theme 最佳实践整理。*
*实施日期: 2026-06-25*
