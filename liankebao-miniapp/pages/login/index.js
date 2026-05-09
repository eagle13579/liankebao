const api = require('../../utils/api')
Page({
  handleWechatLogin() {
    wx.showLoading({ title: '登录中...' })
    api.loginWithWechat().then(() => {
      wx.hideLoading()
      wx.showToast({ title: '登录成功', icon: 'success' })
      wx.switchTab({ url: '/pages/index/index' })
    }).catch(e => {
      wx.hideLoading()
      wx.showToast({ title: e || '登录失败', icon: 'error' })
    })
  }
})
