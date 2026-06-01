import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ChevronLeft, Crown, Shield, Diamond, CheckCircle2,
  TrendingUp, Clock, Headphones, Zap, Star,
  ArrowRight, Sparkles, User, CreditCard, X,
  Ticket, Calendar, Gift, Loader2, AlertCircle,
  Wallet, Check, Ban, Hash, Info
} from 'lucide-react';
import { membershipApi, type MembershipTier, type MembershipStatus } from '../api/membership';
import { paymentApi } from '../api/payment';

// ───────── Types ─────────

type PayStatus = 'idle' | 'preparing' | 'waiting' | 'success' | 'failed' | 'error';

// ───────── Helpers ─────────

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
const formatDate = (s: string | null) => {
  if (!s) return '永久';
  try { return new Date(s).toLocaleDateString('zh-CN'); }
  catch { return s; }
};
const fmtPrice = (n: number) => '¥' + n.toLocaleString('zh-CN');

const levelConfig = {
  free: {
    name: '免费会员',
    icon: Crown,
    color: 'text-slate-600',
    bgColor: 'bg-slate-50',
    borderColor: 'border-slate-200',
    gradient: 'from-slate-500 to-slate-600',
    badgeColor: 'bg-slate-100 text-slate-600',
  },
  gold: {
    name: '金卡会员',
    icon: Shield,
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    gradient: 'from-amber-500 to-orange-600',
    badgeColor: 'bg-amber-100 text-amber-700',
  },
  diamond: {
    name: '钻石会员',
    icon: Diamond,
    color: 'text-sky-600',
    bgColor: 'bg-sky-50',
    borderColor: 'border-sky-200',
    gradient: 'from-sky-500 to-blue-600',
    badgeColor: 'bg-sky-100 text-sky-700',
  },
  board: {
    name: '私董会',
    icon: Star,
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
    gradient: 'from-purple-600 to-indigo-700',
    badgeColor: 'bg-purple-100 text-purple-700',
  },
};

// ───────── Component: MembershipStatusBanner ─────────
// 可复用的会员状态组件 — 显示当前层级、剩余对接券、有效期

export function MembershipStatusBanner({ status, onUpgrade }: {
  status: MembershipStatus | null;
  onUpgrade?: () => void;
}) {
  if (!status) return null;
  const cfg = levelConfig[status.level];
  const Icon = cfg.icon;
  const isFree = status.level === 'free';

  return (
    <div className="relative w-full rounded-2xl overflow-hidden bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 shadow-lg">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent_60%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,rgba(255,255,255,0.08),transparent_50%)]" />
      <div className="relative p-5">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-xl bg-white/20 backdrop-blur flex items-center justify-center">
              <Icon className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="text-white/60 text-[10px] font-bold">当前等级</p>
              <h2 className="text-white font-extrabold text-lg">{status.level_name}</h2>
            </div>
          </div>
          {isFree && onUpgrade && (
            <button
              onClick={onUpgrade}
              className="px-4 py-1.5 bg-white/20 backdrop-blur hover:bg-white/30 rounded-full text-white text-[11px] font-bold transition-all active:scale-95"
            >
              升级
            </button>
          )}
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white/10 backdrop-blur rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Ticket className="w-3 h-3 text-amber-300" />
              <span className="text-white/60 text-[9px] font-bold">剩余对接券</span>
            </div>
            <p className="text-white font-extrabold text-lg">
              {status.remaining_coupons}
              <span className="text-xs text-white/60 font-normal"> / {status.total_coupons_this_month}</span>
            </p>
          </div>
          <div className="bg-white/10 backdrop-blur rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Calendar className="w-3 h-3 text-emerald-300" />
              <span className="text-white/60 text-[9px] font-bold">有效期至</span>
            </div>
            <p className="text-white font-extrabold text-sm leading-tight pt-1">
              {formatDate(status.expired_at)}
            </p>
          </div>
          <div className="bg-white/10 backdrop-blur rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Hash className="w-3 h-3 text-sky-300" />
              <span className="text-white/60 text-[9px] font-bold">本月已用</span>
            </div>
            <p className="text-white font-extrabold text-lg">
              {status.coupon_used_count}
              <span className="text-xs text-white/60 font-normal"> 次</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ───────── Component: TrialGoldModal ─────────
// 首月体验金卡¥99的转化弹窗（免费用户用完3次对接券后弹出）

export function TrialGoldModal({ open, onClose, onConfirm }: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-3xl shadow-2xl max-w-sm w-full p-6 animate-in fade-in zoom-in-95 duration-200">
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 hover:bg-slate-200 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Badge */}
        <div className="flex justify-center mb-4">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-200/50">
            <Gift className="w-8 h-8 text-white" />
          </div>
        </div>

        <h2 className="text-center font-manrope font-extrabold text-xl text-slate-800 mb-1">
          首月体验金卡
        </h2>
        <p className="text-center text-slate-400 text-xs mb-5">
          免费用户的对接券已用完，升级体验金卡畅享更多权益
        </p>

        {/* Price */}
        <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-2xl p-4 mb-5 border border-amber-100">
          <div className="text-center">
            <span className="text-slate-400 text-xs line-through">¥999/年</span>
            <div className="flex items-baseline justify-center gap-1 mt-1">
              <span className="text-3xl font-extrabold text-amber-600">¥99</span>
              <span className="text-slate-400 text-xs font-medium">/首月</span>
            </div>
            <p className="text-[10px] text-amber-600/70 mt-1 font-medium">限时体验价，后恢复原价</p>
          </div>
        </div>

        {/* Benefits */}
        <div className="space-y-2.5 mb-6">
          {[
            '每月 30 张对接券（免费仅3张）',
            '推广佣金提升至 8%',
            '优先审核产品上架',
            '专属客服支持',
          ].map((feat, i) => (
            <div key={i} className="flex items-center gap-2.5">
              <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center shrink-0">
                <Check className="w-3 h-3 text-emerald-600" />
              </div>
              <span className="text-xs text-slate-600">{feat}</span>
            </div>
          ))}
        </div>

        {/* CTA */}
        <button
          onClick={onConfirm}
          className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-amber-500 to-orange-600 text-white text-sm font-extrabold active:scale-[0.97] transition-transform shadow-lg shadow-amber-200/50"
        >
          立即体验 ¥99
        </button>
        <p className="text-center text-[9px] text-slate-400 mt-2">可随时取消，自动续费前提醒</p>
      </div>
    </div>
  );
}

// ───────── Component: TierCard ─────────

function TierCard({ tier, isCurrent, onSelect }: {
  tier: MembershipTier;
  isCurrent: boolean;
  onSelect: (tier: MembershipTier) => void;
}) {
  const cfg = levelConfig[tier.level];
  const Icon = cfg.icon;
  const isFree = tier.level === 'free';

  return (
    <div
      className={`relative bg-white rounded-2xl border-2 p-5 shadow-sm transition-all ${
        isCurrent
          ? 'border-sky-400 shadow-lg shadow-sky-100/50'
          : cfg.borderColor + ' hover:shadow-md'
      }`}
    >
      {/* Badge */}
      {tier.badge && (
        <span className={`absolute -top-2.5 right-4 text-[9px] font-bold px-2.5 py-0.5 rounded-full ${cfg.badgeColor}`}>
          {tier.badge}
        </span>
      )}

      {/* Icon + Name */}
      <div className="flex items-center gap-3 mb-3">
        <div className={`w-12 h-12 rounded-xl ${cfg.bgColor} flex items-center justify-center`}>
          <Icon className={`w-6 h-6 ${cfg.color}`} />
        </div>
        <div>
          <h3 className={`font-extrabold text-base ${cfg.color}`}>{tier.name}</h3>
          <p className="text-slate-400 text-[10px]">
            分润 {Math.round(tier.commission_rate * 100)}%
          </p>
        </div>
      </div>

      {/* Price */}
      <div className="mb-3">
        {tier.price === 0 ? (
          <span className="text-2xl font-extrabold text-slate-700">免费</span>
        ) : (
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-extrabold text-slate-800">{fmtPrice(tier.price)}</span>
            <span className="text-slate-400 text-xs">/年</span>
          </div>
        )}
      </div>

      {/* Coupons & Features */}
      <div className="space-y-2 mb-4">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Ticket className="w-3.5 h-3.5 text-sky-500" />
          <span>每月 {tier.对接券_per_month} 张对接券</span>
        </div>
        {tier.features.map((f, i) => (
          <div key={i} className="flex items-start gap-2 text-xs text-slate-600">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
            <span>{f}</span>
          </div>
        ))}
      </div>

      {/* CTA */}
      {isCurrent ? (
        <div className="w-full py-2.5 rounded-xl bg-sky-50 text-sky-600 text-xs font-bold text-center">
          当前会员
        </div>
      ) : !isFree && (
        <button
          onClick={() => onSelect(tier)}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 text-white text-xs font-bold active:scale-[0.97] transition-transform shadow-sm"
        >
          立即升级
        </button>
      )}
    </div>
  );
}

// ───────── Component: MembershipCenter ─────────
// 会员中心首页 /membership

export function MembershipCenter() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<MembershipStatus | null>(null);
  const [tiers, setTiers] = useState<MembershipTier[]>([]);
  const [loading, setLoading] = useState(true);
  const [showTrial, setShowTrial] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      membershipApi.getStatus(),
      membershipApi.getTiers(),
    ]).then(([sRes, tRes]) => {
      if (sRes.code === 0 && sRes.data) setStatus(sRes.data);
      if (tRes.code === 0 && tRes.data) {
        const sorted = [...tRes.data].sort((a, b) => a.sort_order - b.sort_order);
        setTiers(sorted);
      }
      setLoading(false);
    }).catch(() => {
      setError('加载失败，请检查网络');
      setLoading(false);
    });
  }, []);

  // 检查体验弹窗
  useEffect(() => {
    if (status && status.level === 'free' && status.remaining_coupons <= 0 && status.coupon_used_count >= 3) {
      membershipApi.checkTrialEligibility().then(res => {
        if (res.code === 0 && res.data?.eligible) setShowTrial(true);
      }).catch(() => {});
    }
  }, [status]);

  const handleUpgrade = (tier: MembershipTier) => {
    navigate('/membership/upgrade', { state: { tier, tiers, status }, replace: true });
  };

  const handleTrial = () => {
    setShowTrial(false);
    navigate('/membership/upgrade', {
      state: { tier: tiers.find(t => t.level === 'gold'), tiers, status, isTrial: true },
      replace: true,
    });
  };

  if (loading) {
    return (
      <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
        <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-slate-100 flex items-center gap-3 px-4 h-16">
          <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all">
            <ChevronLeft className="w-5 h-5" />
          </button>
          <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">会员中心</h1>
        </header>
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-sky-500 animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-24">
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

      <main className="max-w-3xl mx-auto w-full p-4 space-y-5">
        {/* Membership Status Banner */}
        <MembershipStatusBanner
          status={status}
          onUpgrade={() => {
            const paid = tiers.filter(t => t.level !== 'free');
            if (paid.length > 0) handleUpgrade(paid[0]);
          }}
        />

        {/* Error */}
        {error && (
          <div className="bg-rose-50 rounded-2xl p-4 border border-rose-100 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
            <span className="text-xs text-rose-700">{error}</span>
          </div>
        )}

        {/* Level-specific content: 付费用户专属区域 */}
        {status && status.level !== 'free' && (
          <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
            {/* Gold: show gold benefits + upgrade to diamond */}
            {status.level === 'gold' && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Shield className="w-5 h-5 text-amber-500" />
                  <h2 className="font-manrope font-extrabold text-slate-800 text-base">金卡专属权益</h2>
                </div>
                <div className="space-y-2 mb-4">
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>每月 {status.total_coupons_this_month} 张对接券 · 剩余 {status.remaining_coupons} 张</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>推广佣金提升至 8%</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>优先审核产品上架</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>专属客服支持</span>
                  </div>
                </div>
                <button
                  onClick={() => {
                    const diamondTier = tiers.find(t => t.level === 'diamond');
                    if (diamondTier) handleUpgrade(diamondTier);
                  }}
                  className="w-full py-2.5 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 text-white text-xs font-bold active:scale-[0.97] transition-transform shadow-sm"
                >
                  升级钻石会员
                </button>
              </div>
            )}

            {/* Diamond: show diamond benefits + upgrade to board */}
            {status.level === 'diamond' && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Diamond className="w-5 h-5 text-sky-600" />
                  <h2 className="font-manrope font-extrabold text-slate-800 text-base">钻石会员专属权益</h2>
                </div>
                <div className="space-y-2 mb-4">
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>每月 {status.total_coupons_this_month} 张对接券 · 剩余 {status.remaining_coupons} 张</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>推广佣金提升至 10%</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>优先匹配高价值商机</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>专属客户成功经理</span>
                  </div>
                </div>
                <button
                  onClick={() => {
                    const boardTier = tiers.find(t => t.level === 'board');
                    if (boardTier) handleUpgrade(boardTier);
                  }}
                  className="w-full py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-700 text-white text-xs font-bold active:scale-[0.97] transition-transform shadow-sm"
                >
                  升级私董会
                </button>
              </div>
            )}

            {/* Board: show board exclusive page */}
            {status.level === 'board' && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Star className="w-5 h-5 text-purple-600" fill="currentColor" />
                  <h2 className="font-manrope font-extrabold text-slate-800 text-base">私董会专属空间</h2>
                </div>
                <div className="bg-gradient-to-br from-purple-50 to-indigo-50 rounded-xl p-4 border border-purple-100 mb-4">
                  <p className="text-xs text-purple-700 font-medium mb-2">
                    欢迎进入私董会！享受最高级别的专属权益与服务。
                  </p>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-xs text-slate-600">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>无限张对接券 · 不限量使用</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-600">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>最高推广佣金 15%</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-600">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>私董会专属资源对接</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-600">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>一对一专属顾问服务</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-600">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>优先参与高端闭门会议</span>
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => navigate('/private-board')}
                  className="w-full py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-700 text-white text-xs font-bold active:scale-[0.97] transition-transform shadow-sm"
                >
                  进入私董会
                </button>
              </div>
            )}
          </section>
        )}

        {/* Tier Comparison */}
        <section>
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-4 h-4 text-amber-500" />
            <h2 className="font-manrope font-extrabold text-slate-800 text-base">会员层级对比</h2>
          </div>

          {/* Mobile: scrollable cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {tiers.map((tier) => (
              <TierCard
                key={tier.id}
                tier={tier}
                isCurrent={status?.level === tier.level}
                onSelect={handleUpgrade}
              />
            ))}
          </div>
        </section>

        {/* Benefits Overview */}
        <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Star className="w-4 h-4 text-amber-500" fill="currentColor" />
            <h2 className="font-manrope font-extrabold text-slate-800 text-base">全会员权益一览</h2>
          </div>
          <div className="overflow-x-auto no-scrollbar">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="text-left py-2.5 px-3 text-slate-400 font-bold">权益</th>
                  {tiers.map(t => {
                    const cfg = levelConfig[t.level];
                    return (
                      <th key={t.id} className={`text-center py-2.5 px-3 font-extrabold ${cfg.color}`}>
                        {t.name}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-slate-50">
                  <td className="py-2.5 px-3 text-slate-600">年费</td>
                  {tiers.map(t => (
                    <td key={t.id} className="text-center py-2.5 px-3 font-bold text-slate-800">
                      {t.price === 0 ? '免费' : fmtPrice(t.price)}
                    </td>
                  ))}
                </tr>
                <tr className="border-b border-slate-50">
                  <td className="py-2.5 px-3 text-slate-600">每月对接券</td>
                  {tiers.map(t => (
                    <td key={t.id} className="text-center py-2.5 px-3 font-bold text-slate-800">
                      {t.对接券_per_month} 张
                    </td>
                  ))}
                </tr>
                <tr className="border-b border-slate-50">
                  <td className="py-2.5 px-3 text-slate-600">分润比例</td>
                  {tiers.map(t => (
                    <td key={t.id} className="text-center py-2.5 px-3 font-extrabold text-emerald-600">
                      {Math.round(t.commission_rate * 100)}%
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-2.5 px-3 text-slate-600">特色权益</td>
                  {tiers.map(t => (
                    <td key={t.id} className="text-center py-2.5 px-3">
                      <div className="space-y-1">
                        {t.features.slice(0, 3).map((f, fi) => (
                          <div key={fi} className="flex items-center gap-1 text-[9px] text-slate-500 justify-center">
                            <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400 shrink-0" />
                            <span className="truncate">{f}</span>
                          </div>
                        ))}
                      </div>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* Quick links */}
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => navigate('/recharge', { state: { transition: 'push' } })}
            className="bg-white rounded-2xl border border-slate-100 p-4 shadow-sm hover:shadow-md transition-all active:scale-[0.98] text-left"
          >
            <div className="w-10 h-10 rounded-xl bg-sky-50 flex items-center justify-center mb-2">
              <Wallet className="w-5 h-5 text-sky-600" />
            </div>
            <h3 className="font-bold text-slate-800 text-sm">账户充值</h3>
            <p className="text-[10px] text-slate-400 mt-0.5">充值余额，支持微信/支付宝</p>
          </button>
          <button
            onClick={() => navigate('/recharge/history', { state: { transition: 'push' } })}
            className="bg-white rounded-2xl border border-slate-100 p-4 shadow-sm hover:shadow-md transition-all active:scale-[0.98] text-left"
          >
            <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center mb-2">
              <TrendingUp className="w-5 h-5 text-amber-600" />
            </div>
            <h3 className="font-bold text-slate-800 text-sm">充值记录</h3>
            <p className="text-[10px] text-slate-400 mt-0.5">查看历史充值及消费明细</p>
          </button>
        </div>
      </main>

      {/* Trial Modal */}
      <TrialGoldModal
        open={showTrial}
        onClose={() => setShowTrial(false)}
        onConfirm={handleTrial}
      />
    </div>
  );
}

// ───────── Component: MembershipUpgradePage ─────────
// 会员升级页 /membership/upgrade — 选择层级→跳转支付宝支付

type WindowWithAlipay = Window & {
  AlipayJSBridge?: {
    call: (name: string, params: any, callback: (res: any) => void) => void;
  };
};

export function MembershipUpgradePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Get state from navigation or URL params
  const locationState = (typeof window !== 'undefined' ? (window.history.state as any)?.usr : null) || {};

  const [tiers, setTiers] = useState<MembershipTier[]>(locationState.tiers || []);
  const [selectedTier, setSelectedTier] = useState<MembershipTier | null>(locationState.tier || null);
  const [status, setStatus] = useState<MembershipStatus | null>(locationState.status || null);
  const [isTrial] = useState(locationState.isTrial || searchParams.get('trial') === '1');

  const [payStatus, setPayStatus] = useState<PayStatus>('idle');
  const [payMessage, setPayMessage] = useState('');
  const [orderNo, setOrderNo] = useState('');
  const [platform, setPlatform] = useState<'alipay' | 'wxpay'>('alipay');
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load data if not from state
  useEffect(() => {
    if (tiers.length === 0) {
      Promise.all([
        membershipApi.getTiers(),
        membershipApi.getStatus(),
      ]).then(([tRes, sRes]) => {
        if (tRes.code === 0 && tRes.data) {
          const sorted = [...tRes.data].sort((a, b) => a.sort_order - b.sort_order);
          setTiers(sorted);
          if (!selectedTier && locationState.tier) {
            const found = sorted.find(t => t.id === locationState.tier.id);
            if (found) setSelectedTier(found);
          }
        }
        if (sRes.code === 0 && sRes.data) setStatus(sRes.data);
      }).catch(() => {});
    }
  }, []);

  // Cleanup polling
  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // Poll order status
  const startPolling = useCallback((no: string) => {
    stopPolling();
    let count = 0;
    pollingRef.current = setInterval(async () => {
      count++;
      try {
        const res = await membershipApi.queryOrder(no);
        if (res.code === 0 && res.data) {
          if (res.data.status === 'paid') {
            stopPolling();
            setPayStatus('success');
            setPayMessage('升级成功！');
            setTimeout(() => {
              navigate('/membership', { replace: true, state: { transition: 'push_back' } });
            }, 2000);
            return;
          } else if (res.data.status === 'failed') {
            stopPolling();
            setPayStatus('failed');
            setPayMessage('支付失败');
          }
        }
        if (count > 20) {
          stopPolling();
          setPayStatus('failed');
          setPayMessage('支付结果确认超时');
        }
      } catch {
        // ignore polling errors
      }
    }, 3000);
  }, [navigate, stopPolling]);

  // Initiate payment
  const handleConfirmUpgrade = async () => {
    if (!selectedTier) return;

    setPayStatus('preparing');
    setPayMessage('正在创建订单...');

    try {
      const res = isTrial
        ? await membershipApi.trialGold(platform)
        : await membershipApi.upgrade(selectedTier.id, platform);

      if (res.code !== 0 || !res.data) {
        setPayStatus('error');
        setPayMessage(res.message || '创建订单失败');
        return;
      }

      const { order_no, pay_params } = res.data;
      setOrderNo(order_no);

      // 支付宝支付调起
      if (platform === 'alipay') {
        const alipayWin = window as WindowWithAlipay;

        if (alipayWin.AlipayJSBridge) {
          // In Alipay mini-program / Alipay browser
          setPayStatus('waiting');
          setPayMessage('请在支付宝中完成支付...');
          alipayWin.AlipayJSBridge.call('tradePay', {
            tradeNO: order_no,
            ...pay_params,
          }, (result) => {
            if (result.resultCode === '9000') {
              startPolling(order_no);
            } else {
              setPayStatus('failed');
              setPayMessage('支付取消或失败');
            }
          });
        } else if (pay_params.trade_no) {
          // Redirect to Alipay page (for desktop/mobile web)
          setPayStatus('waiting');
          setPayMessage('正在跳转支付宝...');
          const form = document.createElement('form');
          form.action = pay_params._redirect_url || 'https://openapi.alipay.com/gateway.do';
          form.method = 'POST';
          form.style.display = 'none';
          // Build auto-submit form with Alipay params
          Object.entries(pay_params).forEach(([k, v]) => {
            if (k !== '_redirect_url' && v != null) {
              const inp = document.createElement('input');
              inp.name = k;
              inp.value = String(v);
              form.appendChild(inp);
            }
          });
          document.body.appendChild(form);
          form.submit();
          startPolling(order_no);
        } else {
          // Fallback: navigate to PaymentBridge
          navigate(`/payment-bridge?order_no=${order_no}&amount=${selectedTier.price}&description=${encodeURIComponent(isTrial ? '首月体验金卡' : selectedTier.name + '升级')}`, {
            state: { transition: 'slide_up' },
          });
        }
      } else {
        // WeChat Pay - delegate to PaymentBridge
        navigate(`/payment-bridge?order_no=${order_no}&amount=${selectedTier.price}&description=${encodeURIComponent(isTrial ? '首月体验金卡' : selectedTier.name + '升级')}`, {
          state: { transition: 'slide_up' },
        });
      }
    } catch (e: any) {
      setPayStatus('error');
      setPayMessage(e.message || '支付异常');
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const handleTierSelect = (tier: MembershipTier) => {
    if (payStatus === 'preparing' || payStatus === 'waiting') return;
    setSelectedTier(tier);
    setPayStatus('idle');
    setPayMessage('');
  };

  const isFreeLevel = selectedTier?.level === 'free';

  // Success / Error screens
  if (payStatus === 'success') {
    return (
      <div className="flex flex-col min-h-screen bg-gradient-to-b from-emerald-50/30 via-white to-white font-sans items-center justify-center p-4">
        <div className="w-20 h-20 rounded-full bg-emerald-100 flex items-center justify-center mb-4">
          <Check className="w-10 h-10 text-emerald-600" />
        </div>
        <h2 className="font-manrope font-extrabold text-xl text-slate-800 mb-1">升级成功！</h2>
        <p className="text-slate-400 text-xs mb-6">正在跳回会员中心...</p>
        <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
      </div>
    );
  }

  if (payStatus === 'error') {
    return (
      <div className="flex flex-col min-h-screen bg-gradient-to-b from-rose-50/30 via-white to-white font-sans items-center justify-center p-4">
        <div className="w-20 h-20 rounded-full bg-rose-100 flex items-center justify-center mb-4">
          <X className="w-10 h-10 text-rose-600" />
        </div>
        <h2 className="font-manrope font-extrabold text-xl text-slate-800 mb-1">支付失败</h2>
        <p className="text-slate-400 text-xs mb-6">{payMessage}</p>
        <button
          onClick={() => { setPayStatus('idle'); setPayMessage(''); }}
          className="px-6 py-2.5 rounded-xl bg-sky-500 text-white text-xs font-bold active:scale-95 transition-transform"
        >
          重新尝试
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex items-center gap-3 px-4 h-16">
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">
          {isTrial ? '首月体验金卡' : '升级会员'}
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4 space-y-5">
        {/* Info banner for trial */}
        {isTrial && (
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-2xl border border-amber-100 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Gift className="w-4 h-4 text-amber-500" />
              <span className="font-bold text-amber-700 text-sm">首月体验 ¥99</span>
            </div>
            <p className="text-[11px] text-amber-600/70">
              免费试用金卡会员全部权益，首月仅需 ¥99，后续自动恢复原价
            </p>
          </div>
        )}

        {/* Tier Selection */}
        {tiers.length > 0 && (
          <section>
            <h3 className="font-bold text-slate-700 text-sm mb-3">选择会员层级</h3>
            <div className="space-y-2">
              {tiers.filter(t => t.level !== 'free').map(tier => {
                const cfg = levelConfig[tier.level];
                const Icon = cfg.icon;
                const isSelected = selectedTier?.id === tier.id;

                return (
                  <button
                    key={tier.id}
                    onClick={() => handleTierSelect(tier)}
                    disabled={payStatus === 'preparing' || payStatus === 'waiting'}
                    className={`w-full text-left bg-white rounded-2xl border-2 p-4 transition-all ${
                      isSelected
                        ? 'border-sky-400 shadow-md shadow-sky-100/50'
                        : 'border-slate-100 hover:border-slate-200'
                    } disabled:opacity-50`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-12 h-12 rounded-xl ${cfg.bgColor} flex items-center justify-center`}>
                        <Icon className={`w-6 h-6 ${cfg.color}`} />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className={`font-extrabold text-sm ${cfg.color}`}>{tier.name}</h4>
                          {isSelected && (
                            <div className="w-5 h-5 rounded-full bg-sky-500 flex items-center justify-center">
                              <Check className="w-3 h-3 text-white" />
                            </div>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {isTrial ? `首月 ¥99，后续 ${fmtPrice(tier.price)}/年` : `${fmtPrice(tier.price)}/年`}
                          {' · '}每月 {tier.对接券_per_month} 张对接券
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-extrabold text-slate-800">
                          {isTrial ? '¥99' : fmtPrice(tier.price)}
                        </p>
                        {!isTrial && (
                          <p className="text-[9px] text-slate-400">/年</p>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* Payment Platform Selection */}
        {selectedTier && !isFreeLevel && payStatus === 'idle' && (
          <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
            <h3 className="font-bold text-slate-700 text-sm mb-3">选择支付方式</h3>
            <div className="space-y-2">
              <button
                onClick={() => setPlatform('alipay')}
                className={`w-full text-left p-3 rounded-xl border-2 transition-all ${
                  platform === 'alipay' ? 'border-blue-400 bg-blue-50/50' : 'border-slate-100'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-500 flex items-center justify-center">
                    <span className="text-white font-extrabold text-xs">支</span>
                  </div>
                  <div className="flex-1">
                    <p className="font-bold text-slate-700 text-sm">支付宝</p>
                    <p className="text-[10px] text-slate-400">推荐：支持信用卡/借记卡</p>
                  </div>
                  {platform === 'alipay' && (
                    <Check className="w-5 h-5 text-blue-500" />
                  )}
                </div>
              </button>
              <button
                onClick={() => setPlatform('wxpay')}
                className={`w-full text-left p-3 rounded-xl border-2 transition-all ${
                  platform === 'wxpay' ? 'border-emerald-400 bg-emerald-50/50' : 'border-slate-100'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-emerald-500 flex items-center justify-center">
                    <span className="text-white font-extrabold text-xs">微</span>
                  </div>
                  <div className="flex-1">
                    <p className="font-bold text-slate-700 text-sm">微信支付</p>
                    <p className="text-[10px] text-slate-400">微信零钱/银行卡支付</p>
                  </div>
                  {platform === 'wxpay' && (
                    <Check className="w-5 h-5 text-emerald-500" />
                  )}
                </div>
              </button>
            </div>
          </section>
        )}

        {/* Price Summary & CTA */}
        {selectedTier && !isFreeLevel && (
          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm text-slate-600">合计</span>
              <span className="text-2xl font-extrabold text-sky-600">
                {isTrial ? '¥99' : fmtPrice(selectedTier.price)}
              </span>
            </div>

            {payStatus === 'preparing' || payStatus === 'waiting' ? (
              <div className="w-full py-3.5 rounded-2xl bg-sky-500 text-white text-sm font-extrabold flex items-center justify-center gap-2 opacity-80">
                <Loader2 className="w-4 h-4 animate-spin" />
                {payMessage}
              </div>
            ) : payStatus === 'failed' ? (
              <div className="space-y-2">
                <p className="text-xs text-rose-600 text-center">{payMessage}</p>
                <button
                  onClick={handleConfirmUpgrade}
                  className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-sky-500 to-blue-600 text-white text-sm font-extrabold active:scale-[0.97] transition-transform shadow-lg"
                >
                  重新支付
                </button>
              </div>
            ) : (
              <button
                onClick={handleConfirmUpgrade}
                className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-sky-500 to-blue-600 text-white text-sm font-extrabold active:scale-[0.97] transition-transform shadow-lg"
              >
                确认支付
              </button>
            )}
          </div>
        )}

        {/* Features of selected tier */}
        {selectedTier && !isFreeLevel && (
          <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
            <h3 className="font-bold text-slate-700 text-sm mb-3 flex items-center gap-2">
              <Info className="w-4 h-4 text-sky-500" />
              {selectedTier.name}权益
            </h3>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Ticket className="w-3.5 h-3.5 text-sky-500" />
                <span>每月 {selectedTier.对接券_per_month} 张对接券</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
                <span>推广佣金 {Math.round(selectedTier.commission_rate * 100)}%</span>
              </div>
              {selectedTier.features.map((f, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-slate-600">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span>{f}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
