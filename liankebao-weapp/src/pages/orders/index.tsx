import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

export default class Orders extends Component {
  state = { orders: [], loading: true }

  componentDidMount() {
    const token = Taro.getStorageSync('token')
    if (!token) {
      Taro.navigateTo({ url: '/pages/login/index' })
      return
    }
    api.get('/orders').then((res: any) => {
      this.setState({ orders: res.data?.items || [], loading: false })
    })
  }

  handleConfirm = (orderId: number) => {
    api.put(`/orders/${orderId}/status`, { status: 'received' }).then((res: any) => {
      if (res.code === 200) {
        Taro.showToast({ title: '已确认收货', icon: 'success' })
        this.componentDidMount()
      }
    })
  }

  render() {
    const { orders, loading } = this.state
    return (
      <View className='orders'>
        <View className='header'>
          <Text>我的订单</Text>
        </View>
        <ScrollView scrollY className='order-list'>
          {loading ? (
            <Text className='loading'>加载中...</Text>
          ) : orders.length === 0 ? (
            <Text className='empty'>暂无订单</Text>
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
