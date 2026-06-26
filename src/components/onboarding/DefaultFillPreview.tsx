/**
 * 三步冷启动引导 — 默认填充预览
 * 展示系统根据用户信息自动填充的名片预览
 *
 * i18n: 所有 text content 和 aria-label 走 useTranslation()
 */
import React from 'react';
import { useTranslation } from '../../i18n';

export interface UserInfo {
  name: string;
  position?: string;
  company?: string;
  phone?: string;
  email?: string;
  wechat?: string;
  website?: string;
  address?: string;
  avatar?: string;
}

export interface DefaultFillPreviewProps {
  userInfo: UserInfo;
  templateId?: string;
  className?: string;
}

/** 根据模板ID返回预览卡片配色 */
function getThemeColors(templateId?: string) {
  const themes: Record<string, { bg: string; text: string; accent: string; cardBg: string }> = {
    'modern-blue':     { bg: 'from-blue-500 to-indigo-700', text: 'text-white', accent: 'text-blue-200', cardBg: 'bg-white/10' },
    'minimal-white':   { bg: 'from-gray-50 to-gray-200', text: 'text-gray-800', accent: 'text-gray-500', cardBg: 'bg-white' },
    'warm-gold':       { bg: 'from-amber-400 to-yellow-500', text: 'text-white', accent: 'text-yellow-100', cardBg: 'bg-white/10' },
    'nature-green':    { bg: 'from-green-400 to-teal-600', text: 'text-white', accent: 'text-green-100', cardBg: 'bg-white/10' },
    'dark-elegance':   { bg: 'from-gray-800 to-gray-900', text: 'text-white', accent: 'text-gray-400', cardBg: 'bg-white/5' },
    'gradient-purple': { bg: 'from-purple-500 to-pink-500', text: 'text-white', accent: 'text-purple-200', cardBg: 'bg-white/10' },
  };
  return themes[templateId || ''] || themes['modern-blue'];
}

export default function DefaultFillPreview({
  userInfo,
  templateId,
  className = '',
}: DefaultFillPreviewProps) {
  const { t } = useTranslation();
  const theme = getThemeColors(templateId);

  return (
    <div className={`w-full ${className}`}>
      {/* Business card preview */}
      <div
        className={`
          relative overflow-hidden rounded-2xl shadow-xl
          bg-gradient-to-br ${theme.bg}
          aspect-[1.586] max-w-sm mx-auto
          transition-all duration-500
        `}
      >
        {/* Decorative elements */}
        <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full bg-white/5" />
        <div className="absolute -bottom-8 -left-8 w-32 h-32 rounded-full bg-white/5" />

        {/* Card content */}
        <div className="relative z-10 p-5 sm:p-6 flex flex-col h-full">
          {/* Top section: Name + Position */}
          <div className="flex items-start gap-3">
            {/* Avatar */}
            <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-white/20 flex items-center justify-center shrink-0 overflow-hidden ring-2 ring-white/30">
              {userInfo.avatar ? (
                <img src={userInfo.avatar} alt={userInfo.name} className="w-full h-full object-cover" />
              ) : (
                <span className="text-lg sm:text-xl font-bold text-white/80">
                  {userInfo.name ? userInfo.name.charAt(0).toUpperCase() : '?'}
                </span>
              )}
            </div>

            <div className="min-w-0 flex-1">
              <h3 className={`text-lg sm:text-xl font-bold truncate ${theme.text}`}>
                {userInfo.name || t('onboarding_preview_name_placeholder', '您的姓名')}
              </h3>
              {userInfo.position && (
                <p className={`text-sm ${theme.accent} truncate mt-0.5`}>
                  {userInfo.position}
                </p>
              )}
              {userInfo.company && (
                <p className={`text-xs ${theme.accent} opacity-75 truncate`}>
                  {userInfo.company}
                </p>
              )}
            </div>
          </div>

          {/* Divider */}
          <div className="my-auto border-t border-white/10 w-full" />

          {/* Bottom section: Contact details */}
          <div className="space-y-1.5">
            {userInfo.phone && (
              <div className="flex items-center gap-2">
                <svg className={`w-3.5 h-3.5 ${theme.accent} shrink-0`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                </svg>
                <span className={`text-xs ${theme.text} truncate`}>{userInfo.phone}</span>
              </div>
            )}
            {userInfo.email && (
              <div className="flex items-center gap-2">
                <svg className={`w-3.5 h-3.5 ${theme.accent} shrink-0`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <span className={`text-xs ${theme.text} truncate`}>{userInfo.email}</span>
              </div>
            )}
            {userInfo.wechat && (
              <div className="flex items-center gap-2">
                <svg className={`w-3.5 h-3.5 ${theme.accent} shrink-0`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <span className={`text-xs ${theme.text} truncate`}>{userInfo.wechat}</span>
              </div>
            )}
            {userInfo.website && (
              <div className="flex items-center gap-2">
                <svg className={`w-3.5 h-3.5 ${theme.accent} shrink-0`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className={`text-xs ${theme.text} truncate`}>{userInfo.website}</span>
              </div>
            )}
          </div>

          {/* Bottom branding */}
          <div className="mt-auto pt-2 flex items-center justify-between">
            <span className={`text-[10px] ${theme.accent} opacity-50`}>{t('onboarding_preview_branding', 'AI 数字名片')}</span>
            <div className="flex gap-1">
              <div className="w-5 h-5 rounded bg-white/10" />
              <div className="w-5 h-5 rounded bg-white/10" />
            </div>
          </div>
        </div>
      </div>

      {/* Auto-fill hint */}
      <div className="mt-4 text-center">
        <p className="text-xs text-gray-400">
          {t('onboarding_preview_auto_fill', '系统已根据您的信息自动填充名片')}
        </p>
        <p className="text-[11px] text-gray-300 mt-0.5">
          {t('onboarding_preview_edit_hint', '您可以在后续步骤中进一步编辑')}
        </p>
      </div>
    </div>
  );
}
