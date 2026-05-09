Page({
  data: {
    user: null,
    isLoggedIn: false,
    userName: '未登录',
    userInitial: '?',
    userRole: '\u666e\u901a\u7528\u6237',
    isPromoter: false,
    isSupplier: false
  },
  onLoad: function() { this.loadUser() },
  onShow: function() { this.loadUser() },
  loadUser: function() {
    var user = wx.getStorageSync('user')
    var self = this
    var roleText = '\u666e\u901a\u7528\u6237'
    if (user && user.role === 'promoter') roleText = '\u63a8\u5e7f\u5458'
    else if (user && user.role === 'supplier') roleText = '\u4ea7\u54c1\u65b9'
    if (user) {
      self.setData({
        user: user,
        isLoggedIn: true,
        userName: user.name || user.username || '\u672a\u767b\u5f55',
        userInitial: user.name ? user.name.charAt(0).toUpperCase() : '?',
        userRole: roleText,
        isPromoter: user.role === 'promoter',
        isSupplier: user.role === 'supplier'
      })
    } else {
      self.setData({
        user: null, isLoggedIn: false, userName: '\u672a\u767b\u5f55',
        userInitial: '?', userRole: '\u666e\u901a\u7528\u6237',
        isPromoter: false, isSupplier: false
      })
    }
  },
  goOrders: function() { wx.navigateTo({ url: '/pages/orders/index' }) },
  handleLogout: function() {
    wx.removeStorageSync('token')
    wx.removeStorageSync('user')
    this.loadUser()
    wx.showToast({ title: '\u5df2\u9000\u51fa', icon: 'success' })
  }
})
