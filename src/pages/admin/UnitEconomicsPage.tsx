/**
 * M6 心智模型注入 — 单位经济仪表盘（前端）
 * ==========================================
 * 链客宝运营面板：LTV/CAC 计算与单位经济健康检查。
 * 后端 API: /api/unit-economics/*
 */
import React, { useCallback, useEffect, useState } from 'react';

const API_BASE = '/api/unit-economics';

interface UnitEcoData {
  period: string;
  days: number;
  cac_metrics: { total_acquisition_cost: number; new_customers: number; cac: number };
  ltv_metrics: { avg_order_value: number; purchase_frequency: number; avg_customer_lifetime_months: number; ltv: number };
  core_ratios: { ltv_cac_ratio: number; payback_months: number; health_status: string };
  auxiliary: { total_revenue: number; gross_margin: number; churn_rate: number };
}

interface SnapshotItem {
  id: number;
  period: string;
  cac: number;
  ltv: number;
  ltv_cac_ratio: number;
  payback_months: number;
  churn_rate: number;
  created_at: string;
}

interface HealthCheck {
  status: string;
  ltv_cac_ratio: number;
  ltv: number;
  cac: number;
  payback_months: number;
  churn_rate: number;
  advice: string;
}

function getAuthHeaders() {
  const t = localStorage.getItem('token') || '';
  return { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

async function apiGet<T>(url: string): Promise<T> {
  return fetch(url, { headers: getAuthHeaders() }).then(r => r.json());
}

export default function UnitEconomicsPage() {
  const [ecoData, setEcoData] = useState<UnitEcoData | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('monthly');
  const [days, setDays] = useState(90);
  const [tab, setTab] = useState<'compute' | 'history' | 'health'>('compute');
  const [error, setError] = useState('');

  const compute = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiGet<{ code: number; data: UnitEcoData }>(`${API_BASE}/compute?period=${period}&days=${days}`);
      if (res.code === 200) setEcoData(res.data);
      else setError('计算失败');
    } catch { setError('请求失败'); }
    setLoading(false);
  }, [period, days]);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ code: number; data: SnapshotItem[] }>(`${API_BASE}/snapshots?limit=20`);
      if (res.code === 200) setSnapshots(res.data);
    } catch {}
    setLoading(false);
  }, []);

  const checkHealth = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ code: number; data: HealthCheck }>(`${API_BASE}/health-check`);
      if (res.code === 200) setHealth(res.data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    if (tab === 'compute') compute();
    else if (tab === 'history') loadHistory();
    else if (tab === 'health') checkHealth();
  }, [tab, compute, loadHistory, checkHealth]);

  const healthColor = (s: string) => s === 'pass' ? 'text-emerald-600' : s === 'warning' ? 'text-amber-600' : 'text-rose-600';
  const healthBg = (s: string) => s === 'pass' ? 'bg-emerald-50 border-emerald-200' : s === 'warning' ? 'bg-amber-50 border-amber-200' : 'bg-rose-50 border-rose-200';

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">📊 M6 单位经济门禁</h1>
        <p className="text-sm text-slate-500 mt-1">LTV/CAC 仪表盘 — 让每一分钱都有据可查</p>
      </div>

      {error && <div className="bg-rose-50 border border-rose-200 text-rose-700 p-3 rounded-lg mb-4 text-sm">{error}</div>}

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(['compute', 'history', 'health'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${tab === t ? 'bg-slate-800 text-white' : 'bg-white border text-slate-600 hover:bg-slate-50'}`}>
            {t === 'compute' ? '实时计算' : t === 'history' ? '历史快照' : '健康检查'}
          </button>
        ))}
      </div>

      {/* Tab: Compute */}
      {tab === 'compute' && (
        <>
          <div className="flex gap-4 items-center mb-6">
            <select value={period} onChange={e => setPeriod(e.target.value)} className="border rounded-lg px-3 py-2 text-sm">
              <option value="daily">每日</option>
              <option value="weekly">每周</option>
              <option value="monthly">每月</option>
            </select>
            <select value={days} onChange={e => setDays(parseInt(e.target.value))} className="border rounded-lg px-3 py-2 text-sm">
              <option value={30}>30天</option>
              <option value={90}>90天</option>
              <option value={180}>180天</option>
              <option value={365}>365天</option>
            </select>
            <button onClick={compute} className="bg-sky-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-sky-700">
              {loading ? '计算中...' : '开始计算'}
            </button>
          </div>

          {ecoData && (
            <div className="space-y-6">
              {/* Core Ratio Card */}
              <div className={`rounded-2xl border-2 p-6 text-center ${healthBg(ecoData.core_ratios.health_status === '健康' ? 'pass' : ecoData.core_ratios.health_status === '临界' ? 'warning' : 'danger')}`}>
                <p className="text-sm text-slate-500 mb-1">LTV / CAC 比值</p>
                <p className={`text-5xl font-black ${healthColor(ecoData.core_ratios.health_status === '健康' ? 'pass' : ecoData.core_ratios.health_status === '临界' ? 'warning' : 'danger')}`}>
                  {ecoData.core_ratios.ltv_cac_ratio}
                </p>
                <p className={`text-sm font-bold mt-2 ${healthColor(ecoData.core_ratios.health_status === '健康' ? 'pass' : ecoData.core_ratios.health_status === '临界' ? 'warning' : 'danger')}`}>
                  {ecoData.core_ratios.health_status} {ecoData.core_ratios.ltv_cac_ratio >= 3 ? '✅' : ecoData.core_ratios.ltv_cac_ratio >= 1 ? '⚠️' : '🚨'}
                </p>
                <p className="text-xs text-slate-400 mt-1">健康阈值: LTV/CAC ≥ 3</p>
              </div>

              {/* Two Column Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white rounded-xl border p-5">
                  <h3 className="font-bold text-slate-700 mb-3">💰 CAC 获客成本</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between p-2 bg-slate-50 rounded"><span className="text-sm text-slate-500">总获客成本</span><span className="font-bold">¥{ecoData.cac_metrics.total_acquisition_cost.toLocaleString()}</span></div>
                    <div className="flex justify-between p-2 bg-slate-50 rounded"><span className="text-sm text-slate-500">新增客户</span><span className="font-bold">{ecoData.cac_metrics.new_customers}</span></div>
                    <div className="flex justify-between p-2 bg-sky-50 rounded"><span className="text-sm text-sky-700 font-bold">CAC</span><span className="font-bold text-sky-700">¥{ecoData.cac_metrics.cac.toFixed(2)}</span></div>
                  </div>
                </div>
                <div className="bg-white rounded-xl border p-5">
                  <h3 className="font-bold text-slate-700 mb-3">📈 LTV 客户价值</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between p-2 bg-slate-50 rounded"><span className="text-sm text-slate-500">平均客单价</span><span className="font-bold">¥{ecoData.ltv_metrics.avg_order_value.toFixed(2)}</span></div>
                    <div className="flex justify-between p-2 bg-slate-50 rounded"><span className="text-sm text-slate-500">购买频次</span><span className="font-bold">{ecoData.ltv_metrics.purchase_frequency}x</span></div>
                    <div className="flex justify-between p-2 bg-slate-50 rounded"><span className="text-sm text-slate-500">生命周期</span><span className="font-bold">{ecoData.ltv_metrics.avg_customer_lifetime_months}月</span></div>
                    <div className="flex justify-between p-2 bg-emerald-50 rounded"><span className="text-sm text-emerald-700 font-bold">LTV</span><span className="font-bold text-emerald-700">¥{ecoData.ltv_metrics.ltv.toFixed(2)}</span></div>
                  </div>
                </div>
              </div>

              {/* Auxiliary */}
              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-bold text-slate-700 mb-3">📋 辅助指标</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center p-3 bg-slate-50 rounded-xl"><p className="text-xs text-slate-400">回本周期</p><p className="font-bold text-lg">{ecoData.core_ratios.payback_months}月</p></div>
                  <div className="text-center p-3 bg-slate-50 rounded-xl"><p className="text-xs text-slate-400">总收入</p><p className="font-bold text-lg">¥{ecoData.auxiliary.total_revenue.toLocaleString()}</p></div>
                  <div className="text-center p-3 bg-slate-50 rounded-xl"><p className="text-xs text-slate-400">流失率</p><p className="font-bold text-lg">{ecoData.auxiliary.churn_rate}%</p></div>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* Tab: History */}
      {tab === 'history' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : snapshots.length === 0 ? (
            <div className="text-center py-12 text-slate-400">暂无历史快照，请先计算</div>
          ) : (
            <div className="bg-white rounded-xl border overflow-hidden">
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase tracking-widest font-bold">
                  <tr><th className="px-4 py-3">时间</th><th className="px-4 py-3">周期</th><th className="px-4 py-3">CAC</th><th className="px-4 py-3">LTV</th><th className="px-4 py-3">LTV/CAC</th><th className="px-4 py-3">回本(月)</th><th className="px-4 py-3">流失率</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {snapshots.map(s => (
                    <tr key={s.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-xs text-slate-400">{new Date(s.created_at).toLocaleString('zh-CN')}</td>
                      <td className="px-4 py-3">{s.period}</td>
                      <td className="px-4 py-3 font-mono">¥{s.cac.toFixed(2)}</td>
                      <td className="px-4 py-3 font-mono">¥{s.ltv.toFixed(2)}</td>
                      <td className={`px-4 py-3 font-bold font-mono ${s.ltv_cac_ratio >= 3 ? 'text-emerald-600' : s.ltv_cac_ratio >= 1 ? 'text-amber-600' : 'text-rose-600'}`}>{s.ltv_cac_ratio}</td>
                      <td className="px-4 py-3">{s.payback_months}</td>
                      <td className="px-4 py-3">{s.churn_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Tab: Health */}
      {tab === 'health' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">检查中...</div> : !health ? (
            <div className="text-center py-12 text-slate-400">尚无数据，请先计算</div>
          ) : (
            <div className={`rounded-2xl border-2 p-8 ${healthBg(health.status)}`}>
              <div className="text-center mb-6">
                <p className={`text-6xl font-black ${healthColor(health.status)}`}>
                  {health.status === 'pass' ? '✅' : health.status === 'warning' ? '⚠️' : '🚨'}
                </p>
                <p className={`text-2xl font-bold mt-2 ${healthColor(health.status)}`}>
                  {health.status === 'pass' ? '单位经济健康' : health.status === 'warning' ? '临界状态' : '单位经济不健康'}
                </p>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="text-center bg-white/80 rounded-xl p-3"><p className="text-xs text-slate-400">LTV/CAC</p><p className="font-bold text-xl">{health.ltv_cac_ratio}</p></div>
                <div className="text-center bg-white/80 rounded-xl p-3"><p className="text-xs text-slate-400">LTV</p><p className="font-bold text-xl">¥{health.ltv.toFixed(2)}</p></div>
                <div className="text-center bg-white/80 rounded-xl p-3"><p className="text-xs text-slate-400">CAC</p><p className="font-bold text-xl">¥{health.cac.toFixed(2)}</p></div>
                <div className="text-center bg-white/80 rounded-xl p-3"><p className="text-xs text-slate-400">回本周期</p><p className="font-bold text-xl">{health.payback_months}月</p></div>
              </div>
              <div className="bg-white/60 rounded-xl p-4">
                <p className="text-sm font-bold mb-1">💡 建议</p>
                <p className="text-sm text-slate-700">{health.advice}</p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
