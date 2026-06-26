/**
 * 链客宝 - 收藏列表
 * ===================
 * 展示所有收藏的匹配项目
 * TODO: Favorite表存在时改用 POST /api/favorites 数据库接口
 */

import React, { useState, useEffect } from 'react';
import { Star, Trash2, Clock, TrendingUp } from 'lucide-react';
import type { FavoriteItem } from '../api-matching';
import { getFavorites, removeFromFavorites } from '../api-matching';

export default function FavoritesPanel() {
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  useEffect(() => {
    setFavorites(getFavorites());
  }, []);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2000);
  };

  const handleRemove = (matchId: number) => {
    removeFromFavorites(matchId);
    setFavorites(getFavorites());
    showToast('已取消收藏');
  };

  const formatDate = (dateStr: string) => {
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
    <div className="mx-4 mb-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
        <Star className="w-5 h-5 text-yellow-400 fill-yellow-400" />
        收藏列表 ({favorites.length})
      </h3>

      {favorites.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          <Star className="w-10 h-10 mx-auto mb-2 opacity-50" />
          <p className="text-sm">暂无收藏</p>
          <p className="text-xs mt-1">在匹配结果中点击星标即可收藏</p>
        </div>
      ) : (
        <div className="space-y-2">
          {favorites.map((fav) => (
            <div
              key={fav.match_id}
              className="p-3 bg-white border border-gray-200 rounded-xl hover:shadow-md transition-shadow flex items-start gap-3"
            >
              {/* Score badge */}
              <div
                className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold ${
                  fav.match_score >= 0.7
                    ? 'bg-green-100 text-green-700'
                    : fav.match_score >= 0.4
                    ? 'bg-yellow-100 text-yellow-700'
                    : 'bg-gray-100 text-gray-500'
                }`}
              >
                {Math.round(fav.match_score * 100)}%
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <h4 className="font-medium text-gray-800 text-sm truncate">{fav.title}</h4>
                <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDate(fav.saved_at)}
                  </span>
                  <span className="flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" />
                    {fav.direction === 'need_to_product' ? '需求→产品' : '产品→需求'}
                  </span>
                </div>
              </div>

              {/* Remove button */}
              <button
                onClick={() => handleRemove(fav.match_id)}
                className="flex-shrink-0 p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                title="取消收藏"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Toast */}
      {toastMsg && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-gray-800 text-white text-sm rounded-lg shadow-lg">
          {toastMsg}
        </div>
      )}

      {/* TODO: 数据库迁移 */}

    </div>
  );
}
