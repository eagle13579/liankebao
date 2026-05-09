Page({
  data: { user: null },

  onLoad() {
    const user = wx.getStorageSync('user')
    this.setData({ user })
  },

  onShow() {
    const user = wx.getStorageSync('user')
    this.setData({ user })
  },

  goOrders() {
    wx.navigateTo({ url: '/pages/orders/index' })
  },

  handleLogout() {
    wx.removeStorageSync('token')
    wx.removeStorageSync('user')
    wx.navigateTo({ url: '/pages/login/index' })
  }
})
