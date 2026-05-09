import { Component } from 'react'
import { View, Text, Image, Button } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

export default class ProductDetail extends Component {
  state = { product: null as any, loading: true }

  componentDidMount() {
    const { id } = this.$router.params
    api.get(`/products/${id}`).then((res: any) => {
      this.setState({ product: res.data, loading: false })
    })
  }

  handleBuy = () => {
    const token = Taro.getStorageSync('token')
    if (!token) {
      Taro.navigateTo({ url: '/pages/login/index' })
      return
    }
    api.post('/orders', { product_id: this.state.product.id, quantity: 1 }).then((res: any) => {
      if (res.code === 200) {
        Taro.showToast({ title: '下单成功', icon: 'success' })
        Taro.navigateTo({ url: '/pages/orders/index' })
      } else {
        Taro.showToast({ title: res.message || '下单失败', icon: 'error' })
      }
    })
  }

  render() {
    const { product, loading } = this.state
    if (loading) return <View className='loading'>加载中...</View>
    if (!product) return <View className='empty'>产品不存在</View>

    return (
      <View className='detail'>
        <Image className='cover' src={JSON.parse(product.images || '[]')[0]} mode='aspectFill' />
        <View className='info'>
          <Text className='name'>{product.name}</Text>
          <Text className='price'>¥{product.price}</Text>
          {product.earn_per_share > 0 && (
            <Text className='earn'>推广赚 ¥{product.earn_per_share}</Text>
          )}
          <Text className='desc'>{product.description}</Text>
        </View>
        <Button className='buy-btn' onClick={this.handleBuy}>
          立即购买
        </Button>
      </View>
    )
  }
}
