// pages/login/index.js
// 登录页 - 微信一键登录 + 手机号登录 + 隐私弹窗
var auth = require('../../utils/auth')
var api = require('../../utils/api')

Page({
  data: {
    mode: 'main',       // main | phone
    phone: '',
    code: '',
    codeSent: false,
    countdown: 0,
    agreePolicy: false,  // 默认不同意，需用户主动勾选
    loading: false,
    showPrivacyPopup: false,  // 隐私弹窗
    privacyResolve: null      // 隐私授权 resolve
  },

  onLoad: function() {
    var self = this
    // 如果已登录则跳转
    if (auth.checkLogin()) {
      wx.switchTab({ url: '/pages/index/index' })
      return
    }

    // 微信隐私协议处理（2023年9月15日起必需）
    if (wx.onNeedPrivacyAuthorization) {
      wx.onNeedPrivacyAuthorization(function(resolve) {
        self.setData({
          showPrivacyPopup: true,
          privacyResolve: resolve
        })
      })
    }

    // 检查隐私授权状态
    if (wx.getPrivacySetting) {
      wx.getPrivacySetting({
        success: function(res) {
          if (res.needAuthorization) {
            // 需要授权，显示隐私弹窗
            self.setData({ showPrivacyPopup: true })
          }
        }
      })
    }
  },

  // 同意隐私协议
  handleAgreePrivacy: function() {
    var self = this
    // 调用微信隐私授权 resolve
    if (self.data.privacyResolve) {
      self.data.privacyResolve({
        buttonId: 'agree-privacy-btn',
        event: 'agree'
      })
    }
    self.setData({
      showPrivacyPopup: false,
      agreePolicy: true,
      privacyResolve: null
    })
  },

  // 拒绝隐私协议
  handleRejectPrivacy: function() {
    var self = this
    if (self.data.privacyResolve) {
      self.data.privacyResolve({
        buttonId: 'reject-privacy-btn',
        event: 'disagree'
      })
    }
    self.setData({
      showPrivacyPopup: false,
      agreePolicy: false,
      privacyResolve: null
    })
    wx.showToast({ title: '需同意隐私政策才能使用服务', icon: 'none' })
  },

  // 微信一键登录
  handleWechatLogin: function() {
    var self = this
    if (!self.data.agreePolicy) {
      wx.showToast({ title: '请先同意用户协议和隐私政策', icon: 'none' })
      return
    }
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
    if (!self.data.agreePolicy) {
      wx.showToast({ title: '请先同意用户协议和隐私政策', icon: 'none' })
      return
    }
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
    var content = ''
    if (type === 'user') {
      content = '链客宝AI用户服务协议\n\n1. 服务条款\n欢迎使用链客宝AI企业家供需匹配平台。使用本服务即表示您同意本协议。\n\n2. 用户义务\n您应提供真实、准确的注册信息，不得利用本平台从事违法活动。\n\n3. 知识产权\n平台所有内容的知识产权归链客宝AI所有。\n\n4. 免责声明\n平台仅提供信息撮合服务，交易风险由交易双方自行承担。'
    } else {
      content = '链客宝AI隐私政策摘要\n\n1. 我们收集手机号、微信昵称、头像用于注册认证\n2. 我们收集名片信息用于供需匹配\n3. 我们收集订单信息用于交易履约\n4. 我们不会出售您的个人信息\n5. 您可以随时在「我的→设置」中注销账户\n\n完整隐私政策请访问：\nhttps://www.go-aiport.com/privacy'
    }
    wx.showModal({
      title: type === 'user' ? '用户服务协议' : '隐私政策',
      content: content,
      showCancel: false,
      confirmText: '我知道了'
    })
  }
})
