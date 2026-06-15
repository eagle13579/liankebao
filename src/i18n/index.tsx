import React, { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';
import zh from './zh';
import en from './en';

// ============================================================
// 语言包类型
// ============================================================
type LangPack = Record<string, string>;
type SupportedLocale = 'zh' | 'en';

const packs: Record<SupportedLocale, LangPack> = { zh, en };

// ============================================================
// 简单模板插值: t('card.viewCount', { n: 42 })
// ============================================================
function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    const val = vars[key];
    return val != null ? String(val) : `{${key}}`;
  });
}

// ============================================================
// 检测浏览器语言
// ============================================================
function detectBrowserLang(): SupportedLocale {
  if (typeof navigator === 'undefined') return 'zh';
  const lang = navigator.language || (navigator as any).userLanguage || '';
  if (lang.startsWith('zh')) return 'zh';
  if (lang.startsWith('en')) return 'en';
  return 'zh';
}

// ============================================================
// Context
// ============================================================
interface I18nContextValue {
  locale: SupportedLocale;
  setLocale: (lang: SupportedLocale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue>({
  locale: 'zh',
  setLocale: () => {},
  t: (key) => key,
});

// ============================================================
// Provider
// ============================================================
export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<SupportedLocale>(() => detectBrowserLang());

  const setLocale = useCallback((lang: SupportedLocale) => {
    setLocaleState(lang);
    if (typeof document !== 'undefined') {
      document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    }
    try {
      localStorage.setItem('lkb_locale', lang);
    } catch {}
  }, []);

  // 恢复上次选择的语言
  useEffect(() => {
    try {
      const saved = localStorage.getItem('lkb_locale') as SupportedLocale | null;
      if (saved && (saved === 'zh' || saved === 'en')) {
        setLocaleState(saved);
      }
    } catch {}
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const pack = packs[locale];
      const template = pack[key];
      if (template === undefined) {
        if (process.env.NODE_ENV === 'development') {
          console.warn(`[i18n] Missing translation key: "${key}" for locale "${locale}"`);
        }
        return key;
      }
      return interpolate(template, vars);
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

// ============================================================
// Hook
// ============================================================
export function useT() {
  const ctx = useContext(I18nContext);
  return ctx.t;
}

export function useLocale() {
  const ctx = useContext(I18nContext);
  return { locale: ctx.locale, setLocale: ctx.setLocale };
}

export function useI18n() {
  return useContext(I18nContext);
}
