import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface Activity {
  id: number
  action_type: string
  summary: string
  detail: string
  created_at: string
}

interface ActivitiesState {
  activities: Activity[]
  loading: boolean
  error: string
  total: number
  page: number
}

const ACTION_LABELS: Record<string, string> = {
  note: '备注',
  call: '电话',
  meeting: '会议',
  email: '邮件',
  wechat: '微信',
  order: '订单',
  import: '导入',
}

const ACTION_ICONS: Record<string, string> = {
  note: '📝',
  call: '📞',
  meeting: '🤝',
  email: '📧',
  wechat: '💬',
  order: '📦',
  import: '📥',
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  return d.toLocaleDateString('zh-CN')
}

export default class ActivitiesIndex extends Component<{}, ActivitiesState> {
  state: ActivitiesState = {
    activities: [],
    loading: true,
    error: '',
    total: 0,
    page: 1,
  }

  componentDidMount() {
    this.fetchActivities()
  }

  fetchActivities = () => {
    const { page } = this.state
    this.setState({ loading: true, error: '' })

    api.get(`/contacts/activities?page=${page}&page_size=20`)
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({
            activities: res.data.items || [],
            total: res.data.total || 0,
            loading: false,
          })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleLoadMore = () => {
    this.setState((prev) => ({ page: prev.page + 1 }), () => this.fetchActivities())
  }

  render() {
    const { activities, loading, error, total, page } = this.state
    const pageSize = 20

    return (
      <View className='activities'>
        {/* Header */}
        <View className='ac-header'>
          <Text className='ac-back' onClick={() => Taro.navigateBack()}>←</Text>
          <View className='ac-header-info'>
            <Text className='ac-header-title'>活动时间线</Text>
            <Text className='ac-header-sub'>联系人互动记录</Text>
          </View>
        </View>

        <ScrollView className='ac-body' scrollY>
          {loading ? (
            <View className='ac-loading'>
              {[1, 2, 3, 4].map((i) => (
                <View key={i} className='ac-skel-item'>
                  <View className='ac-skel-dot' />
                  <View className='ac-skel-lines'>
                    <View className='ac-skel-line w-60' />
                    <View className='ac-skel-line w-40' />
                  </View>
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='ac-error'>
              <Text className='ac-error-icon'>⚠️</Text>
              <Text className='ac-error-text'>{error}</Text>
              <Text className='ac-error-retry' onClick={this.fetchActivities}>点击重试</Text>
            </View>
          ) : activities.length === 0 ? (
            <View className='ac-empty'>
              <Text className='ac-empty-icon'>📋</Text>
              <Text className='ac-empty-text'>暂无活动记录</Text>
              <Text className='ac-empty-hint'>联系人的互动记录将显示在这里</Text>
            </View>
          ) : (
            <View className='ac-timeline'>
              <Text className='ac-total'>共 {total} 条记录</Text>
              {activities.map((act) => (
                <View key={act.id} className='ac-tl-item'>
                  <View className='ac-tl-dot' />
                  <View className='ac-tl-content'>
                    <View className='ac-tl-header'>
                      <View className='ac-tl-type'>
                        <Text className='ac-tl-icon'>{ACTION_ICONS[act.action_type] || '📌'}</Text>
                        <Text className='ac-tl-label'>{ACTION_LABELS[act.action_type] || act.action_type}</Text>
                      </View>
                      <Text className='ac-tl-time'>{formatTime(act.created_at)}</Text>
                    </View>
                    <Text className='ac-tl-summary'>{act.summary}</Text>
                    {act.detail && (
                      <Text className='ac-tl-detail'>{act.detail}</Text>
                    )}
                  </View>
                </View>
              ))}

              {total > page * pageSize && (
                <View className='ac-load-more' onClick={this.handleLoadMore}>
                  <Text>加载更多</Text>
                </View>
              )}
            </View>
          )}
        </ScrollView>
      </View>
    )
  }
}
