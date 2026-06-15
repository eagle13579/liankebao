import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import {
  LayoutDashboard, ClipboardCheck, Package, Users, History, HelpCircle, LogOut, Bell, Settings, Star, TrendingUp, ShoppingCart, Clock, ChevronRight,
  DollarSign, UserCheck, AlertTriangle, BarChart3, CreditCard, Shield, Search, X, Loader2, ChevronDown, Filter, MoreHorizontal, Eye, Edit3, Trash2
} from 'lucide-react';
import { api } from '../api/client';
import { Loading, ErrorBlock, Empty, useApi } from '../components/StatusComponents';
import type { AdminDashboardData, AdminUserItem, AdminProductItem, AdminWithdrawalItem } from '../types';

export function AdminBackend() {
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState('dashboard');
  const [searchUser, setSearchUser] = useState('');
  const [userRoleUpdating, setUserRoleUpdating] = useState<number | null>(null);
  const [userPage, setUserPage] = useState(1);
  const [userTotal, setUserTotal] = useState(0);
  const USER_PAGE_SIZE = 10;

  const { data: dashboard, status: dashStatus, error: dashError, refetch: dashRefetch } = useApi<AdminDashboardData | null>(
    () => api.get<AdminDashboardData>('/api/admin/dashboard').then(r => r.code === 200 && r.data ? r.data : null),
    []
  );

  const { data: products, status: prodStatus, error: prodError, refetch: prodRefetch } = useApi<AdminProductItem[]>(
    () => api.get<{total: number; items: AdminProductItem[]}>('/api/admin/products').then(r => r.code === 200 && r.data ? r.data.items : []),
    []
  );

  const { data: withdrawals, status: wdStatus, error: wdError, refetch: wdRefetch } = useApi<AdminWithdrawalItem[]>(
    () => api.get<{total: number; items: AdminWithdrawalItem[]}>('/api/admin/withdrawals').then(r => r.code === 200 && r.data ? r.data.items : []),
    []
  );

  const { data: userData, status: userStatus, error: userError, refetch: userRefetch } = useApi<{total: number; page: number; page_size: number; items: AdminUserItem[]}>(
    () => {
      const params = new URLSearchParams();
      if (searchUser) params.set('search', searchUser);
      params.set('page', String(userPage));
      params.set('page_size', String(USER_PAGE_SIZE));
      return api.get<{total: number; page: number; page_size: number; items: AdminUserItem[]}>('/api/admin/users?' + params.toString())
        .then(r => {
          if (r.code === 200 && r.data) {
            setUserTotal(r.data.total);
            return r.data;
          }
          return { total: 0, page: 1, page_size: USER_PAGE_SIZE, items: [] };
        });
    },
    [searchUser, userPage]
  );

  const handleReview = async (id: number, action: 'approve' | 'reject') => {
    const res = await api.put(`/api/admin/products/${id}/review`, { action });
    if (res.code === 200) prodRefetch();
  };

  const handleWithdrawalReview = async (id: number, action: 'approve' | 'reject') => {
    const res = await api.put(`/api/admin/withdrawals/${id}/review`, { action });
    if (res.code === 200) wdRefetch();
  };

  const handleRoleChange = async (userId: number, role: string) => {
    setUserRoleUpdating(userId);
    try {
      await api.request(`/api/admin/users/${userId}/role`, { method: 'PATCH', body: JSON.stringify({ role }) });
      userRefetch();
    } catch {}
    setUserRoleUpdating(null);
  };

  const roleColor = (role: string) => {
    const m: Record<string, string> = {
      admin: 'bg-rose-100 text-rose-700',
      promoter: 'bg-sky-100 text-sky-700',
      user: 'bg-slate-100 text-slate-600',
    };
    return m[role] || 'bg-slate-100 text-slate-600';
  };

  const statusBadge = (status: string) => {
    const m: Record<string, {label: string; cls: string}> = {
      approved: { label: '已通过', cls: 'bg-emerald-100 text-emerald-700' },
      pending: { label: '待审核', cls: 'bg-amber-100 text-amber-700' },
      rejected: { label: '已驳回', cls: 'bg-rose-100 text-rose-700' },
      active: { label: '上架', cls: 'bg-emerald-100 text-emerald-700' },
      inactive: { label: '下架', cls: 'bg-slate-100 text-slate-500' },
    };
    const s = m[status] || { label: status, cls: 'bg-slate-100 text-slate-500' };
    return <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${s.cls}`}>{s.label}</span>;
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
            <div onClick={() => setActiveSection('dashboard')} className={`px-4 py-3 flex items-center gap-3 transition-all cursor-pointer ${activeSection === 'dashboard' ? 'bg-sky-500/10 text-sky-400 border-l-4 border-sky-400' : 'hover:text-sky-400 hover:bg-white/5'}`}>
              <LayoutDashboard className="w-5 h-5" /><span>数据看板</span>
            </div>
            <div onClick={() => setActiveSection('products')} className={`px-4 py-3 flex items-center gap-3 transition-all cursor-pointer ${activeSection === 'products' ? 'bg-sky-500/10 text-sky-400 border-l-4 border-sky-400' : 'hover:text-sky-400 hover:bg-white/5'}`}>
              <ClipboardCheck className="w-5 h-5" /><span>产品审核</span>
            </div>
            <div onClick={() => setActiveSection('orders')} className={`px-4 py-3 flex items-center gap-3 transition-all cursor-pointer ${activeSection === 'orders' ? 'bg-sky-500/10 text-sky-400 border-l-4 border-sky-400' : 'hover:text-sky-400 hover:bg-white/5'}`}>
              <ShoppingCart className="w-5 h-5" /><span>订单管理</span>
            </div>
            <div onClick={() => setActiveSection('withdrawals')} className={`px-4 py-3 flex items-center gap-3 transition-all cursor-pointer ${activeSection === 'withdrawals' ? 'bg-sky-500/10 text-sky-400 border-l-4 border-sky-400' : 'hover:text-sky-400 hover:bg-white/5'}`}>
              <DollarSign className="w-5 h-5" /><span>分润结算</span>
            </div>
            <div onClick={() => setActiveSection('users')} className={`px-4 py-3 flex items-center gap-3 transition-all cursor-pointer ${activeSection === 'users' ? 'bg-sky-500/10 text-sky-400 border-l-4 border-sky-400' : 'hover:text-sky-400 hover:bg-white/5'}`}>
              <Users className="w-5 h-5" /><span>用户管理</span>
            </div>
            <div onClick={() => setActiveSection('finance')} className={`px-4 py-3 flex items-center gap-3 transition-all cursor-pointer ${activeSection === 'finance' ? 'bg-sky-500/10 text-sky-400 border-l-4 border-sky-400' : 'hover:text-sky-400 hover:bg-white/5'}`}>
              <CreditCard className="w-5 h-5" /><span>资金概览</span>
            </div>
            <div onClick={() => navigate('/activities')} className="px-4 py-3 flex items-center gap-3 hover:text-sky-400 hover:bg-white/5 transition-all cursor-pointer">
              <History className="w-5 h-5" /><span>活动日志</span>
            </div>
          </nav>
          <div className="p-4 border-t border-slate-800 text-slate-400">
            <div className="px-4 py-3 flex items-center gap-3 hover:text-white transition-all cursor-pointer"><HelpCircle /><span>帮助中心</span></div>
            <div onClick={() => navigate('/', { state: { transition: 'push_back' } })} className="px-4 py-3 flex items-center gap-3 hover:text-white transition-all cursor-pointer"><LogOut /><span>退出登录</span></div>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-8 space-y-8">
          {/* Section: Dashboard */}
          {activeSection === 'dashboard' && (
          <>
          {dashStatus === 'loading' ? (
            <Loading text="加载数据看板..." />
          ) : dashStatus === 'error' ? (
            <ErrorBlock message={dashError} onRetry={dashRefetch} />
          ) : (
          <>
          <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">总交易额</span><TrendingUp className="text-emerald-500" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">¥{((dashboard?.total_revenue || 0)).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span></div>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">总订单数</span><ShoppingCart className="text-sky-500" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">{dashboard?.total_orders || 0}</span></div>
              <p className="text-[10px] text-slate-400 mt-1">今日 +{dashboard?.today_orders || 0}</p>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">注册用户</span><Users className="text-violet-500" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">{dashboard?.total_users || 0}</span></div>
            </div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm border-l-4 border-l-amber-500">
              <div className="flex justify-between mb-2"><span className="text-slate-400 text-xs font-bold uppercase tracking-wider">全部产品</span><Package className="text-amber-500" /></div>
              <div className="flex items-baseline gap-2"><span className="text-2xl font-bold font-manrope">{dashboard?.total_products || 0}</span></div>
            </div>
          </section>

          {/* Alert Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {dashboard && dashboard.pending_review_products > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                <div>
                  <p className="text-sm font-bold text-amber-800">{dashboard.pending_review_products} 个产品待审核</p>
                  <button onClick={() => setActiveSection('products')} className="text-xs text-amber-600 underline mt-0.5">前往审核</button>
                </div>
              </div>
            )}
            {dashboard && dashboard.pending_withdrawals > 0 && (
              <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 flex items-center gap-3">
                <DollarSign className="w-5 h-5 text-rose-600 shrink-0" />
                <div>
                  <p className="text-sm font-bold text-rose-800">{dashboard.pending_withdrawals} 笔提现待处理</p>
                  <button onClick={() => setActiveSection('withdrawals')} className="text-xs text-rose-600 underline mt-0.5">前往处理</button>
                </div>
              </div>
            )}
          </div>

          {/* Quick Overview Cards */}
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
              <h2 className="text-lg font-bold">待审核产品</h2>
              <button onClick={() => setActiveSection('products')} className="text-sm font-bold text-sky-500 hover:underline flex items-center gap-1">
                查看全部 <ChevronRight className="w-4 h-4" />
              </button>
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
                  <tr><th className="px-6 py-4">产品信息</th><th className="px-6 py-4">零售价</th><th className="px-6 py-4">状态</th><th className="px-6 py-4">申请时间</th><th className="px-6 py-4 text-right">操作</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {products.slice(0, 5).map((row, i) => (
                    <tr key={row.id || i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4">
                        <div><p className="font-bold">{row.name}</p></div>
                      </td>
                      <td className="px-6 py-4 font-bold text-sky-600">¥{row.price.toFixed(2)}</td>
                      <td className="px-6 py-4">{statusBadge(row.status)}</td>
                      <td className="px-6 py-4 text-slate-400 text-xs">{new Date(row.created_at).toLocaleDateString('zh-CN')}</td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button onClick={() => handleReview(row.id, 'approve')} className="bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-xs font-bold shadow-sm hover:bg-emerald-600 active:scale-95 transition-all">通过</button>
                        <button onClick={() => handleReview(row.id, 'reject')} className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg text-xs font-bold hover:bg-slate-200 active:scale-95 transition-all">驳回</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              )}
            </div>
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 pb-12">
            <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <h3 className="font-bold mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-sky-500" /> 数据概览</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 bg-sky-50 rounded-xl">
                  <span className="text-sm text-slate-600">用户总数</span>
                  <span className="font-bold text-lg">{dashboard?.total_users || 0}</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-emerald-50 rounded-xl">
                  <span className="text-sm text-slate-600">产品总数</span>
                  <span className="font-bold text-lg">{dashboard?.total_products || 0}</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-amber-50 rounded-xl">
                  <span className="text-sm text-slate-600">订单总数</span>
                  <span className="font-bold text-lg">{dashboard?.total_orders || 0}</span>
                </div>
              </div>
            </section>
            <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <h3 className="font-bold mb-4 flex items-center gap-2"><Users className="w-4 h-4 text-violet-500" /> 待处理事项</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">待审核产品</span>
                  <span className="font-bold text-amber-600">{dashboard?.pending_review_products || 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">待处理提现</span>
                  <span className="font-bold text-rose-600">{dashboard?.pending_withdrawals || 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">今日订单</span>
                  <span className="font-bold text-sky-600">{dashboard?.today_orders || 0}</span>
                </div>
              </div>
            </section>
          </div>
          </>
          )}
          </>
          )}

          {/* Section: Products Review */}
          {activeSection === 'products' && (
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
              <h2 className="text-lg font-bold">产品审核</h2>
              <span className="text-xs text-slate-400">共 {products?.length || 0} 个产品</span>
            </div>
            <div className="overflow-x-auto">
              {prodStatus === 'loading' ? (
                <div className="p-8"><Loading text="加载产品列表..." /></div>
              ) : prodStatus === 'error' ? (
                <div className="p-8"><ErrorBlock message={prodError} onRetry={prodRefetch} /></div>
              ) : !products || products.length === 0 ? (
                <div className="p-8"><Empty text="暂无产品" icon="📦" /></div>
              ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase tracking-widest font-bold">
                  <tr><th className="px-6 py-4">产品名称</th><th className="px-6 py-4">价格</th><th className="px-6 py-4">状态</th><th className="px-6 py-4">创建时间</th><th className="px-6 py-4 text-right">操作</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {products.map((row, i) => (
                    <tr key={row.id || i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4 font-bold">{row.name}</td>
                      <td className="px-6 py-4 font-bold text-sky-600">¥{row.price.toFixed(2)}</td>
                      <td className="px-6 py-4">{statusBadge(row.status)}</td>
                      <td className="px-6 py-4 text-slate-400 text-xs">{new Date(row.created_at).toLocaleString('zh-CN')}</td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button onClick={() => handleReview(row.id, 'approve')} className="bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-xs font-bold shadow-sm hover:bg-emerald-600 active:scale-95 transition-all">通过</button>
                        <button onClick={() => handleReview(row.id, 'reject')} className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg text-xs font-bold hover:bg-slate-200 active:scale-95 transition-all">驳回</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              )}
            </div>
          </section>
          )}

          {/* Section: Orders */}
          {activeSection === 'orders' && (
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold flex items-center gap-2"><ShoppingCart className="w-5 h-5 text-sky-500" /> 订单管理</h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-8">
              <div className="bg-sky-50 rounded-xl p-4 text-center">
                <p className="text-xs text-slate-500 mb-1">总订单</p>
                <p className="text-2xl font-bold text-sky-600">{dashboard?.total_orders || 0}</p>
              </div>
              <div className="bg-emerald-50 rounded-xl p-4 text-center">
                <p className="text-xs text-slate-500 mb-1">今日订单</p>
                <p className="text-2xl font-bold text-emerald-600">{dashboard?.today_orders || 0}</p>
              </div>
              <div className="bg-amber-50 rounded-xl p-4 text-center">
                <p className="text-xs text-slate-500 mb-1">总收入</p>
                <p className="text-2xl font-bold text-amber-600">¥{((dashboard?.total_revenue || 0)).toLocaleString(undefined, {minimumFractionDigits: 2})}</p>
              </div>
            </div>
            <div className="bg-slate-50 rounded-2xl p-8 text-center">
              <BarChart3 className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-400">详细订单管理请前往订单页面</p>
              <button
                onClick={() => navigate('/merchant-orders')}
                className="mt-4 px-6 py-2.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white rounded-xl text-sm font-bold shadow-md active:scale-95 transition-all"
              >
                前往订单管理
              </button>
            </div>
          </section>
          )}

          {/* Section: Withdrawals */}
          {activeSection === 'withdrawals' && (
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
              <h2 className="text-lg font-bold flex items-center gap-2"><DollarSign className="w-5 h-5 text-amber-500" /> 提现审核</h2>
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
                  <tr><th className="px-6 py-4">申请人</th><th className="px-6 py-4">金额</th><th className="px-6 py-4">状态</th><th className="px-6 py-4">申请时间</th><th className="px-6 py-4 text-right">操作</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {withdrawals.map((row, i) => (
                    <tr key={row.id || i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4 font-bold">{row.user_name}</td>
                      <td className="px-6 py-4 font-bold text-sky-600">¥{row.amount.toFixed(2)}</td>
                      <td className="px-6 py-4">{statusBadge(row.status)}</td>
                      <td className="px-6 py-4 text-slate-400 text-xs">{new Date(row.created_at).toLocaleString('zh-CN')}</td>
                      <td className="px-6 py-4 text-right space-x-2">
                        {row.status === 'pending' && (
                          <>
                            <button onClick={() => handleWithdrawalReview(row.id, 'approve')} className="bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-xs font-bold shadow-sm hover:bg-emerald-600 active:scale-95 transition-all">通过</button>
                            <button onClick={() => handleWithdrawalReview(row.id, 'reject')} className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg text-xs font-bold hover:bg-slate-200 active:scale-95 transition-all">驳回</button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              )}
            </div>
          </section>
          )}

          {/* Section: Users */}
          {activeSection === 'users' && (
          <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
              <h2 className="text-lg font-bold flex items-center gap-2"><Users className="w-5 h-5 text-violet-500" /> 用户管理</h2>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="搜索用户..."
                  value={searchUser}
                  onChange={e => { setSearchUser(e.target.value); setUserPage(1); }}
                  className="pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 w-48"
                />
                {searchUser && (
                  <button onClick={() => { setSearchUser(''); setUserPage(1); }} className="absolute right-3 top-1/2 -translate-y-1/2">
                    <X className="w-3.5 h-3.5 text-slate-400" />
                  </button>
                )}
              </div>
            </div>
            <div className="overflow-x-auto">
              {userStatus === 'loading' ? (
                <div className="p-8"><Loading text="加载用户列表..." /></div>
              ) : userStatus === 'error' ? (
                <div className="p-8"><ErrorBlock message={userError} onRetry={userRefetch} /></div>
              ) : (userData?.items?.length || 0) === 0 ? (
                <div className="p-8"><Empty text={searchUser ? '未找到匹配用户' : '暂无用户'} icon="👤" /></div>
              ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-50 text-[10px] text-slate-500 uppercase tracking-widest font-bold">
                  <tr><th className="px-6 py-4">用户</th><th className="px-6 py-4">用户名</th><th className="px-6 py-4">角色</th><th className="px-6 py-4">手机</th><th className="px-6 py-4">公司</th><th className="px-6 py-4">注册时间</th><th className="px-6 py-4 text-right">操作</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                  {(userData?.items || []).map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center text-white text-xs font-bold">
                            {u.name[0] || '?'}
                          </div>
                          <span className="font-bold">{u.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-slate-500">{u.username}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${roleColor(u.role)}`}>
                          {u.role === 'admin' ? '管理员' : u.role === 'promoter' ? '推广员' : '用户'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-slate-500">{u.phone || '-'}</td>
                      <td className="px-6 py-4 text-slate-500 text-xs">{u.company || '-'}</td>
                      <td className="px-6 py-4 text-xs text-slate-400">{new Date(u.created_at).toLocaleDateString('zh-CN')}</td>
                      <td className="px-6 py-4 text-right">
                        <div className="relative inline-block">
                          <select
                            value={u.role}
                            disabled={userRoleUpdating === u.id}
                            onChange={e => handleRoleChange(u.id, e.target.value)}
                            className="appearance-none bg-slate-100 text-xs font-bold px-3 py-1.5 rounded-lg cursor-pointer hover:bg-slate-200 disabled:opacity-50 border border-slate-200 outline-none"
                          >
                            <option value="user">用户</option>
                            <option value="promoter">推广员</option>
                            <option value="admin">管理员</option>
                          </select>
                          {userRoleUpdating === u.id && (
                            <Loader2 className="w-3 h-3 animate-spin absolute right-2 top-1/2 -translate-y-1/2 text-sky-500" />
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              )}
              {/* 分页控件 */}
              {userData && userTotal > USER_PAGE_SIZE && (
                <div className="px-6 py-4 border-t border-slate-200 flex items-center justify-between">
                  <span className="text-sm text-slate-500">
                    共 {userTotal} 条，第 {userData.page}/{Math.ceil(userTotal / USER_PAGE_SIZE)} 页
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      disabled={userData.page <= 1}
                      onClick={() => setUserPage(p => Math.max(1, p - 1))}
                      className="px-3 py-1.5 text-sm font-bold rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      上一页
                    </button>
                    <button
                      disabled={userData.page >= Math.ceil(userTotal / USER_PAGE_SIZE)}
                      onClick={() => setUserPage(p => p + 1)}
                      className="px-3 py-1.5 text-sm font-bold rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      下一页
                    </button>
                  </div>
                </div>
              )}
            </div>
          </section>
          )}

          {/* Section: Finance */}
          {activeSection === 'finance' && (
          <section className="space-y-6">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <h2 className="text-lg font-bold mb-6 flex items-center gap-2"><CreditCard className="w-5 h-5 text-emerald-500" /> 资金概览</h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                <div className="bg-gradient-to-br from-sky-50 to-blue-50 rounded-2xl p-6 border border-sky-100">
                  <p className="text-xs text-slate-500 mb-1">总交易额</p>
                  <p className="text-3xl font-extrabold text-sky-600 font-manrope">¥{((dashboard?.total_revenue || 0)).toLocaleString(undefined, {minimumFractionDigits: 2})}</p>
                </div>
                <div className="bg-gradient-to-br from-emerald-50 to-teal-50 rounded-2xl p-6 border border-emerald-100">
                  <p className="text-xs text-slate-500 mb-1">订单总量</p>
                  <p className="text-3xl font-extrabold text-emerald-600 font-manrope">{dashboard?.total_orders || 0}</p>
                </div>
                <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 border border-amber-100">
                  <p className="text-xs text-slate-500 mb-1">今日订单</p>
                  <p className="text-3xl font-extrabold text-amber-600 font-manrope">{dashboard?.today_orders || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
              <h3 className="font-bold mb-4">待处理事项</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-4 bg-amber-50 rounded-xl border border-amber-100">
                  <div className="flex items-center gap-3">
                    <Clock className="w-5 h-5 text-amber-600" />
                    <span className="text-sm text-slate-700">待审核产品</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-lg text-amber-600">{dashboard?.pending_review_products || 0}</span>
                    <button onClick={() => setActiveSection('products')} className="text-xs text-sky-600 font-medium">处理</button>
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 bg-rose-50 rounded-xl border border-rose-100">
                  <div className="flex items-center gap-3">
                    <DollarSign className="w-5 h-5 text-rose-600" />
                    <span className="text-sm text-slate-700">待处理提现</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-lg text-rose-600">{dashboard?.pending_withdrawals || 0}</span>
                    <button onClick={() => setActiveSection('withdrawals')} className="text-xs text-sky-600 font-medium">处理</button>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pb-12">
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">用户总数</h4>
                <p className="text-2xl font-bold">{dashboard?.total_users || 0}</p>
              </div>
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">产品总数</h4>
                <p className="text-2xl font-bold">{dashboard?.total_products || 0}</p>
              </div>
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">平均订单价</h4>
                <p className="text-2xl font-bold">
                  ¥{dashboard && dashboard.total_orders > 0
                    ? (dashboard.total_revenue / dashboard.total_orders).toFixed(2)
                    : '0.00'}
                </p>
              </div>
            </div>
          </section>
          )}
        </main>
      </div>
    </div>
  );
}
