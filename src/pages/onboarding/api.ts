/**
 * 三步冷启动引导 — API 调用
 *
 * 使用原生 fetch 调用后端接口，不依赖全局 api client，
 * 确保在引导阶段（用户未完成配置前）也能正常工作。
 */

import type { Template } from '../../components/onboarding/TemplateSelector';
import type { OnboardingDefaults, TemplatesResponse } from './types';

const API_BASE = '/api/v1/onboarding';

/** 通用 fetch 封装，含错误处理、超时与 JSON 解析 */
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  try {
    const resp = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!resp.ok) {
      const body = await resp.text().catch(() => '');
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}${body ? ` — ${body}` : ''}`);
    }

    return await resp.json();
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('请求超时，请检查网络连接后重试');
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * 获取模板列表（GET /api/v1/onboarding/templates）
 * 返回 6 个预设名片模板
 */
export async function fetchTemplates(): Promise<Template[]> {
  const data = await request<TemplatesResponse>(`${API_BASE}/templates`);
  return data.templates ?? [];
}

/**
 * 获取引导默认配置（GET /api/v1/onboarding/defaults）
 * 返回三步引导的初始填充数据
 */
export async function fetchOnboardingDefaults(): Promise<OnboardingDefaults | null> {
  try {
    return await request<OnboardingDefaults>(`${API_BASE}/defaults`);
  } catch {
    // 默认配置接口可能尚未部署，静默降级返回 null
    return null;
  }
}
