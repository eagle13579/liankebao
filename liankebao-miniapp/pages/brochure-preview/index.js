// pages/brochure-preview/index.js
// 画册预览页 - 翻页H5查看
var auth = require('../../utils/auth')

Page({
  data: {
    currentPage: 0,
    totalPages: 3,
    touchStartX: 0,
    isSwiping: false,
    brochure: null
  },

  onLoad: function(options) {
    var previewData = wx.getStorageSync('preview_data')
    if (previewData) {
      this.setData({ brochure: previewData })
    } else {
      // 从本地用户数据构造预览
      var user = wx.getStorageSync('user') || {}
      this.setData({
        brochure: {
          name: user.name || '未填写',
          company: user.company || '',
          position: user.position || '',
          bio: user.bio || '',
          phone: user.phone || '',
          email: user.email || '',
          wechat: user.wechat || '',
          purpose: user.purpose || '',
          provide_tags: user.provide_tags || [],
          need_tags: user.need_tags || [],
          images: []
        }
      })
    }
  },

  // === 翻页手势 ===
  onTouchStart: function(e) {
    this.setData({
      touchStartX: e.touches[0].clientX,
      isSwiping: true
    })
  },

  onTouchEnd: function(e) {
    if (!this.data.isSwiping) return
    var dx = e.changedTouches[0].clientX - this.data.touchStartX
    if (Math.abs(dx) > 80) {
      if (dx < 0 && this.data.currentPage < this.data.totalPages - 1) {
        this.setData({ currentPage: this.data.currentPage + 1 })
      } else if (dx > 0 && this.data.currentPage > 0) {
        this.setData({ currentPage: this.data.currentPage - 1 })
      }
    }
    this.setData({ isSwiping: false })
  },

  // === 操作 ===
  goBackEdit: function() {
    wx.navigateBack({ delta: 1 })
  },

  goPublish: function() {
    // 返回编辑器并跳到Step4
    wx.navigateBack({ delta: 1 })
    // 通过event或storage通知发布
  }
})
