/**
 * 链客宝 - 张力评分小部件（可嵌入产品介绍页）
 * 注入点：产品介绍组件中的实时话术张力评估入口
 * 规则：纯新增，不修改现有业务逻辑
 */

import React, { useState, useCallback } from 'react';

type TensionLevel = 'low' | 'medium' | 'high';

interface AnalysisResult {
  score: number;
  level: TensionLevel;
  suggestions: string[];
}

const LEVEL_CONFIG: Record<TensionLevel, { color: string; bg: string; label: string; emoji: string }> = {
  low:    { color: '#EF4444', bg: '#FEF2F2', label: '低张力', emoji: '🟢' },
  medium: { color: '#F59E0B', bg: '#FFFBEB', label: '中张力', emoji: '🟡' },
  high:   { color: '#10B981', bg: '#ECFDF5', label: '高张力', emoji: '🔴' },
};

/**
 * 客户端张力评分引擎（轻量版，无需后端）
 * 基于规则匹配实时打分
 */
function analyzeLocal(text: string): AnalysisResult {
  let score = 50;
  const checks = [
    { pattern: /\d+[%倍元单家天小时分钟]/, label: '含量化数据', points: 5 },
    { pattern: /对比|传统|而|vs|VS|比/, label: '有对比', points: 5 },
    { pattern: /痛点|问题|困难|挑战|浪费|损失|成本高|效率低/, label: '有痛点描述', points: 5 },
    { pattern: /立即|现在|扫码|点击|注册|试试|体验/, label: '有行动号召', points: 5 },
    { pattern: /相当于|等于|好比|就像|如同/, label: '有类比', points: 5 },
    { pattern: /限时|仅剩|最后|名额|错过/, label: '有紧迫感', points: 5 },
    { pattern: /同行|TOP|标杆|已经有|增长/, label: '有社会认同', points: 5 },
    { pattern: /想象|当您|半年后|到那时/, label: '有未来画面', points: 5 },
    { pattern: /[?？]|对吗|是吧/, label: '有反问', points: 5 },
  ];

  const matched: string[] = [];
  for (const check of checks) {
    if (check.pattern.test(text)) {
      score += check.points;
      matched.push(check.label);
    }
  }

  score = Math.min(score, 100);

  let level: TensionLevel;
  if (score <= 40) level = 'low';
  else if (score <= 70) level = 'medium';
  else level = 'high';

  return { score, level, suggestions: matched };
}

interface Props {
  compact?: boolean; // 紧凑模式
  onScoreChange?: (score: number) => void; // 分数变化回调
}

export default function TensionScoreWidget({ compact = false, onScoreChange }: Props) {
  const [text, setText] = useState('');
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const handleAnalyze = useCallback(() => {
    if (!text.trim()) return;
    const r = analyzeLocal(text);
    setResult(r);
    onScoreChange?.(r.score);
  }, [text, onScoreChange]);

  const config = result ? LEVEL_CONFIG[result.level] : null;

  if (compact) {
    // 紧凑模式：小输入框 + 分数条
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-3">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              if (!e.target.value) setResult(null);
            }}
            placeholder="粘贴话术，快速评分..."
            className="flex-1 px-2 py-1.5 text-xs border border-gray-200 rounded-md focus:ring-1 focus:ring-purple-400 focus:border-purple-400"
          />
          <button
            onClick={handleAnalyze}
            disabled={!text.trim()}
            className="px-2.5 py-1.5 text-xs font-medium bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors"
          >
            评分
          </button>
        </div>
        {result && (
          <div className="mt-2 flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${result.score}%`, backgroundColor: config?.color }}
              />
            </div>
            <span className="text-[10px] font-medium" style={{ color: config?.color }}>
              {result.score}分 · {config?.label}
            </span>
          </div>
        )}
      </div>
    );
  }

  // 完整模式
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">
          <span className="mr-1">📏</span>
          张力自检评分
        </h3>
        <span className="text-[10px] text-gray-400">实时分析·无需后端</span>
      </div>
      <div className="p-4 space-y-3">
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (!e.target.value) setResult(null);
          }}
          rows={3}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          placeholder="粘贴您的话术文本，点击分析查看张力评分..."
        />
        <button
          onClick={handleAnalyze}
          disabled={!text.trim()}
          className="w-full py-2 text-sm font-medium rounded-lg text-white bg-purple-600 hover:bg-purple-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors"
        >
          分析张力
        </button>

        {result && (
          <div className="space-y-2">
            {/* 分数圆环 */}
            <div className="flex items-center gap-4">
              <div className="relative w-16 h-16 flex items-center justify-center">
                <svg className="absolute inset-0 w-full h-full transform -rotate-90">
                  <circle cx="32" cy="32" r="28" fill="none" stroke="#E5E7EB" strokeWidth="6" />
                  <circle
                    cx="32" cy="32" r="28"
                    fill="none"
                    stroke={config?.color}
                    strokeWidth="6"
                    strokeLinecap="round"
                    strokeDasharray={175.93}
                    strokeDashoffset={175.93 - (result.score / 100) * 175.93}
                    className="transition-all duration-1000 ease-out"
                  />
                </svg>
                <span className="text-lg font-bold" style={{ color: config?.color }}>
                  {result.score}
                </span>
              </div>
              <div>
                <div className="text-sm font-semibold" style={{ color: config?.color }}>
                  {config?.emoji} {config?.label}
                </div>
                <div className="text-[11px] text-gray-400 mt-0.5">
                  检测到 {result.suggestions.length} 个张力要素
                </div>
              </div>
            </div>

            {/* 匹配要素 */}
            {result.suggestions.length > 0 && (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-1">已检测到的张力要素：</div>
                <div className="flex flex-wrap gap-1">
                  {result.suggestions.map((s, i) => (
                    <span
                      key={i}
                      className="px-2 py-0.5 bg-purple-50 text-purple-700 text-[10px] rounded-full border border-purple-100"
                    >
                      ✓ {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 改进建议 */}
            {result.score < 71 && (
              <div className="p-2 bg-amber-50 rounded-lg border border-amber-100">
                <p className="text-[10px] text-amber-700">
                  💡 建议：增加量化数据、对比句式或紧迫感引导词来提升张力得分。
                  参考"数据增强器"和"话术引导词"功能。
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
