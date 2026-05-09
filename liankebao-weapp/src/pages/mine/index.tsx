import { Component } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'
import './index.scss'

export default class Mine extends Component {
  state = { user: null as any }

  componentDidMount() {
    const user = Taro.getStorageSync('user')
    this.setState({ user })
  }

  handleLogout = () => {
    Taro.removeStorageSync('token')
    Taro.removeStorageSync('user')
    Taro.navigateTo({ url: '/pages/login/index' })
  }

  render() {
    const { user } = this.state
    return (
      <View className='mine'>
        <View className='user-section'>
          <View className='avatar'>
            <Text className='avatar-text'>
              {user?.name ? user.name.charAt(0).toUpperCase() : '?'}
            </Text>
          </View>
          <Text className='user-name'>{user?.name || '未登录'}</Text>
          <Text className='user-role'>
            {user?.role === 'promoter'
              ? '推广员'
              : user?.role === 'supplier'
              ? '产品方'
              : '普通用户'}
          </Text>
        </View>

        <View className='menu-section'>
          <View
            className='menu-item'
            onClick={() => Taro.navigateTo({ url: '/pages/orders/index' })}
          >
            <Text>我的订单</Text>
            <Text className='arrow'>&gt;</Text>
          </View>
          {user?.role === 'promoter' && (
            <View className='menu-item'>
              <Text>推广收益</Text>
              <Text className='arrow'>&gt;</Text>
            </View>
          )}
          {user?.role === 'supplier' && (
            <View className='menu-item'>
              <Text>产品管理</Text>
              <Text className='arrow'>&gt;</Text>
            </View>
          )}
        </View>

        {user && (
          <Button className='logout-btn' onClick={this.handleLogout}>
            退出登录
          </Button>
        )}
      </View>
    )
  }
}
