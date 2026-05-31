import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Share2, Star, Minus, Plus, Heart, Headset, FileText, Factory, ExternalLink, MoreHorizontal, CheckCircle2, Camera, Percent } from 'lucide-react';
import { useState, memo, useEffect } from 'react';
import { api } from '../api/client';
import { ProductItem } from '../types';
import { Loading, ErrorBlock, Empty, useApi } from '../components/StatusComponents';

function safeImageUrl(url) {
  if (!url || typeof url !== 'string') return 'https://via.placeholder.com/200';
  if (url.startsWith('http://47.116.116.87')) return url.replace('http://47.116.116.87', '/lkapi');
  if (url.startsWith('http://') && !url.startsWith('http://localhost')) return url.replace('http://', 'https://');
  return url;
}

export const ProductDetailPage = memo(function ProductDetailPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  // Read productId from navigation state (when coming from product list) or query param (when accessed via direct URL)
  const productId = (location.state as any)?.productId || (searchParams.get('productId') ? Number(searchParams.get('productId')) : null);

  const { data: product, status, error, refetch } = useApi(
    () => productId
      ? api.get<ProductItem>(`/api/products/${productId}`).then(r => r.data || null)
      : Promise.resolve(null),
    [productId]
  );

  // 产品浏览追踪
  useEffect(() => {
    if (productId) {
      api.track('product_view', { target_id: productId, target_type: 'product' });
    }
  }, [productId]);

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-24">
      <header className="fixed top-0 left-0 w-full z-50 flex justify-between items-center px-4 h-14 bg-neutral-bg border-b border-border-light">
        <button onClick={() => navigate('/home', { state: { transition: 'push_back' } })} className="active:scale-95 transition-transform">
          <ArrowLeft className="w-6 h-6 text-primary-container" />
        </button>
        <h1 className="font-manrope font-bold text-lg text-primary-container">产品详情</h1>
        <button className="active:scale-95 transition-transform"><Share2 className="w-6 h-6 text-primary-container" /></button>
      </header>

      <main className="pt-14 overflow-y-auto">
        {status === 'loading' ? (
          <Loading />
        ) : status === 'error' ? (
          <ErrorBlock message={error} onRetry={refetch} />
        ) : !product ? (
          <Empty text="产品不存在" icon="🔍" />
        ) : (
        <>
        <section className="relative w-full h-[300px] bg-white">
          <img src={typeof product?.images === 'string' ? (JSON.parse(product.images || '[]')[0] || 'https://via.placeholder.com/200') : (Array.isArray(product?.images) ? product.images[0] : (product?.images || 'https://via.placeholder.com/200'))} className="w-full h-full object-cover" />
          <div className="absolute bottom-4 right-4 bg-black/20 backdrop-blur-md text-white px-3 py-1 rounded-full text-[10px] font-bold">1 / 1</div>
        </section>

        <section className="p-4 bg-white space-y-4">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-on-surface">{product?.name || '高级护肝综合营养片'}</h2>
            {product?.tags && (
              <div className="flex flex-wrap gap-1.5">
                {product.tags.split(',').map((tag, ti) => (
                  <span key={ti} className="text-[10px] bg-sky-50 text-sky-600 px-2 py-0.5 rounded-full font-medium border border-sky-100">{tag}</span>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <div className="flex text-primary-container"><Star className="w-4 h-4" fill="currentColor" /><Star className="w-4 h-4" fill="currentColor" /><Star className="w-4 h-4" fill="currentColor" /><Star className="w-4 h-4" fill="currentColor" /><Star className="w-4 h-4" /></div>
              <span className="text-text-muted text-xs">库存: {product?.stock || 0}</span>
            </div>
            <p className="text-2xl font-manrope font-bold text-primary-container">¥{(product?.price || 298).toFixed(2)}</p>
          </div>

          <div className="space-y-3">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">规格</span>
            <div className="flex gap-3">
              <button className="flex-1 p-3 rounded-xl border-2 border-primary-container bg-neutral-bg text-primary-container font-bold text-sm">标准装<p className="text-xs opacity-80">¥{(product?.price || 298).toFixed(2)}</p></button>
            </div>
          </div>
        </section>

        <section className="mt-4 px-4">
          <div className="bg-sky-50 border-l-4 border-primary-container p-4 rounded-r-2xl shadow-sm flex justify-between items-center">
            <div className="space-y-1">
              <p className="font-bold text-on-surface">推广本产品，赚取售价的 <span className="text-primary-container">{product?.earn_per_share || 7}%</span></p>
            </div>
            <button
              onClick={() => navigate('/promotion-center', { state: { transition: 'push' } })}
              className="bg-primary-container text-white px-4 py-2 rounded-xl font-bold text-xs active:scale-95"
            >
              立即推广
            </button>
          </div>
        </section>

        <section className="mt-4 bg-white p-4 space-y-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-primary-container" />
              <span className="font-bold">产品详情</span>
            </div>
          </div>
          <p className="text-xs text-secondary leading-relaxed">{product?.description || '我们的高级护肝综合营养片采用100%天然草本提取物配制而成，包括水飞蓟、朝鲜蓟和姜黄。专为现代高压环境设计，支持自然排毒和日常能量水平。'}</p>
        </section>
        </>
      )}
      </main>

      <footer className="fixed bottom-0 left-0 w-full z-50 bg-neutral-bg flex items-center px-4 h-20 shadow-lg border-t border-border-light gap-3 pb-safe">
        <div className="flex gap-4 pr-2">
          <div className="flex flex-col items-center"><Heart className="w-6 h-6 text-on-surface" /><span className="text-[10px] font-bold">收藏</span></div>
          <div className="flex flex-col items-center"><Headset className="w-6 h-6 text-on-surface" /><span className="text-[10px] font-bold">客服</span></div>
        </div>
        <div className="flex-1 flex gap-2">
          <button
            onClick={() => navigate('/order-confirm', { state: { transition: 'slide_up' } })}
            className="flex-1 h-12 rounded-xl border-2 border-primary-container text-primary-container font-bold text-sm bg-white active:scale-95 transition-transform"
          >
            加入购物车
          </button>
          <button className="flex-1 h-12 rounded-xl bg-primary-container text-white font-bold text-sm active:scale-95 transition-transform flex flex-col items-center justify-center">
            <span className="text-[10px] opacity-80 font-normal">¥{(product?.price || 298).toFixed(2)}</span>
            <span>立即购买</span>
          </button>
        </div>
      </footer>
    </div>
  );
});
export const MyProducts = memo(function MyProducts() {
  const navigate = useNavigate();

  const { data: products, status, error, refetch } = useApi(
    () => {
      const currentUser = api.loadToken();
      if (!currentUser) return Promise.resolve([]);
      return api.get<{items: ProductItem[]}>('/api/products').then(r => r.data?.items || []);
    },
    []
  );

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      <header className="flex justify-between items-center px-4 h-14 sticky top-0 z-50 bg-neutral-bg border-b border-border-light">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/promotion-center', { state: { transition: 'push_back' } })}><ArrowLeft className="w-6 h-6 text-primary-container" /></button>
          <h1 className="font-manrope font-bold text-lg text-on-surface">我的产品</h1>
        </div>
        <button
          onClick={() => navigate('/add-product', { state: { transition: 'push' } })}
          className="bg-primary-container text-white px-3 py-1.5 rounded-lg font-bold text-sm"
        >
          上架新品
        </button>
      </header>

      <nav className="flex bg-white border-b border-border-light sticky top-14 z-40 overflow-x-auto no-scrollbar">
        {['已上架', '审核中', '已下架', '审核驳回'].map((tab, i) => (
          <button key={i} className={`flex-1 py-3 text-sm font-bold ${i === 0 ? 'text-primary-container border-b-2 border-primary-container' : 'text-text-muted'}`}>{tab}</button>
        ))}
      </nav>

      <main className="p-4 space-y-4">
        {status === 'loading' ? (
          <Loading />
        ) : status === 'error' ? (
          <ErrorBlock message={error} onRetry={refetch} />
        ) : !products || products.length === 0 ? (
          <Empty text="暂无产品" />
        ) : (
          products.map((item, i) => (
            <div key={item.id || i} className="bg-white rounded-2xl overflow-hidden border border-border-light shadow-sm">
              <div className="p-4 flex gap-4">
                <div className="w-20 h-20 rounded-xl overflow-hidden bg-slate-50"><img src={safeImageUrl(typeof item.images === "string" ? (JSON.parse(item.images || '[]')[0]) : (Array.isArray(item.images) ? item.images[0] : item.images))} className="w-full h-full object-cover" /></div>
                <div className="flex-1 space-y-2">
                  <div className="flex justify-between items-start"><h3 className="font-bold text-sm line-clamp-1">{item.name}</h3><span className="text-[10px] font-bold text-success bg-emerald-50 px-2 py-0.5 rounded">{item.status === 'approved' ? '已上架' : item.status}</span></div>
                  <p className="text-primary-container font-manrope font-bold text-lg">¥{item.price.toFixed(2)}</p>
                  <div className="flex gap-4 text-[10px] text-text-muted"><span>库存 {item.stock}</span></div>
                </div>
              </div>
              <div className="px-4 py-3 border-t border-border-light flex justify-between items-center">
                <div className="flex gap-4 text-xs font-bold text-secondary"><span>编辑</span><span>分享链接</span><span>查看数据</span></div>
                <button className="text-primary-container border border-primary-container rounded-full px-4 py-1 text-xs font-bold active:bg-primary-container active:text-white transition-all">下架</button>
              </div>
            </div>
          ))
        )}
      </main>
    </div>
  );
});
export const AddProduct = memo(function AddProduct() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [earnPerShare, setEarnPerShare] = useState('');
  const [category, setCategory] = useState('大健康 - 营养膳食');
  const [stock, setStock] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const res = await api.post<{product: ProductItem}>('/api/products', {
        name, description, price: parseFloat(price), earn_per_share: parseFloat(earnPerShare),
        category, stock: parseInt(stock)
      });
      if (res.code === 200) {
        navigate('/my-products', { state: { transition: 'push_back' } });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 z-50 w-full bg-white border-b border-border-light h-14 flex items-center px-4">
        <button onClick={() => navigate('/my-products', { state: { transition: 'push_back' } })}><ArrowLeft className="w-6 h-6 text-primary-container" /></button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">上架新产品</h1>
        <div className="ml-auto flex items-center"><MoreHorizontal className="w-6 h-6 text-primary-container" /></div>
      </header>

      <main className="pt-16 p-4 space-y-4">
        <section className="bg-white rounded-2xl p-4 border border-border-light shadow-sm space-y-4">
          <h2 className="font-bold text-lg">基本信息</h2>
          <div className="space-y-4">
            <div className="space-y-1"><label className="text-xs text-secondary">产品名称</label><input value={name} onChange={e => setName(e.target.value)} className="w-full h-12 bg-neutral-bg/50 border-b border-border-light focus:border-primary-container outline-none" placeholder="请输入产品名称" /></div>
            <div className="space-y-1"><label className="text-xs text-secondary">产品描述</label><textarea value={description} onChange={e => setDescription(e.target.value)} className="w-full h-20 bg-neutral-bg/50 border-b border-border-light focus:border-primary-container outline-none resize-none" placeholder="请输入产品描述" /></div>
            <div className="space-y-1"><label className="text-xs text-secondary">产品类目</label><select value={category} onChange={e => setCategory(e.target.value)} className="w-full h-12 bg-neutral-bg/50 border-b border-border-light outline-none"><option>大健康 - 营养膳食</option><option>护肝解酒</option><option>助眠安神</option><option>滋补养生</option></select></div>
          </div>
        </section>

        <section className="bg-white rounded-2xl p-4 border border-border-light shadow-sm space-y-4">
          <h2 className="font-bold text-lg">价格与库存</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1"><label className="text-xs text-secondary">产品价格 (元)</label><input value={price} onChange={e => setPrice(e.target.value)} className="w-full h-12 bg-neutral-bg/50 border-b border-border-light outline-none" placeholder="0.00" type="number" /></div>
            <div className="space-y-1"><label className="text-xs text-secondary">分润比例(%)</label><input value={earnPerShare} onChange={e => setEarnPerShare(e.target.value)} className="w-full h-12 bg-neutral-bg/50 border-b border-border-light outline-none" placeholder="0.00" type="number" /></div>
            <div className="col-span-2 space-y-1"><label className="text-xs text-secondary">产品库存</label><input value={stock} onChange={e => setStock(e.target.value)} className="w-full h-12 bg-neutral-bg/50 border-b border-border-light outline-none" placeholder="请输入库存数量" type="number" /></div>
          </div>
        </section>

        <section className="bg-white rounded-2xl p-4 border border-border-light shadow-sm space-y-4">
          <h2 className="font-bold text-lg">规格选项</h2>
          <div className="p-3 bg-neutral-bg rounded-xl border border-border-light flex justify-between items-center">
            <div className="space-y-1"><p className="font-bold">标准装</p><p className="text-primary-container font-bold">¥{price || '0'}</p></div>
            <button className="text-error"><Minus className="w-5 h-5" /></button>
          </div>
          <button className="w-full py-3 border-2 border-dashed border-border-light rounded-xl text-secondary flex items-center justify-center gap-2 font-bold text-sm"><Plus className="w-5 h-5" />添加规格</button>
        </section>

        <section className="bg-white rounded-2xl p-4 border border-border-light shadow-sm space-y-4">
          <h2 className="font-bold text-lg">产品主图</h2>
          <div className="grid grid-cols-3 gap-3">
            <div className="aspect-square rounded-xl bg-slate-100 flex items-center justify-center border-2 border-dashed border-border-light"><Camera className="text-slate-400" /></div>
          </div>
        </section>

        <section className="bg-white rounded-2xl p-4 border border-border-light shadow-sm space-y-4">
          <h2 className="font-bold text-lg">推广分润比例</h2>
          <div className="bg-sky-50 p-4 rounded-xl border border-sky-100">
            <p className="text-xs">设置推广分润比例（百分比），推广员推广该产品可获得 <span className="text-xl font-bold text-primary-container font-manrope">{earnPerShare || '5'}</span>% 的分润</p>
          </div>
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <Percent className="w-3.5 h-3.5" />
            推广员每成交一单 = 销售额 × {earnPerShare || '5'}%
          </div>
        </section>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 p-4 bg-white/80 backdrop-blur-md border-t border-border-light">
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="w-full h-12 bg-primary-container text-white font-bold rounded-xl shadow-lg active:scale-95 transition-transform disabled:opacity-60"
        >
          {loading ? '提交中...' : '提交上架'}
        </button>
      </footer>
    </div>
  );
});
