import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Wallet, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { paymentApi } from '../api/payment';

type PayStatus = 'preparing' | 'waiting' | 'success' | 'failed' | 'error';

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

export default function PaymentBridge() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const orderNo = searchParams.get('order_no') || '';
  const amount = searchParams.get('amount') || '0.00';
  const description = searchParams.get('description') || '商品订单';

  const [status, setStatus] = useState<PayStatus>('preparing');
  const [message, setMessage] = useState('正在准备支付...');
  const [errorMsg, setErrorMsg] = useState('');
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingCount = useRef(0);

  // 清理轮询
  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  // 轮询订单状态
  const startPolling = () => {
    stopPolling();
    pollingCount.current = 0;
    setStatus('waiting');
    setMessage('等待支付结果...');

    pollingRef.current = setInterval(async () => {
      pollingCount.current += 1;
      try {
        const res = await paymentApi.queryOrder(orderNo);
        if (res.code === 0 && res.data) {
          if (res.data.status === 'success') {
            stopPolling();
            setStatus('success');
            setMessage('支付成功！');
            // 2秒后跳转到成功页
            setTimeout(() => {
              navigate(`/payment-success?order_no=${orderNo}&amount=${amount}`, {
                state: { transition: 'push' },
              });
            }, 2000);
            return;
          } else if (res.data.status === 'failed') {
            stopPolling();
            setStatus('failed');
            setMessage('支付失败');
            setErrorMsg('支付未完成，请重新尝试');
            return;
          }
        }
        // 超时处理：轮询超过60秒（20次）提示用户
        if (pollingCount.current > 20) {
          stopPolling();
          setStatus('failed');
          setMessage('支付超时');
          setErrorMsg('支付结果确认超时，请查询订单状态');
        }
      } catch (e: any) {
        console.error('[PaymentBridge] 轮询失败:', e);
      }
    }, 3000);
  };

  // 尝试调起微信支付
  const invokeWechatPay = async () => {
    setStatus('preparing');
    setMessage('正在获取支付参数...');

    try {
      const res = await paymentApi.unifiedOrder(orderNo, description);
      if (res.code !== 0 || !res.data) {
        setStatus('error');
        setMessage('支付初始化失败');
        setErrorMsg(res.message || '获取支付参数失败');
        return;
      }

      const payData = res.data;
      const win = window as WindowWithWx;

      // 微信小程序环境：使用 wx.requestPayment
      if (typeof win.wx?.requestPayment === 'function') {
        win.wx.requestPayment({
          timestamp: payData.timestamp,
          nonceStr: payData.nonce_str,
          package: payData.package_val,
          signType: 'MD5',
          paySign: payData.sign,
          success: () => {
            // 支付成功，开始轮询确认
            startPolling();
          },
          fail: (err) => {
            setStatus('error');
            setMessage('支付调起失败');
            setErrorMsg(err?.errMsg || '未知错误');
          },
          cancel: () => {
            setStatus('failed');
            setMessage('用户取消支付');
            setErrorMsg('您已取消支付，可在订单列表中继续支付');
          },
        });
      } else {
        // H5环境：直接开始轮询（模拟支付流程）
        // 实际H5场景可能需要跳转微信支付H5页面或展示二维码
        // 这里我们先调用统一下单后直接轮询
        startPolling();
      }
    } catch (e: any) {
      setStatus('error');
      setMessage('支付请求失败');
      setErrorMsg(e.message || '网络错误，请稍后重试');
    }
  };

  useEffect(() => {
    if (orderNo) {
      invokeWechatPay();
    } else {
      setStatus('error');
      setMessage('订单号缺失');
      setErrorMsg('无法获取订单信息');
    }

    return () => {
      stopPolling();
    };
  }, [orderNo]);

  const handleRetry = () => {
    setErrorMsg('');
    invokeWechatPay();
  };

  const handleViewOrder = () => {
    stopPolling();
    navigate('/my-orders', { state: { transition: 'push' } });
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate(-1)}>
          <ArrowLeft className="w-6 h-6 text-on-surface" />
        </button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">支付中心</h1>
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

        {/* 订单信息 */}
        <div className="w-full bg-white rounded-2xl border border-border-light p-4 mt-4 space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-secondary">订单编号</span>
            <span className="font-bold text-on-surface">{orderNo}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-secondary">支付金额</span>
            <span className="font-manrope text-lg font-bold text-primary-container">¥{amount}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-secondary">支付方式</span>
            <span className="font-bold flex items-center gap-1">
              <Wallet className="w-4 h-4 text-green-500" />
              微信支付
            </span>
          </div>
        </div>

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
            <div className="text-center text-xs text-text-muted">
              正在确认支付结果...
            </div>
          )}
          <button
            onClick={handleViewOrder}
            className="w-full py-3 border border-border-light bg-white rounded-xl font-bold active:bg-slate-50"
          >
            查看订单列表
          </button>
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
