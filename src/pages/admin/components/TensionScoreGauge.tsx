/**
 * 链客宝 - 张力评分仪表盘小部件
 * 注入点：可嵌入产品介绍页/话术编辑器的张力评分可视化组件
 * 规则：纯新增，不修改现有业务逻辑
 */

import React from 'react';

interface Props {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  animated?: boolean;
}

const levelConfig = {
  low:    { color: '#EF4444', bg: '#FEF2F2', label: '低张力', range: [0, 40] },
  medium: { color: '#F59E0B', bg: '#FFFBEB', label: '中张力', range: [41, 70] },
  high:   { color: '#10B981', bg: '#ECFDF5', label: '高张力', range: [71, 100] },
};

function getLevel(score: number): keyof typeof levelConfig {
  if (score <= 40) return 'low';
  if (score <= 70) return 'medium';
  return 'high';
}

const sizeMap = {
  sm: { gauge: 64, stroke: 6, fontSize: 'text-lg' },
  md: { gauge: 96, stroke: 8, fontSize: 'text-2xl' },
  lg: { gauge: 140, stroke: 12, fontSize: 'text-3xl' },
};

export default function TensionScoreGauge({ score, size = 'md', showLabel = true, animated = true }: Props) {
  const level = getLevel(score);
  const config = levelConfig[level];
  const dim = sizeMap[size];
  const radius = (dim.gauge - dim.stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={dim.gauge} height={dim.gauge} className="transform -rotate-90">
        {/* 背景圆弧 */}
        <circle
          cx={dim.gauge / 2}
          cy={dim.gauge / 2}
          r={radius}
          fill="none"
          stroke="#E5E7EB"
          strokeWidth={dim.stroke}
        />
        {/* 打分圆弧 */}
        <circle
          cx={dim.gauge / 2}
          cy={dim.gauge / 2}
          r={radius}
          fill="none"
          stroke={config.color}
          strokeWidth={dim.stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={animated ? offset : 0}
          className={animated ? 'transition-all duration-1000 ease-out' : ''}
        />
      </svg>
      {/* 中心分数 */}
      <div className="absolute flex flex-col items-center" style={{ width: dim.gauge, height: dim.gauge }}>
        <span className={`font-bold ${dim.fontSize}`} style={{ color: config.color }}>
          {score}
        </span>
        {showLabel && (
          <span className="text-xs text-gray-500" style={{ marginTop: -2 }}>
            {config.label}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * 评分等级条（水平布局，适用于列表展示）
 */
export function TensionScoreBar({ score }: { score: number }) {
  const level = getLevel(score);
  const config = levelConfig[level];

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${score}%`,
            backgroundColor: config.color,
          }}
        />
      </div>
      <span className="text-xs font-medium min-w-[3.5rem] text-right" style={{ color: config.color }}>
        {config.label}
      </span>
    </div>
  );
}
