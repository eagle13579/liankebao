import { Component } from 'react'
import { View, Text, ScrollView, Button, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import NavBar from '../../components/NavBar'
import FlipBook from '../../components/FlipBook'
import { brochureApi, userApi } from '../../api/digitalBrochure'
import './index.scss'

interface IndexState {
  loading: boolean
  error: string
  brochure: any | null
  hasBrochure: boolean
  isSelf: boolean
  isLoggedIn: boolean
}

export default class Index extends Component<{}, IndexState> {
  state: IndexState = {
    loading: true,
    error: '',
    brochure: null,
    hasBrochure: false,
    isSelf: true,
    isLoggedIn: false,
  }

  componentDidMount() {
    this.checkAuth()
  }

  componentDidShow() {
    // 每次显示时刷新
    this.checkAuth()
  }

  checkAuth = () => {
    const token = Taro.getStorageSync('token')
    if (token) {
      this.setState({ isLoggedIn: true })
      this.loadBrochure()
    } else {
      this.setState({ loading: false, isLoggedIn: false, hasBrochure: false })
    }
  }

  loadBrochure = async () => {
    this.setState({ loading: true, error: '' })
    try {
      const res: any = await brochureApi.getMine()
      if (res && res.code === 200 && res.data) {
        this.setState({
          brochure: res.data,
          hasBrochure: true,
          loading: false,
        })
      } else {
        this.setState({
          hasBrochure: false,
          loading: false,
          error: res?.message || '',
        })
      }
    } catch (e: any) {
      this.setState({
        loading: false,
        error: e.message || '加载失败',
        hasBrochure: false,
      })
    }
  }

  goEdit = () => {
    const { brochure } = this.state
    const url = brochure?.id
      ? `/pages/card-editor/index?editId=${brochure.id}`
      : '/pages/card-editor/index'
    Taro.navigateTo({ url })
  }

  goLogin = () => {
    Taro.navigateTo({ url: '/pages/login/index' })
  }

  handleShare = () => {
    Taro.showShareMenu({
      withShareTicket: true,
    })
  }

  goMatch = () => {
    Taro.switchTab({ url: '/pages/card-match/index' })
  }

  onShareAppMessage() {
    const { brochure } = this.state
    return {
      title: brochure?.name ? `${brochure.name} 的数字名片` : 'AI数字名片',
      path: '/pages/index/index',
    }
  }

  getFlipPages() {
    const { brochure } = this.state
    if (!brochure) return []

    return [
      {
        type: 'cover' as const,
        data: brochure,
      },
      {
        type: 'contact' as const,
        data: brochure,
      },
      {
        type: 'products' as const,
        data: brochure,
      },
      {
        type: 'company' as const,
        data: brochure,
      },
      {
        type: 'qrcode' as const,
        data: brochure,
      },
    ]
  }

  render() {
    const { loading, error, hasBrochure, brochure, isLoggedIn } = this.state

    return (
      <View className='home-page'>
        <NavBar
          title='AI数字名片'
          rightContent={
            <Text className='navbar-share' onClick={this.handleShare}>
              📤
            </Text>
          }
        />

        {!isLoggedIn ? (
          /* 未登录引导页 */
          <ScrollView className='home-content' scrollY>
            <View className='home-guide'>
              <View className='guide-hero'>
                <View className='guide-logo'>
                  <Text className='guide-logo-text'>AI</Text>
                </View>
                <Text className='guide-title'>AI数字名片</Text>
                <Text className='guide-subtitle'>让AI为您连接商业机会</Text>
              </View>

              <View className='guide-features'>
                <View className='guide-feature glass'>
                  <Text className='feature-icon'>📇</Text>
                  <Text className='feature-title'>智能名片</Text>
                  <Text className='feature-desc'>3D翻页电子画册，展示个人与企业形象</Text>
                </View>
                <View className='guide-feature glass'>
                  <Text className='feature-icon'>🤝</Text>
                  <Text className='feature-title'>供需匹配</Text>
                  <Text className='feature-desc'>AI智能分析，精准匹配商业伙伴</Text>
                </View>
                <View className='guide-feature glass'>
                  <Text className='feature-icon'>🔗</Text>
                  <Text className='feature-title'>一键分享</Text>
                  <Text className='feature-desc'>微信生态直达，快速拓展人脉</Text>
                </View>
              </View>

              <View className='guide-actions'>
                <Button className='btn-primary guide-login-btn' onClick={this.goLogin}>
                  微信一键登录
                </Button>
                <Text className='guide-note'>登录即表示同意《用户协议》和《隐私政策》</Text>
              </View>
            </View>
          </ScrollView>
        ) : loading ? (
          /* 加载骨架屏 */
          <View className='home-loading'>
            <View className='skeleton' style={{ width: 80, height: 80, borderRadius: 40, margin: '40px auto 16px' }} />
            <View className='skeleton' style={{ width: '60%', height: 20, margin: '0 auto 8px' }} />
            <View className='skeleton' style={{ width: '40%', height: 16, margin: '0 auto 24px' }} />
            <View className='skeleton' style={{ width: '90%', height: 300, margin: '0 auto' }} />
          </View>
        ) : !hasBrochure ? (
          /* 已登录但无画册 */
          <View className='home-empty'>
            <Text className='empty-icon'>📇</Text>
            <Text className='empty-title'>创建您的数字名片</Text>
            <Text className='empty-desc'>让AI为您连接商业机会</Text>
            <Button className='btn-primary' onClick={this.goEdit}>
              创建名片
            </Button>
          </View>
        ) : (
          /* 已登录有画册 - 展示翻页 */
          <ScrollView className='home-content' scrollY>
            <View className='home-hero'>
              <View className='home-hero-avatar'>
                <Text className='home-hero-avatar-text'>
                  {brochure?.name ? brochure.name.charAt(0) : '?'}
                </Text>
              </View>
              <Text className='home-hero-name'>{brochure?.name || '我的名片'}</Text>
              <Text className='home-hero-company'>
                {brochure?.company || ''}
                {brochure?.company && brochure?.position ? ' · ' : ''}
                {brochure?.position || ''}
              </Text>
            </View>

            <FlipBook pages={this.getFlipPages()} />

            <View className='page-indicator'>
              {[0, 1, 2, 3, 4].map((i) => (
                <View
                  key={i}
                  className={`dot ${i === 0 ? 'active' : ''}`}
                />
              ))}
            </View>

            <View className='home-actions'>
              <Button className='btn-action btn-action-primary' onClick={this.handleShare}>
                📤 分享名片
              </Button>
              <Button className='btn-action' onClick={this.goMatch}>
                🤝 去匹配
              </Button>
              {brochure && (
                <Button className='btn-action' onClick={this.goEdit}>
                  ✏️ 编辑画册
                </Button>
              )}
            </View>

            {brochure && (
              <View className='home-stats'>
                <Text className='stats-text'>👁️ {brochure.view_count || 0} 次浏览</Text>
              </View>
            )}
          </ScrollView>
        )}
      </View>
    )
  }
}
