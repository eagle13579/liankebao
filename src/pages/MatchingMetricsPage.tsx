/**
 * 匹配引擎 Metrics 看板
 * ======================
 * 展示匹配引擎实时运行状态
 *
 * API:
 *   - GET /api/matching/metrics/summary → 精选指标
 *   - POST /api/matching/metrics/adopt  → 记录采纳
 *
 * 功能:
 *   - 4个核心指标卡: 总匹配数 / 平均分 / 成功率 / 缓存命中率
 *   - 分类分布柱状图 (纯CSS)
 *   - 分数分布柱状图 (纯CSS)
 *   - 自动刷新 (每30秒)
 */

import React, { useEffect, useState, useCallback } from 'react';

// ============================================================
// 类型定义
// ============================================================
interface MatchingSummary {
  total_matches: number;
  match_success_rate: number;
  avg_match_score: number;
  avg_response_time_ms: number;
  cache_hit_rate: number;
  category_distribution: Record<string, number>;
  score_distribution: Record<string, number>;
}

// ============================================================
// 工具函数
// ============================================================
const API_BASE = '';

async function fetchJson<T>(url: string): Promise<T> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const res = await fetch(API_BASE + url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  const json = await res.json();
  if (json.code === 200 && json.data !== undefined) return json.data;
  if (json.code === undefined) return json as unknown as T;
  throw new Error(`API error: ${json.message}`);
}

function fmt(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return n.toLocaleString('zh-CN');
}

function pct(n: number): string {
  return (n * 100).toFixed(1) + '%';
}

// ============================================================
// 颜色方案
// ============================================================
const CARD_COLORS = [
  { border: '#0ea5e9', bg: 'rgba(14,165,233,0.08)', text: '#0ea5e9' },
  { border: '#10b981', bg: 'rgba(16,185,129,0.08)', text: '#10b981' },
  { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)', text: '#f59e0b' },
  { border: '#8b5cf6', bg: 'rgba(139,92,246,0.08)', text: '#8b5cf6' },
];

const BAR_COLORS = ['#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#ec4899', '#14b8a6', '#f97316'];

// ============================================================
// 核心指标卡片
// ============================================================
function MetricCards({ data, loading }: { data: MatchingSummary | null; loading: boolean }) {
  const cards = data
    ? [
        { label: '总匹配数', value: fmt(data.total_matches), icon: '📊', desc: '累计匹配请求次数' },
        { label: '平均匹配分', value: data.avg_match_score.toFixed(4), icon: '🏆', desc: '匹配质量平均分 (0~1)' },
        { label: '匹配成功率', value: pct(data.match_success_rate), icon: '✅', desc: '用户采纳率' },
        { label: '缓存命中率', value: pct(data.cache_hit_rate), icon: '⚡', desc: '缓存有效减少计算' },
      ]
    : [];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {(loading ? ['s1','s2','s3','s4'] : cards).map((card, i) => (
        <div
          key={i}
          className="bg-surface dark:bg-dark-surface rounded-xl p-5 shadow-sm border border-border-light dark:border-dark-border transition-all hover:shadow-md"
          style={{ borderLeft: `4px solid ${CARD_COLORS[i % CARD_COLORS.length].border}` }}
        >
          {loading ? (
            <>
              <div className="flex items-center gap-2 text-text-muted dark:text-dark-muted text-sm mb-2">
                <span className="skeleton inline-block w-4 h-4 rounded" />
                <span className="skeleton inline-block w-16 h-3 rounded" />
              </div>
              <div className="skeleton inline-block w-24 h-7 rounded mt-1" />
              <div className="skeleton inline-block w-20 h-2 rounded mt-2" />
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-text-muted dark:text-dark-muted text-sm mb-2">
                <span>{(card as any).icon}</span>
                <span>{(card as any).label}</span>
              </div>
              <div className="text-2xl font-bold text-on-surface dark:text-dark-text">
                {(card as any).value}
              </div>
              <div className="text-[11px] text-text-muted dark:text-dark-muted mt-1">
                {(card as any).desc}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

// ============================================================
// 卡片容器
// ============================================================
function ChartCard({
  title,
  children,
  error,
  badge,
}: {
  title: string;
  children: React.ReactNode;
  error?: string | null;
  badge?: string;
}) {
  return (
    <div className="bg-surface dark:bg-dark-surface rounded-xl p-5 shadow-sm border border-border-light dark:border-dark-border">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-on-surface dark:text-dark-text">{title}</h3>
        {badge && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
            {badge}
          </span>
        )}
      </div>
      {error ? (
        <div className="flex items-center justify-center h-48 text-text-muted dark:text-dark-muted text-sm">
          ⚠️ {error}
        </div>
      ) : (
        children
      )}
    </div>
  );
}

// ============================================================
// 分类分布柱状图 (纯CSS)
// ============================================================
function CategoryBarChart({ data }: { data: Record<string, number> | null }) {
  if (!data || Object.keys(data).length === 0) {
    return (
      <ChartCard title="📂 匹配分类分布">
        <div className="flex items-center justify-center h-48 text-text-muted dark:text-dark-muted text-sm">
          暂无分类数据
        </div>
      </ChartCard>
    );
  }

  const entries = Object.entries(data);
  const maxVal = Math.max(...entries.map(([, v]) => v));

  return (
    <ChartCard title="📂 匹配分类分布">
      <div className="space-y-3">
        {entries.map(([name, count], i) => (
          <div key={name}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-on-surface dark:text-dark-text truncate">{name}</span>
              <span className="text-text-muted dark:text-dark-muted font-medium ml-2">{count}</span>
            </div>
            <div className="w-full h-5 bg-neutral-bg dark:bg-dark-surface rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500 ease-out"
                style={{
                  width: `${Math.max((count / maxVal) * 100, 3)}%`,
                  backgroundColor: BAR_COLORS[i % BAR_COLORS.length],
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}

// ============================================================
// 分数分布柱状图 (纯CSS)
// ============================================================
function ScoreBarChart({ data }: { data: Record<string, number> | null }) {
  if (!data || Object.keys(data).length === 0) {
    return (
      <ChartCard title="📈 匹配分数分布">
        <div className="flex items-center justify-center h-48 text-text-muted dark:text-dark-muted text-sm">
          暂无分数数据
        </div>
      </ChartCard>
    );
  }

  const entries = Object.entries(data);
  const maxVal = Math.max(...entries.map(([, v]) => v));

  return (
    <ChartCard title="📈 匹配分数分布">
      <div className="space-y-3">
        {entries.map(([range, count], i) => (
          <div key={range}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-on-surface dark:text-dark-text">{range}</span>
              <span className="text-text-muted dark:text-dark-muted font-medium ml-2">{count}</span>
            </div>
            <div className="w-full h-5 bg-neutral-bg dark:bg-dark-surface rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500 ease-out"
                style={{
                  width: `${Math.max((count / maxVal) * 100, 3)}%`,
                  backgroundColor: '#10b981',
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}

// ============================================================
// 响应时间 & 采纳率 小卡片
// ============================================================
function ExtraStats({ data }: { data: MatchingSummary | null }) {
  if (!data) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
      <div className="bg-surface dark:bg-dark-surface rounded-xl p-5 shadow-sm border border-border-light dark:border-dark-border">
        <div className="flex items-center gap-2 text-text-muted dark:text-dark-muted text-sm mb-2">
          <span>⏱️</span>
          <span>平均响应时间</span>
        </div>
        <div className="text-xl font-bold text-on-surface dark:text-dark-text">
          {data.avg_response_time_ms.toFixed(1)} <span className="text-sm font-normal text-text-muted">ms</span>
        </div>
      </div>
      <div className="bg-surface dark:bg-dark-surface rounded-xl p-5 shadow-sm border border-border-light dark:border-dark-border">
        <div className="flex items-center gap-2 text-text-muted dark:text-dark-muted text-sm mb-2">
          <span>🎯</span>
          <span>匹配采纳率</span>
        </div>
        <div className="text-xl font-bold text-on-surface dark:text-dark-text">
          {pct(data.match_success_rate)}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 主页面组件
// ============================================================
export default function MatchingMetricsPage() {
  const [data, setData] = useState<MatchingSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const fetchData = useCallback(async () => {
    try {
      const result = await fetchJson<MatchingSummary>('/api/matching/metrics/summary');
      setData(result);
      setError(null);
      setLastUpdated(new Date().toLocaleTimeString('zh-CN'));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // 初始加载 + 自动刷新
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // 每30秒刷新
    return () => clearInterval(interval);
  }, [fetchData]);

  // 手动刷新
  const handleRefresh = () => {
    setLoading(true);
    fetchData();
  };

  // 记录采纳
  const handleAdopt = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;

      const res = await fetch(API_BASE + '/api/matching/metrics/adopt', {
        method: 'POST',
        headers,
      });
      const json = await res.json();
      if (json.code === 200) {
        // 刷新数据
        fetchData();
      }
    } catch (err: any) {
      console.error('Adopt error:', err);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-on-surface dark:text-dark-text">
            🤖 匹配引擎 Metrics
          </h1>
          <p className="text-xs text-text-muted dark:text-dark-muted mt-1">
            匹配引擎实时运行状态看板
            {lastUpdated && <span className="ml-2">· 上次更新: {lastUpdated}</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleAdopt}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
          >
            + 模拟采纳
          </button>
          <button
            onClick={handleRefresh}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors"
            disabled={loading}
          >
            {loading ? '刷新中...' : '⟳ 刷新'}
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          ⚠️ 数据加载失败: {error}
          <button
            onClick={handleRefresh}
            className="ml-3 underline hover:no-underline"
          >
            重试
          </button>
        </div>
      )}

      {/* 4个核心指标卡 */}
      <MetricCards data={data} loading={loading} />

      {/* 额外统计 */}
      <ExtraStats data={data} />

      {/* 图表区域 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <CategoryBarChart data={data?.category_distribution ?? null} />
        <ScoreBarChart data={data?.score_distribution ?? null} />
      </div>

      {/* 底部说明 */}
      <div className="text-center text-[10px] text-text-muted dark:text-dark-muted py-4 border-t border-border-light dark:border-dark-border">
        数据来源: GET /api/matching/metrics/summary · 每30秒自动刷新
      </div>
    </div>
  );
}
