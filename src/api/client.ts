const API_BASE = '/api';

interface ApiResponse<T> {
  code: number;
  message: string;
  data?: T;
}

function loadToken(): string | null { return localStorage.getItem('token'); }
function saveToken(t: string) { localStorage.setItem('token', t); }
function removeToken() { localStorage.removeItem('token'); }

async function request<T>(path: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const headers: Record<string,string> = {'Content-Type': 'application/json'};
  const t = loadToken();
  if (t) headers['Authorization'] = 'Bearer ' + t;
  const res = await fetch(API_BASE + path, {...options, headers});
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: any) => request<T>(path, {method:'POST', body: JSON.stringify(body)}),
  put: <T>(path: string, body: any) => request<T>(path, {method:'PUT', body: JSON.stringify(body)}),
  saveToken, loadToken, removeToken,
};

