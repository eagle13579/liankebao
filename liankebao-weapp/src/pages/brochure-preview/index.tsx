import { Component } from 'react'
import { View, Text, Button, ScrollView, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import NavBar from '../../components/NavBar'
import FlipBook from '../../components/FlipBook'
import { brochureApi, matchApi } from '../../api/digitalBrochure'
import './index.scss'

interface BrochurePreviewState {
  loading: boolean
  brochure: any | null
  error: string
  isOwner: boolean
  unlocked: boolean
}

export default class BrochurePreview extends Component<{}, BrochurePreviewState> {
  state: BrochurePreviewState = {
    loading: true,
    brochure: null,
    error: '',
    isOwner: false,
    unlocked: false,
  }

  componentDidMount() {
    this.loadBrochure()
  }

  loadBrochure = async () => {
    this.setState({ loading: true, error: '' })
    try {
      const params = Taro.getCurrentInstance()?.router?.params
      const id = params?.id as string

      if (id) {
        // 通过 ID 加载他人画册
        const res: any = await brochureApi.getList({ id })
        if (res?.code === 200 && res.data) {
          this.setState({ brochure: res.data, loading: false, isOwner: false })
        } else {
          this.setState({ loading: false, error: '画册加载失败' })
        }
      } else {
        // 加载自己的画册 - 优先 draftBrochure
        const draft = Taro.getStorageSync('draftBrochure')
        if (draft) {
          this.setState({ brochure: draft, loading: false, isOwner: true })
          Taro.removeStorageSync('draftBrochure')
        } else {
          const res: any = await brochureApi.getMine()
          if (res?.code === 200 && res.data) {
            this.setState({ brochure: res.data, loading: false, isOwner: true })
          } else {
            this.setState({ loading: false, error: res?.message || '暂无画册' })
          }
        }
      }
    } catch (e: any) {
      this.setState({ loading: false, error: e.message || '加载失败' })
    }
  }

  handleShare = () => {
    Taro.showShareMenu({ withShareTicket: true })
  }

  goEdit = () => {
    const { brochure } = this.state
    const url = brochure?.id
      ? `/pages/card-editor/index?editId=${brochure.id}`
      : '/pages/card-editor/index'
    Taro.navigateTo({ url })
  }

  goContact = () => {
    Taro.showToast({ title: '联系功能开发中', icon: 'none' })
  }

  handleUnlock = async () => {
    const user = Taro.getStorageSync('user')
    const level = user?.membership_level || 0
    if (level >= 2) {
      // 黄金及以上直接显示
      this.setState({ unlocked: true })
    } else {
      Taro.showModal({
        title: '解锁联系方式',
        content: '升级黄金会员即可解锁查看对方联系方式',
        confirmText: '去升级',
        success: (res) => {
          if (res.confirm) {
            Taro.navigateTo({ url: '/pages/membership/index' })
          }
        },
      })
    }
  }

  maskPhone = (phone: string) => {
    if (!phone) return ''
    if (this.state.isOwner || this.state.unlocked) return phone
    return phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')
  }

  maskEmail = (email: string) => {
    if (!email) return ''
    if (this.state.isOwner || this.state.unlocked) return email
    const [name, domain] = email.split('@')
    if (!domain) return email
    return name.charAt(0) + '***@' + domain
  }

  maskWechat = (wechat: string) => {
    if (!wechat) return ''
    if (this.state.isOwner || this.state.unlocked) return wechat
    return wechat.length > 2 ? wechat.charAt(0) + '***' + wechat.charAt(wechat.length - 1) : '***'
  }

  getFlipPages() {
    const { brochure, isOwner, unlocked } = this.state
    if (!brochure) return []
    const showContact = isOwner || unlocked
    return [
      {
        type: 'cover' as const,
        data: { ...brochure, purpose: brochure.purpose || '' },
      },
      {
        type: 'contact' as const,
        data: {
          ...brochure,
          phone: showContact ? brochure.phone : this.maskPhone(brochure.phone || ''),
          email: showContact ? brochure.email : this.maskEmail(brochure.email || ''),
          wechat: showContact ? brochure.wechat : this.maskWechat(brochure.wechat || ''),
          masked: !showContact,
        },
      },
      {
        type: 'products' as const,
        data: brochure,
      },
      {
        type: 'company' as const,
        data: brochure,
      },
    ]
  }

  render() {
    const { loading, error, brochure, isOwner } = this.state

    return (
      <View className='preview-page'>
        <NavBar title='画册预览' showBack />

        {loading ? (
          <View className='preview-loading'>
            <View className='skeleton' style={{ width: 80, height: 80, borderRadius: 40, margin: '40px auto 16px' }} />
            <View className='skeleton' style={{ width: '60%', height: 20, margin: '0 auto 8px' }} />
            <View className='skeleton' style={{ width: '90%', height: 300, margin: '40px auto' }} />
          </View>
        ) : error ? (
          <View className='preview-empty'>
            <Text className='empty-icon'>📭</Text>
            <Text className='empty-title'>暂无画册</Text>
            <Text className='empty-desc'>{error}</Text>
            {isOwner ? (
              <Button className='btn-primary' onClick={this.goEdit}>创建画册</Button>
            ) : null}
          </View>
        ) : (
          <ScrollView className='preview-content' scrollY>
            <FlipBook pages={this.getFlipPages()} />

            <View className='page-indicator'>
              {[0, 1, 2, 3].map((i) => (
                <View key={i} className={`dot ${i === 0 ? 'active' : ''}`} />
              ))}
            </View>

            {/* 解锁按钮（非本人 + 已脱敏） */}
            {!isOwner && !this.state.unlocked && brochure?.phone && (
              <View className='unlock-bar'>
                <Text className='unlock-icon'>🔒</Text>
                <Text className='unlock-text'>联系方式已脱敏</Text>
                <Button className='btn-unlock' onClick={this.handleUnlock}>
                  解锁查看
                </Button>
              </View>
            )}

            {/* 底部操作栏 */}
            <View className='preview-actions'>
              <Button className='btn-action' onClick={this.handleShare}>
                📤 分享
              </Button>
              <Button className='btn-action btn-action-primary' onClick={this.goContact}>
                💬 联系我
              </Button>
              {isOwner && (
                <Button className='btn-action' onClick={this.goEdit}>
                  ✏️ 编辑画册
                </Button>
              )}
            </View>

            {brochure?.view_count !== undefined && (
              <View className='preview-stats'>
                <Text className='stats-text'>👁️ {brochure.view_count} 次浏览</Text>
              </View>
            )}
          </ScrollView>
        )}
      </View>
    )
  }
}
