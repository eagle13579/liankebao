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
  data: { products: [], loading: true },
  onLoad() {
    var self = this
    api.get('/products').then(function(res) {
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
      self.setData({ products: items, loading: false })
    })
  },
  goDetail(e) {
    wx.navigateTo({ url: '/pages/product/index?id=' + e.currentTarget.dataset.id })
  }
})
