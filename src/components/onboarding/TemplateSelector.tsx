/**
 * 三步冷启动引导 — 模板推荐选择区
 * 展示预设名片模板卡片网格，支持单选
 *
 * i18n: aria-label 走 useTranslation()
 */
import React from 'react';
import { useTranslation } from '../../i18n';

export interface Template {
  id: string;
  name: string;
  description: string;
  previewUrl?: string;
  /** 渐变色或纯色预览替代图 */
  gradient: string;
  tags?: string[];
}

export interface TemplateSelectorProps {
  templates: Template[];
  selectedId: string | null;
  onSelect: (templateId: string) => void;
  className?: string;
}

const DEFAULT_TEMPLATES: Template[] = [
  {
    id: 'modern-blue',
    name: '现代蓝调',
    description: '简约商务风格，适合科技、金融行业',
    gradient: 'from-blue-500 via-blue-600 to-indigo-700',
    tags: ['商务', '科技'],
  },
  {
    id: 'minimal-white',
    name: '极简白',
    description: '干净利落的白色底色，百搭任何行业',
    gradient: 'from-gray-50 to-gray-200',
    tags: ['极简', '通用'],
  },
  {
    id: 'warm-gold',
    name: '暖金尊享',
    description: '金色点缀，彰显高端品质与企业实力',
    gradient: 'from-amber-400 via-orange-400 to-yellow-500',
    tags: ['高端', '商务'],
  },
  {
    id: 'nature-green',
    name: '自然绿意',
    description: '清新绿色调，适合健康、环保、农业',
    gradient: 'from-green-400 via-emerald-500 to-teal-600',
    tags: ['清新', '健康'],
  },
  {
    id: 'dark-elegance',
    name: '暗夜优雅',
    description: '深色背景搭配金色文字，沉稳大气',
    gradient: 'from-gray-800 via-slate-800 to-gray-900',
    tags: ['沉稳', '高端'],
  },
  {
    id: 'gradient-purple',
    name: '梦幻紫韵',
    description: '紫色渐变，适合创意、设计、艺术行业',
    gradient: 'from-purple-500 via-fuchsia-500 to-pink-500',
    tags: ['创意', '艺术'],
  },
];

export default function TemplateSelector({
  templates = DEFAULT_TEMPLATES,
  selectedId,
  onSelect,
  className = '',
}: TemplateSelectorProps) {
  const { t } = useTranslation();

  // 翻译模板名称/描述/标签（基于 template.id 映射到 i18n key）
  const tmplNameKey = (id: string) => `template_${id}`;
  const tmplDescKey = (id: string) => `template_${id}_desc`;

  return (
    <div className={`w-full ${className}`}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {templates.map((template) => {
          const isSelected = selectedId === template.id;
          const displayName = t(tmplNameKey(template.id), template.name);
          const displayDesc = t(tmplDescKey(template.id), template.description);

          return (
            <button
              key={template.id}
              type="button"
              onClick={() => onSelect(template.id)}
              className={`
                relative group rounded-xl overflow-hidden
                transition-all duration-300 ease-out
                focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2
                ${
                  isSelected
                    ? 'ring-2 ring-blue-600 shadow-lg shadow-blue-100 scale-[1.02]'
                    : 'ring-1 ring-gray-200 hover:ring-blue-300 hover:shadow-md'
                }
              `}
              aria-pressed={isSelected}
              aria-label={t('onboarding_select_template', `选择模板：${displayName}`).replace('{name}', displayName)}
            >
              {/* Preview area */}
              <div
                className={`
                  aspect-[1.6] bg-gradient-to-br ${template.gradient}
                  flex items-center justify-center relative overflow-hidden
                `}
              >
                {/* Decorative card mockup */}
                {template.previewUrl ? (
                  <img
                    src={template.previewUrl}
                    alt={displayName}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-4/5 h-3/5 bg-white/20 backdrop-blur-sm rounded-lg flex flex-col items-start justify-center p-3 gap-1">
                    <div className="w-2/3 h-2 bg-white/60 rounded" />
                    <div className="w-1/2 h-1.5 bg-white/40 rounded" />
                    <div className="w-1/3 h-1.5 bg-white/30 rounded mt-1" />
                  </div>
                )}

                {/* Selected check overlay */}
                {isSelected && (
                  <div className="absolute top-2 right-2 w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center shadow-lg">
                    <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
              </div>

              {/* Info area */}
              <div className="p-3 bg-white">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-800 truncate">
                    {displayName}
                  </h3>
                </div>
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-2 leading-relaxed">
                  {displayDesc}
                </p>
                {template.tags && template.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {template.tags.map((tag) => {
                      // 翻译标签 (tag key 映射)
                      const tagKey = `tag_${tag}`;
                      const displayTag = t(tagKey, tag);
                      return (
                        <span
                          key={tag}
                          className="inline-block text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 font-medium"
                        >
                          {displayTag}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
