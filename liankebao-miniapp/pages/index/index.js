const api = require('../../utils/api')

Page({
  data: { products: [], loading: true },
  onLoad() {
    api.get('/products').then(res => {
      const items = (res.data?.items || []).map(p => ({
        ...p,
        firstImage: safeGetImage(p.images)
      }))
      this.setData({ products: items, loading: false })
    })
  },
  goDetail(e) {
    wx.navigateTo({ url: '/pages/product/index?id=' + e.currentTarget.dataset.id })
  }
})

function safeGetImage(images) {
  try {
    const arr = JSON.parse(images || '[]')
    return arr[0] || ''
  } catch {
    return ''
  }
}
