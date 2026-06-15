import { Component } from 'react'
import { View, Text, Image, Button } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface ProductDetailState {
  product: any | null
  loading: boolean
  error: string
}

export default class ProductDetail extends Component<{}, ProductDetailState> {
  state: ProductDetailState = {
    product: null,
    loading: true,
    error: '',
  }

  componentDidMount() {
    const { id } = this.$router!.params
    if (id) {
      this.fetchProduct(id)
    } else {
      this.setState({ error: '缺少产品ID', loading: false })
    }
  }

  fetchProduct = (id: string) => {
    this.setState({ loading: true, error: '' })
    api.get(`/products/${id}`)
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ product: res.data, loading: false })
        } else {
          this.setState({ error: res.message || '产品不存在', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
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
    const { product, loading, error } = this.state

    if (loading) {
      return (
        <View className='pd-page'>
          <View className='pd-header'>
            <Text className='pd-back' onClick={() => Taro.navigateBack()}>←</Text>
            <Text className='pd-title'>产品详情</Text>
          </View>
          <View className='pd-loading'>
            <View className='pd-skel-cover' />
            <View className='pd-skel-body'>
              <View className='pd-skel-line w-60' />
              <View className='pd-skel-line w-30' />
              <View className='pd-skel-line w-40' />
              <View className='pd-skel-line w-90' />
              <View className='pd-skel-line w-80' />
            </View>
          </View>
        </View>
      )
    }

    if (error) {
      return (
        <View className='pd-page'>
          <View className='pd-header'>
            <Text className='pd-back' onClick={() => Taro.navigateBack()}>←</Text>
            <Text className='pd-title'>产品详情</Text>
          </View>
          <View className='pd-error'>
            <Text className='pd-error-icon'>⚠️</Text>
            <Text className='pd-error-text'>{error}</Text>
            <Text className='pd-error-retry' onClick={() => {
              const { id } = this.$router!.params
              if (id) this.fetchProduct(id)
            }}>点击重试</Text>
          </View>
        </View>
      )
    }

    if (!product) {
      return (
        <View className='pd-page'>
          <View className='pd-header'>
            <Text className='pd-back' onClick={() => Taro.navigateBack()}>←</Text>
            <Text className='pd-title'>产品不存在</Text>
          </View>
          <View className='pd-empty'>
            <Text className='pd-empty-icon'>📦</Text>
            <Text className='pd-empty-text'>该产品不存在或已被删除</Text>
          </View>
        </View>
      )
    }

    return (
      <View className='pd-page'>
        <View className='pd-header'>
          <Text className='pd-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='pd-title'>产品详情</Text>
        </View>
        <Image className='pd-cover' src={JSON.parse(product.images || '[]')[0]} mode='aspectFill' lazyLoad />
        <View className='pd-info'>
          <Text className='pd-name'>{product.name}</Text>
          <Text className='pd-price'>¥{product.price}</Text>
          {product.earn_per_share > 0 && (
            <Text className='pd-earn'>推广赚 ¥{product.earn_per_share}</Text>
          )}
          <Text className='pd-desc'>{product.description}</Text>
        </View>
        <Button className='pd-buy-btn' onClick={this.handleBuy}>
          立即购买
        </Button>
      </View>
    )
  }
}
