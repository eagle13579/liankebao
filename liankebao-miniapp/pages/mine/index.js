Page({
  data: {
    user: null,
    isLoggedIn: false,
    userName: '未登录',
    userInitial: '?',
    userRole: '普通用户',
    isPromoter: false,
    isSupplier: false
  },

  onLoad() {
    this.loadUser()
  },

  onShow() {
    this.loadUser()
  },

  loadUser() {
    const user = wx.getStorageSync('user')
    if (user) {
      this.setData({
        user,
        isLoggedIn: true,
        userName: user.name || user.username || '未登录',
        userInitial: user.name ? user.name.charAt(0).toUpperCase() : '?',
        userRole: user.role === 'promoter' ? '推广员' : user.role === 'supplier' ? '产品方' : '普通用户',
        isPromoter: user.role === 'promoter',
        isSupplier: user.role === 'supplier'
      })
    } else {
      this.setData({
        user: null,
        isLoggedIn: false,
        userName: '未登录',
        userInitial: '?',
        userRole: '普通用户',
        isPromoter: false,
        isSupplier: false
      })
    }
  },

  goOrders() {
    wx.navigateTo({ url: '/pages/orders/index' })
  },

  handleLogout() {
    wx.removeStorageSync('token')
    wx.removeStorageSync('user')
    this.loadUser()
    wx.showToast({ title: '已退出', icon: 'success' })
  }
})
