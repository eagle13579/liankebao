import { useNavigate } from 'react-router-dom';
import { ArrowLeft, User, Settings, LogOut, ChevronRight, Bell, Shield, HelpCircle, FileText, Star, Crown, Wallet, Building2, Phone, Mail, Edit3 } from 'lucide-react';
import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Loading, ErrorBlock } from '../components/StatusComponents';

interface UserProfile {
  id: number;
  username: string;
  name: string;
  phone?: string;
  company?: string;
  position?: string;
  role: string;
  avatar?: string;
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    setLoading(true);
    try {
      const res = await api.get<UserProfile>('/api/auth/me');
      if (res.data) setProfile(res.data);
    } catch (e: any) {
      console.error('Failed to load profile:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    api.removeToken();
    navigate('/', { state: { transition: 'none' } });
  };

  if (loading) return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
      <header className="fixed top-0 w-full z-50 bg-white border-b border-border-light flex items-center px-4 h-14">
        <button onClick={() => navigate(-1)} className="text-slate-600"><ArrowLeft className="w-6 h-6" /></button>
        <h1 className="ml-4 font-manrope text-lg font-bold text-on-surface">个人中心</h1>
      </header>
      <main className="pt-14"><Loading /></main>
    </div>
  );

  const roleLabels: Record<string, string> = {
    admin: '管理员', buyer: '买家', promoter: '推广员', supplier: '供应商', member: '会员', viewer: '访客',
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 bg-white border-b border-border-light flex items-center justify-between px-4 h-14">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="text-slate-600 active:scale-95 transition-transform">
            <ArrowLeft className="w-6 h-6" />
          </button>
          <h1 className="font-manrope text-lg font-bold text-on-surface">个人中心</h1>
        </div>
        <button
          onClick={() => navigate('/settings', { state: { transition: 'push' } })}
          className="p-2 rounded-xl text-slate-500 active:scale-90 transition-all"
        >
          <Settings className="w-5 h-5" />
        </button>
      </header>

      <main className="pt-14">
        {/* Profile Card */}
        <section className="bg-white p-6 border-b border-border-light">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center text-white text-3xl font-bold shadow-lg shadow-sky-500/20">
                {profile?.name?.[0] || 'U'}
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 bg-white rounded-full p-1 shadow-sm">
                <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center">
                  <Edit3 className="w-3 h-3 text-white" />
                </div>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-extrabold text-slate-800">{profile?.name || '用户'}</h2>
                <span className="text-[10px] bg-gradient-to-r from-sky-500 to-blue-500 text-white px-2 py-0.5 rounded-full font-bold">
                  {roleLabels[profile?.role || ''] || profile?.role || '会员'}
                </span>
              </div>
              {profile?.company && (
                <p className="text-sm text-slate-500 mt-0.5 flex items-center gap-1">
                  <Building2 className="w-4 h-4 text-slate-400" />
                  {profile.company}{profile.position ? ` · ${profile.position}` : ''}
                </p>
              )}
              <p className="text-xs text-slate-400 mt-1">@{profile?.username || ''}</p>
            </div>
          </div>
        </section>

        {/* Stats Cards */}
        <section className="grid grid-cols-3 gap-3 p-4">
          {[
            { label: '我的订单', icon: FileText, value: '0', path: '/my-orders' },
            { label: '会员等级', icon: Crown, value: '普通', path: '/membership' },
            { label: '我的产品', icon: Star, value: '0', path: '/my-products' },
          ].map((item, i) => {
            const Icon = item.icon;
            return (
              <button
                key={i}
                onClick={() => navigate(item.path, { state: { transition: 'push' } })}
                className="bg-white rounded-2xl p-4 border border-border-light shadow-sm text-center active:scale-95 transition-transform"
              >
                <div className="w-10 h-10 rounded-xl bg-sky-50 flex items-center justify-center mx-auto mb-2">
                  <Icon className="w-5 h-5 text-sky-600" />
                </div>
                <p className="text-lg font-extrabold text-slate-800">{item.value}</p>
                <p className="text-[10px] text-slate-500 mt-0.5">{item.label}</p>
              </button>
            );
          })}
        </section>

        {/* Menu List */}
        <section className="px-4 space-y-2">
          <div className="bg-white rounded-2xl border border-border-light shadow-sm overflow-hidden">
            {[
              { icon: Phone, label: '手机号', value: profile?.phone || '未绑定', path: null },
              { icon: Building2, label: '公司信息', value: profile?.company || '未填写', path: null },
              { icon: Crown, label: '会员中心', value: '', path: '/membership' },
              { icon: FileText, label: '我的订单', value: '', path: '/my-orders' },
              { icon: Wallet, label: '推广收益', value: '', path: '/promotion-center' },
              { icon: Bell, label: '消息通知', value: '', path: '/notifications' },
            ].map((item, i) => {
              const Icon = item.icon;
              return (
                <button
                  key={i}
                  onClick={() => item.path && navigate(item.path, { state: { transition: 'push' } })}
                  className={`w-full flex items-center justify-between px-4 py-3.5 active:bg-slate-50 transition-colors ${
                    i < 6 ? 'border-b border-border-light' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className="w-5 h-5 text-slate-500" />
                    <span className="text-sm text-slate-700">{item.label}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.value && <span className="text-xs text-slate-400">{item.value}</span>}
                    {item.path && <ChevronRight className="w-4 h-4 text-slate-300" />}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* More Section */}
        <section className="px-4 mt-3">
          <div className="bg-white rounded-2xl border border-border-light shadow-sm overflow-hidden">
            {[
              { icon: Shield, label: '账户安全', path: null },
              { icon: HelpCircle, label: '帮助与反馈', path: null },
              { icon: FileText, label: '关于链客宝', path: null },
            ].map((item, i) => {
              const Icon = item.icon;
              return (
                <button
                  key={i}
                  className={`w-full flex items-center justify-between px-4 py-3.5 active:bg-slate-50 transition-colors ${
                    i < 2 ? 'border-b border-border-light' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className="w-5 h-5 text-slate-500" />
                    <span className="text-sm text-slate-700">{item.label}</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-300" />
                </button>
              );
            })}
          </div>
        </section>

        {/* Logout */}
        <div className="px-4 mt-6 pb-6">
          <button
            onClick={handleLogout}
            className="w-full py-3 rounded-xl border-2 border-red-200 text-red-500 font-bold text-sm active:scale-95 transition-transform bg-white hover:bg-red-50"
          >
            <LogOut className="w-4 h-4 inline mr-2" />
            退出登录
          </button>
        </div>
      </main>
    </div>
  );
}
