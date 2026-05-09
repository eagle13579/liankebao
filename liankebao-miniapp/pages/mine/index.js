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

  onLoad: function() {
    this.loadUser()
  },

  onShow: function() {
    this.loadUser()
  },

  loadUser: function() {
    var user = wx.getStorageSync('user')
    var self = this
    if (user) {
      self.setData({
        user: user,
        isLoggedIn: true,
        userName: user.name || user.username || '未登录',
        userInitial: user.name ? user.name.charAt(0).toUpperCase() : '?',
        userRole: user.role === 'promoter' ? '推广员' : user.role === 'supplier' ? '产品方' : '普通用户',
        isPromoter: user.role === 'promoter',
        isSupplier: user.role === 'supplier'
      })
    } else {
      self.setData({
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

  goOrders: function() {
    wx.navigateTo({ url: '/pages/orders/index' })
  },

  handleLogout: function() {
    wx.removeStorageSync('token')
    wx.removeStorageSync('user')
    this.loadUser()
    wx.showToast({ title: '已退出', icon: 'success' })
  }
})
