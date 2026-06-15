import { Component } from 'react'
import { View, Text, ScrollView, Input, Image } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

const PAGE_SIZE = 20

interface ContactsState {
  contacts: any[]
  loading: boolean
  error: string
  total: number
  page: number
  search: string
  searchInput: string
  tags: string
  availableTags: string[]
  showTagFilter: boolean
}

export default class ContactsIndex extends Component<{}, ContactsState> {
  state: ContactsState = {
    contacts: [],
    loading: true,
    error: '',
    total: 0,
    page: 1,
    search: '',
    searchInput: '',
    tags: '',
    availableTags: [],
    showTagFilter: false,
  }

  componentDidMount() {
    this.fetchContacts()
    this.fetchTags()
  }

  fetchTags = () => {
    api.get('/contacts/tags')
      .then((res: any) => {
        if (res.code === 200 && res.data?.tags) {
          this.setState({ availableTags: res.data.tags })
        }
      })
      .catch(() => {})
  }

  fetchContacts = () => {
    const { search, tags, page } = this.state
    this.setState({ loading: true, error: '' })

    let path = `/contacts?page=${page}&page_size=${PAGE_SIZE}`
    if (search) path += `&search=${encodeURIComponent(search)}`
    if (tags) path += `&tags=${encodeURIComponent(tags)}`

    api.get(path)
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ contacts: res.data.items || [], total: res.data.total || 0, loading: false })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleSearchInput = (e: any) => {
    this.setState({ searchInput: e.detail.value })
  }

  handleSearchConfirm = () => {
    this.setState({ search: this.state.searchInput, page: 1 }, () => this.fetchContacts())
  }

  toggleTagFilter = () => {
    this.setState((prev) => ({ showTagFilter: !prev.showTagFilter }))
  }

  toggleTag = (tag: string) => {
    const currentTags = this.state.tags ? this.state.tags.split(',') : []
    const idx = currentTags.indexOf(tag)
    if (idx >= 0) {
      currentTags.splice(idx, 1)
    } else {
      currentTags.push(tag)
    }
    this.setState({ tags: currentTags.join(','), page: 1 }, () => this.fetchContacts())
  }

  clearTagFilter = () => {
    this.setState({ tags: '', page: 1 }, () => this.fetchContacts())
  }

  handlePrevPage = () => {
    if (this.state.page <= 1) return
    this.setState((prev) => ({ page: prev.page - 1 }), () => this.fetchContacts())
  }

  handleNextPage = () => {
    const totalPages = Math.ceil(this.state.total / PAGE_SIZE)
    if (this.state.page >= totalPages) return
    this.setState((prev) => ({ page: prev.page + 1 }), () => this.fetchContacts())
  }

  handleDelete = (id: number, e: any) => {
    e.stopPropagation()
    Taro.showModal({
      title: '提示',
      content: '确定删除此联系人？',
      success: (res) => {
        if (res.confirm) {
          api.post(`/contacts/${id}/delete`, {})
            .then((res2: any) => {
              if (res2.code === 200) {
                Taro.showToast({ title: '删除成功', icon: 'success' })
                this.fetchContacts()
              } else {
                Taro.showToast({ title: res2.message || '删除失败', icon: 'error' })
              }
            })
            .catch(() => {
              Taro.showToast({ title: '删除失败', icon: 'error' })
            })
        }
      },
    })
  }

  render() {
    const { contacts, loading, error, total, page, searchInput, tags, availableTags, showTagFilter } = this.state
    const totalPages = Math.ceil(total / PAGE_SIZE)
    const selectedTags = tags ? tags.split(',') : []

    return (
      <View className='contacts-page'>
        {/* Header */}
        <View className='cp-header'>
          <Text className='cp-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='cp-title'>人脉管理</Text>
        </View>

        {/* Search */}
        <View className='cp-search-wrap'>
          <View className='cp-search'>
            <Text className='cp-search-icon'>🔍</Text>
            <Input
              className='cp-search-input'
              placeholder='搜索姓名、电话、公司...'
              value={searchInput}
              onInput={this.handleSearchInput}
              onConfirm={this.handleSearchConfirm}
            />
          </View>
        </View>

        {/* Tags filter */}
        <View className='cp-tags-bar'>
          <View className='cp-tags-row'>
            <View
              className={`cp-tag-filter-btn ${showTagFilter ? 'cp-tag-filter-active' : ''}`}
              onClick={this.toggleTagFilter}
            >
              <Text>🏷 标签</Text>
            </View>
            {tags && (
              <Text className='cp-clear-filter' onClick={this.clearTagFilter}>
                清除筛选
              </Text>
            )}
          </View>
          {showTagFilter && availableTags.length > 0 && (
            <View className='cp-tag-options'>
              {availableTags.map((tag) => (
                <Text
                  key={tag}
                  className={`cp-tag-option ${selectedTags.includes(tag) ? 'cp-tag-option-active' : ''}`}
                  onClick={() => this.toggleTag(tag)}
                >
                  {tag}
                </Text>
              ))}
            </View>
          )}
        </View>

        {/* Content */}
        <ScrollView className='cp-content' scrollY>
          {loading ? (
            <View className='cp-loading'>
              {[1, 2, 3, 4].map((i) => (
                <View key={i} className='cp-skel-card'>
                  <View className='cp-skel-avatar' />
                  <View className='cp-skel-body'>
                    <View className='cp-skel-line w-60' />
                    <View className='cp-skel-line w-40' />
                  </View>
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='cp-error'>
              <Text className='cp-error-icon'>⚠</Text>
              <Text className='cp-error-text'>{error}</Text>
              <Text className='cp-error-retry' onClick={this.fetchContacts}>点击重试</Text>
            </View>
          ) : contacts.length === 0 ? (
            <View className='cp-empty'>
              <Text className='cp-empty-icon'>👥</Text>
              <Text className='cp-empty-text'>暂无联系人</Text>
            </View>
          ) : (
            <View>
              <View className='cp-list-header'>
                <Text className='cp-total'>共 {total} 位联系人</Text>
              </View>
              {contacts.map((c: any) => (
                <View
                  key={c.id}
                  className='cp-contact-card'
                  onClick={() => Taro.navigateTo({ url: `/pages/contacts/detail?id=${c.id}` })}
                >
                  <View className='cp-card-avatar'>
                    {c.avatar ? (
                      <Image className='cp-avatar-img' src={c.avatar} mode='aspectFill' lazyLoad />
                    ) : (
                      <Text className='cp-avatar-placeholder'>👤</Text>
                    )}
                  </View>
                  <View className='cp-card-body'>
                    <View className='cp-card-top'>
                      <Text className='cp-card-name'>{c.name}</Text>
                      <View className='cp-card-actions'>
                        <Text
                          className='cp-action-delete'
                          onClick={(e) => this.handleDelete(c.id, e)}
                        >
                          🗑
                        </Text>
                      </View>
                    </View>
                    <View className='cp-card-info'>
                      {c.phone && (
                        <Text className='cp-info-item'>📞 {c.phone}</Text>
                      )}
                      {c.company && (
                        <Text className='cp-info-item'>
                          🏢 {c.company}{c.position ? ` · ${c.position}` : ''}
                        </Text>
                      )}
                    </View>
                    {c.tags && c.tags.length > 0 && (
                      <View className='cp-card-tags'>
                        {c.tags.map((tag: string, i: number) => (
                          <Text key={i} className='cp-card-tag'>{tag}</Text>
                        ))}
                      </View>
                    )}
                  </View>
                </View>
              ))}

              {/* Pagination */}
              {totalPages > 1 && (
                <View className='cp-pagination'>
                  <Text
                    className={`cp-page-btn ${page <= 1 ? 'cp-page-disabled' : ''}`}
                    onClick={this.handlePrevPage}
                  >
                    上一页
                  </Text>
                  <Text className='cp-page-info'>{page} / {totalPages}</Text>
                  <Text
                    className={`cp-page-btn ${page >= totalPages ? 'cp-page-disabled' : ''}`}
                    onClick={this.handleNextPage}
                  >
                    下一页
                  </Text>
                </View>
              )}
            </View>
          )}
        </ScrollView>
      </View>
    )
  }
}
