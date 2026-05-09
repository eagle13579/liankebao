const api = require('../../utils/api')

Page({
  data: { product: null, loading: true },

  onLoad(options) {
    const id = options.id
    api.get('/products/' + id).then(res => {
      this.setData({ product: res.data, loading: false })
    })
  },

  handleBuy() {
    const token = wx.getStorageSync('token')
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    api.post('/orders', { product_id: this.data.product.id, quantity: 1 }).then(res => {
      if (res.code === 200) {
        wx.showToast({ title: '下单成功', icon: 'success' })
        wx.navigateTo({ url: '/pages/orders/index' })
      } else {
        wx.showToast({ title: res.message || '下单失败', icon: 'error' })
      }
    })
  }
})
