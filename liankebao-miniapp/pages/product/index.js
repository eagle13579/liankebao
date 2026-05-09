const api = require('../../utils/api')

function safeGetImage(images) {
  try {
    const arr = JSON.parse(images || '[]')
    return arr[0] || ''
  } catch {
    return ''
  }
}

Page({
  data: { product: null, loading: true },

  onLoad(options) {
    const id = options.id
    api.get('/products/' + id).then(res => {
      const p = res.data
      if (p) p.firstImage = safeGetImage(p.images)
      this.setData({ product: p, loading: false })
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
