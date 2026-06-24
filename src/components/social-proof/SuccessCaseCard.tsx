/**
 * SuccessCaseCard.tsx — 成功案例展示卡片
 *
 * 展示合作企业的成功案例，包含：
 * - 企业名称 + 案例标题
 * - 案例描述
 * - 关键指标展示
 * - 标签
 * - 悬停动效
 * - 响应式设计
 */

import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { TrendingUp, Award, Users, Target, Clock, ArrowRight } from 'lucide-react';

export interface SuccessCaseItem {
  id: string;
  company: string;
  title: string;
  description: string;
  icon?: string;
  metrics?: Record<string, string>;
  tags?: string[];
  sort_order?: number;
}

interface SuccessCaseCardProps {
  /** 自定义数据（可选，不传则从 API 获取） */
  cases?: SuccessCaseItem[];
  /** 标题 */
  title?: string;
  /** 最多显示数量 */
  maxCount?: number;
  /** 额外类名 */
  className?: string;
}

const FALLBACK_CASES: SuccessCaseItem[] = [
  {
    id: '1', company: '某科技公司', title: 'AI营销系统渠道拓展',
    description: '通过链客宝AI匹配引擎，精准对接3家省级渠道商，月销售额提升200%。',
    icon: '🏢', metrics: { '销售额提升': '200%', '渠道商数': '3家' }, tags: ['AI营销'],
  },
  {
    id: '2', company: '某制造企业', title: '供应链需求48小时响应',
    description: '发布供应链需求后48小时内收到15家供应商报价，采购成本降低15%。',
    icon: '🏭', metrics: { '响应时间': '48小时', '成本降低': '15%' }, tags: ['供应链'],
  },
  {
    id: '3', company: '某贸易公司', title: 'AI数字名片获客革命',
    description: 'AI数字名片替代传统纸质名片，客户转化率提升40%，累计获客200+。',
    icon: '💼', metrics: { '转化率提升': '40%', '累计获客': '200+' }, tags: ['数字名片'],
  },
  {
    id: '4', company: '某连锁品牌', title: '全国城市合伙人招募',
    description: '3个月内成功招募6省份城市合伙人，门店覆盖扩展至15个城市。',
    icon: '🏪', metrics: { '省份覆盖': '6个', '城市覆盖': '15个' }, tags: ['合伙人'],
  },
];

/** 指标图标映射 */
function getMetricIcon(key: string) {
  const lower = key.toLowerCase();
  if (lower.includes('提升') || lower.includes('增长') || lower.includes('销售')) return <TrendingUp className="w-3 h-3" />;
  if (lower.includes('降低') || lower.includes('成本')) return <Target className="w-3 h-3" />;
  if (lower.includes('覆盖') || lower.includes('拓展')) return <Award className="w-3 h-3" />;
  if (lower.includes('响应') || lower.includes('时间')) return <Clock className="w-3 h-3" />;
  return <Users className="w-3 h-3" />;
}

export default function SuccessCaseCard({
  cases: propCases,
  title = '成功案例',
  maxCount = 6,
  className = '',
}: SuccessCaseCardProps) {
  const [cases, setCases] = useState<SuccessCaseItem[]>(propCases || []);
  const [loading, setLoading] = useState(!propCases);

  // 从 API 获取
  useEffect(() => {
    if (propCases) {
      setCases(propCases);
      setLoading(false);
      return;
    }
    let cancelled = false;
    api.get<{ items: SuccessCaseItem[] }>('/api/social-proof/cases')
      .then(res => {
        if (!cancelled && res.data?.items && res.data.items.length > 0) {
          setCases(res.data.items.slice(0, maxCount));
        } else if (!cancelled) {
          setCases(FALLBACK_CASES);
        }
      })
      .catch(() => { if (!cancelled) setCases(FALLBACK_CASES); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [propCases, maxCount]);

  const displayCases = cases.length > 0 ? cases.slice(0, maxCount) : FALLBACK_CASES;

  return (
    <section className={`w-full ${className}`}>
      {/* 标题 */}
      {title && (
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-1 h-5 bg-gradient-to-b from-[var(--accent-primary)] to-[var(--accent-secondary)] rounded-full" />
            <h2 className="text-sm md:text-base font-bold text-[var(--text-primary)]">
              {title}
            </h2>
          </div>
          <span className="text-[10px] text-[var(--accent-primary)]/60 font-medium">
            实时更新中
          </span>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[1,2,3,4].map(i => (
            <div key={i} className="h-32 bg-[var(--bg-surface)] rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {displayCases.map(item => (
            <CaseCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}

/** 单个案例卡片 */
function CaseCard({ item }: { item: SuccessCaseItem }) {
  const metrics = item.metrics ? Object.entries(item.metrics) : [];

  return (
    <div
      className="group relative overflow-hidden rounded-xl border border-[var(--border-primary)]/60
        bg-[var(--bg-surface)]/40 backdrop-blur-sm
        hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-surface)]/60
        transition-all duration-300 p-3.5 md:p-4 cursor-default"
    >
      {/* Hover glow */}
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500
        bg-gradient-to-br from-[var(--accent-primary)]/5 to-transparent pointer-events-none" />

      {/* 头部：图标 + 企业名 */}
      <div className="relative flex items-start gap-2.5 mb-2">
        <span className="text-xl md:text-2xl shrink-0 mt-0.5">{item.icon || '🏢'}</span>
        <div className="min-w-0">
          <div className="text-[11px] font-bold text-[var(--accent-primary)] tracking-wide uppercase">
            {item.company}
          </div>
          <h3 className="text-sm font-bold text-[var(--text-primary)] leading-tight mt-0.5">
            {item.title}
          </h3>
        </div>
      </div>

      {/* 描述 */}
      <p className="relative text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-2 mb-2.5">
        {item.description}
      </p>

      {/* 指标 */}
      {metrics.length > 0 && (
        <div className="relative flex flex-wrap gap-2 mb-2">
          {metrics.slice(0, 3).map(([key, value]) => (
            <span
              key={key}
              className="inline-flex items-center gap-1 text-[10px] font-semibold
                px-2 py-0.5 rounded-full
                bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]
                border border-[var(--accent-primary)]/20"
            >
              {getMetricIcon(key)}
              <span>{value}</span>
              <span className="text-[var(--text-muted)] font-normal">{key}</span>
            </span>
          ))}
        </div>
      )}

      {/* 标签 */}
      {item.tags && item.tags.length > 0 && (
        <div className="relative flex flex-wrap gap-1.5">
          {item.tags.map(tag => (
            <span
              key={tag}
              className="text-[9px] px-1.5 py-0.5 rounded
                bg-[var(--bg-muted)] text-[var(--text-muted)]
                border border-[var(--border-primary)]/40"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
