import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface NotificationItem {
  id: number
  title: string
  content: string
  is_read: boolean
  created_at: string
  type?: string
}

interface NotificationsState {
  notifications: NotificationItem[]
  loading: boolean
  error: string
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMs / 3600000)
  const diffDay = Math.floor(diffMs / 86400000)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  if (diffHour < 24) return `${diffHour}小时前`
  if (diffDay < 7) return `${diffDay}天前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

export default class NotificationsIndex extends Component<{}, NotificationsState> {
  state: NotificationsState = {
    notifications: [],
    loading: true,
    error: '',
  }

  componentDidMount() {
    this.fetchNotifications()
  }

  fetchNotifications = () => {
    this.setState({ loading: true, error: '' })
    api.get('/notifications')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ notifications: res.data.items || res.data, loading: false })
        } else {
          this.setState({ error: res.message || '获取通知失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  markAsRead = (id: number) => {
    api.put(`/notifications/${id}/read`, {})
      .then(() => {
        this.setState((prev) => ({
          notifications: prev.notifications.map((n) =>
            n.id === id ? { ...n, is_read: true } : n
          ),
        }))
      })
      .catch(() => {})
  }

  render() {
    const { notifications, loading, error } = this.state
    const unreadCount = notifications.filter((n) => !n.is_read).length

    return (
      <View className='notifications'>
        {/* Header */}
        <View className='nf-header'>
          <View className='nf-header-left'>
            <Text className='nf-back' onClick={() => Taro.navigateBack()}>←</Text>
            <View className='nf-header-info'>
              <View className='nf-header-icon-wrap'>
                <Text className='nf-header-icon'>🔔</Text>
              </View>
              <Text className='nf-header-title'>消息中心</Text>
            </View>
          </View>
          {unreadCount > 0 && (
            <View className='nf-unread-badge'>
              <Text className='nf-unread-text'>{unreadCount}条未读</Text>
            </View>
          )}
        </View>

        {/* Content */}
        <ScrollView className='nf-body' scrollY>
          {loading ? (
            <View className='nf-loading'>
              {[1, 2, 3, 4].map((i) => (
                <View key={i} className='nf-skel-card'>
                  <View className='nf-skel-icon' />
                  <View className='nf-skel-body'>
                    <View className='nf-skel-line w-60' />
                    <View className='nf-skel-line w-90' />
                    <View className='nf-skel-line w-30' />
                  </View>
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='nf-error'>
              <Text className='nf-error-icon'>⚠️</Text>
              <Text className='nf-error-text'>{error}</Text>
              <Text className='nf-error-retry' onClick={this.fetchNotifications}>重新加载</Text>
            </View>
          ) : notifications.length === 0 ? (
            <View className='nf-empty'>
              <Text className='nf-empty-icon'>🔕</Text>
              <Text className='nf-empty-text'>暂无消息</Text>
              <Text className='nf-empty-hint'>当有新的通知时，会在这里显示</Text>
            </View>
          ) : (
            <View className='nf-list'>
              {notifications.map((item) => (
                <View
                  key={item.id}
                  className={`nf-card ${item.is_read ? 'nf-card-read' : 'nf-card-unread'}`}
                  onClick={() => !item.is_read && this.markAsRead(item.id)}
                >
                  <View className='nf-card-inner'>
                    {/* Icon */}
                    <View className={`nf-card-icon-wrap ${item.is_read ? 'nf-card-icon-read' : 'nf-card-icon-unread'}`}>
                      <Text className='nf-card-icon'>{item.is_read ? '📨' : '🔔'}</Text>
                    </View>

                    {/* Content */}
                    <View className='nf-card-content'>
                      <View className='nf-card-top'>
                        <Text className={`nf-card-title ${item.is_read ? 'nf-card-title-read' : ''}`}>
                          {item.title}
                        </Text>
                        {!item.is_read && <View className='nf-card-dot' />}
                      </View>
                      <Text className={`nf-card-desc ${item.is_read ? 'nf-card-desc-read' : ''}`}>
                        {item.content}
                      </Text>
                      <View className='nf-card-meta'>
                        <Text className='nf-card-time'>{formatTime(item.created_at)}</Text>
                        {item.is_read && (
                          <Text className='nf-card-read-tag'>✅ 已读</Text>
                        )}
                      </View>
                    </View>
                  </View>
                </View>
              ))}
            </View>
          )}
        </ScrollView>
      </View>
    )
  }
}
