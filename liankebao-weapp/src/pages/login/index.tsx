import { Component } from 'react'
import { View, Text, Button } from '@tarojs/components'
import { loginWithWechat } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

export default class Login extends Component {
  handleWechatLogin = async () => {
    try {
      await loginWithWechat()
      Taro.showToast({ title: '登录成功', icon: 'success' })
      Taro.switchTab({ url: '/pages/index/index' })
    } catch (e) {
      Taro.showToast({ title: '登录失败', icon: 'error' })
    }
  }

  render() {
    return (
      <View className='login'>
        <View className='brand'>
          <Text className='logo'>链客宝</Text>
          <Text className='desc'>企业家专属供需匹配平台</Text>
        </View>
        <Button className='wechat-btn' openType='getUserInfo' onClick={this.handleWechatLogin}>
          微信一键登录
        </Button>
      </View>
    )
  }
}
