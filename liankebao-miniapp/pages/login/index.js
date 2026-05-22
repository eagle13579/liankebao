var api = require('../../utils/api')

Page({
  data: {
    mode: 'wechat',
    username: '',
    password: ''
  },

  // 模式切换
  switchMode: function() {
    this.setData({
      mode: this.data.mode === 'wechat' ? 'account' : 'wechat',
      username: '',
      password: ''
    })
  },

  // 用户名输入
  onUsernameInput: function(e) {
    this.setData({ username: e.detail.value })
  },

  // 密码输入
  onPasswordInput: function(e) {
    this.setData({ password: e.detail.value })
  },

  // 微信一键登录
  handleWechatLogin: function() {
    wx.showLoading({ title: '登录中...' })
    var self = this
    api.loginWithWechat().then(function() {
      wx.hideLoading()
      wx.showToast({ title: '登录成功', icon: 'success' })
      wx.switchTab({ url: '/pages/index/index' })
    }, function(e) {
      wx.hideLoading()
      wx.showToast({ title: e || '登录失败', icon: 'error' })
    })
  },

  // 账号密码登录
  handleAccountLogin: function() {
    var self = this
    var username = this.data.username.trim()
    var password = this.data.password

    if (!username) {
      wx.showToast({ title: '请输入用户名', icon: 'none' })
      return
    }
    if (!password) {
      wx.showToast({ title: '请输入密码', icon: 'none' })
      return
    }

    wx.showLoading({ title: '登录中...' })
    api.post('/auth/login', {
      username: username,
      password: password
    }).then(function(res) {
      wx.hideLoading()
      if (res.code === 200) {
        wx.setStorageSync('token', res.data.token)
        wx.setStorageSync('user', res.data.user)
        wx.showToast({ title: '登录成功', icon: 'success' })
        wx.switchTab({ url: '/pages/index/index' })
      } else {
        wx.showToast({ title: res.message || '登录失败', icon: 'error' })
      }
    })
  },

  // 前往注册
  goToRegister: function() {
    wx.navigateTo({ url: '/pages/register/index' })
  }
})
