import { useNavigate, Link } from 'react-router-dom';
import { Search, Home, Grid, Zap, User, Star, ArrowRight, UserPlus, FileText, Share2, Users, GraduationCap, ChevronRight, LayoutDashboard, ShoppingBag, Receipt, CheckCircle2 } from 'lucide-react';
import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { ProductItem } from '../types';

export function LiankebaoHomepage() {
  const navigate = useNavigate();
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.get<{products: ProductItem[]}>('/api/products' + (search ? `?search=${search}` : '')).then(res => {
      if (res.data?.products) setProducts(res.data.products);
    });
  }, [search]);

  const displayProducts = products.slice(0, 2);

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex justify-between items-center px-4 h-16">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full overflow-hidden bg-slate-200">
            <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuD4tMOKc54Z0YVDSu1fkIMVku0yO7U0ATD54AVlY078SzXn3qA2vyaB0ldf4CKfwMX0BNhxjENkB8q2elgxMnM2QZNr7IWoSguo6SeAc7LRp4iYuP9KRE1dfKpMo5ex_IHlTzWne5NkP3xLwOMJgsT6f1U6QmOyyzEGYth-6syFPneg2Dy6UE19-xanhkpW2HivuCxqQAxzVevnG-3L_0Y6AdyZMyoBtuRRhLFAOvcTkpf1PPlZnE2S-NxRBgBfFE7N8UQoa1clN3Yl" className="w-full h-full object-cover" />
          </div>
          <h1 className="font-manrope text-xl font-bold text-primary-container">Liankebao</h1>
        </div>
        <button className="text-primary-container"><Search className="w-6 h-6" /></button>
      </header>

      <main className="pt-16 p-4 space-y-6">
        <div className="relative flex items-center group">
          <Search className="absolute left-4 text-slate-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-white border border-border-light rounded-2xl py-4 pl-12 pr-4 focus:ring-1 focus:ring-primary-container outline-none"
            placeholder="搜产品、搜企业、搜品类"
          />
        </div>

        <div className="relative w-full aspect-[21/9] rounded-2xl overflow-hidden shadow-lg">
          <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuD4kMHf2SGDagsPzzoXAYyl4Qlh3bwG3ulPT7jY21jQ7ue70WvJXbluRkzFVjy2tHXswVEqHCRqvv2AiubBWe3U707uS8uMG4-zygF4bJKTKta2DT5rTjRsuhkA78QV7IoadSn4DmAE8pNHq0S6ewsN6_tucX89M1Z7qdgbjvP4eAg7tA8SxOzPTPHz0WR4zPBEDm_c2U4odWH6Jwx7K9DDeosBn7ua8DY15uJl3SCxC3CSDtq6kMER2-91tsAjqJ69onzaYW74Z3Pj" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/60 to-transparent flex flex-col justify-center px-6">
            <h2 className="text-white font-manrope font-bold text-xl">精选大健康 · 企业家必备</h2>
            <div className="mt-2"><span className="bg-primary-container text-white px-2 py-0.5 rounded text-[10px] font-bold">精选</span></div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4">
          {[
            { icon: <Star className="text-sky-600" />, label: 'AI名片' },
            { icon: <Zap className="text-sky-600" />, label: 'GEO诊断' },
            { icon: <User className="text-sky-600" />, label: '数字分身' },
            { icon: <Grid className="text-sky-600" />, label: '全部产品' }
          ].map((item, i) => (
            <div key={i} className="flex flex-col items-center gap-2">
              <div className="w-14 h-14 bg-white rounded-2xl flex items-center justify-center border border-border-light shadow-sm active:scale-95 transition-transform">
                {item.icon}
              </div>
              <span className="text-xs text-slate-700">{item.label}</span>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <h2 className="font-manrope text-lg font-bold flex items-center gap-2">
            <span className="w-1 h-5 bg-primary-container rounded-full"></span>
            为您推荐
          </h2>
          <span className="text-xs text-slate-400">更多产品</span>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {displayProducts.map((item, i) => (
            <div key={i} className="bg-white rounded-2xl overflow-hidden border border-border-light group">
              <div className="aspect-square p-2">
                <img src={item.images || 'https://via.placeholder.com/200'} className="w-full h-full object-cover rounded-xl" />
              </div>
              <div className="p-3 space-y-2">
                <h3 className="text-sm font-bold text-on-surface line-clamp-2 leading-tight">{item.name}</h3>
                <div className="flex items-center justify-between">
                  <span className="font-manrope text-lg font-bold text-primary-container">¥{item.price.toFixed(2)}</span>
                </div>
                <div className="bg-sky-50 border border-sky-100 rounded px-2 py-0.5"><span className="text-[10px] font-bold text-sky-700">推广赚 ¥{item.earn_per_share.toFixed(2)}</span></div>
                <button 
                  onClick={() => navigate('/product-detail', { state: { transition: 'push', productId: item.id } })}
                  className="w-full py-2 border-2 border-primary-container text-primary-container rounded-xl font-bold text-xs active:bg-primary-container active:text-white transition-all"
                >
                  我要推广
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>

      <nav className="fixed bottom-0 w-full h-16 bg-white border-t border-border-light flex justify-around items-center px-4 pb-safe">
        <Link to="/home" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-primary-container">
          <Home className="w-5 h-5" />
          <span className="text-[10px] font-bold">首页</span>
        </Link>
        <Link to="/product-pool" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-slate-400">
          <ShoppingBag className="w-5 h-5" />
          <span className="text-[10px] font-medium">产品池</span>
        </Link>
        <Link to="/promotion-center" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-slate-400">
          <User className="w-5 h-5" />
          <span className="text-[10px] font-medium">我的</span>
        </Link>
      </nav>
    </div>
  );
}

export function ProductPool() {
  const navigate = useNavigate();
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('全部');

  useEffect(() => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (category && category !== '全部') params.set('category', category);
    const qs = params.toString();
    api.get<{products: ProductItem[]}>('/api/products' + (qs ? `?${qs}` : '')).then(res => {
      if (res.data?.products) setProducts(res.data.products);
    });
  }, [search, category]);

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex justify-between items-center px-4 h-16">
        <div className="flex items-center gap-3">
          <Grid className="w-6 h-6 text-primary-container" />
          <h1 className="font-manrope text-lg font-bold text-primary-container">产品池</h1>
        </div>
        <Search className="w-6 h-6 text-primary-container" />
      </header>

      <main className="pt-16 pb-12">
        <div className="p-4">
          <div className="relative flex items-center">
            <Search className="absolute left-3 text-slate-400 w-5 h-5" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-white border border-border-light rounded-xl py-2 pl-10 pr-4 text-sm"
              placeholder="搜产品、搜企业、搜品类"
            />
          </div>
        </div>

        <div className="flex overflow-x-auto no-scrollbar gap-6 px-4 py-3 border-b border-border-light bg-white sticky top-16 z-40">
          {['全部', '护肝解酒', '助眠安神', '滋补养生', '男士营养'].map((cat, i) => (
            <span
              key={i}
              onClick={() => setCategory(cat)}
              className={`text-sm font-bold whitespace-nowrap pb-1 cursor-pointer ${cat === category ? 'text-primary-container border-b-2 border-primary-container' : 'text-slate-400'}`}
            >
              {cat}
            </span>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3 p-4">
          {products.map((item, i) => (
            <div key={item.id || i} className="bg-white rounded-xl border border-border-light overflow-hidden shadow-sm">
              <img src={item.images || 'https://via.placeholder.com/200'} className="w-full aspect-square object-cover" />
              <div className="p-3 space-y-2">
                <h3 className="text-xs font-bold line-clamp-2 h-8">{item.name}</h3>
                <p className="text-primary-container font-manrope font-bold">¥{item.price.toFixed(2)}</p>
                <button 
                  onClick={() => navigate('/product-detail', { state: { transition: 'push', productId: item.id } })}
                  className="w-full py-1.5 border border-primary-container text-primary-container rounded-full text-[10px] font-bold active:bg-primary-container active:text-white"
                >
                  我要推广
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>

      <nav className="fixed bottom-0 w-full h-16 bg-white border-t border-border-light flex justify-around items-center px-4 pb-safe">
        <Link to="/home" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-slate-400">
          <Home className="w-5 h-5" />
          <span className="text-[10px] font-medium font-manrope">首页</span>
        </Link>
        <Link to="/product-pool" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-primary-container">
          <ShoppingBag className="w-5 h-5" />
          <span className="text-[10px] font-bold font-manrope">产品池</span>
        </Link>
        <Link to="/promotion-center" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-slate-400">
          <User className="w-5 h-5" />
          <span className="text-[10px] font-medium font-manrope">我的</span>
        </Link>
      </nav>
    </div>
  );
}

export function PromotionCenter() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-24">
      <header className="fixed top-0 w-full z-50 bg-slate-900 flex justify-between items-center px-4 h-12">
        <Grid className="w-5 h-5 text-primary-container" />
        <h1 className="font-manrope font-bold text-white">推广中心</h1>
        <div className="w-5"></div>
      </header>

      <main className="pt-12 p-4 space-y-6">
        <section className="flex items-center gap-4 bg-white p-4 rounded-2xl shadow-sm border border-border-light">
          <div className="relative">
            <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuBuKyvslj8Sf-I9tZohEQpeosSpcblKwhdWiqVlMXd0qsagxqS4K6yznJr7Opusanym978mU3oHeQUKk9KSN_Of36-XIjq9Y9jdQUappQILE_q0z7iom3Ahiz1wzkvqaqkYjMhGoCGVxUxq9Gvr1PcW1YCyEk4OmWwG2jS0pEzlAhGEEDg5T0JAQg9xzAEfHlJU6cR-CVD_4sOVUxu8zIbsWvmm8apd0ipCCVEAtq5Uw_ZClY1oJJ5f0yMpmpeN7mNo7CachYe_5otw" className="w-16 h-16 rounded-full border-2 border-primary-container" />
            <div className="absolute -bottom-1 -right-1 sky-gradient rounded-full p-1 border-2 border-white">
              <CheckCircle2 className="w-3 h-3 text-white" />
            </div>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold">林峰</h2>
              <span className="sky-gradient text-[10px] text-white px-2 py-0.5 rounded-full font-bold">铂金会员</span>
            </div>
            <p className="text-xs text-text-muted mt-1">会员到期日：2024-12-31</p>
          </div>
        </section>

        <section className="bg-white rounded-2xl border-l-4 border-primary-container p-5 shadow-sm border border-border-light">
          <div className="flex justify-between items-start mb-6">
            <div>
              <p className="text-xs text-text-muted">今日收入 (元)</p>
              <p className="text-2xl font-bold text-sky-600 mt-1">+46.80</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-text-muted">可提现余额</p>
              <p className="text-lg font-bold text-slate-900 mt-1">¥ 1,280.50</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 border-t border-border-light pt-4 mb-6">
            <div>
              <p className="text-xs text-text-muted">本月累计</p>
              <p className="font-bold">¥ 3,420.00</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-text-muted">累计总收益</p>
              <p className="font-bold">¥ 12,850.20</p>
            </div>
          </div>
          <button className="w-full sky-gradient text-white py-3 rounded-xl font-bold active:scale-95 transition-transform shadow-md">立即提现</button>
        </section>

        <section className="grid grid-cols-4 gap-4">
          {[
            { label: '我的订单', icon: <FileText />, path: '/my-orders' },
            { label: '分享海报', icon: <Share2 />, path: '#' },
            { label: '我的下级', icon: <Users />, path: '#' },
            { label: '推广教程', icon: <GraduationCap />, path: '#' }
          ].map((item, i) => (
            <div key={i} onClick={() => item.path !== '#' && navigate(item.path, { state: { transition: 'push' } })} className="flex flex-col items-center gap-2 cursor-pointer">
              <div className="w-12 h-12 bg-white rounded-2xl shadow-sm border border-border-light flex items-center justify-center text-slate-900">
                {item.icon}
              </div>
              <span className="text-[10px] font-medium">{item.label}</span>
            </div>
          ))}
        </section>

        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold flex items-center gap-2">
              <span className="w-1 h-5 bg-primary-container rounded-full"></span>
              本月热推产品
            </h3>
            <span className="text-xs text-primary font-bold">更多</span>
          </div>
          {[
            { title: '旗舰版智能健康手表 S3', price: '1,299', earn: '129.9', img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuApC5VJUCEfOGxW-cKut2u8z6NO-kav_mBGu69O34D8YpFcDrbZ8dwSI-LSFCGAbxW_gi1bUwGAtLONndumKY3QM3_GxZgfhh83TfxCMWo0p9YXUwFQSPZOsrNxTKR5xcBn5J2kurh3IlzHyAIl-xmcyeZI9Z88Nf8Ol6P9OqNVQF54URZODLp_oEsz0TlvNJ6z4rFFehdANpM_c9obgqNdYxMpfbcr9YKeBu0HaDFTeUCtb4TAKmEt4ageyc0Dl4KUV1XiSZgSpGXf' },
          ].map((item, i) => (
            <div key={i} className="flex bg-white p-3 rounded-2xl border border-border-light gap-3">
              <div className="w-20 h-20 rounded-xl bg-slate-100 overflow-hidden shrink-0">
                <img src={item.img} className="w-full h-full object-cover" />
              </div>
              <div className="flex-1 flex flex-col justify-between">
                <h4 className="font-bold text-sm line-clamp-1">{item.title}</h4>
                <div className="flex justify-between items-end">
                  <div>
                    <p className="text-sky-600 font-bold text-lg">¥{item.price}</p>
                    <div className="bg-sky-50 px-1 py-0.5 rounded"><span className="text-[10px] text-primary-container font-bold">分润 ¥{item.earn}</span></div>
                  </div>
                  <button 
                    onClick={() => navigate('/product-detail', { state: { transition: 'push' } })}
                    className="px-4 py-1.5 rounded-full bg-primary-container text-white text-xs font-bold active:scale-95 transition-transform"
                  >
                    推广
                  </button>
                </div>
              </div>
            </div>
          ))}
        </section>
      </main>

      <nav className="fixed bottom-0 w-full h-16 bg-white border-t border-border-light flex justify-around items-center px-4 pb-safe">
        <Link to="/home" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-slate-400">
          <Home className="w-5 h-5" />
          <span className="text-[10px] font-medium">首页</span>
        </Link>
        <Link to="/product-pool" state={{ transition: 'none' }} className="flex flex-col items-center gap-1 text-slate-400">
          <ShoppingBag className="w-5 h-5" />
          <span className="text-[10px] font-medium">选品中心</span>
        </Link>
        <div className="flex flex-col items-center gap-1 text-primary-container">
          <Receipt className="w-5 h-5" />
          <span className="text-[10px] font-bold">收益</span>
        </div>
        <div onClick={() => navigate('/promotion-center', { state: { transition: 'none' } })} className="flex flex-col items-center gap-1 text-slate-400 cursor-pointer">
          <User className="w-5 h-5" />
          <span className="text-[10px] font-medium">我的</span>
        </div>
      </nav>
    </div>
  );
}
