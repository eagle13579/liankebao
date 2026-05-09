const api = require('../../utils/api')

Page({
  data: { orders: [], loading: true },

  onLoad() {
    const token = wx.getStorageSync('token')
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    api.get('/orders').then(res => {
      const items = (res.data?.items || []).map(o => ({
        ...o,
        productName: o.product?.name || '未知产品'
      }))
      this.setData({ orders: items, loading: false })
    })
  },

  handleConfirm(e) {
    const orderId = e.currentTarget.dataset.id
    api.put('/orders/' + orderId + '/status', { status: 'received' }).then(res => {
      if (res.code === 200) {
        wx.showToast({ title: '已确认收货', icon: 'success' })
        this.onLoad()
      }
    })
  }
})
