/**
 * M2 心智模型注入 — 假设验证门禁（前端）
 * ==========================================
 * 链客宝需求评审门禁前端页面：管理「核心假设验证」流程。
 * 后端 API: /api/hypothesis-gate/*
 */
import React, { useCallback, useEffect, useState } from 'react';

const API_BASE = '/api/hypothesis-gate';

interface HypothesisItem {
  id: number;
  feature_name: string;
  hypothesis: string;
  falsification_criteria: string;
  validation_method: string;
  status: string;
  evidence: string | null;
  conclusion: string | null;
  product_id: number | null;
  created_at: string;
  updated_at: string;
}

interface StatsData {
  total: number;
  pending: number;
  in_progress: number;
  validated: number;
  falsified: number;
  validation_rate: number;
}

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('token') || '';
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: getAuthHeaders() });
  return res.json();
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body) });
  return res.json();
}

async function apiPut<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: 'PUT', headers: getAuthHeaders(), body: JSON.stringify(body) });
  return res.json();
}

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  pending: { label: '待验证', cls: 'bg-amber-100 text-amber-700' },
  in_progress: { label: '验证中', cls: 'bg-sky-100 text-sky-700' },
  validated: { label: '已验证 ✓', cls: 'bg-emerald-100 text-emerald-700' },
  falsified: { label: '已证伪 ✗', cls: 'bg-rose-100 text-rose-700' },
};

const METHOD_LABELS: Record<string, string> = {
  user_interview: '用户访谈',
  survey: '问卷调查',
  ab_test: 'A/B测试',
  data_analysis: '数据分析',
  prototype_test: '原型测试',
};

export default function HypothesisGatePage() {
  const [items, setItems] = useState<HypothesisItem[]>([]);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ feature_name: '', hypothesis: '', falsification_criteria: '', validation_method: 'user_interview', product_id: '' });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editStatus, setEditStatus] = useState('');
  const [editEvidence, setEditEvidence] = useState('');
  const [editConclusion, setEditConclusion] = useState('');
  const [error, setError] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter ? `?status=${filter}` : '';
      const [listRes, statsRes] = await Promise.all([
        apiGet<{ code: number; data: { items: HypothesisItem[] } }>(`${API_BASE}/checks${params}`),
        apiGet<{ code: number; data: StatsData }>(`${API_BASE}/checks/stats`),
      ]);
      if (listRes.code === 200) setItems(listRes.data.items);
      if (statsRes.code === 200) setStats(statsRes.data);
    } catch { setError('加载失败'); }
    setLoading(false);
  }, [filter]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    if (!form.feature_name || !form.hypothesis || !form.falsification_criteria) {
      setError('请填写必填字段');
      return;
    }
    setError('');
    const res = await apiPost<{ code: number }>(`${API_BASE}/checks`, {
      ...form,
      product_id: form.product_id ? parseInt(form.product_id) : null,
    });
    if (res.code === 200) {
      setShowForm(false);
      setForm({ feature_name: '', hypothesis: '', falsification_criteria: '', validation_method: 'user_interview', product_id: '' });
      loadData();
    } else {
      setError('创建失败');
    }
  };

  const handleUpdate = async (id: number) => {
    const res = await apiPut<{ code: number }>(`${API_BASE}/checks/${id}`, {
      status: editStatus,
      evidence: editEvidence || null,
      conclusion: editConclusion || null,
    });
    if (res.code === 200) {
      setEditingId(null);
      loadData();
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">🧪 M2 假设验证门禁</h1>
          <p className="text-sm text-slate-500 mt-1">创业=验证假设 — 每个需求都必须先验证核心假设</p>
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="bg-sky-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-sky-700 active:scale-95 transition-all">
          {showForm ? '取消' : '+ 新建验证'}
        </button>
      </div>

      {error && <div className="bg-rose-50 border border-rose-200 text-rose-700 p-3 rounded-lg mb-4 text-sm">{error}</div>}

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-5 gap-4 mb-6">
          <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-slate-800">{stats.total}</p><p className="text-xs text-slate-400">总数</p></div>
          <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-amber-600">{stats.pending}</p><p className="text-xs text-slate-400">待验证</p></div>
          <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-sky-600">{stats.in_progress}</p><p className="text-xs text-slate-400">验证中</p></div>
          <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-emerald-600">{stats.validated}</p><p className="text-xs text-slate-400">已验证</p></div>
          <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-rose-600">{stats.falsified}</p><p className="text-xs text-slate-400">已证伪</p></div>
        </div>
      )}

      {/* Create Form */}
      {showForm && (
        <div className="bg-white rounded-xl border p-6 mb-6 space-y-4">
          <h3 className="font-bold">新建假设验证</h3>
          <input placeholder="需求/功能名称 *" value={form.feature_name} onChange={e => setForm(p => ({ ...p, feature_name: e.target.value }))}
            className="w-full border rounded-lg px-3 py-2 text-sm" />
          <textarea placeholder="核心假设（你相信什么？） *" value={form.hypothesis} onChange={e => setForm(p => ({ ...p, hypothesis: e.target.value }))}
            className="w-full border rounded-lg px-3 py-2 text-sm" rows={3} />
          <textarea placeholder="证伪标准（什么情况下假设不成立？） *" value={form.falsification_criteria} onChange={e => setForm(p => ({ ...p, falsification_criteria: e.target.value }))}
            className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} />
          <div className="flex gap-4">
            <select value={form.validation_method} onChange={e => setForm(p => ({ ...p, validation_method: e.target.value }))}
              className="border rounded-lg px-3 py-2 text-sm">
              {Object.entries(METHOD_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input placeholder="关联产品ID（可选）" value={form.product_id} onChange={e => setForm(p => ({ ...p, product_id: e.target.value }))}
              className="border rounded-lg px-3 py-2 text-sm w-40" />
          </div>
          <button onClick={handleCreate} className="bg-sky-600 text-white px-6 py-2 rounded-lg text-sm font-bold hover:bg-sky-700">
            提交验证
          </button>
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-2 mb-4">
        {['', 'pending', 'in_progress', 'validated', 'falsified'].map(s => (
          <button key={s} onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${filter === s ? 'bg-slate-800 text-white' : 'bg-white border text-slate-600 hover:bg-slate-50'}`}>
            {s ? STATUS_MAP[s]?.label || s : '全部'}
          </button>
        ))}
      </div>

      {/* List */}
      {loading ? (
        <div className="text-center py-12 text-slate-400">加载中...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-slate-400">暂无假设验证记录</div>
      ) : (
        <div className="space-y-4">
          {items.map(item => (
            <div key={item.id} className="bg-white rounded-xl border p-5 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="font-bold text-slate-800">{item.feature_name}</h3>
                  <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold mt-1 ${STATUS_MAP[item.status]?.cls || 'bg-slate-100'}`}>
                    {STATUS_MAP[item.status]?.label || item.status}
                  </span>
                  <span className="ml-2 text-[10px] text-slate-400">{METHOD_LABELS[item.validation_method] || item.validation_method}</span>
                </div>
                <button onClick={() => {
                  setEditingId(item.id);
                  setEditStatus(item.status);
                  setEditEvidence(item.evidence || '');
                  setEditConclusion(item.conclusion || '');
                }} className="text-xs text-sky-600 hover:underline">更新结果</button>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div><span className="text-slate-400 text-xs">假设：</span><p className="text-slate-700">{item.hypothesis}</p></div>
                <div><span className="text-slate-400 text-xs">证伪标准：</span><p className="text-slate-700">{item.falsification_criteria}</p></div>
              </div>
              {item.evidence && <div className="mt-2 text-sm"><span className="text-slate-400 text-xs">证据：</span><p className="text-slate-600">{item.evidence}</p></div>}
              {item.conclusion && <div className="mt-1 text-sm"><span className="text-slate-400 text-xs">结论：</span><p className="text-slate-600 font-medium">{item.conclusion}</p></div>}

              {/* Edit Form */}
              {editingId === item.id && (
                <div className="mt-4 border-t pt-4 space-y-3">
                  <select value={editStatus} onChange={e => setEditStatus(e.target.value)}
                    className="border rounded-lg px-3 py-1.5 text-sm">
                    <option value="pending">待验证</option>
                    <option value="in_progress">验证中</option>
                    <option value="validated">验证通过</option>
                    <option value="falsified">证伪</option>
                  </select>
                  <textarea placeholder="验证证据" value={editEvidence} onChange={e => setEditEvidence(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} />
                  <textarea placeholder="结论与下一步" value={editConclusion} onChange={e => setEditConclusion(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} />
                  <div className="flex gap-2">
                    <button onClick={() => handleUpdate(item.id)} className="bg-sky-600 text-white px-4 py-1.5 rounded-lg text-xs font-bold">保存</button>
                    <button onClick={() => setEditingId(null)} className="bg-slate-100 text-slate-600 px-4 py-1.5 rounded-lg text-xs font-bold">取消</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
