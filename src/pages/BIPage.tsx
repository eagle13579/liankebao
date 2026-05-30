/**
 * 链客宝自建BI看板
 * ===================
 * 使用 Chart.js CDN 绘制趋势图表
 * 后端接口: /api/bi/*
 *
 * 功能:
 *   - 总览卡片(4项核心指标)
 *   - 收入趋势折线图(日/周/月)
 *   - 用户增长折线图
 *   - 热门产品TOP10榜单
 *   - AI名片统计
 *   - 转化漏斗柱状图 ← NEW
 *   - 留存率热力图 ← NEW
 *   - 数据导出CSV ← NEW
 */

import React, { useEffect, useRef, useState } from 'react';

// ============================================================
// 类型定义
// ============================================================
interface OverviewData {
  total_users: number;
  total_products: number;
  total_orders: number;
  today_registrations: number;
}

interface RevenueItem {
  date: string;
  revenue: number;
  orders: number;
}

interface TopProduct {
  id: number;
  name: string;
  price: number;
  category: string;
  order_count: number;
  total_revenue: number;
}

interface UserGrowthItem {
  date: string;
  new_users: number;
  cumulative: number;
}

interface CardDailyTrend {
  date: string;
  generated: number;
  views: number;
}

interface CardStatsData {
  total_cards: number;
  recent_cards: number;
  total_views: number;
  avg_views_per_card: number;
  daily_trend: CardDailyTrend[];
}

// === 新增类型: 漏斗 ===
interface FunnelStep {
  step: string;
  users: number;
  rate: number;
}

interface FunnelTransition {
  from: string;
  to: string;
  from_users: number;
  to_users: number;
  transition_rate: number;
}

interface FunnelData {
  steps: FunnelStep[];
  transitions: FunnelTransition[];
  period_days: number;
}

// === 新增类型: 留存 ===
interface RetentionPeriod {
  offset: number;
  label: string;
  active_users: number;
  retention_rate: number;
}

interface CohortRow {
  cohort: string;
  total_users: number;
  retention: RetentionPeriod[];
}

interface RetentionData {
  period: string;
  cohorts: CohortRow[];
}

// === 新增类型: 流失预警 ===
interface ChurnUser {
  id: number;
  name: string;
  company: string;
  phone: string;
  role: string;
  registered_at: string;
  days_since_registration: number;
}

interface ChurnRiskData {
  churn_users: ChurnUser[];
  total_risk_count: number;
  days_threshold: number;
  note: string;
}

// === 新增类型: 地域分布 ===
interface RegionItem {
  region: string;
  user_count: number;
}

interface GeoDistributionData {
  by_region: RegionItem[];
  total_regions: number;
  note: string;
}

interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

// ============================================================
// API 基础地址
// ============================================================
const API_BASE = '/api/bi';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }
  const body: ApiResponse<T> = await res.json();
  if (body.code !== 200) {
    throw new Error(`API error: ${body.message}`);
  }
  return body.data;
}

// ============================================================
// 工具函数
// ============================================================
function fmt(n: number): string {
  if (n >= 10000) {
    return (n / 10000).toFixed(1) + '万';
  }
  return n.toLocaleString('zh-CN');
}

/** 将任意数据导出为 CSV 文件 */
function downloadCSV(filename: string, headers: string[], rows: (string | number)[][]) {
  const csvContent = [
    headers.join(','),
    ...rows.map((row) => row.map((cell) => `"${cell}"`).join(',')),
  ].join('\n');

  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ============================================================
// 概览卡片组件
// ============================================================
function OverviewCards({ data }: { data: OverviewData | null }) {
  const cards = [
    { label: '总用户数', value: data ? fmt(data.total_users) : '--', icon: '👥', color: '#3B82F6' },
    { label: '总产品数', value: data ? fmt(data.total_products) : '--', icon: '📦', color: '#10B981' },
    { label: '总订单数', value: data ? fmt(data.total_orders) : '--', icon: '📋', color: '#F59E0B' },
    { label: '今日注册', value: data ? fmt(data.today_registrations) : '--', icon: '✨', color: '#EF4444' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
      {cards.map((card) => (
        <div
          key={card.label}
          style={{
            background: '#fff',
            borderRadius: 12,
            padding: '20px 24px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
            borderLeft: `4px solid ${card.color}`,
          }}
        >
          <div style={{ fontSize: 14, color: '#6B7280', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>{card.icon}</span>
            <span>{card.label}</span>
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#111827' }}>{card.value}</div>
        </div>
      ))}
    </div>
  );
}

// ============================================================
// Chart.js 折线图封装
// ============================================================
function LineChart({
  labels,
  datasets,
  title,
  height = 200,
}: {
  labels: string[];
  datasets: { label: string; data: number[]; color: string; fill?: boolean }[];
  title: string;
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<any>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if ((window as any).Chart) {
      setLoaded(true);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js';
    script.onload = () => setLoaded(true);
    document.head.appendChild(script);
    return () => {
      if (script.parentNode) script.parentNode.removeChild(script);
    };
  }, []);

  useEffect(() => {
    if (!loaded || !canvasRef.current) return;
    const Chart = (window as any).Chart;
    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    chartRef.current = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: datasets.map((ds) => ({
          label: ds.label,
          data: ds.data,
          borderColor: ds.color,
          backgroundColor: ds.fill ? ds.color + '20' : 'transparent',
          fill: ds.fill ?? false,
          tension: 0.3,
          pointRadius: 3,
          pointHoverRadius: 6,
          borderWidth: 2,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { font: { size: 12 } } },
          title: { display: true, text: title, font: { size: 14, weight: 'bold' }, padding: { bottom: 12 } },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 8, font: { size: 11 } }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { font: { size: 11 } }, grid: { color: '#f0f0f0' } },
        },
      },
    });
  }, [loaded, labels, datasets, title]);

  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.08)', height }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
}

// ============================================================
// 漏斗柱状图组件 ← NEW
// ============================================================
function FunnelChart({ data }: { data: FunnelData | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<any>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if ((window as any).Chart) {
      setLoaded(true);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js';
    script.onload = () => setLoaded(true);
    document.head.appendChild(script);
    return () => {
      if (script.parentNode) script.parentNode.removeChild(script);
    };
  }, []);

  useEffect(() => {
    if (!loaded || !canvasRef.current || !data) return;
    const Chart = (window as any).Chart;
    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    const colors = ['#3B82F6', '#8B5CF6', '#F59E0B', '#10B981'];
    const bgColors = ['#3B82F660', '#8B5CF660', '#F59E0B60', '#10B98160'];

    chartRef.current = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.steps.map((s) => s.step),
        datasets: [
          {
            label: '用户数',
            data: data.steps.map((s) => s.users),
            backgroundColor: bgColors,
            borderColor: colors,
            borderWidth: 2,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          title: { display: true, text: `转化漏斗 (近${data.period_days}天)`, font: { size: 14, weight: 'bold' }, padding: { bottom: 12 } },
          tooltip: {
            callbacks: {
              afterLabel: function (context: any) {
                const idx = context.dataIndex;
                const step = data.steps[idx];
                return `转化率: ${step.rate}%\n相对于上一步: ${idx > 0 ? data.transitions[idx - 1]?.transition_rate + '%' : '-'}`;
              },
            },
          },
        },
        scales: {
          x: { beginAtZero: true, grid: { color: '#f0f0f0' }, ticks: { font: { size: 11 } } },
          y: { grid: { display: false }, ticks: { font: { size: 12 } } },
        },
      },
    });
  }, [loaded, data]);

  // 手动加载状态
  useEffect(() => {
    if (loaded && !data) {
      setError('暂无漏斗数据');
    } else {
      setError(null);
    }
  }, [loaded, data]);

  if (!data) {
    return (
      <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)', height: 280 }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>🔻 转化漏斗</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {['注册', '创建名片', '发布需求', '下单'].map((step, i) => (
            <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 80, fontSize: 13, color: '#6B7280' }}>{step}</span>
              <div style={{ flex: 1, height: 24, background: '#F3F4F6', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ width: `${100 - i * 25}%`, height: '100%', background: ['#3B82F6', '#8B5CF6', '#F59E0B', '#10B981'][i], borderRadius: 4, opacity: 0.3 }} />
              </div>
              <span style={{ width: 60, fontSize: 12, color: '#9CA3AF', textAlign: 'right' }}>--</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.08)', height: 280 }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
}

// ============================================================
// 留存率热力图组件 ← NEW
// ============================================================
function RetentionHeatmap({ data }: { data: RetentionData | null }) {
  if (!data || !data.cohorts || data.cohorts.length === 0) {
    return (
      <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>📊 用户留存率</h3>
        <p style={{ color: '#9CA3AF', textAlign: 'center' }}>暂无留存数据</p>
      </div>
    );
  }

  const periodLabel = data.period === 'day' ? '日' : data.period === 'month' ? '月' : '周';
  const maxPeriods = Math.min(data.cohorts[0]?.retention?.length || 4, 8);

  /** 根据留存率返回颜色（越深越高） */
  function getColor(rate: number): string {
    if (rate >= 80) return '#065F46';
    if (rate >= 60) return '#059669';
    if (rate >= 40) return '#10B981';
    if (rate >= 20) return '#6EE7B7';
    if (rate >= 10) return '#A7F3D0';
    if (rate >= 5) return '#D1FAE5';
    return '#F3F4F6';
  }

  function getTextColor(rate: number): string {
    return rate >= 40 ? '#fff' : '#374151';
  }

  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)', overflowX: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>📊 用户留存率</h3>
        <span style={{ fontSize: 12, color: '#9CA3AF' }}>{(data.period === 'day' ? '按日' : data.period === 'month' ? '按月' : '按周') + '留存'}</span>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr>
            <th style={{ padding: '6px 8px', textAlign: 'left', color: '#6B7280', fontWeight: 500, borderBottom: '2px solid #E5E7EB', whiteSpace: 'nowrap' }}>
              注册时间
            </th>
            <th style={{ padding: '6px 8px', textAlign: 'center', color: '#6B7280', fontWeight: 500, borderBottom: '2px solid #E5E7EB' }}>
              用户数
            </th>
            {Array.from({ length: maxPeriods }).map((_, i) => (
              <th
                key={i}
                style={{
                  padding: '6px 4px',
                  textAlign: 'center',
                  color: '#6B7280',
                  fontWeight: 500,
                  borderBottom: '2px solid #E5E7EB',
                  minWidth: 50,
                }}
              >
                第{i + 1}{periodLabel}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.cohorts.map((cohort, ci) => (
            <tr key={cohort.cohort}>
              <td style={{ padding: '4px 8px', borderBottom: '1px solid #F3F4F6', whiteSpace: 'nowrap', color: '#374151' }}>
                {cohort.cohort}
              </td>
              <td style={{ padding: '4px 8px', borderBottom: '1px solid #F3F4F6', textAlign: 'center', fontWeight: 600, color: '#111827' }}>
                {cohort.total_users}
              </td>
              {Array.from({ length: maxPeriods }).map((_, i) => {
                const period = cohort.retention[i];
                const rate = period ? period.retention_rate : 0;
                return (
                  <td
                    key={i}
                    style={{
                      padding: '4px 4px',
                      borderBottom: '1px solid #F3F4F6',
                      textAlign: 'center',
                      background: getColor(rate),
                      color: getTextColor(rate),
                      fontWeight: rate > 0 ? 600 : 400,
                      borderRadius: 2,
                    }}
                  >
                    {rate > 0 ? rate.toFixed(1) + '%' : '-'}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {/* 颜色图例 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, justifyContent: 'flex-end' }}>
        <span style={{ fontSize: 11, color: '#9CA3AF' }}>低</span>
        {[0, 5, 10, 20, 40, 60, 80].map((v) => (
          <div
            key={v}
            style={{
              width: 16,
              height: 16,
              borderRadius: 2,
              background: getColor(v),
              border: '1px solid #E5E7EB',
            }}
          />
        ))}
        <span style={{ fontSize: 11, color: '#9CA3AF' }}>高</span>
      </div>
    </div>
  );
}

// ============================================================
// 流失预警列表组件 ← NEW
// ============================================================
function ChurnRiskList({ data }: { data: ChurnRiskData | null }) {
  if (!data) {
    return (
      <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>⚠️ 流失预警</h3>
        <p style={{ color: '#9CA3AF', textAlign: 'center' }}>暂无数据</p>
      </div>
    );
  }

  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>⚠️ 流失预警</h3>
        <span style={{ fontSize: 12, color: '#EF4444', fontWeight: 600 }}>
          潜在流失: {data.total_risk_count}人
        </span>
      </div>
      <p style={{ fontSize: 11, color: '#9CA3AF', margin: '0 0 12px' }}>{data.note}</p>

      {data.churn_users.length === 0 ? (
        <p style={{ color: '#10B981', fontSize: 13, textAlign: 'center', padding: 16 }}>✅ 暂无潜在流失用户</p>
      ) : (
        <div style={{ maxHeight: 300, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ padding: '6px 8px', textAlign: 'left', color: '#6B7280', fontWeight: 500, borderBottom: '1px solid #E5E7EB' }}>姓名</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', color: '#6B7280', fontWeight: 500, borderBottom: '1px solid #E5E7EB' }}>公司</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', color: '#6B7280', fontWeight: 500, borderBottom: '1px solid #E5E7EB' }}>角色</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', color: '#6B7280', fontWeight: 500, borderBottom: '1px solid #E5E7EB' }}>注册天数</th>
              </tr>
            </thead>
            <tbody>
              {data.churn_users.slice(0, 20).map((u) => (
                <tr key={u.id}>
                  <td style={{ padding: '4px 8px', borderBottom: '1px solid #F3F4F6', color: '#374151' }}>{u.name}</td>
                  <td style={{ padding: '4px 8px', borderBottom: '1px solid #F3F4F6', color: '#6B7280' }}>{u.company || '-'}</td>
                  <td style={{ padding: '4px 8px', borderBottom: '1px solid #F3F4F6' }}>
                    <span style={{ background: '#FEF3C7', color: '#92400E', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
                      {u.role}
                    </span>
                  </td>
                  <td style={{ padding: '4px 8px', borderBottom: '1px solid #F3F4F6', textAlign: 'center', color: '#EF4444', fontWeight: 600 }}>
                    {u.days_since_registration}天
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <button
        onClick={() => {
          const headers = ['ID', '姓名', '公司', '手机', '角色', '注册日期', '注册天数'];
          const rows = data.churn_users.map((u) => [
            u.id,
            u.name,
            u.company,
            u.phone,
            u.role,
            u.registered_at,
            u.days_since_registration,
          ]);
          downloadCSV('churn-risk-users.csv', headers, rows);
        }}
        style={{
          marginTop: 12,
          padding: '6px 14px',
          fontSize: 12,
          borderRadius: 6,
          border: '1px solid #D1D5DB',
          background: '#fff',
          cursor: 'pointer',
          color: '#374151',
        }}
      >
        📥 导出CSV
      </button>
    </div>
  );
}

// ============================================================
// 地域分布组件 ← NEW
// ============================================================
function GeoDistribution({ data }: { data: GeoDistributionData | null }) {
  if (!data || !data.by_region || data.by_region.length === 0) {
    return (
      <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>🌍 用户地域分布</h3>
        <p style={{ color: '#9CA3AF', textAlign: 'center', fontSize: 12 }}>
          暂无地域数据
          <br />
          <span style={{ fontSize: 11 }}>用户发布需求时填写region后生成</span>
        </p>
      </div>
    );
  }

  const maxCount = Math.max(...data.by_region.map((r) => r.user_count), 1);

  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>🌍 用户地域分布</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.by_region.slice(0, 10).map((r) => (
          <div key={r.region} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 80, fontSize: 13, color: '#374151', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {r.region}
            </span>
            <div style={{ flex: 1, height: 20, background: '#F3F4F6', borderRadius: 4, overflow: 'hidden' }}>
              <div
                style={{
                  width: `${(r.user_count / maxCount) * 100}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, #3B82F6, #8B5CF6)',
                  borderRadius: 4,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
            <span style={{ width: 40, fontSize: 12, color: '#6B7280', textAlign: 'right', fontWeight: 600 }}>
              {r.user_count}
            </span>
          </div>
        ))}
      </div>
      {data.by_region.length > 10 && (
        <p style={{ fontSize: 11, color: '#9CA3AF', textAlign: 'center', marginTop: 8 }}>
          ...还有 {data.by_region.length - 10} 个地区
        </p>
      )}
    </div>
  );
}

// ============================================================
// TOP10 榜单组件
// ============================================================
function TopProducts({ data }: { data: TopProduct[] | null }) {
  if (!data || data.length === 0) {
    return (
      <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>🏆 热门产品 TOP10</h3>
        <p style={{ color: '#9CA3AF', textAlign: 'center' }}>暂无数据</p>
      </div>
    );
  }

  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>🏆 热门产品 TOP10</h3>
        <button
          onClick={() => {
            const headers = ['排名', '产品名', '分类', '价格', '订单数', '总收入'];
            const rows = data.map((p, i) => [i + 1, p.name, p.category, p.price, p.order_count, p.total_revenue]);
            downloadCSV('top-products.csv', headers, rows);
          }}
          style={{
            padding: '4px 10px',
            fontSize: 11,
            borderRadius: 6,
            border: '1px solid #D1D5DB',
            background: '#fff',
            cursor: 'pointer',
            color: '#6B7280',
          }}
        >
          📥 CSV
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {data.map((product, idx) => (
          <div key={product.id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span
              style={{
                width: 24,
                height: 24,
                borderRadius: '50%',
                background: idx < 3 ? '#F59E0B' : '#E5E7EB',
                color: idx < 3 ? '#fff' : '#6B7280',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 12,
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              {idx + 1}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {product.name}
              </div>
              <div style={{ fontSize: 11, color: '#9CA3AF' }}>{product.category}</div>
            </div>
            <div style={{ width: 120, textAlign: 'right', fontSize: 12, color: '#6B7280' }}>
              ¥{product.total_revenue.toLocaleString('zh-CN')}
            </div>
            <div style={{ width: 80, textAlign: 'right' }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#3B82F6' }}>{product.order_count}单</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// 卡片统计组件
// ============================================================
function CardStats({ data }: { data: CardStatsData | null }) {
  if (!data) {
    return (
      <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>📇 AI数字名片统计</h3>
        <p style={{ color: '#9CA3AF', textAlign: 'center' }}>暂无数据</p>
      </div>
    );
  }

  const cards = [
    { label: '总名片数', value: fmt(data.total_cards), color: '#8B5CF6' },
    { label: '近30天新增', value: fmt(data.recent_cards), color: '#EC4899' },
    { label: '总浏览量', value: fmt(data.total_views), color: '#14B8A6' },
    { label: '平均浏览', value: data.avg_views_per_card.toString(), color: '#F97316' },
  ];

  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>📇 AI数字名片统计</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12 }}>
        {cards.map((card) => (
          <div key={card.label} style={{ textAlign: 'center', padding: '12px 8px', background: '#F9FAFB', borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>{card.label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: card.color }}>{card.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// 时间段选择器
// ============================================================
function PeriodSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const options = [
    { value: 'day', label: '按日' },
    { value: 'week', label: '按周' },
    { value: 'month', label: '按月' },
  ];
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <span style={{ fontSize: 13, color: '#6B7280' }}>周期:</span>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: value === opt.value ? '1px solid #3B82F6' : '1px solid #D1D5DB',
            background: value === opt.value ? '#EFF6FF' : '#fff',
            color: value === opt.value ? '#3B82F6' : '#374151',
            fontSize: 12,
            cursor: 'pointer',
            fontWeight: value === opt.value ? 600 : 400,
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ============================================================
// 留存周期选择器 ← NEW
// ============================================================
function RetentionPeriodSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const options = [
    { value: 'day', label: '日留存' },
    { value: 'week', label: '周留存' },
    { value: 'month', label: '月留存' },
  ];
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <span style={{ fontSize: 13, color: '#6B7280' }}>留存:</span>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: value === opt.value ? '1px solid #8B5CF6' : '1px solid #D1D5DB',
            background: value === opt.value ? '#F5F3FF' : '#fff',
            color: value === opt.value ? '#8B5CF6' : '#374151',
            fontSize: 12,
            cursor: 'pointer',
            fontWeight: value === opt.value ? 600 : 400,
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ============================================================
// 加载指示器
// ============================================================
function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60 }}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: '50%',
          border: '3px solid #E5E7EB',
          borderTop: '3px solid #3B82F6',
          animation: 'spin 0.8s linear infinite',
        }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  );
}

// ============================================================
// 导出全部CSV按钮 ← NEW
// ============================================================
function ExportAllButton({
  overview,
  revenue,
  userGrowth,
  funnel,
  churnRisk,
}: {
  overview: OverviewData | null;
  revenue: RevenueItem[];
  userGrowth: UserGrowthItem[];
  funnel: FunnelData | null;
  churnRisk: ChurnRiskData | null;
}) {
  const handleExportAll = () => {
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');

    // 1. 总览
    if (overview) {
      downloadCSV(`overview-${timestamp}.csv`, ['指标', '数值'], [
        ['总用户数', overview.total_users],
        ['总产品数', overview.total_products],
        ['总订单数', overview.total_orders],
        ['今日注册', overview.today_registrations],
      ]);
    }

    // 2. 收入趋势
    if (revenue.length > 0) {
      downloadCSV(`revenue-${timestamp}.csv`, ['日期', '收入', '订单数'], revenue.map((r) => [r.date, r.revenue, r.orders]));
    }

    // 3. 用户增长
    if (userGrowth.length > 0) {
      downloadCSV(`user-growth-${timestamp}.csv`, ['日期', '新增用户', '累计'], userGrowth.map((g) => [g.date, g.new_users, g.cumulative]));
    }

    // 4. 漏斗
    if (funnel) {
      downloadCSV(`funnel-${timestamp}.csv`, ['步骤', '用户数', '转化率%'], funnel.steps.map((s) => [s.step, s.users, s.rate]));
    }

    // 5. 流失预警
    if (churnRisk && churnRisk.churn_users.length > 0) {
      downloadCSV(`churn-risk-${timestamp}.csv`, ['ID', '姓名', '公司', '角色', '注册天数'], churnRisk.churn_users.map((u) => [u.id, u.name, u.company, u.role, u.days_since_registration]));
    }
  };

  return (
    <button
      onClick={handleExportAll}
      style={{
        padding: '8px 18px',
        fontSize: 13,
        borderRadius: 8,
        border: 'none',
        background: '#10B981',
        color: '#fff',
        cursor: 'pointer',
        fontWeight: 600,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}
      title="导出所有数据为CSV文件"
    >
      📥 批量导出CSV
    </button>
  );
}

// ============================================================
// 主 BI 看板页面
// ============================================================
export default function BIPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [revenue, setRevenue] = useState<RevenueItem[]>([]);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [userGrowth, setUserGrowth] = useState<UserGrowthItem[]>([]);
  const [cardStats, setCardStats] = useState<CardStatsData | null>(null);
  const [funnel, setFunnel] = useState<FunnelData | null>(null);
  const [retention, setRetention] = useState<RetentionData | null>(null);
  const [churnRisk, setChurnRisk] = useState<ChurnRiskData | null>(null);
  const [geoDistribution, setGeoDistribution] = useState<GeoDistributionData | null>(null);
  const [period, setPeriod] = useState('month');
  const [retentionPeriod, setRetentionPeriod] = useState('week');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'advanced'>('overview');

  useEffect(() => {
    const abortController = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const results = await Promise.allSettled([
          fetchJson<OverviewData>(`${API_BASE}/overview`),
          fetchJson<RevenueItem[]>(`${API_BASE}/revenue?period=${period}&days=30`),
          fetchJson<TopProduct[]>(`${API_BASE}/top-products?limit=10`),
          fetchJson<UserGrowthItem[]>(`${API_BASE}/user-growth?days=30`),
          fetchJson<CardStatsData>(`${API_BASE}/card-stats?days=30`),
          fetchJson<FunnelData>(`${API_BASE}/funnel?days=90`),
          fetchJson<RetentionData>(`${API_BASE}/retention?period=${retentionPeriod}&cohorts=12`),
          fetchJson<ChurnRiskData>(`${API_BASE}/churn-risk?days_since_activity=7`),
          fetchJson<GeoDistributionData>(`${API_BASE}/geo-distribution`),
        ]);

        if (!abortController.signal.aborted) {
          // 基础API
          if (results[0].status === 'fulfilled') setOverview(results[0].value);
          if (results[1].status === 'fulfilled') setRevenue(results[1].value);
          if (results[2].status === 'fulfilled') setTopProducts(results[2].value);
          if (results[3].status === 'fulfilled') setUserGrowth(results[3].value);
          if (results[4].status === 'fulfilled') setCardStats(results[4].value);

          // 高级API
          if (results[5].status === 'fulfilled') setFunnel(results[5].value);
          if (results[6].status === 'fulfilled') setRetention(results[6].value);
          if (results[7].status === 'fulfilled') setChurnRisk(results[7].value);
          if (results[8].status === 'fulfilled') setGeoDistribution(results[8].value);

          // 收集错误
          const errors = results.filter((r) => r.status === 'rejected').map((r: any) => r.reason?.message);
          if (errors.length > 0) {
            setError('部分数据加载失败: ' + errors.join('; '));
          }
        }
      } catch (err: any) {
        if (!abortController.signal.aborted) {
          setError(err.message || '数据加载失败');
        }
      } finally {
        if (!abortController.signal.aborted) {
          setLoading(false);
        }
      }
    }

    load();
    return () => abortController.abort();
  }, [period, retentionPeriod]);

  // 准备图表数据
  const revenueLabels = revenue.map((r) => r.date);
  const revenueData = revenue.map((r) => r.revenue);

  const growthLabels = userGrowth.map((g) => g.date);
  const growthNewUsers = userGrowth.map((g) => g.new_users);
  const growthCumulative = userGrowth.map((g) => g.cumulative);

  if (loading) return <Loading />;

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '24px 16px' }}>
      {/* 页面标题 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#111827' }}>📊 链客宝 BI 看板</h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#6B7280' }}>
              实时数据聚合 · 自建轻量仪表盘
            </p>
          </div>
          {/* Tab 切换 */}
          <div style={{ display: 'flex', gap: 4, background: '#F3F4F6', borderRadius: 8, padding: 2 }}>
            <button
              onClick={() => setActiveTab('overview')}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                border: 'none',
                background: activeTab === 'overview' ? '#fff' : 'transparent',
                color: activeTab === 'overview' ? '#3B82F6' : '#6B7280',
                fontSize: 13,
                fontWeight: activeTab === 'overview' ? 600 : 400,
                cursor: 'pointer',
                boxShadow: activeTab === 'overview' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              基础看板
            </button>
            <button
              onClick={() => setActiveTab('advanced')}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                border: 'none',
                background: activeTab === 'advanced' ? '#fff' : 'transparent',
                color: activeTab === 'advanced' ? '#8B5CF6' : '#6B7280',
                fontSize: 13,
                fontWeight: activeTab === 'advanced' ? 600 : 400,
                cursor: 'pointer',
                boxShadow: activeTab === 'advanced' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              高级分析
            </button>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ExportAllButton
            overview={overview}
            revenue={revenue}
            userGrowth={userGrowth}
            funnel={funnel}
            churnRisk={churnRisk}
          />
          {activeTab === 'overview' && <PeriodSelector value={period} onChange={setPeriod} />}
          {activeTab === 'advanced' && <RetentionPeriodSelector value={retentionPeriod} onChange={setRetentionPeriod} />}
        </div>
      </div>

      {error && (
        <div
          style={{
            background: '#FEF2F2',
            color: '#B91C1C',
            padding: '12px 16px',
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
            border: '1px solid #FECACA',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* ===== 基础看板 Tab ===== */}
      {activeTab === 'overview' && (
        <>
          <OverviewCards data={overview} />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 16, marginBottom: 24 }}>
            <LineChart
              labels={revenueLabels}
              datasets={[{ label: '收入 (¥)', data: revenueData, color: '#10B981', fill: true }]}
              title="收入趋势"
              height={260}
            />
            <LineChart
              labels={growthLabels}
              datasets={[
                { label: '新增用户', data: growthNewUsers, color: '#3B82F6' },
                { label: '累计用户', data: growthCumulative, color: '#8B5CF6', fill: true },
              ]}
              title="用户增长"
              height={260}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: 16 }}>
            <TopProducts data={topProducts} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <CardStats data={cardStats} />
              <div
                style={{
                  background: '#fff',
                  borderRadius: 12,
                  padding: 24,
                  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                }}
              >
                <h3 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600 }}>⏰ 数据说明</h3>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#6B7280', lineHeight: 1.8 }}>
                  <li>所有数据从数据库实时聚合，非缓存数据</li>
                  <li>收入统计仅含已支付/已收货的订单</li>
                  <li>用户增长含全部注册用户（不含软删除）</li>
                  <li>热门产品按订单数排序</li>
                  <li>名片统计含所有未删除名片</li>
                </ul>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ===== 高级分析 Tab ===== */}
      {activeTab === 'advanced' && (
        <>
          {/* 第一行: 漏斗 + 地域分布 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 16, marginBottom: 24 }}>
            <FunnelChart data={funnel} />
            <GeoDistribution data={geoDistribution} />
          </div>

          {/* 留存率热力图 */}
          <div style={{ marginBottom: 24 }}>
            <RetentionHeatmap data={retention} />
          </div>

          {/* 流失预警 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 16 }}>
            <ChurnRiskList data={churnRisk} />
            <div
              style={{
                background: '#fff',
                borderRadius: 12,
                padding: 24,
                boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              }}
            >
              <h3 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600 }}>🔬 高级分析说明</h3>
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#6B7280', lineHeight: 1.8 }}>
                <li><strong>转化漏斗:</strong> 注册→创建名片→发布需求→下单 各步骤转化率</li>
                <li><strong>留存率:</strong> 按注册时间段分组，追踪后续活跃回访比例</li>
                <li><strong>流失预警:</strong> 注册超过7天且无任何活动（0订单、0名片）的用户</li>
                <li><strong>地域分布:</strong> 基于用户发布需求时填写的地区信息</li>
                <li>点击 <strong>📥 批量导出CSV</strong> 下载所有分析数据</li>
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
