import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import ProductCard from '../../components/ProductCard'
import './index.scss'

export default class Index extends Component {
  state = { products: [], loading: true }

  componentDidMount() {
    api.get('/products').then((res: any) => {
      this.setState({ products: res.data?.items || [], loading: false })
    })
  }

  render() {
    const { products, loading } = this.state
    return (
      <View className='index'>
        <View className='header'>
          <Text className='logo'>链客宝</Text>
          <Text className='subtitle'>企业家的AI营销朋友圈</Text>
        </View>
        <ScrollView className='product-list' scrollY>
          {loading ? (
            <Text className='loading'>加载中...</Text>
          ) : (
            products.map((p: any) => <ProductCard key={p.id} product={p} />)
          )}
        </ScrollView>
      </View>
    )
  }
}
