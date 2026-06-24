/**
 * 链客宝组件库文档 — 索引
 * ==============================
 * 基于 design-tokens.ts 的语义化组件
 * 每个组件导出 Props 类型和默认变体
 */

// ===== 组件 Props 类型 =====

export interface ButtonProps {
  variant: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size: 'sm' | 'md' | 'lg';
  loading?: boolean;
  disabled?: boolean;
  icon?: 'left' | 'right';
}

export interface CardProps {
  variant: 'glass' | 'glow' | 'flat' | 'elevated';
  padding: 'sm' | 'md' | 'lg' | 'xl';
  hover?: boolean;
  onClick?: () => void;
}

export interface InputProps {
  variant: 'default' | 'filled' | 'outlined';
  size: 'sm' | 'md' | 'lg';
  error?: string;
  hint?: string;
  label?: string;
}

export interface BadgeProps {
  variant: 'default' | 'success' | 'warning' | 'danger' | 'info';
  size: 'sm' | 'md';
  dot?: boolean;
}

export interface AvatarProps {
  size: 'sm' | 'md' | 'lg' | 'xl';
  fallback: string;
  src?: string;
}

export interface ModalProps {
  size: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  closeOnOverlay?: boolean;
  showClose?: boolean;
}

export interface ToastProps {
  variant: 'success' | 'error' | 'warning' | 'info';
  duration?: number;
  position: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left';
}

export interface TableProps {
  variant: 'default' | 'striped' | 'bordered';
  size: 'sm' | 'md';
  hover?: boolean;
  loading?: boolean;
}

export interface TabsProps {
  variant: 'underline' | 'pills' | 'segmented';
  size: 'sm' | 'md';
}

export interface TooltipProps {
  position: 'top' | 'bottom' | 'left' | 'right';
  delay?: number;
}

// ===== 设计Token映射 =====
import { designTokens as dt } from './design-tokens';

export const componentStyles = {
  button: {
    base: 'inline-flex items-center justify-center font-semibold transition-all duration-200 rounded-lg',
    variants: {
      primary: `bg-gradient-to-br from-[${dt.colors.brand.primary}] to-[${dt.colors.brand.secondary}] text-white hover:opacity-90 hover:-translate-y-0.5`,
      secondary: `bg-[${dt.colors.bg.card}] text-[${dt.colors.text.primary}] border border-[${dt.colors.border.primary}] hover:border-[${dt.colors.brand.primary}]`,
      outline: `border border-[${dt.colors.border.primary}] text-[${dt.colors.text.primary}] hover:bg-[${dt.colors.bg.surface}]`,
      ghost: `text-[${dt.colors.text.secondary}] hover:text-[${dt.colors.text.primary}] hover:bg-[${dt.colors.bg.surface}]`,
      danger: `bg-[${dt.colors.brand.danger}] text-white hover:opacity-90`,
    },
    sizes: {
      sm: 'h-8 px-3 text-xs gap-1.5',
      md: 'h-10 px-4 text-sm gap-2',
      lg: 'h-12 px-6 text-base gap-2.5',
    },
  },
  card: {
    base: 'rounded-xl border transition-all duration-250',
    variants: {
      glass: `bg-[${dt.colors.bg.card}] border-[${dt.colors.border.primary}] backdrop-blur-xl`,
      glow: `bg-[${dt.colors.bg.card}] border-[${dt.colors.border.primary}] relative overflow-hidden before:absolute before:inset-0 before:bg-gradient-glow before:opacity-0 hover:before:opacity-100 before:transition-opacity`,
      flat: `bg-[${dt.colors.bg.secondary}] border-transparent`,
      elevated: `bg-[${dt.colors.bg.card}] border-[${dt.colors.border.primary}] shadow-lg`,
    },
    paddings: {
      sm: 'p-3',
      md: 'p-4',
      lg: 'p-6',
      xl: 'p-8',
    },
  },
} as const;
