/**
 * 链客宝 — 信任评分仪表盘
 * 路由: /trust
 * 数据: GET /api/trust/score/{user_id}
 *
 * 设计文档: docs/trust_score_ui_design.md
 * 包含:
 *   - SVG 环形信任分仪表盘 (渐变色: red→yellow→green→blue)
 *   - 信任等级徽章 (bronze/silver/gold/platinum)
 *   - 三维度分解卡片 (身份认证/行为信用/担保网络)
 *   - 提升建议区域
 */

import React, { useState, useEffect, useMemo } from 'react';

/* ============ Types ============ */

interface ScoreDimension {
  score: number;
  max: number;
  weight: number;
  detail: Record<string, number>;
}

interface TrustScoreData {
  user_id: number;
  trust_score: number;
  trust_level: 'bronze' | 'silver' | 'gold' | 'platinum';
  level_progress: number;
  next_level: string;
  next_level_at: number;
  breakdown: {
    identity: ScoreDimension;
    behavior: ScoreDimension;
    guarantee: ScoreDimension;
  };
  updated_at: string;
}

/* ============ Constants ============ */

const LEVEL_META: Record<string, { label: string; icon: string; color: string; bg: string; range: [number, number]; benefits: string[] }> = {
  bronze: {
    label: 'Bronze',
    icon: '🥉',
    color: '#CD7F32',
    bg: '#FFF8F0',
    range: [0, 250],
    benefits: ['基础匹配额度 (3次/月)', '基础搜索', '标准推荐'],
  },
  silver: {
    label: 'Silver',
    icon: '🥈',
    color: '#A8B8CC',
    bg: '#F5F8FC',
    range: [251, 500],
    benefits: ['中等匹配额度 (20次/月)', '高级筛选', '优先排序'],
  },
  gold: {
    label: 'Gold',
    icon: '🥇',
    color: '#D4A017',
    bg: '#FFFDF5',
    range: [501, 750],
    benefits: ['高匹配额度', '高级筛选', '排名优先', '专属标识'],
  },
  platinum: {
    label: 'Platinum',
    icon: '💎',
    color: '#7B5EA7',
    bg: '#F8F5FF',
    range: [751, 1000],
    benefits: ['无限制匹配', '优先推荐', '专属客服', '顶级标识'],
  },
};

const DIMENSION_META: Record<string, { label: string; icon: string; color: string; bg: string }> = {
  identity: {
    label: '身份认证',
    icon: '🆔',
    color: '#4A90D9',
    bg: '#F0F6FF',
  },
  behavior: {
    label: '行为信用',
    icon: '🎯',
    color: '#50B86C',
    bg: '#F0FBF4',
  },
  guarantee: {
    label: '担保网络',
    icon: '🔗',
    color: '#F5A623',
    bg: '#FFFBF0',
  },
};

const DIMENSION_DETAIL_LABELS: Record<string, Record<string, string>> = {
  identity: {
    real_name_verified: '实名认证',
    enterprise_verified: '企业资质',
    industry_tags: '行业标签',
    contact_info: '联系方式',
    enterprise_data_match: '企业数据匹配',
  },
  behavior: {
    activity: '活跃度',
    match_response: '匹配响应',
    feedback_quality: '反馈质量',
    deal_completion: '交易完成',
    penalty: '违规扣分',
  },
  guarantee: {
    guarantors_count: '担保人数量',
    guaranteed_count: '被担保人数',
    chain_depth: '担保链深度',
    avg_guarantor_score: '担保人信用均值',
  },
};

const DIMENSION_DETAIL_SUFFIX: Record<string, Record<string, string>> = {
  guarantee: {
    guarantors_count: '人',
    guaranteed_count: '人',
    chain_depth: '级',
    avg_guarantor_score: '分',
  },
};

const SUGGESTIONS = [
  { icon: '💡', text: '完成企业资质验证 → +40 分', action: '完善资料', impact: 40 },
  { icon: '💡', text: '邀请一位信誉良好的用户为您担保 → +15 分', action: '邀请担保', impact: 15 },
  { icon: '💡', text: '回复待处理的匹配请求 → +20 分', action: '查看匹配', impact: 20 },
  { icon: '💡', text: '完善行业标签信息 → +20 分', action: '完善资料', impact: 20 },
];

// Mock data for development
const MOCK_DATA: TrustScoreData = {
  user_id: 10086,
  trust_score: 672,
  trust_level: 'gold',
  level_progress: 0.688,
  next_level: 'platinum',
  next_level_at: 751,
  breakdown: {
    identity: {
      score: 280,
      max: 350,
      weight: 0.35,
      detail: { real_name_verified: 50, enterprise_verified: 100, industry_tags: 60, contact_info: 40, enterprise_data_match: 30 },
    },
    behavior: {
      score: 260,
      max: 400,
      weight: 0.40,
      detail: { activity: 75, match_response: 80, feedback_quality: 45, deal_completion: 60, penalty: 0 },
    },
    guarantee: {
      score: 132,
      max: 250,
      weight: 0.25,
      detail: { guarantors_count: 3, guaranteed_count: 2, chain_depth: 2, avg_guarantor_score: 780 },
    },
  },
  updated_at: '2026-06-25T10:30:00Z',
};

/* ============ Utility Functions ============ */

function getLevel(score: number): string {
  if (score <= 250) return 'bronze';
  if (score <= 500) return 'silver';
  if (score <= 750) return 'gold';
  return 'platinum';
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return dateStr;
  }
}

/* ============ Sub-components ============ */

/** SVG 环形信任分仪表盘 */
function TrustScoreGauge({ score, size = 220 }: { score: number; size?: number }) {
  const strokeWidth = 16;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = score / 1000;
  const offset = circumference * (1 - progress);

  const level = getLevel(score);
  const meta = LEVEL_META[level];

  // SVG gradient ID
  const gradientId = 'trust-score-gradient';

  return (
    <div className="relative flex flex-col items-center">
      <svg width={size} height={size} className="transform -rotate-90">
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#EF4444" />
            <stop offset="33%" stopColor="#F59E0B" />
            <stop offset="67%" stopColor="#10B981" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
        </defs>
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#E5E7EB"
          strokeWidth={strokeWidth}
        />
        {/* Progress ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      {/* Center content */}
      <div
        className="absolute flex flex-col items-center justify-center"
        style={{ width: size, height: size }}
      >
        <span className="text-4xl font-bold" style={{ color: meta.color }}>
          {score}
        </span>
        <span className="text-sm font-medium text-neutral-500 mt-1">/ 1000</span>
      </div>
    </div>
  );
}

/** 信任等级徽章 + 进度条 */
function TrustLevelBadge({
  level,
  score,
  levelProgress,
  nextLevel,
  nextLevelAt,
}: {
  level: string;
  score: number;
  levelProgress: number;
  nextLevel: string;
  nextLevelAt: number;
}) {
  const meta = LEVEL_META[level];
  const nextMeta = LEVEL_META[nextLevel];
  const progressPct = Math.round(levelProgress * 100);
  const pointsToNext = nextLevelAt - score;

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Level badge */}
      <div
        className="inline-flex items-center gap-2 px-4 py-2 rounded-full border text-sm font-semibold"
        style={{
          backgroundColor: meta.bg,
          borderColor: meta.color,
          color: meta.color,
        }}
      >
        <span className="text-lg">{meta.icon}</span>
        <span>{meta.label}</span>
      </div>

      {/* Progress bar to next level */}
      {nextLevel && (
        <div className="w-full max-w-xs">
          <div className="flex justify-between text-xs text-neutral-500 mb-1">
            <span>当前等级进度</span>
            <span>{progressPct}%</span>
          </div>
          <div className="h-2.5 bg-neutral-200 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${progressPct}%`,
                background: `linear-gradient(90deg, ${meta.color}, ${nextMeta.color})`,
              }}
            />
          </div>
          <div className="flex justify-between text-xs text-neutral-400 mt-1">
            <span>{score} 分</span>
            <span>
              还差 <strong className="text-neutral-600">{pointsToNext}</strong> 分升至 {nextMeta.icon} {nextMeta.label}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

/** 等级权益卡 */
function LevelBenefitsCard({ level }: { level: string }) {
  const meta = LEVEL_META[level];

  return (
    <div
      className="rounded-xl p-4 border"
      style={{
        backgroundColor: meta.bg,
        borderColor: meta.color + '40',
      }}
    >
      <div className="text-sm font-semibold text-neutral-700 mb-3 flex items-center gap-2">
        <span>{meta.icon}</span>
        <span>{meta.label} 权益</span>
      </div>
      <ul className="space-y-2">
        {meta.benefits.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-neutral-600">
            <span className="text-success mt-0.5">✓</span>
            <span>{b}</span>
          </li>
        ))}
      </ul>
      <button className="mt-3 text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors">
        升级指南 →
      </button>
    </div>
  );
}

/** 单项维度分解卡片 */
function DimensionCard({
  dimKey,
  data,
}: {
  dimKey: string;
  data: ScoreDimension;
}) {
  const meta = DIMENSION_META[dimKey];
  const detailLabels = DIMENSION_DETAIL_LABELS[dimKey] || {};
  const detailSuffix = DIMENSION_DETAIL_SUFFIX[dimKey] || {};
  const pct = Math.round((data.score / data.max) * 100);
  const weightPct = Math.round(data.weight * 100);

  return (
    <div
      className="rounded-xl border p-5 flex flex-col gap-4"
      style={{
        backgroundColor: meta.bg,
        borderColor: meta.color + '30',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{meta.icon}</span>
          <span className="font-semibold text-neutral-800">{meta.label}</span>
        </div>
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-white border text-neutral-500">
          权重 {weightPct}%
        </span>
      </div>

      {/* Score bar */}
      <div>
        <div className="flex justify-between text-sm mb-1">
          <span className="font-bold" style={{ color: meta.color }}>
            {data.score} / {data.max}
          </span>
          <span className="text-neutral-500">{pct}%</span>
        </div>
        <div className="h-2.5 bg-neutral-200 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${pct}%`,
              backgroundColor: meta.color,
            }}
          />
        </div>
      </div>

      {/* Detail items */}
      <div className="space-y-2">
        {Object.entries(data.detail).map(([key, val]) => {
          const label = detailLabels[key] || key;
          const suffix = detailSuffix[key] || '';
          // For penalty, display differently
          if (key === 'penalty') {
            return (
              <div key={key} className="flex justify-between text-xs">
                <span className="text-neutral-500">{label}</span>
                <span className={val < 0 ? 'text-danger font-medium' : 'text-neutral-500'}>
                  {val}
                </span>
              </div>
            );
          }
          // For guarantor fields, show the raw value
          if (dimKey === 'guarantee' && suffix) {
            return (
              <div key={key} className="flex justify-between text-xs">
                <span className="text-neutral-500">{label}</span>
                <span className="text-neutral-700 font-medium">
                  {val}
                  {suffix}
                </span>
              </div>
            );
          }
          // Default: show score / max
          return (
            <div key={key} className="flex items-center gap-2 text-xs">
              <div className="flex-1 text-neutral-500 truncate">{label}</div>
              <div className="w-20 h-1.5 bg-neutral-200 rounded-full overflow-hidden flex-shrink-0">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(val / (key === 'avg_guarantor_score' ? 1000 : data.max)) * 100}%`,
                    backgroundColor: val > 0 ? meta.color : '#D1D5DB',
                  }}
                />
              </div>
              <span className="text-neutral-600 font-medium w-10 text-right">{val}</span>
            </div>
          );
        })}
      </div>

      <button
        className="text-xs font-medium self-start"
        style={{ color: meta.color }}
      >
        {dimKey === 'identity' ? '完善资料 →' : dimKey === 'behavior' ? '行为记录 →' : '担保网络 →'}
      </button>
    </div>
  );
}

/** 提升建议区域 */
function ImprovementSuggestions() {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5">
      <h3 className="text-sm font-semibold text-neutral-800 mb-4 flex items-center gap-2">
        <span>📈</span> 提升建议
      </h3>
      <div className="space-y-3">
        {SUGGESTIONS.map((s, i) => (
          <div
            key={i}
            className="flex items-center justify-between p-3 rounded-lg bg-neutral-50 hover:bg-neutral-100 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className="text-base">{s.icon}</span>
              <span className="text-sm text-neutral-700">{s.text}</span>
            </div>
            <button className="text-xs font-medium px-3 py-1.5 rounded-full bg-brand-500 text-white hover:bg-brand-600 transition-colors">
              {s.action}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Loading skeleton */
function LoadingSkeleton() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 animate-pulse">
      <div className="h-8 w-48 bg-neutral-200 rounded mb-8" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="lg:col-span-2 bg-neutral-100 rounded-xl h-72" />
        <div className="bg-neutral-100 rounded-xl h-72" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-neutral-100 rounded-xl h-56" />
        ))}
      </div>
      <div className="bg-neutral-100 rounded-xl h-40" />
    </div>
  );
}

/** Error state */
function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="max-w-5xl mx-auto px-4 py-16 flex flex-col items-center gap-4">
      <span className="text-5xl">⚠️</span>
      <h2 className="text-lg font-semibold text-neutral-700">加载失败</h2>
      <p className="text-sm text-neutral-500 text-center max-w-md">{message}</p>
      <button
        onClick={onRetry}
        className="px-6 py-2 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 transition-colors"
      >
        重新加载
      </button>
    </div>
  );
}

/* ============ Main Page Component ============ */

export default function TrustScorePage() {
  const [data, setData] = useState<TrustScoreData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchTrustScore = async () => {
    setLoading(true);
    setError(null);
    try {
      // Try real API first
      const userId = 10086; // Would come from auth context in production
      const res = await fetch(`/api/trust/score/${userId}`);
      if (!res.ok) throw new Error(`API 返回状态码: ${res.status}`);
      const json = await res.json();
      if (json.code === 200 && json.data) {
        setData(json.data);
        setLastUpdated(json.data.updated_at);
      } else {
        throw new Error(json.message || '数据格式异常');
      }
    } catch (err) {
      // Fall back to mock data for development
      console.warn('Trust API 不可用，使用模拟数据:', err);
      setData(MOCK_DATA);
      setLastUpdated(MOCK_DATA.updated_at);
      if (err instanceof TypeError && err.message === 'Failed to fetch') {
        // Silent fallback for network errors
      } else {
        setError(err instanceof Error ? err.message : '未知错误');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const res = await fetch('/api/trust/refresh', { method: 'POST' });
      if (res.ok) {
        const json = await res.json();
        if (json.code === 200) {
          // Re-fetch after refresh
          await fetchTrustScore();
        }
      }
    } catch {
      // Refresh failed, just re-fetch
      await fetchTrustScore();
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchTrustScore();
  }, []);

  // --- Loading state ---
  if (loading && !data) {
    return <LoadingSkeleton />;
  }

  // --- Error state (no data at all) ---
  if (error && !data) {
    return <ErrorState message={error} onRetry={fetchTrustScore} />;
  }

  // --- We should have data by now ---
  if (!data) {
    return <ErrorState message="暂无数据" onRetry={fetchTrustScore} />;
  }

  const level = data.trust_level;
  const meta = LEVEL_META[level];

  return (
    <div className="min-h-screen bg-neutral-50">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* ===== Header ===== */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🛡️</span>
            <h1 className="text-xl font-bold text-neutral-900">信任中心</h1>
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-neutral-400">更新于 {formatDate(lastUpdated)}</span>
            )}
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-600 hover:bg-neutral-100 transition-colors disabled:opacity-50"
            >
              <svg
                className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              {refreshing ? '刷新中...' : '刷新'}
            </button>
          </div>
        </div>

        {/* ===== Top Section: Gauge + Level Badge + Benefits ===== */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Gauge + Level Progress */}
          <div className="lg:col-span-2 rounded-xl border border-neutral-200 bg-white p-6 flex flex-col md:flex-row items-center gap-8">
            {/* Ring Gauge */}
            <div className="flex-shrink-0">
              <TrustScoreGauge score={data.trust_score} size={200} />
            </div>

            {/* Level Info */}
            <div className="flex-1 flex flex-col items-center md:items-start gap-4 w-full">
              <TrustLevelBadge
                level={data.trust_level}
                score={data.trust_score}
                levelProgress={data.level_progress}
                nextLevel={data.next_level}
                nextLevelAt={data.next_level_at}
              />
            </div>
          </div>

          {/* Benefits Card */}
          <div>
            <LevelBenefitsCard level={level} />
          </div>
        </div>

        {/* ===== Dimension Breakdown ===== */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-neutral-800">信任分分解</h2>
            <button className="text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors">
              详情 →
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(data.breakdown).map(([dimKey, dimData]) => (
              <DimensionCard key={dimKey} dimKey={dimKey} data={dimData} />
            ))}
          </div>
        </div>

        {/* ===== Improvement Suggestions ===== */}
        <ImprovementSuggestions />

        {/* ===== Footer Info ===== */}
        <div className="mt-6 text-center text-xs text-neutral-400">
          信任分基于身份认证、行为信用和担保网络三维度综合计算，每日自动更新。
        </div>
      </div>
    </div>
  );
}
