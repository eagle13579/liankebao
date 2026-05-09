const api = require('../../utils/api')

Page({
  data: { products: [], loading: true },
  onLoad() {
    api.get('/products').then(res => {
      this.setData({ products: res.data?.items || [], loading: false })
    })
  },
  goDetail(e) {
    wx.navigateTo({ url: '/pages/product/index?id=' + e.currentTarget.dataset.id })
  }
})
