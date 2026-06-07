/**
 * 链客宝 - ABACC销售话术模板类型定义
 * 注入点：销售话术模板编辑器类型系统
 * 规则：纯新增，不修改现有业务逻辑
 */

/** ABACC单步话术 */
export interface AbaccStep {
  step_id: 'attention' | 'before' | 'after' | 'curiosity' | 'call_action';
  title: string;
  template: string;
  examples: string[];
  tips: string[];
}

/** ABACC五步步骤元数据 */
export const ABACC_STEPS_META: Record<string, { label: string; icon: string; color: string }> = {
  attention:     { label: 'A - 吸引注意',     icon: '🎯', color: '#3B82F6' },
  before:        { label: 'B - 痛点描述',     icon: '🔥', color: '#EF4444' },
  after:         { label: 'A - 改变后状态',   icon: '🌈', color: '#10B981' },
  curiosity:     { label: 'C - 激发好奇',     icon: '💡', color: '#F59E0B' },
  call_action:   { label: 'C - 号召行动',     icon: '🚀', color: '#8B5CF6' },
};

/** 完整话术模板 */
export interface SalesScript {
  id?: number;
  name: string;
  scenario: string;
  target_role: string;
  abacc: AbaccStep[];
  tension_score?: number;
  tags: string[];
  created_at?: string;
  updated_at?: string;
}

/** 数据增强器模式 */
export type AugmenterMode = 'analogy' | 'unit_transform' | 'comparison';

export interface AugmenterExample {
  input: string;
  output: string;
}

export interface AugmenterData {
  description: string;
  examples: AugmenterExample[];
}

/** 数据增强器 */
export interface DataAugmenter {
  [mode: string]: AugmenterData;
}

/** 引导词分类 */
export interface MagicWordCategory {
  name: string;
  words: string[];
}

/** 引导词库 */
export interface MagicWords {
  [category: string]: MagicWordCategory;
}

/** 张力等级 */
export interface TensionLevel {
  score_range: string;
  label: string;
  description: string;
  symptoms: string[];
  fixes: string[];
}

/** 张力自检 */
export interface TensionCheck {
  [level: string]: TensionLevel;
}

/** 张力分析结果 */
export interface TensionAnalysis {
  score: number;
  level: 'low' | 'medium' | 'high';
  label: string;
  description: string;
  symptoms: string[];
  fixes: string[];
}

/** API 响应包装 */
export interface ApiResponse<T> {
  data?: T;
  message?: string;
  presets?: SalesScript[];
  total?: number;
}
