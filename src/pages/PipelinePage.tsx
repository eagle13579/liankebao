/**
 * 客户管道页面
 * ============
 * 管道阶段可视化 + 线索列表 + 新建线索弹窗
 * 调用 GET /api/v1/crm/pipeline 和 GET /api/v1/crm/leads
 * 新建线索: POST /api/v1/crm/leads
 */

import React, { useEffect, useState } from 'react';

// ============================================================
// 类型定义
// ============================================================
interface PipelineStage {
  stage: string;
  label: string;
  count: number;
  value: number;
}

interface PipelineData {
  stages: PipelineStage[];
  total_count: number;
  total_value: number;
}

interface LeadItem {
  id: number;
  name: string;
  company?: string;
  phone?: string;
  source?: string;
  stage: string;
  stage_label?: string;
  assigned_to?: number;
  assigned_name?: string;
  next_action?: string;
  value?: number;
  notes?: string;
  created_at: string;
  updated_at: string;
}

interface LeadsResponse {
  total: number;
  page: number;
  page_size: number;
  items: LeadItem[];
}

interface ApiResponse<T> {
  code: number;
  message: string;
  data?: T;
}

const PIPELINE_STAGE_ORDER = [
  'new_lead',
  'contacted',
  'negotiating',
  'quotation',
  'closed_won',
  'closed_lost',
];

const STAGE_ICONS: Record<string, string> = {
  new_lead: '🆕',
  contacted: '📞',
  negotiating: '🤝',
  quotation: '📄',
  closed_won: '✅',
  closed_lost: '❌',
};

const STAGE_COLORS: Record<string, string> = {
  new_lead: 'bg-sky-100 text-sky-700 border-sky-200',
  contacted: 'bg-blue-100 text-blue-700 border-blue-200',
  negotiating: 'bg-amber-100 text-amber-700 border-amber-200',
  quotation: 'bg-purple-100 text-purple-700 border-purple-200',
  closed_won: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  closed_lost: 'bg-rose-100 text-rose-700 border-rose-200',
};

// ============================================================
// 工具函数
// ============================================================
const API_BASE = '';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const res = await fetch(API_BASE + url, { ...options, headers: { ...headers, ...options?.headers } });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return await res.json();
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return dateStr;
  }
}

function fmtMoney(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return n.toLocaleString('zh-CN');
}

// ============================================================
// 主组件
// ============================================================
export default function PipelinePage() {
  const [pipeline, setPipeline] = useState<PipelineData | null>(null);
  const [leads, setLeads] = useState<LeadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [pipeRes, leadsRes] = await Promise.all([
        fetchJson<ApiResponse<PipelineData>>('/api/v1/crm/pipeline'),
        fetchJson<ApiResponse<LeadsResponse>>('/api/v1/crm/leads?page_size=50'),
      ]);

      if (pipeRes.code === 200 && pipeRes.data) setPipeline(pipeRes.data);
      if (leadsRes.code === 200 && leadsRes.data) setLeads(leadsRes.data.items);
    } catch (err: any) {
      setError(err.message || '加载数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // 按管道阶段排序线索
  const getLeadsByStage = (stage: string): LeadItem[] =>
    leads.filter(l => l.stage === stage);

  return (
    <div className="min-h-screen bg-neutral-bg">
      {/* 页面标题 */}
      <div className="bg-surface border-b border-border-light">
        <div className="max-w-5xl mx-auto px-4 pt-6 pb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-on-surface font-manrope">客户管道</h1>
            <p className="text-sm text-text-muted mt-1">跟进你的每一个客户，推进商机转化</p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-container transition-colors shadow-sm"
          >
            <span className="text-base leading-none">＋</span>
            新建线索
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* 加载态 */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
            <span className="ml-3 text-sm text-text-muted">加载中...</span>
          </div>
        )}

        {/* 错误态 */}
        {!loading && error && (
          <div className="flex flex-col items-center justify-center py-20">
            <p className="text-sm text-error mb-3">{error}</p>
            <button onClick={fetchData} className="px-4 py-2 bg-primary text-white text-sm rounded-lg hover:bg-primary-container transition-colors">
              重新加载
            </button>
          </div>
        )}

        {!loading && !error && (
          <>
            {/* KPI 概览 */}
            {pipeline && (
              <div className="grid grid-cols-4 gap-4 mb-6">
                <div className="bg-surface rounded-xl border border-border-light p-4">
                  <p className="text-xs text-text-muted mb-1">总线索数</p>
                  <p className="text-2xl font-bold text-on-surface">{pipeline.total_count}</p>
                </div>
                <div className="bg-surface rounded-xl border border-border-light p-4">
                  <p className="text-xs text-text-muted mb-1">预计总金额</p>
                  <p className="text-2xl font-bold text-on-surface">¥{fmtMoney(pipeline.total_value)}</p>
                </div>
                <div className="bg-surface rounded-xl border border-border-light p-4">
                  <p className="text-xs text-text-muted mb-1">进行中</p>
                  <p className="text-2xl font-bold text-on-surface">
                    {pipeline.stages
                      .filter(s => !['closed_won', 'closed_lost'].includes(s.stage))
                      .reduce((acc, s) => acc + s.count, 0)}
                  </p>
                </div>
                <div className="bg-surface rounded-xl border border-border-light p-4">
                  <p className="text-xs text-text-muted mb-1">已成交</p>
                  <p className="text-2xl font-bold text-emerald-600">
                    {pipeline.stages.find(s => s.stage === 'closed_won')?.count || 0}
                  </p>
                </div>
              </div>
            )}

            {/* 管道阶段可视化 */}
            {pipeline && (
              <div className="bg-surface rounded-xl border border-border-light p-6 mb-6">
                <h2 className="text-sm font-semibold text-on-surface mb-4">管道阶段分布</h2>
                <div className="flex items-center gap-1">
                  {PIPELINE_STAGE_ORDER.map((stageKey, idx) => {
                    const stageInfo = pipeline.stages.find(s => s.stage === stageKey);
                    const count = stageInfo?.count || 0;
                    const maxCount = Math.max(...pipeline.stages.map(s => s.count), 1);
                    const barHeight = Math.max((count / maxCount) * 100, count > 0 ? 20 : 8);
                    const isLast = idx === PIPELINE_STAGE_ORDER.length - 1;

                    return (
                      <div key={stageKey} className={`flex-1 flex flex-col items-center ${isLast ? '' : ''}`}>
                        <div className="flex items-end justify-center h-28 w-full mb-2">
                          <div
                            className={`w-full max-w-[80px] rounded-t-lg transition-all duration-500 ${
                              stageKey === 'closed_won'
                                ? 'bg-emerald-400'
                                : stageKey === 'closed_lost'
                                  ? 'bg-rose-300'
                                  : 'bg-sky-400'
                            }`}
                            style={{ height: `${barHeight}px` }}
                          >
                            {count > 0 && (
                              <div className="text-center text-white text-xs font-bold pt-1">{count}</div>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col items-center gap-1">
                          <span className="text-lg">{STAGE_ICONS[stageKey] || '📌'}</span>
                          <span className="text-[10px] text-text-muted text-center leading-tight whitespace-nowrap">
                            {stageInfo?.label || stageKey}
                          </span>
                          {stageInfo && stageInfo.value > 0 && (
                            <span className="text-[9px] text-text-muted">¥{fmtMoney(stageInfo.value)}</span>
                          )}
                        </div>
                        {/* 箭头连接 */}
                        {!isLast && (
                          <div className="hidden sm:block absolute translate-x-1/2 ml-0.5 text-text-muted text-xs">→</div>
                        )}
                      </div>
                    );
                  })}
                </div>
                {/* 内联箭头 */}
                <div className="flex justify-between mt-4 px-2 text-text-muted text-xs">
                  <span>新线索</span>
                  <span>→</span>
                  <span>已联系</span>
                  <span>→</span>
                  <span>洽谈中</span>
                  <span>→</span>
                  <span>报价中</span>
                  <span>→</span>
                  <span>已成交</span>
                  <span>→</span>
                  <span>已流失</span>
                </div>
              </div>
            )}

            {/* 线索列表 */}
            <div className="bg-surface rounded-xl border border-border-light p-6">
              <h2 className="text-sm font-semibold text-on-surface mb-4">全部线索</h2>
              {leads.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <span className="text-3xl mb-2">📋</span>
                  <p className="text-sm text-text-muted">暂无线索，点击上方按钮创建</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {leads.map(lead => (
                    <LeadCard key={lead.id} lead={lead} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* 新建线索弹窗 */}
      {showCreateModal && (
        <CreateLeadModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false);
            fetchData();
          }}
        />
      )}
    </div>
  );
}

// ============================================================
// 线索卡片
// ============================================================
function LeadCard({ lead }: { lead: LeadItem }) {
  const colorClass = STAGE_COLORS[lead.stage] || 'bg-slate-100 text-slate-700 border-slate-200';

  return (
    <div className="flex items-center justify-between p-4 bg-neutral-bg rounded-lg border border-border-light hover:border-primary/30 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h4 className="text-sm font-semibold text-on-surface">{lead.name}</h4>
          <span className={`text-[10px] px-2 py-0.5 rounded-full border ${colorClass}`}>
            {STAGE_ICONS[lead.stage] || ''} {lead.stage_label || lead.stage}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-muted">
          {lead.company && <span>🏢 {lead.company}</span>}
          {lead.phone && <span>📞 {lead.phone}</span>}
          {lead.source && <span>📌 {lead.source}</span>}
        </div>
        {lead.next_action && (
          <p className="text-xs text-primary mt-1">📋 下一步: {lead.next_action}</p>
        )}
      </div>
      <div className="flex items-center gap-3 ml-4 shrink-0">
        {lead.value && lead.value > 0 && (
          <span className="text-sm font-semibold text-on-surface">¥{fmtMoney(lead.value)}</span>
        )}
        <span className="text-[10px] text-text-muted">{formatDate(lead.updated_at || lead.created_at)}</span>
      </div>
    </div>
  );
}

// ============================================================
// 新建线索弹窗
// ============================================================
function CreateLeadModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [phone, setPhone] = useState('');
  const [source, setSource] = useState('manual');
  const [nextAction, setNextAction] = useState('');
  const [value, setValue] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setSubmitError('请输入客户姓名');
      return;
    }
    setSubmitting(true);
    setSubmitError(null);

    try {
      const params = new URLSearchParams({
        name: name.trim(),
        company: company.trim(),
        phone: phone.trim(),
        source: source.trim(),
        next_action: nextAction.trim(),
        value: value || '0',
        notes: notes.trim(),
      });

      const json = await fetchJson<ApiResponse<any>>(`/api/v1/crm/leads?${params.toString()}`, {
        method: 'POST',
      });

      if (json.code === 201) {
        onCreated();
      } else {
        throw new Error(json.message || '创建失败');
      }
    } catch (err: any) {
      setSubmitError(err.message || '网络错误');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-surface rounded-2xl shadow-xl border border-border-light w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-border-light">
          <h3 className="text-base font-semibold text-on-surface">新建线索</h3>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-neutral-bg text-text-muted hover:text-on-surface transition-colors"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-on-surface mb-1.5">
              姓名 <span className="text-error">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="客户姓名"
              className="w-full px-3 py-2 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-on-surface mb-1.5">公司</label>
            <input
              type="text"
              value={company}
              onChange={e => setCompany(e.target.value)}
              placeholder="公司名称"
              className="w-full px-3 py-2 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-on-surface mb-1.5">手机号</label>
            <input
              type="text"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              placeholder="手机号"
              className="w-full px-3 py-2 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-on-surface mb-1.5">来源</label>
            <select
              value={source}
              onChange={e => setSource(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white"
            >
              <option value="manual">手动录入</option>
              <option value="phone">电话咨询</option>
              <option value="wechat">微信</option>
              <option value="referral">客户推荐</option>
              <option value="exhibition">展会</option>
              <option value="online">线上推广</option>
              <option value="other">其他</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-on-surface mb-1.5">下一步行动</label>
            <input
              type="text"
              value={nextAction}
              onChange={e => setNextAction(e.target.value)}
              placeholder="例: 周五电话回访"
              className="w-full px-3 py-2 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-on-surface mb-1.5">预计金额 (元)</label>
            <input
              type="number"
              value={value}
              onChange={e => setValue(e.target.value)}
              placeholder="0"
              min="0"
              className="w-full px-3 py-2 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-on-surface mb-1.5">备注</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="客户需求、意向等备注信息"
              rows={3}
              className="w-full px-3 py-2 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white resize-none"
            />
          </div>

          {submitError && (
            <p className="text-xs text-error">{submitError}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 text-sm font-medium text-on-surface bg-neutral-bg rounded-lg hover:bg-slate-200 transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? '提交中...' : '创建线索'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
