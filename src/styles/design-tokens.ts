/**
 * 链客宝设计Token系统 v1
 * ========================
 * 对标 Linear 设计Token体系
 * 提供语义化设计变量，替代 Tailwind 默认值
 *
 * 基于 themes.css 的 Emerald 色系扩展
 * 包含: 颜色/间距/字体/阴影/动画/圆角/断点
 */

export const designTokens = {
  // ===== 颜色系统 =====
  colors: {
    // 品牌色 (Emerald)
    brand: {
      primary: 'var(--accent-primary, #10b981)',
      secondary: 'var(--accent-secondary, #059669)',
      tertiary: 'var(--accent-tertiary, #34d399)',
      success: 'var(--accent-success, #22c55e)',
      warning: 'var(--accent-warning, #f59e0b)',
      danger: 'var(--accent-danger, #ef4444)',
    },
    // 背景色
    bg: {
      primary: 'var(--bg-primary, #0c0e19)',
      secondary: 'var(--bg-secondary, #151929)',
      surface: 'var(--bg-surface, #1a1f33)',
      card: 'var(--bg-card, #1e2438)',
      muted: 'var(--bg-muted, #0c0e19)',
    },
    // 文本色
    text: {
      primary: 'var(--text-primary, #e8ecf4)',
      secondary: 'var(--text-secondary, #949bb8)',
      muted: 'var(--text-muted, #5c6380)',
    },
    // 边框色
    border: {
      primary: 'var(--border-primary, #2a2f45)',
      secondary: 'var(--border-secondary, #1a1f33)',
    },
    // 渐变
    gradient: {
      brand: 'var(--gradient-brand)',
      subtle: 'var(--gradient-subtle)',
      glow: 'var(--gradient-glow)',
    },
  },

  // ===== 间距系统 (8px基准) =====
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
    '2xl': '32px',
    '3xl': '48px',
    '4xl': '64px',
    '5xl': '96px',
  },

  // ===== 字体系统 =====
  typography: {
    fontFamily: {
      sans: "'Geist', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      mono: "'JetBrains Mono', 'Fira Code', monospace",
      display: "'Geist', 'Inter', sans-serif",
    },
    fontSize: {
      xs: '0.75rem',    // 12px
      sm: '0.875rem',   // 14px
      base: '1rem',     // 16px
      lg: '1.125rem',   // 18px
      xl: '1.25rem',    // 20px
      '2xl': '1.5rem',  // 24px
      '3xl': '1.875rem', // 30px
      '4xl': '2.25rem',  // 36px
      '5xl': '3rem',     // 48px
    },
    fontWeight: {
      normal: '400',
      medium: '500',
      semibold: '600',
      bold: '700',
    },
    lineHeight: {
      tight: '1.25',
      normal: '1.5',
      relaxed: '1.75',
    },
  },

  // ===== 阴影系统 =====
  shadows: {
    sm: 'var(--shadow-sm)',
    md: 'var(--shadow-md)',
    lg: 'var(--shadow-lg)',
    glow: '0 0 20px rgba(16, 185, 129, 0.15)',
    'glow-lg': '0 0 40px rgba(16, 185, 129, 0.2)',
  },

  // ===== 圆角 =====
  radius: {
    sm: '6px',
    md: '10px',
    lg: '14px',
    xl: '20px',
    full: '9999px',
  },

  // ===== 动画 =====
  animation: {
    duration: {
      fast: '150ms',
      normal: '250ms',
      slow: '400ms',
      verySlow: '600ms',
    },
    easing: {
      ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
      easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
      easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
      easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
      spring: 'cubic-bezier(0.175, 0.885, 0.32, 1.275)',
    },
  },

  // ===== 响应式断点 =====
  breakpoints: {
    sm: '640px',
    md: '768px',
    lg: '1024px',
    xl: '1280px',
    '2xl': '1536px',
  },

  // ===== Z-index层级 =====
  zIndex: {
    base: 0,
    dropdown: 100,
    sticky: 200,
    overlay: 300,
    modal: 400,
    popover: 500,
    toast: 600,
    tooltip: 700,
  },
} as const;

// ===== 类型导出 =====
export type DesignTokens = typeof designTokens;
export type ColorToken = keyof typeof designTokens.colors;
export type SpacingToken = keyof typeof designTokens.spacing;
export type FontSizeToken = keyof typeof designTokens.typography.fontSize;

// ===== 性能基线 =====
export const performanceBaseline = {
  /** 目标: 首屏加载 < 1s (LCP) */
  lcp: { target: 1000, unit: 'ms', critical: true },
  /** 目标: 搜索响应 < 200ms */
  searchResponse: { target: 200, unit: 'ms', critical: true },
  /** 目标: 名片加载 < 100ms */
  cardLoad: { target: 100, unit: 'ms', critical: true },
  /** 目标: FID < 100ms */
  fid: { target: 100, unit: 'ms' },
  /** 目标: CLS < 0.1 */
  cls: { target: 0.1, unit: 'score' },
  /** 目标: TTI < 3s */
  tti: { target: 3000, unit: 'ms' },
  /** 目标: 匹配请求 P50 < 500ms */
  matchP50: { target: 500, unit: 'ms' },
  /** 目标: 匹配请求 P99 < 2000ms */
  matchP99: { target: 2000, unit: 'ms' },
} as const;
