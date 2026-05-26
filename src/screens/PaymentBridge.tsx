import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Wallet, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { paymentApi } from '../api/payment';
import type { PaymentParams } from '../api/payment';

type PayStatus = 'preparing' | 'waiting' | 'success' | 'failed' | 'error' | 'not_wechat';

/** WeChat JSAPI 调起支付参数（V3 官方字段名） */
interface WechatPayRequest {
  appId: string;
  timeStamp: string;
  nonceStr: string;
  package: string;
  signType: string;
  paySign: string;
}

interface WindowWithWx extends Window {
  wx?: {
    requestPayment: (params: WechatPayRequest & {
      success: () => void;
      fail: (err: any) => void;
      cancel: () => void;
    }) => void;
  };
  WeixinJSBridge?: {
    invoke: (method: string, params: WechatPayRequest, callback: (res: { err_msg?: string }) => void) => void;
  };
}

/**
 * 检测当前是否为微信浏览器（内置 WeChat 或 Weixin JSBridge）
 */
function isWechatBrowser(): boolean {
  const ua = navigator.userAgent.toLowerCase();
  return ua.indexOf('micromessenger') !== -1;
}

export default function PaymentBridge() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const orderIdRaw = searchParams.get('order_no') || searchParams.get('order_id') || '';
  const orderId = parseInt(orderIdRaw, 10) || 0;
  const amount = searchParams.get('amount') || '0.00';
  const description = searchParams.get('description') || '商品订单';

  const [status, setStatus] = useState<PayStatus>('preparing');
  const [message, setMessage] = useState('正在准备支付...');
  const [errorMsg, setErrorMsg] = useState('');
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingCount = useRef(0);

  // 清理轮询
  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // 轮询订单状态
  const startPolling = useCallback(() => {
    stopPolling();
    pollingCount.current = 0;
    setStatus('waiting');
    setMessage('等待支付结果...');

    pollingRef.current = setInterval(async () => {
      pollingCount.current += 1;
      try {
        const res = await paymentApi.queryOrder(orderIdRaw);
        if (res.code === 0 && res.data) {
          if (res.data.status === 'success') {
            stopPolling();
            setStatus('success');
            setMessage('支付成功！');
            setTimeout(() => {
              navigate(`/payment-success?order_no=${orderIdRaw}&amount=${amount}`, {
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
  }, [orderIdRaw, amount, navigate, stopPolling]);

  // ===== 支付调起 =====

  /**
   * 通过 WeixinJSBridge 调起支付（微信内置浏览器，无需加载 JSSDK）
   */
  const invokeByWeixinJSBridge = (params: PaymentParams): Promise<string> =>
    new Promise((resolve, reject) => {
      const win = window as WindowWithWx;
      if (!win.WeixinJSBridge) {
        reject(new Error('WeixinJSBridge 不可用'));
        return;
      }
      win.WeixinJSBridge.invoke('requestPayment', params as WechatPayRequest, (res) => {
        if (res.err_msg === 'request_pay:cancel') {
          resolve('cancel');
        } else if (res.err_msg === 'request_pay:success') {
          resolve('success');
        } else {
          reject(new Error(res.err_msg || '支付调起失败'));
        }
      });
    });

  /**
   * 通过 wx JSSDK 调起支付（需先加载 jweixin）
   */
  const invokeByWxJSSDK = (params: PaymentParams): Promise<string> =>
    new Promise((resolve, reject) => {
      const win = window as WindowWithWx;
      if (typeof win.wx?.requestPayment !== 'function') {
        reject(new Error('wx JSSDK 不可用'));
        return;
      }
      win.wx.requestPayment({
        appId: params.appId,
        timeStamp: params.timeStamp,
        nonceStr: params.nonceStr,
        package: params.package,
        signType: params.signType || 'RSA',
        paySign: params.paySign,
        success: () => resolve('success'),
        fail: (err) => reject(new Error(err?.errMsg || 'wx 支付调起失败')),
        cancel: () => resolve('cancel'),
      });
    });

  /**
   * 尝试调起微信支付
   * 优先级：WeixinJSBridge > wx JSSDK
   */
  const invokeWechatPay = async () => {
    if (!orderId) {
      setStatus('error');
      setMessage('订单号缺失');
      setErrorMsg('无法获取订单信息');
      return;
    }

    setStatus('preparing');
    setMessage('正在获取支付参数...');

    try {
      const res = await paymentApi.unifiedOrder(orderId, description);
      if (res.code !== 0 || !res.data) {
        setStatus('error');
        setMessage('支付初始化失败');
        setErrorMsg(res.message || '获取支付参数失败');
        return;
      }

      // 从响应中提取 V3 支付参数（后端返回结构: { order: {...}, payment: {...} }）
      const paymentParams: PaymentParams = res.data.payment;
      if (!paymentParams || !paymentParams.package) {
        setStatus('error');
        setMessage('支付参数异常');
        setErrorMsg('未获取到有效的支付参数');
        return;
      }

      // 判断运行环境
      if (!isWechatBrowser()) {
        // 非微信浏览器 → 展示引导页
        setStatus('not_wechat');
        setMessage('请在微信中打开');
        setErrorMsg('当前浏览器不支持微信支付，请复制链接后在微信客户端中打开');
        return;
      }

      // 微信浏览器 → 尝试调起支付
      let payResult: string;
      const win = window as WindowWithWx;

      if (win.WeixinJSBridge) {
        payResult = await invokeByWeixinJSBridge(paymentParams);
      } else if (typeof win.wx?.requestPayment === 'function') {
        payResult = await invokeByWxJSSDK(paymentParams);
      } else {
        // WeixinJSBridge 和 wx JSSDK 都不可用 — 可能是微信内但未加载 JSSDK
        // 尝试等待 WeixinJSBridge 就绪，最多等 3 秒
        setMessage('正在初始化支付环境...');
        payResult = await new Promise<string>((resolve, reject) => {
          let resolved = false;
          const timeout = setTimeout(() => {
            if (!resolved) {
              resolved = true;
              reject(new Error('支付环境初始化超时'));
            }
          }, 3000);
          const checkBridge = () => {
            if (resolved) return;
            const w = window as WindowWithWx;
            if (w.WeixinJSBridge) {
              resolved = true;
              clearTimeout(timeout);
              invokeByWeixinJSBridge(paymentParams).then(resolve, reject);
            } else {
              setTimeout(checkBridge, 200);
            }
          };
          checkBridge();
        });
      }

      if (payResult === 'success') {
        startPolling();
      } else if (payResult === 'cancel') {
        setStatus('failed');
        setMessage('用户取消支付');
        setErrorMsg('您已取消支付，可在订单列表中继续支付');
      }
    } catch (e: any) {
      console.error('[PaymentBridge] 支付调起失败:', e);
      setStatus('error');
      setMessage('支付调起失败');
      setErrorMsg(e.message || '网络错误，请稍后重试');
    }
  };

  useEffect(() => {
    invokeWechatPay();
    return () => {
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  const handleRetry = () => {
    setErrorMsg('');
    invokeWechatPay();
  };

  const handleViewOrder = () => {
    stopPolling();
    navigate('/my-orders', { state: { transition: 'push' } });
  };

  const handleCopyLink = () => {
    const url = window.location.href;
    navigator.clipboard.writeText(url).then(() => {
      setErrorMsg('链接已复制，请在微信中打开');
    }).catch(() => {
      setErrorMsg('复制失败，请手动复制地址栏链接');
    });
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
          {status === 'not_wechat' && (
            <div className="w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center">
              <svg className="w-10 h-10 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
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

        {/* 非微信浏览器提示 */}
        {status === 'not_wechat' && (
          <div className="w-full bg-blue-50 border border-blue-200 rounded-2xl p-4 mt-2 space-y-3">
            <p className="text-sm text-blue-700 text-center leading-relaxed">
              微信支付仅支持在微信客户端中使用。
            </p>
            <div className="flex flex-col gap-2">
              <button
                onClick={handleCopyLink}
                className="w-full py-2.5 bg-blue-600 text-white font-bold rounded-xl text-sm active:scale-95 transition-transform"
              >
                复制链接
              </button>
              <p className="text-xs text-blue-500 text-center">
                复制后发送到微信，在微信中打开即可支付
              </p>
            </div>
          </div>
        )}

        {/* 订单信息 */}
        <div className="w-full bg-white rounded-2xl border border-border-light p-4 mt-4 space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-secondary">订单编号</span>
            <span className="font-bold text-on-surface">{orderIdRaw}</span>
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
