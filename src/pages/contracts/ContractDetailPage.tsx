import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ChevronLeft, FileText, User, Building2, DollarSign, Calendar,
  Clock, CheckCircle, XCircle, AlertCircle, Send, PenSquare,
  Play, Ban, ExternalLink, CreditCard, FileDown
} from 'lucide-react';
import { api } from '../../api/client';
import { ContractItem } from '../../types';
import { Loading, ErrorBlock } from '../../components/StatusComponents';
import { Button } from '../../components/ui/Button';

const STATUS_BADGE: Record<string, { color: string; bg: string; dot: string }> = {
  draft: { color: 'text-slate-600', bg: 'bg-slate-100', dot: 'bg-slate-400' },
  pending_sign: { color: 'text-amber-600', bg: 'bg-amber-50', dot: 'bg-amber-500' },
  signed: { color: 'text-blue-600', bg: 'bg-blue-50', dot: 'bg-blue-500' },
  in_progress: { color: 'text-violet-600', bg: 'bg-violet-50', dot: 'bg-violet-500' },
  completed: { color: 'text-emerald-600', bg: 'bg-emerald-50', dot: 'bg-emerald-500' },
  terminated: { color: 'text-rose-600', bg: 'bg-rose-50', dot: 'bg-rose-500' },
};

const STATUS_TRANSITIONS: Record<string, { action: string; label: string; endpoint: string; icon: any; variant: 'primary' | 'secondary' | 'danger' }[]> = {
  draft: [
    { action: 'submit', label: '提交签署', endpoint: '/submit', icon: Send, variant: 'primary' },
    { action: 'terminate', label: '终止合同', endpoint: '/terminate', icon: Ban, variant: 'danger' },
  ],
  pending_sign: [
    { action: 'sign', label: '确认签署', endpoint: '/sign', icon: PenSquare, variant: 'primary' },
    { action: 'terminate', label: '终止合同', endpoint: '/terminate', icon: Ban, variant: 'danger' },
  ],
  signed: [
    { action: 'start', label: '开始履行', endpoint: '/start', icon: Play, variant: 'primary' },
    { action: 'terminate', label: '终止合同', endpoint: '/terminate', icon: Ban, variant: 'danger' },
  ],
  in_progress: [
    { action: 'complete', label: '完成合同', endpoint: '/complete', icon: CheckCircle, variant: 'primary' },
    { action: 'terminate', label: '终止合同', endpoint: '/terminate', icon: Ban, variant: 'danger' },
  ],
  completed: [],
  terminated: [],
};

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [contract, setContract] = useState<ContractItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [showReasonInput, setShowReasonInput] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const fetchContract = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await api.get<ContractItem>(`/api/contracts/${id}`);
      if (res.data) setContract(res.data);
      setLoading(false);
    } catch (e: any) {
      setError(e.message || '加载失败');
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetchContract(); }, [fetchContract]);

  const handleAction = async (action: string, endpoint: string) => {
    if (action === 'terminate' && !reason) {
      setPendingAction(endpoint);
      setShowReasonInput(true);
      return;
    }
    if (action === 'terminate' && !reason.trim()) return;

    setActionLoading(action);
    try {
      const body: any = {};
      if (action === 'terminate' && reason.trim()) body.reason = reason.trim();
      const res = await api.post<ContractItem>(`/api/contracts/${id}${endpoint}`, body);
      if (res.data) setContract(res.data);
      setShowReasonInput(false);
      setReason('');
      setPendingAction(null);
    } catch (e: any) {
      alert('操作失败：' + (e.message || '未知错误'));
    } finally {
      setActionLoading(null);
    }
  };

  const formatAmount = (amount: number) => {
    return `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('zh-CN');
  };

  if (loading) return <div className="min-h-screen bg-neutral-bg flex items-center justify-center"><Loading text="加载合同详情..." /></div>;
  if (error) return <div className="min-h-screen bg-neutral-bg flex items-center justify-center"><ErrorBlock message={error} onRetry={fetchContract} /></div>;
  if (!contract) return <div className="min-h-screen bg-neutral-bg flex items-center justify-center"><ErrorBlock message="合同不存在" /></div>;

  const badge = STATUS_BADGE[contract.status] || STATUS_BADGE.draft;
  const transitions = STATUS_TRANSITIONS[contract.status] || [];

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-24">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 bg-white border-b border-border-light flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="text-slate-600">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <h1 className="font-manrope text-lg font-bold text-slate-800 truncate">合同详情</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(`/contracts/${id}/payments`)}
            className="flex items-center gap-1 text-xs font-medium text-primary-container bg-sky-50 px-3 py-1.5 rounded-xl active:scale-95 transition-transform"
          >
            <CreditCard className="w-4 h-4" />
            支付记录
          </button>
        </div>
      </header>

      <main className="flex-1 pt-16">
        {/* Status banner */}
        <div className="px-4 pt-4 pb-2">
          <div className={`${badge.bg} rounded-2xl p-4 border border-transparent`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl ${badge.bg} flex items-center justify-center`}>
                  <FileText className={`w-5 h-5 ${badge.color}`} />
                </div>
                <div>
                  <h2 className="font-bold text-base text-slate-800">{contract.title}</h2>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                    <span className={`text-xs font-semibold ${badge.color}`}>{contract.status_label}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Parties info */}
        <div className="px-4 mt-2">
          <div className="bg-white rounded-2xl border border-border-light divide-y divide-border-light">
            <div className="p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-sky-50 flex items-center justify-center shrink-0">
                <User className="w-5 h-5 text-primary-container" />
              </div>
              <div className="min-w-0">
                <p className="text-[10px] text-slate-400 font-medium uppercase">甲方</p>
                <p className="text-sm font-bold text-slate-800 truncate">{contract.party_a_name}</p>
                {contract.party_a_contact && (
                  <p className="text-xs text-slate-500">{contract.party_a_contact}</p>
                )}
              </div>
            </div>
            <div className="p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-violet-50 flex items-center justify-center shrink-0">
                <Building2 className="w-5 h-5 text-violet-600" />
              </div>
              <div className="min-w-0">
                <p className="text-[10px] text-slate-400 font-medium uppercase">乙方</p>
                <p className="text-sm font-bold text-slate-800 truncate">{contract.party_b_name}</p>
                {contract.party_b_contact && (
                  <p className="text-xs text-slate-500">{contract.party_b_contact}</p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Amount & Dates */}
        <div className="px-4 mt-3">
          <div className="bg-white rounded-2xl border border-border-light p-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[10px] text-slate-400 font-medium uppercase mb-1">合同金额</p>
                <p className="text-lg font-extrabold text-slate-800">{formatAmount(contract.contract_amount)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-400 font-medium uppercase mb-1">支付状态</p>
                <p className="text-sm font-bold text-slate-700">{contract.payment_status || '未支付'}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-400 font-medium uppercase mb-1">创建时间</p>
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-xs text-slate-600">{formatDate(contract.created_at)}</span>
                </div>
              </div>
              <div>
                <p className="text-[10px] text-slate-400 font-medium uppercase mb-1">更新时间</p>
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-xs text-slate-600">{formatDate(contract.updated_at)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Timeline */}
        <div className="px-4 mt-3">
          <div className="bg-white rounded-2xl border border-border-light p-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">时间线</h3>
            <div className="space-y-3">
              {[
                { label: '签署时间', time: contract.signed_at },
                { label: '开始履行', time: contract.started_at },
                { label: '完成时间', time: contract.completed_at },
                { label: '终止时间', time: contract.terminated_at },
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${item.time ? 'bg-emerald-400' : 'bg-slate-200'}`} />
                  <div className="flex-1 flex items-center justify-between">
                    <span className="text-xs text-slate-500">{item.label}</span>
                    <span className={`text-xs font-medium ${item.time ? 'text-slate-700' : 'text-slate-300'}`}>
                      {item.time ? formatDate(item.time) : '待处理'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Contract text preview */}
        {contract.contract_text && (
          <div className="px-4 mt-3">
            <div className="bg-white rounded-2xl border border-border-light p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">合同正文</h3>
                <button className="flex items-center gap-1 text-xs text-primary-container font-medium">
                  <FileDown className="w-3.5 h-3.5" />
                  下载PDF
                </button>
              </div>
              <div className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap line-clamp-6">
                {contract.contract_text}
              </div>
            </div>
          </div>
        )}

        {/* Notes */}
        {contract.notes && (
          <div className="px-4 mt-3">
            <div className="bg-white rounded-2xl border border-border-light p-4">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">备注</h3>
              <p className="text-xs text-slate-600">{contract.notes}</p>
            </div>
          </div>
        )}

        {/* Reason input modal */}
        {showReasonInput && (
          <div className="fixed inset-0 z-[60] bg-black/40 flex items-end sm:items-center justify-center">
            <div className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 mx-4">
              <h3 className="text-sm font-bold text-slate-800 mb-3">终止原因</h3>
              <textarea
                value={reason}
                onChange={e => setReason(e.target.value)}
                placeholder="请输入终止合同的原因..."
                className="w-full h-24 px-3 py-2.5 text-sm border border-border-light rounded-xl resize-none outline-none focus:border-primary-container/50"
              />
              <div className="flex gap-3 mt-4">
                <button
                  onClick={() => { setShowReasonInput(false); setReason(''); setPendingAction(null); }}
                  className="flex-1 py-2.5 text-sm font-bold rounded-xl border border-border-light text-slate-600 active:scale-95 transition-transform"
                >
                  取消
                </button>
                <button
                  onClick={() => pendingAction && handleAction('terminate', pendingAction)}
                  disabled={!reason.trim() || actionLoading === 'terminate'}
                  className="flex-1 py-2.5 text-sm font-bold rounded-xl bg-rose-500 text-white disabled:opacity-50 active:scale-95 transition-transform"
                >
                  {actionLoading === 'terminate' ? '处理中...' : '确认终止'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Sign URL */}
        {contract.sign_url && (
          <div className="px-4 mt-3">
            <a
              href={contract.sign_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between bg-white rounded-2xl border border-border-light p-4 active:scale-[0.98] transition-transform"
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
                  <ExternalLink className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm font-bold text-slate-800">电子签名链接</p>
                  <p className="text-xs text-slate-400">点击前往签署页面</p>
                </div>
              </div>
              <ChevronLeft className="w-5 h-5 text-slate-400 rotate-180" />
            </a>
          </div>
        )}
      </main>

      {/* Action buttons bar */}
      {transitions.length > 0 && (
        <div className="fixed bottom-0 w-full bg-white border-t border-border-light px-4 py-3">
          <div className="flex gap-3 max-w-lg mx-auto">
            {transitions.map(t => (
              <Button
                key={t.action}
                variant={t.variant}
                size="md"
                className="flex-1"
                loading={actionLoading === t.action}
                icon={<t.icon className="w-4 h-4" />}
                onClick={() => handleAction(t.action, t.endpoint)}
              >
                {t.label}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
