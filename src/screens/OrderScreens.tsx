import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, MapPin, ChevronRight, FileText, Wallet, CheckCircle2, TrendingUp, Home, ShoppingBag, Receipt, User, MoreHorizontal, Star, Search } from 'lucide-react';
import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { OrderItem } from '../types';

export function OrderConfirmation() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate('/product-detail', { state: { transition: 'push_back' } })}><ArrowLeft className="w-6 h-6 text-on-surface" /></button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">订单确认</h1>
      </header>

      <main className="pt-16 p-4 space-y-4 max-w-md mx-auto">
        <section className="bg-white rounded-2xl overflow-hidden border border-border-light shadow-sm">
          <div className="p-4 flex items-start gap-3">
            <MapPin className="text-primary-container mt-1" />
            <div className="flex-1">
              <div className="flex items-baseline gap-3 mb-1"><span className="font-bold text-lg">张三</span><span className="text-secondary text-sm">13800138000</span></div>
              <p className="text-sm text-secondary leading-relaxed">广东省深圳市南山区某某大厦101</p>
            </div>
            <ChevronRight className="text-border-light self-center" />
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-border-light p-4 space-y-3">
          <div className="flex gap-4">
            <div className="w-20 h-20 rounded-xl overflow-hidden bg-slate-50 shrink-0"><img src="https://lh3.googleusercontent.com/aida-public/AB6AXuDx3U-zlH0Wv9KUVMf0IbdPQJaFizVCy3RxZ-a4onJuuW3S6SX9GguEcARJmJmiE6lwQRo-VNHc8ZoCe12VEWnKK0kYbVukkkxbLbGAtN6siNrmOMJV5Y0xqYA9igw7bSXGR1R83x57VnLJ4wj9TDjLEe7ohRrctQsDo0js4qeoR8JUmWUNir_MB-JIjkt16vuymOnHnYGogNDb8ok1vnsnomoyYIagrqs6gRBe9bnHrcaDOeMUTrw3JzMR2eLHHnY9LeGiadzbX6BF" className="w-full h-full object-cover" /></div>
            <div className="flex-1 flex flex-col justify-between">
              <div><h3 className="font-bold text-sm line-clamp-1">高级护肝综合营养片</h3><p className="text-xs text-text-muted mt-1">规格：30天装</p></div>
              <div className="flex justify-between items-end"><span className="font-manrope text-lg font-bold text-primary-container">¥298.00</span><span className="text-xs text-text-muted">x1</span></div>
            </div>
          </div>
        </section>

        <section className="bg-sky-50 border-l-4 border-primary-container p-4 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-2"><Star className="text-primary-container" fill="currentColor" /><span className="font-bold text-sm">推荐人：李四</span></div>
          <span className="text-[10px] text-primary-container font-bold px-2 py-0.5 bg-sky-100 rounded">专属服务</span>
        </section>

        <section className="bg-white rounded-2xl border border-border-light p-4 space-y-2">
          <label className="text-xs font-bold text-on-surface flex items-center gap-1"><Link className="w-4 h-4" to="#" />订单备注</label>
          <input className="w-full h-12 bg-neutral-bg border-none rounded-xl px-4 text-sm focus:ring-1 focus:ring-primary-container" placeholder="订单备注（选填）" />
        </section>

        <section className="bg-white rounded-2xl border border-border-light p-4 space-y-3">
          <div className="flex justify-between text-sm"><span className="text-secondary">商品总额</span><span className="font-bold">¥298.00</span></div>
          <div className="flex justify-between text-sm"><span className="text-secondary">运费</span><span className="text-success font-bold">免运费</span></div>
        </section>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 bg-white border-t border-border-light shadow-xl p-4 pb-safe flex justify-between items-center">
        <div className="flex items-baseline gap-1">
          <span className="text-xs font-bold">合计：</span>
          <span className="font-manrope text-2xl font-bold text-primary-container">¥298.00</span>
        </div>
        <button 
          onClick={() => navigate('/payment-success', { state: { transition: 'push' } })}
          className="bg-primary-container text-white px-6 py-3 rounded-full font-bold flex items-center gap-2 active:scale-95 transition-transform"
        >
          <Wallet className="w-5 h-5" />
          微信支付 ¥298.00
        </button>
      </footer>
    </div>
  );
}

export function PaymentSuccessScreens() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-24 text-center">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate('/home', { state: { transition: 'push' } })} className="active:scale-95 transition-transform"><ArrowLeft className="w-6 h-6 text-on-surface" /></button>
        <h1 className="flex-1 font-manrope font-bold text-lg text-on-surface">Payment Success</h1>
        <div className="w-6"></div>
      </header>

      <main className="pt-24 px-6 flex flex-col items-center">
        <div className="mb-6"><CheckCircle2 className="w-20 h-20 text-success" fill="currentColor" /></div>
        <h2 className="text-2xl font-bold text-on-surface">支付成功！</h2>
        <p className="mt-4 text-3xl font-manrope font-bold text-primary-container">¥298.00</p>
        <p className="mt-2 text-xs text-text-muted">订单号：ORD20260425001</p>

        <div className="w-full h-px bg-border-light my-8"></div>

        <section className="w-full bg-sky-50 border border-primary-container rounded-2xl p-6 relative overflow-hidden text-left">
          <div className="relative z-10 space-y-4">
            <div className="flex items-center gap-2"><span className="bg-primary-container text-white text-[10px] px-2 py-0.5 rounded font-bold">PROMOTION</span><h3 className="font-bold">你也能赚</h3></div>
            <p className="text-sm border-b border-sky-200 pb-2">分享给朋友，TA下单你赚分润</p>
            <p className="font-bold text-sky-700">每单最高赚 <span className="text-2xl text-primary-container">29.8</span> 元</p>
            <button className="w-full py-3 bg-primary-container text-white font-bold rounded-xl flex items-center justify-center gap-2 active:scale-95 transition-transform shadow-lg shadow-sky-600/30">成为推广员 <TrendingUp className="w-4 h-4" /></button>
          </div>
        </section>

        <div className="w-full mt-8 flex flex-col gap-4">
          <button onClick={() => navigate('/my-orders', { state: { transition: 'push' } })} className="w-full py-3 border border-border-light bg-white rounded-xl font-bold active:bg-slate-50">查看订单详情</button>
          <button onClick={() => navigate('/home', { state: { transition: 'push' } })} className="text-secondary font-medium">返回首页</button>
        </div>
      </main>
    </div>
  );
}

export function MyOrders() {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [tab, setTab] = useState('全部');

  useEffect(() => {
    const params = new URLSearchParams();
    if (tab !== '全部') {
      const statusMap: Record<string, string> = { '待支付': 'pending', '待发货': 'shipping', '待收货': 'received', '已完成': 'completed' };
      const s = statusMap[tab];
      if (s) params.set('status', s);
    }
    const qs = params.toString();
    api.get<{orders: OrderItem[]}>('/api/orders' + (qs ? `?${qs}` : '')).then(res => {
      if (res.data?.orders) setOrders(res.data.orders);
    });
  }, [tab]);

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate('/promotion-center', { state: { transition: 'push_back' } })}><ArrowLeft className="w-6 h-6 text-on-surface" /></button>
        <h1 className="flex-1 font-manrope font-bold text-lg text-on-surface text-center">Order Details</h1>
        <MoreHorizontal className="w-6 h-6 text-primary-container" />
      </header>

      <nav className="fixed top-14 w-full bg-white border-b border-border-light z-40 flex overflow-x-auto no-scrollbar px-4 gap-6">
        {['全部', '待支付', '待发货', '待收货', '已完成'].map((t, i) => (
          <span key={i} onClick={() => setTab(t)} className={`py-4 text-sm font-bold whitespace-nowrap cursor-pointer ${t === tab ? 'text-primary border-b-2 border-primary' : 'text-text-muted'}`}>{t}</span>
        ))}
      </nav>

      <main className="pt-32 p-4 space-y-4">
        {orders.map((item, i) => (
          <div key={item.id || i} className="bg-white rounded-xl border border-border-light overflow-hidden shadow-sm">
            <div className="p-3 border-b border-border-light flex justify-between">
              <span className="text-[10px] text-text-muted">订单号: {item.id}</span>
              <span className={`${item.status === 'pending' ? 'bg-primary-container' : 'bg-secondary'} text-white px-2 py-0.5 rounded-full text-[10px] font-bold`}>{item.status}</span>
            </div>
            <div className="p-4 flex gap-4">
              <div className="w-16 h-16 bg-slate-50 rounded-lg shrink-0"></div>
              <div className="flex-1 space-y-1">
                <h3 className="font-bold text-sm">{item.product_name || `产品 #${item.product_id}`}</h3>
                <div className="flex justify-between items-end">
                  <p className="text-primary font-manrope font-bold">¥{item.total_price.toFixed(2)}</p>
                  <span className="text-xs text-text-muted">×{item.quantity}</span>
                </div>
              </div>
            </div>
            <div className="px-4 py-3 bg-sky-50/50 flex justify-between items-center border-t border-border-light">
              <p className="text-sm">合计: <span className="font-bold text-sky-600">¥{item.total_price.toFixed(2)}</span></p>
              <button className="bg-sky-600 text-white px-6 py-2 rounded-full text-xs font-bold">{item.status === 'pending' ? '立即支付' : '确认收货'}</button>
            </div>
          </div>
        ))}
      </main>

      <nav className="fixed bottom-0 w-full h-16 bg-white border-t border-border-light flex justify-around items-center px-4 pb-safe">
        <div onClick={() => navigate('/home', { state: { transition: 'none' } })} className="flex flex-col items-center gap-1 text-slate-400 cursor-pointer">
          <Home className="w-5 h-5" />
          <span className="text-[10px] font-medium uppercase tracking-wider">Home</span>
        </div>
        <div onClick={() => navigate('/product-pool', { state: { transition: 'none' } })} className="flex flex-col items-center gap-1 text-slate-400 cursor-pointer">
          <ShoppingBag className="w-5 h-5" />
          <span className="text-[10px] font-medium uppercase tracking-wider">Product Pool</span>
        </div>
        <div className="flex flex-col items-center gap-1 text-primary-container">
          <Receipt className="w-5 h-5" />
          <span className="text-[10px] font-bold uppercase tracking-wider">Orders</span>
        </div>
        <div className="flex flex-col items-center gap-1 text-slate-400">
          <User className="w-5 h-5" />
          <span className="text-[10px] font-medium uppercase tracking-wider">Profile</span>
        </div>
      </nav>
    </div>
  );
}

export function OrderManagement() {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OrderItem[]>([]);

  useEffect(() => {
    api.get<{orders: OrderItem[]}>('/api/orders?merchant=true').then(res => {
      if (res.data?.orders) setOrders(res.data.orders);
    });
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-24">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate('/admin', { state: { transition: 'push_back' } })}><ArrowLeft className="w-6 h-6 text-primary-container" /></button>
        <h1 className="flex-1 font-manrope font-bold text-lg text-primary-container text-center">Order Management</h1>
        <Search className="w-6 h-6 text-primary-container" />
      </header>

      <nav className="fixed top-14 w-full bg-neutral-bg border-b border-border-light z-40 flex px-4 gap-6 overflow-x-auto no-scrollbar">
        {['待发货', '配送中', '已完成', '全部'].map((tab, i) => (
          <span key={i} className={`py-4 text-sm font-bold whitespace-nowrap ${i === 0 ? 'text-primary-container border-b-2 border-primary-container' : 'text-secondary'}`}>{tab}</span>
        ))}
      </nav>

      <main className="pt-32 p-4 space-y-4">
        {orders.map((item, i) => (
          <div key={item.id || i} className="bg-white rounded-2xl border border-border-light overflow-hidden shadow-sm">
            <div className="p-4 space-y-4">
              <div className="flex justify-between items-start"><p className="text-[10px] text-text-muted">ID: {item.id}</p><span className="bg-red-50 text-error px-2 py-1 rounded text-[10px] font-bold">{item.status}</span></div>
              <div className="flex gap-4 pb-4 border-b border-dashed border-border-light">
                <div className="w-16 h-16 bg-slate-50 rounded-xl shrink-0"></div>
                <div className="flex-1 shrink-0"><h3 className="font-bold text-sm">{item.product_name || `产品 #${item.product_id}`}</h3><p className="text-primary-container font-manrope font-bold text-lg">¥{item.total_price.toFixed(2)}</p></div>
              </div>
              <div className="bg-slate-50 p-3 rounded-xl"><div className="flex items-start gap-2"><User className="w-4 h-4 text-secondary mt-1" /><div className="text-xs font-bold">用户<div className="font-normal text-secondary mt-1">下单时间：{item.created_at}</div></div></div></div>
              <div className="flex justify-between items-center pt-2">
                <div className="flex items-center gap-1.5 px-2 py-1 bg-yellow-50 rounded-full"><Star className="w-3 h-3 text-primary-container" fill="currentColor" /><span className="text-[10px] font-bold">推广员推荐</span></div>
                <button className="bg-primary-container text-white px-6 py-2 rounded-full font-bold text-sm transform active:scale-95 transition-transform">立即发货</button>
              </div>
            </div>
          </div>
        ))}
      </main>

      <footer className="fixed bottom-0 w-full h-16 bg-white border-t border-border-light flex justify-around items-center px-4 pb-safe">
        <Home className="text-slate-400" />
        <ShoppingBag className="text-primary-container" />
        <Wallet className="text-slate-400" />
        <User className="text-slate-400" />
      </footer>
    </div>
  );
}
