import { Component } from 'react'
import { View, Text, ScrollView, Input } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

const CATEGORIES = [
  { key: '', label: '全部' },
  { key: '大健康', label: '大健康' },
  { key: '企业服务', label: '企业服务' },
  { key: '科技产品', label: '科技产品' },
  { key: '教育培训', label: '教育培训' },
  { key: '消费品', label: '消费品' },
]

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

interface SupplyDemandState {
  needs: any[]
  loading: boolean
  error: string
  total: number
  page: number
  category: string
  searchText: string
}

export default class SupplyDemandIndex extends Component<{}, SupplyDemandState> {
  state: SupplyDemandState = {
    needs: [],
    loading: true,
    error: '',
    total: 0,
    page: 1,
    category: '',
    searchText: '',
  }

  componentDidMount() {
    this.fetchNeeds()
  }

  fetchNeeds = () => {
    const { category, page, searchText } = this.state
    this.setState({ loading: true, error: '' })

    let path = `/needs?page=${page}&page_size=20`
    if (category) path += `&category=${encodeURIComponent(category)}`
    if (searchText) path += `&search=${encodeURIComponent(searchText)}`

    api.get(path)
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ needs: res.data.items || [], total: res.data.total || 0, loading: false })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleSearch = () => {
    this.setState({ page: 1 }, () => this.fetchNeeds())
  }

  handleSearchInput = (e: any) => {
    this.setState({ searchText: e.detail.value })
  }

  handleSearchConfirm = () => {
    this.handleSearch()
  }

  handleCategoryChange = (key: string) => {
    this.setState({ category: key, page: 1 }, () => this.fetchNeeds())
  }

  handleLoadMore = () => {
    this.setState((prev) => ({ page: prev.page + 1 }), () => this.fetchNeeds())
  }

  render() {
    const { needs, loading, error, total, page, category, searchText } = this.state
    const pageSize = 20

    return (
      <View className='supply-demand'>
        {/* Header */}
        <View className='sd-header'>
          <View className='sd-header-top'>
            <Text className='sd-back' onClick={() => Taro.navigateBack()}>←</Text>
            <View className='sd-header-info'>
              <Text className='sd-header-title'>需求大厅</Text>
              <Text className='sd-header-sub'>发现商机 · 精准对接</Text>
            </View>
          </View>
          {/* Search */}
          <View className='sd-search'>
            <Text className='sd-search-icon'>🔍</Text>
            <Input
              className='sd-search-input'
              placeholder='搜索需求...'
              value={searchText}
              onInput={this.handleSearchInput}
              onConfirm={this.handleSearchConfirm}
            />
          </View>
        </View>

        {/* Category Tabs */}
        <ScrollView className='sd-categories' scrollX showScrollbar={false}>
          {CATEGORIES.map((cat) => (
            <Text
              key={cat.key}
              className={`sd-cat-tab ${category === cat.key ? 'sd-cat-tab-active' : ''}`}
              onClick={() => this.handleCategoryChange(cat.key)}
            >
              {cat.label}
            </Text>
          ))}
        </ScrollView>

        {/* Content */}
        <ScrollView className='sd-content' scrollY>
          {loading ? (
            <View className='sd-loading'>
              {[1, 2, 3].map((i) => (
                <View key={i} className='sd-skeleton-card'>
                  <View className='sd-skel-line w-75' />
                  <View className='sd-skel-line w-50' />
                  <View className='sd-skel-line w-33' />
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='sd-error'>
              <Text className='sd-error-icon'>⚠</Text>
              <Text className='sd-error-text'>{error}</Text>
              <Text className='sd-error-retry' onClick={this.fetchNeeds}>点击重试</Text>
            </View>
          ) : needs.length === 0 ? (
            <View className='sd-empty'>
              <Text className='sd-empty-icon'>📋</Text>
              <Text className='sd-empty-text'>暂无相关需求</Text>
              <Text className='sd-empty-hint'>发布一条需求，让更多伙伴找到你</Text>
            </View>
          ) : (
            <View>
              <Text className='sd-total'>共 {total} 条需求</Text>
              {needs.map((need: any) => (
                <View
                  key={need.id}
                  className='sd-need-card'
                  onClick={() => Taro.navigateTo({ url: `/pages/supply-demand/detail?id=${need.id}` })}
                >
                  {/* Top row */}
                  <View className='sd-need-top'>
                    <Text className='sd-need-title'>{need.title}</Text>
                    <Text className={`sd-need-status ${need.status === 'open' ? 'sd-status-open' : 'sd-status-closed'}`}>
                      {need.status === 'open' ? '开放中' : '已关闭'}
                    </Text>
                  </View>

                  {/* Tags */}
                  {need.category && (
                    <View className='sd-need-tags'>
                      <Text className='sd-tag'>{need.category}</Text>
                    </View>
                  )}

                  {/* Info */}
                  <View className='sd-need-info'>
                    {need.budget && (
                      <Text className='sd-info-item sd-info-budget'>💰 {need.budget}</Text>
                    )}
                    {need.region && (
                      <Text className='sd-info-item'>📍 {need.region}</Text>
                    )}
                    <Text className='sd-info-item'>🕐 {formatTime(need.created_at)}</Text>
                  </View>

                  {/* User */}
                  {need.user && (
                    <View className='sd-need-user'>
                      <View className='sd-user-avatar'>
                        <Text className='sd-user-avatar-text'>{need.user.name?.[0] || '?'}</Text>
                      </View>
                      <Text className='sd-user-name'>{need.user.name}</Text>
                      {need.user.company && (
                        <Text className='sd-user-company'>| {need.user.company}</Text>
                      )}
                    </View>
                  )}
                </View>
              ))}

              {/* Load more */}
              {total > page * pageSize && (
                <View className='sd-load-more' onClick={this.handleLoadMore}>
                  <Text>加载更多</Text>
                </View>
              )}
            </View>
          )}
        </ScrollView>

        {/* FAB: 发布需求 */}
        <View
          className='sd-fab'
          onClick={() => Taro.navigateTo({ url: '/pages/supply-demand/post' })}
        >
          <Text className='sd-fab-icon'>+</Text>
        </View>
      </View>
    )
  }
}
