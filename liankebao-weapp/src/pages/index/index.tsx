import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import ProductCard from '../../components/ProductCard'
import Taro from '@tarojs/taro'
import './index.scss'

interface IndexState {
  products: any[]
  loading: boolean
  error: string
}

export default class Index extends Component<{}, IndexState> {
  state: IndexState = {
    products: [],
    loading: true,
    error: '',
  }

  componentDidMount() {
    this.fetchProducts()
  }

  fetchProducts = () => {
    this.setState({ loading: true, error: '' })
    api.get('/products')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ products: res.data.items || [], loading: false })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  render() {
    const { products, loading, error } = this.state
    return (
      <View className='index'>
        <View className='header'>
          <Text className='logo'>链客宝</Text>
          <Text className='subtitle'>企业家的AI营销朋友圈</Text>
        </View>
        <ScrollView className='product-list' scrollY>
          {loading ? (
            <View className='hp-loading'>
              {[1, 2, 3, 4].map((i) => (
                <View key={i} className='hp-skel-card'>
                  <View className='hp-skel-thumb' />
                  <View className='hp-skel-body'>
                    <View className='hp-skel-line w-60' />
                    <View className='hp-skel-line w-40' />
                  </View>
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='hp-error'>
              <Text className='hp-error-icon'>⚠️</Text>
              <Text className='hp-error-text'>{error}</Text>
              <Text className='hp-error-retry' onClick={this.fetchProducts}>点击重试</Text>
            </View>
          ) : products.length === 0 ? (
            <View className='hp-empty'>
              <Text className='hp-empty-icon'>📦</Text>
              <Text className='hp-empty-text'>暂无产品</Text>
              <Text className='hp-empty-hint'>新产品上架后将在这里展示</Text>
            </View>
          ) : (
            products.map((p: any) => <ProductCard key={p.id} product={p} />)
          )}
        </ScrollView>
      </View>
    )
  }
}
