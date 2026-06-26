/**
 * 前端 i18n 多语言系统
 * =====================
 * 架构:
 *   1. React Context (I18nContext) — 全局注入 t/setLang/currentLang
 *   2. useTranslation() hook — 组件内使用
 *   3. 从后端 API (GET /api/v1/i18n/translations?lang=xx) 加载翻译
 *   4. localStorage 缓存翻译，离线可用
 *   5. Cookie 写入 'lang' 后刷新页面实现语言切换
 *
 * 优先级:
 *   后端API翻译 > localStorage缓存 > 内置 JSON 翻译 > key 本身(回退)
 */
import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';

// ── 类型定义 ──
export interface I18nContextValue {
  /** 翻译函数: t(key, fallback?) → string */
  t: (key: string, fallback?: string) => string;
  /** 切换语言: 设置 Cookie 后刷新页面 */
  setLang: (lang: string) => void;
  /** 当前语言代码 (zh/ko/en) */
  currentLang: string;
  /** 翻译字典是否已加载完成 */
  ready: boolean;
}

const I18nContext = createContext<I18nContextValue | null>(null);

// ── 常量 ──
const STORAGE_KEY = 'chainke_i18n_cache';
const STORAGE_LANG_KEY = 'chainke_lang';
const COOKIE_NAME = 'lang';
const DEFAULT_LANG = 'zh';
const SUPPORTED_LANGS = ['zh', 'ko', 'en'];

// ── 内置翻译字典 (作为最后回退) ──
// 在构建时从 JSON 文件导入
import zhTranslations from './translations/zh.json';
import enTranslations from './translations/en.json';
import koTranslations from './translations/ko.json';

const BUILTIN_TRANSLATIONS: Record<string, Record<string, string>> = {
  zh: zhTranslations as Record<string, string>,
  en: enTranslations as Record<string, string>,
  ko: koTranslations as Record<string, string>,
};

// ── 工具函数 ──

/** 读取 Cookie 中指定 key 的值 */
function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** 设置 Cookie */
function setCookie(name: string, value: string, days = 365): void {
  if (typeof document === 'undefined') return;
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
}

/** 获取初始语言: Cookie > localStorage > 浏览器语言 > 默认 */
function detectInitialLang(): string {
  // Cookie 优先 (服务端设置)
  const cookieLang = getCookie(COOKIE_NAME);
  if (cookieLang && SUPPORTED_LANGS.includes(cookieLang)) return cookieLang;

  // localStorage
  try {
    const stored = localStorage.getItem(STORAGE_LANG_KEY);
    if (stored && SUPPORTED_LANGS.includes(stored)) return stored;
  } catch { /* 静默降级 */ }

  // 浏览器语言
  if (typeof navigator !== 'undefined') {
    const browserLang = navigator.language?.slice(0, 2);
    if (browserLang && SUPPORTED_LANGS.includes(browserLang)) return browserLang;
  }

  return DEFAULT_LANG;
}

/** 从 localStorage 读取缓存的翻译 */
function loadCache(): Record<string, Record<string, string>> | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as Record<string, Record<string, string>>;
  } catch { /* 忽略 */ }
  return null;
}

/** 写入 localStorage 缓存 */
function saveCache(data: Record<string, Record<string, string>>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch { /* 存储满时静默降级 */ }
}

// ── Provider Props ──
interface I18nProviderProps {
  children: ReactNode;
}

/**
 * I18nProvider — 包裹应用根组件
 *
 * 自动:
 *   - 探测初始语言
 *   - 从后端加载翻译 (缓存优先)
 *   - 注入 t/setLang/currentLang/ready 到 context
 */
export function I18nProvider({ children }: I18nProviderProps) {
  const [currentLang, setCurrentLang] = useState(detectInitialLang);
  const [translations, setTranslations] = useState<Record<string, string> | null>(() => {
    // 初始化: 先尝试缓存, 再回退内置翻译
    const cached = loadCache();
    if (cached && cached[detectInitialLang()]) {
      return cached[detectInitialLang()];
    }
    // 返回内置翻译作为初始渲染
    const initialLang = detectInitialLang();
    return BUILTIN_TRANSLATIONS[initialLang] ?? BUILTIN_TRANSLATIONS[DEFAULT_LANG] ?? null;
  });
  const [ready, setReady] = useState(false);
  const loadedRef = useRef(false);

  // 从后端加载翻译
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;

    let cancelled = false;

    async function loadTranslations(lang: string) {
      // 1. 检查 localStorage 缓存
      const cached = loadCache();
      if (cached && cached[lang]) {
        if (!cancelled) {
          setTranslations(cached[lang]);
          setReady(true);
        }
        // 即使有缓存也异步更新（后台刷新）
      }

      // 2. 从后端 API 加载 (覆盖缓存)
      try {
        const resp = await fetch(`/api/v1/i18n/translations?lang=${lang}`, {
          headers: { 'Accept': 'application/json' },
        });

        if (!resp.ok) {
          // API 不可用时，尝试合并内置翻译
          const builtin = BUILTIN_TRANSLATIONS[lang] ?? BUILTIN_TRANSLATIONS[DEFAULT_LANG] ?? {};
          if (!cancelled) {
            setTranslations((prev) => ({ ...prev, ...builtin }));
            setReady(true);
          }
          return;
        }

        const data = await resp.json();
        const serverTrans: Record<string, string> = data.translations ?? {};

        // 合并: 后端翻译 + 内置翻译 (后端优先)
        const builtin = BUILTIN_TRANSLATIONS[lang] ?? BUILTIN_TRANSLATIONS[DEFAULT_LANG] ?? {};
        const merged = { ...builtin, ...serverTrans };

        // 更新缓存
        const updatedCache = { ...cached, [lang]: merged };
        saveCache(updatedCache);

        if (!cancelled) {
          setTranslations(merged);
          setReady(true);
        }
      } catch {
        // 网络错误: 使用缓存或内置翻译
        const builtin = BUILTIN_TRANSLATIONS[lang] ?? BUILTIN_TRANSLATIONS[DEFAULT_LANG] ?? {};
        if (!cancelled) {
          setTranslations((prev) => prev ?? builtin);
          setReady(true);
        }
      }
    }

    loadTranslations(currentLang);

    return () => { cancelled = true; };
  }, [currentLang]);

  // 翻译函数
  const t = useCallback(
    (key: string, fallback?: string): string => {
      if (!translations) return fallback ?? key;
      return translations[key] ?? fallback ?? key;
    },
    [translations],
  );

  // 切换语言: 设置 Cookie + localStorage，刷新页面
  const setLang = useCallback((lang: string) => {
    if (!SUPPORTED_LANGS.includes(lang)) return;
    setCookie(COOKIE_NAME, lang);
    try {
      localStorage.setItem(STORAGE_LANG_KEY, lang);
    } catch { /* 静默 */ }
    // 刷新页面让后端中间件也生效
    window.location.reload();
  }, []);

  const value: I18nContextValue = {
    t,
    setLang,
    currentLang,
    ready,
  };

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/**
 * useTranslation — 在组件中使用多语言
 *
 * 用法:
 *   const { t, setLang, currentLang } = useTranslation();
 *   <h1>{t('onboarding_title')}</h1>
 *   <button onClick={() => setLang('ko')}>한국어</button>
 */
export function useTranslation(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // 未包裹 Provider 时，返回降级实现
    console.warn('[i18n] I18nProvider not found, using fallback. Wrap your app with <I18nProvider>.');
    return {
      t: (key: string, fallback?: string) => fallback ?? key,
      setLang: () => {},
      currentLang: DEFAULT_LANG,
      ready: true,
    };
  }
  return ctx;
}

export default useTranslation;
