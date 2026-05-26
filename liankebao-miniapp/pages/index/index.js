var api = require('../../utils/api')

function safeGetImage(images) {
  try {
    var arr = JSON.parse(images || '[]')
    return arr[0] || ''
  } catch (e) {
    return ''
  }
}

Page({
  data: {
    products: [],
    recommendProducts: [],
    banners: [
      { image: 'https://via.placeholder.com/750x300/0ea5e9/ffffff?text=链客宝+AI名片' },
      { image: 'https://via.placeholder.com/750x300/0284c7/ffffff?text=GEO+诊断+精准获客' },
      { image: 'https://via.placeholder.com/750x300/0ea5e9/ffffff?text=数字分身+智能交互' }
    ],
    loading: true
  },
  onLoad: function() {
    this.loadData()
  },
  onShow: function() {
    this.loadData()
  },
  onPullDownRefresh: function() {
    var self = this
    self.loadData()
    wx.stopPullDownRefresh()
  },
  loadData: function() {
    var self = this
    self.setData({ loading: true })

    // 从API获取banner
    api.get('/banners').then(function(res) {
      if (res && res.code === 200 && res.data && res.data.length > 0) {
        var bannerList = []
        for (var i = 0; i < res.data.length; i++) {
          var b = res.data[i]
          bannerList.push({
            image: b.image || '',
            title: b.title || '',
            url: b.url || ''
          })
        }
        self.setData({ banners: bannerList })
      }
      // API返回空或失败，保持现有placeholder降级
    }).catch(function() {
      // 静默降级，保留已有placeholder
    })

    api.get('/products?pageSize=10&sort=recommend').then(function(res) {
      var raw = (res.data && res.data.items) || []
      var items = []
      for (var i = 0; i < raw.length; i++) {
        var p = raw[i]
        items.push({
          id: p.id,
          name: p.name,
          price: p.price,
          description: p.description || '',
          earn_per_share: p.earn_per_share,
          images: p.images,
          firstImage: safeGetImage(p.images)
        })
      }
      self.setData({ recommendProducts: items, products: items, loading: false })
    }).catch(function() {
      self.setData({ loading: false })
    })
  },
  goDetail: function(e) {
    wx.navigateTo({ url: '/pages/product/index?id=' + e.currentTarget.dataset.id })
  },
  goPool: function() {
    wx.switchTab({ url: '/pages/pool/index' })
  },
  goPoolWithCat: function(e) {
    var cat = e.currentTarget.dataset.cat
    try {
      wx.setStorageSync('pool_category', cat)
    } catch (e) {}
    wx.switchTab({ url: '/pages/pool/index' })
  },
  goAIDiagnosis: function() {
    wx.navigateTo({ url: '/pages/webview/index?url=' + encodeURIComponent('https://www.go-aiport.com/ai-diagnosis') })
  },
  goAICard: function() {
    wx.navigateTo({ url: '/pages/webview/index?url=' + encodeURIComponent('https://www.go-aiport.com/ai-card') })
  }
})
