import { useNavigate } from 'react-router-dom';
import { ArrowLeft, User, Settings, LogOut, ChevronRight, Bell, Shield, HelpCircle, FileText, Star, Crown, Wallet, Building2, Phone, Mail, Edit3, Camera, Upload, Loader2, Sparkles, X, Scan } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
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

interface ScanFields {
  name?: string;
  phone?: string;
  company?: string;
  position?: string;
  email?: string;
  wechat?: string;
  address?: string;
  website?: string;
}

type ScanStep = 'upload' | 'scanning' | 'review' | 'error';

export default function ProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  // AI名片扫描 state
  const [showScanner, setShowScanner] = useState(false);
  const [scanStep, setScanStep] = useState<ScanStep>('upload');
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState('');
  const [scanFields, setScanFields] = useState<ScanFields>({});
  const [rawText, setRawText] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  // ===== AI名片扫描逻辑 =====
  const openScanner = () => {
    setShowScanner(true);
    setScanStep('upload');
    setScanFields({});
    setRawText('');
    setSuggestions([]);
    setScanError('');
  };

  const closeScanner = () => {
    setShowScanner(false);
    setScanStep('upload');
    setScanFields({});
    setRawText('');
    setSuggestions([]);
    setScanError('');
    setScanLoading(false);
  };

  const handleFileSelect = async (file: File) => {
    const allowedTypes = [
      'application/pdf',
      'image/jpeg', 'image/png', 'image/bmp', 'image/webp', 'image/tiff',
    ];
    if (!allowedTypes.includes(file.type)) {
      setScanError('不支持的文件格式。请上传名片图片（JPG/PNG/BMP/WebP）');
      setScanStep('error');
      return;
    }

    setScanStep('scanning');
    setScanLoading(true);
    setScanError('');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await api.request('/api/card/scan', {
        method: 'POST',
        body: formData,
      });

      if (res.code !== 200) {
        setScanError(res.message || '扫描失败，请稍后重试');
        setScanStep('error');
        return;
      }

      const data = res.data as { raw_text: string; fields: ScanFields; suggestions: string[] };
      setRawText(data.raw_text || '');
      const fields = data.fields || {};

      // 只保留个人资料相关字段：姓名/电话/公司/职位
      setScanFields({
        name: fields.name || '',
        phone: fields.phone || '',
        company: fields.company || '',
        position: fields.position || '',
        email: fields.email || '',
        wechat: fields.wechat || '',
        address: fields.address || '',
        website: fields.website || '',
      });
      setSuggestions(data.suggestions || []);
      setScanStep('review');
    } catch (e: any) {
      console.error('Scan error:', e);
      // 后端端点不可用时显示降级文案
      setScanError('即将上线');
      setScanStep('error');
    } finally {
      setScanLoading(false);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
    // Reset input so same file can be selected again
    e.target.value = '';
  };

  const updateField = (key: keyof ScanFields, value: string) => {
    setScanFields((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveToProfile = async () => {
    if (!scanFields.name?.trim()) {
      setScanError('请至少填写姓名');
      return;
    }
    setSaving(true);
    setScanError('');

    try {
      // 尝试保存到个人资料
      const res = await api.put('/api/auth/me', {
        name: scanFields.name,
        phone: scanFields.phone || '',
        company: scanFields.company || '',
        position: scanFields.position || '',
      });

      if (res.code === 200) {
        // 刷新个人资料
        await loadProfile();
        closeScanner();
      } else {
        setScanError('即将上线');
        setScanStep('error');
      }
    } catch {
      // 后端端点暂不可用
      setScanError('即将上线');
      setScanStep('error');
    } finally {
      setSaving(false);
    }
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

          {/* AI名片扫描入口按钮 */}
          <button
            onClick={openScanner}
            className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-sky-500 to-blue-500 text-white text-sm font-bold shadow-lg shadow-sky-500/20 active:scale-95 transition-transform hover:shadow-xl hover:shadow-sky-500/30"
          >
            <Scan className="w-4 h-4" />
            <span>AI 名片扫描</span>
            <Sparkles className="w-3.5 h-3.5 opacity-80" />
          </button>
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

      {/* ===== AI名片扫描 Modal ===== */}
      {showScanner && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={closeScanner} />

          {/* Modal */}
          <div className="relative w-full max-w-md bg-white rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Close button */}
            <button
              onClick={closeScanner}
              className="absolute top-3 right-3 z-10 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="px-6 pt-8 pb-6">
              {/* 步骤: 上传 */}
              {scanStep === 'upload' && (
                <div className="space-y-6">
                  <div className="text-center">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-sky-50 mb-4">
                      <Camera className="w-8 h-8 text-sky-600" />
                    </div>
                    <h2 className="text-xl font-bold text-on-surface">AI 名片扫描</h2>
                    <p className="text-sm text-text-muted mt-1">
                      上传名片图片，AI 自动提取信息并填充到个人资料
                    </p>
                  </div>

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/bmp,image/webp,image/tiff"
                    className="hidden"
                    onChange={handleFileChange}
                  />

                  <button
                    onClick={handleUploadClick}
                    className="w-full flex flex-col items-center gap-3 py-10 px-6 rounded-2xl border-2 border-dashed border-border-light hover:border-sky-400/50 hover:bg-sky-50/50 transition-all duration-200 active:scale-[0.98]"
                  >
                    <Upload className="w-10 h-10 text-text-muted" />
                    <div>
                      <p className="text-sm font-medium text-on-surface">点击选择名片图片</p>
                      <p className="text-xs text-text-muted mt-1">支持 JPG、PNG、BMP、WebP 格式</p>
                    </div>
                  </button>

                  <div className="text-center">
                    <p className="text-xs text-text-muted">
                      <Sparkles className="w-3 h-3 inline mr-1" />
                      AI 自动识别姓名、电话、公司、职位等信息
                    </p>
                  </div>
                </div>
              )}

              {/* 步骤: 扫描中 */}
              {scanStep === 'scanning' && (
                <div className="flex flex-col items-center justify-center py-10 space-y-4">
                  <Loader2 className="w-10 h-10 text-sky-600 animate-spin" />
                  <p className="text-sm text-text-muted">正在识别名片文字...</p>
                  <div className="w-48 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                    <div className="h-full bg-sky-600 rounded-full animate-pulse" style={{ width: '60%' }} />
                  </div>
                </div>
              )}

              {/* 步骤: 审核编辑 */}
              {scanStep === 'review' && (
                <div className="space-y-5">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setScanStep('upload')}
                      className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
                    >
                      <ArrowLeft className="w-5 h-5 text-slate-600" />
                    </button>
                    <div>
                      <h2 className="text-lg font-bold text-on-surface">确认名片信息</h2>
                      <p className="text-xs text-text-muted">请核对 AI 提取的信息，可手动修改</p>
                    </div>
                  </div>

                  {/* Suggestions */}
                  {suggestions.length > 0 && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
                      <div className="flex gap-2">
                        <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                        <div className="text-xs text-amber-800 space-y-1">
                          {suggestions.map((s, i) => (
                            <p key={i}>{s}</p>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Raw text (collapsible) */}
                  {rawText && (
                    <details className="bg-slate-50 rounded-xl p-3">
                      <summary className="text-xs text-text-muted cursor-pointer select-none">
                        OCR 原始识别文字
                      </summary>
                      <p className="text-xs text-text-muted mt-2 whitespace-pre-wrap">{rawText}</p>
                    </details>
                  )}

                  {/* Editable fields */}
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs font-medium text-slate-500 mb-1.5 block">姓名 *</label>
                      <input
                        type="text"
                        value={scanFields.name || ''}
                        onChange={(e) => updateField('name', e.target.value)}
                        placeholder="请输入姓名"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-border-light text-sm text-on-surface placeholder:text-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500 transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-500 mb-1.5 block">手机号</label>
                      <input
                        type="tel"
                        value={scanFields.phone || ''}
                        onChange={(e) => updateField('phone', e.target.value)}
                        placeholder="请输入手机号"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-border-light text-sm text-on-surface placeholder:text-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500 transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-500 mb-1.5 block">公司</label>
                      <input
                        type="text"
                        value={scanFields.company || ''}
                        onChange={(e) => updateField('company', e.target.value)}
                        placeholder="请输入公司名称"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-border-light text-sm text-on-surface placeholder:text-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500 transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-500 mb-1.5 block">职位</label>
                      <input
                        type="text"
                        value={scanFields.position || ''}
                        onChange={(e) => updateField('position', e.target.value)}
                        placeholder="请输入职位"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-border-light text-sm text-on-surface placeholder:text-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500 transition-all"
                      />
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-3 pt-2">
                    <button
                      onClick={closeScanner}
                      className="flex-1 py-2.5 px-4 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors"
                    >
                      取消
                    </button>
                    <button
                      onClick={handleSaveToProfile}
                      disabled={saving || !scanFields.name?.trim()}
                      className="flex-1 py-2.5 px-4 rounded-xl bg-gradient-to-r from-sky-500 to-blue-500 text-white font-medium text-sm hover:shadow-lg hover:shadow-sky-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {saving ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          保存中...
                        </>
                      ) : (
                        '保存到个人资料'
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* 步骤: 错误/降级文案 */}
              {scanStep === 'error' && (
                <div className="flex flex-col items-center justify-center py-10 space-y-4">
                  <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center">
                    <Scan className="w-8 h-8 text-slate-400" />
                  </div>
                  <div className="text-center">
                    <h3 className="text-lg font-bold text-on-surface">
                      {scanError === '即将上线' ? '即将上线' : '扫描失败'}
                    </h3>
                    <p className="text-sm text-text-muted mt-1">
                      {scanError === '即将上线'
                        ? 'AI名片扫描功能正在紧张开发中，请期待后续版本'
                        : scanError}
                    </p>
                  </div>
                  <button
                    onClick={closeScanner}
                    className="mt-2 px-6 py-2.5 rounded-xl bg-sky-600 text-white text-sm font-medium hover:bg-sky-500 transition-colors"
                  >
                    知道了
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
