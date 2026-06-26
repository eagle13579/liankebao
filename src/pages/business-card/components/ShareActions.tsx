import { Share2, Copy, Check, Sparkles, Zap, AlertTriangle } from 'lucide-react';

interface Props {
  shareUrl: string;
  copied: boolean;
  matchLoading: boolean;
  onCopy: () => void;
  onMatch: () => void;
  onShowQR: () => void;
  remainingCredits?: number;
}

export default function ShareActions({
  shareUrl,
  copied,
  matchLoading,
  onCopy,
  onMatch,
  onShowQR,
  remainingCredits,
}: Props) {
  const isOutOfCredits = remainingCredits !== undefined && remainingCredits <= 0;

  return (
    <div className="flex flex-wrap gap-3 mx-4 mb-4">
      <button
        onClick={onCopy}
        className="flex-1 min-w-[120px] px-4 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 transition-colors flex items-center justify-center gap-2"
      >
        {copied ? (
          <><Check className="w-4 h-4 text-green-500" />已复制</>
        ) : (
          <><Copy className="w-4 h-4" />复制链接</>
        )}
      </button>

      <button
        onClick={onShowQR}
        className="flex-1 min-w-[120px] px-4 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 transition-colors flex items-center justify-center gap-2"
      >
        <Share2 className="w-4 h-4" />二维码
      </button>

      {/* Match button with credits indicator */}
      {isOutOfCredits ? (
        <a
          href="/recharge"
          className="flex-1 min-w-[120px] px-4 py-2.5 bg-red-500 text-white rounded-xl hover:bg-red-600 transition-colors flex items-center justify-center gap-2 text-sm"
        >
          <AlertTriangle className="w-4 h-4" />
          额度不足，去充值
        </a>
      ) : (
        <button
          onClick={onMatch}
          disabled={matchLoading}
          className="flex-1 min-w-[120px] px-4 py-2.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-xl hover:opacity-90 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
        >
          <Sparkles className="w-4 h-4" />
          {matchLoading ? '匹配中...' : '智能匹配'}
        </button>
      )}

      {/* Credits badge */}
      {remainingCredits !== undefined && !isOutOfCredits && (
        <div className="w-full flex items-center justify-end gap-1 text-xs text-gray-400">
          <Zap className="w-3 h-3 text-blue-400" />
          剩余额度: <span className="font-medium text-blue-600">{remainingCredits}</span> 次
        </div>
      )}
    </div>
  );
}
