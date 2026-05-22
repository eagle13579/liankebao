import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Share2, UserPlus, TrendingUp, Target, MessageCircle, FileText, Star, CheckCircle2, Copy, Link } from 'lucide-react';
import { useState } from 'react';

interface Step {
  title: string;
  content: string;
}

interface TutorialCard {
  icon: React.ElementType;
  title: string;
  description: string;
  steps: Step[];
  example: string;
  color: string;
  bgColor: string;
}

const tutorials: TutorialCard[] = [
  {
    icon: Share2,
    title: '如何分享产品',
    description: '进入产品池或首页推荐，点击产品下方的"我要推广"按钮，选择分享链接即可生成专属推广链接，发送给客户或分享到朋友圈。',
    steps: [
      { title: '选择产品', content: '打开链客宝首页或产品池，浏览推荐产品或热推商品，找到您想推广的产品。' },
      { title: '点击推广', content: '在产品卡片下方点击"我要推广"按钮，弹出推广方式选择窗口。' },
      { title: '生成链接', content: '选择"分享链接"方式，系统自动生成您的专属推广链接。链接已包含您的推广ID。' },
      { title: '发送客户', content: '将链接通过微信、短信或朋友圈发送给客户。客户点击链接下单后，您即可获得分润。' },
    ],
    example: '案例：张经理分享旗舰版智能健康手表S3链接给10位老客户，其中3位下单购买，张经理获得分润¥389.7。',
    color: 'text-sky-600',
    bgColor: 'bg-sky-50',
  },
  {
    icon: MessageCircle,
    title: '推广沟通技巧',
    description: '了解产品核心卖点后，用简洁明了的话术向客户介绍。先了解客户需求，再有针对性地推荐匹配产品，提高转化率。',
    steps: [
      { title: '了解客户需求', content: '先与客户沟通，了解其行业、规模和痛点。例如：客户做餐饮行业，可推荐数字化管理平台。' },
      { title: '突出产品价值', content: '针对客户痛点，介绍产品能解决的具体问题。用数据说话："使用后效率提升30%"。' },
      { title: '提供信任背书', content: '分享已成交客户的真实案例或好评截图，增强客户信任感。"已有500+企业选用"。' },
      { title: '促成行动', content: '给予限时优惠或赠品激励："今日下单赠送3个月VIP服务"。发送专属链接引导下单。' },
    ],
    example: '案例：李姐向企业客户推荐数字化管理平台，先了解客户有员工考勤和财务难题，针对性介绍平台功能，成功成交一笔¥9,800的订单。',
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
  },
  {
    icon: UserPlus,
    title: '如何发展下级',
    description: '在推广中心点击"我的下级"，将您的推广二维码或邀请链接分享给朋友。下级推广成交后，您可获得额外团队奖励。',
    steps: [
      { title: '生成邀请码', content: '进入推广中心 → 点击"我的下级" → 选择"邀请下级"，生成您的专属邀请二维码或链接。' },
      { title: '分享邀请', content: '将二维码或链接分享给朋友、同事或行业伙伴。强调收益："推广产品即可获得佣金，无门槛加入"。' },
      { title: '培训支持', content: '指导下级如何推广产品，分享您的推广经验和话术。帮助下级快速上手。' },
      { title: '团队管理', content: '在"我的下级"页面查看团队成员及其业绩。定期沟通，鼓励团队活跃度。' },
    ],
    example: '案例：王总邀请了5位朋友成为下级，每位下级月均推广收益约¥2,000，王总获得团队管理奖励¥500/月，月增收¥2,500。',
    color: 'text-violet-600',
    bgColor: 'bg-violet-50',
  },
  {
    icon: TrendingUp,
    title: '如何提高佣金',
    description: '提升推广等级可获得更高分润比例。持续推广优质产品、发展稳定下级团队、保持高转化率，均可提升您的佣金等级。',
    steps: [
      { title: '提升推广等级', content: '推广越多，等级越高，分润比例越大。普通会员分润5%，黄金会员分润8%，钻石会员分润12%。' },
      { title: '聚焦高佣金产品', content: '在热推产品中关注分润比例高的产品。如企业数字化管理平台分润¥980/单，远高于普通产品。' },
      { title: '发展下级团队', content: '每邀请一位有效下级，您可获得其推广佣金的10%作为团队奖励。团队越大，被动收入越高。' },
      { title: '保持高转化率', content: '精准推荐、及时跟进、优质服务能提高客户复购率。老客户复购无需重新开发，佣金持续到账。' },
    ],
    example: '案例：陈经理月推广额达¥50,000，晋升黄金会员（分润8%），同时拥有8人下级团队，月总收入突破¥6,000。',
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
  },
  {
    icon: Target,
    title: '精准获客策略',
    description: '利用人脉管理功能对客户打标签、分类管理。针对不同客户群体推送对应的产品，提高推广效率和成交率。',
    steps: [
      { title: '客户分类打标签', content: '在"人脉管理"中为联系人添加标签，如"大健康客户""企业服务""高意向""已成交"等，建立客户画像。' },
      { title: '制定推送策略', content: '根据标签分组制定不同推广策略。如向"大健康客户"推送健康手表和茶礼，向"企业服务"推送管理平台。' },
      { title: '定期跟进回访', content: '设置跟进计划，每周联系一次重点客户。使用"人脉管理"的记录功能，追踪每次沟通内容。' },
      { title: '分析优化', content: '定期分析各客户群的转化率。针对转化率低的群体，调整推荐产品或沟通方式，持续优化策略。' },
    ],
    example: '案例：刘总将客户分为"健康关注""企业管理""教育培训"三类，分别推送对应产品，转化率从15%提升至38%。',
    color: 'text-rose-600',
    bgColor: 'bg-rose-50',
  },
  {
    icon: FileText,
    title: '推广素材使用',
    description: '在推广中心可生成产品海报和推广文案，一键复制推广语。使用官方提供的精美素材，让推广更专业、更有说服力。',
    steps: [
      { title: '生成推广海报', content: '在产品推广弹窗中选择"生成海报"，系统自动生成含产品图和二维码的精美海报，可直接保存到相册。' },
      { title: '复制推广文案', content: '在推广方式中选择"复制推广语"，一键复制官方撰写的推广文案。文案包含产品卖点和购买引导。' },
      { title: '多渠道分发', content: '将海报和文案通过微信朋友圈、微信群、公众号、短视频平台等渠道分发，扩大触达面。' },
      { title: '素材组合使用', content: '搭配使用海报+推荐语+客户好评截图，形成完整的推广素材包，提升客户信任度和下单意愿。' },
    ],
    example: '案例：周姐使用系统生成的海报+推广语，配合自己拍摄的产品使用短视频，在朋友圈发布后获得200+点赞，当天成交5单。',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
  },
];

export function PromotionTutorial() {
  const navigate = useNavigate();
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [toast, setToast] = useState('');

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-8">
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex items-center gap-3 px-4 h-16">
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">
          推广教程
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4">
        {/* Header Banner */}
        <div className="relative w-full aspect-[21/8] rounded-2xl overflow-hidden bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 mb-5 shadow-lg">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent_60%)]" />
          <div className="absolute inset-0 flex flex-col justify-center px-6">
            <div className="flex items-center gap-2 mb-2">
              <Star className="w-4 h-4 text-amber-300" />
              <span className="text-white/80 text-[10px] font-bold">推广新手必读</span>
            </div>
            <h2 className="text-white font-bold text-xl leading-tight">成为推广达人</h2>
            <p className="text-white/70 text-xs mt-1 max-w-xs">掌握推广技巧，轻松提升业绩</p>
          </div>
        </div>

        {/* Tutorial Cards */}
        <div className="space-y-4">
          {tutorials.map((tutorial, i) => {
            const Icon = tutorial.icon;
            const isExpanded = expandedIndex === i;
            return (
              <div
                key={i}
                className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm hover:shadow-md transition-all cursor-pointer"
                onClick={() => setExpandedIndex(isExpanded ? null : i)}
              >
                <div className="flex gap-4">
                  <div className={`w-12 h-12 rounded-2xl ${tutorial.bgColor} flex items-center justify-center shrink-0 border border-white/60`}>
                    <Icon className={`w-6 h-6 ${tutorial.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <h3 className="font-extrabold text-slate-800 text-sm">
                        {tutorial.title}
                      </h3>
                      <span className="text-[8px] bg-sky-50 text-sky-600 px-1.5 py-0.5 rounded-full font-bold">
                        Step {i + 1}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 leading-relaxed">
                      {tutorial.description}
                    </p>

                    {/* Expandable Steps */}
                    {isExpanded && (
                      <div className="mt-4 pt-4 border-t border-slate-100 space-y-3">
                        {tutorial.steps.map((step, si) => (
                          <div key={si} className="flex gap-3">
                            <div className="w-6 h-6 rounded-full bg-sky-100 flex items-center justify-center shrink-0 mt-0.5">
                              <span className="text-[10px] font-bold text-sky-600">{si + 1}</span>
                            </div>
                            <div>
                              <h4 className="text-xs font-bold text-slate-700">{step.title}</h4>
                              <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{step.content}</p>
                            </div>
                          </div>
                        ))}

                        {/* Example */}
                        <div className="mt-3 bg-amber-50/80 border border-amber-100/50 rounded-xl p-3">
                          <div className="flex items-center gap-1.5 mb-1">
                            <Star className="w-3.5 h-3.5 text-amber-500" fill="currentColor" />
                            <span className="text-[10px] font-bold text-amber-700">实操案例</span>
                          </div>
                          <p className="text-[11px] text-amber-800/90 leading-relaxed">{tutorial.example}</p>
                        </div>
                      </div>
                    )}

                    {!isExpanded && (
                      <p className="text-[10px] text-sky-400 font-medium mt-2">点击展开详细步骤 →</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom Tip */}
        <div className="mt-6 bg-gradient-to-r from-amber-50 to-amber-50/50 border border-amber-100/50 rounded-2xl p-4">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center shrink-0">
              <Star className="w-4 h-4 text-amber-600" />
            </div>
            <div>
              <h4 className="font-bold text-amber-800 text-sm">小贴士</h4>
              <p className="text-xs text-amber-700/80 mt-1">
                持续学习推广技巧、关注热推产品、维护好您的客户关系网，推广收益会稳步增长。
                如有任何问题，请联系您的上级或客服人员。
              </p>
            </div>
          </div>
        </div>

        {/* Toast */}
        {toast && (
          <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[60] bg-slate-800 text-white text-sm font-bold px-5 py-3 rounded-full shadow-lg animate-[fadeIn_0.2s_ease-out]">
            {toast}
          </div>
        )}
      </main>
    </div>
  );
}
