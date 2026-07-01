/**
 * 链客宝 - 「匹配理由展示」AI推荐卡片组件
 * 注入点：推荐结果展示页中的AI匹配理由可视化入口
 * 规则：纯新增，不修改现有业务逻辑。纯UI组件，不含数据获取逻辑。
 */

import React from 'react';

// 张力等级配置（与 TensionScoreWidget 保持一致）
const TENSION_MAP: Record<string, { color: string; bg: string; label: string; emoji: string }> = {
  low:    { color: '#10B981', bg: '#ECFDF5', label: '低张力', emoji: '🟢' },
  medium: { color: '#F59E0B', bg: '#FFFBEB', label: '中张力', emoji: '🟡' },
  high:   { color: '#EF4444', bg: '#FEF2F2', label: '高张力', emoji: '🔴' },
};

interface Props {
  /** 公司名称 */
  companyName: string;
  /** 匹配度分数（0-100） */
  matchScore: number;
  /** AI匹配理由列表 */
  matchReasons: string[];
  /** 行业匹配度描述 */
  industryFit: string;
  /** 规模匹配度描述 */
  sizeFit: string;
  /** 张力等级：'low' | 'medium' | 'high' */
  tensionLevel: string;
}

/**
 * 匹配度渐变色 — 从红到绿渐变
 */
function matchScoreGradient(score: number): string {
  if (score >= 80) return 'from-emerald-400 to-green-500';
  if (score >= 60) return 'from-blue-400 to-cyan-500';
  if (score >= 40) return 'from-amber-400 to-orange-500';
  return 'from-red-400 to-rose-500';
}

/**
 * 匹配度颜色（文字用）
 */
function matchScoreColor(score: number): string {
  if (score >= 80) return 'text-emerald-600';
  if (score >= 60) return 'text-blue-600';
  if (score >= 40) return 'text-amber-600';
  return 'text-red-600';
}

export default function AIMatchReasonCard({
  companyName,
  matchScore,
  matchReasons,
  industryFit,
  sizeFit,
  tensionLevel,
}: Props) {
  const clampedScore = Math.max(0, Math.min(100, matchScore));
  const tension = TENSION_MAP[tensionLevel] || TENSION_MAP.low;
  const gradClass = matchScoreGradient(clampedScore);
  const textColor = matchScoreColor(clampedScore);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/30 bg-white/70 backdrop-blur-xl shadow-lg transition-all duration-300 hover:shadow-xl hover:bg-white/80">
      {/* 毛玻璃装饰光晕 */}
      <div className="absolute -top-6 -right-6 w-24 h-24 rounded-full bg-gradient-to-br from-purple-200/40 to-blue-200/40 blur-xl pointer-events-none" />
      <div className="absolute -bottom-4 -left-4 w-20 h-20 rounded-full bg-gradient-to-tr from-cyan-200/30 to-emerald-200/30 blur-xl pointer-events-none" />

      <div className="relative p-4 space-y-3">
        {/* ===== 头部：公司名称 + 匹配度 ===== */}
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-800 truncate max-w-[60%]">
            {companyName}
          </h3>
          <div className="flex items-center gap-1.5">
            <span className={`text-xs font-bold ${textColor}`}>
              {clampedScore}%
            </span>
            <span className="text-[10px] text-gray-400">匹配</span>
          </div>
        </div>

        {/* ===== 渐变色匹配度进度条 ===== */}
        <div className="h-2 bg-gray-100/80 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full bg-gradient-to-r ${gradClass} transition-all duration-700 ease-out`}
            style={{ width: `${clampedScore}%` }}
          />
        </div>

        {/* ===== AI 匹配理由标签列表 ===== */}
        {matchReasons.length > 0 && (
          <div>
            <div className="text-[10px] font-medium text-gray-500 mb-1.5 flex items-center gap-1">
              <span>🤖</span> AI 匹配理由
            </div>
            <div className="flex flex-wrap gap-1.5">
              {matchReasons.map((reason, i) => (
                <span
                  key={i}
                  className="inline-flex items-center px-2 py-0.5 bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-700 text-[10px] rounded-full border border-indigo-100/60 shadow-sm"
                >
                  {reason}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ===== 行业 & 规模匹配 ===== */}
        <div className="grid grid-cols-2 gap-2">
          <div className="px-2.5 py-1.5 rounded-lg bg-white/60 border border-gray-100/80">
            <div className="text-[9px] text-gray-400 uppercase tracking-wider">行业匹配</div>
            <div className="text-xs font-medium text-gray-700 mt-0.5 truncate">{industryFit}</div>
          </div>
          <div className="px-2.5 py-1.5 rounded-lg bg-white/60 border border-gray-100/80">
            <div className="text-[9px] text-gray-400 uppercase tracking-wider">规模匹配</div>
            <div className="text-xs font-medium text-gray-700 mt-0.5 truncate">{sizeFit}</div>
          </div>
        </div>

        {/* ===== 张力评分指示器 ===== */}
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg border"
          style={{
            backgroundColor: tension.bg,
            borderColor: tension.color + '30',
          }}
        >
          <div className="flex items-center gap-1">
            <span className="text-sm">{tension.emoji}</span>
            <span className="text-xs font-semibold" style={{ color: tension.color }}>
              {tension.label}
            </span>
          </div>
          <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: tension.color + '20' }}>
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: tensionLevel === 'high' ? '90%' : tensionLevel === 'medium' ? '55%' : '25%',
                backgroundColor: tension.color,
              }}
            />
          </div>
          <span className="text-[10px] text-gray-400">张力</span>
        </div>
      </div>
    </div>
  );
}
