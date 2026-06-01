import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield, Crown, Users, Briefcase, GraduationCap, Handshake,
  ChevronRight, Star, CheckCircle, Clock, AlertCircle, X,
  Award, Sparkles, Quote,
} from 'lucide-react';

// ============================================================
// 类型定义
// ============================================================

interface BoardFeature {
  icon: string;
  title: string;
  description: string;
}

interface Mentor {
  name: string;
  title: string;
  expertise: string;
  avatar: string | null;
}

interface BoardProductInfo {
  name: string;
  subtitle: string;
  price: number;
  quota: number;
  duration_days: number;
  access_requirements: string;
  exclusivity_policy: string;
  features: BoardFeature[];
  mentors: Mentor[];
  annual_schedule: { quarter: string; theme: string; date: string }[];
}

interface BoardStatusData {
  is_board_member: boolean;
  is_expired: boolean;
  membership_expires_at: string | null;
  application: {
    order_id: number;
    status: string;
    company: string;
    created_at: string;
  } | null;
  active_member_count: number;
  total_quota: number;
  remaining_seats: number;
}

// ============================================================
// 图标映射
// ============================================================

function FeatureIcon({ icon }: { icon: string }) {
  switch (icon) {
    case 'users': return <Users className="w-10 h-10 text-amber-400" />;
    case 'briefcase': return <Briefcase className="w-10 h-10 text-amber-400" />;
    case 'graduation-cap': return <GraduationCap className="w-10 h-10 text-amber-400" />;
    case 'handshake': return <Handshake className="w-10 h-10 text-amber-400" />;
    default: return <Star className="w-10 h-10 text-amber-400" />;
  }
}

// ============================================================
// 主页面组件
// ============================================================

export default function PrivateBoardPage() {
  const navigate = useNavigate();
  const [productInfo, setProductInfo] = useState<BoardProductInfo | null>(null);
  const [statusData, setStatusData] = useState<BoardStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // 申请表单状态
  const [showApplyForm, setShowApplyForm] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyMsg, setApplyMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [formData, setFormData] = useState({
    company: '',
    revenue: '',
    industry: '',
    referrer: '',
    referrer_notes: '',
  });

  // 升级支付状态
  const [upgrading, setUpgrading] = useState(false);
  const [upgradeMsg, setUpgradeMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    setLoading(true);
    setError('');
    try {
      const token = localStorage.getItem('token');
      // 并行加载产品信息 + 用户状态
      const [infoRes, statusRes] = await Promise.all([
        fetch('/api/v1/board/info', { headers: { Authorization: `Bearer ${token}` } }),
        fetch('/api/v1/board/status', { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const infoJson = await infoRes.json();
      const statusJson = await statusRes.json();

      if (infoJson.code === 200) setProductInfo(infoJson.data);
      else setError(infoJson.message || '加载产品信息失败');

      if (statusJson.code === 200) setStatusData(statusJson.data);
    } catch {
      setError('网络错误，请稍后重试');
    } finally {
      setLoading(false);
    }
  }

  function handleFormChange(field: string, value: string) {
    setFormData(prev => ({ ...prev, [field]: value }));
  }

  async function handleApply() {
    if (!formData.company.trim()) {
      setApplyMsg({ type: 'error', text: '请填写企业全称' });
      return;
    }
    setApplying(true);
    setApplyMsg(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/board/apply', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });
      const json = await res.json();
      if (json.code === 200) {
        setApplyMsg({ type: 'success', text: '申请提交成功！请等待审核结果。' });
        setShowApplyForm(false);
        // 刷新状态
        fetchData();
      } else {
        setApplyMsg({ type: 'error', text: json.message || '提交失败' });
      }
    } catch {
      setApplyMsg({ type: 'error', text: '网络错误，请稍后重试' });
    } finally {
      setApplying(false);
    }
  }

  async function handleUpgrade(orderId: number) {
    setUpgrading(true);
    setUpgradeMsg(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/board/upgrade', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ order_id: orderId, payment_platform: 'wxpay' }),
      });
      const json = await res.json();
      if (json.code === 200) {
        setUpgradeMsg({ type: 'success', text: '私董会升级成功！欢迎加入。' });
        fetchData();
      } else {
        setUpgradeMsg({ type: 'error', text: json.message || '升级失败' });
      }
    } catch {
      setUpgradeMsg({ type: 'error', text: '网络错误，请稍后重试' });
    } finally {
      setUpgrading(false);
    }
  }

  // ============================================================
  // 渲染
  // ============================================================

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <div className="animate-spin w-10 h-10 border-2 border-amber-400 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <div className="text-center p-8">
          <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <p className="text-gray-300 text-lg">{error}</p>
          <button
            onClick={fetchData}
            className="mt-6 px-6 py-2 bg-amber-500/20 border border-amber-500/40 text-amber-400 rounded-lg hover:bg-amber-500/30 transition"
          >
            重新加载
          </button>
        </div>
      </div>
    );
  }

  if (!productInfo) return null;

  const isBoardMember = statusData?.is_board_member ?? false;
  const hasPendingApp = statusData?.application?.status === 'pending';
  const hasApprovedApp = statusData?.application?.status === 'approved';

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-gray-100">
      {/* ========== 顶部渐变背景 + 导航 ========== */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-amber-900/20 via-transparent to-transparent" />
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl" />
        <div className="absolute top-0 right-1/4 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl" />

        {/* 返回按钮 */}
        <div className="relative z-10 px-4 pt-4">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-gray-400 hover:text-amber-400 transition text-sm"
          >
            <ChevronRight className="w-4 h-4 rotate-180" />
            返回
          </button>
        </div>

        {/* Hero 区域 */}
        <div className="relative z-10 px-4 pb-16 pt-8 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-amber-500/10 border border-amber-500/30 rounded-full text-amber-400 text-xs mb-6">
            <Crown className="w-3.5 h-3.5" />
            仅限50席 · 企业家专属
          </div>

          <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
            <span className="text-white">私董会</span>
            <span className="text-amber-400"> Private Board</span>
          </h1>
          <p className="text-gray-400 mt-4 text-lg max-w-xl mx-auto">
            链客宝最高端企业家社群 — 限量{productInfo.quota}席，对话行业领袖，决胜商业未来
          </p>

          {/* 价格展示 */}
          <div className="mt-8 inline-flex items-baseline gap-1">
            <span className="text-3xl font-bold text-amber-400">¥</span>
            <span className="text-5xl font-bold text-white">19,999</span>
            <span className="text-gray-400 text-lg ml-2">/年</span>
          </div>

          {/* 状态 & 操作按钮 */}
          <div className="mt-8 flex flex-col items-center gap-3">
            {isBoardMember ? (
              <div className="flex items-center gap-3 px-6 py-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl">
                <CheckCircle className="w-6 h-6 text-emerald-400" />
                <span className="text-emerald-400 font-semibold">您已是私董会成员</span>
              </div>
            ) : hasPendingApp ? (
              <div className="flex items-center gap-3 px-6 py-3 bg-amber-500/10 border border-amber-500/30 rounded-xl">
                <Clock className="w-6 h-6 text-amber-400" />
                <span className="text-amber-400 font-semibold">申请已提交，等待审核中</span>
              </div>
            ) : hasApprovedApp ? (
              <div className="flex flex-col items-center gap-3">
                <div className="flex items-center gap-3 px-6 py-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl">
                  <CheckCircle className="w-6 h-6 text-emerald-400" />
                  <span className="text-emerald-400 font-semibold">审核已通过，立即升级</span>
                </div>
                <button
                  onClick={() => statusData?.application?.order_id && handleUpgrade(statusData.application.order_id)}
                  disabled={upgrading}
                  className="px-10 py-3 bg-gradient-to-r from-amber-500 to-amber-600 text-black font-bold rounded-xl hover:from-amber-400 hover:to-amber-500 transition disabled:opacity-50 shadow-lg shadow-amber-500/25"
                >
                  {upgrading ? '处理中...' : '¥19,999 立即升级'}
                </button>
                {upgradeMsg && (
                  <p className={`text-sm ${upgradeMsg.type === 'success' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {upgradeMsg.text}
                  </p>
                )}
              </div>
            ) : (
              <button
                onClick={() => setShowApplyForm(true)}
                className="px-10 py-3 bg-gradient-to-r from-amber-500 to-amber-600 text-black font-bold rounded-xl hover:from-amber-400 hover:to-amber-500 transition shadow-lg shadow-amber-500/25"
              >
                立即申请
              </button>
            )}

            {/* 剩余席位 */}
            {statusData && (
              <p className="text-sm text-gray-500">
                已入驻 <span className="text-amber-400 font-bold">{statusData.active_member_count}</span> 位 |
                剩余 <span className="text-amber-400 font-bold">{statusData.remaining_seats}</span> 席
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ========== 申请弹窗 ========== */}
      {showApplyForm && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-gray-800 rounded-2xl max-w-md w-full p-6 relative">
            <button
              onClick={() => { setShowApplyForm(false); setApplyMsg(null); }}
              className="absolute top-4 right-4 text-gray-500 hover:text-white transition"
            >
              <X className="w-5 h-5" />
            </button>

            <h2 className="text-xl font-bold text-white mb-6">私董会申请</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">企业全称 *</label>
                <input
                  type="text"
                  value={formData.company}
                  onChange={e => handleFormChange('company', e.target.value)}
                  className="w-full px-4 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-amber-500/50 focus:outline-none"
                  placeholder="请输入企业全称"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">年营收</label>
                <input
                  type="text"
                  value={formData.revenue}
                  onChange={e => handleFormChange('revenue', e.target.value)}
                  className="w-full px-4 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-amber-500/50 focus:outline-none"
                  placeholder="如：5000万-1亿"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">所属行业</label>
                <input
                  type="text"
                  value={formData.industry}
                  onChange={e => handleFormChange('industry', e.target.value)}
                  className="w-full px-4 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-amber-500/50 focus:outline-none"
                  placeholder="如：科技、制造、消费"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">推荐人</label>
                <input
                  type="text"
                  value={formData.referrer}
                  onChange={e => handleFormChange('referrer', e.target.value)}
                  className="w-full px-4 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-amber-500/50 focus:outline-none"
                  placeholder="推荐人姓名或ID"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">推荐备注</label>
                <textarea
                  value={formData.referrer_notes}
                  onChange={e => handleFormChange('referrer_notes', e.target.value)}
                  rows={3}
                  className="w-full px-4 py-2.5 bg-gray-800/50 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-amber-500/50 focus:outline-none resize-none"
                  placeholder="推荐关系说明（可选）"
                />
              </div>
            </div>

            {applyMsg && (
              <p className={`mt-4 text-sm ${applyMsg.type === 'success' ? 'text-emerald-400' : 'text-red-400'}`}>
                {applyMsg.text}
              </p>
            )}

            <button
              onClick={handleApply}
              disabled={applying}
              className="w-full mt-6 py-3 bg-gradient-to-r from-amber-500 to-amber-600 text-black font-bold rounded-xl hover:from-amber-400 hover:to-amber-500 transition disabled:opacity-50"
            >
              {applying ? '提交中...' : '提交申请'}
            </button>
          </div>
        </div>
      )}

      {/* ========== 权益清单 ========== */}
      <section className="px-4 py-16 max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-2xl font-bold text-white">会员权益</h2>
          <p className="text-gray-400 mt-2">尊享四大核心权益，赋能企业增长</p>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {productInfo.features.map((feature, i) => (
            <div
              key={i}
              className="group p-6 bg-gradient-to-br from-gray-800/40 to-gray-900/40 border border-gray-700/50 rounded-xl hover:border-amber-500/30 hover:from-gray-800/60 transition-all"
            >
              <div className="flex items-start gap-4">
                <div className="p-3 bg-amber-500/10 rounded-lg shrink-0">
                  <FeatureIcon icon={feature.icon} />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white mb-2">{feature.title}</h3>
                  <p className="text-gray-400 leading-relaxed">{feature.description}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ========== 排他性说明 ========== */}
      <section className="px-4 py-12 max-w-5xl mx-auto">
        <div className="p-6 bg-gradient-to-r from-amber-500/5 to-transparent border border-amber-500/20 rounded-xl">
          <div className="flex items-start gap-4">
            <Shield className="w-8 h-8 text-amber-400 shrink-0 mt-1" />
            <div>
              <h3 className="text-lg font-bold text-white mb-1">严格排他性保障</h3>
              <p className="text-gray-400">{productInfo.exclusivity_policy}</p>
              <p className="text-gray-500 text-sm mt-2">
                准入条件：{productInfo.access_requirements}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ========== 年度安排 ========== */}
      <section className="px-4 py-16 max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-2xl font-bold text-white">年度议程</h2>
          <p className="text-gray-400 mt-2">四季度深度主题，贯穿全年商业智慧</p>
        </div>

        <div className="grid md:grid-cols-4 gap-4">
          {productInfo.annual_schedule.map((item, i) => (
            <div
              key={i}
              className="p-5 bg-gray-800/30 border border-gray-700/50 rounded-xl text-center hover:border-amber-500/30 transition"
            >
              <div className="inline-flex items-center justify-center w-10 h-10 bg-amber-500/10 rounded-full mb-3">
                <span className="text-amber-400 font-bold text-sm">{item.quarter}</span>
              </div>
              <p className="text-sm text-gray-300 font-medium leading-relaxed">{item.theme}</p>
              <p className="text-xs text-gray-500 mt-2">{item.date}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ========== 导师介绍 ========== */}
      <section className="px-4 py-16 max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 mb-2">
            <GraduationCap className="w-5 h-5 text-amber-400" />
            <h2 className="text-2xl font-bold text-white">专家导师</h2>
          </div>
          <p className="text-gray-400">各领域顶尖专家，为您企业战略保驾护航</p>
        </div>

        <div className="grid md:grid-cols-4 gap-6">
          {productInfo.mentors.map((mentor, i) => (
            <div
              key={i}
              className="text-center p-6 bg-gradient-to-b from-gray-800/30 to-gray-900/30 border border-gray-700/50 rounded-xl hover:border-amber-500/20 transition group"
            >
              {/* 头像占位 - 圆形渐变 */}
              <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-amber-400 to-amber-600 p-0.5">
                <div className="w-full h-full rounded-full bg-gray-800 flex items-center justify-center">
                  <span className="text-2xl font-bold text-amber-400">
                    {mentor.name.charAt(0)}
                  </span>
                </div>
              </div>
              <h3 className="font-bold text-white mb-1">{mentor.name}</h3>
              <p className="text-amber-400 text-sm mb-2">{mentor.title}</p>
              <p className="text-gray-500 text-xs">{mentor.expertise}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ========== 底部 CTA ========== */}
      <section className="px-4 py-20 text-center relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-t from-amber-900/10 to-transparent" />
        <div className="relative z-10 max-w-xl mx-auto">
          <Award className="w-12 h-12 text-amber-400 mx-auto mb-4" />
          <h2 className="text-3xl font-bold text-white mb-4">
            与{productInfo.quota}位顶尖企业家同行
          </h2>
          <p className="text-gray-400 mb-8">
            链客宝私董会，不只是社群，更是您企业的战略智囊团
          </p>
          {!isBoardMember && !hasPendingApp && !hasApprovedApp && (
            <button
              onClick={() => setShowApplyForm(true)}
              className="px-10 py-3 bg-gradient-to-r from-amber-500 to-amber-600 text-black font-bold rounded-xl hover:from-amber-400 hover:to-amber-500 transition shadow-lg shadow-amber-500/25"
            >
              立即申请加入
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
