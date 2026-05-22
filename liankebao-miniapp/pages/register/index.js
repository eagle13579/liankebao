var api = require('../../utils/api')

Page({
  data: {
    username: '',
    password: '',
    name: '',
    mobile: '',
    company: '',
    position: '',
    role: 'business',
    agreed: false,
    submitting: false
  },
  onInput: function(e) {
    var field = e.currentTarget.dataset.field
    var obj = {}
    obj[field] = e.detail.value
    this.setData(obj)
  },
  selectRole: function(e) {
    this.setData({ role: e.currentTarget.dataset.role })
  },
  toggleAgree: function() {
    this.setData({ agreed: !this.data.agreed })
  },
  showAgreement: function() {
    wx.showModal({
      title: '用户服务协议',
      content: '欢迎使用链客宝平台。在使用本平台服务前，请您仔细阅读以下条款。通过注册或使用本平台，即表示您同意受本协议约束。本平台提供企业家供需匹配服务，包括但不限于AI名片、GEO诊断、数字分身等产品。',
      showCancel: false
    })
  },
  handleSubmit: function() {
    var self = this
    var d = self.data

    // 表单校验
    if (!d.username.trim()) {
      wx.showToast({ title: '请输入用户名', icon: 'none' })
      return
    }
    if (!d.password || d.password.length < 6) {
      wx.showToast({ title: '密码至少6位', icon: 'none' })
      return
    }
    if (!d.name.trim()) {
      wx.showToast({ title: '请输入姓名', icon: 'none' })
      return
    }
    if (!/^1\d{10}$/.test(d.mobile)) {
      wx.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }

    self.setData({ submitting: true })

    api.post('/auth/register', {
      username: d.username.trim(),
      password: d.password,
      name: d.name.trim(),
      mobile: d.mobile.trim(),
      company: d.company.trim(),
      position: d.position.trim(),
      role: d.role
    }).then(function(res) {
      self.setData({ submitting: false })
      if (res.code === 200) {
        wx.showToast({ title: '注册成功', icon: 'success' })
        // 保存用户信息
        if (res.data && res.data.token) {
          wx.setStorageSync('token', res.data.token)
        }
        if (res.data && res.data.user) {
          wx.setStorageSync('user', res.data.user)
        }
        // 返回首页
        wx.switchTab({ url: '/pages/index/index' })
      } else {
        wx.showToast({ title: res.message || '注册失败', icon: 'error' })
      }
    }).catch(function() {
      self.setData({ submitting: false })
      wx.showToast({ title: '网络错误', icon: 'error' })
    })
  },
  goLogin: function() {
    wx.navigateTo({ url: '/pages/login/index' })
  }
})
