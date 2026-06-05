import { useNavigate } from 'react-router-dom';
import {
  Search, Home, Grid, User, ChevronRight, Bell, ShoppingBag, Receipt, TrendingUp,
  Users, Database, BarChart3, Target, Globe, FileText, HelpCircle, Package,
  Settings, Crown, GraduationCap, Share2, CheckCircle2, X, Image, Copy, Link,
  TableProperties, FolderKanban, HandCoins, Shapes, Sparkles, QrCode
} from 'lucide-react';
import { useState, useEffect, memo } from 'react';
import { api } from '../api/client';
import { ProductItem } from '../types';
import { useApi, ErrorBlock, Empty } from '../components/StatusComponents';

// ==============================
//  Shared Bottom Nav
// ==============================
function BottomNav({ active }: { active: string }) {
  const navigate = useNavigate();
  const items = [
    { id: 'home', icon: Home, label: '首页', path: '/home' },
    { id: 'product', icon: ShoppingBag, label: '产品池', path: '/product-pool' },
    { id: 'business-card', icon: QrCode, label: 'AI名片', path: '/business-card' },
    { id: 'membership', icon: Crown, label: '会员中心', path: '/membership' },
    { id: 'profile', icon: User, label: '我的', path: '/profile' },
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
//  LiankebaoHomepage — 3主按钮模式（深色主题）
// ==============================

export const LiankebaoHomepage = memo(function LiankebaoHomepage() {
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const [showMore, setShowMore] = useState(false);
  const [animatingBtn, setAnimatingBtn] = useState<string | null>(null);

  // 从 /api/home/mission-control 获取3个核心功能的状态
  const [missionStatus, setMissionStatus] = useState<{
    publish_task?: any; invite_partner?: any; track_split?: any;
  }>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get<any>('/api/home/mission-control');
        if (!cancelled && res.data?.data) {
          setMissionStatus(res.data.data);
        }
      } catch {
        // fallback: show static labels if API unavailable
        setMissionStatus({
          publish_task: { label: '发布信息', icon: 'flame', description: '创建分销/合作任务', status: 'active', badge: null, action_hint: '发布新产品', sort_order: 1 },
          invite_partner: { label: '邀请伙伴', icon: 'handshake', description: '发送邀请链接/二维码', status: 'active', badge: null, action_hint: '立即邀请', sort_order: 2 },
          track_split: { label: '追踪分账', icon: 'chart', description: '查看收益/佣金/结算', status: 'active', badge: null, action_hint: '查看详情', sort_order: 3 },
        });
      }
    })();
    return () => { cancelled = true; };
  }, []);

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

  const missionButtons = [
    {
      id: 'publish_task', icon: '🔥',
      label: missionStatus.publish_task?.label || '发布信息',
      desc: missionStatus.publish_task?.description || '创建分销/合作任务',
      hint: missionStatus.publish_task?.action_hint || '发布新产品',
      badge: missionStatus.publish_task?.badge,
      gradient: 'from-orange-500 via-red-500 to-pink-600',
      shadow: 'shadow-orange-500/30',
      path: '/add-product',
    },
    {
      id: 'invite_partner', icon: '🤝',
      label: missionStatus.invite_partner?.label || '邀请伙伴',
      desc: missionStatus.invite_partner?.description || '发送邀请链接/二维码',
      hint: missionStatus.invite_partner?.action_hint || '立即邀请',
      badge: missionStatus.invite_partner?.badge,
      gradient: 'from-emerald-500 via-teal-500 to-green-600',
      shadow: 'shadow-emerald-500/30',
      path: '/contacts',
    },
    {
      id: 'track_split', icon: '📊',
      label: missionStatus.track_split?.label || '追踪分账',
      desc: missionStatus.track_split?.description || '查看收益/佣金/结算',
      hint: missionStatus.track_split?.action_hint || '累计收益 ¥0.00',
      badge: missionStatus.track_split?.badge,
      gradient: 'from-violet-500 via-purple-500 to-indigo-600',
      shadow: 'shadow-violet-500/30',
      path: '/promotion-center',
    },
  ];

  const handleMissionClick = (btn: typeof missionButtons[0]) => {
    setAnimatingBtn(btn.id);
    setTimeout(() => setAnimatingBtn(null), 500);
    navigate(btn.path, { state: { transition: 'push' } });
  };

  // 二级菜单功能列表（深色主题配色）
  const secondaryFeatures = [
    { icon: Database, label: '产品池', desc: '精选优质货源', path: '/product-pool', color: 'text-sky-400', bg: 'bg-sky-500/15' },
    { icon: ShoppingBag, label: '推广中心', desc: '赚取高额分润', path: '/promotion-center', color: 'text-emerald-400', bg: 'bg-emerald-500/15' },
    { icon: Users, label: '人脉管理', desc: '高效触达客户', path: '/contacts', color: 'text-violet-400', bg: 'bg-violet-500/15' },
    { icon: Receipt, label: '我的订单', desc: '订单物流追踪', path: '/my-orders', color: 'text-amber-400', bg: 'bg-amber-500/15' },
    { icon: Target, label: '供需匹配', desc: '精准匹配可信商机', path: '/supply-demand', color: 'text-rose-400', bg: 'bg-rose-500/15' },
    { icon: Package, label: '我的产品', desc: '管理已发布产品', path: '/my-products', color: 'text-indigo-400', bg: 'bg-indigo-500/15' },
    { icon: GraduationCap, label: '推广教程', desc: '学习推广技巧', path: '/promotion-tutorial', color: 'text-teal-400', bg: 'bg-teal-500/15' },
    { icon: Crown, label: '会员中心', desc: '尊享会员权益', path: '/membership', color: 'text-amber-400', bg: 'bg-amber-500/15' },
    { icon: FileText, label: '合伙人政策', desc: '查看分账规则', path: '/partner-policy', color: 'text-blue-400', bg: 'bg-blue-500/15' },
    { icon: Globe, label: 'GEO诊断', desc: 'AI搜索品牌可见度分析', path: 'https://liankebao.top/geo-diagnosis', color: 'text-sky-400', bg: 'bg-sky-500/15' },
    { icon: BarChart3, label: '数据洞察', desc: '生意增长分析', path: '#data', color: 'text-cyan-400', bg: 'bg-cyan-500/15' },
    { icon: HelpCircle, label: '操作指南', desc: '新手上路必看', path: '/promotion-tutorial', color: 'text-slate-400', bg: 'bg-slate-500/15' },
    { icon: Settings, label: '个人设置', desc: '账号安全/偏好', path: '/profile', color: 'text-slate-400', bg: 'bg-slate-500/15' },
  ];

  return (
    <div className="flex flex-col min-h-screen bg-dark-bg font-sans pb-20">
      {/* Decorative mesh background */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-gradient-to-br from-sky-500/8 to-blue-600/5 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 right-0 w-[400px] h-[400px] bg-gradient-to-bl from-violet-500/6 to-purple-600/4 rounded-full blur-[100px]" />
        <div className="absolute bottom-0 left-1/3 w-[500px] h-[500px] bg-gradient-to-tr from-emerald-500/5 to-teal-600/3 rounded-full blur-[100px]" />
      </div>

      {/* Top Navigation Bar - dark theme */}
      <header className="fixed top-0 w-full z-50 bg-dark-surface/80 backdrop-blur-xl border-b border-dark-border/60 px-4 h-16">
        <div className="flex items-center justify-between h-full max-w-3xl mx-auto">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-xl brand-gradient flex items-center justify-center shadow-lg shadow-sky-500/20 glow-pulse">
              <HandshakeIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-manrope text-xl font-extrabold bg-gradient-to-r from-sky-400 to-blue-400 bg-clip-text text-transparent leading-tight">
                链客宝
              </h1>
              <p className="text-[10px] text-dark-muted font-medium tracking-wider -mt-0.5">企业信任关系网</p>
            <div className="flex items-center gap-4 mt-1">
              <span className="text-[9px] text-sky-400/70">🏪 100+ 企业入驻</span>
              <span className="text-[9px] text-emerald-400/70">🤝 500+ 成功对接</span>
              <span className="text-[9px] text-violet-400/70">⭐ 95% 满意度</span>
            </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button onClick={() => navigate('/notifications')} className="relative w-9 h-9 rounded-full bg-dark-surface flex items-center justify-center text-dark-muted hover:bg-sky-500/15 hover:text-sky-400 active:scale-90 transition-all border border-dark-border">
              <Bell className="w-4.5 h-4.5" />
              {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-gradient-to-br from-rose-500 to-rose-600 rounded-full text-white text-[8px] font-bold flex items-center justify-center shadow-sm">{unreadCount > 99 ? '99+' : unreadCount}</span>
              )}
            </button>
            <button onClick={() => { const d=document.documentElement; const n=d.getAttribute('data-theme')==='light'?'dark':'light'; d.setAttribute('data-theme',n); d.classList.remove('light','dark'); d.classList.add(n); localStorage.setItem('liankebao-theme',n); }} className="w-9 h-9 rounded-full bg-dark-surface flex items-center justify-center text-dark-muted hover:bg-sky-500/15 hover:text-sky-400 active:scale-90 transition-all border border-dark-border">
              <span className="text-base">☀️</span>
            </button>
            <button onClick={() => navigate('/profile')} className="w-9 h-9 rounded-full bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center text-white shadow-md shadow-sky-500/20 active:scale-90 transition-all border-2 border-dark-surface">
              <User className="w-4.5 h-4.5" />
            </button>
          </div>
        </div>
      </header>

      {/* ====== 平台数据总览 ====== */}
      <div className="pt-20 px-4 max-w-3xl mx-auto w-full relative z-10">
        <div className="bg-dark-surface/60 backdrop-blur-sm rounded-2xl border border-dark-border/60 p-4 grid grid-cols-3 gap-3">
          <div className="text-center">
            <div className="text-lg font-extrabold text-sky-400">100+</div>
            <div className="text-[10px] text-dark-muted font-medium">企业入驻</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-extrabold text-emerald-400">500+</div>
            <div className="text-[10px] text-dark-muted font-medium">成功对接</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-extrabold text-violet-400">95%</div>
            <div className="text-[10px] text-dark-muted font-medium">满意度</div>
          </div>
        </div>
      </div>

      <main className="pt-4 max-w-3xl mx-auto w-full relative z-10">
        {/* ====== 3 MAIN BUTTONS — enhanced ====== */}
        <div className="px-4 pt-8 pb-2">
          {/* Section label — dark theme */}
          <div className="flex items-center gap-2 mb-5">
            <div className="w-1 h-5 bg-gradient-to-b from-sky-400 to-blue-500 rounded-full shadow-sm shadow-sky-500/30" />
            <h2 className="font-manrope text-sm font-extrabold text-dark-muted uppercase tracking-widest">核心功能</h2>
          </div>

          <div className="flex flex-col gap-5">
            {missionButtons.map((btn) => (
              <button
                key={btn.id}
                onClick={() => handleMissionClick(btn)}
                className={`
                  relative w-full overflow-hidden rounded-2xl p-0 border-0 cursor-pointer
                  transition-all duration-300 ease-out
                  active:scale-[0.96]
                  ${animatingBtn === btn.id ? 'scale-[0.96]' : 'hover:scale-[1.02] hover:shadow-xl'}
                  shadow-lg ${btn.shadow}
                `}
                style={{ WebkitTapHighlightColor: 'transparent' }}
              >
                <div className={`absolute inset-0 bg-gradient-to-r ${btn.gradient}`} />
                {/* Animated shine overlay */}
                <div className="absolute inset-0 opacity-20"
                  style={{ backgroundImage: `radial-gradient(circle at 30% 40%, rgba(255,255,255,0.9) 0%, transparent 60%)` }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent" />
                <div className="relative flex items-center gap-5 px-6 py-6 min-h-[5.5rem]">
                  <div className="flex-shrink-0 w-16 h-16 rounded-2xl bg-white/20 backdrop-blur-md flex items-center justify-center text-3xl shadow-inner border border-white/25">
                    {btn.icon}
                  </div>
                  <div className="flex-1 text-left">
                    <div className="flex items-center gap-2.5">
                      <span className="text-white font-manrope font-extrabold text-xl tracking-wide drop-shadow-sm">{btn.label}</span>
                      {btn.badge && (
                        <span className="bg-white/25 backdrop-blur-sm text-white text-[10px] font-bold px-2.5 py-0.5 rounded-full border border-white/20 shadow-sm">{btn.badge}</span>
                      )}
                    </div>
                    <p className="text-white/80 text-sm mt-0.5 font-medium drop-shadow-sm">{btn.desc}</p>
                  </div>
                  <div className="flex-shrink-0 flex flex-col items-end gap-1.5">
                    <span className="text-white/70 text-[11px] font-semibold whitespace-nowrap drop-shadow-sm">{btn.hint}</span>
                    <div className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center border border-white/25 shadow-inner">
                      <ChevronRight className="w-4.5 h-4.5 text-white" />
                    </div>
                  </div>
                </div>
                {/* Bottom accent line */}
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-white/30 via-white/10 to-transparent" />
                {animatingBtn === btn.id && (
                  <span className="absolute inset-0 rounded-2xl animate-pulse bg-white/10" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* ====== MORE FEATURES ENTRY — dark theme ====== */}
        <div className="px-4 py-5">
          <button
            onClick={() => setShowMore(!showMore)}
            className="w-full flex items-center justify-between px-5 py-4 rounded-2xl bg-dark-surface/70 border border-dark-border hover:bg-dark-surface hover:border-sky-500/40 hover:shadow-lg hover:shadow-sky-500/5 active:scale-[0.98] transition-all shadow-sm backdrop-blur-sm"
          >
            <div className="flex items-center gap-3">
              <div className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${showMore ? 'bg-gradient-to-br from-sky-500 to-blue-600 text-white shadow-md shadow-sky-500/20' : 'bg-dark-surface text-dark-muted border border-dark-border'}`}>
                <Grid className={`w-4.5 h-4.5 transition-transform duration-300 ${showMore ? 'rotate-90' : ''}`} />
              </div>
              <div className="text-left">
                <span className="text-sm font-bold text-dark-text">{showMore ? '收起二级菜单' : '更多功能'}</span>
                <p className="text-[10px] text-dark-muted font-medium">产品池 · 推广 · 人脉 · 订单 · 数据</p>
              </div>
            </div>
            <div className={`w-7 h-7 rounded-full flex items-center justify-center transition-all ${showMore ? 'bg-sky-500/20 text-sky-400 rotate-90' : 'bg-dark-surface text-dark-muted border border-dark-border'}`}>
              <ChevronRight className="w-4 h-4" />
            </div>
          </button>

          {/* Expanded secondary menu — dark theme */}
          <div className={`overflow-hidden transition-all duration-400 ease-in-out ${showMore ? 'max-h-[1000px] opacity-100 mt-3' : 'max-h-0 opacity-0'}`}>
            <div className="bg-dark-surface/80 backdrop-blur-sm rounded-2xl border border-dark-border shadow-lg overflow-hidden">
              <div className="p-4">
                <div className="flex items-center gap-2 mb-3 px-1">
                  <Shapes className="w-3.5 h-3.5 text-sky-400" />
                  <span className="text-[10px] font-bold text-dark-muted uppercase tracking-widest">全部功能</span>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {secondaryFeatures.map((feat, i) => {
                    const Icon = feat.icon;
                    return (
                      <button
                        key={i}
                        onClick={() => {
                          if (feat.path === '#data') {
                            alert('数据洞察功能开发中，敬请期待');
                          } else {
                            navigate(feat.path, { state: { transition: 'push' } });
                          }
                        }}
                        className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-dark-bg hover:border-sky-500/20 active:scale-95 transition-all border border-transparent"
                      >
                        <div className={`w-11 h-11 ${feat.bg} rounded-xl flex items-center justify-center backdrop-blur-sm border border-white/5`}>
                          <Icon className={`w-5 h-5 ${feat.color}`} />
                        </div>
                        <span className="text-[10px] font-bold text-dark-text text-center leading-tight">{feat.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Site Footer — 公司信息 */}
      <footer className="px-4 py-6 mt-2 border-t border-dark-border/40">
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-[11px] text-dark-muted/60 font-medium mb-1">
          </p>
          <p className="text-[10px] text-dark-muted/40">
            沪ICP备2026007459号-2
          </p>
        </div>
      </footer>

      <BottomNav active="home" />
    </div>
  );
});

// Handshake icon component
function HandshakeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m11 17 2 2a1 1 0 1 0 3-3" />
      <path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4" />
      <path d="m21 3 1 11h-2" />
      <path d="M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3" />
      <path d="M3 4h8" />
    </svg>
  );
}

// ==============================
//  ProductPool
// ==============================
function safeImageUrl(url: string) {
  if (!url || typeof url !== 'string') return 'https://via.placeholder.com/200';
  if (url.startsWith('http://47.116.116.87')) return url.replace('http://47.116.116.87', '/lkapi');
  if (url.startsWith('http://') && !url.startsWith('http://localhost')) return url.replace('http://', 'https://');
  return url;
}

export const ProductPool = memo(function ProductPool() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('全部');
  const [sortBy, setSortBy] = useState('relevance');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<string[]>(['全部']);
  const pageSize = 12;

  // ===== AI智能匹配推荐 =====
  interface AiMatchItem {
    company: string;
    match_score: number;
    description: string;
  }
  const [aiRecs, setAiRecs] = useState<AiMatchItem[]>([]);
  const [aiReady, setAiReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get<{items: AiMatchItem[]}>('/api/match/recommend');
        if (!cancelled && res.code === 200 && res.data?.items && res.data.items.length > 0) {
          setAiRecs(res.data.items);
          setAiReady(true);
        }
      } catch {
        // 后端不可用 → 优雅降级，隐藏AI匹配区域
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const params = new URLSearchParams();
  if (search) params.set('q', search);
  if (category && category !== '全部') params.set('category', category);
  params.set('sort_by', sortBy);
  params.set('page', String(page));
  params.set('page_size', String(pageSize));
  const qs = params.toString();

  const { data: products, status, error, refetch } = useApi(
    () => api.get<{total: number; items: ProductItem[]}>('/api/search' + (qs ? `?${qs}` : ''))
      .then(r => {
        if (r.data?.items && r.data.items.length > 0) {
          setTotal(r.data.total);
          return r.data.items;
        }
        // 数据库为空时使用模拟产品数据
        setTotal(MOCK_PRODUCTS.length);
        return filterMockProducts(search, category, sortBy, page);
      })
      .catch(() => {
        setTotal(MOCK_PRODUCTS.length);
        return filterMockProducts(search, category, sortBy, page);
      }),
    [search, category, sortBy, page]
  );

  // Load categories dynamically from API
  useEffect(() => {
    api.get<{categories: string[]}>('/api/search/categories')
      .then(r => {
        if (r.data?.categories && r.data.categories.length > 0) {
          setCategories(['全部', ...r.data.categories]);
        } else {
          setCategories(['全部', 'AI工具', '企业服务', '营销工具', '数据服务', '开发服务', '培训服务']);
        }
      })
      .catch(() => {
        setCategories(['全部', 'AI工具', '企业服务', '营销工具', '数据服务', '开发服务', '培训服务']);
      });
  }, []);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [search, category, sortBy]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // ===== 模拟产品数据（数据库为空时展示） =====
  const MOCK_PRODUCTS: ProductItem[] = [
    { id: 1, name: '企业AI数字名片 Pro', description: 'AI智能识别+翻页图册+一键分享，让每一次社交都成为商机', price: 299, earn_per_share: 89, category: 'AI工具', stock: 999, images: '', status: 'active', owner_id: 1, tags: 'AI,名片,企业' },
    { id: 2, name: '智能供需匹配服务', description: 'AI算法精准匹配买家和供应商，让企业对接效率提升10倍', price: 1999, earn_per_share: 599, category: '企业服务', stock: 999, images: '', status: 'active', owner_id: 1, tags: '匹配,AI,供需' },
    { id: 3, name: '企业信任认证套餐', description: '企业实名认证+信用评分+资质展示，构建可信商业网络', price: 499, earn_per_share: 149, category: '企业服务', stock: 999, images: '', status: 'active', owner_id: 1, tags: '认证,信任,企业' },
    { id: 4, name: '社交裂变推广工具', description: '三级分润+专属推广链接+数据看板，让客户成为您的推广大使', price: 799, earn_per_share: 239, category: '营销工具', stock: 999, images: '', status: 'active', owner_id: 1, tags: '推广,裂变,分销' },
    { id: 5, name: '企业CRM轻量版', description: '客户管理+跟进记录+标签分类+数据洞察，精准经营每一位客户', price: 399, earn_per_share: 119, category: '企业服务', stock: 999, images: '', status: 'active', owner_id: 1, tags: 'CRM,客户,管理' },
    { id: 6, name: 'AI销售助手', description: '智能话术推荐+跟进提醒+成交预测，让销售业绩提升50%', price: 599, earn_per_share: 179, category: 'AI工具', stock: 999, images: '', status: 'active', owner_id: 1, tags: 'AI,销售,助手' },
    { id: 7, name: '企业大数据洞察', description: '行业趋势分析+竞品监控+商机挖掘，数据驱动决策', price: 2999, earn_per_share: 899, category: '数据服务', stock: 999, images: '', status: 'active', owner_id: 1, tags: '数据,洞察,分析' },
    { id: 8, name: '微信小程序搭建服务', description: '专业团队为企业定制微信小程序，快速上线获客新渠道', price: 4999, earn_per_share: 1499, category: '开发服务', stock: 999, images: '', status: 'active', owner_id: 1, tags: '小程序,开发,微信' },
    { id: 9, name: '企业培训课程包', description: 'AI营销+私域运营+销售技巧，助力企业团队能力升级', price: 199, earn_per_share: 59, category: '培训服务', stock: 999, images: '', status: 'active', owner_id: 1, tags: '培训,课程,营销' },
    { id: 10, name: '企业AI名片 基础版', description: '电子名片+联系方式+社交链接，免费开启数字化社交', price: 0, earn_per_share: 0, category: 'AI工具', stock: 999, images: '', status: 'active', owner_id: 1, tags: '免费,名片,基础' },
  ];

  function filterMockProducts(searchTerm: string, cat: string, sort: string, pg: number): ProductItem[] {
    let filtered = [...MOCK_PRODUCTS];
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      filtered = filtered.filter(p => p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q) || (p.tags && p.tags.toLowerCase().includes(q)));
    }
    if (cat && cat !== '全部') {
      filtered = filtered.filter(p => p.category === cat);
    }
    if (sort === 'price_asc') filtered.sort((a, b) => a.price - b.price);
    else if (sort === 'price_desc') filtered.sort((a, b) => b.price - a.price);
    else if (sort === 'newest') filtered.sort((a, b) => b.id - a.id);
    // 分页
    const start = (pg - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }

  const sortOptions = [
    { value: 'relevance', label: '相关性' },
    { value: 'price_asc', label: '价格升序' },
    { value: 'price_desc', label: '价格降序' },
    { value: 'newest', label: '最新' },
  ];

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
          {categories.map((cat, i) => (
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

        {/* Sort Dropdown */}
        <div className="flex justify-end px-4 pb-2">
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            className="text-xs font-medium bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-600 focus:ring-2 focus:ring-sky-500/15 focus:border-sky-500 outline-none cursor-pointer transition-all shadow-sm"
          >
            {sortOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* ===== AI智能匹配推荐 ===== */}
        {aiReady && aiRecs.length > 0 && (
          <div className="px-4 pt-2 pb-1">
            <div className="bg-dark-surface/80 backdrop-blur-sm rounded-2xl border border-dark-border overflow-hidden shadow-lg">
              {/* Header */}
              <div className="flex items-center gap-2 px-5 py-3 border-b border-dark-border/60">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center shadow-sm">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
                <span className="text-sm font-extrabold text-dark-text">AI智能匹配</span>
                <span className="text-[10px] text-dark-muted font-medium ml-auto">基于您的需求智能推荐</span>
              </div>
              {/* Cards */}
              <div className="p-4 space-y-3">
                {aiRecs.map((item, i) => (
                  <div
                    key={i}
                    onClick={() => navigate('/product-detail', { state: { transition: 'push', productId: -1 } })}
                    className="bg-dark-bg/50 rounded-xl border border-dark-border/60 p-4 hover:border-sky-500/30 hover:bg-dark-bg/70 transition-all cursor-pointer active:scale-[0.98]"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <h4 className="text-sm font-bold text-dark-text">{item.company}</h4>
                      <span className="text-xs font-extrabold text-sky-400">{item.match_score}%</span>
                    </div>
                    {/* Progress bar */}
                    <div className="w-full h-1.5 bg-dark-surface rounded-full overflow-hidden mb-2.5">
                      <div
                        className="h-full bg-gradient-to-r from-sky-500 to-blue-500 rounded-full transition-all duration-1000 ease-out"
                        style={{ width: `${Math.min(100, Math.max(0, item.match_score))}%` }}
                      />
                    </div>
                    <p className="text-xs text-dark-muted leading-relaxed line-clamp-2">{item.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="px-4 pt-4">
          {products && products.length > 0 && total === 10 && (
            <div className="mb-3 flex items-center gap-2 text-[10px] text-amber-600 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
              <Sparkles className="w-3 h-3 shrink-0" />
              <span>当前为模拟数据，接入真实数据后自动替换</span>
            </div>
          )}
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
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <div className="w-20 h-20 bg-gradient-to-br from-sky-100 to-blue-50 rounded-2xl flex items-center justify-center mb-5 shadow-sm border border-sky-100">
                <span className="text-3xl">📦</span>
              </div>
              <h3 className="text-base font-bold text-slate-700 mb-2">还没有产品</h3>
              <p className="text-xs text-slate-400 mb-6 max-w-[240px] leading-relaxed">发布第一个产品，开启你的企业家之旅</p>
              <button
                onClick={() => navigate('/add-product')}
                className="px-6 py-2.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white text-xs font-bold rounded-xl shadow-md shadow-sky-500/20 hover:shadow-lg active:scale-95 transition-all"
              >
                发布新产品
              </button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                {products.map((item, i) => (
                  <div
                    key={item.id || i}
                    onClick={() => navigate('/product-detail', { state: { transition: 'push', productId: item.id } })}
                    className="bg-white rounded-xl border border-slate-100 overflow-hidden shadow-sm hover:shadow-md transition-all card-hover cursor-pointer"
                  >
                    <img src={safeImageUrl(typeof item.images === "string" ? (JSON.parse(item.images || '[]')[0]) : (Array.isArray(item.images) ? item.images[0] : item.images))} className="w-full aspect-square object-cover bg-slate-50" alt={item.name} />
                    <div className="p-3 space-y-2">
                      <h3 className="text-xs font-bold line-clamp-2 h-8 text-slate-800">{item.name}</h3>
                      {item.tags && (
                        <div className="flex flex-wrap gap-1">
                          {item.tags.split(',').slice(0, 3).map((tag, ti) => (
                            <span key={ti} className="text-[8px] bg-sky-50 text-sky-600 px-1.5 py-0.5 rounded-full font-medium border border-sky-100">{tag}</span>
                          ))}
                        </div>
                      )}
                      <p className="text-sky-600 font-manrope font-bold">¥{item.price.toFixed(2)}</p>
                      {item.brochure_id && (
                        <a
                          href={`https://liankebao.top/api/brochure/${item.brochure_id}/brochure`}
                          target="_blank"
                          onClick={(e) => e.stopPropagation()}
                          className="block w-full py-1.5 border border-emerald-200 text-emerald-600 rounded-full text-[10px] font-bold hover:bg-emerald-500 hover:text-white hover:border-emerald-500 active:scale-95 transition-all text-center"
                        >
                          📖 电子画册
                        </a>
                      )}
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

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-6 mb-4">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="px-3 py-1.5 text-xs font-bold rounded-lg border border-slate-200 bg-white text-slate-500 hover:bg-sky-50 hover:border-sky-200 hover:text-sky-600 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    上一页
                  </button>
                  {(() => {
                    const buttons: number[] = [];
                    const maxVisible = 5;
                    if (totalPages <= maxVisible) {
                      for (let i = 1; i <= totalPages; i++) buttons.push(i);
                    } else if (page <= 3) {
                      for (let i = 1; i <= maxVisible; i++) buttons.push(i);
                    } else if (page >= totalPages - 2) {
                      for (let i = totalPages - maxVisible + 1; i <= totalPages; i++) buttons.push(i);
                    } else {
                      for (let i = page - 2; i <= page + 2; i++) buttons.push(i);
                    }
                    return buttons.map(pageNum => (
                      <button
                        key={pageNum}
                        onClick={() => setPage(pageNum)}
                        className={`w-8 h-8 text-xs font-bold rounded-lg border transition-all ${
                          pageNum === page
                            ? 'bg-sky-500 text-white border-sky-500 shadow-sm'
                            : 'bg-white text-slate-500 border-slate-200 hover:bg-sky-50 hover:border-sky-200 hover:text-sky-600'
                        }`}
                      >
                        {pageNum}
                      </button>
                    ));
                  })()}
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="px-3 py-1.5 text-xs font-bold rounded-lg border border-slate-200 bg-white text-slate-500 hover:bg-sky-50 hover:border-sky-200 hover:text-sky-600 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    下一页
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </main>

      <BottomNav active="product" />
    </div>
  );
});

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
