const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8001';

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
      return { code: res.status, message: `HTTP ${res.status}: ${res.statusText}` };
    }
    return res.json();
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
};
