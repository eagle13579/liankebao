/**
 * useTranslation hook 测试
 * ========================
 * 覆盖：hook 默认值、翻译查找、语言切换、Provider、韩语翻译
 */
import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { I18nProvider, useTranslation } from '../index';

// ── 辅助组件：在测试中暴露 hook 值 ──
function TestConsumer() {
  const { t, setLang, currentLang, ready } = useTranslation();
  return (
    <div>
      <span data-testid="currentLang">{currentLang}</span>
      <span data-testid="ready">{ready ? 'true' : 'false'}</span>
      <span data-testid="t_title">{t('onboarding_title', '三步冷启动')}</span>
      <span data-testid="t_missing">{t('nonexistent_key', '回退文本')}</span>
      <span data-testid="t_no_fallback">{t('another_missing_key')}</span>
      <span data-testid="t_company">{t('onboarding_company_name', '公司名称')}</span>
      <button
        data-testid="setLangKo"
        onClick={() => setLang('ko')}
      >
        한국어
      </button>
    </div>
  );
}

// ── 模拟 localStorage ──
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// ── 模拟 document.cookie ──
let mockCookie = '';
Object.defineProperty(document, 'cookie', {
  get: () => mockCookie,
  set: (val: string) => { mockCookie = val; },
  configurable: true,
});

// ── 模拟 fetch ──
const mockFetch = jest.fn();
global.fetch = mockFetch;

// ── 模拟 navigator.language ──
Object.defineProperty(navigator, 'language', {
  get: () => 'zh-CN',
  configurable: true,
});

describe('useTranslation', () => {
  beforeEach(() => {
    localStorageMock.clear();
    mockCookie = '';
    mockFetch.mockReset();
    // 默认 fetch 返回后端翻译（合并）
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        lang: 'zh',
        translations: {
          onboarding_title: '三步冷启动（后端）',
          onboarding_company_name: '公司名称（后端）',
        },
      }),
    });
  });

  // ── Test 1: Provider 包裹时 hook 返回正常值 ──
  test('1. Provider 包裹时返回 currentLang/ready/t 正常', async () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    // 初始渲染时 ready 可能为 false, 等待异步加载
    const langEl = await screen.findByTestId('currentLang');
    expect(langEl.textContent).toBe('zh');

    const readyEl = screen.getByTestId('ready');
    // 最终应为 true (mock fetch 会成功)
    await screen.findByText('三步冷启动（后端）');
    expect(readyEl.textContent).toBe('true');
  });

  // ── Test 2: t() 返回正确的翻译值 ──
  test('2. t() 返回已翻译的字符串', async () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    // 等待后端翻译加载完成
    const titleEl = await screen.findByText('三步冷启动（后端）', {}, { timeout: 2000 });
    expect(titleEl).toBeInTheDocument();
  });

  // ── Test 3: t() 在 key 不存在时返回 fallback ──
  test('3. t() 在 key 不存在时返回 fallback', async () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    const missingEl = await screen.findByTestId('t_missing');
    // fallback 是 '回退文本'
    expect(missingEl.textContent).toBe('回退文本');
  });

  // ── Test 4: t() 在没有 fallback 时返回 key 本身 ──
  test('4. t() 无 fallback 时返回 key', async () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    const noFallbackEl = await screen.findByTestId('t_no_fallback');
    expect(noFallbackEl.textContent).toBe('another_missing_key');
  });

  // ── Test 5: 第三方语言检测（ko）─ 翻译文件中有韩语 ──
  test('5. 韩语翻译 key 存在时正确返回', async () => {
    // 模拟韩语环境
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        lang: 'ko',
        translations: {
          onboarding_title: '3단계 콜드 스타트',
          onboarding_company_name: '회사명',
          onboarding_company_name_placeholder: '회사 전체 이름을 입력하세요',
        },
      }),
    });

    // 设置 cookie 为 ko
    document.cookie = 'lang=ko; path=/';

    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    // 等待韩语翻译加载
    const langEl = await screen.findByTestId('currentLang');
    // Cookie 为 ko
    expect(langEl.textContent).toBe('ko');

    // 检查韩语翻译
    const titleEl = await screen.findByText('3단계 콜드 스타트', {}, { timeout: 2000 });
    expect(titleEl).toBeInTheDocument();
  });

  // ── Test 6: setLang 调用时设置 cookie ──
  test('6. setLang 设置 cookie', () => {
    // 创建一个测试组件在一个单独的上下文中
    function SetLangTest() {
      const { setLang } = useTranslation();
      return (
        <button
          data-testid="set-ko"
          onClick={() => setLang('ko')}
        >
          Set KO
        </button>
      );
    }

    render(
      <I18nProvider>
        <SetLangTest />
      </I18nProvider>
    );

    const btn = screen.getByTestId('set-ko');
    act(() => {
      fireEvent.click(btn);
    });

    // setLang 应设置 cookie
    expect(mockCookie).toContain('lang=ko');
  });

  // ── Test 7: setLang 存储到 localStorage ──
  test('7. setLang 存储到 localStorage', () => {
    function SetLangTest() {
      const { setLang } = useTranslation();
      return (
        <button
          data-testid="set-en"
          onClick={() => setLang('en')}
        >
          Set EN
        </button>
      );
    }

    render(
      <I18nProvider>
        <SetLangTest />
      </I18nProvider>
    );

    const btn = screen.getByTestId('set-en');
    act(() => {
      fireEvent.click(btn);
    });

    expect(localStorageMock.getItem('chainke_lang')).toBe('en');
  });

  // ── Test 8: 没有 Provider 时返回降级值 ──
  test('8. 无 Provider 时 hook 返回降级值（不崩溃）', () => {
    function NoProviderTest() {
      const { t, currentLang, ready } = useTranslation();
      return (
        <div>
          <span data-testid="no-provider-lang">{currentLang}</span>
          <span data-testid="no-provider-ready">{ready ? 'true' : 'false'}</span>
          <span data-testid="no-provider-t">{t('some_key', 'fallback_val')}</span>
        </div>
      );
    }

    render(<NoProviderTest />);

    expect(screen.getByTestId('no-provider-lang').textContent).toBe('zh');
    expect(screen.getByTestId('no-provider-ready').textContent).toBe('true');
    expect(screen.getByTestId('no-provider-t').textContent).toBe('fallback_val');
  });

  // ── Test 9: 翻译加载完成后 ready 为 true ──
  test('9. 翻译异步加载后 ready 正确切换', async () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    const readyEl = screen.getByTestId('ready');
    // 最终应为 true
    await waitFor(() => {
      expect(readyEl.textContent).toBe('true');
    }, { timeout: 2000 });
  });

  // ── Test 10: API 失败时降级到内置翻译 ──
  test('10. API 失败时降级到内置本地翻译', async () => {
    // API 请求失败
    mockFetch.mockRejectedValue(new Error('Network error'));

    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    // 内置翻译中的值
    const companyEl = await screen.findByTestId('t_company');
    // 内置 zh.json 中有 "onboarding_company_name": "公司名称"
    expect(companyEl.textContent).toBe('公司名称');
  });

  // ── Test 11: localStorage 缓存被优先使用 ──
  test('11. localStorage 缓存优先于 API', async () => {
    // 预置缓存
    localStorageMock.setItem('chainke_i18n_cache', JSON.stringify({
      zh: {
        onboarding_title: '缓存标题',
        onboarding_company_name: '缓存公司名',
      },
    }));

    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    // 缓存应当立即生效
    const titleEl = screen.getByTestId('t_title');
    expect(titleEl.textContent).toBe('缓存标题');
  });

  // ── Test 12: 初始语言检测使用 navigator.language ──
  test('12. 检测浏览器语言', () => {
    // 设置 navigator.language 为 ko-KR
    Object.defineProperty(navigator, 'language', {
      get: () => 'ko-KR',
      configurable: true,
    });

    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>
    );

    const langEl = screen.getByTestId('currentLang');
    expect(langEl.textContent).toBe('ko');
  });
});

// 需要从 @testing-library/react 导入 waitFor
import { waitFor } from '@testing-library/react';
