import { Component } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'
import './index.scss'

interface MineState {
  user: any | null
  loading: boolean
}

export default class Mine extends Component<{}, MineState> {
  state: MineState = { user: null, loading: true }

  componentDidMount() {
    this.loadUser()
  }

  componentDidShow() {
    // Reload user info when page shows (in case of login/logout)
    this.loadUser()
  }

  loadUser = () => {
    this.setState({ loading: true })
    const user = Taro.getStorageSync('user')
    this.setState({ user, loading: false })
  }

  handleLogout = () => {
    Taro.removeStorageSync('token')
    Taro.removeStorageSync('user')
    Taro.showToast({ title: '已退出登录', icon: 'success' })
    this.loadUser()
    Taro.navigateTo({ url: '/pages/login/index' })
  }

  render() {
    const { user, loading } = this.state

    if (loading) {
      return (
        <View className='mine'>
          <View className='mine-loading'>
            <View className='mine-skel-avatar' />
            <View className='mine-skel-line w-40' />
            <View className='mine-skel-line w-25' />
          </View>
        </View>
      )
    }

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
          {!user && (
            <Text
              className='user-login-btn'
              onClick={() => Taro.navigateTo({ url: '/pages/login/index' })}
            >
              点击登录
            </Text>
          )}
        </View>

        <View className='menu-section'>
          <View
            className='menu-item'
            onClick={() => Taro.navigateTo({ url: '/pages/orders/index' })}
          >
            <Text>我的订单</Text>
            <Text className='arrow'>&gt;</Text>
          </View>
          <View
            className='menu-item'
            onClick={() => Taro.navigateTo({ url: '/pages/membership/index' })}
          >
            <Text>会员中心</Text>
            <Text className='arrow'>&gt;</Text>
          </View>
          <View
            className='menu-item'
            onClick={() => Taro.navigateTo({ url: '/pages/notifications/index' })}
          >
            <Text>消息通知</Text>
            <Text className='arrow'>&gt;</Text>
          </View>
          <View
            className='menu-item'
            onClick={() => Taro.navigateTo({ url: '/pages/tutorial/index' })}
          >
            <Text>推广教程</Text>
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
