import { Component } from 'react'
import { View, Text, Input, Button, ScrollView, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import NavBar from '../../components/NavBar'
import { matchApi, membershipApi } from '../../api/digitalBrochure'
import './index.scss'

interface MatchItem {
  id: string
  name: string
  company: string
  position: string
  avatar?: string
  provide_tags: string[]
  need_tags: string[]
  match_score: number
  phone: string
  email: string
  wechat: string
  industry?: string
  region?: string
  unlocked?: boolean
}

interface CardMatchState {
  loading: boolean
  keyword: string
  matches: MatchItem[]
  page: number
  hasMore: boolean
  refreshing: boolean
  industry: string
  region: string
  sortBy: 'match' | 'time'
  showFilter: boolean
}

const INDUSTRIES = ['全部', '互联网', '金融', '教育', '医疗', '制造', '零售', '地产', '文化传媒', '其他']
const REGIONS = ['全部', '北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '南京', '其他']

export default class CardMatch extends Component<{}, CardMatchState> {
  state: CardMatchState = {
    loading: true,
    keyword: '',
    matches: [],
    page: 1,
    hasMore: true,
    refreshing: false,
    industry: '全部',
    region: '全部',
    sortBy: 'match',
    showFilter: false,
  }

  componentDidMount() {
    this.loadMatches()
  }

  componentDidShow() {
    // 每次显示刷新
    if (this.state.matches.length > 0) {
      this.setState({ page: 1, matches: [] }, () => this.loadMatches())
    } else {
      this.loadMatches()
    }
  }

  loadMatches = async (append = false) => {
    const { keyword, page, industry, region, sortBy } = this.state
    this.setState({ loading: !append, refreshing: append })

    try {
      const params: any = {
        page,
        page_size: 20,
        keyword: keyword || undefined,
        sort_by: sortBy,
      }
      if (industry && industry !== '全部') params.industry = industry
      if (region && region !== '全部') params.region = region

      const res: any = await matchApi.getMatches(params)
      if (res?.code === 200) {
        const list = res.data?.list || res.data || []
        this.setState((prev) => ({
          matches: append ? [...prev.matches, ...list] : list,
          hasMore: list.length >= 20,
          loading: false,
          refreshing: false,
        }))
      } else {
        this.setState({ loading: false, refreshing: false })
      }
    } catch {
      this.setState({ loading: false, refreshing: false })
    }
  }

  handleSearch = () => {
    this.setState({ page: 1, matches: [] }, () => this.loadMatches())
  }

  handleKeywordInput = (e: any) => {
    this.setState({ keyword: e.detail.value })
  }

  handleConfirm = () => {
    this.handleSearch()
  }

  loadMore = () => {
    if (!this.state.hasMore || this.state.loading) return
    this.setState((prev) => ({ page: prev.page + 1 }), () => this.loadMatches(true))
  }

  handleUnlock = async (item: MatchItem) => {
    const user = Taro.getStorageSync('user')
    const level = user?.membership_level || 0

    if (level >= 2) {
      // 黄金及以上直接解锁
      try {
        const res: any = await matchApi.unlock(item.id)
        if (res?.code === 200) {
          this.setState((prev) => ({
            matches: prev.matches.map((m) =>
              m.id === item.id ? { ...m, unlocked: true } : m
            ),
          }))
          Taro.showToast({ title: '已解锁', icon: 'success' })
        } else {
          Taro.showToast({ title: res?.message || '解锁失败', icon: 'error' })
        }
      } catch {
        Taro.showToast({ title: '解锁失败', icon: 'error' })
      }
    } else {
      Taro.showModal({
        title: '升级会员',
        content: '黄金会员及以上可解锁查看联系方式，是否前往升级？',
        confirmText: '去升级',
        success: (res) => {
          if (res.confirm) {
            Taro.navigateTo({ url: '/pages/membership/index' })
          }
        },
      })
    }
  }

  goPreview = (id: string) => {
    Taro.navigateTo({ url: `/pages/brochure-preview/index?id=${id}` })
  }

  toggleFilter = () => {
    this.setState((prev) => ({ showFilter: !prev.showFilter }))
  }

  setIndustry = (val: string) => {
    this.setState({ industry: val, page: 1, matches: [], showFilter: false }, () => this.loadMatches())
  }

  setRegion = (val: string) => {
    this.setState({ region: val, page: 1, matches: [], showFilter: false }, () => this.loadMatches())
  }

  setSortBy = (val: 'match' | 'time') => {
    this.setState({ sortBy: val, page: 1, matches: [] }, () => this.loadMatches())
  }

  maskPhone = (phone: string) => {
    if (!phone) return ''
    return phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')
  }

  renderMatchItem = (item: MatchItem) => {
    const showContact = item.unlocked
    return (
      <View key={item.id} className='match-item glass' onClick={() => this.goPreview(item.id)}>
        <View className='match-item-top'>
          <View className='match-avatar'>
            {item.avatar ? (
              <Image className='match-avatar-img' src={item.avatar} mode='aspectFill' />
            ) : (
              <Text className='match-avatar-text'>{item.name ? item.name.charAt(0) : '?'}</Text>
            )}
          </View>
          <View className='match-info'>
            <View className='match-name-row'>
              <Text className='match-name'>{item.name || '未知'}</Text>
              <View className='match-score-badge'>
                <Text className='match-score-text'>{item.match_score}%</Text>
              </View>
            </View>
            <Text className='match-company'>
              {item.company || ''}{item.company && item.position ? ' · ' : ''}{item.position || ''}
            </Text>
          </View>
        </View>

        {/* 供需标签精简展示 */}
        <View className='match-tags'>
          {item.provide_tags?.slice(0, 3).map((tag, i) => (
            <Text key={i} className='tag tag-provide'>{tag}</Text>
          ))}
          {item.need_tags?.slice(0, 3).map((tag, i) => (
            <Text key={i} className='tag tag-need'>{tag}</Text>
          ))}
          {(item.provide_tags?.length > 3 || item.need_tags?.length > 3) && (
            <Text className='tag tag-more'>+更多</Text>
          )}
        </View>

        {/* 联系方式 */}
        <View className='match-contact'>
          {item.phone && (
            <Text className='contact-masked'>
              📞 {showContact ? item.phone : this.maskPhone(item.phone)}
            </Text>
          )}
          {!showContact && item.phone && (
            <Button className='btn-unlock-sm' onClick={(e) => { e.stopPropagation?.(); this.handleUnlock(item) }}>
              🔒 解锁查看
            </Button>
          )}
        </View>
      </View>
    )
  }

  render() {
    const { loading, matches, keyword, hasMore, refreshing, showFilter, industry, region, sortBy } = this.state

    return (
      <View className='match-page'>
        <NavBar title='匹配结果' />

        {/* 搜索栏 */}
        <View className='match-search-bar'>
          <View className='search-input-wrap'>
            <Text className='search-icon'>🔍</Text>
            <Input
              className='search-input'
              placeholder='搜索姓名、公司、标签...'
              value={keyword}
              onInput={this.handleKeywordInput}
              onConfirm={this.handleConfirm}
              confirmType='search'
            />
            {keyword ? (
              <Text className='search-clear' onClick={() => this.setState({ keyword: '' }, this.handleSearch)}>✕</Text>
            ) : null}
          </View>
          <Button className='search-btn' onClick={this.handleSearch}>搜索</Button>
        </View>

        {/* 筛选排序 */}
        <View className='match-filter-bar'>
          <View className='filter-chips'>
            <View className={`filter-chip ${showFilter ? 'active' : ''}`} onClick={this.toggleFilter}>
              <Text>筛选</Text>
              <Text className='chip-arrow'>{showFilter ? '▲' : '▼'}</Text>
            </View>
            <View className={`filter-chip ${sortBy === 'match' ? 'active' : ''}`} onClick={() => this.setSortBy('match')}>
              <Text>匹配度</Text>
            </View>
            <View className={`filter-chip ${sortBy === 'time' ? 'active' : ''}`} onClick={() => this.setSortBy('time')}>
              <Text>最新</Text>
            </View>
          </View>
        </View>

        {/* 筛选面板 */}
        {showFilter && (
          <View className='filter-panel glass'>
            <View className='filter-section'>
              <Text className='filter-label'>行业</Text>
              <View className='filter-options'>
                {INDUSTRIES.map((ind) => (
                  <Text
                    key={ind}
                    className={`filter-option ${industry === ind ? 'active' : ''}`}
                    onClick={() => this.setIndustry(ind)}
                  >
                    {ind}
                  </Text>
                ))}
              </View>
            </View>
            <View className='filter-section'>
              <Text className='filter-label'>地区</Text>
              <View className='filter-options'>
                {REGIONS.map((reg) => (
                  <Text
                    key={reg}
                    className={`filter-option ${region === reg ? 'active' : ''}`}
                    onClick={() => this.setRegion(reg)}
                  >
                    {reg}
                  </Text>
                ))}
              </View>
            </View>
          </View>
        )}

        {/* 匹配列表 */}
        <ScrollView
          className='match-list'
          scrollY
          onScrollToLower={this.loadMore}
        >
          {loading && matches.length === 0 ? (
            <View className='match-loading'>
              {[1, 2, 3].map((i) => (
                <View key={i} className='match-skeleton glass'>
                  <View className='skeleton' style={{ width: 48, height: 48, borderRadius: 24 }} />
                  <View style={{ flex: 1, marginLeft: 12 }}>
                    <View className='skeleton' style={{ width: '60%', height: 16, marginBottom: 8 }} />
                    <View className='skeleton' style={{ width: '40%', height: 12 }} />
                  </View>
                </View>
              ))}
            </View>
          ) : matches.length === 0 ? (
            <View className='match-empty'>
              <Text className='empty-icon'>🔍</Text>
              <Text className='empty-title'>暂无匹配</Text>
              <Text className='empty-desc'>完善名片信息提高匹配率</Text>
              <Button
                className='btn-secondary'
                onClick={() => Taro.switchTab({ url: '/pages/index/index' })}
              >
                完善名片
              </Button>
            </View>
          ) : (
            <>
              {matches.map((item) => this.renderMatchItem(item))}
              {refreshing && (
                <View className='loading'>加载中...</View>
              )}
              {!hasMore && matches.length > 0 && (
                <View className='loading'>没有更多了</View>
              )}
            </>
          )}
        </ScrollView>
      </View>
    )
  }
}
