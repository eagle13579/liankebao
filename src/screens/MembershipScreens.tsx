import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Crown, Shield, Diamond, Star, CheckCircle2,
  TrendingUp, Clock, Headphones, Zap, Package, ShoppingBag,
  ArrowRight, Sparkles, User, CreditCard
} from 'lucide-react';

interface MembershipTier {
  name: string;
  icon: React.ElementType;
  price: string;
  color: string;
  bgColor: string;
  borderColor: string;
  features: string[];
  badge: string;
}

const tiers: MembershipTier[] = [
  {
    name: '普通会员',
    icon: Crown,
    price: '免费',
    color: 'text-slate-600',
    bgColor: 'bg-slate-50',
    borderColor: 'border-slate-200',
    features: ['基础产品推广权限', '标准分润比例 5%', '基础数据查看'],
    badge: '免费',
  },
  {
    name: '黄金会员',
    icon: Shield,
    price: '¥199/年',
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    features: ['推广佣金提升至 8%', '优先审核产品上架', '专属客服支持', '月度推广报告'],
    badge: '热销',
  },
  {
    name: '钻石会员',
    icon: Diamond,
    price: '¥499/年',
    color: 'text-sky-600',
    bgColor: 'bg-sky-50',
    borderColor: 'border-sky-200',
    features: ['推广佣金提升至 12%', '优先审核 + 24h上架', '专属客服经理', '季度营销支持', '线下活动优先参与'],
    badge: '推荐',
  },
  {
    name: '至尊会员',
    icon: Crown,
    price: '¥999/年',
    color: 'text-violet-600',
    bgColor: 'bg-violet-50',
    borderColor: 'border-violet-200',
    features: ['推广佣金提升至 15%', '极速审核 + 即时上架', '1对1专属客户经理', '定制营销方案', '品牌联合推广机会', '年度峰会VIP席位'],
    badge: '尊享',
  },
];

const memberBenefits = [
  { icon: TrendingUp, label: '推广佣金提升', desc: '最高可达15%分润比例' },
  { icon: Clock, label: '优先审核', desc: '产品上架审核提速' },
  { icon: Headphones, label: '专属客服', desc: '7×24小时专属服务' },
  { icon: Zap, label: '极速上架', desc: '钻石及以上即时上架' },
  { icon: Star, label: '营销支持', desc: '季度/年度营销方案' },
  { icon: User, label: '专属经理', desc: '1对1客户经理服务' },
];

export function MembershipCenter() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-12">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex items-center gap-3 px-4 h-16">
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">
          会员中心
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4 space-y-6">
        {/* Current Membership Banner */}
        <div className="relative w-full aspect-[21/7] rounded-2xl overflow-hidden bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 shadow-lg">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent_60%)]" />
          <div className="absolute inset-0 flex flex-col justify-center px-6">
            <div className="flex items-center gap-2 mb-1">
              <Crown className="w-5 h-5 text-amber-300" />
              <span className="text-white/80 text-[10px] font-bold">当前等级</span>
            </div>
            <h2 className="text-white font-bold text-2xl leading-tight">普通会员</h2>
            <p className="text-white/70 text-xs mt-1">升级会员享更高佣金比例与专属权益</p>
          </div>
        </div>

        {/* Upgrade Cards */}
        <section>
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-4 h-4 text-amber-500" />
            <h2 className="font-manrope font-extrabold text-slate-800 text-base">升级会员等级</h2>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {tiers.map((tier, i) => {
              const Icon = tier.icon;
              return (
                <div
                  key={i}
                  className={`bg-white rounded-2xl border ${tier.borderColor} p-4 shadow-sm hover:shadow-md transition-all`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className={`w-10 h-10 rounded-xl ${tier.bgColor} flex items-center justify-center`}>
                      <Icon className={`w-5 h-5 ${tier.color}`} />
                    </div>
                    <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
                      i === 0 ? 'bg-slate-100 text-slate-500' :
                      i === 1 ? 'bg-amber-100 text-amber-700' :
                      i === 2 ? 'bg-sky-100 text-sky-700' :
                      'bg-violet-100 text-violet-700'
                    }`}>
                      {tier.badge}
                    </span>
                  </div>
                  <h3 className="font-bold text-slate-800 text-sm">{tier.name}</h3>
                  <p className="text-lg font-extrabold text-sky-600 mt-1">{tier.price}</p>
                  <ul className="mt-2 space-y-1">
                    {tier.features.slice(0, 2).map((f, fi) => (
                      <li key={fi} className="flex items-center gap-1 text-[10px] text-slate-500">
                        <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  {i > 0 && (
                    <button
                      onClick={() => alert(`即将开通${tier.name}，敬请期待`)}
                      className="w-full mt-3 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 text-white text-xs font-bold active:scale-[0.97] transition-transform shadow-sm"
                    >
                      立即升级
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Membership Benefits */}
        <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Star className="w-4 h-4 text-amber-500" fill="currentColor" />
            <h2 className="font-manrope font-extrabold text-slate-800 text-base">会员权益一览</h2>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {memberBenefits.map((benefit, i) => {
              const Icon = benefit.icon;
              return (
                <div key={i} className="text-center">
                  <div className="w-10 h-10 rounded-xl bg-sky-50 flex items-center justify-center mx-auto mb-2">
                    <Icon className="w-5 h-5 text-sky-600" />
                  </div>
                  <h4 className="text-[11px] font-bold text-slate-700">{benefit.label}</h4>
                  <p className="text-[9px] text-slate-400 mt-0.5">{benefit.desc}</p>
                </div>
              );
            })}
          </div>
        </section>

        {/* My Products Entry */}
        <section
          onClick={() => navigate('/my-products', { state: { transition: 'push' } })}
          className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm cursor-pointer active:scale-[0.98] transition-transform"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 flex items-center justify-center">
                <Package className="w-6 h-6 text-emerald-600" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800 text-sm">我的产品</h3>
                <p className="text-[10px] text-slate-400 mt-0.5">管理您上架的产品，查看推广数据</p>
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-slate-300" />
          </div>
        </section>

        {/* Add Product Entry */}
        <section
          onClick={() => navigate('/add-product', { state: { transition: 'push' } })}
          className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm cursor-pointer active:scale-[0.98] transition-transform"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl bg-amber-50 flex items-center justify-center">
                <ShoppingBag className="w-6 h-6 text-amber-600" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800 text-sm">上架新产品</h3>
                <p className="text-[10px] text-slate-400 mt-0.5">提交您的优质货源，触达海量推广员</p>
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-slate-300" />
          </div>
        </section>

        {/* Recharge Entry */}
        <section
          onClick={() => navigate('/recharge', { state: { transition: 'push' } })}
          className="bg-gradient-to-r from-sky-50 to-blue-50 rounded-2xl border border-sky-100 p-5 shadow-sm cursor-pointer active:scale-[0.98] transition-transform"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl bg-white flex items-center justify-center shadow-sm">
                <CreditCard className="w-6 h-6 text-sky-600" />
              </div>
              <div>
                <h3 className="font-bold text-sky-800 text-sm">账户充值</h3>
                <p className="text-[10px] text-sky-600/70 mt-0.5">充值到账户余额，支持微信/支付宝</p>
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-sky-400" />
          </div>
        </section>

        {/* Commission Comparison Table */}
        <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-amber-500" />
            <h2 className="font-manrope font-extrabold text-slate-800 text-base">佣金比例对比</h2>
          </div>
          <div className="space-y-3">
            {[
              { level: '普通会员', rate: '5%', color: 'bg-slate-100 text-slate-700' },
              { level: '黄金会员', rate: '8%', color: 'bg-amber-100 text-amber-700' },
              { level: '钻石会员', rate: '12%', color: 'bg-sky-100 text-sky-700' },
              { level: '至尊会员', rate: '15%', color: 'bg-violet-100 text-violet-700' },
            ].map((item, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-b-0">
                <span className="text-sm font-medium text-slate-700">{item.level}</span>
                <span className={`text-sm font-extrabold px-3 py-1 rounded-full ${item.color}`}>{item.rate}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
