var api = require('../../utils/api')

Page({
  data: {
    user: null,
    isLoggedIn: false,
    userName: '未登录',
    userInitial: '?',
    userRole: '普通用户',
    isPromoter: false,
    isSupplier: false,
    unreadCount: 0
  },
  onLoad: function() { this.loadUser(); this.loadUnreadCount() },
  onShow: function() { this.loadUser(); this.loadUnreadCount() },
  loadUser: function() {
    var user = wx.getStorageSync('user')
    var self = this
    var roleText = '普通用户'
    if (user && user.role === 'promoter') roleText = '推广员'
    else if (user && user.role === 'supplier') roleText = '产品方'
    if (user) {
      self.setData({
        user: user,
        isLoggedIn: true,
        userName: user.name || user.username || '未登录',
        userInitial: user.name ? user.name.charAt(0).toUpperCase() : '?',
        userRole: roleText,
        isPromoter: user.role === 'promoter',
        isSupplier: user.role === 'supplier'
      })
    } else {
      self.setData({
        user: null, isLoggedIn: false, userName: '未登录',
        userInitial: '?', userRole: '普通用户',
        isPromoter: false, isSupplier: false
      })
    }
  },
  loadUnreadCount: function() {
    var self = this
    api.get('/api/notifications/unread-count').then(function(res) {
      var count = 0
      if (res && res.code === 200 && res.data) {
        count = parseInt(res.data.count !== undefined ? res.data.count : res.data)
      } else if (res && res.count !== undefined) {
        count = parseInt(res.count)
      }
      self.setData({ unreadCount: count || 0 })
    }).catch(function() {
      // silent
    })
  },
  goOrders: function() { wx.navigateTo({ url: '/pages/orders/index' }) },
  goNotifications: function() { wx.navigateTo({ url: '/pages/notifications/index' }) },
  goPartnerPolicy: function() { wx.navigateTo({ url: '/pages/partner-policy/index' }) },
  goPromotion: function() { wx.navigateTo({ url: '/pages/promotion/index' }) },
  goManageProducts: function() { wx.navigateTo({ url: '/pages/manage-products/index' }) },
  goAddress: function() {
    wx.navigateTo({ url: '/pages/address/index' })
  },
  goAbout: function() {
    wx.showModal({
      title: '关于链客宝',
      content: '链客宝 - 企业家的AI营销朋友圈\n版本 1.0.0',
      showCancel: false
    })
  },
  handleLogout: function() {
    var self = this
    wx.showModal({
      title: '提示',
      content: '确定退出登录？',
      success: function(res) {
        if (res.confirm) {
          wx.removeStorageSync('token')
          wx.removeStorageSync('user')
          self.loadUser()
          wx.showToast({ title: '已退出', icon: 'success' })
        }
      }
    })
  }
})
