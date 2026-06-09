import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface Step {
  title: string
  content: string
}

interface TutorialCard {
  icon: string
  title: string
  description: string
  steps: Step[]
  example: string
  color: string
  bgColor: string
}

const tutorials: TutorialCard[] = [
  {
    icon: '🔗',
    title: '如何分享产品',
    description: '进入产品池或首页推荐，点击产品下方的"我要推广"按钮，选择分享链接即可生成专属推广链接，发送给客户或分享到朋友圈。',
    steps: [
      { title: '选择产品', content: '打开链客宝AI首页或产品池，浏览推荐产品或热推商品，找到您想推广的产品。' },
      { title: '点击推广', content: '在产品卡片下方点击"我要推广"按钮，弹出推广方式选择窗口。' },
      { title: '生成链接', content: '选择"分享链接"方式，系统自动生成您的专属推广链接。链接已包含您的推广ID。' },
      { title: '发送客户', content: '将链接通过微信、短信或朋友圈发送给客户。客户点击链接下单后，您即可获得分润。' },
    ],
    example: '案例：张经理分享旗舰版智能健康手表S3链接给10位老客户，其中3位下单购买，张经理获得分润¥389.7。',
    color: '#0284c7',
    bgColor: '#f0f9ff',
  },
  {
    icon: '💬',
    title: '推广沟通技巧',
    description: '了解产品核心卖点后，用简洁明了的话术向客户介绍。先了解客户需求，再有针对性地推荐匹配产品，提高转化率。',
    steps: [
      { title: '了解客户需求', content: '先与客户沟通，了解其行业、规模和痛点。例如：客户做餐饮行业，可推荐数字化管理平台。' },
      { title: '突出产品价值', content: '针对客户痛点，介绍产品能解决的具体问题。用数据说话："使用后效率提升30%"。' },
      { title: '提供信任背书', content: '分享已成交客户的真实案例或好评截图，增强客户信任感。"已有500+企业选用"。' },
      { title: '促成行动', content: '给予限时优惠或赠品激励："今日下单赠送3个月VIP服务"。发送专属链接引导下单。' },
    ],
    example: '案例：李姐向企业客户推荐数字化管理平台，先了解客户有员工考勤和财务难题，针对性介绍平台功能，成功成交一笔¥9,800的订单。',
    color: '#059669',
    bgColor: '#ecfdf5',
  },
  {
    icon: '👥',
    title: '如何发展下级',
    description: '在推广中心点击"我的下级"，将您的推广二维码或邀请链接分享给朋友。下级推广成交后，您可获得额外团队奖励。',
    steps: [
      { title: '生成邀请码', content: '进入推广中心 → 点击"我的下级" → 选择"邀请下级"，生成您的专属邀请二维码或链接。' },
      { title: '分享邀请', content: '将二维码或链接分享给朋友、同事或行业伙伴。强调收益："推广产品即可获得佣金，无门槛加入"。' },
      { title: '培训支持', content: '指导下级如何推广产品，分享您的推广经验和话术。帮助下级快速上手。' },
      { title: '团队管理', content: '在"我的下级"页面查看团队成员及其业绩。定期沟通，鼓励团队活跃度。' },
    ],
    example: '案例：王总邀请了5位朋友成为下级，每位下级月均推广收益约¥2,000，王总获得团队管理奖励¥500/月，月增收¥2,500。',
    color: '#7c3aed',
    bgColor: '#f5f3ff',
  },
  {
    icon: '📈',
    title: '如何提高佣金',
    description: '提升推广等级可获得更高分润比例。持续推广优质产品、发展稳定下级团队、保持高转化率，均可提升您的佣金等级。',
    steps: [
      { title: '提升推广等级', content: '推广越多，等级越高，分润比例越大。普通会员分润5%，黄金会员分润8%，钻石会员分润12%。' },
      { title: '聚焦高佣金产品', content: '在热推产品中关注分润比例高的产品。如企业数字化管理平台分润¥980/单，远高于普通产品。' },
      { title: '发展下级团队', content: '每邀请一位有效下级，您可获得其推广佣金的10%作为团队奖励。团队越大，被动收入越高。' },
      { title: '保持高转化率', content: '精准推荐、及时跟进、优质服务能提高客户复购率。老客户复购无需重新开发，佣金持续到账。' },
    ],
    example: '案例：陈经理月推广额达¥50,000，晋升黄金会员（分润8%），同时拥有8人下级团队，月总收入突破¥6,000。',
    color: '#d97706',
    bgColor: '#fffbeb',
  },
  {
    icon: '🎯',
    title: '精准获客策略',
    description: '利用人脉管理功能对客户打标签、分类管理。针对不同客户群体推送对应的产品，提高推广效率和成交率。',
    steps: [
      { title: '客户分类打标签', content: '在"人脉管理"中为联系人添加标签，如"大健康客户""企业服务""高意向""已成交"等，建立客户画像。' },
      { title: '制定推送策略', content: '根据标签分组制定不同推广策略。如向"大健康客户"推送健康手表和茶礼，向"企业服务"推送管理平台。' },
      { title: '定期跟进回访', content: '设置跟进计划，每周联系一次重点客户。使用"人脉管理"的记录功能，追踪每次沟通内容。' },
      { title: '分析优化', content: '定期分析各客户群的转化率。针对转化率低的群体，调整推荐产品或沟通方式，持续优化策略。' },
    ],
    example: '案例：刘总将客户分为"健康关注""企业管理""教育培训"三类，分别推送对应产品，转化率从15%提升至38%。',
    color: '#e11d48',
    bgColor: '#fff1f2',
  },
  {
    icon: '📄',
    title: '推广素材使用',
    description: '在推广中心可生成产品海报和推广文案，一键复制推广语。使用官方提供的精美素材，让推广更专业、更有说服力。',
    steps: [
      { title: '生成推广海报', content: '在产品推广弹窗中选择"生成海报"，系统自动生成含产品图和二维码的精美海报，可直接保存到相册。' },
      { title: '复制推广文案', content: '在推广方式中选择"复制推广语"，一键复制官方撰写的推广文案。文案包含产品卖点和购买引导。' },
      { title: '多渠道分发', content: '将海报和文案通过微信朋友圈、微信群、公众号、短视频平台等渠道分发，扩大触达面。' },
      { title: '素材组合使用', content: '搭配使用海报+推荐语+客户好评截图，形成完整的推广素材包，提升客户信任度和下单意愿。' },
    ],
    example: '案例：周姐使用系统生成的海报+推广语，配合自己拍摄的产品使用短视频，在朋友圈发布后获得200+点赞，当天成交5单。',
    color: '#2563eb',
    bgColor: '#eff6ff',
  },
]

interface TutorialState {
  expandedIndex: number | null
  loading: boolean
  error: string
  dataLoaded: boolean
}

export default class TutorialIndex extends Component<{}, TutorialState> {
  state: TutorialState = {
    expandedIndex: null,
    loading: true,
    error: '',
    dataLoaded: false,
  }

  componentDidMount() {
    // Simulate initial load by fetching from API (fallback to local data)
    this.fetchTutorialData()
  }

  fetchTutorialData = () => {
    this.setState({ loading: true, error: '' })
    api.get('/tutorial')
      .then((res: any) => {
        // API data is optional; local data is always available
        this.setState({ dataLoaded: true, loading: false })
      })
      .catch(() => {
        // Fallback: just use local data
        this.setState({ dataLoaded: true, loading: false })
      })
  }

  toggleExpand = (index: number) => {
    this.setState((prev) => ({
      expandedIndex: prev.expandedIndex === index ? null : index,
    }))
  }

  render() {
    const { expandedIndex, loading, error, dataLoaded } = this.state

    return (
      <View className='tutorial'>
        {/* Header */}
        <View className='tt-header'>
          <Text className='tt-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='tt-title'>推广教程</Text>
        </View>

        <ScrollView className='tt-body' scrollY>
          {loading ? (
            <View className='tt-loading'>
              <View className='tt-skel-banner' />
              <View className='tt-skel-list'>
                {[1, 2, 3].map((i) => (
                  <View key={i} className='tt-skel-card'>
                    <View className='tt-skel-icon-large' />
                    <View className='tt-skel-content'>
                      <View className='tt-skel-line w-50' />
                      <View className='tt-skel-line w-80' />
                      <View className='tt-skel-line w-60' />
                    </View>
                  </View>
                ))}
              </View>
            </View>
          ) : error ? (
            <View className='tt-error'>
              <Text className='tt-error-icon'>⚠️</Text>
              <Text className='tt-error-text'>{error}</Text>
              <Text className='tt-error-retry' onClick={this.fetchTutorialData}>点击重试</Text>
            </View>
          ) : (
            <View>
              {/* Header Banner */}
              <View className='tt-banner'>
                <View className='tt-banner-content'>
                  <View className='tt-banner-label'>
                    <Text className='tt-banner-star'>⭐</Text>
                    <Text className='tt-banner-label-text'>推广新手必读</Text>
                  </View>
                  <Text className='tt-banner-title'>成为推广达人</Text>
                  <Text className='tt-banner-desc'>掌握推广技巧，轻松提升业绩</Text>
                </View>
              </View>

              {/* Tutorial Cards */}
              <View className='tt-card-list'>
                {tutorials.map((tutorial, i) => {
                  const isExpanded = expandedIndex === i
                  return (
                    <View
                      key={i}
                      className='tt-card'
                      onClick={() => this.toggleExpand(i)}
                    >
                      <View className='tt-card-inner'>
                        <View className='tt-card-icon-wrap' style={{ backgroundColor: tutorial.bgColor }}>
                          <Text className='tt-card-icon'>{tutorial.icon}</Text>
                        </View>
                        <View className='tt-card-body'>
                          <View className='tt-card-top'>
                            <Text className='tt-card-title'>{tutorial.title}</Text>
                            <Text className='tt-card-step-label'>Step {i + 1}</Text>
                          </View>
                          <Text className='tt-card-desc'>{tutorial.description}</Text>

                          {/* Expandable Steps */}
                          {isExpanded && (
                            <View className='tt-steps'>
                              <View className='tt-steps-divider' />
                              {tutorial.steps.map((step, si) => (
                                <View key={si} className='tt-step'>
                                  <View className='tt-step-num-wrap'>
                                    <Text className='tt-step-num'>{si + 1}</Text>
                                  </View>
                                  <View className='tt-step-content'>
                                    <Text className='tt-step-title'>{step.title}</Text>
                                    <Text className='tt-step-desc'>{step.content}</Text>
                                  </View>
                                </View>
                              ))}

                              {/* Example */}
                              <View className='tt-example'>
                                <View className='tt-example-top'>
                                  <Text className='tt-example-star'>⭐</Text>
                                  <Text className='tt-example-label'>实操案例</Text>
                                </View>
                                <Text className='tt-example-text'>{tutorial.example}</Text>
                              </View>
                            </View>
                          )}

                          {!isExpanded && (
                            <Text className='tt-expand-hint'>点击展开详细步骤 →</Text>
                          )}
                        </View>
                      </View>
                    </View>
                  )
                })}
              </View>

              {/* Bottom Tip */}
              <View className='tt-tip'>
                <View className='tt-tip-inner'>
                  <View className='tt-tip-icon-wrap'>
                    <Text className='tt-tip-icon'>⭐</Text>
                  </View>
                  <View className='tt-tip-content'>
                    <Text className='tt-tip-title'>小贴士</Text>
                    <Text className='tt-tip-desc'>
                      持续学习推广技巧、关注热推产品、维护好您的客户关系网，推广收益会稳步增长。
                      如有任何问题，请联系您的上级或客服人员。
                    </Text>
                  </View>
                </View>
              </View>
            </View>
          )}
        </ScrollView>
      </View>
    )
  }
}
