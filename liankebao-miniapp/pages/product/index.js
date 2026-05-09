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
  data: { product: null, loading: true },

  onLoad: function(options) {
    var self = this
    var id = options.id
    api.get('/products/' + id).then(function(res) {
      var p = res.data
      if (p) {
        p.firstImage = safeGetImage(p.images)
      }
      self.setData({ product: p, loading: false })
    })
  },

  handleBuy: function() {
    var token = wx.getStorageSync('token')
    var self = this
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    api.post('/orders', { product_id: self.data.product.id, quantity: 1 }).then(function(res) {
      if (res.code === 200) {
        wx.showToast({ title: '下单成功', icon: 'success' })
        wx.navigateTo({ url: '/pages/orders/index' })
      } else {
        wx.showToast({ title: res.message || '下单失败', icon: 'error' })
      }
    })
  }
})
