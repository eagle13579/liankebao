import { useNavigate } from 'react-router-dom';
import { LayoutDashboard, ClipboardCheck, Package, Users, History, HelpCircle, LogOut, Bell, Settings, Star, TrendingUp, ShoppingCart, Clock, ChevronRight } from 'lucide-react';
import { api } from '../api/client';
import { Loading, ErrorBlock, Empty, useApi } from '../components/StatusComponents';

interface DashboardData {
  today_revenue: number;
  today_orders: number;
  active_promoters: number;
  pending_products: number;
}
interface ProductReview {
  id: number; name: string; company?: string; price: number; created_at: string;
}
interface WithdrawalReview {
  id: number; user_name: string; amount: number; status: string; created_at: string;
}

export function AdminBackend() {
  const navigate = useNavigate();

  const { data: dashboard, status: dashStatus, error: dashError, refetch: dashRefetch } = useApi(
    () => api.get<{dashboard: DashboardData}>('/api/admin/dashboard').then(r => r.data?.dashboard || null),
    []
  );

  const { data: products, status: prodStatus, error: prodError, refetch: prodRefetch } = useApi(
    () => api.get<{products: ProductReview[]}>('/api/admin/products').then(r => r.data?.products || []),
    []
  );

  const { data: withdrawals, status: wdStatus, error: wdError, refetch: wdRefetch } = useApi(
    () => api.get<{withdrawals: WithdrawalReview[]}>('/api/admin/withdrawals').then(r => r.data?.withdrawals || []),
    []
  );

  const handleReview = async (id: number, action: 'approve' | 'reject') => {
    const res = await api.put(`/api/admin/products/${id}/review`, { action });
    if (res.code === 200) {
      prodRefetch();
    }
  };

  const handleWithdrawalReview = async (id: number, action: 'approve' | 'reject') => {
    const res = await api.put(`/api/admin/withdrawals/${id}/review`, { action });
    if (res.code === 200) {
      wdRefetch();
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 font-sans">
      <header className="sticky top-0 z-50 flex justify-between items-center px-6 h-16 w-full bg-white border-b border-slate-200 shadow-sm font-manrope antialiased">
        <div className="flex items-center gap-4">
          <span className="text-xl font-extrabold tracking-tight text-sky-600 uppercase">企盟 · 管理后台</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden md:flex gap-4 mr-4">
            <button className="p-2 hover:bg-slate-100 rounded-full transition-colors"><Bell className="w-5 h-5 text-slate-600" /></button>
            <button className="p-2 hover:bg-slate-100 rounded-full transition-colors"><Settings className="w-5 h-5 text-slate-600" /></button>
          </div>
          <div className="flex items-center gap-3 pl-4 border-l border-slate-200">
            <div className="text-right hidden sm:block">
              <p className="text-xs font-bold">管理员</p>
              <p className="text-[10px] text-slate-400">超级管理员</p>
            </div>
            <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuAmSWd7mn7UJhRx3PlEEJFehjEvLKuCYZPDC8pnc2yJhSgF6Z3XCx63_mPX1JAr4vqao1Yz-2-MD3w_D0tIMqQQUT_oTirdfdYWY3EJucOReHpNdZA3hJ8oK0DEfU_alRwIEdYI2O_P_6N3o6Lq9KUo9_MGjKRdKCNuFguJGbK58Ve_61lROxhwEZ71BPcr_BwcPlwvEIeYBeTohvmkSfH1fT9EH2pj7fIqArpoU5_KXCuUozA9qoZRdOK3uvk6-QthDhW22BR5PZf2" className="w-10 h-10 rounded-full border-2 border-sky-500" />
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="hidden md:flex flex-col w-64 bg-slate-900 h-full shadow-xl shrink-0">
          <div className="p-6">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-sky-500 rounded-lg flex items-center justify-center shadow-lg shadow-sky-500/20"><Star className="text-white w-5 h-5" fill="currentColor" /></div>
              <div><h2 className="text-white font-black text-lg tracking-tight">企盟</h2><p className="text-slate-500 text-[10px] font-bold">管理后台</p></div>
            </div>
          </div>
          <nav className="flex-1 py-4 text-slate-400 space-y-1">
            <div onClick={() => navigate('/admin', { state: { transition: 'none' } })} className="px-4 py-3 flex items-center gap-3 hover:text-sky-400 hover:bg-white/5 transition-all cursor-pointer"><LayoutDashboard className="w-5 h-5" /><span>数据看板</span></div>
            <div onClick={() => navigate('/admin', { state: { transition: 'none' } })} className="px-4 py-3 bg-sky-500/10 text-sky-400 border-l-4 border-sky-400 flex items-center gap-3 cursor-pointer"><ClipboardCheck className="w-5 h-5" /><span>产品审核</span></div>
            <div onClick={() => navigate('/merchant-orders', { state: { transition: 'push' } })} className="px-4 py-3 flex items-center gap-3 hover:text-white hover:bg-slate-800 transition-all cursor-pointer"><span>订单管理</span></div>
            <div className="px-4 py-3 flex items-center gap-3 hover:text-white hover:bg-slate-800 transition-all cursor-pointer"><span>分润结算</span></div>
            <div className="px-4 py-3 flex items-center gap-3 hover:text-white hover:bg-slate-800 transition-all cursor-pointer"><span>用户管理</span></div>
            <div className="px-4 py-3 flex items-center gap-3 hover:text-white hover:bg-slate-800 transition-all cursor-pointer"><span>系统日志</span></div>
          </nav>
          <div className="p-4 border-t border-slate-800 text-slate-400">
            <div className="px-4 py-3 flex items-center gap-3 hover:text-white transition-all cursor-pointer"><HelpCircle /><span>帮助中心</span></div>
            <div onClick={() => navigate('/', { state: { transition: 'push_back' } })} className="px-4 py-3 flex items-center gap-3 hover:text-white transition-all cursor-pointer"><LogOut /><span>退出登录</span></div>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-8 space-y-8">
          {dashStatus === 'loading' ? (
            <Loading text="加载数据看板..." />
          ) : dashStatus === 'error' ? (
            <ErrorBlock message={dashError} onRetry={dashRefetch} />
          ) : (
          <>
          <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">今日交易额</span><TrendingUp className="text-emerald-500" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">¥{(dashboard?.today_revenue || 0).toLocaleString()}</span></div>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">今日订单数</span><ShoppingCart className="text-sky-500" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">{dashboard?.today_orders || 0}</span></div>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">活跃推广员</span><Users className="text-slate-600" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">{dashboard?.active_promoters || 0}</span></div>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm border-l-4 border-l-sky-500">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">待审核产品</span><Clock className="text-sky-600" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">{dashboard?.pending_products || 0}</span></div>
            </div>
          </section>

          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
              <h2 className="text-lg font-bold">产品审核</h2>
              <button className="text-sm font-bold text-sky-500 hover:underline">查看全部 <ChevronRight className="inline w-4 h-4" /></button>
            </div>
            <div className="overflow-x-auto">
              {prodStatus === 'loading' ? (
                <div className="p-8"><Loading text="加载产品审核..." /></div>
              ) : prodStatus === 'error' ? (
                <div className="p-8"><ErrorBlock message={prodError} onRetry={prodRefetch} /></div>
              ) : !products || products.length === 0 ? (
                <div className="p-8"><Empty text="暂无待审核产品" icon="✅" /></div>
              ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase tracking-widest font-bold">
                  <tr><th className="px-6 py-4">产品信息</th><th className="px-6 py-4">建议零售价</th><th className="px-6 py-4">申请时间</th><th className="px-6 py-4 text-right">操作</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {products.map((row, i) => (
                    <tr key={row.id || i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4 flex items-center gap-3">
                        <div className="w-10 h-10 rounded bg-slate-100 border border-slate-200"></div>
                        <div><p className="font-bold">{row.name}</p><p className="text-[10px] text-slate-400">{row.company || '-'}</p></div>
                      </td>
                      <td className="px-6 py-4 font-bold text-sky-600 uppercase tracking-tighter">¥{row.price.toFixed(2)}</td>
                      <td className="px-6 py-4 text-slate-400">{row.created_at}</td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button onClick={() => handleReview(row.id, 'approve')} className="bg-success text-white px-4 py-1.5 rounded-lg text-xs font-bold shadow-sm">通过</button>
                        <button onClick={() => handleReview(row.id, 'reject')} className="bg-slate-100 text-slate-600 px-4 py-1.5 rounded-lg text-xs font-bold grayscale">驳回</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              )}
            </div>
          </section>

          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
              <h2 className="text-lg font-bold">提现审核</h2>
              <button className="text-sm font-bold text-sky-500 hover:underline">查看全部 <ChevronRight className="inline w-4 h-4" /></button>
            </div>
            <div className="overflow-x-auto">
              {wdStatus === 'loading' ? (
                <div className="p-8"><Loading text="加载提现审核..." /></div>
              ) : wdStatus === 'error' ? (
                <div className="p-8"><ErrorBlock message={wdError} onRetry={wdRefetch} /></div>
              ) : !withdrawals || withdrawals.length === 0 ? (
                <div className="p-8"><Empty text="暂无提现申请" icon="✅" /></div>
              ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase tracking-widest font-bold">
                  <tr><th className="px-6 py-4">申请人</th><th className="px-6 py-4">金额</th><th className="px-6 py-4">申请时间</th><th className="px-6 py-4 text-right">操作</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {withdrawals.map((row, i) => (
                    <tr key={row.id || i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4 font-bold">{row.user_name}</td>
                      <td className="px-6 py-4 font-bold text-sky-600">¥{row.amount.toFixed(2)}</td>
                      <td className="px-6 py-4 text-slate-400">{row.created_at}</td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button onClick={() => handleWithdrawalReview(row.id, 'approve')} className="bg-success text-white px-4 py-1.5 rounded-lg text-xs font-bold shadow-sm">通过</button>
                        <button onClick={() => handleWithdrawalReview(row.id, 'reject')} className="bg-slate-100 text-slate-600 px-4 py-1.5 rounded-lg text-xs font-bold grayscale">驳回</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              )}
            </div>
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 pb-12">
            <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6"><h3 className="font-bold mb-6">7日交易额趋势</h3><div className="h-64 flex items-end gap-4"><div className="flex-1 bg-amber-500 rounded-t h-[60%]"></div><div className="flex-1 bg-amber-500 rounded-t h-[80%]"></div><div className="flex-1 bg-amber-500 rounded-t h-[40%]"></div><div className="flex-1 bg-amber-500 rounded-t h-[90%]"></div></div></section>
            <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6"><h3 className="font-bold mb-6">推广员排行榜</h3><div className="space-y-4">{[1,2,3].map(i => (<div key={i} className="flex items-center gap-3"><div className="w-8 h-8 rounded-full bg-slate-100"></div><div className="flex-1 h-3 bg-slate-50 rounded-full"></div><div className="w-12 h-3 bg-slate-50 rounded-full"></div></div>))}</div></section>
          </div>
          </>
          )}
        </main>
      </div>
    </div>
  );
}
