App({
  onLaunch: function() {
    // 检查登录状态
    var token = wx.getStorageSync('token')
    if (token) {
      this.globalData.isLoggedIn = true
    }
  },
  onShow: function() {
    // 小程序从后台切前台时刷新用户状态
    var token = wx.getStorageSync('token')
    this.globalData.isLoggedIn = !!token
  },
  globalData: {
    isLoggedIn: false,
    userInfo: null
  }
})
