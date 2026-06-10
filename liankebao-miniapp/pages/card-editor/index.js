// pages/card-editor/index.js
// 填单页 - 四步向导：上传名片 → 填写信息 → 预览 → 发布
var api = require('../../utils/api')

Page({
  data: {
    step: 1,
    maxSteps: 4,
    submitting: false,
    uploadedImage: '',
    purpose: '',               // 名片用途
    form: {
      name: '',
      phone: '',
      email: '',
      wechat: '',
      company: '',
      position: '',
      bio: '',
      provide: '',             // 我能提供
      need: '',                // 我需要
      images: []               // 图片列表
    },
    purposeOptions: [
      { value: '找合作伙伴', icon: '🤝', label: '找合作伙伴' },
      { value: '找客户', icon: '💰', label: '找客户' },
      { value: '找投资人', icon: '📈', label: '找投资人' },
      { value: '找供应商', icon: '🔧', label: '找供应商' }
    ],
    previewData: null,
    stepLabels: ['上传名片', '填写信息', '预览画册', '发布'],
    // 预计算的标签数组（供WXML使用，不能在模板内做split）
    provideTags: [],
    needTags: []
  },

  // 从form.provide字符串更新provideTags数组
  _updateTagArrays: function() {
    var p = this.data.form.provide || ''
    var n = this.data.form.need || ''
    var pt = p ? p.split(/[,，、\s]+/).filter(function(t) { return t.trim() }) : []
    var nt = n ? n.split(/[,，、\s]+/).filter(function(t) { return t.trim() }) : []
    this.setData({ provideTags: pt, needTags: nt })
  },

  onLoad: function(options) {
    // 如果有 editId，加载已有画册数据
    if (options.editId) {
      this.loadExistingBrochure(options.editId)
    }
  },

  loadExistingBrochure: function(id) {
    var self = this
    api.getMyBrochures().then(function(res) {
      var brochures = []
      if (res && res.data) {
        brochures = Array.isArray(res.data) ? res.data : (Array.isArray(res) ? res : [])
      } else if (Array.isArray(res)) {
        brochures = res
      }
      var target = brochures.find(function(b) { return b.id == id || b._id == id })
      if (target) {
        self.setData({
          form: {
            name: target.name || '',
            phone: target.phone || '',
            email: target.email || '',
            wechat: target.wechat || '',
            company: target.company || '',
            position: target.position || '',
            bio: target.bio || '',
            provide: Array.isArray(target.provide_tags) ? target.provide_tags.join(', ') : (target.provide || ''),
            need: Array.isArray(target.need_tags) ? target.need_tags.join(', ') : (target.need || ''),
            images: target.images || []
          },
          purpose: target.purpose || '',
          uploadedImage: target.card_image || ''
        })
      }
    }).catch(function() {})
  },

  // === 步骤导航 ===
  nextStep: function() {
    var s = this.data.step
    // Step1: 验证用途
    if (s === 1 && !this.data.purpose) {
      wx.showToast({ title: '请选择名片用途', icon: 'none' })
      return
    }
    if (s < this.data.maxSteps) {
      this.setData({ step: s + 1 })
    }
    if (s === 2) {
      // Step2→3: 生成预览数据
      this.generatePreview()
    }
  },

  prevStep: function() {
    var s = this.data.step
    if (s > 1) this.setData({ step: s - 1 })
  },

  goBack: function() {
    wx.navigateBack({ delta: 1 })
  },

  // === Step1: 上传名片 + 选择用途 ===
  uploadImage: function() {
    var self = this
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: function(res) {
        var tempFile = res.tempFiles[0]
        self.setData({ uploadedImage: tempFile.tempFilePath })
        wx.showToast({ title: '上传成功', icon: 'success' })
        // 模拟AI提取字段
        self.mockAIExtract()
      }
    })
  },

  selectPurpose: function(e) {
    var val = e.currentTarget.dataset.value
    this.setData({ purpose: val })
  },

  // 模拟AI提取
  mockAIExtract: function() {
    wx.showLoading({ title: 'AI识别中...' })
    var self = this
    setTimeout(function() {
      wx.hideLoading()
      var user = wx.getStorageSync('user') || {}
      self.setData({
        'form.name': user.name || '张三',
        'form.company': user.company || '示例科技有限公司',
        'form.position': user.position || '产品经理',
        'form.phone': user.phone || '13800138000',
        'form.email': user.email || 'zhang@example.com',
        'form.bio': user.bio || '专注AI与数字化领域'
      })
      self.setData({ step: 2 })
      wx.showToast({ title: 'AI提取完成，请核对', icon: 'success' })
    }, 1500)
  },

  // === Step2: 表单输入 ==>
  onInput: function(e) {
    var field = e.currentTarget.dataset.field
    var value = e.detail.value
    this.setData({ ['form.' + field]: value })
    // 供需字段变更时更新标签数组
    if (field === 'provide' || field === 'need') {
      this._updateTagArrays()
    }
  },

  // 选择多图片
  chooseImages: function() {
    var self = this
    var remain = 9 - (self.data.form.images || []).length
    if (remain <= 0) {
      wx.showToast({ title: '最多上传9张', icon: 'none' })
      return
    }
    wx.chooseMedia({
      count: remain,
      mediaType: ['image'],
      sourceType: ['album'],
      success: function(res) {
        var newImages = (self.data.form.images || []).slice()
        for (var i = 0; i < res.tempFiles.length; i++) {
          newImages.push(res.tempFiles[i].tempFilePath)
        }
        self.setData({ 'form.images': newImages })
      }
    })
  },

  removeImage: function(e) {
    var idx = e.currentTarget.dataset.index
    var images = this.data.form.images.slice()
    images.splice(idx, 1)
    this.setData({ 'form.images': images })
  },

  // 预览数据生成
  generatePreview: function() {
    var f = this.data.form
    var provideTags = f.provide ? f.provide.split(/[,，、\s]+/).filter(function(t) { return t.trim() }) : []
    var needTags = f.need ? f.need.split(/[,，、\s]+/).filter(function(t) { return t.trim() }) : []

    this.setData({
      previewData: {
        name: f.name,
        phone: f.phone,
        email: f.email,
        wechat: f.wechat,
        company: f.company,
        position: f.position,
        bio: f.bio,
        purpose: this.data.purpose,
        provide_tags: provideTags,
        need_tags: needTags,
        images: f.images
      }
    })
  },

  // === Step4: 发布 ===
  publish: function() {
    var self = this
    if (self.data.submitting) return
    self.setData({ submitting: true })

    var f = self.data.form
    var provideTags = f.provide ? f.provide.split(/[,，、\s]+/).filter(function(t) { return t.trim() }) : []
    var needTags = f.need ? f.need.split(/[,，、\s]+/).filter(function(t) { return t.trim() }) : []

    var payload = {
      name: f.name,
      phone: f.phone,
      email: f.email,
      wechat: f.wechat,
      company: f.company,
      position: f.position,
      bio: f.bio,
      purpose: self.data.purpose,
      provide_tags: provideTags,
      need_tags: needTags
    }

    wx.showLoading({ title: '发布中...' })

    api.createBrochure(payload).then(function(res) {
      wx.hideLoading()
      self.setData({ submitting: false })
      wx.showToast({ title: '发布成功', icon: 'success' })

      // 更新本地用户信息
      var user = wx.getStorageSync('user') || {}
      user.name = f.name
      user.company = f.company
      user.position = f.position
      user.phone = f.phone
      user.provide_tags = provideTags
      user.need_tags = needTags
      wx.setStorageSync('user', user)

      // 跳转至匹配页
      setTimeout(function() {
        wx.switchTab({ url: '/pages/match/index' })
      }, 1000)
    }).catch(function(err) {
      wx.hideLoading()
      self.setData({ submitting: false })
      wx.showToast({ title: err.message || '发布失败', icon: 'none' })
    })
  },

  // 预览跳转
  goPreview: function() {
    // 保存到storage供预览页读取
    wx.setStorageSync('preview_data', this.data.previewData)
    wx.navigateTo({ url: '/pages/brochure-preview/index' })
  }
})
