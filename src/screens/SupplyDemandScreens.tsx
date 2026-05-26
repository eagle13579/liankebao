import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { api } from '../api/client';
import type { NeedItem } from '../types';

// Icons
const ArrowLeft = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 18l-6-6 6-6" />
  </svg>
);
const Plus = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);
const MapPin = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
  </svg>
);
const Wallet = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="1" y="4" width="22" height="16" rx="2" ry="2" /><line x1="1" y1="10" x2="23" y2="10" />
  </svg>
);
const Clock = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
  </svg>
);
const Search = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const CATEGORIES = [
  { key: '', label: '全部' },
  { key: '大健康', label: '大健康' },
  { key: '企业服务', label: '企业服务' },
  { key: '科技产品', label: '科技产品' },
  { key: '教育培训', label: '教育培训' },
  { key: '消费品', label: '消费品' },
];

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  return d.toLocaleDateString('zh-CN');
}

export function SupplyDemandHall() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [needs, setNeeds] = useState<NeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState(searchParams.get('category') || '');
  const [searchText, setSearchText] = useState('');
  const pageSize = 20;

  const fetchNeeds = async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    params.set('page', String(page));
    params.set('page_size', String(pageSize));
    if (searchText) params.set('search', searchText);
    const res = await api.get<{ total: number; page: number; page_size: number; items: NeedItem[] }>(`/api/needs?${params.toString()}`);
    if (res.code === 200 && res.data) {
      setNeeds(res.data.items);
      setTotal(res.data.total);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchNeeds();
  }, [category, page]);

  const handleSearch = () => {
    setPage(1);
    fetchNeeds();
  };

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/50 via-white to-white font-sans pb-24">
      {/* Header */}
      <header className="sky-gradient px-4 pt-12 pb-6 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="bubble w-72 h-72 bg-white -top-20 -right-20" />
          <div className="bubble w-48 h-48 bg-white bottom-0 left-10" />
        </div>
        <div className="flex items-center gap-3 relative z-10 mb-4">
          <button onClick={() => navigate('/home')} className="w-9 h-9 flex items-center justify-center rounded-xl bg-white/20 text-white active:scale-90 transition-all">
            <ArrowLeft />
          </button>
          <div>
            <h1 className="text-xl font-extrabold text-white font-manrope">需求大厅</h1>
            <p className="text-xs text-white/70">发现商机 · 精准对接</p>
          </div>
        </div>

        {/* Search */}
        <div className="relative z-10 flex items-center gap-2 bg-white/20 backdrop-blur-sm rounded-2xl px-4 py-2.5">
          <Search />
          <input
            type="text"
            placeholder="搜索需求..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            className="flex-1 bg-transparent text-sm text-white placeholder-white/50 outline-none"
          />
        </div>
      </header>

      {/* Category Tabs */}
      <div className="sticky top-0 z-20 bg-white/90 backdrop-blur-xl border-b border-sky-100/50 px-4 py-3">
        <div className="flex gap-2 overflow-x-auto no-scrollbar">
          {CATEGORIES.map(cat => (
            <button
              key={cat.key}
              onClick={() => { setCategory(cat.key); setPage(1); }}
              className={`shrink-0 px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
                category === cat.key
                  ? 'bg-sky-500 text-white shadow-md shadow-sky-500/20'
                  : 'bg-sky-50 text-sky-600 hover:bg-sky-100'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-4 pt-3 space-y-3">
        {loading ? (
          <div className="space-y-3 pt-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm">
                <div className="skeleton h-5 w-3/4 rounded mb-3" />
                <div className="skeleton h-4 w-1/2 rounded mb-2" />
                <div className="skeleton h-4 w-1/3 rounded" />
              </div>
            ))}
          </div>
        ) : needs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <div className="w-16 h-16 rounded-full bg-sky-50 flex items-center justify-center mb-4">
              <Search />
            </div>
            <p className="text-sm">暂无相关需求</p>
            <p className="text-xs mt-1">发布一条需求，让更多伙伴找到你</p>
          </div>
        ) : (
          <>
            <div className="text-xs text-slate-400 px-1">共 {total} 条需求</div>
            <AnimatePresence mode="popLayout">
              {needs.map((need, i) => (
                <motion.div
                  key={need.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  onClick={() => navigate(`/supply-demand/${need.id}`, { state: { transition: 'push' } })}
                  className="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm cursor-pointer active:scale-[0.98] transition-all card-hover"
                >
                  {/* Top row */}
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="text-[15px] font-bold text-slate-800 leading-snug flex-1 mr-2 line-clamp-2">
                      {need.title}
                    </h3>
                    <span className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      need.status === 'open' ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'
                    }`}>
                      {need.status === 'open' ? '开放中' : '已关闭'}
                    </span>
                  </div>

                  {/* Tags row */}
                  <div className="flex flex-wrap items-center gap-2 mb-2.5">
                    {need.category && (
                      <span className="px-2 py-0.5 rounded-md bg-rose-50 text-rose-600 text-[11px] font-medium">
                        {need.category}
                      </span>
                    )}
                  </div>

                  {/* Info row */}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                    {need.budget && (
                      <span className="flex items-center gap-1">
                        <Wallet /> <span className="text-sky-600 font-medium">{need.budget}</span>
                      </span>
                    )}
                    {need.region && (
                      <span className="flex items-center gap-1">
                        <MapPin /> {need.region}
                      </span>
                    )}
                    <span className="flex items-center gap-1">
                      <Clock /> {formatTime(need.created_at)}
                    </span>
                  </div>

                  {/* User info */}
                  {need.user && (
                    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-50">
                      <div className="w-6 h-6 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center text-white text-[10px] font-bold">
                        {need.user.name?.[0] || '?'}
                      </div>
                      <span className="text-xs text-slate-500">{need.user.name}</span>
                      {need.user.company && (
                        <span className="text-[10px] text-slate-400">| {need.user.company}</span>
                      )}
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>

            {/* Load more */}
            {total > page * pageSize && (
              <button
                onClick={() => setPage(p => p + 1)}
                className="w-full py-3 text-sm text-sky-500 font-medium bg-sky-50 rounded-2xl active:scale-95 transition-all"
              >
                加载更多
              </button>
            )}
          </>
        )}
      </div>

      {/* FAB: 发布需求 */}
      <button
        onClick={() => navigate('/supply-demand/post', { state: { transition: 'slide_up' } })}
        className="fixed bottom-24 right-5 z-30 w-14 h-14 rounded-2xl bg-gradient-to-br from-rose-500 to-pink-600 text-white shadow-xl shadow-rose-500/30 flex items-center justify-center active:scale-90 transition-all"
      >
        <Plus />
      </button>
    </div>
  );
}

export function NeedDetail() {
  const navigate = useNavigate();
  const [need, setNeed] = useState<NeedItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPhone, setShowPhone] = useState(false);
  const pathParts = window.location.pathname.split('/');
  const needId = parseInt(pathParts[pathParts.length - 1]);

  useEffect(() => {
    const fetchDetail = async () => {
      setLoading(true);
      const res = await api.get<NeedItem>(`/api/needs/${needId}`);
      if (res.code === 200 && res.data) {
        setNeed(res.data);
      }
      setLoading(false);
    };
    if (needId) fetchDetail();
  }, [needId]);

  if (loading) {
    return (
      <div className="flex flex-col min-h-screen bg-white font-sans">
        <header className="sky-gradient px-4 pt-12 pb-6">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="w-9 h-9 flex items-center justify-center rounded-xl bg-white/20 text-white active:scale-90 transition-all">
              <ArrowLeft />
            </button>
            <h1 className="text-xl font-extrabold text-white font-manrope">需求详情</h1>
          </div>
        </header>
        <div className="p-4 space-y-4">
          <div className="skeleton h-6 w-3/4 rounded" />
          <div className="skeleton h-4 w-1/2 rounded" />
          <div className="skeleton h-20 w-full rounded" />
        </div>
      </div>
    );
  }

  if (!need) {
    return (
      <div className="flex flex-col min-h-screen bg-white font-sans">
        <header className="sky-gradient px-4 pt-12 pb-6">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate('/supply-demand')} className="w-9 h-9 flex items-center justify-center rounded-xl bg-white/20 text-white active:scale-90 transition-all">
              <ArrowLeft />
            </button>
            <h1 className="text-xl font-extrabold text-white font-manrope">需求不存在</h1>
          </div>
        </header>
        <div className="flex flex-col items-center justify-center py-20 text-slate-400">
          <p>该需求已删除或不存在</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 font-sans pb-24">
      {/* Header */}
      <header className="sky-gradient px-4 pt-12 pb-8 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="bubble w-72 h-72 bg-white -top-20 -right-20" />
          <div className="bubble w-48 h-48 bg-white bottom-0 left-10" />
        </div>
        <div className="flex items-center gap-3 relative z-10">
          <button onClick={() => navigate(-1)} className="w-9 h-9 flex items-center justify-center rounded-xl bg-white/20 text-white active:scale-90 transition-all">
            <ArrowLeft />
          </button>
          <div>
            <h1 className="text-xl font-extrabold text-white font-manrope">需求详情</h1>
          </div>
        </div>
      </header>

      <div className="px-4 -mt-4 space-y-3">
        {/* Main card */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
          {/* Status + Category */}
          <div className="flex items-center gap-2 mb-3">
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
              need.status === 'open' ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'
            }`}>
              {need.status === 'open' ? '开放中' : '已关闭'}
            </span>
            {need.category && (
              <span className="px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-600 text-[10px] font-bold">
                {need.category}
              </span>
            )}
          </div>

          <h2 className="text-lg font-extrabold text-slate-800 mb-4">{need.title}</h2>

          {need.description && (
            <div className="mb-4">
              <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">{need.description}</p>
            </div>
          )}

          {/* Detail info */}
          <div className="space-y-2.5 bg-sky-50/50 rounded-xl p-4">
            <div className="flex items-center gap-3 text-sm">
              <Wallet />
              <span className="text-slate-500">预算：</span>
              <span className="text-sky-600 font-bold">{need.budget || '面议'}</span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <MapPin />
              <span className="text-slate-500">地区：</span>
              <span className="text-slate-700">{need.region || '不限'}</span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <Clock />
              <span className="text-slate-500">发布时间：</span>
              <span className="text-slate-700">{new Date(need.created_at).toLocaleString('zh-CN')}</span>
            </div>
          </div>
        </div>

        {/* Contact card */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
          <h3 className="text-sm font-bold text-slate-700 mb-3">联系方式</h3>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-rose-400 to-pink-500 flex items-center justify-center text-white text-sm font-bold">
              {need.contact_name[0]}
            </div>
            <div>
              <p className="text-sm font-bold text-slate-800">{need.contact_name}</p>
              <p className="text-xs text-slate-400">发布者</p>
            </div>
          </div>
          {showPhone && need.contact_phone ? (
            <a
              href={`tel:${need.contact_phone}`}
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-gradient-to-r from-rose-500 to-pink-600 text-white text-sm font-bold shadow-md shadow-rose-500/20 active:scale-95 transition-all"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" /></svg>
              {need.contact_phone}
            </a>
          ) : (
            <button
              onClick={() => setShowPhone(true)}
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-gradient-to-r from-rose-500 to-pink-600 text-white text-sm font-bold shadow-md shadow-rose-500/20 active:scale-95 transition-all"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" /></svg>
              查看联系方式
            </button>
          )}

          {/* Back button */}
          <button
            onClick={() => navigate('/supply-demand')}
            className="w-full py-3 mt-3 rounded-xl bg-sky-50 text-sky-600 text-sm font-bold active:scale-95 transition-all"
          >
            返回需求大厅
          </button>
        </div>
      </div>
    </div>
  );
}
