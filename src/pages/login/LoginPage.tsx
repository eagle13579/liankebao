/**
 * 链客宝 — 登录/注册页面
 *
 * 暗色主题 + 毛玻璃效果 + 海洋蓝/紫色渐变
 * 登录调用 POST /api/auth/login
 * 注册调用 POST /api/auth/register
 * 注册后自动登录跳转
 *
 * 测试账号: admin / admin123
 */
import React, { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

// ── 登录 API ──
async function loginApi(username: string, password: string): Promise<{token: string; user: any}> {
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `登录失败 (${resp.status})`);
  }

  return await resp.json();
}

// ── 注册 API ──
async function registerApi(data: {
  username: string;
  password: string;
  name: string;
  phone: string;
  company: string;
}): Promise<{token: string; user: any; message: string}> {
  const resp = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `注册失败 (${resp.status})`);
  }

  return await resp.json();
}

// ── 装饰性背景粒子 ──
function BackgroundGlow() {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden">
      <div className="absolute -top-32 -left-32 w-96 h-96 bg-blue-500/20 rounded-full blur-[120px]" />
      <div className="absolute top-1/3 -right-20 w-80 h-80 bg-cyan-400/15 rounded-full blur-[100px]" />
      <div className="absolute -bottom-20 left-1/4 w-72 h-72 bg-purple-600/20 rounded-full blur-[100px]" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-br from-blue-500/5 via-transparent to-purple-600/5 rounded-full blur-[80px]" />
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }}
      />
    </div>
  );
}

// ── 登录表单 ──
function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedUser = username.trim();
    if (!trimmedUser) { setError('请输入用户名'); return; }
    if (!password) { setError('请输入密码'); return; }

    setLoading(true);
    try {
      const data = await loginApi(trimmedUser, password);
      localStorage.setItem('token', data.token);
      localStorage.setItem('user', JSON.stringify(data.user));
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">用户名</label>
        <input
          type="text" value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="请输入用户名"
          autoComplete="username" autoFocus
          className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10
                     text-sm text-white placeholder-slate-500
                     focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50
                     transition-all duration-200"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">密码</label>
        <input
          type="password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="请输入密码"
          autoComplete="current-password"
          className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10
                     text-sm text-white placeholder-slate-500
                     focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50
                     transition-all duration-200"
        />
      </div>
      <button type="submit" disabled={loading}
        className="w-full py-2.5 rounded-xl text-sm font-semibold text-white
                   bg-gradient-to-r from-blue-600 via-cyan-500 to-purple-600
                   hover:from-blue-500 hover:via-cyan-400 hover:to-purple-500
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-all duration-200 shadow-lg shadow-blue-500/20"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            登录中...
          </span>
        ) : '登 录'}
      </button>
      <p className="text-center text-xs text-slate-500">测试账号: admin / admin123</p>
    </form>
  );
}

// ── 注册表单 ──
function RegisterForm({ onSuccess }: { onSuccess: () => void }) {
  const [form, setForm] = useState({
    username: '', password: '', name: '', phone: '', company: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateField = (field: string, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.username.trim()) { setError('请输入用户名'); return; }
    if (form.password.length < 6) { setError('密码至少6位'); return; }

    setLoading(true);
    try {
      const data = await registerApi({
        username: form.username.trim(),
        password: form.password,
        name: form.name.trim(),
        phone: form.phone.trim(),
        company: form.company.trim(),
      });
      localStorage.setItem('token', data.token);
      localStorage.setItem('user', JSON.stringify(data.user));
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">用户名 *</label>
          <input type="text" value={form.username}
            onChange={(e) => updateField('username', e.target.value)}
            placeholder="用户名" autoFocus
            className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                       placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">密码 *</label>
          <input type="password" value={form.password}
            onChange={(e) => updateField('password', e.target.value)}
            placeholder="至少6位"
            className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                       placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">姓名</label>
          <input type="text" value={form.name}
            onChange={(e) => updateField('name', e.target.value)}
            placeholder="您的姓名"
            className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                       placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">手机号</label>
          <input type="text" value={form.phone}
            onChange={(e) => updateField('phone', e.target.value)}
            placeholder="手机号"
            className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                       placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50" />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-300 mb-1">公司</label>
        <input type="text" value={form.company}
          onChange={(e) => updateField('company', e.target.value)}
          placeholder="公司名称"
          className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-sm text-white
                     placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50" />
      </div>
      <button type="submit" disabled={loading}
        className="w-full py-2.5 rounded-xl text-sm font-semibold text-white
                   bg-gradient-to-r from-emerald-600 via-teal-500 to-cyan-600
                   hover:from-emerald-500 hover:via-teal-400 hover:to-cyan-500
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-all duration-200 shadow-lg shadow-emerald-500/20"
      >
        {loading ? '注册中...' : '注 册'}
      </button>
    </form>
  );
}

// ── 主组件 ──
export default function LoginPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string | null>(null);

  const handleSuccess = () => {
    navigate('/card', { replace: true });
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center bg-slate-950 overflow-hidden">
      <BackgroundGlow />

      <div className="relative z-10 w-full max-w-md mx-4">
        <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-3xl shadow-2xl p-8 sm:p-10">
          {/* Logo / 标题 */}
          <div className="text-center mb-6">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 via-cyan-300 to-purple-400 bg-clip-text text-transparent">
              链客宝
            </h1>
            <p className="mt-2 text-sm text-slate-400">企业家供需匹配平台</p>
          </div>

          {/* Tab 切换 */}
          <div className="flex mb-6 bg-white/5 rounded-xl p-1">
            <button
              onClick={() => setTab('login')}
              className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                tab === 'login'
                  ? 'bg-blue-600/30 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              登录
            </button>
            <button
              onClick={() => setTab('register')}
              className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                tab === 'register'
                  ? 'bg-emerald-600/30 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              注册
            </button>
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="mb-4 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/25 text-sm text-red-300 flex items-start gap-2">
              <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* 表单 */}
          {tab === 'login' ? (
            <LoginForm onSuccess={handleSuccess} />
          ) : (
            <RegisterForm onSuccess={handleSuccess} />
          )}
        </div>
      </div>
    </div>
  );
}
