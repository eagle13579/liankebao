import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface Tier {
  name: string
  icon: string
  price: string
  color: string
  bgColor: string
  borderColor: string
  features: string[]
  badge: string
}

const tiers: Tier[] = [
  {
    name: '普通会员',
    icon: '👑',
    price: '免费',
    color: '#64748b',
    bgColor: '#f8fafc',
    borderColor: '#e2e8f0',
    features: ['基础产品推广权限', '标准分润比例 5%', '基础数据查看'],
    badge: '免费',
  },
  {
    name: '黄金会员',
    icon: '🛡️',
    price: '¥199/年',
    color: '#d97706',
    bgColor: '#fffbeb',
    borderColor: '#fde68a',
    features: ['推广佣金提升至 8%', '优先审核产品上架', '专属客服支持', '月度推广报告'],
    badge: '热销',
  },
  {
    name: '钻石会员',
    icon: '💎',
    price: '¥499/年',
    color: '#0284c7',
    bgColor: '#f0f9ff',
    borderColor: '#bae6fd',
    features: ['推广佣金提升至 12%', '优先审核 + 24h上架', '专属客服经理', '季度营销支持', '线下活动优先参与'],
    badge: '推荐',
  },
  {
    name: '至尊会员',
    icon: '👑',
    price: '¥999/年',
    color: '#7c3aed',
    bgColor: '#f5f3ff',
    borderColor: '#ddd6fe',
    features: ['推广佣金提升至 15%', '极速审核 + 即时上架', '1对1专属客户经理', '定制营销方案', '品牌联合推广机会', '年度峰会VIP席位'],
    badge: '尊享',
  },
]

const memberBenefits = [
  { icon: '📈', label: '推广佣金提升', desc: '最高可达15%分润比例' },
  { icon: '⏱️', label: '优先审核', desc: '产品上架审核提速' },
  { icon: '🎧', label: '专属客服', desc: '7×24小时专属服务' },
  { icon: '⚡', label: '极速上架', desc: '钻石及以上即时上架' },
  { icon: '⭐', label: '营销支持', desc: '季度/年度营销方案' },
  { icon: '👤', label: '专属经理', desc: '1对1客户经理服务' },
]

interface MembershipState {
  memberInfo: any | null
  loading: boolean
  error: string
}

export default class MembershipIndex extends Component<{}, MembershipState> {
  state: MembershipState = {
    memberInfo: null,
    loading: true,
    error: '',
  }

  componentDidMount() {
    this.fetchMemberInfo()
  }

  fetchMemberInfo = () => {
    this.setState({ loading: true, error: '' })
    api.get('/membership')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ memberInfo: res.data, loading: false })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleUpgrade = (tier: Tier) => {
    Taro.showToast({ title: `即将开通${tier.name}，敬请期待`, icon: 'none' })
  }

  render() {
    const { memberInfo, loading, error } = this.state
    const currentLevel = memberInfo?.level || '普通会员'

    return (
      <View className='membership'>
        {/* Header */}
        <View className='ms-header'>
          <Text className='ms-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='ms-title'>会员中心</Text>
        </View>

        <ScrollView className='ms-body' scrollY>
          {loading ? (
            <View className='ms-loading'>
              <View className='ms-skel-banner' />
              <View className='ms-skel-grid'>
                {[1, 2, 3, 4].map((i) => (
                  <View key={i} className='ms-skel-card' />
                ))}
              </View>
              <View className='ms-skel-benefits' />
            </View>
          ) : error ? (
            <View className='ms-error'>
              <Text className='ms-error-icon'>⚠️</Text>
              <Text className='ms-error-text'>{error}</Text>
              <Text className='ms-error-retry' onClick={this.fetchMemberInfo}>点击重试</Text>
            </View>
          ) : (
            <View>
              {/* Current Membership Banner */}
              <View className='ms-banner'>
                <View className='ms-banner-content'>
                  <View className='ms-banner-label'>
                    <Text className='ms-banner-icon'>👑</Text>
                    <Text className='ms-banner-label-text'>当前等级</Text>
                  </View>
                  <Text className='ms-banner-level'>{currentLevel}</Text>
                  <Text className='ms-banner-desc'>升级会员享更高佣金比例与专属权益</Text>
                </View>
              </View>

              {/* Upgrade Cards */}
              <View className='ms-section'>
                <View className='ms-section-title-row'>
                  <Text className='ms-section-icon'>✨</Text>
                  <Text className='ms-section-title'>升级会员等级</Text>
                </View>
                <View className='ms-tier-grid'>
                  {tiers.map((tier, i) => {
                    const isCurrent = tier.name === currentLevel
                    return (
                      <View
                        key={i}
                        className={`ms-tier-card ${isCurrent ? 'ms-tier-current' : ''}`}
                        style={{ borderColor: tier.borderColor }}
                      >
                        <View className='ms-tier-top'>
                          <View className='ms-tier-icon-wrap' style={{ backgroundColor: tier.bgColor }}>
                            <Text className='ms-tier-icon'>{tier.icon}</Text>
                          </View>
                          <Text
                            className='ms-tier-badge'
                            style={{
                              backgroundColor: i === 0 ? '#f1f5f9' : i === 1 ? '#fef3c7' : i === 2 ? '#e0f2fe' : '#ede9fe',
                              color: i === 0 ? '#64748b' : i === 1 ? '#b45309' : i === 2 ? '#0369a1' : '#6d28d9',
                            }}
                          >
                            {tier.badge}
                          </Text>
                        </View>
                        <Text className='ms-tier-name'>{tier.name}</Text>
                        <Text className='ms-tier-price'>{tier.price}</Text>
                        <View className='ms-tier-features'>
                          {tier.features.slice(0, 2).map((f, fi) => (
                            <Text key={fi} className='ms-tier-feature'>✅ {f}</Text>
                          ))}
                        </View>
                        {!isCurrent && i > 0 && (
                          <View className='ms-tier-btn' onClick={() => this.handleUpgrade(tier)}>
                            <Text>立即升级</Text>
                          </View>
                        )}
                        {isCurrent && (
                          <View className='ms-tier-current-badge'>
                            <Text>当前等级</Text>
                          </View>
                        )}
                      </View>
                    )
                  })}
                </View>
              </View>

              {/* Membership Benefits */}
              <View className='ms-section ms-benefits-section'>
                <View className='ms-section-title-row'>
                  <Text className='ms-section-icon'>⭐</Text>
                  <Text className='ms-section-title'>会员权益一览</Text>
                </View>
                <View className='ms-benefits-grid'>
                  {memberBenefits.map((benefit, i) => (
                    <View key={i} className='ms-benefit-item'>
                      <View className='ms-benefit-icon-wrap'>
                        <Text className='ms-benefit-icon'>{benefit.icon}</Text>
                      </View>
                      <Text className='ms-benefit-label'>{benefit.label}</Text>
                      <Text className='ms-benefit-desc'>{benefit.desc}</Text>
                    </View>
                  ))}
                </View>
              </View>

              {/* My Products Entry */}
              <View
                className='ms-entry-card'
                onClick={() => Taro.navigateTo({ url: '/pages/mine/index' })}
              >
                <View className='ms-entry-left'>
                  <View className='ms-entry-icon-wrap ms-entry-green'>
                    <Text className='ms-entry-icon'>📦</Text>
                  </View>
                  <View className='ms-entry-info'>
                    <Text className='ms-entry-title'>我的产品</Text>
                    <Text className='ms-entry-desc'>管理您上架的产品，查看推广数据</Text>
                  </View>
                </View>
                <Text className='ms-entry-arrow'>›</Text>
              </View>

              {/* Add Product Entry */}
              <View
                className='ms-entry-card'
                onClick={() => Taro.showToast({ title: '功能开发中', icon: 'none' })}
              >
                <View className='ms-entry-left'>
                  <View className='ms-entry-icon-wrap ms-entry-amber'>
                    <Text className='ms-entry-icon'>🛍️</Text>
                  </View>
                  <View className='ms-entry-info'>
                    <Text className='ms-entry-title'>上架新产品</Text>
                    <Text className='ms-entry-desc'>提交您的优质货源，触达海量推广员</Text>
                  </View>
                </View>
                <Text className='ms-entry-arrow'>›</Text>
              </View>

              {/* Recharge Entry */}
              <View
                className='ms-entry-card ms-entry-recharge'
                onClick={() => Taro.navigateTo({ url: '/pages/recharge/index' })}
              >
                <View className='ms-entry-left'>
                  <View className='ms-entry-icon-wrap ms-entry-sky'>
                    <Text className='ms-entry-icon'>💳</Text>
                  </View>
                  <View className='ms-entry-info'>
                    <Text className='ms-entry-title ms-entry-title-sky'>账户充值</Text>
                    <Text className='ms-entry-desc ms-entry-desc-sky'>充值到账户余额，支持微信/支付宝</Text>
                  </View>
                </View>
                <Text className='ms-entry-arrow ms-entry-arrow-sky'>›</Text>
              </View>

              {/* Commission Comparison */}
              <View className='ms-commission-section'>
                <View className='ms-section-title-row'>
                  <Text className='ms-section-icon'>📊</Text>
                  <Text className='ms-section-title'>佣金比例对比</Text>
                </View>
                <View className='ms-commission-list'>
                  {[
                    { level: '普通会员', rate: '5%', color: 'text-slate' },
                    { level: '黄金会员', rate: '8%', color: 'text-amber' },
                    { level: '钻石会员', rate: '12%', color: 'text-sky' },
                    { level: '至尊会员', rate: '15%', color: 'text-violet' },
                  ].map((item, i) => (
                    <View key={i} className='ms-commission-row'>
                      <Text className='ms-commission-level'>{item.level}</Text>
                      <Text className={`ms-commission-rate ms-commission-${item.color}`}>
                        {item.rate}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            </View>
          )}
        </ScrollView>
      </View>
    )
  }
}
