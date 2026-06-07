/**
 * 链客宝 - ABACC销售话术模板 API客户端
 * 注入点：话术模板CRUD + 张力武器库API调用
 * 规则：纯新增，不修改现有业务逻辑
 */

import type {
  SalesScript,
  DataAugmenter,
  MagicWords,
  TensionCheck,
  TensionAnalysis,
  AugmenterMode,
  ApiResponse,
} from './salesScriptTypes';

const BASE = '/api/sales-script';

/** 通用fetch包装 */
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ===== ABACC话术CRUD =====

/** 获取所有预设话术模板 */
export async function fetchPresets(): Promise<{ presets: SalesScript[]; total: number }> {
  return request(`${BASE}/presets`);
}

/** 获取单个话术模板详情 */
export async function fetchPreset(id: number): Promise<SalesScript> {
  return request(`${BASE}/presets/${id}`);
}

/** 创建自定义话术模板 */
export async function createScript(script: SalesScript): Promise<{ id: number; message: string }> {
  return request(`${BASE}/scripts`, {
    method: 'POST',
    body: JSON.stringify(script),
  });
}

/** 更新话术模板 */
export async function updateScript(id: number, script: SalesScript): Promise<{ message: string }> {
  return request(`${BASE}/scripts/${id}`, {
    method: 'PUT',
    body: JSON.stringify(script),
  });
}

/** 删除话术模板 */
export async function deleteScript(id: number): Promise<{ message: string }> {
  return request(`${BASE}/scripts/${id}`, {
    method: 'DELETE',
  });
}

// ===== 张力武器库 =====

/** 获取数据增强器示例 */
export async function fetchDataAugmenter(mode?: AugmenterMode): Promise<DataAugmenter> {
  const params = mode ? `?mode=${mode}` : '';
  return request(`${BASE}/weapons/data-augmenter${params}`);
}

/** 获取话术引导词推荐 */
export async function fetchMagicWords(category?: string): Promise<MagicWords> {
  const params = category ? `?category=${category}` : '';
  return request(`${BASE}/weapons/magic-words${params}`);
}

/** 获取张力自检评分标准 */
export async function fetchTensionCheck(score?: number): Promise<TensionCheck> {
  const params = score !== undefined ? `?score=${score}` : '';
  return request(`${BASE}/weapons/tension-check${params}`);
}

/** 分析话术张力并评分 */
export async function analyzeTension(text: string): Promise<TensionAnalysis> {
  return request(`${BASE}/weapons/analyze`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}
