import { useNavigate } from 'react-router-dom';
import { Handshake, MessageCircle, Smartphone, Mail, ShieldCheck, Network, ArrowLeft, Camera, CheckCircle2, ArrowRight, Sparkles, QrCode, ChevronRight, Globe, Award, Lock } from 'lucide-react';
import { useState } from 'react';
import { api } from '../api/client';
import { Loading } from '../components/StatusComponents';

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleWechatLogin = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.post<{token: string; access_token: string; user: any}>('/api/auth/login', { username, password });
      const token = res.data?.token || res.data?.access_token;
      if (res.code === 200 && token) {
        api.saveToken(token);
        navigate('/home', { state: { transition: 'push' } });
      } else {
        setError(res.message || '登录失败');
      }
    } catch (e: any) {
      setError('网络错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen login-mesh font-sans relative overflow-hidden">
      {/* Decorative floating bubbles */}
      <div className="bubble w-72 h-72 bg-sky-400 -top-20 -left-20" />
      <div className="bubble w-96 h-96 bg-blue-400 -top-40 -right-40" />
      <div className="bubble w-64 h-64 bg-cyan-400 bottom-40 -right-16" />
      <div className="bubble w-48 h-48 bg-indigo-400 bottom-20 -left-24" />

      {/* Subtle grid pattern overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(14,165,233,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(14,165,233,0.03)_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

      <header className="fixed top-0 w-full z-50 bg-white/60 backdrop-blur-md border-b border-sky-100/50 flex justify-between items-center px-4 h-14">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg brand-gradient flex items-center justify-center shadow-sm">
            <Handshake className="w-4 h-4 text-white" />
          </div>
          <span className="text-base font-bold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent font-manrope">链客宝</span>
        </div>
        <button
          onClick={() => navigate('/register', { state: { transition: 'push' } })}
          className="text-xs font-bold text-sky-600 bg-sky-50 px-4 py-1.5 rounded-full border border-sky-100 hover:bg-sky-100 active:scale-95 transition-all"
        >
          注册
        </button>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-6 pt-20 pb-8 relative z-10">
        {/* Brand Hero */}
        <section className="text-center mb-10 animate-[fadeIn_0.6s_ease-out]">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-white/80 shadow-lg shadow-sky-200/40 border border-sky-100/60 mb-5 glow-pulse">
            <Handshake className="w-10 h-10 text-sky-500" />
          </div>
          <h1 className="text-3xl font-extrabold font-manrope mb-2">
            <span className="bg-gradient-to-r from-sky-600 via-blue-600 to-indigo-600 bg-clip-text text-transparent">
              链客宝
            </span>
          </h1>
          <p className="text-slate-500 text-sm tracking-wide">企业家供需匹配平台 · 精准链接商业伙伴</p>
          <div className="flex items-center justify-center gap-2 mt-3">
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full font-medium">
              <Sparkles className="w-3 h-3" /> 企业认证
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] text-sky-600 bg-sky-50 px-2.5 py-1 rounded-full font-medium">
              <ShieldCheck className="w-3 h-3" /> 安全保障
            </span>
          </div>
        </section>

        {/* Login Form Card */}
        <section className="w-full max-w-sm animate-[fadeIn_0.8s_ease-out]">
          <div className="bg-white/70 backdrop-blur-2xl rounded-3xl p-8 border border-white/80 shadow-xl shadow-sky-900/5 space-y-5">
            {/* Form fields */}
            <div className="space-y-3">
              <div className="relative group">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300 group-focus-within:text-sky-500 transition-colors">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
                  </svg>
                </div>
                <input
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  className="w-full h-12 bg-slate-50/80 border border-slate-200 rounded-xl pl-12 pr-4 text-sm text-slate-700 placeholder:text-slate-400 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all"
                  placeholder="请输入账号"
                />
              </div>
              <div className="relative group">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300 group-focus-within:text-sky-500 transition-colors">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
                  </svg>
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full h-12 bg-slate-50/80 border border-slate-200 rounded-xl pl-12 pr-4 text-sm text-slate-700 placeholder:text-slate-400 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all"
                  placeholder="请输入密码"
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5">
                <div className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                <p className="text-xs text-red-600">{error}</p>
              </div>
            )}

            <button
              onClick={handleWechatLogin}
              disabled={loading}
              className="w-full h-13 bg-gradient-to-r from-sky-500 to-blue-600 text-white rounded-xl font-bold text-sm flex items-center justify-center gap-2.5 active:scale-[0.98] transition-all duration-150 shadow-lg shadow-sky-500/25 hover:shadow-xl hover:shadow-sky-500/30 disabled:opacity-60"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>登录中...</span>
                </div>
              ) : (
                <>
                  <Lock className="w-5 h-5" />
                  <span>登录</span>
                </>
              )}
            </button>

            {/* Divider */}
            <div className="flex items-center gap-3 py-1">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-slate-200 to-transparent" />
              <span className="text-[10px] text-slate-400 font-medium tracking-wider">其他方式</span>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-slate-200 to-transparent" />
            </div>

            {/* Social login buttons */}
            <div className="flex justify-center gap-5">
              <button className="w-12 h-12 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-500 hover:border-sky-200 hover:text-sky-500 hover:shadow-sm active:scale-90 transition-all duration-150 shadow-sm">
                <Smartphone className="w-5 h-5" />
              </button>
              <button className="w-12 h-12 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-500 hover:border-sky-200 hover:text-sky-500 hover:shadow-sm active:scale-90 transition-all duration-150 shadow-sm">
                <Mail className="w-5 h-5" />
              </button>
              <button className="w-12 h-12 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-500 hover:border-sky-200 hover:text-sky-500 hover:shadow-sm active:scale-90 transition-all duration-150 shadow-sm">
                <QrCode className="w-5 h-5" />
              </button>
            </div>
            <button
              onClick={() => {/* WeChat OAuth */}}
              className="w-full h-12 bg-[#07C160] text-white font-bold text-sm rounded-xl flex items-center justify-center gap-2 active:scale-[0.98] transition-all duration-150 shadow-sm hover:bg-[#06AD56]"
            >
              <MessageCircle className="w-5 h-5" />
              <span>微信一键登录</span>
            </button>

            {/* Agreement */}
            <div className="text-center pt-1">
              <p className="text-[10px] text-slate-400 leading-relaxed">
                登录即表示同意
                <span className="text-sky-600 font-semibold hover:underline cursor-pointer">《用户协议》</span>
                <span className="text-slate-300 mx-0.5">和</span>
                <span className="text-sky-600 font-semibold hover:underline cursor-pointer">《隐私政策》</span>
              </p>
            </div>
          </div>
        </section>

        {/* Trust badges */}
        <section className="w-full max-w-sm mt-8 animate-[fadeIn_1s_ease-out]">
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white/50 backdrop-blur-sm p-3 rounded-2xl border border-white/70 text-center">
              <div className="w-8 h-8 rounded-lg bg-sky-50 flex items-center justify-center mx-auto mb-1.5">
                <ShieldCheck className="w-4 h-4 text-sky-600" />
              </div>
              <p className="text-[10px] font-bold text-slate-700">企业实名认证</p>
              <p className="text-[8px] text-slate-400 mt-0.5">全平台商户深度认证</p>
            </div>
            <div className="bg-white/50 backdrop-blur-sm p-3 rounded-2xl border border-white/70 text-center">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center mx-auto mb-1.5">
                <Lock className="w-4 h-4 text-emerald-600" />
              </div>
              <p className="text-[10px] font-bold text-slate-700">数据加密传输</p>
              <p className="text-[8px] text-slate-400 mt-0.5">SSL/TLS 安全通道</p>
            </div>
            <div className="bg-white/50 backdrop-blur-sm p-3 rounded-2xl border border-white/70 text-center">
              <div className="w-8 h-8 rounded-lg bg-amber-50 flex items-center justify-center mx-auto mb-1.5">
                <Award className="w-4 h-4 text-amber-600" />
              </div>
              <p className="text-[10px] font-bold text-slate-700">平台服务保障</p>
              <p className="text-[8px] text-slate-400 mt-0.5">资金担保 · 放心交易</p>
            </div>
          </div>
        </section>
      </main>

      <footer className="py-6 text-center relative z-10 space-y-2">
        <p className="text-xs text-slate-500">
          还没有账号？
          <button onClick={() => navigate('/register', { state: { transition: 'push' } })} className="text-sky-600 font-bold hover:underline ml-1">
            去注册
          </button>
        </p>
        <p className="text-[9px] text-slate-400 tracking-wider font-medium">
          商业精英网络 © 2025 链客宝 · 版权所有
        </p>
      </footer>

      {/* Entrance animation keyframe */}
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(16px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

export function UserRegistration() {
  const navigate = useNavigate();
  const [role, setRole] = useState('buyer');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [company, setCompany] = useState('');
  const [position, setPosition] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [registerSuccess, setRegisterSuccess] = useState(false);

  const handleFinish = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.post<{token: string; user: any}>('/api/auth/register', {
        username, password, name, phone, company, position, role
      });
      if (res.code === 200) {
        setRegisterSuccess(true);
        setTimeout(() => {
          navigate('/', { state: { transition: 'push' } });
        }, 2000);
      } else {
        setError(res.message || '注册失败');
      }
    } catch (e: any) {
      setError('网络错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    navigate('/', { state: { transition: 'push_back' } });
  };

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50 via-white to-white font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-sky-100/50 h-14 flex items-center px-4">
        <button onClick={handleBack} className="text-sky-600 active:scale-90 transition-transform p-1 -ml-1">
          <ArrowLeft className="w-6 h-6" />
        </button>
        <h1 className="ml-3 font-manrope text-lg font-bold text-slate-800">完善资料</h1>
      </header>

      <main className="pt-20 px-4 max-w-md mx-auto space-y-8">
        <section className="flex flex-col items-center">
          <div className="relative group cursor-pointer">
            <div className="w-24 h-24 rounded-full bg-gradient-to-br from-sky-100 to-blue-50 border-2 border-dashed border-sky-200 flex items-center justify-center group-hover:border-sky-400 transition-colors">
              <Camera className="w-8 h-8 text-sky-400" />
            </div>
            <div className="absolute bottom-0 right-0 bg-gradient-to-br from-sky-500 to-blue-600 text-white p-1.5 rounded-full shadow-lg border-2 border-white">
              <span className="text-xs font-bold">+</span>
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-400">点击上传头像</p>
        </section>

        <section className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs text-slate-500 font-medium px-1">用户名</label>
            <input value={username} onChange={e => setUsername(e.target.value)} className="w-full h-12 bg-white border border-slate-200 rounded-xl px-4 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all text-sm" placeholder="登录用户名" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-500 font-medium px-1">密码</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} className="w-full h-12 bg-white border border-slate-200 rounded-xl px-4 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all text-sm" placeholder="登录密码" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-500 font-medium px-1">姓名</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full h-12 bg-white border border-slate-200 rounded-xl px-4 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all text-sm" placeholder="请输入真实姓名" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-500 font-medium px-1">手机号码</label>
            <input value={phone} onChange={e => setPhone(e.target.value)} className="w-full h-12 bg-white border border-slate-200 rounded-xl px-4 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all text-sm" placeholder="请输入11位手机号" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-500 font-medium px-1">公司名称</label>
            <input value={company} onChange={e => setCompany(e.target.value)} className="w-full h-12 bg-white border border-slate-200 rounded-xl px-4 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all text-sm" placeholder="请输入所在单位全称" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-500 font-medium px-1">职位</label>
            <input value={position} onChange={e => setPosition(e.target.value)} className="w-full h-12 bg-white border border-slate-200 rounded-xl px-4 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 outline-none transition-all text-sm" placeholder="请输入担任职位" />
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <span className="w-1 h-5 bg-sky-500 rounded-full"></span>
            选择您的身份
          </h2>
          <div className="grid gap-3">
            {[
              { id: 'buyer', title: '企业主 / 购买者', desc: '寻找优质产品与商务合作', emoji: '🤝' },
              { id: 'promoter', title: '推广员', desc: '共享资源，赚取高额分销佣金', emoji: '📢' },
              { id: 'supplier', title: '产品方', desc: '上架您的优质货源，触达海量推客', emoji: '📦' }
            ].map(r => (
              <div
                key={r.id}
                onClick={() => setRole(r.id)}
                className={`p-4 rounded-2xl border-2 transition-all cursor-pointer flex items-center gap-4 ${
                  role === r.id
                    ? 'border-sky-500 bg-white shadow-md shadow-sky-100'
                    : 'border-slate-100 bg-white/50 hover:border-slate-200'
                }`}
              >
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-xl ${
                  role === r.id ? 'bg-sky-50' : 'bg-slate-50'
                }`}>
                  {r.emoji}
                </div>
                <div className="flex-1">
                  <h3 className={`font-bold ${role === r.id ? 'text-sky-600' : 'text-slate-800'}`}>{r.title}</h3>
                  <p className="text-[10px] text-slate-400">{r.desc}</p>
                </div>
                {role === r.id && <CheckCircle2 className="w-5 h-5 text-sky-500" />}
              </div>
            ))}
          </div>
        </section>

        {error && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5">
            <div className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
            <p className="text-xs text-red-600">{error}</p>
          </div>
        )}

        <div className="flex items-start gap-2 py-4">
          <input type="checkbox" id="terms" className="mt-1 rounded text-sky-500 focus:ring-sky-500" defaultChecked />
          <label htmlFor="terms" className="text-[11px] text-slate-400 leading-relaxed">
            我已阅读并同意 <span className="text-sky-600 font-medium">《用户注册协议》</span> 与 <span className="text-sky-600 font-medium">《隐私政策》</span>
          </label>
        </div>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 p-4 bg-white/80 backdrop-blur-md border-t border-slate-100">
        {registerSuccess ? (
          <div className="w-full h-13 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center gap-2 text-emerald-700 font-bold text-sm">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            <span>注册成功，请返回登录</span>
          </div>
        ) : (
          <button
            onClick={handleFinish}
            disabled={loading}
            className="w-full h-13 bg-gradient-to-r from-sky-500 to-blue-600 text-white font-manrope font-bold text-base rounded-xl shadow-lg shadow-sky-500/25 flex items-center justify-center gap-2 active:scale-[0.98] transition-transform disabled:opacity-60"
          >
            {loading ? (
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>注册中...</span>
              </div>
            ) : (
              <>
                完成注册
                <ArrowRight className="w-5 h-5" />
              </>
            )}
          </button>
        )}
      </footer>
    </div>
  );
}
