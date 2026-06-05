/**
 * OnboardingPainSelector — 注册流程中的「你的核心痛点是什么」三选一组件
 *
 * 三个选项：
 *   1. 「获客成本太高」 → low_acquisition_cost
 *   2. 「缺信任背书难成交」 → lack_trust
 *   3. 「分销结算太麻烦」 → distribution_pain
 *
 * 选择后触发 onSelect(painPoint) 回调，由父组件驱动后续流程。
 */

import { useState } from 'react';
import { CheckCircle2, TrendingDown, ShieldAlert, Repeat2 } from 'lucide-react';

export type PainPoint = 'low_acquisition_cost' | 'lack_trust' | 'distribution_pain';

interface PainOption {
  id: PainPoint;
  icon: React.ReactNode;
  title: string;
  description: string;
  emoji: string;
}

const PAIN_OPTIONS: PainOption[] = [
  {
    id: 'low_acquisition_cost',
    icon: <TrendingDown className="w-6 h-6" />,
    title: '获客成本太高',
    description: '新客获取越来越贵，急需更低成本的获客渠道',
    emoji: '📉',
  },
  {
    id: 'lack_trust',
    icon: <ShieldAlert className="w-6 h-6" />,
    title: '缺信任背书难成交',
    description: '客户犹豫不决，需要企业信任网络来加速成交',
    emoji: '🛡️',
  },
  {
    id: 'distribution_pain',
    icon: <Repeat2 className="w-6 h-6" />,
    title: '分销结算太麻烦',
    description: '渠道佣金计算繁琐，希望一键发布信息邀请伙伴推广',
    emoji: '🔄',
  },
];

interface OnboardingPainSelectorProps {
  selected: PainPoint | null;
  onSelect: (painPoint: PainPoint) => void;
}

export function OnboardingPainSelector({ selected, onSelect }: OnboardingPainSelectorProps) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
        <span className="w-1 h-5 bg-sky-500 rounded-full" />
        你的核心痛点是什么
      </h2>
      <p className="text-xs text-slate-400 pl-3 -mt-1">
        选择当前最困扰你的问题，我们将为你定制专属引导
      </p>

      <div className="grid gap-2.5">
        {PAIN_OPTIONS.map((option) => (
          <div
            key={option.id}
            onClick={() => onSelect(option.id)}
            className={`p-4 rounded-2xl border-2 transition-all cursor-pointer flex items-center gap-4 ${
              selected === option.id
                ? 'border-sky-500 bg-white shadow-md shadow-sky-100'
                : 'border-slate-100 bg-white/50 hover:border-slate-200 hover:shadow-sm'
            }`}
          >
            <div
              className={`w-12 h-12 rounded-xl flex items-center justify-center text-xl ${
                selected === option.id ? 'bg-sky-50' : 'bg-slate-50'
              }`}
            >
              {option.emoji}
            </div>
            <div className="flex-1 min-w-0">
              <h3
                className={`font-bold text-sm ${
                  selected === option.id ? 'text-sky-600' : 'text-slate-800'
                }`}
              >
                {option.title}
              </h3>
              <p className="text-[10px] text-slate-400 mt-0.5">{option.description}</p>
            </div>
            {selected === option.id && (
              <CheckCircle2 className="w-5 h-5 text-sky-500 shrink-0" />
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * 根据痛点点返回推荐的功能入口排序（按优先级从高到低）
 * 首页可用此来调整功能卡片显示顺序
 */
export function getFeaturePriorityByPainPoint(
  painPoint: PainPoint | null
): string[] {
  switch (painPoint) {
    case 'low_acquisition_cost':
      return ['product-pool', 'promotion-center', 'supply-demand', 'contacts', 'my-orders', 'data'];
    case 'lack_trust':
      return ['supply-demand', 'contacts', 'product-pool', 'promotion-center', 'my-orders', 'data'];
    case 'distribution_pain':
      return ['promotion-center', 'product-pool', 'my-orders', 'contacts', 'supply-demand', 'data'];
    default:
      return ['product-pool', 'promotion-center', 'contacts', 'my-orders', 'supply-demand', 'data'];
  }
}

/**
 * 根据痛点点返回推荐路由路径
 * 注册完成后的引导跳转目标
 */
export function getOnboardingRedirect(painPoint: PainPoint | null): string {
  switch (painPoint) {
    case 'low_acquisition_cost':
      return '/product-pool'; // 引导选择「推荐任务」
    case 'lack_trust':
      return '/supply-demand'; // 「企业信任网络」引导
    case 'distribution_pain':
      return '/promotion-center'; // 「发布信息→邀请伙伴」引导
    default:
      return '/home';
  }
}
