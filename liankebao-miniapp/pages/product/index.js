var api = require('../../utils/api')

function parseImages(images) {
  try {
    var arr = JSON.parse(images || '[]')
    return Array.isArray(arr) ? arr : []
  } catch (e) {
    return []
  }
}

Page({
  data: {
    product: null,
    loading: true,
    imageList: []
  },

  onLoad: function(options) {
    var self = this
    var id = options.id

    api.get('/products/' + id).then(function(res) {
      var p = res.data
      var images = []

      if (p) {
        images = parseImages(p.images)
        p.firstImage = images.length > 0 ? images[0] : ''
        p.specText = parseImages(p.specifications)
      }

      self.setData({
        product: p,
        imageList: images,
        loading: false
      })
    })
  },

  handleBuy: function() {
    var self = this
    var token = wx.getStorageSync('token')

    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }

    api.post('/orders', {
      product_id: self.data.product.id,
      quantity: 1
    }).then(function(res) {
      if (res.code === 200) {
        wx.showToast({ title: '下单成功', icon: 'success' })
        wx.navigateTo({ url: '/pages/orders/index' })
      } else {
        wx.showToast({ title: res.message || '下单失败', icon: 'error' })
      }
    })
  },

  handlePreviewImage: function(e) {
    var current = e.currentTarget.dataset.url
    var list = this.data.imageList
    wx.previewImage({ current: current, urls: list })
  }
})
