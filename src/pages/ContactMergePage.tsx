import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, AlertTriangle, CheckCircle2, XCircle, ArrowRight, User, Phone, Building2, Mail, MessageCircle } from 'lucide-react';
import { api } from '../api/client';
import { Contact, DuplicateGroup } from '../types';
import { Loading, ErrorBlock } from '../components/StatusComponents';

interface MergeGroup {
  id: number;
  contacts: Contact[];
  score: number;
}

const FIELD_LABELS: Record<string, string> = {
  name: '姓名',
  phone: '电话',
  wechat_id: '微信',
  company: '公司',
  position: '职位',
  email: '邮箱',
  tags: '标签',
  notes: '备注',
  source: '来源',
};

const COMPARABLE_FIELDS = ['name', 'phone', 'wechat_id', 'company', 'position', 'email', 'tags', 'notes', 'source'];

export default function ContactMergePage() {
  const navigate = useNavigate();
  const [mergeGroups, setMergeGroups] = useState<MergeGroup[]>([]);
  const [selectedFields, setSelectedFields] = useState<Record<string, Record<string, string>>>({});
  const [status, setStatus] = useState<'loading' | 'error' | 'success'>('loading');
  const [error, setError] = useState('');
  const [merging, setMerging] = useState(false);
  const [result, setResult] = useState<{ merged: number; skipped: number } | null>(null);
  const [skipAll, setSkipAll] = useState<Record<number, boolean>>({});

  useEffect(() => {
    setStatus('loading');
    api.get<{ groups: { id: number; contacts: Contact[]; score: number }[] }>('/api/contacts/duplicates')
      .then(res => {
        if (res.data?.groups) {
          setMergeGroups(res.data.groups);
          const fieldSelections: Record<string, Record<string, string>> = {};
          const skip: Record<number, boolean> = {};
          res.data.groups.forEach((g, idx) => {
            fieldSelections[g.id] = {};
            COMPARABLE_FIELDS.forEach(f => {
              // Pick first non-empty value
              fieldSelections[g.id][f] = g.contacts.find(c => (c as any)[f])?.id.toString() || '';
            });
            skip[g.id] = false;
          });
          setSelectedFields(fieldSelections);
          setSkipAll(skip);
        }
        setStatus('success');
      })
      .catch((e: any) => {
        setError(e.message || '加载失败');
        setStatus('error');
      });
  }, []);

  const handleFieldSelect = (groupId: number, field: string, contactId: string) => {
    setSelectedFields(prev => ({
      ...prev,
      [groupId]: { ...prev[groupId], [field]: contactId },
    }));
  };

  const handleSkipGroup = (groupId: number) => {
    setSkipAll(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  const handleMergeAll = async () => {
    setMerging(true);
    let merged = 0;
    let skipped = 0;

    for (const group of mergeGroups) {
      if (skipAll[group.id]) {
        skipped++;
        continue;
      }
      const keepId = parseInt(selectedFields[group.id]?.name || group.contacts[0].id.toString());
      try {
        await api.post(`/api/contacts/merge`, {
          group_id: group.id,
          keep_id: keepId,
          field_selection: selectedFields[group.id],
        });
        merged++;
      } catch {
        skipped++;
      }
    }

    setResult({ merged, skipped });
    setMerging(false);
  };

  const handleSkipAllGroups = () => {
    setSkipAll(prev => {
      const next = { ...prev };
      Object.keys(next).forEach(k => { next[Number(k)] = true; });
      return next;
    });
  };

  if (status === 'loading') {
    return (
      <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
        <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center px-4 h-16">
          <button onClick={() => navigate(-1)} className="text-slate-600"><ChevronLeft className="w-6 h-6" /></button>
          <h1 className="font-manrope text-lg font-bold text-primary-container ml-3">去重合并</h1>
        </header>
        <main className="pt-16"><Loading /></main>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
        <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center px-4 h-16">
          <button onClick={() => navigate(-1)} className="text-slate-600"><ChevronLeft className="w-6 h-6" /></button>
          <h1 className="font-manrope text-lg font-bold text-primary-container ml-3">去重合并</h1>
        </header>
        <main className="pt-16"><ErrorBlock message={error} /></main>
      </div>
    );
  }

  if (result) {
    return (
      <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
        <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center px-4 h-16">
          <button onClick={() => navigate(-1)} className="text-slate-600"><ChevronLeft className="w-6 h-6" /></button>
        </header>
        <main className="pt-16 p-4">
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center mb-4">
              <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            </div>
            <h2 className="text-lg font-bold text-on-surface mb-2">合并完成</h2>
            <div className="bg-white rounded-2xl border border-border-light p-4 w-full max-w-xs space-y-2 mb-6">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">已合并</span>
                <span className="font-bold text-emerald-600">{result.merged} 组</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">已跳过</span>
                <span className="font-bold text-slate-400">{result.skipped} 组</span>
              </div>
            </div>
            <button
              onClick={() => navigate('/contacts', { state: { transition: 'push_back' } })}
              className="w-full max-w-xs py-3 bg-primary-container text-white rounded-xl font-bold text-sm active:scale-95 transition-transform shadow-lg"
            >
              返回人脉列表
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-24">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="text-slate-600">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <h1 className="font-manrope text-lg font-bold text-primary-container">去重合并</h1>
        </div>
        <button
          onClick={handleSkipAllGroups}
          className="text-xs text-slate-400 font-bold active:opacity-70"
        >
          全部跳过
        </button>
      </header>

      <main className="pt-16 p-4 space-y-4">
        {mergeGroups.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16">
            <CheckCircle2 className="w-12 h-12 text-emerald-400 mb-3" />
            <p className="text-sm text-text-muted">暂无重复联系人</p>
          </div>
        ) : (
          <>
            <div className="bg-sky-50 rounded-2xl border border-sky-100 p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-bold text-slate-700">检测到 {mergeGroups.length} 组重复联系人</p>
                  <p className="text-[10px] text-text-muted mt-0.5">请为每组选择要保留的联系人和字段值</p>
                </div>
              </div>
            </div>

            {mergeGroups.map((group) => {
              if (skipAll[group.id]) {
                return (
                  <div key={group.id} className="bg-white rounded-2xl border border-border-light p-4 opacity-50">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-slate-400">#{group.id} - 已跳过</span>
                      <button onClick={() => handleSkipGroup(group.id)} className="text-xs text-primary-container font-bold">撤销跳过</button>
                    </div>
                  </div>
                );
              }

              return (
                <div key={group.id} className="bg-white rounded-2xl border border-border-light overflow-hidden">
                  {/* Group Header */}
                  <div className="p-4 border-b border-border-light flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-5 h-5 text-amber-500" />
                      <span className="text-sm font-bold">重复组 #{group.id}</span>
                      <span className="text-[10px] bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full">
                        {(group.score * 100).toFixed(0)}% 相似
                      </span>
                    </div>
                    <button
                      onClick={() => handleSkipGroup(group.id)}
                      className="text-xs text-slate-400 underline active:opacity-70"
                    >
                      跳过此组
                    </button>
                  </div>

                  {/* Contact Comparison */}
                  <div className="divide-y divide-border-light">
                    {group.contacts.map((c, ci) => (
                      <div key={c.id} className="p-4">
                        <div className="flex items-center gap-3 mb-3">
                          <div className="w-10 h-10 rounded-full bg-sky-50 flex items-center justify-center text-sm font-bold text-primary-container shrink-0">
                            {c.name[0]}
                          </div>
                          <div>
                            <p className="text-sm font-bold">{c.name}</p>
                            <p className="text-[10px] text-text-muted">ID: {c.id}</p>
                          </div>
                          {ci === 0 && (
                            <span className="text-[10px] bg-primary-container text-white px-2 py-0.5 rounded-full font-bold">主记录</span>
                          )}
                        </div>

                        <div className="space-y-1.5">
                          {COMPARABLE_FIELDS.map(f => {
                            const val = (c as any)[f];
                            if (!val && f !== 'tags') return null;
                            if (f === 'tags' && (!val || val.length === 0)) return null;
                            const displayVal = f === 'tags' ? (val as string[]).join(', ') : val;
                            return (
                              <div key={f} className="flex items-center gap-2">
                                <span className="text-[10px] text-text-muted w-10 shrink-0">{FIELD_LABELS[f]}</span>
                                <span className="text-xs font-medium">{displayVal}</span>
                              </div>
                            );
                          })}
                        </div>

                        {/* Field selector */}
                        {ci > 0 && (
                          <div className="mt-3 pt-3 border-t border-dashed border-border-light">
                            <p className="text-[10px] font-bold text-slate-400 mb-2">选择性保留此记录的字段：</p>
                            <div className="flex flex-wrap gap-1.5">
                              {COMPARABLE_FIELDS.filter(f => (c as any)[f] && (group.contacts[0] as any)[f] !== (c as any)[f]).map(f => {
                                const currentSelection = selectedFields[group.id]?.[f];
                                const isSelected = currentSelection === c.id.toString();
                                return (
                                  <button
                                    key={f}
                                    onClick={() => handleFieldSelect(group.id, f, c.id.toString())}
                                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border transition-all ${
                                      isSelected
                                        ? 'bg-primary-container text-white border-primary-container'
                                        : 'bg-white text-slate-500 border-border-light'
                                    }`}
                                  >
                                    {FIELD_LABELS[f]}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}

            {/* Merge Button */}
            <button
              onClick={handleMergeAll}
              disabled={merging}
              className="fixed bottom-0 left-0 right-0 z-50 m-4 py-3 bg-primary-container text-white rounded-xl font-bold text-sm active:scale-95 transition-transform shadow-lg disabled:opacity-50"
            >
              {merging ? '合并中...' : `合并 ${mergeGroups.filter(g => !skipAll[g.id]).length} 组重复联系人`}
            </button>
          </>
        )}
      </main>
    </div>
  );
}
