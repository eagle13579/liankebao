import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ChevronLeft, CreditCard, DollarSign, Calendar, CheckCircle,
  XCircle, Clock, AlertCircle, ExternalLink, Copy
} from 'lucide-react';
import { api } from '../../api/client';
import { PaymentTransactionItem, ContractTransactionsResponse } from '../../types';
import { Loading, ErrorBlock, Empty } from '../../components/StatusComponents';

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  success: { label: '成功', color: 'text-emerald-600', bg: 'bg-emerald-50', icon: CheckCircle },
  pending: { label: '处理中', color: 'text-amber-600', bg: 'bg-amber-50', icon: Clock },
  failed: { label: '失败', color: 'text-rose-600', bg: 'bg-rose-50', icon: XCircle },
  refunded: { label: '已退款', color: 'text-violet-600', bg: 'bg-violet-50', icon: AlertCircle },
};

const PLATFORM_ICONS: Record<string, string> = {
  wechat: '💚',
  alipay: '💙',
  bank: '🏦',
  balance: '💰',
};

export default function PaymentHistoryPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [contractTitle, setContractTitle] = useState('');
  const [transactions, setTransactions] = useState<PaymentTransactionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchTransactions = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await api.get<ContractTransactionsResponse>(`/api/contracts/${id}/transactions`);
      if (res.data) {
        setContractTitle(res.data.contract_title);
        setTransactions(res.data.items);
      }
      setLoading(false);
    } catch (e: any) {
      setError(e.message || '加载失败');
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);

  const formatAmount = (amount: number) => {
    const sign = amount >= 0 ? '+' : '';
    return `${sign}¥${Math.abs(amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('zh-CN');
  };

  const getStatusConfig = (status: string) => {
    return STATUS_CONFIG[status] || { label: status, color: 'text-slate-600', bg: 'bg-slate-100', icon: AlertCircle };
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 bg-white border-b border-border-light flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="text-slate-600">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <div>
            <h1 className="font-manrope text-lg font-bold text-slate-800">支付记录</h1>
            {contractTitle && (
              <p className="text-[10px] text-slate-400 truncate max-w-[200px]">{contractTitle}</p>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 pt-16 px-4">
        {loading && <Loading text="加载支付记录..." />}

        {error && <ErrorBlock message={error} onRetry={fetchTransactions} />}

        {!loading && !error && transactions.length === 0 && (
          <Empty
            text="暂无支付记录"
            description="该合同尚未产生支付交易"
            icon="💳"
          />
        )}

        {transactions.length > 0 && (
          <div className="space-y-3 pt-4">
            {/* Summary */}
            <div className="bg-white rounded-2xl border border-border-light p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CreditCard className="w-5 h-5 text-primary-container" />
                  <span className="text-sm font-bold text-slate-800">交易汇总</span>
                </div>
                <span className="text-xs text-slate-400">共 {transactions.length} 笔</span>
              </div>
            </div>

            {/* Transaction list */}
            {transactions.map(tx => {
              const sc = getStatusConfig(tx.status);
              const Icon = sc.icon;
              return (
                <div
                  key={tx.id}
                  className="bg-white rounded-2xl border border-border-light p-4 active:scale-[0.98] transition-transform"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2.5">
                      <div className={`w-9 h-9 rounded-xl ${sc.bg} flex items-center justify-center`}>
                        <Icon className={`w-5 h-5 ${sc.color}`} />
                      </div>
                      <div>
                        <p className="text-sm font-bold text-slate-800">
                          {tx.description || '交易'}
                        </p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${sc.bg} ${sc.color}`}>
                            {sc.label}
                          </span>
                          {tx.trade_type && (
                            <span className="text-[10px] text-slate-400">{tx.trade_type}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <span className={`text-sm font-extrabold ${tx.status === 'success' ? 'text-emerald-600' : tx.status === 'failed' ? 'text-rose-600' : 'text-slate-600'}`}>
                      {formatAmount(tx.amount)}
                    </span>
                  </div>

                  <div className="space-y-1.5 text-xs text-slate-500">
                    {tx.transaction_no && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-400">交易号:</span>
                        <span className="font-mono text-slate-600">{tx.transaction_no}</span>
                      </div>
                    )}
                    {tx.platform && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-400">支付方式:</span>
                        <span>{PLATFORM_ICONS[tx.platform] || ''} {tx.platform}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-1.5">
                      <Calendar className="w-3 h-3 text-slate-400" />
                      <span>创建: {formatDate(tx.created_at)}</span>
                    </div>
                    {tx.paid_at && (
                      <div className="flex items-center gap-1.5">
                        <CheckCircle className="w-3 h-3 text-emerald-400" />
                        <span>支付: {formatDate(tx.paid_at)}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
