import { useState } from 'react';
import {
  Users,
  Loader2,
  ThumbsUp,
  ThumbsDown,
  Star,
  MessageSquare,
  Phone,
} from 'lucide-react';
import type { MatchItem } from '../types';
import {
  isFavorite,
  saveToFavorites,
  removeFromFavorites,
  markContacted,
  isContacted,
  getReviewForMatch,
} from '../api-matching';
import ReviewFormModal from './ReviewFormModal';
import MatchRating from './MatchRating';

interface Props {
  items: MatchItem[];
  loading: boolean;
  onCreditsChange?: () => void;
}

const API_BASE = '';

async function submitFeedback(productId: number, action: 'like' | 'dislike') {
  try {
    const resp = await fetch(`${API_BASE}/api/recommend/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: 0,
        product_id: productId,
        action,
        source: 'match_card',
      }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

export default function MatchResultsPanel({ items, loading, onCreditsChange }: Props) {
  const [feedbacks, setFeedbacks] = useState<Record<number, 'like' | 'dislike'>>({});
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<number | null>(null);
  const [reviewMode, setReviewMode] = useState<'server' | 'local'>('server');

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2500);
  };

  const handleFeedback = async (productId: number, action: 'like' | 'dislike') => {
    if (feedbacks[productId] === action) return;
    const ok = await submitFeedback(productId, action);
    if (ok) {
      setFeedbacks(prev => ({ ...prev, [productId]: action }));
      showToast('已记录反馈，下次匹配会更准');
    } else {
      showToast('反馈提交失败，请稍后重试');
    }
  };

  const handleToggleFavorite = (item: MatchItem) => {
    if (isFavorite(item.id)) {
      removeFromFavorites(item.id);
      showToast('已取消收藏');
    } else {
      saveToFavorites({
        match_id: item.id,
        title: item.name,
        match_score: item.match_score,
        saved_at: new Date().toISOString(),
        direction: 'need_to_product',
        description: `${item.position} @ ${item.company}`,
      });
      showToast('已收藏');
    }
  };

  const handleContact = (item: MatchItem) => {
    markContacted(item.id);
    showToast('已标记为已联系');
  };

  if (loading)
    return (
      <div className="flex justify-center p-8">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  if (items.length === 0) return null;

  return (
    <div className="mx-4 mb-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
        <Users className="w-5 h-5" />
        匹配推荐 ({items.length})
      </h3>

      <div className="space-y-3">
        {items.map((item) => {
          const fav = isFavorite(item.id);
          const contacted = isContacted(item.id);
          const review = getReviewForMatch(item.id);
          return (
            <div
              key={item.id}
              className="p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md transition-shadow"
            >
              {/* Header */}
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="font-medium text-gray-800">{item.name}</h4>
                  <p className="text-sm text-gray-500">
                    {item.position} @ {item.company}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {/* Favorite star */}
                  <button
                    onClick={() => handleToggleFavorite(item)}
                    className="p-1 rounded-lg hover:bg-yellow-50 transition-colors"
                    title={fav ? '取消收藏' : '收藏'}
                  >
                    <Star
                      className={`w-4 h-4 ${
                        fav ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300 hover:text-yellow-400'
                      }`}
                    />
                  </button>
                  <div className="text-sm font-medium text-blue-600">
                    {Math.round(item.match_score * 100)}% 匹配
                  </div>
                </div>
              </div>

              {/* Tags */}
              {item.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {item.tags.map((t, i) => (
                    <span
                      key={i}
                      className="px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {/* Common contacts */}
              {item.common_contacts > 0 && (
                <p className="text-xs text-green-600 mt-1">
                  {item.common_contacts} 个共同联系人
                </p>
              )}

              {/* Action bar */}
              <div className="flex items-center gap-2 mt-3 pt-2 border-t border-gray-100 flex-wrap">
                {/* Like/Dislike */}
                <button
                  onClick={() => handleFeedback(item.id, 'like')}
                  className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-full transition-colors ${
                    feedbacks[item.id] === 'like'
                      ? 'bg-green-100 text-green-700 border border-green-300'
                      : 'bg-gray-50 text-gray-500 border border-gray-200 hover:bg-green-50 hover:text-green-600'
                  }`}
                >
                  <ThumbsUp className="w-3.5 h-3.5" /> 喜欢
                </button>
                <button
                  onClick={() => handleFeedback(item.id, 'dislike')}
                  className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-full transition-colors ${
                    feedbacks[item.id] === 'dislike'
                      ? 'bg-red-100 text-red-700 border border-red-300'
                      : 'bg-gray-50 text-gray-500 border border-gray-200 hover:bg-red-50 hover:text-red-600'
                  }`}
                >
                  <ThumbsDown className="w-3.5 h-3.5" /> 不喜欢
                </button>

                {/* Contact */}
                <button
                  onClick={() => handleContact(item)}
                  className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-full transition-colors ${
                    contacted
                      ? 'bg-green-100 text-green-700 border border-green-300'
                      : 'bg-gray-50 text-gray-500 border border-gray-200 hover:bg-green-50 hover:text-green-600'
                  }`}
                >
                  <Phone className="w-3.5 h-3.5" />
                  {contacted ? '已联系' : '标记联系'}
                </button>

                {/* Review */}
                <button
                  onClick={() => setReviewingId(reviewingId === item.id ? null : item.id)}
                  className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-full transition-colors ${
                    review
                      ? 'bg-purple-100 text-purple-700 border border-purple-300'
                      : 'bg-gray-50 text-gray-500 border border-gray-200 hover:bg-purple-50 hover:text-purple-600'
                  }`}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  {review ? `已评价(${review.accuracy}★)` : '评价'}
                </button>
              </div>

              {/* Review form (inline) */}
              {reviewingId === item.id && (
                <div className="mt-3 space-y-2">
                  {/* Tab toggle: localStorage vs server */}
                  <div className="flex gap-1 border-b border-gray-100 pb-1">
                    <button
                      onClick={() => setReviewMode('server')}
                      className={`text-xs px-2 py-0.5 rounded-t transition-colors ${
                        reviewMode === 'server'
                          ? 'bg-blue-50 text-blue-600 border border-b-white border-gray-200'
                          : 'text-gray-400 hover:text-gray-600'
                      }`}
                    >
                      服务端提交
                    </button>
                    <button
                      onClick={() => setReviewMode('local')}
                      className={`text-xs px-2 py-0.5 rounded-t transition-colors ${
                        reviewMode === 'local'
                          ? 'bg-blue-50 text-blue-600 border border-b-white border-gray-200'
                          : 'text-gray-400 hover:text-gray-600'
                      }`}
                    >
                      本地保存
                    </button>
                  </div>
                  {reviewMode === 'server' ? (
                    <MatchRating
                      matchId={item.id}
                      matchTitle={item.name}
                      productId={item.id}
                      onClose={() => { setReviewingId(null); setReviewMode('server'); }}
                      onSubmitted={() => setReviewingId(null)}
                    />
                  ) : (
                    <ReviewFormModal
                      matchId={item.id}
                      matchTitle={item.name}
                      onClose={() => setReviewingId(null)}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Toast */}
      {toastMsg && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-gray-800 text-white text-sm rounded-lg shadow-lg transition-opacity">
          {toastMsg}
        </div>
      )}
    </div>
  );
}
