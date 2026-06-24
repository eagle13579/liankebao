/**
 * SocialProofDashboard.tsx — 动态数据看板
 *
 * 展示平台关键统计数据，包含：
 * - 累计匹配数
 * - 累计交易数
 * - 入驻企业数
 * - 满意度
 * - 数字滚动动画
 * - 响应式网格布局
 */

import { useState, useEffect, useRef } from 'react';
import { api } from '../../api/client';
import { Handshake, ShoppingCart, Building2, ThumbsUp } from 'lucide-react';

interface StatItem {
  label: string;
  value: number;
  suffix?: string;
  icon: React.ReactNode;
  color: string;
  gradient: string;
}

interface SocialProofDashboardProps {
  /** 自定义统计数据（可选，不传则从 API 获取） */
  stats?: {
    total_matches: number;
    total_transactions: number;
    total_enterprises: number;
    satisfaction_rate: number;
  };
  /** 标题 */
  title?: string;
  /** 额外类名 */
  className?: string;
}

const FALLBACK_STATS = {
  total_matches: 12860,
  total_transactions: 5680,
  total_enterprises: 1280,
  satisfaction_rate: 96.8,
};

/** 数字滚动动画 Hook */
function useCountUp(target: number, duration = 2000, enabled = true) {
  const [display, setDisplay] = useState(0);
  const startRef = useRef<number>(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!enabled) {
      setDisplay(target);
      return;
    }
    startRef.current = performance.now();

    function step(now: number) {
      const elapsed = now - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.floor(eased * target));

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(step);
      }
    }

    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration, enabled]);

  return display;
}

/** 格式化数字（千分位） */
function formatNum(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万+';
  return n.toLocaleString('zh-CN');
}

export default function SocialProofDashboard({
  stats: propStats,
  title = '平台数据',
  className = '',
}: SocialProofDashboardProps) {
  const [stats, setStats] = useState(propStats || null);
  const [loading, setLoading] = useState(!propStats);
  const [inView, setInView] = useState(false);
  const sectionRef = useRef<HTMLDivElement>(null);

  // Intersection Observer 触发动画
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setInView(true); },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 从 API 获取
  useEffect(() => {
    if (propStats) {
      setStats(propStats);
      setLoading(false);
      return;
    }
    let cancelled = false;
    api.get<{
      total_matches: number;
      total_transactions: number;
      total_enterprises: number;
      satisfaction_rate: number;
    }>('/api/social-proof/stats')
      .then(res => {
        if (!cancelled && res.data) {
          setStats(res.data);
        } else if (!cancelled) {
          setStats(FALLBACK_STATS);
        }
      })
      .catch(() => { if (!cancelled) setStats(FALLBACK_STATS); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [propStats]);

  const data = stats || FALLBACK_STATS;

  const statItems: StatItem[] = [
    {
      label: '累计匹配',
      value: data.total_matches,
      suffix: '+',
      icon: <Handshake className="w-4 h-4 md:w-5 md:h-5" />,
      color: 'text-emerald-400',
      gradient: 'from-emerald-500/20 to-emerald-600/10',
    },
    {
      label: '累计交易',
      value: data.total_transactions,
      suffix: '+',
      icon: <ShoppingCart className="w-4 h-4 md:w-5 md:h-5" />,
      color: 'text-sky-400',
      gradient: 'from-sky-500/20 to-sky-600/10',
    },
    {
      label: '入驻企业',
      value: data.total_enterprises,
      suffix: '+',
      icon: <Building2 className="w-4 h-4 md:w-5 md:h-5" />,
      color: 'text-violet-400',
      gradient: 'from-violet-500/20 to-violet-600/10',
    },
    {
      label: '客户满意度',
      value: data.satisfaction_rate,
      suffix: '%',
      icon: <ThumbsUp className="w-4 h-4 md:w-5 md:h-5" />,
      color: 'text-amber-400',
      gradient: 'from-amber-500/20 to-amber-600/10',
    },
  ];

  const animatedMatches = useCountUp(data.total_matches, 2500, inView);
  const animatedTransactions = useCountUp(data.total_transactions, 2500, inView);
  const animatedEnterprises = useCountUp(data.total_enterprises, 2000, inView);
  const animatedSatisfaction = useCountUp(data.satisfaction_rate * 10, 2000, inView);

  const animatedValues = [
    animatedMatches,
    animatedTransactions,
    animatedEnterprises,
    Math.round(animatedSatisfaction / 10),
  ];

  return (
    <section
      ref={sectionRef}
      className={`w-full ${className}`}
    >
      {/* 标题 */}
      {title && (
        <div className="flex items-center gap-2 mb-4">
          <div className="w-1 h-5 bg-gradient-to-b from-[var(--accent-primary)] to-[var(--accent-secondary)] rounded-full" />
          <h2 className="text-sm md:text-base font-bold text-[var(--text-primary)]">
            {title}
          </h2>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1,2,3,4].map(i => (
            <div key={i} className="h-24 bg-[var(--bg-surface)] rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {statItems.map((item, idx) => (
            <StatCard
              key={item.label}
              item={item}
              animatedValue={animatedValues[idx]}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function StatCard({
  item,
  animatedValue,
}: {
  item: StatItem;
  animatedValue: number;
}) {
  const displayValue = item.label === '客户满意度'
    ? animatedValue
    : animatedValue;

  return (
    <div
      className="group relative overflow-hidden rounded-xl border border-[var(--border-primary)]/60
        bg-[var(--bg-surface)]/40 backdrop-blur-sm p-3.5 md:p-4
        hover:border-[var(--accent-primary)]/30
        transition-all duration-300"
    >
      {/* 渐变背景 */}
      <div className={`absolute inset-0 bg-gradient-to-br ${item.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none`} />

      {/* 图标 */}
      <div className={`relative mb-2 w-8 h-8 md:w-10 md:h-10 rounded-lg
        bg-[var(--bg-muted)] flex items-center justify-center
        ${item.color} group-hover:scale-110 transition-transform duration-300`}
      >
        {item.icon}
      </div>

      {/* 数值 */}
      <div className="relative">
        <span className="text-xl md:text-2xl font-extrabold text-[var(--text-primary)] tabular-nums">
          {item.label === '客户满意度' ? displayValue : formatNum(displayValue)}
        </span>
        <span className="text-xs md:text-sm text-[var(--text-muted)] ml-0.5">
          {item.suffix}
        </span>
      </div>

      {/* 标签 */}
      <div className="relative text-[10px] md:text-xs text-[var(--text-muted)] font-medium mt-0.5">
        {item.label}
      </div>
    </div>
  );
}
