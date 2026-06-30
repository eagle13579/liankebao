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

// ── 微信一键登录 ──
function WeChatPromptDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-slate-900 border border-white/10 rounded-2xl p-8 max-w-sm mx-4 text-center" onClick={e => e.stopPropagation()}>
        <div className="text-5xl mb-4">📱</div>
        <h3 className="text-lg font-semibold text-white mb-2">请在微信客户端打开</h3>
        <p className="text-sm text-slate-400 mb-4">链客宝微信登录功能仅支持在微信内使用，请使用微信扫描二维码或在微信中打开此页面。</p>
        <button onClick={onClose} className="px-6 py-2 rounded-xl text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 transition">我知道了</button>
      </div>
    </div>
  );
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

// ── 微信一键登录按钮 ──
function WeChatLoginButton({ onSuccess }: { onSuccess: () => void }) {
  const [loading, setLoading] = useState(false);
  const [prompt, setPrompt] = useState(false);

  const handleWeChatLogin = async () => {
    const isWeChat = navigator.userAgent.toLowerCase().includes('micromessenger');
    if (!isWeChat) {
      // 非微信浏览器 → 走开放平台扫码登录 (qrconnect)
      try {
        setLoading(true);
        const resp = await fetch('/api/wechat/qrconnect-url', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ redirect_uri: location.href.split('?')[0] }),
        });
        if (!resp.ok) throw new Error('获取扫码登录URL失败');
        const data = await resp.json();
        location.href = data.url;
      } catch (err) {
        console.error('扫码登录失败', err);
        setPrompt(true); // API 不可用时 fallback 到提示弹窗
      } finally {
        setLoading(false);
      }
      return;
    }

    setLoading(true);
    try {
      // 1. 获取 JS-SDK 配置
      const url = location.href.split('#')[0];
      const resp = await fetch('/api/wechat/js-config', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      if (!resp.ok) throw new Error('获取微信配置失败');
      const cfg = await resp.json();

      // 2. 调用 wx.config（如果 wx 已加载）
      if (typeof wx !== 'undefined') {
        wx.config({ debug: false, appId: cfg.appid, timestamp: cfg.timestamp, nonceStr: cfg.noncestr, signature: cfg.signature, jsApiList: [] });
      }

      // 3. 检查是否有 OAuth 回调 code
      const params = new URLSearchParams(location.search);
      const code = params.get('code');
      if (code) {
        const loginResp = await fetch('/api/wechat/oauth/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code }),
        });
        if (!loginResp.ok) throw new Error('微信登录失败');
        const userData = await loginResp.json();
        localStorage.setItem('wechat_user', JSON.stringify(userData));
        localStorage.setItem('token', userData.openid);
        onSuccess();
      } else {
        // 4. 跳转微信 OAuth 授权
        const state = Math.random().toString(36).slice(2);
        const redirectUri = encodeURIComponent(location.href.split('?')[0]);
        location.href = `https://open.weixin.qq.com/connect/oauth2/authorize?appid=${cfg.appid}&redirect_uri=${redirectUri}&response_type=code&scope=snsapi_userinfo&state=${state}#wechat_redirect`;
      }
    } catch (err) {
      console.error('微信登录失败', err);
    } finally {
      setLoading(false);
    }
  };

  return (<>
    <div className="relative my-4"><div className="absolute inset-0 flex items-center"><div className="w-full border-t border-white/10"></div></div><div className="relative flex justify-center"><span className="bg-slate-900 px-3 text-xs text-slate-500">其他方式</span></div></div>
    <button onClick={handleWeChatLogin} disabled={loading}
      className="w-full py-2.5 rounded-xl text-sm font-semibold text-white bg-green-600 hover:bg-green-500 disabled:opacity-50 transition-all duration-200 shadow-lg shadow-green-500/20 flex items-center justify-center gap-2">
      {loading ? (<span className="flex items-center justify-center gap-2"><svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>处理中...</span>)
      : (<><svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 0 0 .167-.054l1.903-1.114a.864.864 0 0 1 .717-.098 10.16 10.16 0 0 0 2.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178A1.17 1.17 0 0 1 4.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178 1.17 1.17 0 0 1-1.162-1.178c0-.651.52-1.18 1.162-1.18z"/></svg>微信一键登录</>)}
    </button>
    <WeChatPromptDialog open={prompt} onClose={() => setPrompt(false)} />
  </>);
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
            <>
              <LoginForm onSuccess={handleSuccess} />
              <WeChatLoginButton onSuccess={handleSuccess} />
            </>
          ) : (
            <RegisterForm onSuccess={handleSuccess} />
          )}
        </div>
        {/* ICP备案号 */}
        <div className="mt-6 text-center text-xs text-slate-500/60">
          <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" className="hover:text-slate-400 transition-colors">
            沪ICP备2026007459号-2
          </a>
        </div>
      </div>
    </div>
  );
}
