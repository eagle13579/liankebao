/**
 * 智能推荐页面
 * ============
 * Tab切换: 热门推荐 / 个性化推荐
 * 调用 GET /api/v1/recommend/hot 和 /api/v1/recommend/personalized/{user_id}
 */

import React, { useEffect, useState } from 'react';

// ============================================================
// 类型定义
// ============================================================
interface RecommendProduct {
  id: number;
  name?: string;
  title?: string;
  description?: string;
  price?: number;
  category?: string;
  images?: string;
  tags?: string;
  match_score?: number;
  match_reasons?: string[];
  strategy?: string;
  brand?: string;
  sale_price?: number;
}

interface RecommendResponse {
  code: number;
  message: string;
  data?: {
    items: RecommendProduct[];
    total: number;
    strategy?: string;
  };
}

// ============================================================
// 工具函数
// ============================================================
const API_BASE = '';

async function fetchJson<T>(url: string): Promise<T> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const res = await fetch(API_BASE + url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  const json: T = await res.json();
  return json;
}

function getUserId(): number {
  try {
    const stored = localStorage.getItem('user');
    if (stored) {
      const user = JSON.parse(stored);
      return user.id || 0;
    }
  } catch { /* ignore */ }
  return 0;
}

function getProductName(item: RecommendProduct): string {
  return item.name || item.title || '未命名产品';
}

function getProductImage(item: RecommendProduct): string {
  if (item.images) {
    const imgs = item.images.split(',').map(s => s.trim()).filter(Boolean);
    if (imgs.length > 0) return imgs[0];
  }
  return '';
}

function getProductCategory(item: RecommendProduct): string {
  return item.category || '未分类';
}

function getMatchReasons(item: RecommendProduct): string[] {
  if (item.match_reasons && item.match_reasons.length > 0) return item.match_reasons;
  if (item.tags) return item.tags.split(',').map(s => s.trim()).filter(Boolean);
  return [];
}

// ============================================================
// 主组件
// ============================================================
export default function RecommendPage() {
  const [activeTab, setActiveTab] = useState<'hot' | 'personalized'>('hot');
  const [items, setItems] = useState<RecommendProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<string>('');

  const fetchData = async (tab: 'hot' | 'personalized') => {
    setLoading(true);
    setError(null);
    try {
      let url: string;
      if (tab === 'hot') {
        url = '/api/v1/recommend/hot?limit=20';
      } else {
        const userId = getUserId();
        if (!userId) throw new Error('请先登录后再查看个性化推荐');
        url = `/api/v1/recommend/personalized/${userId}?limit=20`;
      }

      const json = await fetchJson<RecommendResponse>(url);
      if (json.code === 200 && json.data) {
        setItems(json.data.items || []);
        setStrategy(json.data.strategy || '');
      } else {
        throw new Error(json.message || '获取推荐列表失败');
      }
    } catch (err: any) {
      setError(err.message || '网络错误，请稍后重试');
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(activeTab);
  }, [activeTab]);

  return (
    <div className="min-h-screen bg-neutral-bg">
      {/* 页面标题 */}
      <div className="bg-surface border-b border-border-light">
        <div className="max-w-4xl mx-auto px-4 pt-6 pb-4">
          <h1 className="text-2xl font-bold text-on-surface font-manrope">智能推荐</h1>
          <p className="text-sm text-text-muted mt-1">AI 驱动的高效匹配，发现适合您的商业机会</p>
        </div>

        {/* Tab 切换 */}
        <div className="max-w-4xl mx-auto px-4 flex gap-6 border-b border-border-light">
          <button
            onClick={() => setActiveTab('hot')}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'hot'
                ? 'border-primary text-primary'
                : 'border-transparent text-text-muted hover:text-on-surface'
            }`}
          >
            🔥 热门推荐
          </button>
          <button
            onClick={() => setActiveTab('personalized')}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'personalized'
                ? 'border-primary text-primary'
                : 'border-transparent text-text-muted hover:text-on-surface'
            }`}
          >
            ✨ 个性化推荐
          </button>
        </div>
      </div>

      {/* 内容区 */}
      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* 策略提示 */}
        {strategy && !loading && !error && items.length > 0 && (
          <div className="mb-4 px-4 py-2 bg-primary-light/50 rounded-lg text-xs text-primary">
            {activeTab === 'hot'
              ? '📊 基于近7天用户浏览数据聚合的热门产品'
              : strategy === 'personalized'
                ? '🎯 根据您的浏览和搜索偏好智能匹配'
                : '📊 暂无行为数据，为您展示热门产品'
            }
          </div>
        )}

        {/* 加载态 */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
            <span className="ml-3 text-sm text-text-muted">加载中...</span>
          </div>
        )}

        {/* 错误态 */}
        {!loading && error && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-16 h-16 bg-error/10 rounded-full flex items-center justify-center mb-4">
              <span className="text-3xl">⚠️</span>
            </div>
            <p className="text-sm text-error mb-3">{error}</p>
            <button
              onClick={() => fetchData(activeTab)}
              className="px-4 py-2 bg-primary text-white text-sm rounded-lg hover:bg-primary-container transition-colors"
            >
              重新加载
            </button>
          </div>
        )}

        {/* 空态 */}
        {!loading && !error && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
              <span className="text-3xl">📭</span>
            </div>
            <p className="text-sm text-text-muted">暂无推荐内容</p>
            <p className="text-xs text-text-muted mt-1">稍后再来看看吧</p>
          </div>
        )}

        {/* 产品卡片列表 */}
        {!loading && !error && items.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map((item) => (
              <ProductCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// 产品卡片子组件
// ============================================================
function ProductCard({ item }: { item: RecommendProduct }) {
  const imgUrl = getProductImage(item);
  const reasons = getMatchReasons(item);

  return (
    <div className="bg-surface rounded-xl border border-border-light overflow-hidden hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 group">
      {/* 图片区域 */}
      <div className="aspect-video bg-sky-gradient-light flex items-center justify-center overflow-hidden relative">
        {imgUrl ? (
          <img
            src={imgUrl}
            alt={getProductName(item)}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
              (e.target as HTMLImageElement).parentElement!.classList.add('flex', 'items-center', 'justify-center');
            }}
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-text-muted">
            <span className="text-3xl mb-1">📦</span>
            <span className="text-xs">暂无图片</span>
          </div>
        )}
        {/* 匹配度徽章 */}
        {item.match_score !== undefined && item.match_score > 0 && (
          <div className="absolute top-2 right-2 px-2 py-0.5 bg-primary/90 text-white text-[10px] font-medium rounded-full">
            {(item.match_score * 100).toFixed(0)}% 匹配
          </div>
        )}
      </div>

      {/* 信息区域 */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="text-sm font-semibold text-on-surface line-clamp-1 flex-1">
            {getProductName(item)}
          </h3>
          <span className="shrink-0 text-[10px] px-2 py-0.5 bg-primary-light/60 text-primary rounded-full font-medium">
            {getProductCategory(item)}
          </span>
        </div>

        {item.description && (
          <p className="text-xs text-text-muted line-clamp-2 mb-3">
            {item.description}
          </p>
        )}

        {/* 价格 */}
        {(item.price || item.sale_price) && (
          <div className="mb-3">
            {item.sale_price ? (
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-error">¥{item.sale_price}</span>
                {item.price && item.price > item.sale_price && (
                  <span className="text-xs text-text-muted line-through">¥{item.price}</span>
                )}
              </div>
            ) : (
              <span className="text-sm font-bold text-on-surface">¥{item.price}</span>
            )}
          </div>
        )}

        {/* 推荐理由标签 */}
        {reasons.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {reasons.slice(0, 3).map((reason, idx) => (
              <span
                key={idx}
                className="text-[10px] px-2 py-0.5 bg-slate-100 text-text-muted rounded-full"
              >
                {reason}
              </span>
            ))}
            {reasons.length > 3 && (
              <span className="text-[10px] text-text-muted">+{reasons.length - 3}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
