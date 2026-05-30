import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface PromoterState {
  earnings: {
    total_earnings: number
    withdrawn: number
    pending: number
    available: number
    order_count: number
  } | null
  withdrawals: any[]
  loading: boolean
  error: string
  tab: 'earnings' | 'withdrawals'
}

export default class PromoterIndex extends Component<{}, PromoterState> {
  state: PromoterState = {
    earnings: null,
    withdrawals: [],
    loading: true,
    error: '',
    tab: 'earnings',
  }

  componentDidMount() {
    this.fetchData()
  }

  fetchData = () => {
    this.setState({ loading: true, error: '' })
    Promise.all([
      api.get('/promoter/earnings'),
      api.get('/promoter/withdrawals'),
    ])
      .then(([earningsRes, withdrawalsRes]: any[]) => {
        this.setState({
          earnings: earningsRes.data || null,
          withdrawals: withdrawalsRes.data?.items || [],
          loading: false,
        })
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleWithdraw = () => {
    Taro.showToast({ title: '提现功能待完善', icon: 'none' })
  }

  handleSwitchTab = (tab: 'earnings' | 'withdrawals') => {
    this.setState({ tab })
  }

  render() {
    const { earnings, withdrawals, loading, error, tab } = this.state

    return (
      <View className='promoter'>
        {/* Header */}
        <View className='pt-header'>
          <Text className='pt-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='pt-title'>推广员中心</Text>
        </View>

        <ScrollView className='pt-body' scrollY>
          {loading ? (
            <View className='pt-loading'>
              {[1, 2, 3].map((i) => (
                <View key={i} className='pt-skel-card' />
              ))}
            </View>
          ) : error ? (
            <View className='pt-error'>
              <Text className='pt-error-icon'>⚠️</Text>
              <Text className='pt-error-text'>{error}</Text>
              <Text className='pt-error-retry' onClick={this.fetchData}>点击重试</Text>
            </View>
          ) : (
            <View>
              {/* Earnings Overview */}
              {earnings && (
                <View className='pt-earnings-card'>
                  <Text className='pt-ec-title'>我的收益</Text>
                  <Text className='pt-ec-amount'>¥{earnings.available.toFixed(2)}</Text>
                  <Text className='pt-ec-label'>可提现金额</Text>

                  <View className='pt-ec-stats'>
                    <View className='pt-ec-stat'>
                      <Text className='pt-ec-stat-val'>¥{earnings.total_earnings.toFixed(2)}</Text>
                      <Text className='pt-ec-stat-lbl'>累计收益</Text>
                    </View>
                    <View className='pt-ec-stat'>
                      <Text className='pt-ec-stat-val'>¥{earnings.withdrawn.toFixed(2)}</Text>
                      <Text className='pt-ec-stat-lbl'>已提现</Text>
                    </View>
                    <View className='pt-ec-stat'>
                      <Text className='pt-ec-stat-val'>¥{earnings.pending.toFixed(2)}</Text>
                      <Text className='pt-ec-stat-lbl'>审核中</Text>
                    </View>
                  </View>

                  <View className='pt-ec-action' onClick={this.handleWithdraw}>
                    <Text>申请提现</Text>
                  </View>
                </View>
              )}

              {/* Tab Switcher */}
              <View className='pt-tabs'>
                <Text
                  className={`pt-tab ${tab === 'earnings' ? 'pt-tab-active' : ''}`}
                  onClick={() => this.handleSwitchTab('earnings')}
                >
                  收益明细
                </Text>
                <Text
                  className={`pt-tab ${tab === 'withdrawals' ? 'pt-tab-active' : ''}`}
                  onClick={() => this.handleSwitchTab('withdrawals')}
                >
                  提现记录
                </Text>
              </View>

              {/* Withdrawals List */}
              {tab === 'withdrawals' && (
                <View className='pt-withdrawals'>
                  {withdrawals.length === 0 ? (
                    <View className='pt-empty'>
                      <Text className='pt-empty-text'>暂无提现记录</Text>
                    </View>
                  ) : (
                    withdrawals.map((w: any) => (
                      <View key={w.id} className='pt-wd-item'>
                        <View className='pt-wd-top'>
                          <Text className='pt-wd-amount'>¥{w.amount?.toFixed(2)}</Text>
                          <Text className={`pt-wd-status pt-wd-status-${w.status}`}>
                            {w.status === 'approved' ? '已通过' : w.status === 'pending' ? '审核中' : '已驳回'}
                          </Text>
                        </View>
                        <Text className='pt-wd-time'>{w.created_at}</Text>
                      </View>
                    ))
                  )}
                </View>
              )}

              {/* Earnings Details Placeholder */}
              {tab === 'earnings' && (
                <View className='pt-earnings-detail'>
                  <View className='pt-ed-card'>
                    <Text className='pt-ed-label'>推广订单数</Text>
                    <Text className='pt-ed-value'>{earnings?.order_count || 0} 单</Text>
                  </View>
                  <View className='pt-ed-card'>
                    <Text className='pt-ed-label'>推广码</Text>
                    <Text className='pt-ed-hint' onClick={() => Taro.showToast({ title: '推广码功能待完善', icon: 'none' })}>
                      点击生成推广小程序码
                    </Text>
                  </View>
                </View>
              )}
            </View>
          )}
        </ScrollView>
      </View>
    )
  }
}
