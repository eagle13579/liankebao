import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Wallet, Loader2, CheckCircle2, XCircle,
  CreditCard, ChevronRight, Clock, TrendingUp, ArrowDown, ArrowUp,
  Plus, Banknote, Filter
} from 'lucide-react';
import {
  getRechargeBalance, createRechargePrecreate, queryRechargeOrder,
  getRechargeList, getBalanceLogs, RechargeBalanceResponse,
  RechargeItem
} from '../api/recharge';

// ─────────────────── Helpers ───────────────────

const PRESET_AMOUNTS = [50, 100, 200, 500, 1000];

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

const formatTime = (s: string | null) => {
  if (!s) return '—';
  try {
    const d = new Date(s);
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return s;
  }
};

const formatAmount = (n: number) => '¥' + n.toFixed(2);

const statusLabel: Record<string, string> = {
  paid: '支付成功',
  pending: '处理中',
  failed: '支付失败',
  expired: '已过期',
  timeout: '超时',
};

const statusColor: Record<string, string> = {
  paid: 'text-emerald-600 bg-emerald-50',
  pending: 'text-amber-600 bg-amber-50',
  failed: 'text-rose-600 bg-rose-50',
  expired: 'text-slate-400 bg-slate-100',
  timeout: 'text-rose-600 bg-rose-50',
};

// ─────────────────── Types ───────────────────

type PaymentStatus = 'preparing' | 'waiting' | 'success' | 'failed' | 'error';

interface WindowWithWx extends Window {
  wx?: {
    requestPayment: (params: {
      timestamp: string;
      nonceStr: string;
      package: string;
      signType: string;
      paySign: string;
      success: () => void;
      fail: (err: any) => void;
      cancel: () => void;
    }) => void;
  };
}

// ─────────────────── Page: RechargeAmountPage ───────────────────

export function RechargeAmountPage() {
  const navigate = useNavigate();
  const [balanceData, setBalanceData] = useState<RechargeBalanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAmount, setSelectedAmount] = useState<number | null>(null);
  const [customAmount, setCustomAmount] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    getRechargeBalance().then(res => {
      if (res.code === 0 && res.data) setBalanceData(res.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const getAmount = (): number | null => {
    if (selectedAmount !== null) return selectedAmount;
    if (customAmount) {
      const v = parseFloat(customAmount);
      if (!isNaN(v) && v > 0) return Math.round(v * 100) / 100;
    }
    return null;
  };

  const handleConfirm = () => {
    const amount = getAmount();
    if (amount === null) {
      setError('请选择或输入充值金额');
      return;
    }
    if (amount > 999999.99) {
      setError('单次充值金额不能超过¥999,999.99');
      return;
    }
    setError('');
    navigate('/recharge/pay?amount=' + amount.toFixed(2));
  };

  const handleCustomChange = (v: string) => {
    // 只允许数字和小数点，最多2位小数
    if (!/^\d*\.?\d{0,2}$/.test(v)) return;
    setCustomAmount(v);
    setSelectedAmount(null);
    setError('');
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate(-1)}>
          <ArrowLeft className="w-6 h-6 text-on-surface" />
        </button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">账户充值</h1>
      </header>

      <main className="pt-20 px-5 max-w-md mx-auto w-full space-y-6">
        {/* 余额卡片 */}
        <div className="bg-gradient-to-br from-sky-500 to-blue-600 rounded-2xl p-5 shadow-lg">
          <div className="flex items-center gap-2 mb-1">
            <Wallet className="w-5 h-5 text-white/80" />
            <span className="text-white/70 text-xs font-bold">可用余额</span>
          </div>
          {loading ? (
            <div className="h-10 w-28 skeleton rounded-lg mt-1" />
          ) : (
            <p className="text-white text-3xl font-extrabold font-manrope mt-1">
              {formatAmount(balanceData?.balance ?? 0)}
            </p>
          )}
          {balanceData && (
            <div className="flex gap-4 mt-3 text-white/70 text-[10px]">
              <span>累计充值 {formatAmount(balanceData.total_recharged)}</span>
              <span>累计消费 {formatAmount(balanceData.total_consumed)}</span>
            </div>
          )}
        </div>

        {/* 预设金额 */}
        <section>
          <h2 className="font-bold text-on-surface text-sm mb-3">选择金额</h2>
          <div className="grid grid-cols-3 gap-3">
            {PRESET_AMOUNTS.map((amt) => (
              <button
                key={amt}
                onClick={() => { setSelectedAmount(amt); setCustomAmount(''); setError(''); }}
                className={`py-3 rounded-xl font-bold text-sm border-2 transition-all active:scale-95 ${
                  selectedAmount === amt
                    ? 'border-sky-500 bg-sky-50 text-sky-700'
                    : 'border-border-light bg-white text-on-surface hover:border-sky-300'
                }`}
              >
                ¥{amt}
              </button>
            ))}
          </div>
        </section>

        {/* 自定义金额 */}
        <section>
          <h2 className="font-bold text-on-surface text-sm mb-3">自定义金额</h2>
          <div className="relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-xl font-bold text-slate-400">¥</span>
            <input
              type="text"
              inputMode="decimal"
              placeholder="输入充值金额"
              value={customAmount}
              onChange={e => handleCustomChange(e.target.value)}
              className="w-full pl-10 pr-4 py-3 bg-white border border-border-light rounded-xl text-lg font-bold text-on-surface placeholder:text-text-muted focus:outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            />
          </div>
        </section>

        {error && <p className="text-error text-xs text-center">{error}</p>}

        {/* 确认充值 */}
        <button
          onClick={handleConfirm}
          className="w-full py-3 bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold rounded-xl text-base active:scale-[0.98] transition-transform shadow-md"
        >
          确认充值
        </button>

        {/* 快捷入口 */}
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/recharge/history')}
            className="flex-1 py-3 bg-white border border-border-light rounded-xl text-sm font-bold text-on-surface active:bg-slate-50 flex items-center justify-center gap-1"
          >
            <Banknote className="w-4 h-4" /> 充值记录
          </button>
          <button
            onClick={() => navigate('/recharge/balance')}
            className="flex-1 py-3 bg-white border border-border-light rounded-xl text-sm font-bold text-on-surface active:bg-slate-50 flex items-center justify-center gap-1"
          >
            <TrendingUp className="w-4 h-4" /> 余额明细
          </button>
        </div>
      </main>
    </div>
  );
}

// ─────────────────── Page: RechargePaymentPage ───────────────────

export function RechargePaymentPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const amount = searchParams.get('amount') || '0.00';

  const [platform, setPlatform] = useState<'wxpay' | 'alipay'>('wxpay');
  const [status, setStatus] = useState<PaymentStatus>('preparing');
  const [message, setMessage] = useState('正在准备支付...');
  const [errorMsg, setErrorMsg] = useState('');
  const [orderNo, setOrderNo] = useState('');
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingCount = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback((no: string) => {
    stopPolling();
    pollingCount.current = 0;
    setStatus('waiting');
    setMessage('等待支付结果...');

    pollingRef.current = setInterval(async () => {
      pollingCount.current += 1;
      try {
        const res = await queryRechargeOrder(no);
        if (res.code === 0 && res.data) {
          if (res.data.status === 'paid') {
            stopPolling();
            setStatus('success');
            setMessage('充值成功！');
            setTimeout(() => {
              navigate('/recharge/result?order_no=' + no + '&amount=' + amount + '&status=success', {
                state: { transition: 'push' },
              });
            }, 1500);
            return;
          } else if (res.data.status === 'failed') {
            stopPolling();
            setStatus('failed');
            setMessage('充值失败');
            setErrorMsg('支付未完成，请重新尝试');
            return;
          }
        }
        if (pollingCount.current >= 20) {
          stopPolling();
          setStatus('failed');
          setMessage('支付超时');
          setErrorMsg('支付结果确认超时，请查询充值记录');
        }
      } catch (e: any) {
        console.error('[RechargePayment] 轮询失败:', e);
      }
    }, 3000);
  }, [amount, navigate, stopPolling]);

  const invokePayment = useCallback(async () => {
    setStatus('preparing');
    setMessage('正在获取支付参数...');
    setErrorMsg('');

    try {
      const numericAmount = parseFloat(amount);
      if (isNaN(numericAmount) || numericAmount <= 0) {
        setStatus('error');
        setMessage('金额无效');
        setErrorMsg('请返回重新选择充值金额');
        return;
      }

      const res = await createRechargePrecreate(numericAmount, platform);
      if (res.code !== 0 || !res.data) {
        setStatus('error');
        setMessage('支付初始化失败');
        setErrorMsg(res.message || '获取支付参数失败');
        return;
      }

      const data = res.data;
      setOrderNo(data.order_no);

      const win = window as WindowWithWx;

      if (platform === 'wxpay' && typeof win.wx?.requestPayment === 'function') {
        // 微信小程序环境
        const params = data.pay_params || {};
        win.wx.requestPayment({
          timestamp: params.timestamp || '',
          nonceStr: params.nonce_str || '',
          package: params.package_val || params.package || '',
          signType: params.sign_type || 'MD5',
          paySign: params.sign || '',
          success: () => startPolling(data.order_no),
          fail: (err) => {
            setStatus('error');
            setMessage('支付调起失败');
            setErrorMsg(err?.errMsg || '未知错误');
          },
          cancel: () => {
            setStatus('failed');
            setMessage('用户取消支付');
            setErrorMsg('您已取消支付，可在充值记录中继续支付');
          },
        });
      } else {
        // H5 环境：直接开始轮询（模拟支付流程）
        startPolling(data.order_no);
      }
    } catch (e: any) {
      setStatus('error');
      setMessage('支付请求失败');
      setErrorMsg(e.message || '网络错误，请稍后重试');
    }
  }, [amount, platform, startPolling]);

  useEffect(() => {
    invokePayment();
    return () => stopPolling();
  }, []);

  const handleChangePlatform = (p: 'wxpay' | 'alipay') => {
    if (status === 'preparing' || status === 'waiting') return; // 支付中不可切换
    setPlatform(p);
  };

  const handleRetry = () => {
    setErrorMsg('');
    invokePayment();
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate(-1)}>
          <ArrowLeft className="w-6 h-6 text-on-surface" />
        </button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">充值支付</h1>
      </header>

      <main className="pt-24 px-6 flex flex-col items-center max-w-md mx-auto w-full">
        {/* 状态图标 */}
        <div className="mb-6">
          {status === 'preparing' && (
            <div className="w-20 h-20 bg-sky-50 rounded-full flex items-center justify-center">
              <Loader2 className="w-10 h-10 text-primary-container animate-spin" />
            </div>
          )}
          {status === 'waiting' && (
            <div className="w-20 h-20 bg-amber-50 rounded-full flex items-center justify-center">
              <Loader2 className="w-10 h-10 text-amber-500 animate-spin" />
            </div>
          )}
          {status === 'success' && (
            <div className="w-20 h-20 bg-green-50 rounded-full flex items-center justify-center">
              <CheckCircle2 className="w-10 h-10 text-success" />
            </div>
          )}
          {(status === 'failed' || status === 'error') && (
            <div className="w-20 h-20 bg-red-50 rounded-full flex items-center justify-center">
              <XCircle className="w-10 h-10 text-error" />
            </div>
          )}
        </div>

        {/* 状态文本 */}
        <h2 className="text-xl font-bold text-on-surface mb-2">{message}</h2>
        {errorMsg && (
          <p className="text-sm text-error mb-4 text-center">{errorMsg}</p>
        )}

        {/* 充值信息 */}
        <div className="w-full bg-white rounded-2xl border border-border-light p-4 space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-secondary">充值金额</span>
            <span className="font-manrope text-lg font-bold text-primary-container">¥{amount}</span>
          </div>
          {orderNo && (
            <div className="flex justify-between text-sm">
              <span className="text-secondary">订单编号</span>
              <span className="font-bold text-on-surface text-xs">{orderNo}</span>
            </div>
          )}
          <div className="flex justify-between text-sm">
            <span className="text-secondary">支付方式</span>
            <span className="font-bold flex items-center gap-1">
              {platform === 'wxpay' ? (
                <><Wallet className="w-4 h-4 text-green-500" /> 微信支付</>
              ) : (
                <><CreditCard className="w-4 h-4 text-blue-500" /> 支付宝</>
              )}
            </span>
          </div>
        </div>

        {/* 支付方式选择 */}
        {(status === 'failed' || status === 'error' || status === 'preparing') && status !== 'waiting' && (
          <div className="w-full mt-6">
            <h3 className="font-bold text-on-surface text-sm mb-3">选择支付方式</h3>
            <div className="space-y-2">
              <button
                onClick={() => handleChangePlatform('wxpay')}
                className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 transition-all ${
                  platform === 'wxpay' ? 'border-green-500 bg-green-50' : 'border-border-light bg-white'
                }`}
              >
                <Wallet className="w-6 h-6 text-green-500" />
                <span className="font-bold text-sm text-on-surface">微信支付</span>
                {platform === 'wxpay' && <CheckCircle2 className="w-5 h-5 text-green-500 ml-auto" />}
              </button>
              <button
                onClick={() => handleChangePlatform('alipay')}
                className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 transition-all ${
                  platform === 'alipay' ? 'border-blue-500 bg-blue-50' : 'border-border-light bg-white'
                }`}
              >
                <CreditCard className="w-6 h-6 text-blue-500" />
                <span className="font-bold text-sm text-on-surface">支付宝</span>
                {platform === 'alipay' && <CheckCircle2 className="w-5 h-5 text-blue-500 ml-auto" />}
              </button>
            </div>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="w-full mt-8 flex flex-col gap-3">
          {(status === 'failed' || status === 'error') && (
            <button
              onClick={handleRetry}
              className="w-full py-3 bg-primary-container text-white font-bold rounded-xl flex items-center justify-center gap-2 active:scale-95 transition-transform"
            >
              <Wallet className="w-5 h-5" />
              重新支付
            </button>
          )}
          {status === 'waiting' && (
            <div className="text-center text-xs text-text-muted">正在确认支付结果...</div>
          )}
          {status === 'success' && (
            <button
              onClick={() => navigate('/recharge/result?status=success&amount=' + amount + '&order_no=' + orderNo)}
              className="w-full py-3 bg-primary-container text-white font-bold rounded-xl active:scale-95 transition-transform"
            >
              查看结果
            </button>
          )}
        </div>
      </main>
    </div>
  );
}

// ─────────────────── Page: RechargeResultPage ───────────────────

export function RechargeResultPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const resultStatus = searchParams.get('status') || 'success';
  const amount = searchParams.get('amount') || '0.00';
  const isSuccess = resultStatus === 'success';

  const [balance, setBalance] = useState<number | null>(null);

  useEffect(() => {
    if (isSuccess) {
      getRechargeBalance().then(res => {
        if (res.code === 0 && res.data) setBalance(res.data.balance);
      }).catch(() => {});
    }
  }, [isSuccess]);

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate('/recharge')}>
          <ArrowLeft className="w-6 h-6 text-on-surface" />
        </button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">充值结果</h1>
      </header>

      <main className="pt-24 px-6 flex flex-col items-center max-w-md mx-auto w-full">
        {/* 状态图标 */}
        <div className={`w-20 h-20 rounded-full flex items-center justify-center mb-6 ${isSuccess ? 'bg-green-50' : 'bg-red-50'}`}>
          {isSuccess ? (
            <CheckCircle2 className="w-10 h-10 text-success" />
          ) : (
            <XCircle className="w-10 h-10 text-error" />
          )}
        </div>

        <h2 className="text-xl font-bold text-on-surface mb-2">
          {isSuccess ? '充值成功' : '充值失败'}
        </h2>

        {isSuccess ? (
          <>
            <p className="text-3xl font-extrabold font-manrope text-primary-container mb-2">
              +¥{amount}
            </p>
            {balance !== null && (
              <p className="text-sm text-text-muted">
                当前余额：<span className="font-bold text-on-surface">{formatAmount(balance)}</span>
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-text-muted mb-2">支付未完成，请重新尝试</p>
        )}

        {/* 操作按钮 */}
        <div className="w-full mt-8 flex flex-col gap-3">
          {isSuccess ? (
            <>
              <button
                onClick={() => navigate('/recharge/balance')}
                className="w-full py-3 bg-primary-container text-white font-bold rounded-xl active:scale-95 transition-transform"
              >
                查看余额明细
              </button>
              <button
                onClick={() => navigate('/recharge')}
                className="w-full py-3 border border-border-light bg-white rounded-xl font-bold text-on-surface active:bg-slate-50"
              >
                继续充值
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => navigate('/recharge/pay?amount=' + amount)}
                className="w-full py-3 bg-primary-container text-white font-bold rounded-xl active:scale-95 transition-transform"
              >
                重新支付
              </button>
              <button
                onClick={() => navigate('/recharge/history')}
                className="w-full py-3 border border-border-light bg-white rounded-xl font-bold text-on-surface active:bg-slate-50"
              >
                查看充值记录
              </button>
            </>
          )}
          <button
            onClick={() => navigate('/home', { state: { transition: 'push_back' } })}
            className="text-secondary font-medium text-sm py-2"
          >
            返回首页
          </button>
        </div>
      </main>
    </div>
  );
}

// ─────────────────── Page: RechargeHistoryPage ───────────────────

export function RechargeHistoryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<RechargeItem[]>([]);
  const [balanceData, setBalanceData] = useState<RechargeBalanceResponse | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const pageSize = 20;

  const loadData = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const [balanceRes, listRes] = await Promise.all([
        getRechargeBalance(),
        getRechargeList(p, pageSize),
      ]);
      if (balanceRes.code === 0 && balanceRes.data) setBalanceData(balanceRes.data);
      if (listRes.code === 0 && listRes.data) {
        setItems(p === 1 ? listRes.data.items : prev => [...prev, ...listRes.data!.items]);
        setTotal(listRes.data.total);
        setPage(p);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(1); }, [loadData]);

  const hasMore = items.length < total;

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate(-1)}>
          <ArrowLeft className="w-6 h-6 text-on-surface" />
        </button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">充值记录</h1>
      </header>

      <main className="pt-20 px-5 max-w-md mx-auto w-full space-y-4">
        {/* 余额汇总卡片 */}
        <div className="bg-white rounded-2xl border border-border-light p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <Wallet className="w-4 h-4 text-sky-500" />
            <h2 className="font-bold text-on-surface text-sm">余额汇总</h2>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <p className="text-xs text-text-muted">可用余额</p>
              <p className="text-lg font-extrabold font-manrope text-on-surface">
                {formatAmount(balanceData?.balance ?? 0)}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-muted">本月充值</p>
              <p className="text-lg font-extrabold font-manrope text-emerald-600">
                {formatAmount(balanceData?.total_recharged ?? 0)}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-muted">本月消费</p>
              <p className="text-lg font-extrabold font-manrope text-rose-500">
                {formatAmount(balanceData?.total_consumed ?? 0)}
              </p>
            </div>
          </div>
        </div>

        {/* 列表 */}
        <section>
          <h2 className="font-bold text-on-surface text-sm mb-3">充值明细</h2>
          {loading && items.length === 0 ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-16 skeleton rounded-xl" />)}
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-10">
              <Banknote className="w-12 h-12 text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-muted">暂无充值记录</p>
            </div>
          ) : (
            <div className="space-y-2">
              {items.map(item => (
                <div key={item.id} className="bg-white rounded-xl border border-border-light p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-bold text-on-surface text-sm">{formatAmount(item.amount)}</p>
                      <p className="text-xs text-text-muted mt-1">
                        {item.platform === 'wxpay' ? '微信支付' : '支付宝'} · {formatTime(item.created_at)}
                      </p>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-1 rounded-full ${statusColor[item.status] || 'text-slate-500 bg-slate-100'}`}>
                      {statusLabel[item.status] || item.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 加载更多 */}
          {hasMore && (
            <button
              onClick={() => loadData(page + 1)}
              disabled={loading}
              className="w-full mt-3 py-3 border border-border-light bg-white rounded-xl text-sm font-bold text-secondary active:bg-slate-50 disabled:opacity-50"
            >
              {loading ? '加载中...' : '加载更多'}
            </button>
          )}
        </section>
      </main>
    </div>
  );
}

// ─────────────────── Page: BalanceDetailPage ───────────────────

export function BalanceDetailPage() {
  const navigate = useNavigate();
  const [logs, setLogs] = useState<RechargeBalanceResponse['recent_logs']>([]);
  const [balanceData, setBalanceData] = useState<RechargeBalanceResponse | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const pageSize = 20;

  const loadData = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const [balanceRes, logsRes] = await Promise.all([
        getRechargeBalance(),
        getBalanceLogs(p, pageSize),
      ]);
      if (balanceRes.code === 0 && balanceRes.data) setBalanceData(balanceRes.data);
      if (logsRes.code === 0 && logsRes.data) {
        setLogs(p === 1 ? logsRes.data.items : prev => [...prev, ...logsRes.data!.items]);
        setTotal(logsRes.data.total);
        setPage(p);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(1); }, [loadData]);

  const hasMore = logs.length < total;

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate(-1)}>
          <ArrowLeft className="w-6 h-6 text-on-surface" />
        </button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">余额明细</h1>
      </header>

      <main className="pt-20 px-5 max-w-md mx-auto w-full space-y-4">
        {/* 余额卡片 */}
        <div className="bg-gradient-to-br from-sky-500 to-blue-600 rounded-2xl p-5 shadow-lg">
          <div className="flex items-center gap-2 mb-1">
            <Wallet className="w-5 h-5 text-white/80" />
            <span className="text-white/70 text-xs font-bold">当前余额</span>
          </div>
          <p className="text-white text-3xl font-extrabold font-manrope mt-1">
            {formatAmount(balanceData?.balance ?? 0)}
          </p>
        </div>

        {/* 明细列表 */}
        <section>
          <h2 className="font-bold text-on-surface text-sm mb-3">变动明细</h2>
          {loading && logs.length === 0 ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-16 skeleton rounded-xl" />)}
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-10">
              <TrendingUp className="w-12 h-12 text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-muted">暂无变动记录</p>
            </div>
          ) : (
            <div className="space-y-2">
              {logs.map(log => {
                const isIncome = log.type === 'recharge';
                return (
                  <div key={log.id} className="bg-white rounded-xl border border-border-light p-4 flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
                      isIncome ? 'bg-emerald-50' : 'bg-rose-50'
                    }`}>
                      {isIncome ? (
                        <ArrowDown className="w-5 h-5 text-emerald-600" />
                      ) : (
                        <ArrowUp className="w-5 h-5 text-rose-500" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                          isIncome ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600'
                        }`}>
                          {isIncome ? '充值' : '消费'}
                        </span>
                        <span className="text-xs text-text-muted truncate">{log.description}</span>
                      </div>
                      <p className="text-xs text-text-muted mt-1">{formatTime(log.created_at)}</p>
                    </div>
                    <p className={`font-bold font-manrope text-sm shrink-0 ${
                      isIncome ? 'text-emerald-600' : 'text-rose-500'
                    }`}>
                      {isIncome ? '+' : '-'}{formatAmount(log.amount)}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {/* 加载更多 */}
          {hasMore && (
            <button
              onClick={() => loadData(page + 1)}
              disabled={loading}
              className="w-full mt-3 py-3 border border-border-light bg-white rounded-xl text-sm font-bold text-secondary active:bg-slate-50 disabled:opacity-50"
            >
              {loading ? '加载中...' : '加载更多'}
            </button>
          )}
        </section>
      </main>
    </div>
  );
}

// ─────────────────── Router Export ───────────────────

export default function RechargeScreens() {
  return <RechargeAmountPage />;
}
