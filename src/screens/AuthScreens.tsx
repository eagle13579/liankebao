import { useNavigate } from 'react-router-dom';
import { Handshake, MessageCircle, Smartphone, Mail, ShieldCheck, Network, ArrowLeft, Camera, CheckCircle2, ArrowRight } from 'lucide-react';
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
      const res = await api.post<{token: string; user: any}>('/api/auth/login', { username, password });
      if (res.code === 200 && res.data?.token) {
        api.saveToken(res.data.token);
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
    <div className="flex flex-col min-h-screen login-mesh font-sans">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg/80 backdrop-blur-md border-b border-border-light flex justify-between items-center px-4 h-14">
        <button className="text-primary-container"><ArrowLeft className="w-6 h-6" /></button>
        <span className="text-xl font-bold text-primary-container font-manrope">Liankebao</span>
        <div className="w-6"></div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-6 pt-24 pb-12">
        <section className="text-center mb-16">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-white shadow-xl border border-yellow-100 mb-6">
            <Handshake className="w-10 h-10 text-primary" fill="currentColor" />
          </div>
          <h1 className="text-2xl font-bold text-primary-container font-manrope mb-2">Liankebao</h1>
          <p className="text-secondary tracking-widest opacity-80">企业家供需匹配平台</p>
        </section>

        <section className="w-full max-w-sm space-y-6">
          <div className="bg-white/60 backdrop-blur-xl rounded-2xl p-8 border border-white shadow-sm space-y-4">
            <div className="space-y-2">
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none"
                placeholder="用户名"
              />
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none"
                placeholder="密码"
              />
            </div>
            {error && <p className="text-red-500 text-xs text-center">{error}</p>}
            <button
              onClick={handleWechatLogin}
              disabled={loading}
              className="w-full h-14 bg-primary-container text-white rounded-xl font-semibold flex items-center justify-center gap-3 active:scale-95 transition-transform shadow-lg shadow-sky-600/20 disabled:opacity-60"
            >
              <MessageCircle className="w-6 h-6" />
              {loading ? '登录中...' : '微信一键登录'}
            </button>
            <div className="text-center">
              <span className="text-xs text-text-muted">测试账号: admin/admin123 或 buyer1/123456</span>
            </div>
            <div className="mt-4 text-center">
              <p className="text-xs text-text-muted leading-relaxed">
                还没有账号？
                <button onClick={() => navigate('/register', { state: { transition: 'push' } })} className="text-primary-container font-semibold">注册</button>
              </p>
            </div>
            <div className="mt-4 text-center">
              <p className="text-xs text-text-muted leading-relaxed">
                登录即表示同意
                <span className="text-primary-container font-semibold">《用户协议》</span> 和 <span className="text-primary-container font-semibold">《隐私政策》</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 py-4">
            <div className="h-px flex-1 bg-border-light"></div>
            <span className="text-xs text-text-muted">其他方式</span>
            <div className="h-px flex-1 bg-border-light"></div>
          </div>

          <div className="flex justify-center gap-6">
            <button className="w-12 h-12 rounded-full border border-border-light flex items-center justify-center text-secondary hover:bg-white transition-colors">
              <Smartphone className="w-5 h-5" />
            </button>
            <button className="w-12 h-12 rounded-full border border-border-light flex items-center justify-center text-secondary hover:bg-white transition-colors">
              <Mail className="w-5 h-5" />
            </button>
          </div>
        </section>

        <section className="w-full max-w-sm mt-16 grid grid-cols-2 gap-3">
          <div className="bg-white/40 p-4 rounded-xl border border-white/60 flex flex-col gap-2">
            <ShieldCheck className="w-5 h-5 text-primary-container" />
            <h3 className="text-xs font-bold text-on-surface">企业实名</h3>
            <p className="text-[10px] text-text-muted">全平台商户深度认证，安全交易</p>
          </div>
          <div className="bg-white/40 p-4 rounded-xl border border-white/60 flex flex-col gap-2">
            <Network className="w-5 h-5 text-primary-container" />
            <h3 className="text-xs font-bold text-on-surface">供需直达</h3>
            <p className="text-[10px] text-text-muted">大数据算法精准匹配，省时高效</p>
          </div>
        </section>
      </main>

      <footer className="py-8 text-center opacity-40">
        <p className="text-[10px] font-bold uppercase tracking-widest">Premium Business Network © 2024 Liankebao</p>
      </footer>
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

  const handleFinish = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.post<{token: string; user: any}>('/api/auth/register', {
        username, password, name, phone, company, position, role
      });
      if (res.code === 200 && res.data?.token) {
        api.saveToken(res.data.token);
        navigate('/home', { state: { transition: 'push' } });
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
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-32">
      <header className="fixed top-0 left-0 right-0 z-50 bg-neutral-bg border-b border-border-light h-14 flex items-center px-4">
        <button onClick={handleBack} className="text-primary-container"><ArrowLeft className="w-6 h-6" /></button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">完善资料</h1>
      </header>

      <main className="pt-20 px-4 max-w-md mx-auto space-y-8">
        <section className="flex flex-col items-center">
          <div className="relative group cursor-pointer">
            <div className="w-24 h-24 rounded-full bg-white border-2 border-dashed border-border-light flex items-center justify-center">
              <Camera className="w-8 h-8 text-text-muted" />
            </div>
            <div className="absolute bottom-0 right-0 bg-primary-container text-white p-1.5 rounded-full shadow-lg border-2 border-white">
              <span className="text-xs font-bold">+</span>
            </div>
          </div>
          <p className="mt-2 text-xs text-text-muted">点击上传头像</p>
        </section>

        <section className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs text-secondary px-1">用户名</label>
            <input value={username} onChange={e => setUsername(e.target.value)} className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none" placeholder="登录用户名" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-secondary px-1">密码</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none" placeholder="登录密码" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-secondary px-1">姓名</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none" placeholder="请输入真实姓名" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-secondary px-1">手机号码</label>
            <input value={phone} onChange={e => setPhone(e.target.value)} className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none" placeholder="请输入11位手机号" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-secondary px-1">公司名称</label>
            <input value={company} onChange={e => setCompany(e.target.value)} className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none" placeholder="请输入所在单位全称" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-secondary px-1">职位</label>
            <input value={position} onChange={e => setPosition(e.target.value)} className="w-full h-12 bg-white border border-border-light rounded-xl px-4 focus:ring-1 focus:ring-primary-container outline-none" placeholder="请输入担任职位" />
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="text-lg font-bold text-on-surface">选择您的身份</h2>
          <div className="grid gap-3">
            {[
              { id: 'buyer', title: '企业主 / 购买者', desc: '寻找优质产品与商务合作', icon: 'Business' },
              { id: 'promoter', title: '推广员', desc: '共享资源，赚取高额分销佣金', icon: 'Megaphone' },
              { id: 'supplier', title: '产品方', desc: '上架您的优质货源，触达海量推客', icon: 'Package' }
            ].map(r => (
              <div 
                key={r.id}
                onClick={() => setRole(r.id)}
                className={`p-4 rounded-2xl border-2 transition-all cursor-pointer flex items-center gap-4 ${role === r.id ? 'border-primary-container bg-white shadow-sm' : 'border-border-light bg-white/50'}`}
              >
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${role === r.id ? 'bg-primary-container/10' : 'bg-slate-100'}`}>
                  {r.id === 'buyer' && <Handshake className={role === r.id ? 'text-primary-container' : 'text-slate-400'} />}
                  {r.id === 'promoter' && <Network className={role === r.id ? 'text-primary-container' : 'text-slate-400'} />}
                  {r.id === 'supplier' && <Network className={role === r.id ? 'text-primary-container' : 'text-slate-400'} />}
                </div>
                <div className="flex-1">
                  <h3 className={`font-bold ${role === r.id ? 'text-primary-container' : 'text-on-surface'}`}>{r.title}</h3>
                  <p className="text-[10px] text-text-muted">{r.desc}</p>
                </div>
                {role === r.id && <CheckCircle2 className="w-5 h-5 text-primary-container" fill="currentColor" />}
              </div>
            ))}
          </div>
        </section>

        {error && <p className="text-red-500 text-xs text-center">{error}</p>}

        <div className="flex items-start gap-2 py-4">
          <input type="checkbox" id="terms" className="mt-1 rounded text-primary-container" />
          <label htmlFor="terms" className="text-[11px] text-text-muted leading-relaxed">
            我已阅读并同意 <span className="text-primary-container font-medium">《用户注册协议》</span> 与 <span className="text-primary-container font-medium">《隐私政策》</span>
          </label>
        </div>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 p-4 bg-white/80 backdrop-blur-md border-t border-border-light">
        <button 
          onClick={handleFinish}
          disabled={loading}
          className="w-full h-14 bg-primary-container text-white font-manrope font-bold text-lg rounded-xl shadow-lg flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60"
        >
          {loading ? '注册中...' : '完成注册'}
          <ArrowRight className="w-6 h-6" />
        </button>
      </footer>
    </div>
  );
}
