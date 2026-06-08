/**
 * M7 心智模型注入 — 留存分析看板（前端）
 * ==========================================
 * 链客宝用户留存分析：群组留存、留存概览、流失预警。
 * 后端 API: /api/retention/*
 */
import React, { useCallback, useEffect, useState } from 'react';

const API_BASE = '/api/retention';

interface RetentionOverview {
  d1: { label: string; total_users: number; retained: number; retention_rate: number };
  d7: { label: string; total_users: number; retained: number; retention_rate: number };
  d30: { label: string; total_users: number; retained: number; retention_rate: number };
}

interface CohortItem {
  cohort_label: string;
  total_users: number;
  retention: Array<{ week_offset: number; label: string; active_users: number; retention_rate: number }>;
}

interface CohortData {
  cohorts: CohortItem[];
  period: string;
  lookback_weeks: number;
}

interface RiskUser {
  user_id: number;
  name: string;
  company: string;
  registered_days: number;
  total_orders: number;
  risk_level: string;
}

interface ChurnData {
  total_at_risk: number;
  risk_users: RiskUser[];
}

interface EngagementData {
  total_users: number;
  active_30d: number;
  active_30d_rate: number;
  engagement_tiers: { high_value: number; medium: number; low: number; dormant: number };
}

function getAuthHeaders() {
  const t = localStorage.getItem('token') || '';
  return { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}
async function apiGet<T>(url: string): Promise<T> {
  return fetch(url, { headers: getAuthHeaders() }).then(r => r.json());
}

export default function RetentionDashboardPage() {
  const [tab, setTab] = useState<'overview' | 'cohort' | 'churn' | 'engagement'>('overview');
  const [overview, setOverview] = useState<RetentionOverview | null>(null);
  const [cohort, setCohort] = useState<CohortData | null>(null);
  const [churn, setChurn] = useState<ChurnData | null>(null);
  const [engagement, setEngagement] = useState<EngagementData | null>(null);
  const [loading, setLoading] = useState(true);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: RetentionOverview }>(`${API_BASE}/overview`);
    if (res.code === 200) setOverview(res.data);
    setLoading(false);
  }, []);

  const loadCohort = useCallback(async () => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: CohortData }>(`${API_BASE}/cohort?lookback_weeks=12`);
    if (res.code === 200) setCohort(res.data);
    setLoading(false);
  }, []);

  const loadChurn = useCallback(async () => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: ChurnData }>(`${API_BASE}/churn-risk`);
    if (res.code === 200) setChurn(res.data);
    setLoading(false);
  }, []);

  const loadEngagement = useCallback(async () => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: EngagementData }>(`${API_BASE}/engagement`);
    if (res.code === 200) setEngagement(res.data);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (tab === 'overview') loadOverview();
    else if (tab === 'cohort') loadCohort();
    else if (tab === 'churn') loadChurn();
    else if (tab === 'engagement') loadEngagement();
  }, [tab, loadOverview, loadCohort, loadChurn, loadEngagement]);

  const retentionColor = (rate: number) => {
    if (rate >= 30) return 'bg-emerald-100 text-emerald-700';
    if (rate >= 15) return 'bg-amber-100 text-amber-700';
    return 'bg-rose-100 text-rose-700';
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">📈 M7 留存为王</h1>
        <p className="text-sm text-slate-500 mt-1">用户留存分析看板 — 留存是增长的核心</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(['overview', 'cohort', 'churn', 'engagement'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${tab === t ? 'bg-slate-800 text-white' : 'bg-white border text-slate-600 hover:bg-slate-50'}`}>
            {t === 'overview' ? '留存概览' : t === 'cohort' ? '群组留存' : t === 'churn' ? '流失预警' : '活跃度分布'}
          </button>
        ))}
      </div>

      {/* Tab: Overview */}
      {tab === 'overview' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : !overview ? (
            <div className="text-center py-12 text-slate-400">暂无数据</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {[overview.d1, overview.d7, overview.d30].map(item => (
                <div key={item.label} className="bg-white rounded-xl border p-6 text-center hover:shadow-md transition-shadow">
                  <p className="text-sm text-slate-500 mb-2">{item.label}</p>
                  <p className={`text-4xl font-black ${retentionColor(item.retention_rate)}`}>
                    {item.retention_rate}%
                  </p>
                  <div className="flex justify-between mt-4 text-xs text-slate-400">
                    <span>留存: {item.retained}</span>
                    <span>基数: {item.total_users}</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2 mt-3">
                    <div className={`h-2 rounded-full transition-all ${item.retention_rate >= 30 ? 'bg-emerald-500' : item.retention_rate >= 15 ? 'bg-amber-500' : 'bg-rose-500'}`}
                      style={{ width: `${Math.min(item.retention_rate, 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab: Cohort */}
      {tab === 'cohort' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : !cohort ? (
            <div className="text-center py-12 text-slate-400">暂无数据</div>
          ) : (
            <div className="bg-white rounded-xl border overflow-x-auto">
              <table className="w-full text-center text-xs">
                <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider">
                  <tr>
                    <th className="px-3 py-3 text-left">注册群组</th>
                    <th className="px-3 py-3">用户数</th>
                    {Array.from({ length: 12 }, (_, i) => (
                      <th key={i} className="px-3 py-3">第{i}周</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {cohort.cohorts.map(c => (
                    <tr key={c.cohort_label} className="hover:bg-slate-50">
                      <td className="px-3 py-2 text-left font-bold text-slate-700">{c.cohort_label}</td>
                      <td className="px-3 py-2 font-mono">{c.total_users}</td>
                      {c.retention.map(r => (
                        <td key={r.week_offset}
                          className="px-3 py-2 font-mono"
                          style={{
                            backgroundColor: r.retention_rate > 0
                              ? `rgba(59, 130, 246, ${Math.min(r.retention_rate / 100, 1)})`
                              : 'transparent',
                            color: r.retention_rate > 30 ? 'white' : 'inherit',
                          }}>
                          {r.retention_rate > 0 ? `${r.retention_rate}%` : '-'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Tab: Churn */}
      {tab === 'churn' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : !churn ? (
            <div className="text-center py-12 text-slate-400">暂无数据</div>
          ) : (
            <div>
              <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 mb-6 flex items-center gap-3">
                <span className="text-2xl">🚨</span>
                <div>
                  <p className="font-bold text-rose-800">{churn.total_at_risk} 个用户处于流失风险中</p>
                  <p className="text-sm text-rose-600">建议及时进行召回触达</p>
                </div>
              </div>
              {churn.risk_users.length === 0 ? (
                <div className="text-center py-12 text-slate-400">暂无流失风险用户 🎉</div>
              ) : (
                <div className="bg-white rounded-xl border overflow-hidden">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase tracking-widest font-bold">
                      <tr><th className="px-4 py-3">用户</th><th className="px-4 py-3">公司</th><th className="px-4 py-3">注册天数</th><th className="px-4 py-3">订单数</th><th className="px-4 py-3">风险等级</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {churn.risk_users.map(u => (
                        <tr key={u.user_id} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-medium">{u.name}</td>
                          <td className="px-4 py-3 text-slate-500">{u.company || '-'}</td>
                          <td className="px-4 py-3">{u.registered_days}天</td>
                          <td className="px-4 py-3">{u.total_orders}</td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${u.risk_level === '高' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}>
                              {u.risk_level}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Tab: Engagement */}
      {tab === 'engagement' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : !engagement ? (
            <div className="text-center py-12 text-slate-400">暂无数据</div>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white rounded-xl border p-6 text-center">
                  <p className="text-sm text-slate-500">总用户数</p>
                  <p className="text-3xl font-bold text-slate-800">{engagement.total_users}</p>
                </div>
                <div className="bg-white rounded-xl border p-6 text-center">
                  <p className="text-sm text-slate-500">30日活跃</p>
                  <p className="text-3xl font-bold text-sky-600">{engagement.active_30d} <span className="text-base text-slate-400">({engagement.active_30d_rate}%)</span></p>
                </div>
              </div>

              <div className="bg-white rounded-xl border p-6">
                <h3 className="font-bold mb-4">用户活跃度分层</h3>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-1"><span>高价值用户 (≥5笔)</span><span className="font-bold text-emerald-600">{engagement.engagement_tiers.high_value}</span></div>
                    <div className="w-full bg-slate-100 rounded-full h-3"><div className="bg-emerald-500 h-3 rounded-full" style={{ width: `${engagement.engagement_tiers.high_value / Math.max(engagement.total_users, 1) * 100}%` }} /></div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1"><span>中等用户 (2-4笔)</span><span className="font-bold text-sky-600">{engagement.engagement_tiers.medium}</span></div>
                    <div className="w-full bg-slate-100 rounded-full h-3"><div className="bg-sky-500 h-3 rounded-full" style={{ width: `${engagement.engagement_tiers.medium / Math.max(engagement.total_users, 1) * 100}%` }} /></div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1"><span>低活跃 (1笔)</span><span className="font-bold text-amber-600">{engagement.engagement_tiers.low}</span></div>
                    <div className="w-full bg-slate-100 rounded-full h-3"><div className="bg-amber-500 h-3 rounded-full" style={{ width: `${engagement.engagement_tiers.low / Math.max(engagement.total_users, 1) * 100}%` }} /></div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1"><span>沉睡用户</span><span className="font-bold text-rose-600">{engagement.engagement_tiers.dormant}</span></div>
                    <div className="w-full bg-slate-100 rounded-full h-3"><div className="bg-rose-500 h-3 rounded-full" style={{ width: `${engagement.engagement_tiers.dormant / Math.max(engagement.total_users, 1) * 100}%` }} /></div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
