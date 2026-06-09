import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Crown, TrendingUp, Star, HelpCircle, CheckCircle, Zap, Users, Building2, ShoppingBag, Percent } from 'lucide-react';
import { useState } from 'react';

interface FaqItem {
  q: string;
  a: string;
}

const faqs: FaqItem[] = [
  {
    q: '什么是流量合伙人？',
    a: '流量合伙人即链客宝AI推广员。您只需推荐企业免费入驻链客宝AI，企业上架产品时自行设置分润比例（如5%），您推广该产品成交后即可获得销售额×分润比例的佣金。无需囤货、无需售后，推广赚钱就是这么简单。',
  },
  {
    q: '注册成为流量合伙人需要付费吗？',
    a: '完全免费，零门槛。链客宝AI不收取任何注册费、入门费、保证金。注册即获得专属推广码，分享即可赚取佣金。',
  },
  {
    q: '分润比例是谁设定的？',
    a: '分润比例由入驻企业自行设定。企业在上架产品时设置"推广分润比例"（如5%、8%、10%等），平台审核通过后，推广员每成交一单即可获得该比例的分润。比例越高，产品对推广员的吸引力越大。',
  },
  {
    q: '分润怎么计算？佣金何时到账？',
    a: '佣金=订单成交额×企业设定的分润比例。订单确认收货后T+1到账钱包，最低提现¥100，0手续费，提现至支付宝/微信/银行卡。',
  },
  {
    q: '我是企业，如何入驻并设置分润？',
    a: '3步走：① 注册链客宝AI账号 ② 上架产品时在"推广分润比例"栏输入您愿意支付的百分比（如5%） ③ 提交审核上架。之后所有推广员都会看到您的产品，推广成交后平台自动计算分润。',
  },
  {
    q: '客户退款了怎么办？',
    a: '退款成功后该笔订单佣金从钱包扣回（余额不足时从后续新增佣金抵扣）。退款不影响绑定关系，客户下次购买您仍享受分润。',
  },
  {
    q: '推广方式有哪些？',
    a: '多种方式：社交分享（朋友圈发产品海报）、私聊推荐（一对一推荐给潜在客户）、线下展示（带样品参加活动）、内容引流（抖音/小红书做内容挂链接）。链客宝AI为您提供专属推广码和推广素材。',
  },
  {
    q: '为什么选择链客宝AI流量合伙人模式？',
    a: '① 零成本零风险：免费注册，无需囤货，无需售后 ② 企业自主设比例：分润透明，推广员按成交拿钱 ③ 产品丰富多样：大健康、企业服务、教育培训等多品类 ④ 结算及时：确认收货后T+1到账。',
  },
];

export default function PartnerPolicy() {
  const navigate = useNavigate();
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
          分润政策
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4">
        {/* Hero Banner */}
        <div className="relative w-full aspect-[21/8] rounded-2xl overflow-hidden bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 mb-5 shadow-lg">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent_60%)]" />
          <div className="absolute inset-0 flex flex-col justify-center px-6">
            <div className="flex items-center gap-2 mb-2">
              <Crown className="w-4 h-4 text-amber-300" />
              <span className="text-white/80 text-[10px] font-bold">流量合伙人模式</span>
            </div>
            <h2 className="text-white font-bold text-xl leading-tight">推广赚钱，就这么简单</h2>
            <p className="text-white/70 text-xs mt-1 max-w-xs">推荐企业入驻 · 推广产品成交 · 赚取分润佣金</p>
          </div>
        </div>

        {/* Mode Explanation */}
        <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm mb-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="w-1 h-5 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full" />
            <h3 className="font-extrabold text-slate-800">分润模式说明</h3>
          </div>

          <div className="space-y-4">
            {/* Step 1 */}
            <div className="flex gap-3 items-start">
              <div className="w-8 h-8 rounded-xl bg-sky-100 flex items-center justify-center shrink-0">
                <span className="text-sm font-extrabold text-sky-600">1</span>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <Users className="w-4 h-4 text-sky-500" />
                  <h4 className="font-bold text-slate-800 text-sm">推广员推荐企业</h4>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  推广员（流量合伙人）推荐企业免费入驻链客宝AI平台，获取专属推广码。
                </p>
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex gap-3 items-start">
              <div className="w-8 h-8 rounded-xl bg-sky-100 flex items-center justify-center shrink-0">
                <span className="text-sm font-extrabold text-sky-600">2</span>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <Building2 className="w-4 h-4 text-sky-500" />
                  <h4 className="font-bold text-slate-800 text-sm">企业上架产品并设分润</h4>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  入驻企业上架产品，自行设置推广分润比例（如5%）。产品通过审核后进入产品池。
                </p>
              </div>
            </div>

            {/* Step 3 */}
            <div className="flex gap-3 items-start">
              <div className="w-8 h-8 rounded-xl bg-sky-100 flex items-center justify-center shrink-0">
                <span className="text-sm font-extrabold text-sky-600">3</span>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <ShoppingBag className="w-4 h-4 text-sky-500" />
                  <h4 className="font-bold text-slate-800 text-sm">买家购买产品</h4>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  买家通过推广员的推广链接或二维码下单购买产品，完成交易。
                </p>
              </div>
            </div>

            {/* Step 4 */}
            <div className="flex gap-3 items-start">
              <div className="w-8 h-8 rounded-xl bg-emerald-100 flex items-center justify-center shrink-0">
                <span className="text-sm font-extrabold text-emerald-600">4</span>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <Percent className="w-4 h-4 text-emerald-500" />
                  <h4 className="font-bold text-slate-800 text-sm">推广员获得分润</h4>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  推广员获得该笔销售额 × 企业设定的分润比例。分润透明、结算及时。
                </p>
              </div>
            </div>
          </div>

          {/* Example */}
          <div className="mt-5 bg-gradient-to-r from-sky-50 to-sky-50/30 border border-sky-100/50 rounded-xl p-4">
            <div className="flex items-center gap-1.5 mb-2">
              <Star className="w-4 h-4 text-amber-500" fill="currentColor" />
              <span className="text-xs font-bold text-sky-700">分润示例</span>
            </div>
            <p className="text-xs text-sky-800/90 leading-relaxed">
              某企业上架一款产品售价¥1,000，设置分润比例5%。推广员推广成交1单佣金=1,000×5%=¥50；推广10单佣金=¥500。分润比例越高，推广员收益越大。
            </p>
          </div>
        </section>

        {/* Role Structure */}
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="w-1 h-5 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full" />
            <h3 className="font-extrabold text-slate-800">角色说明</h3>
          </div>

          <div className="space-y-4">
            {/* Promoter Role */}
            <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden shadow-sm">
              <div className="p-5 flex gap-4 items-start">
                <div className="w-14 h-14 rounded-2xl bg-sky-50 flex items-center justify-center shrink-0 border border-white/60">
                  <Zap className="w-7 h-7 text-sky-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-extrabold text-slate-800 text-base">推广员</h3>
                    <span className="text-[10px] bg-sky-50 text-sky-600 px-2 py-0.5 rounded-full font-bold">
                      流量合伙人
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">零门槛注册，推广产品赚取分润佣金</p>
                  <div className="mt-2 flex flex-wrap gap-4">
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">免费注册</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">无需囤货</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">按成交分润</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">T+1到账</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Enterprise Role */}
            <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden shadow-sm">
              <div className="p-5 flex gap-4 items-start">
                <div className="w-14 h-14 rounded-2xl bg-violet-50 flex items-center justify-center shrink-0 border border-white/60">
                  <Building2 className="w-7 h-7 text-violet-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-extrabold text-slate-800 text-base">入驻企业</h3>
                    <span className="text-[10px] bg-violet-50 text-violet-600 px-2 py-0.5 rounded-full font-bold">
                      产品供应方
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">上架产品，自主设定分润比例，获得推广员网络</p>
                  <div className="mt-2 flex flex-wrap gap-4">
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">自主设分润</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">按效果付费</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">海量推广员</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-[11px] text-slate-600">平台担保交易</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
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
        <div className="bg-gradient-to-r from-sky-50 to-sky-50/30 border border-sky-100/50 rounded-2xl p-5 text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <HelpCircle className="w-4 h-4 text-sky-500" />
            <span className="text-xs font-bold text-sky-800">还有疑问？</span>
          </div>
          <p className="text-xs text-sky-700/80">
            更多详细内容请联系链客宝AI运营客服，或查看平台公告了解最新政策。
          </p>
        </div>
      </main>
    </div>
  );
}
