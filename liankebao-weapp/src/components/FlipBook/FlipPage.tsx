import { Component } from 'react'
import { View, Text, Image } from '@tarojs/components'
import './FlipPage.scss'

interface FlipPageProps {
  type: 'cover' | 'contact' | 'products' | 'qrcode' | 'company'
  data: any
  isActive: boolean
  position: 'prev' | 'active' | 'next'
}

export default class FlipPage extends Component<FlipPageProps> {
  renderCover() {
    const { data } = this.props
    return (
      <View className='card-inner glass'>
        <View className='fp-avatar'>
          <Text className='fp-avatar-text'>
            {data.name ? data.name.charAt(0) : '?'}
          </Text>
        </View>
        <Text className='fp-name'>{data.name || '未填写'}</Text>
        <Text className='fp-company'>
          {data.company}
          {data.position ? ` · ${data.position}` : ''}
        </Text>
        {data.bio && <Text className='fp-bio'>{data.bio}</Text>}
        {data.purpose && <Text className='fp-purpose'>{data.purpose}</Text>}
        <View className='fp-tags'>
          {data.provide_tags && data.provide_tags.length > 0 && (
            <View className='fp-tag-group'>
              <Text className='tag-label'>我能提供:</Text>
              <View>
                {data.provide_tags.map((tag: string, i: number) => (
                  <Text key={i} className='tag tag-provide'>{tag}</Text>
                ))}
              </View>
            </View>
          )}
          {data.need_tags && data.need_tags.length > 0 && (
            <View className='fp-tag-group'>
              <Text className='tag-label'>我需要:</Text>
              <View>
                {data.need_tags.map((tag: string, i: number) => (
                  <Text key={i} className='tag tag-need'>{tag}</Text>
                ))}
              </View>
            </View>
          )}
        </View>
      </View>
    )
  }

  renderContact() {
    const { data } = this.props
    return (
      <View className='card-inner glass'>
        <Text className='fp-title'>📞 联系方式</Text>
        {data.phone && (
          <View className='contact-item'>
            <Text className='contact-icon'>📞</Text>
            <Text>{data.phone}</Text>
          </View>
        )}
        {data.email && (
          <View className='contact-item'>
            <Text className='contact-icon'>✉️</Text>
            <Text>{data.email}</Text>
          </View>
        )}
        {data.wechat && (
          <View className='contact-item'>
            <Text className='contact-icon'>💬</Text>
            <Text>{data.wechat}</Text>
          </View>
        )}
        {!data.phone && !data.email && !data.wechat && (
          <View className='fp-empty'>
            <Text className='empty-icon'>🔒</Text>
            <Text className='empty-desc'>暂无联系方式</Text>
          </View>
        )}
      </View>
    )
  }

  renderProducts() {
    const { data } = this.props
    return (
      <View className='card-inner glass'>
        <Text className='fp-title'>📸 产品展示</Text>
        {data.images && data.images.length > 0 ? (
          <View className='fp-images'>
            {data.images.map((img: string, i: number) => (
              <Image key={i} className='fp-image' src={img} mode='aspectFill' />
            ))}
          </View>
        ) : (
          <View className='fp-empty'>
            <Text className='empty-icon'>🖼️</Text>
            <Text className='empty-desc'>暂无展示图片</Text>
          </View>
        )}
      </View>
    )
  }

  renderCompany() {
    const { data } = this.props
    return (
      <View className='card-inner glass'>
        <Text className='fp-title'>🏢 企业信息</Text>
        <View className='fp-company-info'>
          <View className='fp-info-row'>
            <Text className='fp-info-label'>公司</Text>
            <Text className='fp-info-value'>{data.company || '未填写'}</Text>
          </View>
          <View className='fp-info-row'>
            <Text className='fp-info-label'>主营</Text>
            <Text className='fp-info-value'>{data.main_business || '未填写'}</Text>
          </View>
          <View className='fp-info-row'>
            <Text className='fp-info-label'>优势</Text>
            <Text className='fp-info-value'>{data.advantage || '未填写'}</Text>
          </View>
        </View>
      </View>
    )
  }

  renderQRCode() {
    const { data } = this.props
    return (
      <View className='card-inner glass'>
        <Text className='fp-title'>📱 扫码加好友</Text>
        <View className='fp-qrcode'>
          <View className='fp-qrcode-placeholder'>
            <Text style={{ fontSize: '64px' }}>📱</Text>
          </View>
          <Text className='fp-qrcode-text'>
            {data.name ? `扫描二维码添加 ${data.name}` : '扫描二维码添加好友'}
          </Text>
        </View>
      </View>
    )
  }

  render() {
    const { type, isActive, position } = this.props

    const classNames = [
      'flip-page',
      isActive ? 'active' : '',
      position === 'prev' ? 'prev' : position === 'next' ? 'next' : '',
    ]
      .filter(Boolean)
      .join(' ')

    const renderers: Record<string, () => React.ReactNode> = {
      cover: this.renderCover,
      contact: this.renderContact,
      products: this.renderProducts,
      company: this.renderCompany,
      qrcode: this.renderQRCode,
    }

    return <View className={classNames}>{renderers[type]?.() || this.renderCover()}</View>
  }
}
