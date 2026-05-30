import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface DashboardData {
  total_users: number
  total_products: number
  total_orders: number
  total_revenue: number
  today_orders: number
  pending_review_products: number
  pending_withdrawals: number
}

interface AdminState {
  dashboard: DashboardData | null
  loading: boolean
  error: string
}

export default class AdminIndex extends Component<{}, AdminState> {
  state: AdminState = {
    dashboard: null,
    loading: true,
    error: '',
  }

  componentDidMount() {
    this.fetchDashboard()
  }

  fetchDashboard = () => {
    this.setState({ loading: true, error: '' })
    api.get('/admin/dashboard')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ dashboard: res.data, loading: false })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleNavigate = (url: string) => {
    Taro.navigateTo({ url })
  }

  render() {
    const { dashboard, loading, error } = this.state

    return (
      <View className='admin'>
        {/* Header */}
        <View className='ad-header'>
          <Text className='ad-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='ad-title'>管理后台</Text>
        </View>

        <ScrollView className='ad-body' scrollY>
          {loading ? (
            <View className='ad-loading'>
              <View className='ad-skel-grid'>
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <View key={i} className='ad-skel-card' />
                ))}
              </View>
            </View>
          ) : error ? (
            <View className='ad-error'>
              <Text className='ad-error-icon'>⚠️</Text>
              <Text className='ad-error-text'>{error}</Text>
              <Text className='ad-error-retry' onClick={this.fetchDashboard}>点击重试</Text>
            </View>
          ) : (
            <View>
              {/* Dashboard Stats */}
              <View className='ad-stats-grid'>
                <View className='ad-stat-card ad-stat-blue'>
                  <Text className='ad-stat-icon'>👥</Text>
                  <Text className='ad-stat-value'>{dashboard?.total_users || 0}</Text>
                  <Text className='ad-stat-label'>总用户数</Text>
                </View>
                <View className='ad-stat-card ad-stat-green'>
                  <Text className='ad-stat-icon'>📦</Text>
                  <Text className='ad-stat-value'>{dashboard?.total_products || 0}</Text>
                  <Text className='ad-stat-label'>总产品数</Text>
                </View>
                <View className='ad-stat-card ad-stat-amber'>
                  <Text className='ad-stat-icon'>📋</Text>
                  <Text className='ad-stat-value'>{dashboard?.total_orders || 0}</Text>
                  <Text className='ad-stat-label'>总订单数</Text>
                </View>
                <View className='ad-stat-card ad-stat-violet'>
                  <Text className='ad-stat-icon'>💰</Text>
                  <Text className='ad-stat-value'>¥{dashboard?.total_revenue?.toFixed(2) || '0.00'}</Text>
                  <Text className='ad-stat-label'>总营收</Text>
                </View>
                <View className='ad-stat-card ad-stat-sky'>
                  <Text className='ad-stat-icon'>🛒</Text>
                  <Text className='ad-stat-value'>{dashboard?.today_orders || 0}</Text>
                  <Text className='ad-stat-label'>今日订单</Text>
                </View>
                <View className='ad-stat-card ad-stat-rose'>
                  <Text className='ad-stat-icon'>⏳</Text>
                  <Text className='ad-stat-value'>{dashboard?.pending_review_products || 0}</Text>
                  <Text className='ad-stat-label'>待审核产品</Text>
                </View>
              </View>

              {/* Quick Actions */}
              <View className='ad-section'>
                <Text className='ad-section-title'>快捷操作</Text>
                <View className='ad-actions'>
                  <View
                    className='ad-action-card'
                    onClick={() => this.handleNavigate('/pages/admin/users')}
                  >
                    <Text className='ad-action-icon'>👥</Text>
                    <Text className='ad-action-label'>用户管理</Text>
                    <Text className='ad-action-arrow'>›</Text>
                  </View>
                  <View
                    className='ad-action-card'
                    onClick={() => this.handleNavigate('/pages/admin/products')}
                  >
                    <Text className='ad-action-icon'>📦</Text>
                    <Text className='ad-action-label'>产品审核</Text>
                    {dashboard && dashboard.pending_review_products > 0 && (
                      <Text className='ad-action-badge'>{dashboard.pending_review_products}</Text>
                    )}
                    <Text className='ad-action-arrow'>›</Text>
                  </View>
                  <View
                    className='ad-action-card'
                    onClick={() => this.handleNavigate('/pages/admin/withdrawals')}
                  >
                    <Text className='ad-action-icon'>💳</Text>
                    <Text className='ad-action-label'>提现审核</Text>
                    {dashboard && dashboard.pending_withdrawals > 0 && (
                      <Text className='ad-action-badge'>{dashboard.pending_withdrawals}</Text>
                    )}
                    <Text className='ad-action-arrow'>›</Text>
                  </View>
                  <View
                    className='ad-action-card'
                    onClick={() => this.handleNavigate('/pages/admin/orders')}
                  >
                    <Text className='ad-action-icon'>📋</Text>
                    <Text className='ad-action-label'>订单管理</Text>
                    <Text className='ad-action-arrow'>›</Text>
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
