"use client";

import type { IntentSuggestion } from "@/lib/data";

interface IntentSuggestionsProps {
  suggestions: IntentSuggestion[];
  onSelect: (text: string) => void;
  isLocked?: boolean;
}

export default function IntentSuggestions({
  suggestions,
  onSelect,
  isLocked = false,
}: IntentSuggestionsProps) {
  if (suggestions.length === 0 || isLocked) return null;

  return (
    <div className="px-6 py-3 border-t border-slate-700/20 bg-slate-800/10">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
        💡 快捷提问
      </div>
      <div className="flex gap-2 flex-wrap">
        {suggestions.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.text)}
            className="px-3 py-1.5 bg-slate-700/40 hover:bg-slate-700/70 border border-slate-600/30 rounded-lg text-xs text-slate-300 hover:text-slate-100 transition flex items-center gap-1.5"
          >
            <span>{s.icon}</span>
            <span>{s.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
