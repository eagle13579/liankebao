import { useNavigate, Link } from 'react-router-dom';
import {
  Search, Home, Grid, Zap, User, Star, ArrowRight, UserPlus, FileText, Share2, Users,
  GraduationCap, ChevronRight, LayoutDashboard, ShoppingBag, Receipt, CheckCircle2,
  Bell, Package, TrendingUp, MessageCircle, Store, Building2, Wallet, Settings,
  Sparkles, Database, BarChart3, Target, Globe, HelpCircle, LogOut, Clock, X, Copy, Link, Image, Crown
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { ProductItem } from '../types';
import { Loading, ErrorBlock, Empty, useApi } from '../components/StatusComponents';
import BorderGlow from '../components/BorderGlow';
import SpotlightCard from '../components/SpotlightCard';

// ==============================
//  Shared Bottom Nav
// ==============================
function BottomNav({ active }: { active: string }) {
  const navigate = useNavigate();
  const items = [
    { id: 'home', icon: Home, label: '首页', path: '/home' },
    { id: 'product', icon: ShoppingBag, label: '产品池', path: '/product-pool' },
    { id: 'contacts', icon: Users, label: '人脉', path: '/contacts' },
    { id: 'profile', icon: User, label: '我的', path: '/promotion-center' },
  ];

  return (
    <nav className="fixed bottom-0 w-full h-16 bg-white/90 backdrop-blur-lg border-t border-slate-100 flex justify-around items-center px-2 pb-safe shadow-[0_-2px_20px_rgba(0,0,0,0.04)]">
      {items.map((item) => {
        const isActive = active === item.id;
        const Icon = item.icon;
        return (
          <button
            key={item.id}
            onClick={() => navigate(item.path, { state: { transition: 'none' } })}
            className={`flex flex-col items-center gap-0.5 px-3 py-1 relative ${
              isActive ? 'text-sky-600' : 'text-slate-400'
            }`}
          >
            {isActive && (
              <div className="absolute -top-1 w-8 h-1 bg-gradient-to-r from-sky-500 to-blue-500 rounded-full" />
            )}
            <Icon className={`w-5 h-5 ${isActive ? 'drop-shadow-sm' : ''}`} />
            <span className={`text-[9px] font-bold tracking-wide ${
              isActive ? 'text-sky-600' : 'text-slate-400'
            }`}>
              {item.label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

// ==============================
//  LiankebaoHomepage
// ==============================
export function LiankebaoHomepage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [currentBanner, setCurrentBanner] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const { data: products, status, error, refetch } = useApi(
    () => api.get<{total: number; items: ProductItem[]}>('/api/products' + (search ? `?search=${search}` : '')).then(r => r.data?.items || []),
    [search]
  );

  const displayProducts = (products || []).slice(0, 4);

  // Fetch unread notification count
  const fetchUnread = async () => {
    try {
      const res = await api.get<{count: number}>('/api/notifications/unread-count');
      if (res.data) setUnreadCount(res.data.count || 0);
    } catch {}
  };
  useEffect(() => {
    fetchUnread();
    const interval = setInterval(fetchUnread, 30000);
    return () => clearInterval(interval);
  }, []);

  // Carousel with product-relevant background images
  const banners = [
    {
      tag: '精选推荐', title: '精选大健康 · 企业家必备', desc: '优质品牌直供，专业团队严选',
      btnText: '立即查看', link: '/product-pool',
      bgImage: 'https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?w=800&h=400&fit=crop',
    },
    {
      tag: 'VIP会员', title: '开通会员享超值权益', desc: '推广佣金翻倍 · 优先审核 · 专属客服',
      btnText: '了解详情', link: '/membership',
      bgImage: 'https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=800&h=400&fit=crop',
    },
    {
      tag: 'AI赋能', title: 'AI数字名片 · 智能获客', desc: '一键生成电子画册，精准触达潜在客户',
      btnText: '立即体验', link: 'http://localhost:8003', external: true,
      bgImage: 'https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=800&h=400&fit=crop',
    },
    {
      tag: 'GEO诊断', title: 'AI诊断你的线上曝光', desc: '分析品牌在AI搜索引擎中的可见度，精准优化',
      btnText: '开始诊断', link: 'http://localhost:5061', external: true,
      bgImage: 'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=800&h=400&fit=crop',
    },
  ];

  // Auto-play
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentBanner(prev => (prev + 1) % banners.length);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  const featureCards = [
    { icon: Database, label: '产品池', desc: '精选优质货源', color: 'from-sky-500 to-blue-600', bg: 'bg-sky-50', path: '/product-pool' },
    { icon: TrendingUp, label: '推广中心', desc: '赚取高额分润', color: 'from-emerald-500 to-teal-600', bg: 'bg-emerald-50', path: '/promotion-center' },
    { icon: Users, label: '人脉管理', desc: '高效触达客户', color: 'from-violet-500 to-purple-600', bg: 'bg-violet-50', path: '/contacts' },
    { icon: Receipt, label: '我的订单', desc: '订单物流追踪', color: 'from-amber-500 to-orange-600', bg: 'bg-amber-50', path: '/my-orders' },
    { icon: Target, label: '信任对接', desc: '精准匹配可信商机', color: 'from-rose-500 to-pink-600', bg: 'bg-rose-50', path: '/supply-demand' },
    { icon: BarChart3, label: '数据洞察', desc: '生意增长分析', color: 'from-cyan-500 to-teal-600', bg: 'bg-cyan-50', path: '#data' },
  ];

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/50 via-white to-white font-sans pb-20">
      {/* Top Navigation Bar */}
      <header className="fixed top-0 w-full z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 px-4 h-16">
        <div className="flex items-center justify-between h-full max-w-3xl mx-auto">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-xl brand-gradient flex items-center justify-center shadow-md shadow-sky-500/20">
              <HandshakeIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-manrope text-xl font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent leading-tight">
                链客宝
              </h1>
              <p className="text-[10px] text-slate-400 font-medium tracking-wider -mt-0.5">企业信任关系网，对接更快更准</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button onClick={() => navigate('/notifications')} className="relative w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all border border-slate-100">
              <Bell className="w-4.5 h-4.5" />
              {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-gradient-to-br from-rose-500 to-rose-600 rounded-full text-white text-[8px] font-bold flex items-center justify-center shadow-sm">{unreadCount > 99 ? '99+' : unreadCount}</span>
              )}
            </button>
            <button onClick={() => navigate('/promotion-center')} className="w-9 h-9 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center text-white shadow-md shadow-sky-500/20 active:scale-90 transition-all border-2 border-white">
              <User className="w-4.5 h-4.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="pt-16 max-w-3xl mx-auto w-full">
        {/* Search Bar */}
        <div className="px-4 pt-4 pb-2">
          <div className="relative group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-300 group-focus-within:text-sky-500 transition-colors" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-white/80 border border-slate-200 rounded-2xl py-3.5 pl-11 pr-4 text-sm text-slate-600 placeholder:text-slate-400 focus:ring-2 focus:ring-sky-500/15 focus:border-sky-500 outline-none transition-all shadow-sm"
              placeholder="搜产品、搜企业、搜品类..."
            />
          </div>
        </div>

        {/* Feature Cards Grid */}
        <div className="px-4 py-3">
          <div className="grid grid-cols-4 gap-3">
            {featureCards.map((card, i) => {
              const Icon = card.icon;
              return (
                <button
                  key={i}
                  onClick={() => {
                    if (card.path === '#data') {
                      alert('数据洞察功能开发中');
                    } else {
                      navigate(card.path, { state: { transition: 'push' } });
                    }
                  }}
                  className="group flex flex-col items-center gap-2 active:scale-95 transition-transform"
                >
                  <div className={`w-14 h-14 rounded-2xl ${card.bg} flex items-center justify-center border border-white/60 shadow-sm group-hover:shadow-md transition-all`}>
                    <Icon className="w-6 h-6 text-slate-700" />
                  </div>
                  <div className="text-center">
                    <span className="text-xs font-bold text-slate-700 block leading-tight">{card.label}</span>
                    <span className="text-[8px] text-slate-400">{card.desc}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Banner Carousel - Horizontal Sliding */}
        <div className="px-4 py-3">
          <BorderGlow
            glowColor="190 80 80"
            backgroundColor="#ffffff"
            glowIntensity={0.6}
            borderRadius={16}
            glowRadius={12}
          >
          <div className="relative w-full aspect-[21/9] rounded-2xl overflow-hidden shadow-lg">
            {/* Sliding Track */}
            <div
              className="flex transition-transform duration-500 ease-in-out h-full"
              style={{ transform: `translateX(-${currentBanner * 100}%)` }}
            >
              {banners.map((b, i) => (
                <div key={i} className="relative w-full h-full shrink-0">
                  {/* Background Image */}
                  <img
                    src={b.bgImage}
                    alt=""
                    className="absolute inset-0 w-full h-full object-cover"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                    }}
                  />
                  {/* Dark overlay for text readability */}
                  <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-black/30 to-transparent" />
                  <div className="absolute inset-0 flex flex-col justify-center px-6">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="bg-white/20 backdrop-blur-sm text-white text-[10px] px-2 py-0.5 rounded-full font-bold border border-white/20">{b.tag}</span>
                    </div>
                    <h2 className="text-white font-manrope font-bold text-xl leading-tight">{b.title}</h2>
                    <p className="text-white/70 text-xs mt-1">{b.desc}</p>
                    <button
                      onClick={() => {
                        if (!b.link || b.link === '#') return;
                        if (b.external) window.open(b.link, '_blank');
                        else navigate(b.link, { state: { transition: 'push' } });
                      }}
                      className="mt-3 w-fit bg-white/20 backdrop-blur-sm text-white text-xs font-bold px-4 py-2 rounded-full border border-white/20 hover:bg-white/30 active:scale-95 transition-all flex items-center gap-1.5"
                    >
                      {b.btnText} <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {/* Dots */}
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 z-10">
              {banners.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrentBanner(i)}
                  className={`transition-all duration-300 rounded-full ${
                    i === currentBanner
                      ? 'w-5 h-1.5 bg-white shadow-sm'
                      : 'w-1.5 h-1.5 bg-white/40 hover:bg-white/60'
                  }`}
                />
              ))}
            </div>
            {/* Auto-play indicator */}
            <div className="absolute top-3 right-3 z-10 bg-black/20 backdrop-blur-sm text-white text-[9px] font-bold px-2 py-0.5 rounded-full">
              {currentBanner + 1}/{banners.length}
            </div>
            </div>
          </BorderGlow>
        </div>

        {/* Quick Tools */}
        <div className="px-4 py-2">
          <div className="flex items-center gap-3 overflow-x-auto no-scrollbar py-1">
            {[
              { icon: Star, label: 'AI名片', color: 'text-amber-500', bg: 'bg-amber-50', link: 'http://localhost:8003', external: true },
              { icon: Zap, label: 'GEO', color: 'text-violet-500', bg: 'bg-violet-50', link: 'http://localhost:5061', external: true },
              { icon: Target, label: 'AI员工', color: 'text-sky-500', bg: 'bg-sky-50', link: 'http://localhost:5020', external: true },
              { icon: Globe, label: '信任对接', color: 'text-emerald-500', bg: 'bg-emerald-50', link: '/supply-demand', external: false },
              { icon: BarChart3, label: '数据洞察', color: 'text-blue-500', bg: 'bg-blue-50', link: '#', external: false },
              { icon: Grid, label: '全部产品', color: 'text-slate-500', bg: 'bg-slate-50', link: '/product-pool', external: false },
            ].map((item, i) => {
              const Icon = item.icon;
              return (
                <div key={i} onClick={() => {
                  if (item.external) {
                    window.open(item.link, '_blank');
                  } else if (item.link !== '#') {
                    navigate(item.link, { state: { transition: 'push' } });
                  }
                }} className="flex items-center gap-2 px-4 py-2.5 bg-white rounded-xl border border-slate-100 shadow-sm cursor-pointer active:scale-95 transition-all shrink-0">
                  <div className={`w-8 h-8 ${item.bg} rounded-lg flex items-center justify-center`}>
                    <Icon className={`w-4 h-4 ${item.color}`} />
                  </div>
                  <span className="text-xs font-bold text-slate-700 whitespace-nowrap">{item.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Recommended Products Header */}
        <div className="px-4 pt-4 pb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-1 h-5 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full" />
            <h2 className="font-manrope text-base font-extrabold text-slate-800">为您推荐</h2>
            <Sparkles className="w-4 h-4 text-amber-400" />
          </div>
          <button
            onClick={() => navigate('/product-pool', { state: { transition: 'push' } })}
            className="text-xs text-sky-600 font-bold flex items-center gap-0.5 hover:underline"
          >
            更多产品 <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Products Grid */}
        <div className="px-4 pb-6">
          {status === 'loading' ? (
            <div className="grid grid-cols-2 gap-4">
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="bg-white rounded-2xl overflow-hidden border border-slate-100">
                  <div className="aspect-square skeleton" />
                  <div className="p-3 space-y-2">
                    <div className="h-4 skeleton rounded w-3/4" />
                    <div className="h-5 skeleton rounded w-1/2" />
                    <div className="h-8 skeleton rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : status === 'error' ? (
            <ErrorBlock message={error} onRetry={refetch} />
          ) : !products || products.length === 0 ? (
            <Empty text="暂无推荐产品" />
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {displayProducts.map((item, i) => (
                <SpotlightCard
                  key={i}
                  className="cursor-pointer"
                  spotlightColor="rgba(56, 189, 248, 0.12)"
                >
                <div
                  onClick={() => navigate('/product-detail', { state: { transition: 'push', productId: item.id } })}
                  className="bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-sm hover:shadow-md hover:border-sky-200 active:shadow-sm transition-all card-hover group"
                >
                  <div className="aspect-square p-2 relative">
                    <div className="absolute top-3 left-3 z-10 bg-gradient-to-r from-sky-500 to-blue-600 text-white text-[8px] font-bold px-2 py-0.5 rounded-full shadow-sm">
                      推荐
                    </div>
                    <img
                      src={item.images || 'https://via.placeholder.com/200'}
                      className="w-full h-full object-cover rounded-xl bg-slate-50"
                      alt={item.name}
                    />
                  </div>
                  <div className="px-3 pb-3 space-y-2">
                    <h3 className="text-sm font-bold text-slate-800 line-clamp-2 leading-tight">{item.name}</h3>
                    <div className="flex items-center justify-between">
                      <span className="font-manrope text-lg font-extrabold text-sky-600">¥{item.price.toFixed(2)}</span>
                    </div>
                    <div className="bg-gradient-to-r from-emerald-50 to-emerald-50/50 border border-emerald-100/50 rounded-lg px-2.5 py-1 flex items-center gap-1">
                      <TrendingUp className="w-3 h-3 text-emerald-600" />
                      <span className="text-[10px] font-bold text-emerald-700">推广赚 ¥{item.earn_per_share.toFixed(2)}</span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate('/product-detail', { state: { transition: 'push', productId: item.id } }); }}
                      className="w-full py-2.5 border-2 border-sky-200 text-sky-600 rounded-xl font-bold text-xs hover:bg-sky-500 hover:text-white hover:border-sky-500 active:scale-[0.97] transition-all mb-0.5"
                    >
                      查看详情
                    </button>
                  </div>
                </div>
                </SpotlightCard>
              ))}
            </div>
          )}
        </div>
      </main>

      <BottomNav active="home" />

      <style>{`
        .handshake-icon { display: inline-block; }
      `}</style>
    </div>
  );
}

// Inline Handshake icon to avoid import conflict
function HandshakeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 17a4 4 0 0 1-8 0V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2Z" />
      <path d="M16.7 13H19a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H7" />
      <path d="M 7 17h.01" />
      <path d="m11 8 2.3-2.3a2.4 2.4 0 0 1 3.4.9L18 8" />
    </svg>
  );
}

// ==============================
//  ProductPool
// ==============================
export function ProductPool() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('全部');

  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (category && category !== '全部') params.set('category', category);
  const qs = params.toString();

  const { data: products, status, error, refetch } = useApi(
    () => api.get<{total: number; items: ProductItem[]}>('/api/products' + (qs ? `?${qs}` : '')).then(r => r.data?.items || []),
    [search, category]
  );

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-20">
      <header className="fixed top-0 w-full z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex justify-between items-center px-4 h-16">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg brand-gradient flex items-center justify-center">
            <Grid className="w-4 h-4 text-white" />
          </div>
          <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">产品池</h1>
        </div>
        <button className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all border border-slate-100">
          <Search className="w-4.5 h-4.5" />
        </button>
      </header>

      <main className="pt-16 pb-12 max-w-3xl mx-auto w-full">
        <div className="px-4 pt-4 pb-2">
          <div className="relative">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-300" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-white/80 border border-slate-200 rounded-xl py-3 pl-10 pr-4 text-sm text-slate-600 placeholder:text-slate-400 focus:ring-2 focus:ring-sky-500/15 focus:border-sky-500 outline-none transition-all shadow-sm"
              placeholder="搜产品、搜企业、搜品类"
            />
          </div>
        </div>

        {/* Category Tabs - Dynamically from API */}
        <div className="flex overflow-x-auto no-scrollbar gap-2 px-4 py-3">
          {['全部', '大健康', '企业服务', '教育培训', 'SaaS硬件', '食品/大健康', '企业家服务'].map((cat, i) => (
            <span
              key={i}
              onClick={() => setCategory(cat)}
              className={`text-xs font-bold whitespace-nowrap px-4 py-1.5 rounded-full cursor-pointer transition-all shrink-0 border ${
                cat === category
                  ? 'bg-sky-500 text-white border-sky-500 shadow-sm'
                  : 'bg-white text-slate-500 border-slate-200 hover:border-sky-200 hover:text-sky-600'
              }`}
            >
              {cat.replace('/大健康', '')}
            </span>
          ))}
        </div>

        <div className="px-4 pt-4">
          {status === 'loading' ? (
            <div className="grid grid-cols-2 gap-3">
              {[1,2,3,4].map(i => (
                <div key={i} className="bg-white rounded-xl border border-slate-100 overflow-hidden">
                  <div className="aspect-square skeleton" />
                  <div className="p-3 space-y-2">
                    <div className="h-3 skeleton rounded w-3/4" />
                    <div className="h-4 skeleton rounded w-1/2" />
                    <div className="h-7 skeleton rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : status === 'error' ? (
            <ErrorBlock message={error} onRetry={refetch} />
          ) : !products || products.length === 0 ? (
            <Empty text="暂无产品" />
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {products.map((item, i) => (
                <div
                  key={item.id || i}
                  onClick={() => navigate('/product-detail', { state: { transition: 'push', productId: item.id } })}
                  className="bg-white rounded-xl border border-slate-100 overflow-hidden shadow-sm hover:shadow-md transition-all card-hover cursor-pointer"
                >
                  <img src={item.images || 'https://via.placeholder.com/200'} className="w-full aspect-square object-cover bg-slate-50" alt={item.name} />
                  <div className="p-3 space-y-2">
                    <h3 className="text-xs font-bold line-clamp-2 h-8 text-slate-800">{item.name}</h3>
                    <p className="text-sky-600 font-manrope font-bold">¥{item.price.toFixed(2)}</p>
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate('/product-detail', { state: { transition: 'push', productId: item.id } }); }}
                      className="w-full py-1.5 border border-sky-200 text-sky-600 rounded-full text-[10px] font-bold hover:bg-sky-500 hover:text-white hover:border-sky-500 active:scale-95 transition-all"
                    >
                      查看详情
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      <BottomNav active="product" />
    </div>
  );
}

// ==============================
//  PromotionCenter
// ==============================
export function PromotionCenter() {
  const navigate = useNavigate();
  const [showEbrochure, setShowEbrochure] = useState(false);
  const [showPromotionModal, setShowPromotionModal] = useState(false);
  const [promotionProduct, setPromotionProduct] = useState<{title: string; price: string; earn: string} | null>(null);
  const [promotionToast, setPromotionToast] = useState('');

  const quickActions = [
    { label: '我的订单', icon: FileText, path: '/my-orders' },
    { label: '分享海报', icon: Share2, path: '#', isSharePoster: true },
    { label: '我的下级', icon: Users, path: '/subordinates' },
    { label: '推广教程', icon: GraduationCap, path: '/promotion-tutorial' },
    { label: '合伙人政策', icon: FileText, path: '/partner-policy' },
    { label: '会员中心', icon: Crown, path: '/membership' },
    { label: '我的产品', icon: Package, path: '/my-products' },
    { label: '上架新品', icon: ShoppingBag, path: '/add-product' },
  ];

  const hotProducts = [
    { title: '旗舰版智能健康手表 S3', price: '1,299', earn: '129.9', img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuApC5VJUCEfOGxW-cKut2u8z6NO-kav_mBGu69O34D8YpFcDrbZ8dwSI-LSFCGAbxW_gi1bUwGAtLONndumKY3QM3_GxZgfhh83TfxCMWo0p9YXUwFQSPZOsrNxTKR5xcBn5J2kurh3IlzHyAIl-xmcyeZI9Z88Nf8Ol6P9OqNVQF54URZODLp_oEsz0TlvNJ6z4rFFehdANpM_c9obgqNdYxMpfbcr9YKeBu0HaDFTeUCtb4TAKmEt4ageyc0Dl4KUV1XiSZgSpGXf' },
    { title: '高端商务茶礼套装·臻选', price: '688', earn: '68.8', img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuD6b6MOwAIPbCsj8tSABTYTMoMBRzPMfEdmy0WTZcSMEPQ25XlqFrBc8crM9_SM_qrFod0Y30mKFCQhCFsASq_hOxYhn83IVrWqMLzV2t0c_Xx3Y88etZQEz3xV97ldEr7VQf10DzqHbbjlCBLzBLlmWAXQlQR5u8nXjFjwG0_OkkCRiCsZQbMbLg2QvGjDBV4gXKx6EJBbt7z-gFcCkbVg_i_otOF3B2H6IVtAK8wNFKBrGTuGoq3qZt0MJc4z3vRHqiVfjCAp' },
    { title: '企业数字化管理平台 Pro', price: '9,800', earn: '980', img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuC3OG2SYpQhGeQMKADmTn9gjwN3T8C_LfQADWYWLPBs-_PFh9K6gh8tRq0E4mqMZDV8iKkG5hJzXN4bRb7G7JqFjQ7nt1SUXL64jljBDcrt4gQIV3j4NPEAVz9vZ2GUFJ3pb7nGk2dPN6sUqRnlQIA9vMEHLK7k9J6cE_GQhMULfjTkEKGx3d2v0f0F7aX2ftMIBsO6kQvhQtxb5zHX44xMT8vkfInMK2bKqQ9SxdEfG5LxV88SgAEGQ0CjYOmHwwxjWl__UXCZ' },
  ];

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-24">
      <header className="fixed top-0 w-full z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex justify-between items-center px-4 h-16">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg brand-gradient flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-white" />
          </div>
          <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">推广中心</h1>
        </div>
        <button className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all border border-slate-100">
          <Settings className="w-4.5 h-4.5" />
        </button>
      </header>

      <main className="pt-16 max-w-3xl mx-auto w-full p-4 space-y-6">
        {/* User Profile Card */}
        <section className="flex items-center gap-4 bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
          <div className="relative">
            <img
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuBuKyvslj8Sf-I9tZohEQpeosSpcblKwhdWiqVlMXd0qsagxqS4K6yznJr7Opusanym978mU3oHeQUKk9KSN_Of36-XIjq9Y9jdQUappQILE_q0z7iom3Ahiz1wzkvqaqkYjMhGoCGVxUxq9Gvr1PcW1YCyEk4OmWwG2jS0pEzlAhGEEDg5T0JAQg9xzAEfHlJU6cR-CVD_4sOVUxu8zIbsWvmm8apd0ipCCVEAtq5Uw_ZClY1oJJ5f0yMpmpeN7mNo7CachYe_5otw"
              className="w-16 h-16 rounded-full border-2 border-sky-500 object-cover"
            />
            <div className="absolute -bottom-1 -right-1 bg-gradient-to-br from-sky-500 to-blue-600 rounded-full p-1 border-2 border-white">
              <CheckCircle2 className="w-3 h-3 text-white" />
            </div>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-extrabold text-slate-800">林峰</h2>
              <span className="bg-gradient-to-r from-amber-400 to-amber-600 text-[10px] text-white px-2 py-0.5 rounded-full font-bold shadow-sm">铂金会员</span>
            </div>
            <p className="text-xs text-slate-400 mt-1">会员到期日：2024-12-31</p>
          </div>
        </section>

        {/* Revenue Card */}
        <section className="bg-white rounded-2xl border-l-4 border-sky-500 p-5 shadow-sm border border-slate-100">
          <div className="flex justify-between items-start mb-6">
            <div>
              <p className="text-xs text-slate-400 font-medium">今日收入 (元)</p>
              <p className="text-2xl font-extrabold text-sky-600 mt-1">+46.80</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-400 font-medium">可提现余额</p>
              <p className="text-lg font-extrabold text-slate-900 mt-1">¥ 1,280.50</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 mb-6">
            <div>
              <p className="text-xs text-slate-400">本月累计</p>
              <p className="font-bold text-slate-800">¥ 3,420.00</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-400">累计总收益</p>
              <p className="font-bold text-slate-800">¥ 12,850.20</p>
            </div>
          </div>
          <button className="w-full bg-gradient-to-r from-sky-500 to-blue-600 text-white py-3 rounded-xl font-bold active:scale-[0.98] transition-transform shadow-md shadow-sky-500/20">
            立即提现
          </button>
        </section>

        {/* Quick Actions */}
        <section className="grid grid-cols-5 gap-3">
          {quickActions.map((item, i) => {
            const Icon = item.icon;
            return (
              <div
                key={i}
                onClick={() => {
                  if (item.isSharePoster) {
                    setShowEbrochure(true);
                  } else if (item.path !== '#') {
                    navigate(item.path, { state: { transition: 'push' } });
                  }
                }}
                className="flex flex-col items-center gap-2 cursor-pointer group"
              >
                <div className="w-12 h-12 bg-white rounded-2xl shadow-sm border border-slate-100 flex items-center justify-center text-slate-700 group-hover:border-sky-200 group-hover:text-sky-600 active:scale-90 transition-all">
                  <Icon className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-medium text-slate-600">{item.label}</span>
              </div>
            );
          })}
        </section>

        {/* Hot Products */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-extrabold text-slate-800 flex items-center gap-2">
              <span className="w-1 h-5 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full"></span>
              本月热推产品
            </h3>
            <span
              onClick={() => navigate('/product-pool', { state: { transition: 'push' } })}
              className="text-xs text-sky-600 font-bold flex items-center gap-0.5 cursor-pointer hover:underline"
            >
              更多 <ChevronRight className="w-3.5 h-3.5" />
            </span>
          </div>
          {hotProducts.map((item, i) => (
            <div key={i} className="flex bg-white p-3 rounded-2xl border border-slate-100 gap-3 shadow-sm hover:shadow-md transition-all">
              <div className="w-20 h-20 rounded-xl bg-slate-100 overflow-hidden shrink-0">
                <img src={item.img} className="w-full h-full object-cover" />
              </div>
              <div className="flex-1 flex flex-col justify-between">
                <h4 className="font-bold text-sm line-clamp-1 text-slate-800">{item.title}</h4>
                <div className="flex justify-between items-end">
                  <div>
                    <p className="text-sky-600 font-extrabold text-lg">¥{item.price}</p>
                    <div className="bg-gradient-to-r from-emerald-50 to-emerald-50/50 px-1.5 py-0.5 rounded border border-emerald-100/50">
                      <span className="text-[10px] text-emerald-700 font-bold">分润 ¥{item.earn}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setPromotionProduct(item);
                      setShowPromotionModal(true);
                    }}
                    className="px-4 py-1.5 rounded-full bg-gradient-to-r from-sky-500 to-blue-600 text-white text-xs font-bold active:scale-95 transition-transform shadow-sm"
                  >
                    我要推广
                  </button>
                </div>
              </div>
            </div>
          ))}
        </section>

        {/* E-Brochure Modal */}
        {showEbrochure && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4" onClick={() => setShowEbrochure(false)}>
            <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="relative bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 p-5 text-white">
                <button
                  onClick={() => setShowEbrochure(false)}
                  className="absolute top-3 right-3 w-7 h-7 rounded-full bg-white/20 flex items-center justify-center hover:bg-white/30 transition-all"
                >
                  <X className="w-4 h-4" />
                </button>
                <div className="flex items-center gap-2 mb-1">
                  <Image className="w-5 h-5" />
                  <span className="text-xs font-bold text-white/80">电子画册</span>
                </div>
                <h3 className="text-lg font-extrabold">链客宝精选产品画册</h3>
                <p className="text-xs text-white/70 mt-1">2024 企业供需优选指南</p>
              </div>

              {/* Preview Content */}
              <div className="p-5 space-y-4 max-h-80 overflow-y-auto">
                <div className="bg-sky-50 rounded-xl p-4 border border-sky-100">
                  <h4 className="font-bold text-sky-800 text-sm mb-2">🌿 大健康专区</h4>
                  <p className="text-xs text-sky-600/80">旗舰版智能健康手表 S3 · 高端商务茶礼 · 滋补养生套装</p>
                </div>
                <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-100">
                  <h4 className="font-bold text-emerald-800 text-sm mb-2">💼 企业服务专区</h4>
                  <p className="text-xs text-emerald-600/80">企业数字化管理平台 · 智能办公解决方案 · 企业财税服务</p>
                </div>
                <div className="bg-violet-50 rounded-xl p-4 border border-violet-100">
                  <h4 className="font-bold text-violet-800 text-sm mb-2">🚀 科技产品专区</h4>
                  <p className="text-xs text-violet-600/80">AI智能助手 · 物联网设备 · 数字化转型工具</p>
                </div>
                <div className="bg-amber-50 rounded-xl p-4 border border-amber-100">
                  <h4 className="font-bold text-amber-800 text-sm mb-2">🎓 教育培训专区</h4>
                  <p className="text-xs text-amber-600/80">企业管理课程 · 职业技能培训 · 行业认证考试</p>
                </div>
                <div className="text-center pt-2">
                  <p className="text-[10px] text-slate-400">更多精彩内容即将上线，敬请期待</p>
                </div>
              </div>

              {/* Footer */}
              <div className="px-5 pb-5">
                <button
                  onClick={() => setShowEbrochure(false)}
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold text-sm active:scale-[0.98] transition-transform shadow-md shadow-sky-500/20"
                >
                  我知道了
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Promotion Method Modal */}
        {showPromotionModal && promotionProduct && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4" onClick={() => setShowPromotionModal(false)}>
            <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="px-5 pt-5 pb-3 flex items-center justify-between">
                <h3 className="font-extrabold text-slate-800 text-lg">推广方式</h3>
                <button
                  onClick={() => setShowPromotionModal(false)}
                  className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center hover:bg-slate-200 transition-all"
                >
                  <X className="w-4 h-4 text-slate-500" />
                </button>
              </div>

              {/* Product Info */}
              <div className="px-5 pb-4 border-b border-slate-100">
                <p className="text-sm font-bold text-slate-700">{promotionProduct.title}</p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-sky-600 font-extrabold">¥{promotionProduct.price}</span>
                  <span className="text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-full font-bold">分润 ¥{promotionProduct.earn}</span>
                </div>
              </div>

              {/* Options */}
              <div className="p-5 space-y-3">
                <button
                  onClick={() => {
                    setPromotionToast(`已复制「${promotionProduct.title}」分享链接`);
                    setShowPromotionModal(false);
                    setTimeout(() => setPromotionToast(''), 2500);
                  }}
                  className="w-full flex items-center gap-4 p-4 rounded-xl border border-slate-100 hover:border-sky-200 hover:bg-sky-50 active:scale-[0.98] transition-all group"
                >
                  <div className="w-10 h-10 rounded-xl bg-sky-50 flex items-center justify-center group-hover:bg-sky-100 transition-all">
                    <Link className="w-5 h-5 text-sky-600" />
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-bold text-slate-800">分享链接</p>
                    <p className="text-[10px] text-slate-400">生成专属推广链接发送给客户</p>
                  </div>
                </button>

                <button
                  onClick={() => {
                    setPromotionToast('海报生成中，请稍候...');
                    setShowPromotionModal(false);
                    setTimeout(() => setPromotionToast(''), 2500);
                  }}
                  className="w-full flex items-center gap-4 p-4 rounded-xl border border-slate-100 hover:border-sky-200 hover:bg-sky-50 active:scale-[0.98] transition-all group"
                >
                  <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center group-hover:bg-emerald-100 transition-all">
                    <Image className="w-5 h-5 text-emerald-600" />
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-bold text-slate-800">生成海报</p>
                    <p className="text-[10px] text-slate-400">生成精美的推广海报图片</p>
                  </div>
                </button>

                <button
                  onClick={() => {
                    const texts = [
                      '🔥 强烈推荐！这款产品真的太棒了，性价比超高！',
                      '💪 自用推荐，品质有保障，赶紧入手吧！',
                      '🎯 分享一款好产品，需要的朋友千万别错过～',
                    ];
                    navigator.clipboard.writeText(texts[Math.floor(Math.random() * texts.length)]);
                    setPromotionToast('推广语已复制到剪贴板');
                    setShowPromotionModal(false);
                    setTimeout(() => setPromotionToast(''), 2500);
                  }}
                  className="w-full flex items-center gap-4 p-4 rounded-xl border border-slate-100 hover:border-sky-200 hover:bg-sky-50 active:scale-[0.98] transition-all group"
                >
                  <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center group-hover:bg-amber-100 transition-all">
                    <Copy className="w-5 h-5 text-amber-600" />
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-bold text-slate-800">复制推广语</p>
                    <p className="text-[10px] text-slate-400">一键复制推广文案发送给客户</p>
                  </div>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Toast Notification */}
        {promotionToast && (
          <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[60] bg-slate-800 text-white text-sm font-bold px-5 py-3 rounded-full shadow-lg animate-[fadeIn_0.2s_ease-out]">
            {promotionToast}
          </div>
        )}
      </main>

      <BottomNav active="profile" />
    </div>
  );
}
