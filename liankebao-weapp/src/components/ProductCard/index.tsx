import { Component } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import './index.scss'

export default class ProductCard extends Component<{ product: any }> {
  handleClick = () => {
    Taro.navigateTo({ url: `/pages/product/index?id=${this.props.product.id}` })
  }

  render() {
    const p = this.props.product
    const img = JSON.parse(p.images || '[]')[0]
    return (
      <View className='card' onClick={this.handleClick}>
        <Image className='thumb' src={img} mode='aspectFill' lazyLoad />
        <View className='body'>
          <Text className='name'>{p.name}</Text>
          <Text className='price'>¥{p.price}</Text>
          {p.earn_per_share > 0 && <Text className='earn'>推广赚 ¥{p.earn_per_share}</Text>}
        </View>
      </View>
    )
  }
}
