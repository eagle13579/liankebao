// pages/mine/index.js
// 我的页面 - 名片管理 + 数据看板 + 会员中心 + 设置
var api = require('../../utils/api')
var auth = require('../../utils/auth')

Page({
  data: {
    user: null,
    isLoggedIn: false,
    userName: '未登录',
    userInitial: '?',
    userCompany: '',
    userPosition: '',
    membershipTier: '基础版',
    membershipBadge: '基础版',
    // 数据看板
    stats: {
      views: 0,
      matches: 0,
      contacts: 0
    },
    unreadCount: 0
  },

  onLoad: function() {
    this.loadData()
  },

  onShow: function() {
    this.loadData()
  },

  loadData: function() {
    this.loadUserInfo()
    this.loadStats()
  },

  loadUserInfo: function() {
    var self = this
    var user = wx.getStorageSync('user')

    if (user) {
      var tierMap = { 'free': '基础版', 'gold': '黄金会员', 'diamond': '钻石会员', 'board': '至尊会员' }
      var tier = tierMap[user.membership_tier] || '基础版'
      self.setData({
        user: user,
        isLoggedIn: true,
        userName: user.name || user.nickName || '未设置',
        userInitial: (user.name || user.nickName || '?')[0].toUpperCase(),
        userCompany: user.company || '',
        userPosition: user.position || '',
        membershipTier: tier,
        membershipBadge: user.membership_tier === 'vip' || user.membership_tier === 'premium' ? 'VIP' : '基础版'
      })
    } else {
      self.setData({
        user: null, isLoggedIn: false, userName: '未登录',
        userInitial: '?', userCompany: '', userPosition: '',
        membershipTier: '基础版', membershipBadge: '基础版'
      })
    }

    // 从后端获取最新信息
    api.getUserInfo().then(function(res) {
      var u = res.data || res
      if (u) {
        var tierMap = { 'free': '基础版', 'vip': 'VIP会员', 'premium': '高级版' }
        var tier = tierMap[u.membership_tier] || '基础版'
        self.setData({
          user: u,
          userName: u.name || u.nickName || self.data.userName,
          userInitial: (u.name || u.nickName || '?')[0].toUpperCase(),
          userCompany: u.company || '',
          userPosition: u.position || '',
          membershipTier: tier,
          membershipBadge: u.membership_tier === 'vip' || u.membership_tier === 'premium' ? 'VIP' : '基础版'
        })
        // 更新缓存
        var cachedUser = wx.getStorageSync('user') || {}
        cachedUser.name = u.name || cachedUser.name
        cachedUser.company = u.company || cachedUser.company
        cachedUser.position = u.position || cachedUser.position
        cachedUser.membership_tier = u.membership_tier || cachedUser.membership_tier
        wx.setStorageSync('user', cachedUser)
      }
    }).catch(function() {})
  },

  loadStats: function() {
    var self = this
    // 从后端获取统计数据
    api.get('/api/users/me/stats').then(function(res) {
      var s = res.data || res
      if (s) {
        self.setData({
          stats: {
            views: s.views || s.view_count || 0,
            matches: s.matches || s.match_count || 0,
            contacts: s.contacts || s.contact_count || 0
          }
        })
      }
    }).catch(function() {
      // 从本地缓存获取
      var user = wx.getStorageSync('user') || {}
      self.setData({
        stats: {
          views: user.view_count || 152,
          matches: user.match_count || 12,
          contacts: user.contact_count || 8
        }
      })
    })
  },

  loadUnreadCount: function() {
    var self = this
    api.get('/api/v1/notifications/unread-count').then(function(res) {
      var count = 0
      if (res && res.data) {
        count = parseInt(res.data.count !== undefined ? res.data.count : res.data)
      }
      self.setData({ unreadCount: count || 0 })
    }).catch(function() {})
  },

  // === 导航 ===
  goMyCard: function() {
    wx.switchTab({ url: '/pages/index/index' })
  },

  goEditCard: function() {
    wx.navigateTo({ url: '/pages/card-editor/index' })
  },

  goDataBoard: function() {
    wx.showModal({
      title: '数据看板',
      content: '浏览: ' + this.data.stats.views + ' 次\n匹配: ' + this.data.stats.matches + ' 次\n被联系: ' + this.data.stats.contacts + ' 次',
      showCancel: false
    })
  },

  goMembership: function() {
    var self = this
    wx.showActionSheet({
      itemList: ['💎 VIP会员 ¥99/月 - 无限解锁', '🎫 单次解锁券 ¥9.9/次'],
      success: function(res) {
        if (res.tapIndex === 0) {
          wx.showToast({ title: '即将开通会员...', icon: 'none' })
        } else {
          wx.showToast({ title: '即将购买解锁券...', icon: 'none' })
        }
      }
    })
  },

  goNotifications: function() {
    wx.showToast({ title: '消息中心', icon: 'none' })
  },

  goSettings: function() {
    wx.showActionSheet({
      itemList: ['编辑资料', '关于我们', '退出登录'],
      success: function(res) {
        if (res.tapIndex === 0) {
          wx.navigateTo({ url: '/pages/card-editor/index' })
        } else if (res.tapIndex === 1) {
          wx.showModal({
            title: '关于链客宝AI',
            content: '链客宝AI - AI数字名片\n用AI连接每一个商业机会\n版本 1.0.0',
            showCancel: false
          })
        } else if (res.tapIndex === 2) {
          self.handleLogout()
        }
      }.bind(this)
    })
  },

  goLogin: function() {
    wx.reLaunch({ url: '/pages/login/index' })
  },

  handleLogout: function() {
    var self = this
    wx.showModal({
      title: '提示',
      content: '确定退出登录？',
      success: function(res) {
        if (res.confirm) {
          auth.logout()
        }
      }
    })
  },

  handleUpgrade: function() {
    this.goMembership()
  }
})
