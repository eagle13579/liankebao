/**
 * F1-F9 心智模型注入 — 深度复盘看板（前端）
 * ==========================================
 * 链客宝后台复盘模板与操作日志追踪。
 * 后端 API: /api/retro/*
 */
import React, { useCallback, useEffect, useState } from 'react';

const API_BASE = '/api/retro';

interface FrameworkStep {
  key: string;
  name: string;
  prompt: string;
}

interface BoardItem {
  id: number;
  title: string;
  context: string | null;
  owner_name: string | null;
  status: string;
  tags: string | null;
  progress: string;
  created_at: string;
  updated_at: string | null;
}

interface BoardDetail {
  board: {
    id: number;
    title: string;
    context: string | null;
    owner_name: string | null;
    status: string;
    tags: string | null;
    created_at: string;
    updated_at: string | null;
  };
  steps: Array<{
    step_key: string;
    step_name: string;
    prompt: string;
    content: string;
    updated_at: string | null;
  }>;
  logs: Array<{
    action: string;
    operator_name: string | null;
    detail: string | null;
    created_at: string;
  }>;
}

interface LogItem {
  id: number;
  board_id: number | null;
  action: string;
  operator_name: string | null;
  detail: string | null;
  created_at: string;
}

function getAuthHeaders() {
  const t = localStorage.getItem('token') || '';
  return { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

async function apiGet<T>(url: string): Promise<T> {
  return fetch(url, { headers: getAuthHeaders() }).then(r => r.json());
}
async function apiPost<T>(url: string, body: unknown): Promise<T> {
  return fetch(url, { method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(body) }).then(r => r.json());
}
async function apiPut<T>(url: string, body: unknown): Promise<T> {
  return fetch(url, { method: 'PUT', headers: getAuthHeaders(), body: JSON.stringify(body) }).then(r => r.json());
}

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  draft: { label: '草稿', cls: 'bg-slate-100 text-slate-600' },
  in_progress: { label: '进行中', cls: 'bg-sky-100 text-sky-700' },
  completed: { label: '已完成', cls: 'bg-emerald-100 text-emerald-700' },
};

export default function RetroBoardPage() {
  const [framework, setFramework] = useState<FrameworkStep[]>([]);
  const [boards, setBoards] = useState<BoardItem[]>([]);
  const [detail, setDetail] = useState<BoardDetail | null>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'boards' | 'framework' | 'logs'>('boards');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ title: '', context: '', tags: '' });
  const [error, setError] = useState('');

  const loadBoards = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter ? `?status=${statusFilter}` : '';
      const res = await apiGet<{ code: number; data: { items: BoardItem[] } }>(`${API_BASE}/boards${params}`);
      if (res.code === 200) setBoards(res.data.items);
    } catch {}
    setLoading(false);
  }, [statusFilter]);

  const loadFramework = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ code: number; data: { steps: FrameworkStep[] } }>(`${API_BASE}/framework`);
      if (res.code === 200) setFramework(res.data.steps);
    } catch {}
    setLoading(false);
  }, []);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ code: number; data: LogItem[] }>(`${API_BASE}/logs?limit=50`);
      if (res.code === 200) setLogs(res.data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    if (tab === 'boards') loadBoards();
    else if (tab === 'framework') loadFramework();
    else if (tab === 'logs') loadLogs();
  }, [tab, loadBoards, loadFramework, loadLogs]);

  const loadDetail = async (id: number) => {
    const res = await apiGet<{ code: number; data: BoardDetail }>(`${API_BASE}/boards/${id}`);
    if (res.code === 200) setDetail(res.data);
  };

  const handleCreate = async () => {
    if (!createForm.title) { setError('请输入复盘标题'); return; }
    setError('');
    const res = await apiPost<{ code: number }>(`${API_BASE}/boards`, createForm);
    if (res.code === 200) {
      setShowCreate(false);
      setCreateForm({ title: '', context: '', tags: '' });
      loadBoards();
    } else setError('创建失败');
  };

  const handleStepUpdate = async (boardId: number, stepKey: string, content: string) => {
    const res = await apiPut<{ code: number }>(`${API_BASE}/boards/${boardId}/steps/${stepKey}`, { content });
    if (res.code === 200) loadDetail(boardId);
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">🔄 F1-F9 深度复盘</h1>
        <p className="text-sm text-slate-500 mt-1">从目标回顾到行动跟踪 — 完整的复盘闭环</p>
      </div>

      {error && <div className="bg-rose-50 border border-rose-200 text-rose-700 p-3 rounded-lg mb-4 text-sm">{error}</div>}

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(['boards', 'framework', 'logs'] as const).map(t => (
          <button key={t} onClick={() => { setTab(t); setDetail(null); }}
            className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${tab === t ? 'bg-slate-800 text-white' : 'bg-white border text-slate-600 hover:bg-slate-50'}`}>
            {t === 'boards' ? '复盘看板' : t === 'framework' ? 'F1-F9框架' : '操作日志'}
          </button>
        ))}
      </div>

      {/* Tab: Framework */}
      {tab === 'framework' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : (
            <div className="space-y-4">
              {framework.map((step, i) => (
                <div key={step.key} className="bg-white rounded-xl border p-5">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="bg-sky-100 text-sky-700 px-2 py-0.5 rounded text-xs font-bold">{step.key}</span>
                    <h3 className="font-bold text-slate-800">{step.name}</h3>
                    <span className="text-[10px] text-slate-400">第{i + 1}/9步</span>
                  </div>
                  <p className="text-sm text-slate-500 ml-1">{step.prompt}</p>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab: Boards */}
      {tab === 'boards' && (
        <>
          {!detail ? (
            <>
              <div className="flex justify-between items-center mb-4">
                <div className="flex gap-2">
                  {['', 'draft', 'in_progress', 'completed'].map(s => (
                    <button key={s} onClick={() => setStatusFilter(s)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${statusFilter === s ? 'bg-slate-800 text-white' : 'bg-white border text-slate-600 hover:bg-slate-50'}`}>
                      {s ? STATUS_MAP[s]?.label || s : '全部'}
                    </button>
                  ))}
                </div>
                <button onClick={() => setShowCreate(!showCreate)}
                  className="bg-sky-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-sky-700">
                  {showCreate ? '取消' : '+ 新建复盘'}
                </button>
              </div>

              {showCreate && (
                <div className="bg-white rounded-xl border p-5 mb-6 space-y-3">
                  <h3 className="font-bold">新建复盘</h3>
                  <input placeholder="复盘标题 *" value={createForm.title} onChange={e => setCreateForm(p => ({ ...p, title: e.target.value }))}
                    className="w-full border rounded-lg px-3 py-2 text-sm" />
                  <textarea placeholder="复盘背景" value={createForm.context} onChange={e => setCreateForm(p => ({ ...p, context: e.target.value }))}
                    className="w-full border rounded-lg px-3 py-2 text-sm" rows={3} />
                  <input placeholder="标签（逗号分隔）" value={createForm.tags} onChange={e => setCreateForm(p => ({ ...p, tags: e.target.value }))}
                    className="w-full border rounded-lg px-3 py-2 text-sm" />
                  <button onClick={handleCreate} className="bg-sky-600 text-white px-6 py-2 rounded-lg text-sm font-bold">创建复盘（将自动初始化F1-F9步骤）</button>
                </div>
              )}

              {loading ? (
                <div className="text-center py-12 text-slate-400">加载中...</div>
              ) : boards.length === 0 ? (
                <div className="text-center py-12 text-slate-400">暂无复盘记录</div>
              ) : (
                <div className="space-y-4">
                  {boards.map(b => (
                    <div key={b.id} onClick={() => loadDetail(b.id)}
                      className="bg-white rounded-xl border p-5 hover:shadow-md transition-shadow cursor-pointer">
                      <div className="flex justify-between items-start">
                        <div>
                          <h3 className="font-bold text-slate-800">{b.title}</h3>
                          <div className="flex gap-2 mt-1">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${STATUS_MAP[b.status]?.cls || 'bg-slate-100'}`}>
                              {STATUS_MAP[b.status]?.label || b.status}
                            </span>
                            <span className="text-[10px] text-slate-400">{b.progress} 步骤完成</span>
                            {b.tags && <span className="text-[10px] text-slate-400">🏷️ {b.tags}</span>}
                          </div>
                        </div>
                        <span className="text-xs text-slate-400">{new Date(b.created_at).toLocaleDateString('zh-CN')}</span>
                      </div>
                      {b.context && <p className="text-sm text-slate-500 mt-2">{b.context}</p>}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            /* Detail View */
            <div>
              <button onClick={() => setDetail(null)} className="text-sm text-sky-600 hover:underline mb-4">← 返回列表</button>
              <div className="bg-white rounded-xl border p-6 mb-6">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h2 className="text-xl font-bold">{detail.board.title}</h2>
                    <div className="flex gap-2 mt-1">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${STATUS_MAP[detail.board.status]?.cls}`}>
                        {STATUS_MAP[detail.board.status]?.label}
                      </span>
                      <span className="text-xs text-slate-400">负责人: {detail.board.owner_name || '-'}</span>
                    </div>
                  </div>
                </div>
                {detail.board.context && <p className="text-sm text-slate-600 mb-4">{detail.board.context}</p>}
              </div>

              {/* Steps */}
              <div className="space-y-4 mb-6">
                <h3 className="font-bold text-slate-700">F1-F9 复盘步骤</h3>
                {detail.steps.map(step => (
                  <StepEditor
                    key={step.step_key}
                    step={step}
                    boardId={detail.board.id}
                    onSave={handleStepUpdate}
                  />
                ))}
              </div>

              {/* Logs */}
              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-bold text-slate-700 mb-3">📋 操作日志</h3>
                <div className="space-y-2">
                  {detail.logs.map((log, i) => (
                    <div key={i} className="flex items-start gap-3 text-sm p-2 hover:bg-slate-50 rounded">
                      <span className="text-[10px] text-slate-400 whitespace-nowrap">{new Date(log.created_at).toLocaleString('zh-CN')}</span>
                      <span className="text-xs font-bold text-slate-600">{log.operator_name || '-'}</span>
                      <span className="text-xs text-slate-500">{log.detail || log.action}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* Tab: Logs */}
      {tab === 'logs' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : (
            <div className="bg-white rounded-xl border overflow-hidden">
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase tracking-widest font-bold">
                  <tr><th className="px-4 py-3">时间</th><th className="px-4 py-3">操作人</th><th className="px-4 py-3">操作</th><th className="px-4 py-3">详情</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {logs.map(l => (
                    <tr key={l.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-xs text-slate-400">{new Date(l.created_at).toLocaleString('zh-CN')}</td>
                      <td className="px-4 py-3">{l.operator_name || '-'}</td>
                      <td className="px-4 py-3"><span className="px-2 py-0.5 bg-slate-100 rounded text-xs font-bold">{l.action}</span></td>
                      <td className="px-4 py-3 text-slate-500">{l.detail || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StepEditor({ step, boardId, onSave }: {
  step: { step_key: string; step_name: string; prompt: string; content: string };
  boardId: number;
  onSave: (boardId: number, stepKey: string, content: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(step.content);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(boardId, step.step_key, content);
    setSaving(false);
    setEditing(false);
  };

  return (
    <div className="bg-white rounded-xl border p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="bg-sky-100 text-sky-700 px-2 py-0.5 rounded text-xs font-bold">{step.step_key}</span>
          <span className="font-bold text-sm text-slate-700">{step.step_name}</span>
        </div>
        <button onClick={() => setEditing(!editing)} className="text-xs text-sky-600 hover:underline">
          {editing ? '取消' : (step.content ? '编辑' : '填写')}
        </button>
      </div>
      <p className="text-xs text-slate-400 mb-2 italic">"{step.prompt}"</p>
      {editing ? (
        <div className="space-y-2">
          <textarea value={content} onChange={e => setContent(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 text-sm" rows={3} placeholder="输入复盘内容..." />
          <button onClick={handleSave} disabled={saving}
            className="bg-sky-600 text-white px-4 py-1.5 rounded-lg text-xs font-bold disabled:opacity-50">
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      ) : (
        <p className="text-sm text-slate-600 whitespace-pre-wrap">{step.content || <span className="text-slate-300 italic">未填写</span>}</p>
      )}
    </div>
  );
}
