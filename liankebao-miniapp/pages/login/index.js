// pages/login/index.js
// 登录页 - 微信一键登录 + 手机号登录
var auth = require('../../utils/auth')
var api = require('../../utils/api')

Page({
  data: {
    mode: 'main',       // main | phone
    phone: '',
    code: '',
    codeSent: false,
    countdown: 0,
    agreePolicy: true,
    loading: false
  },

  onLoad: function() {
    // 如果已登录则跳转
    if (auth.checkLogin()) {
      wx.switchTab({ url: '/pages/index/index' })
    }
  },

  // 微信一键登录
  handleWechatLogin: function() {
    var self = this
    self.setData({ loading: true })
    auth.wxLogin().then(function() {
      self.setData({ loading: false })
      wx.showToast({ title: '登录成功', icon: 'success' })
      wx.switchTab({ url: '/pages/index/index' })
    }).catch(function(err) {
      self.setData({ loading: false })
      wx.showToast({ title: err.message || err || '登录失败', icon: 'none' })
    })
  },

  // 切换到手机号登录
  switchToPhone: function() {
    this.setData({ mode: 'phone', phone: '', code: '', codeSent: false })
  },

  // 返回主页面
  backToMain: function() {
    this.setData({ mode: 'main' })
  },

  // 手机号输入
  onPhoneInput: function(e) {
    this.setData({ phone: e.detail.value })
  },

  // 验证码输入
  onCodeInput: function(e) {
    this.setData({ code: e.detail.value })
  },

  // 发送验证码
  sendCode: function() {
    var self = this
    var phone = this.data.phone.trim()
    if (!phone || phone.length < 11) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' })
      return
    }
    self.setData({ loading: true })
    // 调用后端发送验证码
    api.post('/api/auth/send-code', { phone: phone }).then(function(res) {
      self.setData({ loading: false, codeSent: true })
      self.startCountdown()
      wx.showToast({ title: '验证码已发送', icon: 'success' })
    }).catch(function(err) {
      self.setData({ loading: false })
      wx.showToast({ title: err.message || '发送失败', icon: 'none' })
    })
  },

  // 倒计时
  startCountdown: function() {
    var self = this
    self.setData({ countdown: 60 })
    var timer = setInterval(function() {
      var cd = self.data.countdown - 1
      if (cd <= 0) {
        clearInterval(timer)
        self.setData({ countdown: 0, codeSent: false })
      } else {
        self.setData({ countdown: cd })
      }
    }, 1000)
  },

  // 手机号登录
  handlePhoneLogin: function() {
    var self = this
    var phone = this.data.phone.trim()
    var code = this.data.code.trim()
    if (!phone || phone.length < 11) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' })
      return
    }
    if (!code || code.length < 4) {
      wx.showToast({ title: '请输入验证码', icon: 'none' })
      return
    }
    self.setData({ loading: true })
    api.phoneLogin(phone, code).then(function(res) {
      self.setData({ loading: false })
      wx.showToast({ title: '登录成功', icon: 'success' })
      wx.switchTab({ url: '/pages/index/index' })
    }).catch(function(err) {
      self.setData({ loading: false })
      wx.showToast({ title: err.message || '登录失败', icon: 'none' })
    })
  },

  // 同意协议
  toggleAgree: function() {
    this.setData({ agreePolicy: !this.data.agreePolicy })
  },

  // 查看协议
  viewPolicy: function(e) {
    var type = e.currentTarget.dataset.type || 'user'
    wx.showModal({
      title: type === 'user' ? '用户协议' : '隐私政策',
      content: '这里是链客宝用户协议/隐私政策的详细内容...',
      showCancel: false
    })
  }
})
