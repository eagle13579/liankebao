const API_BASE = import.meta.env.VITE_API_BASE ?? '';

interface ApiResponse<T> {
  code: number;
  message: string;
  data?: T;
}

function loadToken(): string | null { return localStorage.getItem('token'); }
function saveToken(t: string) { localStorage.setItem('token', t); }
function removeToken() { localStorage.removeItem('token'); }

async function request<T>(path: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const t = loadToken();
  const isFormData = options?.body instanceof FormData;
  const headers: Record<string,string> = isFormData ? {} : {'Content-Type': 'application/json'};
  if (t) headers['Authorization'] = 'Bearer ' + t;
    try {
    const res = await fetch(API_BASE + path, {...options, headers});
    if (!res.ok) {
      // 尝试读取后端的错误详情，用人话显示
      try {
        const errBody = await res.json();
        const detail = errBody?.detail || errBody?.message || '';
        if (Array.isArray(detail)) {
          // FastAPI 422 验证错误格式
          const msgs = detail.map((d: any) => d.msg).filter(Boolean);
          return { code: res.status, message: msgs.join('；') || `请求数据有误` };
        }
        if (typeof detail === 'string' && detail) {
          return { code: res.status, message: detail };
        }
      } catch {}
      return { code: res.status, message: `操作失败，请检查输入是否正确` };
    }
    const json = await res.json();
    // 兼容两种后端响应格式：
    // 格式A（8000后端）: { token, access_token, user, ... } 扁平格式 → 包装为 {code:200, data:json}
    // 格式B（8001后端）: { code, data, message, ... } 嵌套格式 → 原样返回
    if (json.code !== undefined) return json;
    return { code: 200, message: 'ok', data: json };
  } catch (e: any) {
    console.error('[API Error]', path, e);
    return { code: 500, message: e.message || '网络错误，请检查连接' };
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: any) => request<T>(path, {method:'POST', body: JSON.stringify(body)}),
  put: <T>(path: string, body: any) => request<T>(path, {method:'PUT', body: JSON.stringify(body)}),
  request: <T>(path: string, options?: RequestInit) => request<T>(path, options),
  saveToken, loadToken, removeToken,
  // 埋点追踪辅助函数
  track: (eventType: string, data?: Record<string, any>) => {
    const userId = (() => {
      try {
        const token = loadToken();
        if (!token) return null;
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.user_id || payload.sub || null;
      } catch { return null; }
    })();
    const payload = { event_type: eventType, user_id: userId, ...data };
    // 异步 fire-and-forget
    request('/api/events/track', {method:'POST', body: JSON.stringify(payload)}).catch(() => {});
  },
};
