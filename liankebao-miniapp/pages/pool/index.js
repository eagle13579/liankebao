var api = require('../../utils/api')

function safeGetImage(images) {
  try {
    var arr = JSON.parse(images || '[]')
    return arr[0] || ''
  } catch (e) {
    return ''
  }
}

var searchTimer = null

Page({
  data: {
    products: [],
    keyword: '',
    currentCategory: '',
    categories: ['AI名片', 'GEO诊断', '数字分身', '营销工具', '企业服务', '其他'],
    page: 1,
    pageSize: 20,
    hasMore: true,
    loading: false
  },
  onLoad: function() {
    try {
      var cat = wx.getStorageSync('pool_category')
      if (cat) {
        this.setData({ currentCategory: cat })
        wx.removeStorageSync('pool_category')
      }
    } catch (e) {}
    this.loadProducts(true)
  },
  onShow: function() {
    try {
      var cat = wx.getStorageSync('pool_category')
      if (cat) {
        this.setData({ currentCategory: cat, keyword: '' })
        wx.removeStorageSync('pool_category')
        this.loadProducts(true)
        return
      }
    } catch (e) {}
    if (this.data.products.length > 0) {
      this.loadProducts(true)
    }
  },
  onPullDownRefresh: function() {
    this.loadProducts(true)
    wx.stopPullDownRefresh()
  },
  loadProducts: function(reset) {
    var self = this
    if (reset) {
      self.setData({ page: 1, hasMore: true, products: [], loading: true })
    } else {
      self.setData({ loading: true })
    }

    var params = { page: self.data.page, pageSize: self.data.pageSize }
    if (self.data.keyword) params.search = self.data.keyword
    if (self.data.currentCategory) params.category = self.data.currentCategory

    api.get('/products?' + objToParams(params)).then(function(res) {
      var raw = (res.data && res.data.items) || []
      var items = []
      for (var i = 0; i < raw.length; i++) {
        var p = raw[i]
        items.push({
          id: p.id,
          name: p.name,
          price: p.price,
          earn_per_share: p.earn_per_share,
          images: p.images,
          firstImage: safeGetImage(p.images)
        })
      }

      var newList = reset ? items : self.data.products.concat(items)
      var hasMore = items.length >= self.data.pageSize

      self.setData({
        products: newList,
        hasMore: hasMore,
        loading: false,
        page: reset ? 2 : self.data.page + 1
      })
    }).catch(function() {
      self.setData({ loading: false })
    })
  },
  onSearchInput: function(e) {
    var self = this
    var value = e.detail.value
    self.setData({ keyword: value })
    // 300ms 防抖
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(function() {
      self.loadProducts(true)
    }, 300)
  },
  onSearch: function() {
    if (searchTimer) clearTimeout(searchTimer)
    this.loadProducts(true)
  },
  clearSearch: function() {
    if (searchTimer) clearTimeout(searchTimer)
    this.setData({ keyword: '' })
    this.loadProducts(true)
  },
  selectCategory: function(e) {
    var cat = e.currentTarget.dataset.cat
    this.setData({ currentCategory: cat })
    this.loadProducts(true)
  },
  loadMore: function() {
    if (!this.data.hasMore || this.data.loading) return
    this.loadProducts(false)
  },
  goDetail: function(e) {
    wx.navigateTo({ url: '/pages/product/index?id=' + e.currentTarget.dataset.id })
  }
})

function objToParams(obj) {
  var parts = []
  for (var key in obj) {
    if (obj[key] !== undefined && obj[key] !== null && obj[key] !== '') {
      parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(obj[key]))
    }
  }
  return parts.join('&')
}
