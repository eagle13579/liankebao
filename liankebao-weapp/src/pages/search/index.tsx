import { Component } from 'react'
import { View, Text, ScrollView, Input, Image } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface ProductItem {
  id: number
  name: string
  description: string
  price: number
  category: string
  images: string
  tags: string
  brand: string
  highlight_title?: string
  highlight_content?: string
}

interface SearchState {
  query: string
  results: ProductItem[]
  suggestions: string[]
  categories: string[]
  loading: boolean
  error: string
  total: number
  page: number
  selectedCategory: string
  sortBy: string
  showSuggestions: boolean
}

const SORT_OPTIONS = [
  { key: 'relevance', label: '相关度' },
  { key: 'price_asc', label: '价格↑' },
  { key: 'price_desc', label: '价格↓' },
  { key: 'newest', label: '最新' },
]

export default class SearchIndex extends Component<{}, SearchState> {
  state: SearchState = {
    query: '',
    results: [],
    suggestions: [],
    categories: [],
    loading: false,
    error: '',
    total: 0,
    page: 1,
    selectedCategory: '',
    sortBy: 'relevance',
    showSuggestions: false,
  }

  componentDidMount() {
    this.fetchCategories()
  }

  fetchCategories = () => {
    api.get('/search/categories')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ categories: res.data.categories || [] })
        }
      })
      .catch(() => {})
  }

  handleInput = (e: any) => {
    const value = e.detail.value
    this.setState({ query: value, showSuggestions: value.length > 0 })

    if (value.length >= 2) {
      this.fetchSuggestions(value)
    } else {
      this.setState({ suggestions: [] })
    }
  }

  fetchSuggestions = (q: string) => {
    api.get(`/search/suggestions?q=${encodeURIComponent(q)}&limit=5`)
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ suggestions: res.data.suggestions || [] })
        }
      })
      .catch(() => {})
  }

  handleSearch = (query?: string) => {
    const q = query || this.state.query
    if (!q.trim()) return

    this.setState({ query: q, showSuggestions: false, page: 1 }, () => {
      this.doSearch()
    })
  }

  handleSuggestionClick = (suggestion: string) => {
    this.setState({ query: suggestion, showSuggestions: false }, () => {
      this.handleSearch(suggestion)
    })
  }

  doSearch = () => {
    const { query, page, selectedCategory, sortBy } = this.state
    this.setState({ loading: true, error: '' })

    let path = `/search?q=${encodeURIComponent(query)}&page=${page}&page_size=20&sort_by=${sortBy}&highlight=true`
    if (selectedCategory) path += `&category=${encodeURIComponent(selectedCategory)}`

    api.get(path)
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({
            results: page === 1 ? (res.data.items || []) : [...this.state.results, ...(res.data.items || [])],
            total: res.data.total || 0,
            loading: false,
          })
        } else {
          this.setState({ error: res.message || '搜索失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleCategoryChange = (cat: string) => {
    this.setState({ selectedCategory: cat, page: 1 }, () => {
      if (this.state.query) this.doSearch()
    })
  }

  handleSortChange = (sort: string) => {
    this.setState({ sortBy: sort, page: 1 }, () => {
      if (this.state.query) this.doSearch()
    })
  }

  handleLoadMore = () => {
    this.setState((prev) => ({ page: prev.page + 1 }), () => this.doSearch())
  }

  handleProductClick = (id: number) => {
    Taro.navigateTo({ url: `/pages/product/index?id=${id}` })
  }

  parseImages = (imagesStr: string): string[] => {
    try {
      const parsed = JSON.parse(imagesStr)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  render() {
    const { query, results, suggestions, categories, loading, error, total, page, selectedCategory, sortBy, showSuggestions } = this.state
    const pageSize = 20

    return (
      <View className='search-page'>
        {/* Search Bar */}
        <View className='sp-header'>
          <View className='sp-search-bar'>
            <Text className='sp-search-icon'>🔍</Text>
            <Input
              className='sp-search-input'
              placeholder='搜索产品名称、描述、品牌...'
              value={query}
              onInput={this.handleInput}
              onConfirm={() => this.handleSearch()}
              onFocus={() => this.setState({ showSuggestions: query.length > 0 })}
              onBlur={() => setTimeout(() => this.setState({ showSuggestions: false }), 200)}
            />
            {query && (
              <Text className='sp-clear' onClick={() => this.setState({ query: '', results: [], total: 0 })}>✕</Text>
            )}
          </View>
        </View>

        {/* Suggestions Dropdown */}
        {showSuggestions && suggestions.length > 0 && (
          <View className='sp-suggestions'>
            {suggestions.map((s, i) => (
              <View key={i} className='sp-sug-item' onClick={() => this.handleSuggestionClick(s)}>
                <Text className='sp-sug-icon'>🔍</Text>
                <Text className='sp-sug-text'>{s}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Categories */}
        {categories.length > 0 && (
          <ScrollView className='sp-categories' scrollX showScrollbar={false}>
            <Text
              className={`sp-cat-tab ${!selectedCategory ? 'sp-cat-tab-active' : ''}`}
              onClick={() => this.handleCategoryChange('')}
            >
              全部
            </Text>
            {categories.map((cat) => (
              <Text
                key={cat}
                className={`sp-cat-tab ${selectedCategory === cat ? 'sp-cat-tab-active' : ''}`}
                onClick={() => this.handleCategoryChange(cat)}
              >
                {cat}
              </Text>
            ))}
          </ScrollView>
        )}

        {/* Sort Options */}
        {results.length > 0 && (
          <View className='sp-sort-bar'>
            {SORT_OPTIONS.map((opt) => (
              <Text
                key={opt.key}
                className={`sp-sort-btn ${sortBy === opt.key ? 'sp-sort-btn-active' : ''}`}
                onClick={() => this.handleSortChange(opt.key)}
              >
                {opt.label}
              </Text>
            ))}
          </View>
        )}

        {/* Results */}
        <ScrollView className='sp-body' scrollY>
          {!query ? (
            <View className='sp-welcome'>
              <Text className='sp-welcome-icon'>🔍</Text>
              <Text className='sp-welcome-text'>搜索海量产品</Text>
              <Text className='sp-welcome-hint'>输入关键词，快速找到您需要的产品</Text>
            </View>
          ) : loading && page === 1 ? (
            <View className='sp-loading'>
              {[1, 2, 3].map((i) => (
                <View key={i} className='sp-skel-card'>
                  <View className='sp-skel-img' />
                  <View className='sp-skel-info'>
                    <View className='sp-skel-line w-75' />
                    <View className='sp-skel-line w-50' />
                    <View className='sp-skel-line w-33' />
                  </View>
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='sp-error'>
              <Text className='sp-error-icon'>⚠️</Text>
              <Text className='sp-error-text'>{error}</Text>
              <Text className='sp-error-retry' onClick={() => this.doSearch()}>点击重试</Text>
            </View>
          ) : results.length === 0 ? (
            <View className='sp-empty'>
              <Text className='sp-empty-icon'>📭</Text>
              <Text className='sp-empty-text'>未找到相关产品</Text>
              <Text className='sp-empty-hint'>试试其他关键词或筛选条件</Text>
            </View>
          ) : (
            <View>
              <Text className='sp-result-count'>共 {total} 个结果</Text>
              {results.map((product) => (
                <View
                  key={product.id}
                  className='sp-product-card'
                  onClick={() => this.handleProductClick(product.id)}
                >
                  <View className='sp-prod-img-wrap'>
                    <Text className='sp-prod-img-placeholder'>📦</Text>
                  </View>
                  <View className='sp-prod-info'>
                    <Text
                      className='sp-prod-name'
                      dangerouslySetInnerHTML={{ __html: product.highlight_title || product.name }}
                    />
                    {product.brand && (
                      <Text className='sp-prod-brand'>{product.brand}</Text>
                    )}
                    <Text
                      className='sp-prod-desc'
                      dangerouslySetInnerHTML={{ __html: product.highlight_content || product.description }}
                    />
                    <View className='sp-prod-bottom'>
                      <Text className='sp-prod-price'>¥{product.price?.toFixed(2)}</Text>
                      {product.category && (
                        <Text className='sp-prod-cat'>{product.category}</Text>
                      )}
                    </View>
                  </View>
                </View>
              ))}

              {total > page * pageSize && (
                <View className='sp-load-more' onClick={this.handleLoadMore}>
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
