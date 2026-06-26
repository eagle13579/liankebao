/**
 * 三步冷启动引导 — 类型定义
 */

import type { Template } from '../../components/onboarding/TemplateSelector';

// ── 企业基本信息 ──
export interface EnterpriseInfo {
  companyName: string;
  industry: string;
  scale: string;
  region: string;
}

// ── 需求偏好 ──
export interface DemandPreference {
  cooperationType: string;
  goal: string;
  budgetRange: string;
}

// ── 引导默认配置（GET /api/v1/onboarding/defaults 返回值） ──
export interface OnboardingDefaults {
  enterpriseInfo: EnterpriseInfo;
  demandPreference: DemandPreference;
  userInfo: {
    name: string;
    position?: string;
    company?: string;
    phone?: string;
    email?: string;
    wechat?: string;
    website?: string;
    address?: string;
    avatar?: string;
  };
}

// ── 模板列表响应（GET /api/v1/onboarding/templates 返回值） ──
export interface TemplatesResponse {
  templates: Template[];
  total: number;
}

// ── 三步引导当前输入状态（用于本地状态管理） ──
export interface OnboardingState {
  enterpriseInfo: EnterpriseInfo;
  demandPreference: DemandPreference;
  selectedTemplateId: string | null;
}

// ── 步骤定义 ──
export interface OnboardingStep {
  id: number;
  label: string;
  description?: string;
}

// ── 预设常量 ──
export const ONBOARDING_STEPS: OnboardingStep[] = [
  { id: 1, label: '企业信息', description: '填写企业基本信息' },
  { id: 2, label: '需求偏好', description: '设置合作偏好与目标' },
  { id: 3, label: '模板选择', description: '选择名片模板并预览' },
];

export const INDUSTRY_OPTIONS = [
  { value: '科技', label: '科技/互联网' },
  { value: '金融', label: '金融/保险' },
  { value: '教育', label: '教育/培训' },
  { value: '医疗', label: '医疗/健康' },
  { value: '制造', label: '制造业' },
  { value: '零售', label: '零售/电商' },
  { value: '房地产', label: '房地产/建筑' },
  { value: '文化', label: '文化/传媒' },
  { value: '咨询', label: '咨询/服务' },
  { value: '其他', label: '其他' },
];

export const SCALE_OPTIONS = [
  { value: '1-10', label: '1-10 人' },
  { value: '11-50', label: '11-50 人' },
  { value: '51-200', label: '51-200 人' },
  { value: '201-1000', label: '201-1000 人' },
  { value: '1000+', label: '1000 人以上' },
];

export const REGION_OPTIONS = [
  { value: '华北', label: '华北地区' },
  { value: '华东', label: '华东地区' },
  { value: '华南', label: '华南地区' },
  { value: '华中', label: '华中地区' },
  { value: '西南', label: '西南地区' },
  { value: '西北', label: '西北地区' },
  { value: '东北', label: '东北地区' },
  { value: '港澳台', label: '港澳台地区' },
  { value: '海外', label: '海外' },
];

export const COOPERATION_TYPE_OPTIONS = [
  { value: 'supply', label: '供应商合作' },
  { value: 'distribution', label: '渠道分销' },
  { value: 'investment', label: '投资融资' },
  { value: 'technology', label: '技术合作' },
  { value: 'marketing', label: '市场推广' },
  { value: 'other', label: '其他' },
];

export const GOAL_OPTIONS = [
  { value: 'brand', label: '品牌曝光' },
  { value: 'leads', label: '获取线索' },
  { value: 'partnership', label: '建立合作' },
  { value: 'recruitment', label: '人才招聘' },
  { value: 'showcase', label: '企业展示' },
];

export const BUDGET_OPTIONS = [
  { value: '0-10k', label: '1 万以内' },
  { value: '10k-50k', label: '1-5 万' },
  { value: '50k-200k', label: '5-20 万' },
  { value: '200k+', label: '20 万以上' },
  { value: 'undetermined', label: '待定' },
];
