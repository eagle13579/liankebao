import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Plus, FileText, ChevronLeft, ChevronRight,
  User, Building2, DollarSign, Calendar, AlertCircle,
  X, Filter
} from 'lucide-react';
import { api } from '../../api/client';
import { ContractItem, ContractListResponse } from '../../types';
import { Loading, ErrorBlock, Empty } from '../../components/StatusComponents';

const PAGE_SIZE = 20;
const STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'pending_sign', label: '待签署' },
  { value: 'signed', label: '已签署' },
  { value: 'in_progress', label: '履行中' },
  { value: 'completed', label: '已完成' },
  { value: 'terminated', label: '已终止' },
];

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  pending_sign: 'bg-amber-50 text-amber-600',
  signed: 'bg-blue-50 text-blue-600',
  in_progress: 'bg-violet-50 text-violet-600',
  completed: 'bg-emerald-50 text-emerald-600',
  terminated: 'bg-rose-50 text-rose-600',
};

export default function ContractsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'error' | 'success'>('loading');
  const [error, setError] = useState('');
  const [showFilter, setShowFilter] = useState(false);

  const fetchContracts = useCallback(async () => {
    setStatus('loading');
    try {
      const params = new URLSearchParams();
      if (search) params.set('keyword', search);
      if (statusFilter) params.set('status', statusFilter);
      params.set('page', String(page));
      params.set('size', String(PAGE_SIZE));
      const res = await api.get<ContractListResponse>(`/api/contracts?${params}`);
      if (res.data) {
        setContracts(res.data.items);
        setTotal(res.data.total);
      }
      setStatus('success');
    } catch (e: any) {
      setError(e.message || '加载失败');
      setStatus('error');
    }
  }, [search, statusFilter, page]);

  useEffect(() => { fetchContracts(); }, [fetchContracts]);

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      setSearch(searchInput);
      setPage(1);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const formatAmount = (amount: number) => {
    return `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/home')} className="text-slate-600">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <h1 className="font-manrope text-lg font-bold text-primary-container">合同管理</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilter(!showFilter)}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-bold border transition-all active:scale-95 ${
              showFilter || statusFilter
                ? 'bg-primary-container text-white border-primary-container'
                : 'bg-white text-slate-600 border-border-light'
            }`}
          >
            <Filter className="w-4 h-4" />
            筛选
          </button>
          <button
            onClick={() => navigate('/contracts/new')}
            className="flex items-center gap-1 bg-primary-container text-white px-3 py-1.5 rounded-xl text-xs font-bold active:scale-95 transition-transform"
          >
            <Plus className="w-4 h-4" />
            新建
          </button>
        </div>
      </header>

      {/* Search bar */}
      <div className="fixed top-16 w-full z-40 px-4 pt-2 pb-2 bg-neutral-bg">
        <div className="flex items-center gap-2 bg-white border border-border-light rounded-xl px-3 h-10 shadow-sm">
          <Search className="w-4 h-4 text-slate-400 shrink-0" />
          <input
            type="text"
            placeholder="搜索合同标题或乙方名称..."
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            className="flex-1 bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none border-none"
          />
          {searchInput && (
            <button onClick={() => { setSearchInput(''); setSearch(''); setPage(1); }} className="text-slate-400 hover:text-slate-600">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Status filter chips */}
      {showFilter && (
        <div className="fixed top-28 w-full z-40 px-4 py-2 bg-neutral-bg border-b border-border-light">
          <div className="flex flex-wrap gap-2">
            {STATUS_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => { setStatusFilter(opt.value); setPage(1); }}
                className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all active:scale-95 ${
                  statusFilter === opt.value
                    ? 'bg-primary-container text-white'
                    : 'bg-white text-slate-500 border border-border-light hover:border-primary-container/30'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main content */}
      <main className={`flex-1 px-4 ${showFilter ? 'pt-52' : 'pt-36'}`}>
        {status === 'loading' && <Loading text="加载合同中..." />}

        {status === 'error' && (
          <ErrorBlock message={error} onRetry={fetchContracts} />
        )}

        {status === 'success' && contracts.length === 0 && (
          <Empty
            text="暂无合同"
            description="创建您的第一份合同，开启交易履约"
            icon="📝"
            actionText="新建合同"
            onAction={() => navigate('/contracts/new')}
          />
        )}

        {status === 'success' && contracts.length > 0 && (
          <>
            <div className="space-y-3">
              {contracts.map(c => (
                <div
                  key={c.id}
                  onClick={() => navigate(`/contracts/${c.id}`, { state: { transition: 'push' } })}
                  className="bg-white rounded-2xl border border-border-light p-4 active:scale-[0.98] transition-transform cursor-pointer hover:shadow-md"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-9 h-9 rounded-xl bg-sky-50 flex items-center justify-center shrink-0">
                        <FileText className="w-5 h-5 text-primary-container" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-bold text-sm text-slate-800 truncate">{c.title}</h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {c.party_a_name} ↔ {c.party_b_name}
                        </p>
                      </div>
                    </div>
                    <span className={`shrink-0 text-[10px] font-bold px-2 py-1 rounded-full ${STATUS_COLORS[c.status] || 'bg-slate-100 text-slate-600'}`}>
                      {c.status_label}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-slate-500">
                    {c.contract_amount > 0 && (
                      <div className="flex items-center gap-1">
                        <DollarSign className="w-3.5 h-3.5" />
                        <span className="font-medium text-slate-700">{formatAmount(c.contract_amount)}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5" />
                      <span>{new Date(c.created_at).toLocaleDateString('zh-CN')}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-4 py-6">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white border border-border-light text-xs font-bold disabled:opacity-30 active:scale-95 transition-all"
                >
                  <ChevronLeft className="w-4 h-4" />
                  上一页
                </button>
                <span className="text-xs text-text-muted">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white border border-border-light text-xs font-bold disabled:opacity-30 active:scale-95 transition-all"
                >
                  下一页
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
