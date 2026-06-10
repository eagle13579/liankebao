/**
 * 链客宝AI数据仪表盘
 * =================
 * 使用 ECharts CDN 渲染图表
 *
 * 功能:
 *   - 顶部4个KPI卡片: 总产品数, 总用户, 线索数, 已成交
 *   - 饼图: 管道阶段分布 (/api/v1/crm/pipeline)
 *   - 柱状图: 产品分类分布 (/api/v1/products + 前端统计分类)
 *   - 折线图: 月度线索趋势 ( mock 数据, 标注 "模拟数据" )
 *   - 表格: 最新10条线索 (/api/v1/crm/leads?limit=10)
 */

import React, { useEffect, useRef, useState } from 'react';

// ============================================================
// 类型定义
// ============================================================
interface KPIData {
  total_products: number;
  total_users: number;
  total_leads: number;
  total_deals: number;
}

interface PipelineStage {
  stage: string;
  count: number;
}

interface LeadItem {
  id: number;
  name: string;
  company?: string;
  phone?: string;
  source?: string;
  stage?: string;
  created_at: string;
}

interface ProductItem {
  id: number;
  name: string;
  category: string;
}

interface ApiResponse<T> {
  code: number;
  message: string;
  data?: T;
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
  const json: ApiResponse<T> = await res.json();
  if (json.code === 200 && json.data !== undefined) return json.data;
  if (json.code === undefined) return json as unknown as T; // 兼容扁平格式
  throw new Error(`API error: ${json.message}`);
}

function fmt(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return n.toLocaleString('zh-CN');
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
  } catch {
    return dateStr;
  }
}

// ============================================================
// ECharts 加载器
// ============================================================
function useECharts(): boolean {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if ((window as any).echarts) {
      setLoaded(true);
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js';
    script.onload = () => setLoaded(true);
    document.head.appendChild(script);
    return () => {
      if (script.parentNode) script.parentNode.removeChild(script);
    };
  }, []);

  return loaded;
}

// ============================================================
// KPI 卡片组件
// ============================================================
function KPICards({ data, loading }: { data: KPIData | null; loading: boolean }) {
  const cards = [
    { label: '总产品数', value: data ? fmt(data.total_products) : '--', icon: '📦', color: '#0ea5e9' },
    { label: '总用户', value: data ? fmt(data.total_users) : '--', icon: '👥', color: '#10b981' },
    { label: '线索数', value: data ? fmt(data.total_leads) : '--', icon: '📋', color: '#f59e0b' },
    { label: '已成交', value: data ? fmt(data.total_deals) : '--', icon: '✅', color: '#8b5cf6' },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-surface dark:bg-dark-surface rounded-xl p-5 shadow-sm border border-border-light dark:border-dark-border transition-all hover:shadow-md"
          style={{ borderLeft: `4px solid ${card.color}` }}
        >
          <div className="flex items-center gap-2 text-text-muted dark:text-dark-muted text-sm mb-2">
            <span>{card.icon}</span>
            <span>{card.label}</span>
          </div>
          <div className="text-2xl font-bold text-on-surface dark:text-dark-text">
            {loading ? (
              <span className="skeleton inline-block w-20 h-7 rounded" />
            ) : (
              card.value
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================
// ECharts 饼图 — 管道阶段分布
// ============================================================
function PipelinePieChart() {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<any>(null);
  const echartsLoaded = useECharts();
  const [data, setData] = useState<PipelineStage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<PipelineStage[]>('/api/v1/crm/pipeline')
      .then(setData)
      .catch((err) => {
        console.error('Pipeline fetch error:', err);
        setError(err.message);
      });
  }, []);

  useEffect(() => {
    if (!echartsLoaded || !chartRef.current) return;
    const echarts = (window as any).echarts;

    if (instanceRef.current) {
      instanceRef.current.dispose();
      instanceRef.current = null;
    }

    const chart = echarts.init(chartRef.current);
    instanceRef.current = chart;

    const colors = ['#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#ec4899'];

    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: {
        orient: 'vertical',
        right: 10,
        top: 'center',
        textStyle: { color: '#94a3b8', fontSize: 12 },
      },
      series: [
        {
          type: 'pie',
          radius: ['40%', '65%'],
          center: ['35%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 6, borderColor: 'transparent', borderWidth: 2 },
          label: { show: false },
          emphasis: {
            label: { show: true, fontSize: 14, fontWeight: 'bold', color: '#f1f5f9' },
            itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' },
          },
          data: data.length > 0
            ? data.map((d, i) => ({ value: d.count, name: d.stage, itemStyle: { color: colors[i % colors.length] } }))
            : [{ value: 1, name: '暂无数据', itemStyle: { color: '#334155' } }],
        },
      ],
    });

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (instanceRef.current) instanceRef.current.dispose();
    };
  }, [echartsLoaded, data]);

  return (
    <ChartCard title="📈 管道阶段分布" error={error}>
      <div ref={chartRef} style={{ width: '100%', height: 280 }} />
    </ChartCard>
  );
}

// ============================================================
// ECharts 柱状图 — 产品分类分布
// ============================================================
function CategoryBarChart() {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<any>(null);
  const echartsLoaded = useECharts();
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<{ name: string; count: number }[]>([]);

  useEffect(() => {
    fetchJson<ProductItem[]>('/api/v1/products')
      .then((products) => {
        const map = new Map<string, number>();
        (products || []).forEach((p) => {
          const cat = p.category || '未分类';
          map.set(cat, (map.get(cat) || 0) + 1);
        });
        const sorted = Array.from(map.entries())
          .map(([name, count]) => ({ name, count }))
          .sort((a, b) => b.count - a.count);
        setCategories(sorted);
      })
      .catch((err) => {
        console.error('Products fetch error:', err);
        setError(err.message);
      });
  }, []);

  useEffect(() => {
    if (!echartsLoaded || !chartRef.current) return;
    const echarts = (window as any).echarts;

    if (instanceRef.current) {
      instanceRef.current.dispose();
      instanceRef.current = null;
    }

    const chart = echarts.init(chartRef.current);
    instanceRef.current = chart;

    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: categories.length > 0 ? categories.map((c) => c.name) : ['暂无数据'],
        axisLabel: { color: '#94a3b8', fontSize: 11, rotate: categories.length > 6 ? 35 : 0 },
        axisLine: { lineStyle: { color: '#334155' } },
        axisTick: { alignWithLabel: true },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      series: [
        {
          type: 'bar',
          barWidth: '55%',
          data: categories.length > 0
            ? categories.map((c) => ({
                value: c.count,
                itemStyle: {
                  color: new (echarts.graphic as any).LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: '#0ea5e9' },
                    { offset: 1, color: '#38bdf8' },
                  ]),
                  borderRadius: [4, 4, 0, 0],
                },
              }))
            : [{ value: 0, itemStyle: { color: '#334155' } }],
          label: {
            show: categories.length > 0 && categories.length <= 10,
            position: 'top',
            color: '#94a3b8',
            fontSize: 11,
          },
        },
      ],
    });

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (instanceRef.current) instanceRef.current.dispose();
    };
  }, [echartsLoaded, categories]);

  return (
    <ChartCard title="📊 产品分类分布" error={error}>
      <div ref={chartRef} style={{ width: '100%', height: 280 }} />
    </ChartCard>
  );
}

// ============================================================
// ECharts 折线图 — 月度线索趋势 (mock)
// ============================================================
function MonthlyTrendLineChart() {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<any>(null);
  const echartsLoaded = useECharts();

  // 生成模拟数据: 最近12个月
  const mockData = (() => {
    const months: string[] = [];
    const values: number[] = [];
    const now = new Date();
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      months.push(`${d.getMonth() + 1}月`);
      values.push(Math.floor(Math.random() * 80) + 20 + (i === 0 ? 10 : 0)); // 最近一个月略高
    }
    return { months, values };
  })();

  useEffect(() => {
    if (!echartsLoaded || !chartRef.current) return;
    const echarts = (window as any).echarts;

    if (instanceRef.current) {
      instanceRef.current.dispose();
      instanceRef.current = null;
    }

    const chart = echarts.init(chartRef.current);
    instanceRef.current = chart;

    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: mockData.months,
        boundaryGap: false,
        axisLabel: { color: '#94a3b8', fontSize: 11 },
        axisLine: { lineStyle: { color: '#334155' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      },
      series: [
        {
          type: 'line',
          data: mockData.values,
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 3, color: '#10b981' },
          areaStyle: {
            color: new (echarts.graphic as any).LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(16, 185, 129, 0.3)' },
              { offset: 1, color: 'rgba(16, 185, 129, 0.02)' },
            ]),
          },
          itemStyle: { color: '#10b981' },
          markLine: {
            silent: true,
            data: [
              { yAxis: Math.round(mockData.values.reduce((a, b) => a + b, 0) / mockData.values.length), label: { formatter: '均值: {c}', color: '#f59e0b', fontSize: 11 }, lineStyle: { color: '#f59e0b', type: 'dashed' } },
            ],
          },
        },
      ],
    });

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (instanceRef.current) instanceRef.current.dispose();
    };
  }, [echartsLoaded]);

  return (
    <ChartCard title="📉 月度线索趋势" badge="模拟数据">
      <div ref={chartRef} style={{ width: '100%', height: 280 }} />
    </ChartCard>
  );
}

// ============================================================
// 图表卡片容器
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
// 最新线索表格
// ============================================================
function LatestLeadsTable() {
  const [leads, setLeads] = useState<LeadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<LeadItem[]>('/api/v1/crm/leads?limit=10')
      .then((data) => {
        setLeads(data || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Leads fetch error:', err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (error) {
    return (
      <div className="bg-surface dark:bg-dark-surface rounded-xl p-5 shadow-sm border border-border-light dark:border-dark-border">
        <h3 className="text-sm font-semibold text-on-surface dark:text-dark-text mb-4">🆕 最新线索</h3>
        <div className="flex items-center justify-center h-32 text-text-muted dark:text-dark-muted text-sm">
          ⚠️ {error}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface dark:bg-dark-surface rounded-xl p-5 shadow-sm border border-border-light dark:border-dark-border">
      <h3 className="text-sm font-semibold text-on-surface dark:text-dark-text mb-4">🆕 最新线索 (最近10条)</h3>
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-8 rounded" />
          ))}
        </div>
      ) : leads.length === 0 ? (
        <div className="flex items-center justify-center h-24 text-text-muted dark:text-dark-muted text-sm">
          暂无线索数据
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border-light dark:border-dark-border">
                <th className="text-left py-2 px-2 font-medium text-text-muted dark:text-dark-muted">姓名</th>
                <th className="text-left py-2 px-2 font-medium text-text-muted dark:text-dark-muted">公司</th>
                <th className="text-left py-2 px-2 font-medium text-text-muted dark:text-dark-muted">来源</th>
                <th className="text-left py-2 px-2 font-medium text-text-muted dark:text-dark-muted">阶段</th>
                <th className="text-left py-2 px-2 font-medium text-text-muted dark:text-dark-muted">日期</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr
                  key={lead.id}
                  className="border-b border-border-light/50 dark:border-dark-border/50 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                >
                  <td className="py-2.5 px-2 font-medium text-on-surface dark:text-dark-text">{lead.name || '--'}</td>
                  <td className="py-2.5 px-2 text-text-muted dark:text-dark-muted">{lead.company || '--'}</td>
                  <td className="py-2.5 px-2">
                    <span className="px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 text-[10px]">
                      {lead.source || '未知'}
                    </span>
                  </td>
                  <td className="py-2.5 px-2">
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10px]">
                      {lead.stage || '新线索'}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-text-muted dark:text-dark-muted">{formatDate(lead.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================
// 主页面
// ============================================================
export default function DashboardPage() {
  const [kpiData, setKpiData] = useState<KPIData | null>(null);
  const [kpiLoading, setKpiLoading] = useState(true);

  useEffect(() => {
    // 从多个接口汇总 KPI 数据
    Promise.all([
      fetchJson<any>('/api/v1/crm/leads?limit=1').catch(() => null),
      fetchJson<any[]>('/api/v1/products').catch(() => []),
    ])
      .then(([leadsRes, products]) => {
        // 线索总数从 leads 接口的响应 headers 或 count 获取
        const totalLeads = (leadsRes && (leadsRes.total || leadsRes.count || 0)) || 0;
        const totalProducts = Array.isArray(products) ? products.length : 0;

        // 剩余两个指标用 mock 或从其他接口补充
        // 实际项目中可从 /api/v1/admin/dashboard 获取
        setKpiData({
          total_products: totalProducts,
          total_users: 0, // 需要从用户接口获取
          total_leads: totalLeads,
          total_deals: 0, // 需要从订单/成交接口获取
        });
        setKpiLoading(false);
      })
      .catch(() => setKpiLoading(false));

    // 尝试从 dashboard 接口补充完整 KPI
    fetchJson<KPIData>('/api/v1/admin/dashboard')
      .then((data) => {
        if (data) setKpiData(data);
      })
      .catch(() => {
        // 静默失败, 保留已有数据
      });
  }, []);

  return (
    <div className="min-h-screen bg-neutral-bg dark:bg-dark-bg p-4 md:p-6">
      {/* 页面头部 */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-on-surface dark:text-dark-text">📊 数据仪表盘</h1>
        <p className="text-xs text-text-muted dark:text-dark-muted mt-1">链客宝AI全平台数据可视化看板</p>
      </div>

      {/* KPI 卡片 */}
      <KPICards data={kpiData} loading={kpiLoading} />

      {/* 图表区域: 2列网格 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <PipelinePieChart />
        <CategoryBarChart />
      </div>

      {/* 折线图: 全宽 */}
      <div className="mb-6">
        <MonthlyTrendLineChart />
      </div>

      {/* 线索表格 */}
      <div>
        <LatestLeadsTable />
      </div>
    </div>
  );
}
