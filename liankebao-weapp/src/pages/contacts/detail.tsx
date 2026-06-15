import { Component } from 'react'
import { View, Text, ScrollView, Image } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './detail.scss'

interface ContactDetailState {
  contact: any | null
  loading: boolean
  error: string
}

export default class ContactDetail extends Component<{}, ContactDetailState> {
  state: ContactDetailState = {
    contact: null,
    loading: true,
    error: '',
  }

  componentDidMount() {
    const { id } = this.$router!.params
    if (id) {
      this.fetchDetail(id)
    } else {
      this.setState({ error: '缺少联系人ID', loading: false })
    }
  }

  fetchDetail = (id: string) => {
    this.setState({ loading: true, error: '' })
    api.get(`/contacts/${id}`)
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ contact: res.data, loading: false })
        } else {
          this.setState({ error: res.message || '联系人不存在', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleCall = (phone: string) => {
    Taro.makePhoneCall({ phoneNumber: phone })
  }

  render() {
    const { contact, loading, error } = this.state

    if (loading) {
      return (
        <View className='cd-page'>
          <View className='cd-header'>
            <Text className='cd-back' onClick={() => Taro.navigateBack()}>←</Text>
            <Text className='cd-title'>联系人详情</Text>
          </View>
          <View className='cd-loading'>
            <View className='cd-skel-avatar-lg' />
            <View className='cd-skel-line w-50' />
            <View className='cd-skel-line w-30' />
            <View className='cd-skel-card-lg' />
          </View>
        </View>
      )
    }

    if (error) {
      return (
        <View className='cd-page'>
          <View className='cd-header'>
            <Text className='cd-back' onClick={() => Taro.navigateBack()}>←</Text>
            <Text className='cd-title'>联系人详情</Text>
          </View>
          <View className='cd-error'>
            <Text className='cd-error-icon'>⚠</Text>
            <Text className='cd-error-text'>{error}</Text>
            <Text className='cd-error-retry' onClick={() => {
              const { id } = this.$router!.params
              if (id) this.fetchDetail(id)
            }}>点击重试</Text>
          </View>
        </View>
      )
    }

    if (!contact) {
      return (
        <View className='cd-page'>
          <View className='cd-header'>
            <Text className='cd-back' onClick={() => Taro.navigateBack()}>←</Text>
            <Text className='cd-title'>联系人不存在</Text>
          </View>
          <View className='cd-empty'>
            <Text className='cd-empty-icon'>👤</Text>
            <Text className='cd-empty-text'>该联系人不存在或已被删除</Text>
          </View>
        </View>
      )
    }

    return (
      <View className='cd-page'>
        <View className='cd-header'>
          <Text className='cd-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='cd-title'>联系人详情</Text>
        </View>

        <ScrollView className='cd-body' scrollY>
          {/* User profile */}
          <View className='cd-profile'>
            <View className='cd-avatar-lg'>
              {contact.avatar ? (
                <Image className='cd-avatar-img-lg' src={contact.avatar} mode='aspectFill' lazyLoad />
              ) : (
                <Text className='cd-avatar-text-lg'>
                  {contact.name?.[0] || '?'}
                </Text>
              )}
            </View>
            <Text className='cd-profile-name'>{contact.name}</Text>
            {contact.position && (
              <Text className='cd-profile-position'>{contact.position}</Text>
            )}
          </View>

          {/* Contact info card */}
          <View className='cd-info-card'>
            <Text className='cd-info-title'>基本信息</Text>
            <View className='cd-info-row'>
              <Text className='cd-info-label'>📞 电话</Text>
              {contact.phone ? (
                <Text className='cd-info-value cd-info-phone' onClick={() => this.handleCall(contact.phone)}>
                  {contact.phone}
                </Text>
              ) : (
                <Text className='cd-info-value cd-info-na'>未填写</Text>
              )}
            </View>
            <View className='cd-info-row'>
              <Text className='cd-info-label'>🏢 公司</Text>
              <Text className='cd-info-value'>{contact.company || '未填写'}</Text>
            </View>
            <View className='cd-info-row'>
              <Text className='cd-info-label'>💼 职位</Text>
              <Text className='cd-info-value'>{contact.position || '未填写'}</Text>
            </View>
            <View className='cd-info-row'>
              <Text className='cd-info-label'>📧 邮箱</Text>
              <Text className='cd-info-value'>{contact.email || '未填写'}</Text>
            </View>
            <View className='cd-info-row cd-info-row-last'>
              <Text className='cd-info-label'>📍 地址</Text>
              <Text className='cd-info-value'>{contact.address || '未填写'}</Text>
            </View>
          </View>

          {/* Tags */}
          {contact.tags && contact.tags.length > 0 && (
            <View className='cd-tags-card'>
              <Text className='cd-info-title'>标签</Text>
              <View className='cd-tags-list'>
                {contact.tags.map((tag: string, i: number) => (
                  <Text key={i} className='cd-tag-item'>{tag}</Text>
                ))}
              </View>
            </View>
          )}

          {/* Notes */}
          {contact.notes && (
            <View className='cd-notes-card'>
              <Text className='cd-info-title'>备注</Text>
              <Text className='cd-notes-text'>{contact.notes}</Text>
            </View>
          )}

          {/* Timestamps */}
          <View className='cd-timestamps'>
            <Text className='cd-ts-item'>创建时间：{contact.created_at ? new Date(contact.created_at).toLocaleString('zh-CN') : '未知'}</Text>
            {contact.updated_at && (
              <Text className='cd-ts-item'>更新时间：{new Date(contact.updated_at).toLocaleString('zh-CN')}</Text>
            )}
          </View>

          {/* Action buttons */}
          <View className='cd-actions'>
            {contact.phone && (
              <View className='cd-action-btn cd-action-call' onClick={() => this.handleCall(contact.phone)}>
                <Text>📞 拨打电话</Text>
              </View>
            )}
            <View
              className='cd-action-btn cd-action-edit'
              onClick={() => Taro.navigateTo({ url: `/pages/contacts/detail?id=${contact.id}&edit=1` })}
            >
              <Text>✏️ 编辑资料</Text>
            </View>
          </View>
        </ScrollView>
      </View>
    )
  }
}
