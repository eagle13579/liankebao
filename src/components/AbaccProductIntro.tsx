/**
 * 链客宝 - ABACC产品介绍框架组件
 * 注入点：链客宝官网ABOUT页面加入ABACC框架展示
 * 规则：纯新增，不修改现有业务逻辑
 */

import React, { useState } from 'react';

interface AbaccCard {
  step: string;
  title: string;
  icon: string;
  color: string;
  description: string;
  example: string;
  tip: string;
}

const ABACC_CARDS: AbaccCard[] = [
  {
    step: 'A - Attention',
    title: '吸引注意',
    icon: '🎯',
    color: '#3B82F6',
    description: '用客户所在行业的趋势、竞品动态或具体数据破冰，在3秒内抓住客户注意力。',
    example: '"张总，我注意到贵司在拓展华东市场。链客宝刚帮同行业的XX公司在华东3个月匹配了200+意向客户。"',
    tip: '首句必须包含客户行业关键词或身份标签',
  },
  {
    step: 'B - Before',
    title: '痛点唤醒',
    icon: '🔥',
    color: '#EF4444',
    description: '将客户隐性的痛点具象化，用量化损失让"不痛"变成"很痛"。',
    example: '"现在销售团队30%时间在录信息而非成交，每月隐性损失超过5万。您的团队也有这个问题吧？"',
    tip: '金额/时间/效率的量化数据 + 反问确认句式',
  },
  {
    step: 'A - After',
    title: '愿景描绘',
    icon: '🌈',
    color: '#10B981',
    description: '展示使用链客宝后的理想状态，让客户"看到"改变后的价值。',
    example: '"使用链客宝后，销售自动完成信息录入和人脉匹配，团队效率提升40%，每周多出1天专注成交。"',
    tip: '用"想象一下""当您使用后"构建心理画面',
  },
  {
    step: 'C - Curiosity',
    title: '激发好奇',
    icon: '💡',
    color: '#F59E0B',
    description: '抛出差异化卖点中的"杀手锏"，制造信息差勾起客户深入了解的欲望。',
    example: '"链客宝不只是名片——它内置AI供需匹配引擎，自动推荐有真实需求的企业，这在行业内是唯一的。"',
    tip: '突出"唯一""首创"，与传统方案形成断层对比',
  },
  {
    step: 'C - Call Action',
    title: '号召行动',
    icon: '🚀',
    color: '#8B5CF6',
    description: '给出清晰的下一步动作，用二选一法降低决策门槛，制造紧迫感。',
    example: '"我让技术团队给您开一个免费试用账号，今天就能上线体验AI匹配效果——您看今天下午还是明天方便？"',
    tip: '二选一提问 + 具体时间节点 + 低承诺高价值',
  },
];

export default function AbaccProductIntro() {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  return (
    <section className="py-16 bg-gradient-to-b from-gray-50 to-white">
      <div className="max-w-5xl mx-auto px-4">
        {/* 标题区 */}
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-gray-900 mb-3">
            ABACC 说服逻辑框架
          </h2>
          <p className="text-gray-500 max-w-2xl mx-auto leading-relaxed">
            链客宝基于认知心理学与B2B销售实战沉淀的ABACC五步说服框架，
            帮助每一位销售在最短时间内构建高张力话术，提升转化率。
          </p>
          <div className="mt-4 inline-flex items-center gap-2 px-3 py-1 bg-blue-50 text-blue-700 text-xs rounded-full border border-blue-100">
            <span>⚡</span>
            <span>Attention → Before → After → Curiosity → Call Action</span>
          </div>
        </div>

        {/* 五步卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {ABACC_CARDS.map((card, index) => (
            <div
              key={card.step}
              className={`
                relative p-5 rounded-xl border-2 transition-all duration-300 cursor-pointer
                ${activeIndex === index
                  ? 'shadow-lg scale-105 border-opacity-100'
                  : 'shadow-sm hover:shadow-md hover:border-opacity-60'
                }
              `}
              style={{
                borderColor: card.color + (activeIndex === index ? 'ff' : '40'),
                backgroundColor: activeIndex === index ? '#FFFFFF' : '#FAFAFA',
              }}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onClick={() => setActiveIndex(activeIndex === index ? null : index)}
            >
              {/* 步骤标识 */}
              <div
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-white text-[10px] font-medium mb-3"
                style={{ backgroundColor: card.color }}
              >
                <span>{card.icon}</span>
                <span>{card.step}</span>
              </div>

              {/* 标题 */}
              <h3 className="text-base font-semibold text-gray-800 mb-2">{card.title}</h3>

              {/* 描述（展开时显示） */}
              <div className={`
                overflow-hidden transition-all duration-300
                ${activeIndex === index ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}
              `}>
                <p className="text-xs text-gray-500 leading-relaxed mb-2">
                  {card.description}
                </p>
                <div className="p-2 bg-gray-50 rounded-lg border border-gray-100 mb-2">
                  <p className="text-[11px] text-gray-600 italic">
                    "{card.example}"
                  </p>
                </div>
                <div className="flex items-start gap-1">
                  <span className="text-[10px] mt-0.5">💡</span>
                  <span className="text-[11px] text-gray-400">{card.tip}</span>
                </div>
              </div>

              {/* 未展开时的提示 */}
              {activeIndex !== index && (
                <p className="text-[10px] text-gray-400">悬停/点击查看详情 →</p>
              )}
            </div>
          ))}
        </div>

        {/* 底部CTA */}
        <div className="mt-10 text-center">
          <p className="text-sm text-gray-400 mb-3">
            在链客宝话术模板编辑器中，您可以基于ABACC框架创建和优化专属话术
          </p>
          <div className="flex justify-center gap-4 text-xs text-gray-400">
            <span>📊 数据增强器</span>
            <span>✨ 话术引导词</span>
            <span>📏 张力自检评分</span>
          </div>
        </div>
      </div>
    </section>
  );
}
