var api = require('../../utils/api')

Page({
  data: {
    needs: [],
    currentCategory: '',
    categories: ['AI名片', 'GEO诊断', '数字分身', '营销工具', '企业服务', '软件开发', '设计', '其他'],
    page: 1,
    pageSize: 20,
    hasMore: true,
    loading: false
  },
  onLoad: function() {
    this.loadNeeds(true)
  },
  onShow: function() {
    if (this.data.needs.length > 0) {
      this.loadNeeds(true)
    }
  },
  onPullDownRefresh: function() {
    this.loadNeeds(true)
    wx.stopPullDownRefresh()
  },
  loadNeeds: function(reset) {
    var self = this
    if (reset) {
      self.setData({ page: 1, hasMore: true, needs: [], loading: true })
    } else {
      self.setData({ loading: true })
    }

    var params = { page: self.data.page, pageSize: self.data.pageSize }
    if (self.data.currentCategory) params.category = self.data.currentCategory

    api.get('/api/v1/needs?' + objToParams(params)).then(function(res) {
      var raw = (res.data && res.data.items) || res.data || []
      if (!Array.isArray(raw)) raw = []

      var newList = reset ? raw : self.data.needs.concat(raw)
      var hasMore = raw.length >= self.data.pageSize

      self.setData({
        needs: newList,
        hasMore: hasMore,
        loading: false,
        page: reset ? 2 : self.data.page + 1
      })
    }).catch(function() {
      self.setData({ loading: false })
    })
  },
  selectCategory: function(e) {
    var cat = e.currentTarget.dataset.cat
    this.setData({ currentCategory: cat })
    this.loadNeeds(true)
  },
  loadMore: function() {
    if (!this.data.hasMore || this.data.loading) return
    this.loadNeeds(false)
  },
  goDetail: function(e) {
    wx.navigateTo({ url: '/pages/product/index?id=' + e.currentTarget.dataset.id })
  },
  goPostNeed: function() {
    wx.navigateTo({ url: '/pages/post-need/index' })
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
