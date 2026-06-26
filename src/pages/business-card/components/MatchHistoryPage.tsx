/**
 * 链客宝 - 匹配历史页面
 * =======================
 * 用户查看所有匹配记录（need→products 和 product→needs）
 * 列表：匹配时间、对方名称、匹配分、是否已联系、状态
 * 详情：展开查看匹配理由、产品描述、联系信息
 */

import React, { useState, useCallback } from 'react';
import {
  History,
  Star,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Phone,
  User,
  Mail,
  Clock,
  TrendingUp,
} from 'lucide-react';
import type { MatchHistoryItem } from '../api-matching';
import { fetchMatchHistory, isFavorite, isContacted } from '../api-matching';

interface Props {
  userId?: number;
}

const PAGE_SIZE = 20;

export default function MatchHistoryPage({ userId }: Props) {
  const [items, setItems] = useState<MatchHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [direction, setDirection] = useState<'need_to_product' | 'product_to_need'>('need_to_product');

  const loadHistory = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchMatchHistory(userId, direction, 0, PAGE_SIZE);
      setItems(result.items);
      setTotal(result.total);
    } catch (e: any) {
      setError(e.message || '加载匹配历史失败');
    } finally {
      setLoading(false);
    }
  }, [userId, direction]);

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '—';
    try {
      const d = new Date(dateStr);
      return d.toLocaleString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-gray-100">
        <div className="max-w-4xl mx-auto px-4 py-3">
          <div className="flex items-center gap-3">
            <History className="w-5 h-5 text-blue-600" />
            <h1 className="text-lg font-semibold text-gray-800">匹配历史</h1>
            <span className="text-sm text-gray-400 ml-1">
              {total > 0 ? `共 ${total} 条` : ''}
            </span>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-4">
        {/* Direction toggle */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setDirection('need_to_product')}
            className={`px-4 py-2 text-sm rounded-lg transition-colors ${
              direction === 'need_to_product'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            我的需求匹配产品
          </button>
          <button
            onClick={() => setDirection('product_to_need')}
            className={`px-4 py-2 text-sm rounded-lg transition-colors ${
              direction === 'product_to_need'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            我的产品匹配需求
          </button>
          <button
            onClick={loadHistory}
            disabled={loading || !userId}
            className="ml-auto px-4 py-2 text-sm bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors disabled:opacity-50"
          >
            {loading ? '加载中...' : '加载历史'}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="p-3 mb-4 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">{error}</div>
        )}

        {/* Empty state */}
        {!loading && items.length === 0 && !error && (
          <div className="text-center py-16 text-gray-400">
            <History className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-sm">暂无匹配记录</p>
            <p className="text-xs mt-1">点击「加载历史」查看您的匹配记录</p>
          </div>
        )}

        {/* Match list */}
        {items.length > 0 && (
          <div className="space-y-3">
            {items.map((item) => {
              const expanded = expandedIds.has(item.id);
              const fav = isFavorite(item.id);
              const contacted = isContacted(item.id);
              return (
                <div
                  key={item.id}
                  className="bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition-shadow"
                >
                  {/* Summary row */}
                  <div
                    className="p-4 flex items-start gap-3 cursor-pointer"
                    onClick={() => toggleExpand(item.id)}
                  >
                    {/* Match score badge */}
                    <div
                      className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold ${
                        item.match_score >= 0.7
                          ? 'bg-green-100 text-green-700'
                          : item.match_score >= 0.4
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {Math.round(item.match_score * 100)}%
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-gray-800 truncate">{item.title}</h3>
                      {item.category && (
                        <span className="inline-block px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full mt-1">
                          {item.category}
                        </span>
                      )}
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDate(item.matched_at)}
                        </span>
                        {contacted ? (
                          <span className="text-green-600 flex items-center gap-1">
                            <Phone className="w-3 h-3" />
                            已联系
                          </span>
                        ) : (
                          <span className="text-gray-400">未联系</span>
                        )}
                      </div>
                    </div>

                    {/* Status indicators */}
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {fav && <Star className="w-4 h-4 text-yellow-400 fill-yellow-400" />}
                      {expanded ? (
                        <ChevronUp className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      )}
                    </div>
                  </div>

                  {/* Expanded detail */}
                  {expanded && (
                    <div className="px-4 pb-4 pt-0 border-t border-gray-100">
                      {item.description && (
                        <div className="mt-3">
                          <h4 className="text-xs font-medium text-gray-500 mb-1">描述</h4>
                          <p className="text-sm text-gray-700">{item.description}</p>
                        </div>
                      )}
                      {item.match_reasons.length > 0 && (
                        <div className="mt-3">
                          <h4 className="text-xs font-medium text-gray-500 mb-1">匹配理由</h4>
                          <div className="flex flex-wrap gap-1">
                            {item.match_reasons.map((r, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 bg-purple-50 text-purple-600 text-xs rounded-full"
                              >
                                {r}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="mt-3 flex items-center gap-2 text-xs">
                        <span className="text-gray-400 flex items-center gap-1">
                          <TrendingUp className="w-3 h-3" />
                          策略: {item.strategy || 'v2'}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
