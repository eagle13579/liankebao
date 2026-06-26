/**
 * 链客宝 - 匹配评价组件 (服务端版)
 * ===================================
 * 1-5 星评价 + 文字评价 → POST /api/recommend/feedback {action: "rate", score, comment}
 * 与 ReviewFormModal (localStorage 版) 并存，优先走服务端
 */

import React, { useState } from 'react';
import { Star, MessageSquare, Send, CheckCircle2 } from 'lucide-react';
import { submitRatingFeedback } from '../api-matching';

interface Props {
  matchId: number;
  matchTitle: string;
  productId?: number;
  onClose?: () => void;
  onSubmitted?: () => void;
}

const LABELS: Record<number, string> = {
  1: '很不准确',
  2: '不太准确',
  3: '一般',
  4: '比较准确',
  5: '非常准确',
};

export default function MatchRating({ matchId, matchTitle, productId, onClose, onSubmitted }: Props) {
  const [score, setScore] = useState(5);
  const [hoverRating, setHoverRating] = useState(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (score < 1 || score > 5) {
      setError('请选择评分');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const ok = await submitRatingFeedback({
        matchId,
        productId: productId ?? matchId,
        score,
        comment: comment.trim() || undefined,
      });
      if (ok) {
        setSubmitted(true);
        onSubmitted?.();
      } else {
        setError('提交失败，请稍后重试');
      }
    } catch (e: any) {
      setError(e.message || '提交异常');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="p-4 bg-white border border-green-200 rounded-xl text-center">
        <CheckCircle2 className="w-8 h-8 text-green-500 mx-auto mb-2" />
        <p className="text-gray-800 font-medium text-sm">评价已提交</p>
        <p className="text-xs text-gray-400 mt-1">感谢反馈，匹配算法将持续优化</p>
        {onClose && (
          <button
            onClick={onClose}
            className="mt-2 px-3 py-1 text-xs bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
          >
            关闭
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="p-3 bg-white border border-gray-200 rounded-xl">
      <div className="flex items-center gap-1.5 mb-2">
        <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
        <h3 className="text-xs font-medium text-gray-800">评价匹配质量</h3>
      </div>

      <p className="text-xs text-gray-500 mb-2 truncate">{matchTitle}</p>

      {/* Star rating */}
      <div className="mb-2">
        <label className="text-xs text-gray-500 block mb-1">匹配准确度</label>
        <div className="flex gap-0.5">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              type="button"
              onClick={() => setScore(star)}
              onMouseEnter={() => setHoverRating(star)}
              onMouseLeave={() => setHoverRating(0)}
              className="p-0.5 transition-transform hover:scale-110"
            >
              <Star
                className={`w-5 h-5 ${
                  star <= (hoverRating || score)
                    ? 'text-yellow-400 fill-yellow-400'
                    : 'text-gray-300'
                }`}
              />
            </button>
          ))}
          <span className="text-xs text-gray-400 ml-1 self-center">
            {LABELS[hoverRating || score]}
          </span>
        </div>
      </div>

      {/* Comment */}
      <div className="mb-2">
        <label className="text-xs text-gray-500 block mb-0.5">文字评价（选填）</label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="这个匹配结果如何？"
          rows={2}
          className="w-full text-xs border border-gray-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-400 resize-none"
        />
      </div>

      {/* Error */}
      {error && <p className="text-xs text-red-500 mb-1.5">{error}</p>}

      {/* Submit */}
      <div className="flex gap-1.5">
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {submitting ? (
            '提交中...'
          ) : (
            <>
              <Send className="w-3 h-3" />
              提交评价
            </>
          )}
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
          >
            取消
          </button>
        )}
      </div>
    </div>
  );
}
