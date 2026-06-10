// pages/index/index.js
// 首页 - AI数字名片翻页画册展示
var api = require('../../utils/api')
var util = require('../../utils/util')
var auth = require('../../utils/auth')

Page({
  data: {
    loading: true,
    error: null,
    hasBrochure: false,
    // 翻页相关
    currentPage: 0,
    totalPages: 4,
    pages: [
      { type: 'cover', title: '个人封面' },
      { type: 'contact', title: '联系方式' },
      { type: 'company', title: '企业信息' },
      { type: 'qrcode', title: '二维码' }
    ],
    touchStartX: 0,
    touchStartY: 0,
    isSwiping: false,
    // 名片数据
    brochure: null,
    // 底部统计
    viewCount: 0
  },

  onLoad: function(options) {
    // 检查登录
    if (!auth.checkLogin()) {
      wx.reLaunch({ url: '/pages/login/index' })
      return
    }
    this.loadBrochure()
  },

  onShow: function() {
    if (auth.checkLogin()) {
      this.loadBrochure()
    }
  },

  loadBrochure: function() {
    var self = this
    self.setData({ loading: true })

    api.getMyBrochures().then(function(res) {
      var brochures = []
      if (res && res.data) {
        brochures = Array.isArray(res.data) ? res.data : (Array.isArray(res) ? res : [])
      } else if (Array.isArray(res)) {
        brochures = res
      }

      if (brochures.length > 0) {
        var brochure = brochures[0]
        self.setData({
          brochure: brochure,
          hasBrochure: true,
          viewCount: brochure.view_count || brochure.stats?.views || 0,
          loading: false
        })
      } else {
        self.setData({ loading: false, hasBrochure: false })
      }
    }).catch(function(e) {
      // 如果接口报错，尝试从本地storage读取
      var user = wx.getStorageSync('user')
      if (user && user.name) {
        self.setData({
          loading: false,
          hasBrochure: true,
          brochure: {
            name: user.name,
            company: user.company || '',
            position: user.position || '',
            bio: user.bio || '',
            avatar: user.avatar || '',
            phone: user.phone || '',
            email: user.email || '',
            wechat: user.wechat || '',
            purpose: user.purpose || '',
            provide_tags: user.provide_tags || [],
            need_tags: user.need_tags || []
          }
        })
      } else {
        self.setData({ loading: false, hasBrochure: false, error: '暂无名片数据' })
      }
    })
  },

  // === 翻页手势 ===
  onTouchStart: function(e) {
    this.setData({
      touchStartX: e.touches[0].clientX,
      touchStartY: e.touches[0].clientY,
      isSwiping: true
    })
  },

  onTouchEnd: function(e) {
    if (!this.data.isSwiping) return
    var dx = e.changedTouches[0].clientX - this.data.touchStartX
    var dy = e.changedTouches[0].clientY - this.data.touchStartY
    // 水平滑动阈值 50rpx，要求水平移动大于垂直移动
    if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      if (dx < 0 && this.data.currentPage < this.data.totalPages - 1) {
        this.nextPage()
      } else if (dx > 0 && this.data.currentPage > 0) {
        this.prevPage()
      }
    }
    this.setData({ isSwiping: false })
  },

  nextPage: function() {
    var cp = this.data.currentPage
    if (cp < this.data.totalPages - 1) {
      this.setData({ currentPage: cp + 1 })
    }
  },

  prevPage: function() {
    var cp = this.data.currentPage
    if (cp > 0) {
      this.setData({ currentPage: cp - 1 })
    }
  },

  // === 页面操作 ===
  goEdit: function() {
    wx.navigateTo({ url: '/pages/card-editor/index' })
  },

  goPreview: function() {
    wx.navigateTo({ url: '/pages/brochure-preview/index' })
  },

  // 分享（微信使用 onShareAppMessage 生命周期，非 wx.shareAppMessage）
  onShareAppMessage: function() {
    var brochure = this.data.brochure || {}
    return {
      title: brochure.name ? (brochure.name + '的数字名片') : 'AI数字名片',
      path: '/pages/index/index'
    }
  },

  handleContact: function() {
    // 触发匹配流程
    wx.switchTab({ url: '/pages/match/index' })
  },

  onCreateNew: function() {
    wx.navigateTo({ url: '/pages/card-editor/index' })
  }
})
