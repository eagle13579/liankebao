/**
 * 链客宝 - 评价表单
 * ===================
 * 匹配成功/联系后，评价匹配质量
 * 维度: 匹配准确度(1-5星) + 文字评价
 * 数据可用于后续训练CTR模型
 */

import React, { useState } from 'react';
import { Star, MessageSquare, Send } from 'lucide-react';
import type { ReviewData } from '../api-matching';
import { submitReview, getReviewForMatch } from '../api-matching';

interface Props {
  matchId: number;
  matchTitle: string;
  onClose?: () => void;
}

export default function ReviewFormModal({ matchId, matchTitle, onClose }: Props) {
  const existing = getReviewForMatch(matchId);
  const [accuracy, setAccuracy] = useState(existing?.accuracy || 5);
  const [comment, setComment] = useState(existing?.comment || '');
  const [hoverRating, setHoverRating] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = () => {
    if (accuracy < 1 || accuracy > 5) {
      setError('请选择评分');
      return;
    }
    const review: ReviewData = {
      match_id: matchId,
      title: matchTitle,
      accuracy,
      comment: comment.trim(),
      created_at: new Date().toISOString(),
    };
    submitReview(review);
    setSubmitted(true);
    setError(null);
  };

  if (submitted) {
    return (
      <div className="p-6 bg-white border border-gray-200 rounded-xl text-center">
        <Star className="w-10 h-10 text-yellow-400 fill-yellow-400 mx-auto mb-2" />
        <p className="text-gray-800 font-medium">评价已提交</p>
        <p className="text-xs text-gray-400 mt-1">感谢您的反馈，这将帮助我们优化匹配质量</p>
        {onClose && (
          <button
            onClick={onClose}
            className="mt-3 px-4 py-1.5 text-sm bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
          >
            关闭
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="p-4 bg-white border border-gray-200 rounded-xl">
      <div className="flex items-center gap-2 mb-3">
        <MessageSquare className="w-4 h-4 text-blue-500" />
        <h3 className="text-sm font-medium text-gray-800">评价匹配质量</h3>
      </div>

      <p className="text-xs text-gray-500 mb-3 truncate">{matchTitle}</p>

      {/* Star rating */}
      <div className="mb-3">
        <label className="text-xs text-gray-500 block mb-1.5">匹配准确度</label>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              type="button"
              onClick={() => setAccuracy(star)}
              onMouseEnter={() => setHoverRating(star)}
              onMouseLeave={() => setHoverRating(0)}
              className="p-0.5 transition-transform hover:scale-110"
            >
              <Star
                className={`w-6 h-6 ${
                  star <= (hoverRating || accuracy)
                    ? 'text-yellow-400 fill-yellow-400'
                    : 'text-gray-300'
                }`}
              />
            </button>
          ))}
          <span className="text-xs text-gray-400 ml-2 self-center">
            {accuracy === 1 && '很不准确'}
            {accuracy === 2 && '不太准确'}
            {accuracy === 3 && '一般'}
            {accuracy === 4 && '比较准确'}
            {accuracy === 5 && '非常准确'}
          </span>
        </div>
      </div>

      {/* Comment */}
      <div className="mb-3">
        <label className="text-xs text-gray-500 block mb-1.5">文字评价（选填）</label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="说说这个匹配结果如何..."
          rows={3}
          className="w-full text-sm border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-400 resize-none"
        />
      </div>

      {/* Error */}
      {error && <p className="text-xs text-red-500 mb-2">{error}</p>}

      {/* Submit */}
      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
          提交评价
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            取消
          </button>
        )}
      </div>

      {/* TODO: 提交评价数据至数据库，用于CTR模型训练 */}

    </div>
  );
}
