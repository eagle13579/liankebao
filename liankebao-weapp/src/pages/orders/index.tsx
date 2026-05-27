import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface OrdersState {
  orders: any[]
  loading: boolean
  error: string
}

export default class Orders extends Component<{}, OrdersState> {
  state: OrdersState = {
    orders: [],
    loading: true,
    error: '',
  }

  componentDidMount() {
    const token = Taro.getStorageSync('token')
    if (!token) {
      Taro.navigateTo({ url: '/pages/login/index' })
      return
    }
    this.fetchOrders()
  }

  fetchOrders = () => {
    this.setState({ loading: true, error: '' })
    api.get('/orders')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ orders: res.data.items || [], loading: false })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleConfirm = (orderId: number) => {
    api.put(`/orders/${orderId}/status`, { status: 'received' }).then((res: any) => {
      if (res.code === 200) {
        Taro.showToast({ title: '已确认收货', icon: 'success' })
        this.fetchOrders()
      }
    })
  }

  render() {
    const { orders, loading, error } = this.state
    return (
      <View className='orders'>
        <View className='header'>
          <Text className='header-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='header-title'>我的订单</Text>
        </View>
        <ScrollView scrollY className='order-list'>
          {loading ? (
            <View className='od-loading'>
              {[1, 2, 3].map((i) => (
                <View key={i} className='od-skel-card'>
                  <View className='od-skel-line w-50' />
                  <View className='od-skel-line w-30' />
                  <View className='od-skel-line w-70' />
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='od-error'>
              <Text className='od-error-icon'>⚠️</Text>
              <Text className='od-error-text'>{error}</Text>
              <Text className='od-error-retry' onClick={this.fetchOrders}>点击重试</Text>
            </View>
          ) : orders.length === 0 ? (
            <View className='od-empty'>
              <Text className='od-empty-icon'>📋</Text>
              <Text className='od-empty-text'>暂无订单</Text>
              <Text className='od-empty-hint'>去逛逛，发现更多优质产品</Text>
            </View>
          ) : (
            orders.map((o: any) => (
              <View key={o.id} className='order-card'>
                <View className='order-top'>
                  <Text className='order-name'>{o.product?.name}</Text>
                  <Text className='order-status'>{o.status}</Text>
                </View>
                <View className='order-body'>
                  <Text className='order-price'>
                    ¥{o.total_price} × {o.quantity}
                  </Text>
                  {o.status === 'paid' && (
                    <Text className='confirm-btn' onClick={() => this.handleConfirm(o.id)}>
                      确认收货
                    </Text>
                  )}
                </View>
              </View>
            ))
          )}
        </ScrollView>
      </View>
    )
  }
}
