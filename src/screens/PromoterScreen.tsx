import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, TrendingUp, Wallet, Clock, CheckCircle2, Users,
  DollarSign, Banknote, History, Copy, Share2, ChevronRight,
  UserPlus, Gift, BarChart3, Loader2, X, AlertCircle
} from 'lucide-react';
import { api } from '../api/client';
import { Loading, ErrorBlock, useApi } from '../components/StatusComponents';
import type { PromoterEarnings, WithdrawalItem } from '../types';

export function PromoterPage() {
  const navigate = useNavigate();

  const { data: earnings, status: earnStatus, error: earnError, refetch: earnRefetch } = useApi<PromoterEarnings | null>(
    () => api.get<PromoterEarnings>('/api/promoter/earnings').then(r => (r.code === 200 && r.data ? r.data : null)),
    []
  );

  const { data: withdrawals, status: wdStatus, error: wdError, refetch: wdRefetch } = useApi<WithdrawalItem[]>(
    () => api.get<{total: number; items: WithdrawalItem[]}>('/api/promoter/withdrawals').then(r => (r.code === 200 && r.data ? r.data.items : [])),
    []
  );

  const [showWithdrawModal, setShowWithdrawModal] = useState(false);
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [bankInfo, setBankInfo] = useState('');
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawError, setWithdrawError] = useState('');
  const [copyToast, setCopyToast] = useState('');

  const handleWithdraw = async () => {
    setWithdrawError('');
    const amount = parseFloat(withdrawAmount);
    if (!amount || amount <= 0) { setWithdrawError('请输入有效的提现金额'); return; }
    if (earnings && amount > earnings.available) { setWithdrawError(`可提现金额不足，最多可提现 ¥${earnings.available.toFixed(2)}`); return; }

    setWithdrawing(true);
    try {
      const res = await api.post('/api/promoter/withdraw', {
        amount,
        bank_info: bankInfo.trim() || undefined,
      });
      if (res.code === 200) {
        setShowWithdrawModal(false);
        setWithdrawAmount('');
        setBankInfo('');
        setCopyToast('提现申请已提交，等待审核');
        setTimeout(() => setCopyToast(''), 2500);
        earnRefetch();
        wdRefetch();
      } else {
        setWithdrawError(res.message || '提现失败，请重试');
      }
    } catch (e: any) {
      setWithdrawError(e.message || '网络错误');
    } finally {
      setWithdrawing(false);
    }
  };

  const copyInviteLink = () => {
    navigator.clipboard.writeText('https://liankebao.top/register?ref=promoter');
    setCopyToast('推广链接已复制');
    setTimeout(() => setCopyToast(''), 2500);
  };

  const statusBadge = (status: string) => {
    const m: Record<string, {label: string; cls: string}> = {
      approved: { label: '已到账', cls: 'bg-emerald-50 text-emerald-600' },
      pending: { label: '审核中', cls: 'bg-amber-50 text-amber-600' },
      rejected: { label: '已驳回', cls: 'bg-rose-50 text-rose-600' },
    };
    const s = m[status] || { label: status, cls: 'bg-slate-100 text-slate-500' };
    return <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${s.cls}`}>{s.label}</span>;
  };

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/50 via-white to-white font-sans pb-24">
      {/* Header */}
      <header className="bg-gradient-to-r from-sky-500 to-indigo-500 px-4 pt-12 pb-6 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute w-72 h-72 bg-white rounded-full -top-20 -right-20" />
          <div className="absolute w-48 h-48 bg-white rounded-full bottom-0 left-10" />
        </div>
        <div className="flex items-center gap-3 relative z-10">
          <button onClick={() => navigate('/home')} className="w-9 h-9 flex items-center justify-center rounded-xl bg-white/20 text-white active:scale-90 transition-all">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-xl font-extrabold text-white font-manrope">推广分润中心</h1>
            <p className="text-xs text-white/70">推广赚钱 · 提现灵活</p>
          </div>
        </div>
      </header>

      <div className="px-4 -mt-4 space-y-4">
        {/* Earnings Summary Card */}
        {earnStatus === 'loading' ? (
          <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm">
            <div className="skeleton h-8 w-24 rounded mb-4" />
            <div className="grid grid-cols-2 gap-4">
              <div className="skeleton h-6 w-full rounded" />
              <div className="skeleton h-6 w-full rounded" />
              <div className="skeleton h-6 w-full rounded" />
              <div className="skeleton h-6 w-full rounded" />
            </div>
          </div>
        ) : earnStatus === 'error' ? (
          <ErrorBlock message={earnError} onRetry={earnRefetch} />
        ) : earnings ? (
          <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-700 flex items-center gap-2">
                <Wallet className="w-4 h-4 text-sky-500" />
                收益概览
              </h2>
              <span className="text-xs text-slate-400">共 {earnings.order_count} 笔订单</span>
            </div>

            {/* Main Amount */}
            <div className="text-center py-4 mb-4 bg-gradient-to-br from-sky-50 to-blue-50 rounded-2xl border border-sky-100">
              <p className="text-xs text-slate-500 mb-1">可提现余额</p>
              <p className="text-4xl font-extrabold text-sky-600 font-manrope">
                ¥{earnings.available.toFixed(2)}
              </p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="text-center p-3 bg-slate-50 rounded-xl">
                <p className="text-[10px] text-slate-400 mb-1">累计收益</p>
                <p className="text-sm font-bold text-slate-800">¥{earnings.total_earnings.toFixed(2)}</p>
              </div>
              <div className="text-center p-3 bg-slate-50 rounded-xl">
                <p className="text-[10px] text-slate-400 mb-1">已提现</p>
                <p className="text-sm font-bold text-emerald-600">¥{earnings.withdrawn.toFixed(2)}</p>
              </div>
              <div className="text-center p-3 bg-slate-50 rounded-xl">
                <p className="text-[10px] text-slate-400 mb-1">审核中</p>
                <p className="text-sm font-bold text-amber-600">¥{earnings.pending.toFixed(2)}</p>
              </div>
            </div>

            {/* Withdraw Button */}
            <button
              onClick={() => setShowWithdrawModal(true)}
              disabled={earnings.available <= 0}
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold text-sm shadow-lg shadow-sky-500/20 active:scale-[0.98] transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Banknote className="w-4 h-4" />
              立即提现
            </button>
          </div>
        ) : null}

        {/* Quick Actions */}
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={copyInviteLink}
            className="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm flex items-center gap-3 active:scale-[0.97] transition-all"
          >
            <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center">
              <UserPlus className="w-5 h-5 text-emerald-600" />
            </div>
            <div className="text-left">
              <p className="text-sm font-bold text-slate-800">邀请推广员</p>
              <p className="text-[10px] text-slate-400">复制邀请链接</p>
            </div>
          </button>
          <button
            onClick={() => navigate('/subordinates')}
            className="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm flex items-center gap-3 active:scale-[0.97] transition-all"
          >
            <div className="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center">
              <Users className="w-5 h-5 text-violet-600" />
            </div>
            <div className="text-left">
              <p className="text-sm font-bold text-slate-800">我的团队</p>
              <p className="text-[10px] text-slate-400">下级推广员</p>
            </div>
          </button>
        </div>

        {/* Referral Stats */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
              <Gift className="w-4 h-4 text-rose-500" />
              推广数据
            </h3>
            <button onClick={() => navigate('/promotion-tutorial')} className="text-xs text-sky-600 font-medium flex items-center gap-0.5">
              教程 <ChevronRight className="w-3 h-3" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-3 p-3 bg-sky-50 rounded-xl">
              <BarChart3 className="w-5 h-5 text-sky-500" />
              <div>
                <p className="text-xs text-slate-500">推广订单</p>
                <p className="text-lg font-bold text-slate-800">{earnings?.order_count || 0}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-amber-50 rounded-xl">
              <TrendingUp className="w-5 h-5 text-amber-500" />
              <div>
                <p className="text-xs text-slate-500">分润比例</p>
                <p className="text-lg font-bold text-slate-800">最高 15%</p>
              </div>
            </div>
          </div>
        </div>

        {/* Withdrawal History */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
              <History className="w-4 h-4 text-sky-500" />
              提现记录
            </h3>
          </div>
          {wdStatus === 'loading' ? (
            <div className="p-8"><Loading text="加载提现记录..." /></div>
          ) : wdStatus === 'error' ? (
            <div className="p-4"><ErrorBlock message={wdError} onRetry={wdRefetch} /></div>
          ) : !withdrawals || withdrawals.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-slate-400">
              <History className="w-10 h-10 mb-3 text-slate-300" />
              <p className="text-sm">暂无提现记录</p>
              <p className="text-xs mt-1">推广产品获得收益后即可提现</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-50">
              {withdrawals.map((w) => (
                <div key={w.id} className="px-5 py-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-bold text-slate-800">¥{w.amount.toFixed(2)}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {new Date(w.created_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                  {statusBadge(w.status)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Withdraw Modal */}
      {showWithdrawModal && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowWithdrawModal(false)}>
          <div className="bg-white rounded-t-3xl sm:rounded-2xl w-full max-w-md p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-extrabold text-slate-800">提现</h3>
              <button onClick={() => setShowWithdrawModal(false)} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            {withdrawError && (
              <div className="bg-rose-50 border border-rose-200 rounded-xl px-4 py-3 text-sm text-rose-600 mb-4 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {withdrawError}
              </div>
            )}

            <div className="mb-4">
              <label className="text-xs font-bold text-slate-500 mb-2 block">可提现金额：¥{(earnings?.available || 0).toFixed(2)}</label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-lg font-bold text-slate-400">¥</span>
                <input
                  type="number"
                  placeholder="请输入提现金额"
                  value={withdrawAmount}
                  onChange={e => setWithdrawAmount(e.target.value)}
                  className="w-full pl-10 pr-4 py-4 text-lg font-bold text-slate-800 bg-slate-50 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500"
                />
              </div>
            </div>

            <div className="mb-6">
              <label className="text-xs font-bold text-slate-500 mb-2 block">银行信息（选填）</label>
              <input
                type="text"
                placeholder="如：招商银行 尾号8888"
                value={bankInfo}
                onChange={e => setBankInfo(e.target.value)}
                className="w-full px-4 py-3 text-sm text-slate-800 bg-slate-50 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500"
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowWithdrawModal(false)}
                className="flex-1 py-3.5 rounded-xl bg-slate-100 text-slate-600 font-bold text-sm active:scale-[0.97] transition-all"
              >
                取消
              </button>
              <button
                onClick={handleWithdraw}
                disabled={withdrawing}
                className="flex-1 py-3.5 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold text-sm shadow-lg shadow-sky-500/20 active:scale-[0.97] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {withdrawing ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {withdrawing ? '提交中...' : '确认提现'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {copyToast && (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[60] bg-slate-800 text-white text-sm font-bold px-5 py-3 rounded-full shadow-lg animate-fadeIn">
          {copyToast}
        </div>
      )}
    </div>
  );
}
