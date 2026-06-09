import { Sparkles, ExternalLink } from 'lucide-react';
import type { MatchItem } from '../types';

interface MatchResultsPanelProps {
  items: MatchItem[];
  loading: boolean;
}

export default function MatchResultsPanel({ items, loading }: MatchResultsPanelProps) {
  if (loading) {
    return (
      <div className="border-t border-border-light pt-4">
        <div className="flex items-center gap-2 text-sm text-text-muted">
          <Sparkles className="w-4 h-4 animate-pulse" />
          正在匹配...
        </div>
      </div>
    );
  }

  if (items.length === 0) return null;

  return (
    <div className="border-t border-border-light pt-4">
      <h3 className="text-sm font-bold text-on-surface mb-3 flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-primary" />
        AI 匹配结果 ({items.length})
      </h3>
      <div className="space-y-2">
        {items.slice(0, 5).map((item) => (
          <div
            key={`${item.type}-${item.id}`}
            className="bg-slate-50 rounded-xl p-3 flex items-start gap-3"
          >
            <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
              item.type === 'need' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'
            }`}>
              {item.type === 'need' ? '需求' : '产品'}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-on-surface truncate">
                {item.title}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-text-muted">{item.category}</span>
                <span className={`text-xs font-medium ${
                  item.score >= 0.7 ? 'text-green-600' : item.score >= 0.4 ? 'text-amber-600' : 'text-text-muted'
                }`}>
                  匹配度 {Math.round(item.score * 100)}%
                </span>
              </div>
            </div>
            <ExternalLink className="w-4 h-4 text-text-muted shrink-0" />
          </div>
        ))}
        {items.length > 5 && (
          <p className="text-xs text-primary text-center py-2">
            还有 {items.length - 5} 个匹配结果
          </p>
        )}
      </div>
    </div>
  );
}
