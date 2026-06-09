import { Copy, Check, Share2, RefreshCw, QrCode, Loader2 } from 'lucide-react';

interface ShareActionsProps {
  shareUrl: string;
  copied: boolean;
  matchLoading: boolean;
  onCopy: () => void;
  onMatch: () => void;
  onShowQR: () => void;
}

export default function ShareActions({
  shareUrl,
  copied,
  matchLoading,
  onCopy,
  onMatch,
  onShowQR,
}: ShareActionsProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="flex-1 bg-slate-50 rounded-xl px-3 py-2.5 text-xs text-on-surface truncate">
          {shareUrl}
        </div>
        <button
          onClick={onCopy}
          className="p-2.5 rounded-xl bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
          title={copied ? '已复制' : '复制链接'}
        >
          {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>

      <div className="flex gap-3">
        <button
          onClick={onMatch}
          disabled={matchLoading}
          className="flex-1 py-3 px-4 rounded-xl bg-gradient-to-r from-primary to-purple-600 text-white font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {matchLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          AI 供需匹配
        </button>
        <button
          onClick={onCopy}
          className="flex-1 py-3 px-4 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
        >
          <Share2 className="w-4 h-4" />
          分享
        </button>
        <button
          onClick={onShowQR}
          className="py-3 px-4 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
        >
          <QrCode className="w-4 h-4" />
          画册QR
        </button>
      </div>
    </div>
  );
}
