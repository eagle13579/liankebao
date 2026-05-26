import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Crown, Users, Globe, TrendingUp, Star, Award, HelpCircle, CheckCircle, Zap, Target, Gift } from 'lucide-react';
import { useState } from 'react';

interface LevelDetail {
  icon: React.ElementType;
  title: string;
  subtitle: string;
  level: string;
  rate: string;
  requirements: string[];
  benefits: string[];
  color: string;
  bgColor: string;
}

const levels: LevelDetail[] = [
  {
    icon: Zap,
    title: 'L1 资源经纪人',
    subtitle: '入门层 · 0门槛注册即享',
    level: 'L1',
    rate: '50%',
    requirements: [
      '0门槛，注册即成为推广员',
      '无需任何费用，零成本启动',
      '无硬性考核要求',
    ],
    benefits: [
      '自购返利：零售价50%返还',
      '分享佣金：成交额50%佣金',
      '专属推广码，永久绑定上下级',
      '免费培训：每周推广大师课',
      '爆品优先体验权：每月2款免费试用',
      '推广素材库每周更新',
    ],
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
  },
  {
    icon: Users,
    title: 'L2 企业合伙人',
    subtitle: '骨干层 · 带团队放大收益',
    level: 'L2',
    rate: '20%~30%',
    requirements: [
      '月推广成交 ≥ 5单',
      '或 直属团队 ≥ 10人',
      '或 个人+团队月GMV ≥ ¥30,000',
    ],
    benefits: [
      '包含L1全部权益',
      '团队管理奖：L1团队成交额的20%~30%',
      '优先选品权：新品提前48小时锁货',
      '企业合伙人官方授权证书',
      '总部线下沙龙每月1次',
      '1对1专属运营顾问',
    ],
    color: 'text-violet-600',
    bgColor: 'bg-violet-50',
  },
  {
    icon: Globe,
    title: 'L3 城市合伙人',
    subtitle: '战略层 · 掌控城市运营权',
    level: 'L3',
    rate: '8%~15%',
    requirements: [
      '团队总人数 ≥ 50人',
      '直属L2 ≥ 5人',
      '团队月GMV ≥ ¥100,000（连续3月）',
      '通过总部面试/答辩',
    ],
    benefits: [
      '包含L1+L2全部权益',
      '区域分成：所辖区域订单8%~15%流水分成',
      '城市经营授权：可用品牌开展招商活动',
      '总部战略会席位：参与产品定价与决策',
      '股权/期权激励池（年度考核前10%）',
      '区域招商权、线下活动补贴',
    ],
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
  },
];

interface Incentive {
  period: string;
  items: { rank: string; prize: string }[];
}

const incentives: Incentive[] = [
  {
    period: '日榜（每日结算）',
    items: [
      { rank: '🥇 冠军', prize: '¥888' },
      { rank: '🥇 新人奖', prize: '¥188' },
      { rank: '🎯 破零奖', prize: '¥66' },
    ],
  },
  {
    period: '周榜（每周一结算）',
    items: [
      { rank: '🥇 第1名', prize: '¥3,888' },
      { rank: '🥈 第2名', prize: '¥1,888' },
      { rank: '🥉 第3名', prize: '¥888' },
      { rank: '🏆 团队第1名', prize: '¥5,888' },
    ],
  },
  {
    period: '月榜（每月1日结算）',
    items: [
      { rank: '🥇 第1名', prize: '¥18,888' },
      { rank: '🥈 第2名', prize: '¥8,888' },
      { rank: '🥉 第3名', prize: '¥3,888' },
      { rank: '🏆 最强团队奖', prize: '¥38,888' },
    ],
  },
  {
    period: '年榜（年度盛典）',
    items: [
      { rank: '🏆 总冠军', prize: '¥388,888 + 奔驰E级使用权1年' },
      { rank: '🥇 亚军', prize: '¥188,888 + 欧洲商务考察' },
      { rank: '🥈 季军', prize: '¥88,888 + 日本参访' },
      { rank: '🌟 最佳团队奖', prize: '¥288,888' },
    ],
  },
];

interface FaqItem {
  q: string;
  a: string;
}

const faqs: FaqItem[] = [
  {
    q: '如何注册成为链客宝推广员？',
    a: '3步走：扫推荐人二维码 → 填写手机号获取验证码 → 完善资料即完成。注册后自动成为L1资源经纪人，获得专属推广码。全程免费，零门槛。',
  },
  {
    q: '注册需要交钱吗？',
    a: '完全免费，零门槛。链客宝不收取任何注册费、入门费、保证金。注册即可获得专属推广码，分享即可赚取佣金。',
  },
  {
    q: '我是外地的，能注册吗？',
    a: '全国均可注册，无地域限制。L1和L2面向全国招募。L3城市合伙人需在固定城市运营，但初期不需要确定城市。',
  },
  {
    q: '注册后从哪里开始？',
    a: '三步启动：① 先买一单体验流程 ② 分享朋友圈使用一键发圈 ③ 私聊3位企业家朋友推荐产品。完成可领新人破冰奖¥66。',
  },
  {
    q: '我该怎么推广？有哪些方式？',
    a: '4种核心方式：社交分享（朋友圈发海报）、私聊推荐（一对一推荐）、线下展示（带样品参加活动）、内容引流（抖音/小红书做内容）。',
  },
  {
    q: '客户下单后，怎么知道是我的业绩？',
    a: '采用永久绑定制。客户通过你的推广码首次访问后，系统自动绑定到你名下。该客户后续所有消费你都有分润，终身有效。',
  },
  {
    q: '客户退款了怎么办？',
    a: '退款成功后该笔订单佣金从钱包扣回（余额不足时从后续新增佣金扣）。退款不影响绑定关系，客户下次购买你仍享受分润。',
  },
  {
    q: '我能自己买自己的东西吗？',
    a: '可以。通过自己的推广码消费同样享受50%自购返利（相当于5折）。但严禁虚假交易套取佣金，违者永久封号。',
  },
  {
    q: '分润怎么计算？佣金何时到账？',
    a: '直推佣金T+1到账钱包，团队管理奖T+7，区域分成次月10日前。最低提现¥100，0手续费，提现至支付宝/微信/银行卡。',
  },
  {
    q: '从L1升级到L2需要什么条件？',
    a: '满足其一即可：① 个人月成交≥5单 ② 直属团队≥10人 ③ 个人+团队月GMV≥¥30,000。满足条件后系统自动升级。',
  },
];

export default function PartnerPolicy() {
  const navigate = useNavigate();
  const [expandedLevel, setExpandedLevel] = useState<number | null>(null);
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-8">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex items-center gap-3 px-4 h-16">
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">
          合伙人政策
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4">
        {/* Hero Banner */}
        <div className="relative w-full aspect-[21/8] rounded-2xl overflow-hidden bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 mb-5 shadow-lg">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent_60%)]" />
          <div className="absolute inset-0 flex flex-col justify-center px-6">
            <div className="flex items-center gap-2 mb-2">
              <Crown className="w-4 h-4 text-amber-300" />
              <span className="text-white/80 text-[10px] font-bold">三级合伙人体系</span>
            </div>
            <h2 className="text-white font-bold text-xl leading-tight">人人都是创业者</h2>
            <p className="text-white/70 text-xs mt-1 max-w-xs">零成本创业 · 高端人脉圈 · 终身收益管道</p>
          </div>
        </div>

        {/* Three Levels */}
        <section className="space-y-4 mb-6">
          <div className="flex items-center gap-2">
            <span className="w-1 h-5 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full" />
            <h3 className="font-extrabold text-slate-800">三级合伙人体系</h3>
          </div>

          {levels.map((level, i) => {
            const Icon = level.icon;
            const isExpanded = expandedLevel === i;
            return (
              <div
                key={i}
                className="bg-white rounded-2xl border border-slate-100 overflow-hidden shadow-sm hover:shadow-md transition-all cursor-pointer"
                onClick={() => setExpandedLevel(isExpanded ? null : i)}
              >
                {/* Card Header */}
                <div className="p-5 flex gap-4 items-start">
                  <div className={`w-14 h-14 rounded-2xl ${level.bgColor} flex items-center justify-center shrink-0 border border-white/60`}>
                    <Icon className={`w-7 h-7 ${level.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-extrabold text-slate-800 text-base">{level.title}</h3>
                      <span className={`text-[10px] ${level.bgColor} ${level.color} px-2 py-0.5 rounded-full font-bold`}>
                        {level.level}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">{level.subtitle}</p>
                    <div className="mt-2 flex items-center gap-1">
                      <TrendingUp className={`w-3.5 h-3.5 ${level.color}`} />
                      <span className={`text-sm font-extrabold ${level.color}`}>分润 {level.rate}</span>
                    </div>
                  </div>
                  <div className={`w-6 h-6 rounded-full ${isExpanded ? 'bg-sky-100' : 'bg-slate-50'} flex items-center justify-center shrink-0 transition-all`}>
                    <ChevronLeft className={`w-4 h-4 ${isExpanded ? 'text-sky-600' : 'text-slate-400'} transition-transform ${isExpanded ? 'rotate-90' : '-rotate-90'}`} />
                  </div>
                </div>

                {/* Expandable Details */}
                {isExpanded && (
                  <div className="px-5 pb-5 pt-0 border-t border-slate-100">
                    {/* Requirements */}
                    <div className="mt-4">
                      <h4 className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1.5">
                        <Target className="w-3.5 h-3.5 text-sky-500" />
                        晋升门槛
                      </h4>
                      <div className="space-y-1.5">
                        {level.requirements.map((req, ri) => (
                          <div key={ri} className="flex items-center gap-2">
                            <CheckCircle className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                            <span className="text-xs text-slate-600">{req}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Benefits */}
                    <div className="mt-4">
                      <h4 className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1.5">
                        <Gift className="w-3.5 h-3.5 text-sky-500" />
                        核心权益
                      </h4>
                      <div className="space-y-1.5">
                        {level.benefits.map((ben, bi) => (
                          <div key={bi} className="flex items-center gap-2">
                            <CheckCircle className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                            <span className="text-xs text-slate-600">{ben}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Example */}
                    <div className="mt-4 bg-gradient-to-r from-sky-50 to-sky-50/30 border border-sky-100/50 rounded-xl p-3">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Star className="w-3.5 h-3.5 text-amber-500" fill="currentColor" />
                        <span className="text-[10px] font-bold text-sky-700">分润示例</span>
                      </div>
                      <p className="text-[11px] text-sky-800/90 leading-relaxed">
                        {level.level === 'L1' && '以¥1,980爆品套餐为例：推广成交1单佣金=1,980×50%=¥990；推广10单佣金=¥9,900。'}
                        {level.level === 'L2' && 'L2自己成交拿50%，下级L1成交拿团队管理奖20%~30%（取决于团队月GMV档位）。月GMV>20万按30%计算。'}
                        {level.level === 'L3' && 'L3自己成交=直推佣金50%+区域分成8%~15%。以区域月GMV 200万、分成12%计算，区域月收入=24万。'}
                      </p>
                    </div>
                  </div>
                )}

                {!isExpanded && (
                  <div className="px-5 pb-4">
                    <p className="text-[10px] text-sky-400 font-medium">点击展开详情 →</p>
                  </div>
                )}
              </div>
            );
          })}
        </section>

        {/* Incentive Prizes */}
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="w-1 h-5 bg-gradient-to-b from-amber-400 to-amber-600 rounded-full" />
            <h3 className="font-extrabold text-slate-800">四大排行榜激励方案</h3>
          </div>

          <div className="space-y-3">
            {incentives.map((incentive, i) => (
              <div key={i} className="bg-white rounded-2xl border border-slate-100 p-4 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                  <Award className="w-4 h-4 text-amber-500" />
                  <h4 className="text-xs font-extrabold text-slate-700">{incentive.period}</h4>
                </div>
                <div className="space-y-2">
                  {incentive.items.map((item, ii) => (
                    <div key={ii} className="flex items-center justify-between py-1.5 px-3 rounded-xl bg-slate-50/50">
                      <span className="text-xs font-bold text-slate-700">{item.rank}</span>
                      <span className="text-xs font-extrabold text-amber-600">{item.prize}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* FAQ */}
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="w-1 h-5 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full" />
            <h3 className="font-extrabold text-slate-800">常见问题（FAQ）</h3>
          </div>

          <div className="space-y-2">
            {faqs.map((faq, i) => {
              const isExpanded = expandedFaq === i;
              return (
                <div
                  key={i}
                  className="bg-white rounded-2xl border border-slate-100 overflow-hidden shadow-sm cursor-pointer"
                  onClick={() => setExpandedFaq(isExpanded ? null : i)}
                >
                  <div className="flex items-start gap-3 p-4">
                    <div className="w-6 h-6 rounded-full bg-sky-100 flex items-center justify-center shrink-0 mt-0.5">
                      <span className="text-[10px] font-bold text-sky-600">{i + 1}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-xs font-bold text-slate-700">{faq.q}</h4>
                      {isExpanded && (
                        <p className="text-[11px] text-slate-500 mt-2 leading-relaxed">{faq.a}</p>
                      )}
                    </div>
                    <ChevronLeft className={`w-4 h-4 text-slate-400 shrink-0 mt-1 transition-transform ${isExpanded ? 'rotate-90' : '-rotate-90'}`} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Bottom CTA */}
        <div className="bg-gradient-to-r from-amber-50 to-amber-50/30 border border-amber-100/50 rounded-2xl p-5 text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <HelpCircle className="w-4 h-4 text-amber-500" />
            <span className="text-xs font-bold text-amber-800">还有疑问？</span>
          </div>
          <p className="text-xs text-amber-700/80">
            更多详细内容请查看《合伙人政策手册》完整版，或联系您的运营顾问。
          </p>
        </div>
      </main>
    </div>
  );
}
